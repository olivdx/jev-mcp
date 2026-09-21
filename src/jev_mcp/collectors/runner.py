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
