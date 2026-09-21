from __future__ import annotations

import importlib.metadata
from typing import Annotated

import typer

from jev_mcp.cli.key import key_app
from jev_mcp.cli.serve import serve_cmd


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(importlib.metadata.version("mcp-jev-mcp"))
        raise typer.Exit()


app = typer.Typer(name="jev-mcp", help="jev-mcp - AI engineering control layer for MCP clients")


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show installed version and exit",
        ),
    ] = None,
) -> None:
    """Collect repository signals, ask TypeSafe Jev, and return a typed verdict."""


app.command("serve")(serve_cmd)
app.add_typer(key_app)


if __name__ == "__main__":
    app()
