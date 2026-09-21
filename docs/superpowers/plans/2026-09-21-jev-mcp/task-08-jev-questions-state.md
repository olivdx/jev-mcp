# Task 8 — Question set, answer normalization, state builder

**Deliverable:** The `engineering-gate-v2` question set with descriptive criteria, a normalizer that turns a `SystemOneResponse` into plain values, and the redacted state payload sent to Jev.

**Files:**
- Create: `src/jev_mcp/jev/__init__.py`, `src/jev_mcp/jev/questions.py`, `src/jev_mcp/jev/answers.py`, `src/jev_mcp/jev/state_builder.py`
- Create: `tests/test_questions.py`, `tests/test_answers.py`, `tests/test_state_builder.py`

**Interfaces:**
- Consumes: `redact_text` (task 2).
- Produces: `QUESTIONSET_ID`, `RISK_LEVELS`, `build_questions`, `ChoiceAnswer`, `ScoreAnswer`, `JevAnswers`, `normalize_response`, `build_state`.

**Why the criteria carry descriptions:** the Score documentation shows that label-only levels collapse calibration — `["0","1","2"]` produced confidence 0.33 where descriptive levels produced 1.0. Every option and level below describes a situation, not a degree.

**Score semantics to honor:** `score` is a probability-weighted mean from `0` to `len(criteria) - 1`. `ScoreAnswer.normalized` divides by `top_level` so thresholds do not depend on how many levels a question has. Nouls return a bare probability with no confidence field.

---

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_questions.py
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
```

```python
# tests/test_answers.py
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
```

```python
# tests/test_state_builder.py
from jev_mcp.jev.state_builder import build_state


def test_goal_only_records_missing_signals():
    state, missing = build_state(goal="add retry")
    assert state["goal"] == "add retry"
    assert sorted(missing) == ["git", "tests"]


def test_git_and_tests_are_included():
    git = {
        "branch": "main",
        "is_clean": False,
        "changed_files": ["a.py"],
        "diff_stat": "1 file changed",
        "diff": "+print('x')",
        "omitted_files": [{"path": "big.lock", "bytes": 9}],
    }
    tests = {
        "command": ["pytest"],
        "exit_code": 1,
        "timed_out": False,
        "stdout": "1 failed",
        "stderr": "",
    }
    state, missing = build_state(goal="fix bug", git=git, tests=tests)
    assert missing == []
    assert state["git"]["changed_files"] == ["a.py"]
    assert state["git"]["omitted_files"] == ["big.lock"]
    assert state["tests"]["exit_code"] == 1


def test_secrets_are_redacted_before_leaving_the_machine():
    git = {"diff": "+TYPESAFE_API_KEY=supersecretvalue", "changed_files": [], "diff_stat": ""}
    state, _ = build_state(goal="rotate key", git=git)
    assert "supersecretvalue" not in state["git"]["diff"]


def test_extra_is_passed_through():
    state, _ = build_state(goal="g", extra={"notes": "context"})
    assert state["extra"]["notes"] == "context"
```

- [ ] **Step 2: Run and confirm failure**

Run: `poetry run pytest tests/test_questions.py tests/test_answers.py tests/test_state_builder.py -v`

Expected: `ModuleNotFoundError: No module named 'jev_mcp.jev'`.

- [ ] **Step 3: Implement `jev/questions.py`**

```python
# src/jev_mcp/jev/__init__.py
```

```python
# src/jev_mcp/jev/questions.py
from __future__ import annotations

from typesafe_sdk import Choice, Noul, Score

QUESTIONSET_ID = "engineering-gate-v2"

NOUL_KEYS: tuple[str, ...] = (
    "goal_addressed",
    "goal_ambiguous",
    "tests_blocking",
    "incomplete_work",
    "scope_creep",
)
SCORE_KEYS: tuple[str, ...] = ("risk_regression",)
CHOICE_KEYS: tuple[str, ...] = ("next_action",)

# Levels describe situations, not degrees: label-only criteria collapse calibration.
RISK_LEVELS: list[str] = [
    "Localized change: one module, with no behavior visible outside it",
    "Several modules changed, or one user-visible behavior changed",
    "Broad change, or it touches a critical path such as authentication, payments, or data migrations",
    "Likely to break existing behavior unless strong test evidence says otherwise",
]


