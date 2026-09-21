from jev_mcp.jev.state_builder import build_state


def test_goal_only_records_missing_tests():
    state, missing = build_state(goal="add retry")
    assert state["goal"] == "add retry"
    assert missing == ["tests"]
    assert state["git"]["diff"] == ""


def test_tests_and_extra_are_included():
    tests = {
        "command": ["pytest"],
        "exit_code": 1,
        "timed_out": False,
        "stdout": "1 failed",
        "stderr": "",
    }
    state, missing = build_state(
        goal="fix bug",
        tests=tests,
        extra={"summary": "Updated auth module"},
    )
    assert missing == []
    assert state["tests"]["exit_code"] == 1
    assert state["extra"]["summary"] == "Updated auth module"


def test_secrets_in_extra_are_not_double_redacted():
    state, _ = build_state(goal="g", extra={"notes": "plain text"})
    assert state["extra"]["notes"] == "plain text"
