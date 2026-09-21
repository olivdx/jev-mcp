from typer.testing import CliRunner

from jev_mcp.cli.main import app
from jev_mcp.credentials import resolve_api_key, save_api_key
from jev_mcp.errors import InvalidKeyError

runner = CliRunner()


def test_key_add_verifies_then_saves(isolated_home, monkeypatch):
    seen = {}
    monkeypatch.setattr("jev_mcp.cli.key.verify_api_key", lambda key: seen.setdefault("key", key))
    result = runner.invoke(app, ["key", "add", "  live-key  "])
    assert result.exit_code == 0
    assert seen["key"] == "live-key"
    assert resolve_api_key()[0] == "live-key"


def test_key_add_does_not_write_when_verification_fails(isolated_home, monkeypatch):
    def reject(_key):
        raise InvalidKeyError("nope")

    monkeypatch.setattr("jev_mcp.cli.key.verify_api_key", reject)
    result = runner.invoke(app, ["key", "add", "bad-key"])
    assert result.exit_code == 1
    assert "INVALID_KEY" in result.output
    assert resolve_api_key()[0] is None


def test_key_add_never_echoes_the_key(isolated_home, monkeypatch):
    monkeypatch.setattr("jev_mcp.cli.key.verify_api_key", lambda key: None)
    result = runner.invoke(app, ["key", "add", "super-secret-value"])
    assert "super-secret-value" not in result.output


def test_key_status_reports_source_and_hint(isolated_home):
    save_api_key("typesafe-key-a1b2")
    result = runner.invoke(app, ["key", "status"])
    assert result.exit_code == 0
    assert "file" in result.output
    assert "a1b2" in result.output
    assert "typesafe-key" not in result.output


def test_key_status_without_a_key(isolated_home):
    result = runner.invoke(app, ["key", "status"])
    assert "none" in result.output


def test_key_remove(isolated_home):
    save_api_key("abc")
    assert runner.invoke(app, ["key", "remove"]).exit_code == 0
    assert resolve_api_key()[0] is None
