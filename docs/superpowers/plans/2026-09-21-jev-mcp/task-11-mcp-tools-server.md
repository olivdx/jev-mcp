# Task 11 — MCP handlers and FastMCP server

**Deliverable:** Five live MCP tools. `server.py` stays thin; all logic lives in `tools.py` handlers that the CLI reuses in task 12.

**Files:**
- Create: `src/jev_mcp/mcp/tools.py`
- Modify: `src/jev_mcp/mcp/server.py` (replace the task 1 stub)
- Modify: `tests/conftest.py` (add the `app_state` fixture)
- Create: `tests/test_mcp_tools.py`, `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: everything from tasks 2 through 10.
- Produces: `AppState`, `create_app_state`, `handle_collect_git`, `handle_run_tests`, `handle_decide`, `handle_health`, `handle_describe`, `create_mcp_app`, `run_server`.

**Conventions:**
- Every handler wraps its body in `_Timer`, which emits `tool_start` / `tool_end` and supplies `request_id` and `duration_ms`.
- Handlers raise `JevMcpError`; the FastMCP tool functions convert it to `RuntimeError("[CODE] message")`.
- `handle_decide` validates the profile **before** calling Jev, so a typo never costs an API request.
- `describe` is generated from `build_questions()` and the policy constants, so it cannot drift from behavior.

---

- [ ] **Step 1: Add the `app_state` fixture to `tests/conftest.py`**

```python
@pytest.fixture
def app_state():
    from jev_mcp.config import load_config
    from jev_mcp.mcp.tools import create_app_state

    return create_app_state(load_config(use_user_file=False))
```

- [ ] **Step 2: Write the failing handler tests**

```python
# tests/test_mcp_tools.py
import pytest

from jev_mcp.errors import InvalidProfileError, JevMcpError, NotConfiguredError
from jev_mcp.jev.answers import ChoiceAnswer, JevAnswers, ScoreAnswer
from jev_mcp.mcp.tools import (
    handle_collect_git,
    handle_decide,
    handle_describe,
    handle_health,
    handle_run_tests,
)

CLEAN_ANSWERS = JevAnswers(
    model="jev-1.13",
    nouls={
        "goal_addressed": 0.95,
        "goal_ambiguous": 0.05,
        "tests_blocking": 0.05,
        "incomplete_work": 0.05,
        "scope_creep": 0.05,
    },
    choices={"next_action": ChoiceAnswer("done", 0.9)},
    scores={"risk_regression": ScoreAnswer(0.3, 0.9, 3)},
)


def assert_envelope(payload: dict) -> None:
    assert payload["schema_version"] == "1.0"
    assert payload["request_id"]
    assert payload["duration_ms"] >= 0
    assert payload["errors"] == []


async def test_collect_git_returns_an_enveloped_snapshot(app_state, git_repo):
    payload = await handle_collect_git(app_state, project_root=str(git_repo))
    assert_envelope(payload)
    assert payload["is_clean"] is False
    assert "a.txt" in payload["changed_files"]


async def test_collect_git_rejects_a_bad_path(app_state, tmp_path):
    with pytest.raises(JevMcpError) as exc:
        await handle_collect_git(app_state, project_root=str(tmp_path / "missing"))
    assert exc.value.code == "PATH_INVALID"


async def test_run_tests_returns_an_enveloped_result(app_state, tmp_path):
    import sys

    payload = await handle_run_tests(
        app_state,
        project_root=str(tmp_path),
        command=[sys.executable, "-c", "print('ok')"],
    )
    assert_envelope(payload)
    assert payload["exit_code"] == 0


async def test_decide_without_a_key_raises_not_configured(app_state):
    with pytest.raises(NotConfiguredError):
        await handle_decide(app_state, goal="add retry")


async def test_decide_rejects_an_unknown_profile_before_calling_jev(app_state, monkeypatch):
    called = False

    async def spy(*args, **kwargs):
        nonlocal called
        called = True
        return CLEAN_ANSWERS

    monkeypatch.setenv("TYPESAFE_API_KEY", "key")
    monkeypatch.setattr("jev_mcp.mcp.tools.evaluate_state", spy)
    with pytest.raises(InvalidProfileError):
        await handle_decide(app_state, goal="x", profile="nope")
    assert called is False


