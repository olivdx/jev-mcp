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
    test_command: list[str] | None,
    skip_tests: bool,
    extra: dict | None,
) -> dict:
    root = str(project_root)
    tests_payload = None
    if not skip_tests:
        try:
            tests_payload = await handle_run_tests(
                state, project_root=root, command=test_command
            )
        except NoTestCommandError:
            tests_payload = None

    return await handle_decide(
        state,
        goal=goal,
        tests=tests_payload,
        project_root=root,
        profile=profile,
        extra=extra,
    )


def gate_cmd(
    goal: Annotated[str, typer.Option("--goal", help="What the change was supposed to do")],
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Repository root")
    ] = Path.cwd(),
    profile: Annotated[
        str | None, typer.Option("--profile", help="default, strict, or ci")
    ] = None,
    test_command: Annotated[
        str | None, typer.Option("--test-command", help="Override the detected test command")
    ] = None,
    no_tests: Annotated[bool, typer.Option("--no-tests", help="Skip the test run")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Print the raw envelope")] = False,
) -> None:
    """Run optional tests then decide; exit 0 for done, 1 for fix, 2 for ask."""
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
                test_command=shlex.split(test_command) if test_command else None,
                skip_tests=no_tests,
                extra=None,
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
