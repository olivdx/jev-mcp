import json

from jev_mcp.logger import configure, new_request_id, trace


def test_request_ids_are_unique():
    assert new_request_id() != new_request_id()


def test_text_format_renders_key_value_pairs(capsys):
    configure(level="info", log_format="text")
    trace("tool_start", tool="decide", request_id="abc")
    err = capsys.readouterr().err
    assert "tool_start" in err
    assert "tool=decide" in err
    assert "request_id=abc" in err


def test_json_format_emits_one_object_per_event(capsys):
    configure(level="info", log_format="json")
    trace("policy_route", action="fix", confidence=0.82)
    payload = json.loads(capsys.readouterr().err.strip())
    assert payload == {"event": "policy_route", "action": "fix", "confidence": 0.82}


def test_none_fields_are_dropped(capsys):
    configure(level="info", log_format="json")
    trace("tool_end", tool="health", error_code=None)
    payload = json.loads(capsys.readouterr().err.strip())
    assert "error_code" not in payload


def test_string_fields_are_redacted(capsys):
    configure(level="info", log_format="text", redact=True)
    trace("jev_request", note="Authorization: Bearer abcdef1234567890")
    err = capsys.readouterr().err
    assert "abcdef1234567890" not in err
    assert "<REDACTED>" in err


def test_redaction_can_be_disabled(capsys):
    configure(level="info", log_format="text", redact=False)
    trace("jev_request", note="Authorization: Bearer abcdef1234567890")
    assert "abcdef1234567890" in capsys.readouterr().err
