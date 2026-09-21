# Task 10 — Decision policy and envelope

**Deliverable:** The layer that actually decides. Deterministic facts are checked before any model answer, Jev's `next_action` is only a cross-check, and every outcome carries a reason and a trace.

**Files:**
- Create: `src/jev_mcp/decision/__init__.py`, `src/jev_mcp/decision/policy.py`, `src/jev_mcp/decision/envelope.py`
- Create: `tests/test_policy.py`, `tests/test_envelope.py`

**Interfaces:**
- Consumes: `DecisionConfig`, `Thresholds` (task 3); `JevAnswers`, `ChoiceAnswer`, `ScoreAnswer` (task 8); `InvalidProfileError` (task 2); `QUESTIONSET_ID` (task 8).
- Produces: `POLICY_ID`, `PROFILES`, `Facts`, `DecideResult`, `facts_from_payloads`, `decisiveness`, `route_decision`, `build_decide_payload`.

**Rule order** (first match wins):

| # | Condition | Action | Confidence |
|---|-----------|--------|-----------|
| 1 | tests ran and timed out | `fix` | 1.0 |
| 2 | tests ran and `exit_code != 0` | `fix` | 1.0 |
| 3 | `goal_ambiguous >= goal_ambiguous_ask` | `ask` | decisiveness |
| 4 | `tests_blocking >= tests_blocking_fix` | `fix` | decisiveness |
| 5 | `incomplete_work >= incomplete_work_fix` | `fix` | decisiveness |
| 6 | `goal_addressed < goal_addressed_min` | `fix` | decisiveness |
| 7 | `scope_creep >= scope_creep_ask` | `ask` | decisiveness |
| 8 | `normalized(risk_regression) >= risk_high_normalized` and tests did not run | `fix` | score confidence |
| 9 | otherwise | `done` | weakest decisiveness among the nouls that stayed below their thresholds |

Then the cross-check runs, then profile gates apply to a `done`.

**Why decisiveness:** a Noul returns a bare probability with no confidence field. `abs(noul - 0.5) * 2` expresses how far the model committed, so a `done` reached on five coin-flip answers is visibly low-confidence.

---

- [ ] **Step 1: Write the failing policy tests**

