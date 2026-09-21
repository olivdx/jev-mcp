# Task 7 — Test detection and execution

**Deliverable:** `detect_test_command` (config rules then built-in markers) and `run_tests`, which treats a failing test suite as a **signal**, not an error.

**Files:**
- Create: `src/jev_mcp/collectors/detect.py`, `src/jev_mcp/collectors/runner.py`
- Create: `tests/test_detect.py`, `tests/test_runner.py`

**Interfaces:**
- Consumes: `TestsConfig`, `TestProjectRule` (task 3); `run_argv`, `CommandNotFoundError` (task 5); `NoTestCommandError`, `TestRunnerFailedError` (task 2).
- Produces: `detect_test_command(project_root, cfg) -> tuple[str, list[str]] | None`, `async run_tests(...) -> dict`.

**Rules that matter:**
- A non-zero exit code returns normally with `exit_code` set. Only a runner that cannot be launched raises `TEST_RUNNER_FAILED`.
- A timeout returns `timed_out: True` with the partial output. The policy layer turns that into `fix`.
- The child process inherits the parent environment; the caller-supplied `env` mapping is filtered through `tests.env_allowlist` so an MCP caller cannot inject arbitrary variables.

---

- [ ] **Step 1: Write the failing detection tests**

```python
# tests/test_detect.py
import json

from jev_mcp.collectors.detect import detect_test_command
from jev_mcp.config import TestProjectRule, TestsConfig

CFG = TestsConfig()


def test_no_markers_returns_none(tmp_path):
    assert detect_test_command(tmp_path, CFG) is None


def test_pyproject_maps_to_pytest(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\n", encoding="utf-8")
    runner_id, command = detect_test_command(tmp_path, CFG)
    assert runner_id == "pytest"
    assert command == ["pytest", "-q"]


def test_poetry_lock_prefixes_poetry_run(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\n", encoding="utf-8")
    (tmp_path / "poetry.lock").write_text("", encoding="utf-8")
    _, command = detect_test_command(tmp_path, CFG)
    assert command == ["poetry", "run", "pytest", "-q"]


def test_package_json_with_test_script(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8"
    )
    runner_id, command = detect_test_command(tmp_path, CFG)
    assert runner_id == "npm"
    assert command == ["npm", "test"]


def test_package_json_without_test_script_is_ignored(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"build": "x"}}), encoding="utf-8")
    assert detect_test_command(tmp_path, CFG) is None


def test_makefile_test_target(tmp_path):
    (tmp_path / "Makefile").write_text("build:\n\techo b\ntest:\n\techo t\n", encoding="utf-8")
    runner_id, command = detect_test_command(tmp_path, CFG)
    assert runner_id == "make"
    assert command == ["make", "test"]


def test_config_rule_wins_over_builtin(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\n", encoding="utf-8")
    cfg = TestsConfig(
        projects=[TestProjectRule(match="pyproject.toml", command=["nx", "test", "api"])]
    )
    runner_id, command = detect_test_command(tmp_path, cfg)
    assert runner_id == "config:pyproject.toml"
    assert command == ["nx", "test", "api"]


def test_first_matching_config_rule_wins(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "x"}}), encoding="utf-8")
    cfg = TestsConfig(
        projects=[
            TestProjectRule(match="absent.toml", command=["never"]),
            TestProjectRule(match="package.json", command=["pnpm", "test"]),
        ]
    )
    _, command = detect_test_command(tmp_path, cfg)
    assert command == ["pnpm", "test"]
```

- [ ] **Step 2: Implement `collectors/detect.py`**

```python
# src/jev_mcp/collectors/detect.py
from __future__ import annotations

import json
from pathlib import Path

from jev_mcp.config import TestsConfig

_PYTHON_MARKERS = ("pyproject.toml", "pytest.ini", "setup.cfg")


def detect_test_command(project_root: Path, cfg: TestsConfig) -> tuple[str, list[str]] | None:
    """Return (runner_id, argv) for the first rule that matches, or None."""
    for rule in cfg.projects:
        if (project_root / rule.match).exists():
            return f"config:{rule.match}", list(rule.command)

    if any((project_root / marker).exists() for marker in _PYTHON_MARKERS):
        if (project_root / "poetry.lock").exists():
            return "pytest", ["poetry", "run", "pytest", "-q"]
        return "pytest", ["pytest", "-q"]

    manifest_path = project_root / "package.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            manifest = {}
        scripts = manifest.get("scripts") if isinstance(manifest, dict) else None
        if isinstance(scripts, dict) and scripts.get("test"):
            return "npm", ["npm", "test"]

    makefile = project_root / "Makefile"
    if makefile.exists():
        for line in makefile.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("test:"):
                return "make", ["make", "test"]

    return None
```

- [ ] **Step 3: Run the detection tests**

Run: `poetry run pytest tests/test_detect.py -v`

Expected: 8 passed.

- [ ] **Step 4: Write the failing runner tests**

