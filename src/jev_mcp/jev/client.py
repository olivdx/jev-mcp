from __future__ import annotations

import json

import typesafe_sdk

from jev_mcp.config import AppConfig
from jev_mcp.errors import (
    ApiUnreachableError,
    AuthFailedError,
    JevError,
    JevTimeoutError,
    RateLimitedError,
)
from jev_mcp.jev.answers import JevAnswers, normalize_response
from jev_mcp.jev.questions import QUESTIONSET_ID, build_questions
from jev_mcp.logger import trace


async def evaluate_state(state: dict, cfg: AppConfig, api_key: str) -> JevAnswers:
    questions = build_questions()
    trace(
        "jev_request",
        model=cfg.jev.model,
        questionset_id=QUESTIONSET_ID,
        question_count=len(questions),
        state_bytes=len(json.dumps(state, default=str).encode("utf-8")),
    )

    try:
        async with typesafe_sdk.AsyncTypeSafeClient(
            api_key=api_key,
            model=cfg.jev.model,
            retry=typesafe_sdk.RetryPolicy(max_retries=cfg.jev.max_retries),
            timeout=cfg.jev.request_timeout_s,
        ) as client:
            response = await client.system_one(state=state, questions=questions)
    except Exception as exc:
        raise _map_sdk_error(exc) from exc

    return normalize_response(response, questions)


def _map_sdk_error(exc: Exception) -> Exception:
    if isinstance(exc, typesafe_sdk.TypeSafeAuthenticationError):
        return AuthFailedError("TypeSafe rejected the API key (401)")
    if isinstance(exc, typesafe_sdk.TypeSafeRateLimitError):
        wait_ms = getattr(exc, "retry_after_ms", None)
        suffix = f"; retry after {wait_ms} ms" if wait_ms else ""
        return RateLimitedError(f"TypeSafe rate limit reached (429){suffix}")
    if isinstance(exc, typesafe_sdk.TypeSafeAPITimeoutError):
        return JevTimeoutError("TypeSafe request timed out")
    if isinstance(exc, typesafe_sdk.TypeSafeAPIConnectionError):
        return ApiUnreachableError("Cannot reach the TypeSafe API")
    if isinstance(exc, typesafe_sdk.TypeSafeAPIError):
        detail = str(exc).strip() or getattr(exc, "_message", "") or "request rejected"
        return JevError(f"TypeSafe API error (status {exc.status}): {detail}")
    if isinstance(exc, typesafe_sdk.TypeSafeError):
        return JevError(str(exc))
    return exc