async def test_decide_returns_a_verdict(app_state, monkeypatch):
    async def fake_evaluate(state, cfg, api_key):
        assert state["goal"] == "add retry"
        return CLEAN_ANSWERS

    monkeypatch.setenv("TYPESAFE_API_KEY", "key")
    monkeypatch.setattr("jev_mcp.mcp.tools.evaluate_state", fake_evaluate)

    payload = await handle_decide(
        app_state,
        goal="add retry",
        git={"diff": "+x", "changed_files": ["a.py"]},
        tests={"exit_code": 0, "timed_out": False},
    )
    assert_envelope(payload)
    assert payload["action"] == "done"
    assert payload["jev"]["questionset_id"] == "engineering-gate-v2"
    assert payload["missing_signals"] == []


async def test_decide_records_missing_signals(app_state, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "key")
    monkeypatch.setattr(
        "jev_mcp.mcp.tools.evaluate_state",
        lambda state, cfg, api_key: _resolved(CLEAN_ANSWERS),
    )
    payload = await handle_decide(app_state, goal="add retry")
    assert sorted(payload["missing_signals"]) == ["git", "tests"]


def _resolved(value):
    async def _coro():
        return value

    return _coro()


async def test_health_does_not_probe_by_default(app_state):
    payload = await handle_health(app_state)
    assert_envelope(payload)
    assert payload["typesafe_reachable"] is None
    assert payload["key_source"] == "none"
    assert payload["ok"] is False


async def test_health_reports_a_detected_test_command(app_state, tmp_path, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "key")
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\n", encoding="utf-8")
    payload = await handle_health(app_state, project_root=str(tmp_path))
    assert payload["test_command"] == ["pytest", "-q"]
    assert payload["key_source"] == "env"
    assert payload["key_hint"]


async def test_health_probe_reports_failure_as_an_error_entry(app_state, monkeypatch):
    from jev_mcp.errors import ApiUnreachableError

    def offline(_key):
        raise ApiUnreachableError()

    monkeypatch.setenv("TYPESAFE_API_KEY", "key")
    monkeypatch.setattr("jev_mcp.mcp.tools.verify_api_key", offline)
    payload = await handle_health(app_state, probe=True)
    assert payload["typesafe_reachable"] is False
    assert payload["errors"][0]["code"] == "API_UNREACHABLE"


async def test_describe_is_generated_from_the_code(app_state):
    payload = await handle_describe(app_state)
    assert payload["questionset_id"] == "engineering-gate-v2"
    assert payload["policy_id"] == "policy-engineering-gate-v2"
    assert set(payload["profiles"]) == {"default", "strict", "ci"}
    assert len(payload["questions"]) == 7
    assert len(payload["risk_levels"]) == 4
    assert "decide" in payload["tools"]
```

- [ ] **Step 3: Implement `mcp/tools.py`**

```python
# src/jev_mcp/mcp/tools.py
from __future__ import annotations

import asyncio
import shutil
import time
from dataclasses import dataclass

from jev_mcp.collectors.detect import detect_test_command
from jev_mcp.collectors.git import collect_git
from jev_mcp.collectors.runner import run_tests
from jev_mcp.config import AppConfig, load_config
from jev_mcp.credentials import mask, resolve_api_key, verify_api_key
from jev_mcp.decision.envelope import build_decide_payload
from jev_mcp.decision.policy import POLICY_ID, PROFILES, facts_from_payloads, route_decision
from jev_mcp.errors import InvalidProfileError, JevMcpError, NotConfiguredError
from jev_mcp.jev.client import evaluate_state
from jev_mcp.jev.questions import QUESTIONSET_ID, RISK_LEVELS, build_questions
from jev_mcp.jev.state_builder import build_state
from jev_mcp.logger import new_request_id, trace
from jev_mcp.util.paths import config_path, jev_home, resolve_project_root
from jev_mcp.util.responses import tool_response


@dataclass
class AppState:
    config: AppConfig


