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
