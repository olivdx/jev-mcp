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


def build_state(
    *,
    goal: str,
    tests: dict | None = None,
    extra: dict | None = None,
) -> tuple[dict, list[str]]:
    """Assemble Jev state. Agent context goes in ``extra`` (summary, plan, notes).

    ``git`` is always an empty placeholder for the API; we do not collect diffs.
    """
    missing: list[str] = []
    state: dict = {
        "goal": redact_text(goal),
        "git": _empty_git(),
    }

    if tests:
        state["tests"] = _tests_from_collector(tests)
    else:
        missing.append("tests")
        state["tests"] = _empty_tests()

    if extra:
        state["extra"] = extra

    return state, missing
