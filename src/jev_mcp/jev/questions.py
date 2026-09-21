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
