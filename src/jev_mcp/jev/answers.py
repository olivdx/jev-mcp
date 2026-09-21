from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChoiceAnswer:
    choice: str
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoreAnswer:
    score: float
    confidence: float
    top_level: int
    probabilities: dict[int, float] = field(default_factory=dict)

    @property
    def normalized(self) -> float:
        return self.score / self.top_level if self.top_level > 0 else 0.0


@dataclass(frozen=True)
class JevAnswers:
    model: str
    nouls: dict[str, float] = field(default_factory=dict)
    choices: dict[str, ChoiceAnswer] = field(default_factory=dict)
    scores: dict[str, ScoreAnswer] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "nouls": dict(self.nouls),
            "choices": {
                key: {
                    "choice": value.choice,
                    "confidence": value.confidence,
                    "probabilities": value.probabilities,
                }
                for key, value in self.choices.items()
            },
            "scores": {
                key: {
                    "score": value.score,
                    "confidence": value.confidence,
                    "top_level": value.top_level,
                    "normalized": round(value.normalized, 4),
                    "probabilities": {str(k): v for k, v in value.probabilities.items()},
                }
                for key, value in self.scores.items()
            },
        }


def normalize_response(response, questions: dict) -> JevAnswers:
    nouls = {key: float(answer.noul) for key, answer in dict(response.nouls).items()}

    choices = {
        key: ChoiceAnswer(
            choice=str(answer.choice),
            confidence=float(answer.confidence),
            probabilities={
                str(name): float(value)
                for name, value in dict(getattr(answer, "probabilities", {}) or {}).items()
            },
        )
        for key, answer in dict(response.choices).items()
    }

    scores: dict[str, ScoreAnswer] = {}
    for key, answer in dict(response.scores).items():
        criteria = getattr(questions.get(key), "criteria", None) or []
        scores[key] = ScoreAnswer(
            score=float(answer.score),
            confidence=float(answer.confidence),
            top_level=max(len(criteria) - 1, 1),
            probabilities={
                int(level): float(value)
                for level, value in dict(getattr(answer, "probabilities", {}) or {}).items()
            },
        )

    return JevAnswers(
        model=str(getattr(response, "model", "") or ""),
        nouls=nouls,
        choices=choices,
        scores=scores,
    )
