# Task 9 — TypeSafe client and SDK error mapping

**Deliverable:** One async call to `system_one` with all seven questions in a single request, retries delegated to the SDK, and every SDK exception translated into a stable jev-mcp code.

**Files:**
- Create: `src/jev_mcp/jev/client.py`
- Create: `tests/test_jev_client.py`

**Interfaces:**
- Consumes: `AppConfig` (task 3), `build_questions` / `normalize_response` (task 8), the Jev error classes (task 2), `trace` (task 2).
- Produces: `async def evaluate_state(state: dict, cfg: AppConfig, api_key: str) -> JevAnswers`.

**Two rules this task must not break:**
1. **No hand-rolled retry loop.** `typesafe_sdk` ships `RetryPolicy` (backed by tenacity). Pass `RetryPolicy(max_retries=cfg.jev.max_retries)` and let the SDK do the waiting.
2. **Exception order is most-specific-first.** `TypeSafeAPITimeoutError` subclasses `TypeSafeAPIConnectionError`, and the status-specific errors all subclass `TypeSafeAPIError`. Checking the general class first would swallow the specific one.

**Mapping table:**

| SDK exception | jev-mcp error | Code |
|---|---|---|
| `TypeSafeAuthenticationError` | `AuthFailedError` | `AUTH_FAILED` |
| `TypeSafeRateLimitError` | `RateLimitedError` | `JEV_RATE_LIMITED` |
| `TypeSafeAPITimeoutError` | `JevTimeoutError` | `JEV_TIMEOUT` |
| `TypeSafeAPIConnectionError` | `ApiUnreachableError` | `API_UNREACHABLE` |
| `TypeSafeAPIError` | `JevError` | `JEV_ERROR` |
| `TypeSafeError` | `JevError` | `JEV_ERROR` |

---

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_jev_client.py
import pytest
import typesafe_sdk

from jev_mcp.config import AppConfig
from jev_mcp.errors import (
    ApiUnreachableError,
    AuthFailedError,
    JevError,
    JevTimeoutError,
    RateLimitedError,
)
from jev_mcp.jev.client import evaluate_state

CFG = AppConfig()


class FakeResponse:
    model = "jev-1.13"

    def __init__(self):
        self.nouls = {}
        self.choices = {}
        self.scores = {}


class FakeClient:
    """Stands in for AsyncTypeSafeClient; records what the caller asked for."""

    last_kwargs: dict = {}
    last_call: dict = {}
    raises: Exception | None = None

    def __init__(self, **kwargs):
        FakeClient.last_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def system_one(self, *, state, questions, **kwargs):
        FakeClient.last_call = {"state": state, "questions": questions, **kwargs}
        if FakeClient.raises is not None:
            raise FakeClient.raises
        return FakeResponse()


@pytest.fixture(autouse=True)
def fake_sdk(monkeypatch):
    FakeClient.raises = None
    monkeypatch.setattr(typesafe_sdk, "AsyncTypeSafeClient", FakeClient)
    return FakeClient


async def test_all_questions_go_in_one_request():
    await evaluate_state({"goal": "x"}, CFG, "key")
    questions = FakeClient.last_call["questions"]
    assert len(questions) == 7
    assert "next_action" in questions


async def test_client_gets_key_model_timeout_and_retry_policy():
    await evaluate_state({"goal": "x"}, CFG, "the-key")
    kwargs = FakeClient.last_kwargs
    assert kwargs["api_key"] == "the-key"
    assert kwargs["model"] == CFG.jev.model
    assert kwargs["timeout"] == CFG.jev.request_timeout_s
    assert isinstance(kwargs["retry"], typesafe_sdk.RetryPolicy)


@pytest.mark.parametrize(
    ("sdk_error", "expected"),
    [
        (typesafe_sdk.TypeSafeAuthenticationError, AuthFailedError),
        (typesafe_sdk.TypeSafeRateLimitError, RateLimitedError),
        (typesafe_sdk.TypeSafeAPITimeoutError, JevTimeoutError),
        (typesafe_sdk.TypeSafeAPIConnectionError, ApiUnreachableError),
        (typesafe_sdk.TypeSafeAPIError, JevError),
    ],
)
async def test_sdk_errors_map_to_stable_codes(sdk_error, expected, monkeypatch):
    FakeClient.raises = _build(sdk_error)
    with pytest.raises(expected):
        await evaluate_state({"goal": "x"}, CFG, "key")


def _build(sdk_error: type[Exception]) -> Exception:
    """Instantiate an SDK error regardless of its constructor shape."""
    for args in ((), ("boom",), (500, None, {}, None), (500, None, {}, None, None)):
        try:
            return sdk_error(*args)
        except TypeError:
            continue
    raise AssertionError(f"Cannot construct {sdk_error!r}")


async def test_unknown_errors_are_not_swallowed():
    FakeClient.raises = ValueError("something else")
    with pytest.raises(ValueError):
        await evaluate_state({"goal": "x"}, CFG, "key")
```

- [ ] **Step 2: Run and confirm failure**

Run: `poetry run pytest tests/test_jev_client.py -v`

Expected: `ModuleNotFoundError: No module named 'jev_mcp.jev.client'`.

- [ ] **Step 3: Implement `jev/client.py`**

```python
# src/jev_mcp/jev/client.py
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
    """Ask the whole question set in one request; the questions run in parallel server-side."""
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
    except Exception as exc:  # narrowed immediately by the mapper below
        raise _map_sdk_error(exc) from exc

    return normalize_response(response, questions)


def _map_sdk_error(exc: Exception) -> Exception:
    """Translate SDK exceptions into stable codes; unknown errors pass through unchanged."""
    # Most specific first: timeout subclasses connection, and the status errors subclass APIError.
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
        return JevError(f"TypeSafe API error (status {getattr(exc, 'status', 'unknown')})")
    if isinstance(exc, typesafe_sdk.TypeSafeError):
        return JevError(str(exc))
    return exc
```

- [ ] **Step 4: Run the tests**

Run: `poetry run pytest tests/test_jev_client.py -v`

Expected: all pass, including the five mapping cases.

- [ ] **Step 5: Confirm the real SDK surface matches**

Run:

```bash
poetry run python -c "import typesafe_sdk; print(typesafe_sdk.__version__ if hasattr(typesafe_sdk,'__version__') else 'n/a'); print(hasattr(typesafe_sdk,'AsyncTypeSafeClient'), hasattr(typesafe_sdk,'RetryPolicy'))"
```

Expected: `True True`. If `RetryPolicy` does not accept `max_retries` in the installed version, check `poetry run python -c "import typesafe_sdk, inspect; print(inspect.signature(typesafe_sdk.RetryPolicy))"` and use the field it does expose — but still do not write a retry loop.

- [ ] **Step 6: Commit**

```bash
git add src/jev_mcp/jev/client.py tests/test_jev_client.py
git commit -m "feat: add TypeSafe client with SDK-owned retries and error mapping"
```
