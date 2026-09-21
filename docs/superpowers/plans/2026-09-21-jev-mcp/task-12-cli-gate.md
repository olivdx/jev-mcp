# Task 12 — Headless `jev-mcp gate`

**Deliverable:** The same pipeline Cursor drives over MCP, runnable from a git hook or CI, with exit codes a shell can branch on.

**Files:**
- Create: `src/jev_mcp/cli/gate.py`
- Modify: `src/jev_mcp/cli/main.py` (register `gate`)
- Create: `tests/test_cli_gate.py`

**Interfaces:**
- Consumes: `handle_collect_git`, `handle_run_tests`, `handle_decide`, `create_app_state` (task 11).
- Produces: `gate_cmd`, `EXIT_CODES`.

**Exit codes:**

| Outcome | Code |
|---------|------|
| `done` | 0 |
| `fix` | 1 |
| `ask` | 2 |
| `JevMcpError` | 3 |

**Behavior:** `collect_git`, then `run_tests` unless `--no-tests`, then `decide`. A missing test command is not fatal — the run continues with `tests` omitted, which `decide` records in `missing_signals`. Under `--profile ci` that absence is what turns the verdict into `fix`.

---

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_gate.py
import json

import pytest
from typer.testing import CliRunner

from jev_mcp.cli.main import app
from jev_mcp.errors import ApiUnreachableError

runner = CliRunner()


def _verdict(action: str, confidence: float = 0.9) -> dict:
    return {
        "schema_version": "1.0",
        "request_id": "test",
        "duration_ms": 1,
        "errors": [],
        "action": action,
        "confidence": confidence,
        "reasons": [f"routed to {action}"],
        "policy_trace": [f"route:{action}"],
        "missing_signals": [],
        "jev": {
            "model": "jev-1.13",
            "questionset_id": "engineering-gate-v2",
            "policy_id": "policy-engineering-gate-v2",
            "answers": {},
        },
    }


@pytest.fixture
def stub_pipeline(monkeypatch):
    """Replace the three handlers so the gate runs without git, tests, or network."""
    calls: dict = {}

    async def fake_git(state, **kwargs):
        calls["git"] = kwargs
        return {"diff": "+x", "changed_files": ["a.py"]}

    async def fake_tests(state, **kwargs):
        calls["tests"] = kwargs
        return {"exit_code": 0, "timed_out": False}

    async def fake_decide(state, **kwargs):
        calls["decide"] = kwargs
        return _verdict(calls.get("action", "done"))

    monkeypatch.setattr("jev_mcp.cli.gate.handle_collect_git", fake_git)
    monkeypatch.setattr("jev_mcp.cli.gate.handle_run_tests", fake_tests)
    monkeypatch.setattr("jev_mcp.cli.gate.handle_decide", fake_decide)
    return calls


@pytest.mark.parametrize(("action", "code"), [("done", 0), ("fix", 1), ("ask", 2)])
def test_exit_code_follows_the_action(stub_pipeline, monkeypatch, tmp_path, action, code):
    async def fake_decide(state, **kwargs):
        return _verdict(action)

    monkeypatch.setattr("jev_mcp.cli.gate.handle_decide", fake_decide)
    result = runner.invoke(app, ["gate", "--goal", "g", "--project-root", str(tmp_path)])
    assert result.exit_code == code


def test_json_output_is_the_decide_envelope(stub_pipeline, tmp_path):
    result = runner.invoke(
        app, ["gate", "--goal", "g", "--project-root", str(tmp_path), "--json"]
    )
    payload = json.loads(result.stdout)
    assert payload["action"] == "done"
    assert payload["jev"]["policy_id"] == "policy-engineering-gate-v2"


def test_human_output_shows_action_and_reason(stub_pipeline, tmp_path):
    result = runner.invoke(app, ["gate", "--goal", "g", "--project-root", str(tmp_path)])
    assert "DONE" in result.stdout
    assert "routed to done" in result.stdout


def test_no_tests_skips_the_runner(stub_pipeline, tmp_path):
    runner.invoke(
        app, ["gate", "--goal", "g", "--project-root", str(tmp_path), "--no-tests"]
    )
    assert "tests" not in stub_pipeline
    assert stub_pipeline["decide"]["tests"] is None


def test_missing_test_command_is_not_fatal(stub_pipeline, monkeypatch, tmp_path):
    from jev_mcp.errors import NoTestCommandError

    async def no_command(state, **kwargs):
        raise NoTestCommandError("nothing to run")

    monkeypatch.setattr("jev_mcp.cli.gate.handle_run_tests", no_command)
    result = runner.invoke(app, ["gate", "--goal", "g", "--project-root", str(tmp_path)])
    assert result.exit_code == 0
    assert stub_pipeline["decide"]["tests"] is None


def test_options_reach_the_handlers(stub_pipeline, tmp_path):
    runner.invoke(
        app,
        [
            "gate",
            "--goal",
            "ship it",
            "--project-root",
            str(tmp_path),
            "--profile",
            "strict",
            "--base-ref",
            "main",
            "--test-command",
            "pytest -q tests",
        ],
    )
    assert stub_pipeline["git"]["base_ref"] == "main"
    assert stub_pipeline["tests"]["command"] == ["pytest", "-q", "tests"]
    assert stub_pipeline["decide"]["profile"] == "strict"
    assert stub_pipeline["decide"]["goal"] == "ship it"


