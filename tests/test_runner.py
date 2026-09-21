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
    assert result["duration_s"] >= 0


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


async def test_child_inherits_the_parent_environment(tmp_path):
    # The runner must not strip PATH and friends, or pytest and npm break on Windows.
    script = "import os; print(bool(os.getenv('PATH')))"
    result = await run_tests(tmp_path, CFG, command=[PYTHON, "-c", script])
    assert "True" in result["stdout"]


async def test_long_output_is_truncated(tmp_path):
    cfg = TestsConfig(default_timeout_s=30, max_output_bytes=500)
    result = await run_tests(tmp_path, cfg, command=[PYTHON, "-c", "print('x' * 5000)"])
    assert result["output_truncated"] is True