```python
# tests/test_policy.py
import pytest

from jev_mcp.config import DecisionConfig
from jev_mcp.decision.policy import (
    POLICY_ID,
    Facts,
    decisiveness,
    facts_from_payloads,
    route_decision,
)
from jev_mcp.errors import InvalidProfileError
from jev_mcp.jev.answers import ChoiceAnswer, JevAnswers, ScoreAnswer

CFG = DecisionConfig()


def answers(**overrides) -> JevAnswers:
    """A clean-bill-of-health answer set; override one key per test."""
    nouls = {
        "goal_addressed": 0.95,
        "goal_ambiguous": 0.05,
        "tests_blocking": 0.05,
        "incomplete_work": 0.05,
        "scope_creep": 0.05,
    }
    nouls.update({k: v for k, v in overrides.items() if k in nouls})
    return JevAnswers(
        model="jev-1.13",
        nouls=nouls,
        choices=overrides.get("choices", {}),
        scores=overrides.get("scores", {"risk_regression": ScoreAnswer(0.2, 0.9, 3)}),
    )


def route(ans, *, facts=None, profile="default", missing=None):
    return route_decision(
        ans,
        facts=facts or Facts(diff_empty=False, tests_ran=True, tests_exit_code=0),
        profile=profile,
        cfg=CFG,
        missing_signals=missing or [],
    )


def test_policy_id_is_versioned():
    assert POLICY_ID == "policy-engineering-gate-v2"


def test_decisiveness_measures_distance_from_a_coin_flip():
    assert decisiveness(0.5) == 0.0
    assert decisiveness(1.0) == 1.0
    assert decisiveness(0.0) == 1.0
    assert decisiveness(0.75) == 0.5


# Rule 1 and 2: deterministic facts beat any model answer.
def test_timed_out_tests_force_fix_even_when_jev_says_done():
    result = route(
        answers(choices={"next_action": ChoiceAnswer("done", 0.99)}),
        facts=Facts(diff_empty=False, tests_ran=True, tests_exit_code=None, tests_timed_out=True),
    )
    assert result.action == "fix"
    assert result.confidence == 1.0
    assert "rule:tests_timed_out" in result.policy_trace


def test_failing_tests_force_fix():
    result = route(
        answers(),
        facts=Facts(diff_empty=False, tests_ran=True, tests_exit_code=1),
    )
    assert result.action == "fix"
    assert result.confidence == 1.0
    assert any("exit_code" in reason for reason in result.reasons)


# Rules 3 to 7: one noul each, in order.
def test_ambiguous_goal_asks():
    result = route(answers(goal_ambiguous=0.8))
    assert result.action == "ask"
    assert "rule:goal_ambiguous" in result.policy_trace


def test_blocking_tests_fix():
    result = route(answers(tests_blocking=0.9))
    assert result.action == "fix"
    assert "rule:tests_blocking" in result.policy_trace


def test_incomplete_work_fixes():
    result = route(answers(incomplete_work=0.7))
    assert result.action == "fix"


def test_goal_not_addressed_fixes():
    result = route(answers(goal_addressed=0.2))
    assert result.action == "fix"
    assert "rule:goal_addressed" in result.policy_trace


def test_scope_creep_asks():
    result = route(answers(scope_creep=0.85))
    assert result.action == "ask"


def test_ambiguity_is_checked_before_blocking_tests():
    result = route(answers(goal_ambiguous=0.8, tests_blocking=0.9))
    assert result.action == "ask"


# Rule 8: high risk with no test evidence.
def test_high_risk_without_tests_fixes():
    result = route(
        answers(scores={"risk_regression": ScoreAnswer(2.4, 0.8, 3)}),
        facts=Facts(diff_empty=False, tests_ran=False),
    )
    assert result.action == "fix"
    assert result.confidence == 0.8
    assert "rule:risk_without_tests" in result.policy_trace


def test_high_risk_with_passing_tests_is_allowed():
    result = route(answers(scores={"risk_regression": ScoreAnswer(2.4, 0.8, 3)}))
    assert result.action == "done"


# Rule 9 and confidence.
def test_clean_state_is_done():
    result = route(answers())
    assert result.action == "done"
    assert result.confidence == pytest.approx(0.9, abs=0.01)


def test_done_on_weak_signals_reports_low_confidence():
    result = route(answers(goal_addressed=0.55, goal_ambiguous=0.45))
    assert result.action == "done"
    assert result.confidence < 0.2


# Cross-check.
def test_disagreement_is_recorded_but_does_not_change_default_profile():
    result = route(answers(choices={"next_action": ChoiceAnswer("fix", 0.9)}))
    assert result.action == "done"
    assert "crosscheck:disagree" in result.policy_trace


def test_strict_downgrades_done_when_the_crosscheck_disagrees():
    result = route(
        answers(choices={"next_action": ChoiceAnswer("fix", 0.9)}),
        profile="strict",
    )
    assert result.action == "ask"
    assert "strict:downgrade_done" in result.policy_trace


def test_strict_ignores_a_low_confidence_disagreement():
    result = route(
        answers(choices={"next_action": ChoiceAnswer("fix", 0.2)}),
        profile="strict",
    )
    assert result.action == "done"


# Profile gates.
def test_strict_asks_when_code_changed_without_tests():
    result = route(
        answers(),
        facts=Facts(diff_empty=False, tests_ran=False),
        profile="strict",
        missing=["tests"],
    )
    assert result.action == "ask"
    assert "strict:no_tests" in result.policy_trace


def test_ci_requires_a_passing_test_run_for_done():
    result = route(
        answers(),
        facts=Facts(diff_empty=False, tests_ran=False),
        profile="ci",
        missing=["tests"],
    )
    assert result.action == "fix"
    assert "ci:needs_passing_tests" in result.policy_trace


def test_ci_fixes_when_git_is_missing():
    result = route(answers(), profile="ci", missing=["git"])
    assert result.action == "fix"
    assert "ci:no_git" in result.policy_trace


def test_ci_allows_done_with_passing_tests():
    result = route(answers(), profile="ci")
    assert result.action == "done"


def test_unknown_profile_raises():
    with pytest.raises(InvalidProfileError) as exc:
        route(answers(), profile="nope")
    assert exc.value.code == "INVALID_PROFILE"


# Missing answers must not crash the policy.
def test_missing_nouls_are_skipped():
    result = route(JevAnswers(model="m"))
    assert result.action == "done"


# facts_from_payloads.
def test_facts_from_payloads_reads_both_collectors():
    facts = facts_from_payloads(
        {"diff": "+x", "changed_files": ["a.py"]},
        {"exit_code": 2, "timed_out": False},
    )
    assert facts.diff_empty is False
    assert facts.tests_ran is True
    assert facts.tests_exit_code == 2


def test_facts_from_payloads_handles_absent_signals():
    facts = facts_from_payloads(None, None)
    assert facts.diff_empty is True
    assert facts.tests_ran is False
```

