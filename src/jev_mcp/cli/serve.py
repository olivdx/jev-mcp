from __future__ import annotations

from typing import Annotated

import typer

from jev_mcp.mcp.server import run_server
from jev_mcp.mcp.transport import Transport


def serve_cmd(
    transport: Annotated[
        Transport,
        typer.Option(help="MCP transport: stdio for clients, http for local debugging"),
    ] = Transport.STDIO,
    host: Annotated[str | None, typer.Option(help="Bind host (http only)")] = None,
    port: Annotated[int | None, typer.Option(help="Bind port (http only)")] = None,
) -> None:
    """Start the MCP server."""
    run_server(host=host, port=port, transport=transport)
