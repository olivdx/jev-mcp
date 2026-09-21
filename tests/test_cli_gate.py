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
def stub_pipeline(monkeypatch):
    calls: dict = {}

    async def fake_tests(state, **kwargs):
        calls["tests"] = kwargs
        return {"exit_code": 0, "timed_out": False}

    async def fake_decide(state, **kwargs):
        calls["decide"] = kwargs
        return _verdict("done")

    monkeypatch.setattr("jev_mcp.cli.gate.handle_run_tests", fake_tests)
    monkeypatch.setattr("jev_mcp.cli.gate.handle_decide", fake_decide)
    return calls


@pytest.mark.parametrize(("action", "code"), [("done", 0), ("fix", 1), ("ask", 2)])
def test_exit_code_follows_the_action(stub_pipeline, monkeypatch, tmp_path, action, code):
    async def fake_decide(state, **kwargs):
        return _verdict(action)

    monkeypatch.setattr("jev_mcp.cli.gate.handle_decide", fake_decide)
    result = runner.invoke(app, ["gate", "--goal", "g", "--project-root", str(tmp_path)])
    assert result.exit_code == code


def test_json_output_is_the_decide_envelope(stub_pipeline, tmp_path):
    result = runner.invoke(
        app, ["gate", "--goal", "g", "--project-root", str(tmp_path), "--json"]
    )
    payload = json.loads(result.stdout)
    assert payload["action"] == "done"
    assert payload["jev"]["policy_id"] == "policy-engineering-gate-v2"


def test_human_output_shows_action_and_reason(stub_pipeline, tmp_path):
    result = runner.invoke(app, ["gate", "--goal", "g", "--project-root", str(tmp_path)])
    assert "DONE" in result.stdout
    assert "routed to done" in result.stdout


def test_no_tests_skips_the_runner(stub_pipeline, tmp_path):
    runner.invoke(
        app, ["gate", "--goal", "g", "--project-root", str(tmp_path), "--no-tests"]
    )
    assert "tests" not in stub_pipeline
    assert stub_pipeline["decide"]["tests"] is None


def test_missing_test_command_is_not_fatal(stub_pipeline, monkeypatch, tmp_path):
    from jev_mcp.errors import NoTestCommandError

    async def no_command(state, **kwargs):
        raise NoTestCommandError("nothing to run")

    monkeypatch.setattr("jev_mcp.cli.gate.handle_run_tests", no_command)
    result = runner.invoke(app, ["gate", "--goal", "g", "--project-root", str(tmp_path)])
    assert result.exit_code == 0
    assert stub_pipeline["decide"]["tests"] is None


def test_options_reach_the_handlers(stub_pipeline, tmp_path):
    runner.invoke(
        app,
        [
            "gate",
            "--goal",
            "ship it",
            "--project-root",
            str(tmp_path),
            "--profile",
            "strict",
            "--test-command",
            "pytest -q tests",
        ],
    )
    assert stub_pipeline["tests"]["command"] == ["pytest", "-q", "tests"]
    assert stub_pipeline["decide"]["profile"] == "strict"
    assert stub_pipeline["decide"]["goal"] == "ship it"


def test_tool_errors_exit_with_three(monkeypatch, tmp_path):
    async def unreachable(state, **kwargs):
        raise ApiUnreachableError()

    monkeypatch.setattr("jev_mcp.cli.gate.handle_decide", unreachable)
    result = runner.invoke(
        app, ["gate", "--goal", "g", "--project-root", str(tmp_path), "--no-tests"]
    )
    assert result.exit_code == 3
    assert "API_UNREACHABLE" in result.output
