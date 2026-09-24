from __future__ import annotations

from dataclasses import dataclass, field

from jev_mcp.config import DecisionConfig
from jev_mcp.errors import InvalidProfileError
from jev_mcp.jev.answers import JevAnswers

POLICY_ID = "policy-engineering-gate-v2"
PROFILES: tuple[str, ...] = ("default", "strict", "ci")

ACTION_FIX = "fix"
ACTION_ASK = "ask"
ACTION_DONE = "done"

_CROSSCHECK_MAP = {"fix": ACTION_FIX, "ask_user": ACTION_ASK, "done": ACTION_DONE}
_GUARDED_NOULS = (
    "goal_ambiguous",
    "tests_blocking",
    "incomplete_work",
    "goal_addressed",
    "scope_creep",
)


@dataclass(frozen=True)
class Facts:
    diff_empty: bool = True
    tests_ran: bool = False
    tests_exit_code: int | None = None
    tests_timed_out: bool = False


@dataclass(frozen=True)
class DecideResult:
    action: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    policy_trace: list[str] = field(default_factory=list)


def facts_from_payloads(git: dict | None, tests: dict | None) -> Facts:
    diff_empty = True
    if git:
        diff_empty = not str(git.get("diff", "")).strip() and not git.get("changed_files")
    if not tests:
        return Facts(diff_empty=diff_empty)
    tests_ran = (
        tests.get("exit_code") is not None
        or bool(tests.get("summary"))
        or bool(tests.get("stdout"))
        or bool(tests.get("stderr"))
        or bool(tests.get("tests_ran"))
    )
    return Facts(
        diff_empty=diff_empty,
        tests_ran=tests_ran,
        tests_exit_code=tests.get("exit_code"),
        tests_timed_out=bool(tests.get("timed_out")),
    )


def decisiveness(noul: float) -> float:
    return round(abs(noul - 0.5) * 2, 4)


def route_decision(
    answers: JevAnswers,
    *,
    facts: Facts,
    profile: str,
    cfg: DecisionConfig,
    missing_signals: list[str],
) -> DecideResult:
    if profile not in PROFILES:
        raise InvalidProfileError(
            f"Unknown profile '{profile}'. Use one of: {', '.join(PROFILES)}"
        )

    result = _base_route(answers, facts, cfg, [f"profile:{profile}"])
    result = _apply_crosscheck(result, answers, cfg, profile)
    if result.action == ACTION_DONE:
        result = _apply_profile_gates(result, facts, profile, missing_signals)
    return result


def _result(action: str, confidence: float, reasons: list[str], trace: list[str]) -> DecideResult:
    return DecideResult(
        action=action,
        confidence=round(float(confidence), 4),
        reasons=reasons,
        policy_trace=trace,
    )


def _base_route(
    answers: JevAnswers,
    facts: Facts,
    cfg: DecisionConfig,
    trace: list[str],
) -> DecideResult:
    thresholds = cfg.thresholds

    if facts.tests_ran and facts.tests_timed_out:
        return _result(
            ACTION_FIX,
            1.0,
            ["the test run timed out"],
            [*trace, "rule:tests_timed_out", "route:fix"],
        )

    if facts.tests_ran and facts.tests_exit_code not in (None, 0):
        return _result(
            ACTION_FIX,
            1.0,
            [f"tests exit_code={facts.tests_exit_code} (non-zero)"],
            [*trace, "rule:tests_exit_code", "route:fix"],
        )

    noul_rules = (
        ("goal_ambiguous", thresholds.goal_ambiguous_ask, ACTION_ASK, "above"),
        ("tests_blocking", thresholds.tests_blocking_fix, ACTION_FIX, "above"),
        ("incomplete_work", thresholds.incomplete_work_fix, ACTION_FIX, "above"),
        ("goal_addressed", thresholds.goal_addressed_min, ACTION_FIX, "below"),
        ("scope_creep", thresholds.scope_creep_ask, ACTION_ASK, "above"),
    )
    for key, threshold, action, direction in noul_rules:
        value = answers.nouls.get(key)
        if value is None:
            continue
        triggered = value >= threshold if direction == "above" else value < threshold
        if triggered:
            symbol = ">=" if direction == "above" else "<"
            return _result(
                action,
                decisiveness(value),
                [f"{key}={value:.2f} {symbol} {threshold}"],
                [*trace, f"rule:{key}", f"route:{action}"],
            )

    risk = answers.scores.get("risk_regression")
    if risk is not None and risk.normalized >= thresholds.risk_high_normalized and not facts.tests_ran:
        return _result(
            ACTION_FIX,
            risk.confidence,
            [f"risk_regression normalized={risk.normalized:.2f} with no test evidence"],
            [*trace, "rule:risk_without_tests", "route:fix"],
        )

    margins = [
        decisiveness(answers.nouls[key]) for key in _GUARDED_NOULS if key in answers.nouls
    ]
    return _result(
        ACTION_DONE,
        min(margins) if margins else 0.5,
        ["no blocking signal"],
        [*trace, "rule:default", "route:done"],
    )


def _apply_crosscheck(
    result: DecideResult,
    answers: JevAnswers,
    cfg: DecisionConfig,
    profile: str,
) -> DecideResult:
    crosscheck = answers.choices.get("next_action")
    if crosscheck is None:
        return result
    mapped = _CROSSCHECK_MAP.get(crosscheck.choice)
    if mapped is None or mapped == result.action:
        return result

    reasons = [
        *result.reasons,
        f"cross-check said {crosscheck.choice} at confidence {crosscheck.confidence:.2f}",
    ]
    trace = [*result.policy_trace, "crosscheck:disagree"]

    downgrade = (
        profile == "strict"
        and result.action == ACTION_DONE
        and crosscheck.confidence >= cfg.thresholds.crosscheck_min_confidence
    )
    if downgrade:
        return _result(
            ACTION_ASK,
            crosscheck.confidence,
            reasons,
            [*trace, "strict:downgrade_done", "route:ask"],
        )
    return DecideResult(result.action, result.confidence, reasons, trace)


def _apply_profile_gates(
    result: DecideResult,
    facts: Facts,
    profile: str,
    missing_signals: list[str],
) -> DecideResult:
    if profile == "strict" and not facts.tests_ran and not facts.diff_empty:
        return _result(
            ACTION_ASK,
            1.0,
            [*result.reasons, "strict: code changed but no test signal was supplied"],
            [*result.policy_trace, "strict:no_tests", "route:ask"],
        )

    if profile == "ci":
        if not facts.tests_ran or facts.tests_exit_code != 0:
            return _result(
                ACTION_FIX,
                1.0,
                [*result.reasons, "ci: done requires a passing test run"],
                [*result.policy_trace, "ci:needs_passing_tests", "route:fix"],
            )

    return result