def test_tool_errors_exit_with_three(monkeypatch, tmp_path):
    async def unreachable(state, **kwargs):
        raise ApiUnreachableError()

    async def fake_git(state, **kwargs):
        return {"diff": "", "changed_files": []}

    monkeypatch.setattr("jev_mcp.cli.gate.handle_collect_git", fake_git)
    monkeypatch.setattr("jev_mcp.cli.gate.handle_decide", unreachable)
    result = runner.invoke(
        app, ["gate", "--goal", "g", "--project-root", str(tmp_path), "--no-tests"]
    )
    assert result.exit_code == 3
    assert "API_UNREACHABLE" in result.output
```

- [ ] **Step 2: Run and confirm failure**

Run: `poetry run pytest tests/test_cli_gate.py -v`

Expected: `No such command 'gate'`.

- [ ] **Step 3: Implement `cli/gate.py`**

```python
# src/jev_mcp/cli/gate.py
from __future__ import annotations

import asyncio
import json
import shlex
from pathlib import Path
from typing import Annotated

import typer

from jev_mcp.config import load_config
from jev_mcp.errors import JevMcpError, NoTestCommandError
from jev_mcp.logger import configure
from jev_mcp.mcp.tools import (
    AppState,
    create_app_state,
    handle_collect_git,
    handle_decide,
    handle_run_tests,
)

EXIT_CODES = {"done": 0, "fix": 1, "ask": 2}
ERROR_EXIT_CODE = 3


async def _run_pipeline(
    state: AppState,
    *,
    goal: str,
    project_root: Path,
    profile: str | None,
    base_ref: str | None,
    test_command: list[str] | None,
    skip_tests: bool,
) -> dict:
    root = str(project_root)
    git_payload = await handle_collect_git(state, project_root=root, base_ref=base_ref)

    tests_payload = None
    if not skip_tests:
        try:
            tests_payload = await handle_run_tests(
                state, project_root=root, command=test_command
            )
        except NoTestCommandError:
            # Absent tests are a missing signal, not a failure; the profile decides what that means.
            tests_payload = None

    return await handle_decide(
        state,
        goal=goal,
        git=git_payload,
        tests=tests_payload,
        project_root=root,
        profile=profile,
    )


def gate_cmd(
    goal: Annotated[str, typer.Option("--goal", help="What the change was supposed to do")],
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Repository root")
    ] = Path.cwd(),
    profile: Annotated[
        str | None, typer.Option("--profile", help="default, strict, or ci")
    ] = None,
    base_ref: Annotated[
        str | None, typer.Option("--base-ref", help="Diff against this ref")
    ] = None,
    test_command: Annotated[
        str | None, typer.Option("--test-command", help="Override the detected test command")
    ] = None,
    no_tests: Annotated[bool, typer.Option("--no-tests", help="Skip the test run")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Print the raw envelope")] = False,
) -> None:
    """Run collect_git, run_tests, and decide, then exit 0 for done, 1 for fix, 2 for ask."""
    cfg = load_config()
    configure(cfg.log_level, cfg.log_format, cfg.log_redact)
    state = create_app_state(cfg)

    try:
        payload = asyncio.run(
            _run_pipeline(
                state,
                goal=goal,
                project_root=project_root,
                profile=profile,
                base_ref=base_ref,
                test_command=shlex.split(test_command) if test_command else None,
                skip_tests=no_tests,
            )
        )
    except JevMcpError as exc:
        typer.echo(f"[{exc.code}] {exc.message}", err=True)
        raise typer.Exit(code=ERROR_EXIT_CODE) from exc

    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(f"{payload['action'].upper()}  confidence={payload['confidence']}")
        for reason in payload["reasons"]:
            typer.echo(f"  - {reason}")
        if payload["missing_signals"]:
            typer.echo(f"  missing: {', '.join(payload['missing_signals'])}")

    raise typer.Exit(code=EXIT_CODES.get(payload["action"], ERROR_EXIT_CODE))
```

- [ ] **Step 4: Register the command in `cli/main.py`**

```python
from jev_mcp.cli.gate import gate_cmd

app.command("serve")(serve_cmd)
app.command("gate")(gate_cmd)
app.add_typer(key_app)
```

- [ ] **Step 5: Run the tests**

Run: `poetry run pytest tests/test_cli_gate.py -v`

Expected: 11 passed (3 parametrized exit-code cases plus 8 others).

- [ ] **Step 6: Manual smoke against this repository**

Run: `poetry run jev-mcp gate --goal "verify the gate wiring" --project-root . --no-tests --json`

Expected: either a JSON envelope, or `[NOT_CONFIGURED] ...` with exit code 3 when no key is configured. Both prove the wiring; only the first needs a real key.

- [ ] **Step 7: Commit**

```bash
git add src/jev_mcp/cli tests/test_cli_gate.py
git commit -m "feat: add headless jev-mcp gate with CI-friendly exit codes"
```