def create_app_state(config: AppConfig | None = None) -> AppState:
    return AppState(config=config or load_config())


class _Timer:
    """Times a handler and emits the tool_start / tool_end pair."""

    def __init__(self, tool: str, mcp_session_id: str | None) -> None:
        self.tool = tool
        self.request_id = new_request_id()
        self.mcp_session_id = mcp_session_id
        self._started = time.monotonic()

    def __enter__(self) -> _Timer:
        trace(
            "tool_start",
            tool=self.tool,
            request_id=self.request_id,
            mcp_session_id=self.mcp_session_id,
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        trace(
            "tool_end",
            tool=self.tool,
            request_id=self.request_id,
            duration_ms=self.duration_ms,
            error_code=exc.code if isinstance(exc, JevMcpError) else None,
        )
        return False

    @property
    def duration_ms(self) -> int:
        return int((time.monotonic() - self._started) * 1000)


async def handle_collect_git(
    state: AppState,
    *,
    project_root: str,
    base_ref: str | None = None,
    staged_only: bool = False,
    max_diff_bytes: int | None = None,
    mcp_session_id: str | None = None,
) -> dict:
    with _Timer("collect_git", mcp_session_id) as timer:
        root = resolve_project_root(project_root)
        payload = await collect_git(
            root,
            state.config.git,
            base_ref=base_ref,
            staged_only=staged_only,
            max_diff_bytes=max_diff_bytes,
        )
        trace(
            "git_collected",
            request_id=timer.request_id,
            changed_files=len(payload["changed_files"]),
            diff_bytes=len(payload["diff"]),
            truncated=payload["truncated"],
        )
        return tool_response(payload, request_id=timer.request_id, duration_ms=timer.duration_ms)


async def handle_run_tests(
    state: AppState,
    *,
    project_root: str,
    command: list[str] | None = None,
    timeout_s: float | None = None,
    env: dict[str, str] | None = None,
    mcp_session_id: str | None = None,
) -> dict:
    with _Timer("run_tests", mcp_session_id) as timer:
        root = resolve_project_root(project_root)
        payload = await run_tests(
            root, state.config.tests, command=command, timeout_s=timeout_s, env=env
        )
        trace(
            "tests_ran",
            request_id=timer.request_id,
            runner_id=payload["runner_id"],
            exit_code=payload["exit_code"],
            duration_s=payload["duration_s"],
            timed_out=payload["timed_out"],
        )
        return tool_response(payload, request_id=timer.request_id, duration_ms=timer.duration_ms)


async def handle_decide(
    state: AppState,
    *,
    goal: str,
    git: dict | None = None,
    tests: dict | None = None,
    project_root: str | None = None,
    profile: str | None = None,
    extra: dict | None = None,
    mcp_session_id: str | None = None,
) -> dict:
    with _Timer("decide", mcp_session_id) as timer:
        chosen = profile or state.config.decision.default_profile
        # Validate before spending an API request on a typo.
        if chosen not in PROFILES:
            raise InvalidProfileError(
                f"Unknown profile '{chosen}'. Use one of: {', '.join(PROFILES)}"
            )

        api_key, _ = resolve_api_key()
        if not api_key:
            raise NotConfiguredError()

        jev_state, missing = build_state(goal=goal, git=git, tests=tests, extra=extra)
        answers = await evaluate_state(jev_state, state.config, api_key)
        result = route_decision(
            answers,
            facts=facts_from_payloads(git, tests),
            profile=chosen,
            cfg=state.config.decision,
            missing_signals=missing,
        )
        trace(
            "policy_route",
            request_id=timer.request_id,
            profile=chosen,
            action=result.action,
            confidence=result.confidence,
            project_root=project_root,
        )
        payload = build_decide_payload(
            result, answers, model=state.config.jev.model, missing_signals=missing
        )
        return tool_response(payload, request_id=timer.request_id, duration_ms=timer.duration_ms)


async def handle_health(
    state: AppState,
    *,
    project_root: str | None = None,
    probe: bool = False,
    mcp_session_id: str | None = None,
) -> dict:
    with _Timer("health", mcp_session_id) as timer:
        errors: list[dict] = []
        api_key, source = resolve_api_key()

        reachable = None
        if probe and api_key:
            try:
                await asyncio.to_thread(verify_api_key, api_key)
                reachable = True
            except JevMcpError as exc:
                reachable = False
                errors.append({"code": exc.code, "message": exc.message})

        git_available = shutil.which("git") is not None

        test_command = None
        if project_root:
            detected = detect_test_command(resolve_project_root(project_root), state.config.tests)
            test_command = list(detected[1]) if detected else None

        body = {
            "ok": bool(api_key) and git_available and reachable is not False,
            "key_source": source,
            "key_hint": mask(api_key) if api_key else None,
            "typesafe_reachable": reachable,
            "git_available": git_available,
            "home": str(jev_home()),
            "config_path": str(config_path()),
            "test_command": test_command,
        }
        return tool_response(
            body, request_id=timer.request_id, duration_ms=timer.duration_ms, errors=errors
        )


async def handle_describe(state: AppState, *, mcp_session_id: str | None = None) -> dict:
    with _Timer("describe", mcp_session_id) as timer:
        questions = build_questions()
        body = {
            "tools": ["collect_git", "run_tests", "decide", "health", "describe"],
            "questionset_id": QUESTIONSET_ID,
            "policy_id": POLICY_ID,
            "profiles": list(PROFILES),
            "questions": {
                key: {
                    "type": type(question).__name__.lower(),
                    "instructions": getattr(question, "instructions", ""),
                }
                for key, question in questions.items()
            },
            "risk_levels": list(RISK_LEVELS),
            "workflow": [
                "call collect_git with the project root",
                "call run_tests with the project root",
                "call decide with the goal plus both payloads",
                "obey the action: fix keeps working, ask goes to the user, done may finish",
            ],
            "notes": [
                "next_action is a cross-check; the action comes from policy in code",
                "nouls carry no confidence; decide.confidence describes the rule that fired",
            ],
        }
        return tool_response(body, request_id=timer.request_id, duration_ms=timer.duration_ms)
```

- [ ] **Step 4: Run the handler tests**

Run: `poetry run pytest tests/test_mcp_tools.py -v`

Expected: all pass.

- [ ] **Step 5: Write the server test**

```python
# tests/test_mcp_server.py
import pytest

from jev_mcp.mcp.server import create_mcp_app


async def test_all_five_tools_are_registered():
    mcp = create_mcp_app("127.0.0.1", 8089)
    names = {tool.name for tool in await mcp.list_tools()}
    assert names == {"collect_git", "run_tests", "decide", "health", "describe"}


async def test_every_tool_has_a_description():
    mcp = create_mcp_app("127.0.0.1", 8089)
    for tool in await mcp.list_tools():
        assert tool.description


async def test_domain_errors_surface_with_their_code(monkeypatch):
    from jev_mcp.errors import NotARepoError
    import jev_mcp.mcp.server as server

    async def boom(*args, **kwargs):
        raise NotARepoError("not a repo")

    monkeypatch.setattr(server, "handle_collect_git", boom)
    mcp = create_mcp_app("127.0.0.1", 8089)
    with pytest.raises(Exception) as exc:
        await mcp.call_tool("collect_git", {"project_root": "."})
    assert "NOT_A_REPO" in str(exc.value)
```

> If the installed `mcp` version exposes a different introspection API than `list_tools()` / `call_tool()`, check `poetry run python -c "from mcp.server.fastmcp import FastMCP; print([n for n in dir(FastMCP) if not n.startswith('_')])"` and use the equivalent methods. The assertions — five tools, all described, errors carrying their code — stay the same.

- [ ] **Step 6: Implement `mcp/server.py`**

```python
# src/jev_mcp/mcp/server.py
from __future__ import annotations

from mcp.server.fastmcp import Context, FastMCP

from jev_mcp.config import load_config
from jev_mcp.errors import JevMcpError
from jev_mcp.logger import configure
from jev_mcp.mcp.tools import (
    AppState,
    create_app_state,
    handle_collect_git,
    handle_decide,
    handle_describe,
    handle_health,
    handle_run_tests,
)
from jev_mcp.mcp.transport import Transport

_state: AppState | None = None


def _app_state() -> AppState:
    global _state
    if _state is None:
        _state = create_app_state()
    return _state


def _session_id(ctx: Context) -> str | None:
    try:
        request = ctx.request_context.request
    except Exception:
        return None
    headers = getattr(request, "headers", None) if request is not None else None
    if headers is None:
        return None
    return headers.get("mcp-session-id") or headers.get("Mcp-Session-Id")


def _fail(exc: JevMcpError) -> RuntimeError:
    return RuntimeError(f"[{exc.code}] {exc.message}")


def create_mcp_app(host: str, port: int) -> FastMCP:
    mcp = FastMCP("jev-mcp", host=host, port=port)

    @mcp.tool()
    async def collect_git(
        ctx: Context,
        project_root: str,
        base_ref: str | None = None,
        staged_only: bool = False,
        max_diff_bytes: int | None = None,
    ) -> dict:
        """Snapshot the git work tree: branch, changed files, and a per-file budgeted diff."""
        try:
            return await handle_collect_git(
                _app_state(),
                project_root=project_root,
                base_ref=base_ref,
                staged_only=staged_only,
                max_diff_bytes=max_diff_bytes,
                mcp_session_id=_session_id(ctx),
            )
        except JevMcpError as exc:
            raise _fail(exc) from exc

    @mcp.tool()
    async def run_tests(
        ctx: Context,
        project_root: str,
        command: list[str] | None = None,
        timeout_s: float | None = None,
    ) -> dict:
        """Run the project's tests. A non-zero exit code is returned as data, not an error."""
        try:
            return await handle_run_tests(
                _app_state(),
                project_root=project_root,
                command=command,
                timeout_s=timeout_s,
                mcp_session_id=_session_id(ctx),
            )
        except JevMcpError as exc:
            raise _fail(exc) from exc

    @mcp.tool()
    async def decide(
        ctx: Context,
        goal: str,
        git: dict | None = None,
        tests: dict | None = None,
        project_root: str | None = None,
        profile: str | None = None,
        extra: dict | None = None,
    ) -> dict:
        """Judge the work against the goal and return fix, ask, or done with a reason trace.

        Pass the payloads returned by collect_git and run_tests.
        """
        try:
            return await handle_decide(
                _app_state(),
                goal=goal,
                git=git,
                tests=tests,
                project_root=project_root,
                profile=profile,
                extra=extra,
                mcp_session_id=_session_id(ctx),
            )
        except JevMcpError as exc:
            raise _fail(exc) from exc

    @mcp.tool()
    async def health(ctx: Context, project_root: str | None = None, probe: bool = False) -> dict:
        """Report key source, git availability, and the detected test command."""
        try:
            return await handle_health(
                _app_state(),
                project_root=project_root,
                probe=probe,
                mcp_session_id=_session_id(ctx),
            )
        except JevMcpError as exc:
            raise _fail(exc) from exc

    @mcp.tool()
    async def describe(ctx: Context) -> dict:
        """Describe the question set, policy rules, profiles, and the recommended workflow."""
        return await handle_describe(_app_state(), mcp_session_id=_session_id(ctx))

    return mcp


def run_server(
    host: str | None = None,
    port: int | None = None,
    transport: Transport = Transport.STDIO,
) -> None:
    global _state
    cfg = load_config()
    configure(cfg.log_level, cfg.log_format, cfg.log_redact)
    _state = create_app_state(cfg)
    mcp = create_mcp_app(host or cfg.host, port or cfg.port)
    mcp.run(transport="stdio" if transport is Transport.STDIO else "streamable-http")
```

- [ ] **Step 7: Run the server tests and the whole suite**

Run: `poetry run pytest -v && poetry run ruff check src tests`

Expected: everything green.

- [ ] **Step 8: Commit**

```bash
git add src/jev_mcp/mcp tests/conftest.py tests/test_mcp_tools.py tests/test_mcp_server.py
git commit -m "feat: expose collect_git, run_tests, decide, health, and describe over MCP"
```
