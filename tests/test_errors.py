import pytest

from jev_mcp.errors import JevMcpError, NotConfiguredError, PathInvalidError


def test_error_exposes_code_and_message():
    error = JevMcpError("SOME_CODE", "something went wrong")
    assert error.code == "SOME_CODE"
    assert error.message == "something went wrong"
    assert str(error) == "[SOME_CODE] something went wrong"


@pytest.mark.parametrize(
    ("factory", "expected_code"),
    [
        (NotConfiguredError, "NOT_CONFIGURED"),
        (lambda: PathInvalidError("bad path"), "PATH_INVALID"),
    ],
)
def test_subclasses_carry_their_code(factory, expected_code):
    assert factory().code == expected_code


def test_not_configured_message_tells_the_user_what_to_run():
    assert "jev-mcp key add" in NotConfiguredError().message
