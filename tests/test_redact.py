import pytest

from jev_mcp.util.redact import PLACEHOLDER, redact_text


@pytest.mark.parametrize(
    "secret_line",
    [
        "Authorization: Bearer abcdef1234567890",
        'api_key = "sk-abcdefghijklmnop"',
        "TYPESAFE_API_KEY=supersecretvalue",
        "token: ghp_abcdefghijklmnopqrstuvwxyz0123",
    ],
)
def test_known_secret_shapes_are_scrubbed(secret_line):
    cleaned = redact_text(secret_line)
    assert PLACEHOLDER in cleaned
    for fragment in (
        "abcdef1234567890",
        "sk-abcdefghijklmnop",
        "supersecretvalue",
        "ghp_abcdefghij",
    ):
        assert fragment not in cleaned


def test_ordinary_code_is_left_alone():
    source = "def add(a, b):\n    return a + b\n"
    assert redact_text(source) == source
