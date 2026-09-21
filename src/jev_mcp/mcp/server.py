from __future__ import annotations

from jev_mcp.mcp.transport import Transport


def run_server(
    host: str | None = None,
    port: int | None = None,
    transport: Transport = Transport.STDIO,
) -> None:
    # Wired to FastMCP in task 11.
    raise NotImplementedError("MCP server is implemented in task 11")
