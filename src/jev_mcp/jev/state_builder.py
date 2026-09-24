from __future__ import annotations

from jev_mcp.util.redact import redact_text


def _empty_git() -> dict:
    return {
        "branch": None,
        "is_clean": None,
        "changed_files": [],
        "untracked_files": [],
        "diff_stat": "",
        "diff": "",
        "omitted_files": [],
    }


def _empty_tests() -> dict:
    return {
        "command": None,
        "exit_code": None,
        "timed_out": False,
        "stdout": "",
        "stderr": "",
    }


def _tests_from_collector(tests: dict) -> dict:
    return {
        "command": tests.get("command"),
        "exit_code": tests.get("exit_code"),
        "timed_out": tests.get("timed_out"),
        "stdout": redact_text(str(tests.get("stdout", ""))),
        "stderr": redact_text(str(tests.get("stderr", ""))),
    }


def _agent_tests_payload(tests: dict | None, extra: dict | None) -> dict | None:
    """Resolve test evidence from decide.tests or agent fields in extra."""
    if tests:
        return tests
    if not extra:
        return None
    for key in ("verification", "tests"):
        block = extra.get(key)
        if isinstance(block, dict) and (
            "exit_code" in block or block.get("tests_ran") or block.get("summary")
        ):
            return block
    return None


def build_state(
    *,
    goal: str,
    tests: dict | None = None,
    extra: dict | None = None,
) -> tuple[dict, list[str]]:
    """Assemble Jev state. Agent context goes in ``extra`` (summary, plan, verification).

    ``git`` is always an empty placeholder for the API; we do not collect diffs.
    Test runs are not executed here — the agent reports them via ``tests`` or
    ``extra.verification``.
    """
    missing: list[str] = []
    state: dict = {
        "goal": redact_text(goal),
        "git": _empty_git(),
    }

    agent_tests = _agent_tests_payload(tests, extra)
    if agent_tests:
        state["tests"] = _tests_from_collector(agent_tests)
    else:
        missing.append("tests")
        state["tests"] = _empty_tests()

    if extra:
        state["extra"] = extra

    return state, missing