def build_questions() -> dict[str, object]:
    """The engineering-gate-v2 set: atomic signals plus one cross-check."""
    return {
        "goal_addressed": Noul(
            instructions=(
                "The code changes in the diff implement what the stated goal describes. "
                "Judge only whether the change does the thing the goal asks for, "
                "not whether it is elegant or complete in other respects."
            )
        ),
        "goal_ambiguous": Noul(
            instructions=(
                "The stated goal is too vague or underspecified to tell whether the diff completes it. "
                "This is about the wording of the goal, not the quality of the change."
            )
        ),
        "tests_blocking": Noul(
            instructions=(
                "The test output reports failures, errors, or collection problems that block "
                "completing this task. Skipped tests, deprecation warnings, and passing runs "
                "are not blocking."
            )
        ),
        "incomplete_work": Noul(
            instructions=(
                "The diff contains obviously unfinished work: newly added TODO or FIXME markers, "
                "stubbed functions, bodies that only raise NotImplementedError or pass, "
                "leftover debug prints, or large blocks of commented-out code."
            )
        ),
        "scope_creep": Noul(
            instructions=(
                "The diff contains substantial changes unrelated to the stated goal, "
                "beyond incidental formatting, imports, or lockfile updates."
            )
        ),
        "risk_regression": Score(
            instructions="How much of the system could this change break?",
            criteria=list(RISK_LEVELS),
        ),
        "next_action": Choice(
            instructions=(
                "An engineering agent made this change toward the stated goal. "
                "What should it do next?"
            ),
            criteria={
                "fix": (
                    "Keep working: the change is incomplete, tests fail, "
                    "or the diff has obvious gaps."
                ),
                "ask_user": (
                    "Stop and ask a person: the goal is unclear, or finishing needs a decision "
                    "the agent cannot make on its own."
                ),
                "done": (
                    "The change addresses the goal and the available test evidence supports "
                    "stopping here."
                ),
            },
        ),
    }
```

- [ ] **Step 4: Implement `jev/answers.py`**

```python
# src/jev_mcp/jev/answers.py
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
        """Score on 0..1 so thresholds do not depend on the number of levels."""
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
    """Flatten a SystemOneResponse into plain values the policy can reason about."""
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
```

- [ ] **Step 5: Implement `jev/state_builder.py`**

```python
# src/jev_mcp/jev/state_builder.py
from __future__ import annotations

from jev_mcp.util.redact import redact_text


def build_state(
    *,
    goal: str,
    git: dict | None = None,
    tests: dict | None = None,
    extra: dict | None = None,
) -> tuple[dict, list[str]]:
    """Assemble the Jev state and report which signals the caller did not supply."""
    missing: list[str] = []
    state: dict = {"goal": redact_text(goal)}

    if git:
        state["git"] = {
            "branch": git.get("branch"),
            "is_clean": git.get("is_clean"),
            "changed_files": list(git.get("changed_files", [])),
            "untracked_files": list(git.get("untracked_files", [])),
            "diff_stat": redact_text(str(git.get("diff_stat", ""))),
            "diff": redact_text(str(git.get("diff", ""))),
            "omitted_files": [entry.get("path") for entry in git.get("omitted_files", [])],
        }
    else:
        missing.append("git")

    if tests:
        state["tests"] = {
            "command": tests.get("command"),
            "exit_code": tests.get("exit_code"),
            "timed_out": tests.get("timed_out"),
            "stdout": redact_text(str(tests.get("stdout", ""))),
            "stderr": redact_text(str(tests.get("stderr", ""))),
        }
    else:
        missing.append("tests")

    if extra:
        state["extra"] = extra

    return state, missing
```

- [ ] **Step 6: Run the tests**

Run: `poetry run pytest tests/test_questions.py tests/test_answers.py tests/test_state_builder.py -v`

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/jev_mcp/jev tests/test_questions.py tests/test_answers.py tests/test_state_builder.py
git commit -m "feat: add engineering-gate-v2 questions, answer normalization, and state builder"
```
