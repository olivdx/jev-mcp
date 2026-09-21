from mcp.server.fastmcp import Context, FastMCP

from jev_mcp.config import load_config
from jev_mcp.errors import JevMcpError
from jev_mcp.logger import configure
from jev_mcp.mcp.tools import (
    AppState,
    create_app_state,
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
        tests: dict | None = None,
        project_root: str | None = None,
        profile: str | None = None,
        extra: dict | None = None,
    ) -> dict:
        """Judge the goal and agent summary; return fix, ask, or done.

        Put the plan or change summary in extra, e.g. extra.summary or extra.plan_text.
        """
        try:
            return await handle_decide(
                _app_state(),
                goal=goal,
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
        """Report key source and optional TypeSafe probe."""
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
        """Describe questions, policy, profiles, and the recommended workflow."""
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
