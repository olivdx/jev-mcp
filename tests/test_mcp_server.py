import pytest

from jev_mcp.mcp.server import create_mcp_app


async def test_four_tools_are_registered():
    mcp = create_mcp_app("127.0.0.1", 8089)
    names = {tool.name for tool in await mcp.list_tools()}
    assert names == {"run_tests", "decide", "health", "describe"}


async def test_every_tool_has_a_description():
    mcp = create_mcp_app("127.0.0.1", 8089)
    for tool in await mcp.list_tools():
        assert tool.description


async def test_domain_errors_surface_with_their_code(monkeypatch):
    from jev_mcp.errors import NotConfiguredError
    import jev_mcp.mcp.server as server

    async def boom(*args, **kwargs):
        raise NotConfiguredError()

    monkeypatch.setattr(server, "handle_decide", boom)
    mcp = create_mcp_app("127.0.0.1", 8089)
    with pytest.raises(Exception) as exc:
        await mcp.call_tool("decide", {"goal": "review plan"})
    assert "NOT_CONFIGURED" in str(exc.value)
