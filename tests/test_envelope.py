from jev_mcp.decision.envelope import build_decide_payload
from jev_mcp.decision.policy import POLICY_ID, DecideResult
from jev_mcp.jev.answers import JevAnswers
from jev_mcp.jev.questions import QUESTIONSET_ID


def test_payload_carries_ids_and_trace():
    result = DecideResult("fix", 0.82, ["tests_blocking=0.91 >= 0.6"], ["rule:tests_blocking"])
    answers = JevAnswers(model="jev-1.13", nouls={"tests_blocking": 0.91})
    payload = build_decide_payload(result, answers, model="jev-1.13", missing_signals=["tests"])

    assert payload["action"] == "fix"
    assert payload["confidence"] == 0.82
    assert payload["missing_signals"] == ["tests"]
    assert payload["jev"]["questionset_id"] == QUESTIONSET_ID
    assert payload["jev"]["policy_id"] == POLICY_ID
    assert payload["jev"]["answers"]["nouls"]["tests_blocking"] == 0.91


def test_model_falls_back_to_configuration():
    payload = build_decide_payload(
        DecideResult("done", 1.0),
        JevAnswers(model=""),
        model="jev-1.13",
        missing_signals=[],
    )
    assert payload["jev"]["model"] == "jev-1.13"


def test_payload_is_json_serializable():
    import json

    json.dumps(
        build_decide_payload(
            DecideResult("done", 1.0), JevAnswers(model="m"), model="m", missing_signals=[]
        )
    )
