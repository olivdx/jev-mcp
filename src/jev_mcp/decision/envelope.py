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
