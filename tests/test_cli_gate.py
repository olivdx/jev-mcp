import json

import pytest
from typer.testing import CliRunner

from jev_mcp.cli.main import app
from jev_mcp.errors import ApiUnreachableError

runner = CliRunner()


def _verdict(action: str, confidence: float = 0.9) -> dict:
    return {
        "schema_version": "1.0",
        "request_id": "test",
        "duration_ms": 1,
        "errors": [],
        "action": action,
        "confidence": confidence,
        "reasons": [f"routed to {action}"],
        "policy_trace": [f"route:{action}"],
        "missing_signals": [],
        "jev": {
            "model": "jev-1.13",
            "questionset_id": "engineering-gate-v2",
            "policy_id": "policy-engineering-gate-v2",
            "answers": {},
        },
    }


@pytest.fixture
def stub_decide(monkeypatch):
    calls: dict = {}

    async def fake_decide(state, **kwargs):
        calls["decide"] = kwargs
        return _verdict("done")

    monkeypatch.setattr("jev_mcp.cli.gate.handle_decide", fake_decide)
    return calls


@pytest.mark.parametrize(("action", "code"), [("done", 0), ("fix", 1), ("ask", 2)])
def test_exit_code_follows_the_action(stub_decide, monkeypatch, tmp_path, action, code):
    async def fake_decide(state, **kwargs):
        return _verdict(action)

    monkeypatch.setattr("jev_mcp.cli.gate.handle_decide", fake_decide)
    result = runner.invoke(app, ["gate", "--goal", "g", "--project-root", str(tmp_path)])
    assert result.exit_code == code


def test_json_output_is_the_decide_envelope(stub_decide, tmp_path):
    result = runner.invoke(
        app, ["gate", "--goal", "g", "--project-root", str(tmp_path), "--json"]
    )
    payload = json.loads(result.stdout)
    assert payload["action"] == "done"
    assert payload["jev"]["policy_id"] == "policy-engineering-gate-v2"


def test_human_output_shows_action_and_reason(stub_decide, tmp_path):
    result = runner.invoke(app, ["gate", "--goal", "g", "--project-root", str(tmp_path)])
    assert "DONE" in result.stdout
    assert "routed to done" in result.stdout


def test_extra_json_reaches_decide(stub_decide, tmp_path):
    extra = '{"summary":"ok","verification":{"exit_code":0}}'
    runner.invoke(
        app,
        ["gate", "--goal", "ship it", "--project-root", str(tmp_path), "--extra-json", extra],
    )
    assert stub_decide["decide"]["goal"] == "ship it"
    assert stub_decide["decide"]["extra"]["summary"] == "ok"


def test_invalid_extra_json_exits_three(tmp_path):
    result = runner.invoke(
        app, ["gate", "--goal", "g", "--project-root", str(tmp_path), "--extra-json", "not-json"]
    )
    assert result.exit_code == 3


def test_tool_errors_exit_with_three(monkeypatch, tmp_path):
    async def unreachable(state, **kwargs):
        raise ApiUnreachableError()

    monkeypatch.setattr("jev_mcp.cli.gate.handle_decide", unreachable)
    result = runner.invoke(app, ["gate", "--goal", "g", "--project-root", str(tmp_path)])
    assert result.exit_code == 3
    assert "API_UNREACHABLE" in result.output
