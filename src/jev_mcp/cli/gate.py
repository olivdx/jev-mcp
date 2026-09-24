from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer

from jev_mcp.config import load_config
from jev_mcp.errors import JevMcpError
from jev_mcp.logger import configure
from jev_mcp.mcp.tools import create_app_state, handle_decide

EXIT_CODES = {"done": 0, "fix": 1, "ask": 2}
ERROR_EXIT_CODE = 3


def gate_cmd(
    goal: Annotated[str, typer.Option("--goal", help="What the change was supposed to do")],
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Repository root")
    ] = Path.cwd(),
    profile: Annotated[
        str | None, typer.Option("--profile", help="default, strict, or ci")
    ] = None,
    extra_json: Annotated[
        str | None,
        typer.Option(
            "--extra-json",
            help='Agent context JSON, e.g. {"summary":"...","verification":{"exit_code":0}}',
        ),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print the raw envelope")] = False,
) -> None:
    """Call decide with goal and optional agent-authored extra JSON."""
    cfg = load_config()
    configure(cfg.log_level, cfg.log_format, cfg.log_redact)
    state = create_app_state(cfg)

    extra = None
    if extra_json:
        try:
            extra = json.loads(extra_json)
        except json.JSONDecodeError as exc:
            typer.echo(f"Invalid --extra-json: {exc}", err=True)
            raise typer.Exit(code=ERROR_EXIT_CODE) from exc
        if not isinstance(extra, dict):
            typer.echo("--extra-json must be a JSON object", err=True)
            raise typer.Exit(code=ERROR_EXIT_CODE)

    try:
        payload = asyncio.run(
            handle_decide(
                state,
                goal=goal,
                tests=None,
                project_root=str(project_root),
                profile=profile,
                extra=extra,
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
