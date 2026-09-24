import pytest

from jev_mcp.errors import InvalidProfileError, NotConfiguredError
from jev_mcp.jev.answers import ChoiceAnswer, JevAnswers, ScoreAnswer
from jev_mcp.mcp.tools import handle_decide, handle_describe, handle_health

CLEAN_ANSWERS = JevAnswers(
    model="jev-1.13",
    nouls={
        "goal_addressed": 0.95,
        "goal_ambiguous": 0.05,
        "tests_blocking": 0.05,
        "incomplete_work": 0.05,
        "scope_creep": 0.05,
    },
    choices={"next_action": ChoiceAnswer("done", 0.9)},
    scores={"risk_regression": ScoreAnswer(0.3, 0.9, 3)},
)


def assert_envelope(payload: dict) -> None:
    assert payload["schema_version"] == "1.0"
    assert payload["request_id"]
    assert payload["duration_ms"] >= 0
    assert payload["errors"] == []


async def test_decide_without_a_key_raises_not_configured(app_state):
    with pytest.raises(NotConfiguredError):
        await handle_decide(app_state, goal="add retry")


async def test_decide_rejects_an_unknown_profile_before_calling_jev(app_state, monkeypatch):
    called = False

    async def spy(*args, **kwargs):
        nonlocal called
        called = True
        return CLEAN_ANSWERS

    monkeypatch.setenv("TYPESAFE_API_KEY", "key")
    monkeypatch.setattr("jev_mcp.mcp.tools.evaluate_state", spy)
    with pytest.raises(InvalidProfileError):
        await handle_decide(app_state, goal="x", profile="nope")
    assert called is False


async def test_decide_returns_a_verdict(app_state, monkeypatch):
    async def fake_evaluate(state, cfg, api_key):
        assert state["goal"] == "add retry"
        assert state["extra"]["summary"] == "did the thing"
        return CLEAN_ANSWERS

    monkeypatch.setenv("TYPESAFE_API_KEY", "key")
    monkeypatch.setattr("jev_mcp.mcp.tools.evaluate_state", fake_evaluate)

    payload = await handle_decide(
        app_state,
        goal="add retry",
        extra={"summary": "did the thing"},
        tests={"exit_code": 0, "timed_out": False},
    )
    assert_envelope(payload)
    assert payload["action"] == "done"
    assert payload["jev"]["questionset_id"] == "engineering-gate-v2"
    assert payload["missing_signals"] == []


async def test_decide_records_missing_tests(app_state, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "key")
    monkeypatch.setattr(
        "jev_mcp.mcp.tools.evaluate_state",
        lambda state, cfg, api_key: _resolved(CLEAN_ANSWERS),
    )
    payload = await handle_decide(app_state, goal="add retry")
    assert payload["missing_signals"] == ["tests"]


def _resolved(value):
    async def _coro():
        return value

    return _coro()


async def test_health_does_not_probe_by_default(app_state):
    payload = await handle_health(app_state)
    assert_envelope(payload)
    assert payload["typesafe_reachable"] is None
    assert payload["key_source"] == "none"
    assert payload["ok"] is False


async def test_health_reports_mode_and_key(app_state, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "key")
    payload = await handle_health(app_state)
    assert payload["mode"] == "agent_summary"
    assert payload["key_source"] == "env"
    assert payload["key_hint"]


async def test_health_probe_reports_failure_as_an_error_entry(app_state, monkeypatch):
    from jev_mcp.errors import ApiUnreachableError

    def offline(_key):
        raise ApiUnreachableError()

    monkeypatch.setenv("TYPESAFE_API_KEY", "key")
    monkeypatch.setattr("jev_mcp.mcp.tools.verify_api_key", offline)
    payload = await handle_health(app_state, probe=True)
    assert payload["typesafe_reachable"] is False
    assert payload["errors"][0]["code"] == "API_UNREACHABLE"


async def test_describe_is_generated_from_the_code(app_state):
    payload = await handle_describe(app_state)
    assert payload["questionset_id"] == "engineering-gate-v2"
    assert payload["policy_id"] == "policy-engineering-gate-v2"
    assert set(payload["profiles"]) == {"default", "strict", "ci"}
    assert len(payload["questions"]) == 7
    assert "run_tests" not in payload["tools"]
    assert payload["tools"] == ["decide", "health", "describe"]
