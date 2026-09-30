from __future__ import annotations

from typesafe_sdk import Choice, Noul, Score

QUESTIONSET_ID = "engineering-gate-v3"

NOUL_KEYS: tuple[str, ...] = (
    "goal_addressed",
    "goal_ambiguous",
    "tests_blocking",
    "incomplete_work",
    "scope_creep",
)
SCORE_KEYS: tuple[str, ...] = ("risk_regression",)
CHOICE_KEYS: tuple[str, ...] = ("next_action",)

RISK_LEVELS: list[str] = [
    "Localized change: one module, with no behavior visible outside it",
    "Several modules changed, or one user-visible behavior changed",
    "Broad change, or it touches a critical path such as authentication, payments, or data migrations",
    "Likely to break existing behavior unless strong test evidence says otherwise",
]


def build_questions() -> dict[str, object]:
    """Agent-summary gate: atomic signals from goal + extra, plus one cross-check."""
    return {
        "goal_addressed": Noul(
            instructions=(
                "Given `goal` and what the agent wrote in `extra` (especially `extra.summary`), "
                "the described work implements what the goal asks for. "
                "Judge only whether the summary shows the goal is met, not elegance or unrelated polish."
            )
        ),
        "goal_ambiguous": Noul(
            instructions=(
                "The stated `goal` is too vague or underspecified to tell from `extra` whether the work is complete. "
                "This is about the goal wording and missing detail in `extra`, not code quality."
            )
        ),
        "tests_blocking": Noul(
            instructions=(
                "From `tests` and/or `extra.verification`, the reported test outcome shows failures, errors, "
                "or collection problems that block completing this task. "
                "Skipped tests, deprecation warnings, and passing runs are not blocking."
            )
        ),
        "incomplete_work": Noul(
            instructions=(
                "From `extra.summary` and any other `extra` fields, the agent's description still shows "
                "obviously unfinished work: TODO/FIXME left in scope, stubbed behavior, NotImplementedError, "
                "debug leftovers, or large commented-out blocks they admit are not done."
            )
        ),
        "scope_creep": Noul(
            instructions=(
                "From `extra.summary`, the described changes include substantial work unrelated to `goal`, "
                "beyond incidental formatting, imports, or lockfile updates."
            )
        ),
        "risk_regression": Score(
            instructions=(
                "From `extra.summary` and `goal`, how much of the system could this described change break?"
            ),
            criteria=list(RISK_LEVELS),
        ),
        "next_action": Choice(
            instructions=(
                "An engineering agent reported work toward `goal` in `extra`. "
                "What should it do next?"
            ),
            criteria={
                "fix": (
                    "Keep working: the summary shows gaps, tests fail or are blocking, "
                    "or the goal is not met yet."
                ),
                "ask_user": (
                    "Stop and ask a person: the goal is unclear, or finishing needs a decision "
                    "the agent cannot make on its own."
                ),
                "done": (
                    "The summary shows the goal is addressed and the reported test evidence "
                    "(if any) supports stopping here."
                ),
            },
        ),
    }
