import importlib.metadata


def test_distribution_version_is_available():
    assert importlib.metadata.version("mcp-jev-mcp")


def test_cli_app_is_named_jev_mcp():
    from jev_mcp.cli.main import app

    assert app.info.name == "jev-mcp"
