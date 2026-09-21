from dataclasses import dataclass

from jev_mcp.jev.answers import JevAnswers, ScoreAnswer, normalize_response
from jev_mcp.jev.questions import build_questions


@dataclass
class FakeNoul:
    noul: float


@dataclass
class FakeChoice:
    choice: str
    confidence: float
    probabilities: dict


@dataclass
class FakeScore:
    score: float
    confidence: float
    probabilities: dict


class FakeResponse:
    model = "jev-1.13"

    def __init__(self, nouls=None, choices=None, scores=None):
        self.nouls = nouls or {}
        self.choices = choices or {}
        self.scores = scores or {}


def test_normalize_flattens_every_primitive():
    response = FakeResponse(
        nouls={"goal_addressed": FakeNoul(0.9)},
        choices={"next_action": FakeChoice("done", 0.8, {"done": 0.8, "fix": 0.2})},
        scores={"risk_regression": FakeScore(1.5, 0.6, {0: 0.1, 1: 0.4, 2: 0.4, 3: 0.1})},
    )
    answers = normalize_response(response, build_questions())
    assert answers.model == "jev-1.13"
    assert answers.nouls["goal_addressed"] == 0.9
    assert answers.choices["next_action"].choice == "done"
    assert answers.choices["next_action"].confidence == 0.8
    assert answers.scores["risk_regression"].score == 1.5
    assert answers.scores["risk_regression"].top_level == 3


def test_score_normalizes_against_its_top_level():
    assert ScoreAnswer(score=1.5, confidence=0.6, top_level=3).normalized == 0.5
    assert ScoreAnswer(score=3.0, confidence=1.0, top_level=3).normalized == 1.0
    assert ScoreAnswer(score=0.0, confidence=1.0, top_level=3).normalized == 0.0


def test_as_dict_is_json_serializable():
    import json

    answers = JevAnswers(model="m", nouls={"a": 0.5})
    json.dumps(answers.as_dict())
