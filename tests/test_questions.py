from typesafe_sdk import Choice, Noul, Score

from jev_mcp.jev.questions import CHOICE_KEYS, NOUL_KEYS, QUESTIONSET_ID, RISK_LEVELS, build_questions


def test_questionset_id_is_versioned():
    assert QUESTIONSET_ID == "engineering-gate-v2"


def test_every_declared_key_is_built():
    questions = build_questions()
    for key in (*NOUL_KEYS, *CHOICE_KEYS, "risk_regression"):
        assert key in questions


def test_primitive_types_match_the_spec():
    questions = build_questions()
    assert all(isinstance(questions[key], Noul) for key in NOUL_KEYS)
    assert isinstance(questions["risk_regression"], Score)
    assert isinstance(questions["next_action"], Choice)


def test_risk_has_four_described_levels():
    assert len(RISK_LEVELS) == 4
    assert all(len(level) > 20 for level in RISK_LEVELS)


def test_choice_options_have_descriptions():
    criteria = build_questions()["next_action"].criteria
    assert set(criteria) == {"fix", "ask_user", "done"}
    assert all(isinstance(text, str) and text for text in criteria.values())
