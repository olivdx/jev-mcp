from jev_mcp.util.responses import SCHEMA_VERSION, tool_response


def test_envelope_carries_the_common_fields():
    out = tool_response({"branch": "main"}, request_id="fixed-id", duration_ms=10)
    assert out["schema_version"] == SCHEMA_VERSION
    assert out["request_id"] == "fixed-id"
    assert out["duration_ms"] == 10
    assert out["errors"] == []
    assert out["branch"] == "main"


def test_errors_are_passed_through():
    out = tool_response(
        {},
        request_id="r",
        duration_ms=1,
        errors=[{"code": "GIT_FAILED", "message": "boom"}],
    )
    assert out["errors"][0]["code"] == "GIT_FAILED"
