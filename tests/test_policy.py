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


def test_clean_state_is_done():
    result = route(answers())
    assert result.action == "done"
    assert result.confidence == pytest.approx(0.9, abs=0.01)


def test_done_on_weak_signals_reports_low_confidence():
    result = route(answers(goal_addressed=0.55, goal_ambiguous=0.45))
    assert result.action == "done"
    assert result.confidence < 0.2


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


def test_missing_nouls_are_skipped():
    result = route(JevAnswers(model="m"))
    assert result.action == "done"


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