- [ ] **Step 2: Run and confirm failure**

Run: `poetry run pytest tests/test_policy.py -v`

Expected: `ModuleNotFoundError: No module named 'jev_mcp.decision'`.

- [ ] **Step 3: Implement `decision/policy.py`**

```python
# src/jev_mcp/decision/__init__.py
```

```python
# src/jev_mcp/decision/policy.py
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
    """Deterministic inputs the policy trusts ahead of any model answer."""

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
    return Facts(
        diff_empty=diff_empty,
        tests_ran=True,
        tests_exit_code=tests.get("exit_code"),
        tests_timed_out=bool(tests.get("timed_out")),
    )


def decisiveness(noul: float) -> float:
    """How far a noul committed; a noul has no confidence field of its own."""
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
            [f"tests exited with code {facts.tests_exit_code}"],
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
    """next_action never drives the decision; it only annotates or, in strict, downgrades."""
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
    """Extra conditions a 'done' must satisfy under the stricter profiles."""
    if profile == "strict" and not facts.tests_ran and not facts.diff_empty:
        return _result(
            ACTION_ASK,
            1.0,
            [*result.reasons, "strict: code changed but no test signal was supplied"],
            [*result.policy_trace, "strict:no_tests", "route:ask"],
        )

    if profile == "ci":
        if "git" in missing_signals:
            return _result(
                ACTION_FIX,
                1.0,
                [*result.reasons, "ci: no git signal was supplied"],
                [*result.policy_trace, "ci:no_git", "route:fix"],
            )
        if not facts.tests_ran or facts.tests_exit_code != 0:
            return _result(
                ACTION_FIX,
                1.0,
                [*result.reasons, "ci: done requires a passing test run"],
                [*result.policy_trace, "ci:needs_passing_tests", "route:fix"],
            )

    return result
```

- [ ] **Step 4: Run the policy tests**

Run: `poetry run pytest tests/test_policy.py -v`

Expected: all pass (24 cases).

- [ ] **Step 5: Write the envelope test**

```python
# tests/test_envelope.py
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
```

- [ ] **Step 6: Implement `decision/envelope.py`**

```python
# src/jev_mcp/decision/envelope.py
from __future__ import annotations

from jev_mcp.decision.policy import POLICY_ID, DecideResult
from jev_mcp.jev.answers import JevAnswers
from jev_mcp.jev.questions import QUESTIONSET_ID


def build_decide_payload(
    result: DecideResult,
    answers: JevAnswers,
    *,
    model: str,
    missing_signals: list[str],
) -> dict:
    return {
        "action": result.action,
        "confidence": result.confidence,
        "reasons": list(result.reasons),
        "policy_trace": list(result.policy_trace),
        "missing_signals": list(missing_signals),
        "jev": {
            "model": answers.model or model,
            "questionset_id": QUESTIONSET_ID,
            "policy_id": POLICY_ID,
            "answers": answers.as_dict(),
        },
    }
```

- [ ] **Step 7: Run both test files and lint**

Run: `poetry run pytest tests/test_policy.py tests/test_envelope.py -v && poetry run ruff check src tests`

- [ ] **Step 8: Commit**

```bash
git add src/jev_mcp/decision tests/test_policy.py tests/test_envelope.py
git commit -m "feat: add decision policy with deterministic facts and cross-check"
```