```python
# tests/test_runner.py
import sys

import pytest

from jev_mcp.collectors.runner import run_tests
from jev_mcp.config import TestProjectRule, TestsConfig
from jev_mcp.errors import NoTestCommandError, TestRunnerFailedError

PYTHON = sys.executable
CFG = TestsConfig(default_timeout_s=30, max_output_bytes=10_000)


async def test_explicit_command_runs(tmp_path):
    result = await run_tests(tmp_path, CFG, command=[PYTHON, "-c", "print('ok')"])
    assert result["runner_id"] == "explicit"
    assert result["exit_code"] == 0
    assert "ok" in result["stdout"]
    assert result["timed_out"] is False
    assert result["output_truncated"] is False


async def test_failing_suite_is_a_signal_not_an_error(tmp_path):
    result = await run_tests(tmp_path, CFG, command=[PYTHON, "-c", "raise SystemExit(1)"])
    assert result["exit_code"] == 1


async def test_timeout_returns_a_flag(tmp_path):
    result = await run_tests(
        tmp_path,
        CFG,
        command=[PYTHON, "-c", "import time; time.sleep(30)"],
        timeout_s=0.5,
    )
    assert result["timed_out"] is True


async def test_missing_runner_raises(tmp_path):
    with pytest.raises(TestRunnerFailedError) as exc:
        await run_tests(tmp_path, CFG, command=["definitely-not-a-real-binary-xyz"])
    assert exc.value.code == "TEST_RUNNER_FAILED"


async def test_no_detected_command_raises(tmp_path):
    with pytest.raises(NoTestCommandError) as exc:
        await run_tests(tmp_path, CFG)
    assert exc.value.code == "NO_TEST_COMMAND"


async def test_detected_command_is_used(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\n", encoding="utf-8")
    cfg = TestsConfig(
        default_timeout_s=30,
        max_output_bytes=10_000,
        projects=[
            TestProjectRule(
                match="pyproject.toml",
                command=[PYTHON, "-c", "print('detected')"],
            )
        ],
    )
    result = await run_tests(tmp_path, cfg)
    assert result["runner_id"] == "config:pyproject.toml"
    assert "detected" in result["stdout"]


async def test_env_is_filtered_by_the_allowlist(tmp_path):
    cfg = TestsConfig(default_timeout_s=30, max_output_bytes=10_000, env_allowlist=["ALLOWED"])
    script = "import os; print(os.getenv('ALLOWED'), os.getenv('BLOCKED'))"
    result = await run_tests(
        tmp_path,
        cfg,
        command=[PYTHON, "-c", script],
        env={"ALLOWED": "yes", "BLOCKED": "no"},
    )
    assert "yes" in result["stdout"]
    assert "None" in result["stdout"]
```

- [ ] **Step 5: Implement `collectors/runner.py`**

```python
# src/jev_mcp/collectors/runner.py
from __future__ import annotations

import os
from pathlib import Path

from jev_mcp.collectors.detect import detect_test_command
from jev_mcp.config import TestsConfig
from jev_mcp.errors import NoTestCommandError, TestRunnerFailedError
from jev_mcp.util.proc import CommandNotFoundError, run_argv


def _child_env(cfg: TestsConfig, extra: dict[str, str] | None) -> dict[str, str]:
    """Inherit the parent environment, but only let allowlisted keys be overridden."""
    env = dict(os.environ)
    for key, value in (extra or {}).items():
        if key in cfg.env_allowlist:
            env[key] = str(value)
    return env


async def run_tests(
    project_root: Path,
    cfg: TestsConfig,
    *,
    command: list[str] | None = None,
    timeout_s: float | None = None,
    env: dict[str, str] | None = None,
) -> dict:
    if command:
        runner_id, argv = "explicit", [str(part) for part in command]
    else:
        detected = detect_test_command(project_root, cfg)
        if detected is None:
            raise NoTestCommandError(
                f"No test command detected for {project_root}. "
                "Pass 'command' or add a tests.projects rule to config.yaml."
            )
        runner_id, argv = detected

    timeout = float(timeout_s or cfg.default_timeout_s)
    try:
        result = await run_argv(
            argv,
            project_root,
            timeout_s=timeout,
            max_output_bytes=cfg.max_output_bytes,
            env=_child_env(cfg, env),
        )
    except CommandNotFoundError as exc:
        raise TestRunnerFailedError(f"Cannot launch test runner: {argv[0]}") from exc

    return {
        "runner_id": runner_id,
        "command": argv,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "output_truncated": result.truncated,
        "duration_s": result.duration_s,
    }
```

- [ ] **Step 6: Run the runner tests**

Run: `poetry run pytest tests/test_runner.py -v`

Expected: 7 passed.

- [ ] **Step 7: Commit**

```bash
git add src/jev_mcp/collectors tests/test_detect.py tests/test_runner.py
git commit -m "feat: add test command detection and execution collectors"
```
