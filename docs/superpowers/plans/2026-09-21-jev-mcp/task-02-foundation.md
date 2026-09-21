# Task 2 — Errors, logging, paths, redaction, response envelope

**Deliverable:** The shared primitives every later module imports, plus the test-isolation fixture that keeps the suite away from the developer's real `~/.jev-mcp`.

**Files:**
- Create: `src/jev_mcp/errors.py`
- Create: `src/jev_mcp/logger.py`
- Create: `src/jev_mcp/util/__init__.py`, `src/jev_mcp/util/paths.py`, `src/jev_mcp/util/redact.py`, `src/jev_mcp/util/responses.py`
- Create: `tests/conftest.py`
- Create: `tests/test_errors.py`, `tests/test_paths.py`, `tests/test_redact.py`, `tests/test_responses.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `JevMcpError` and subclasses, `jev_home()`, `config_path()`, `credentials_path()`, `resolve_project_root()`, `redact_text()`, `tool_response()`, `new_request_id()`, `trace()`, `configure()`.

---

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_errors.py
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
```

```python
# tests/test_paths.py
import pytest

from jev_mcp.errors import PathInvalidError
from jev_mcp.util.paths import config_path, credentials_path, jev_home, resolve_project_root


def test_home_follows_the_env_override(isolated_home):
    assert jev_home() == isolated_home
    assert config_path() == isolated_home / "config.yaml"
    assert credentials_path() == isolated_home / "credentials.yaml"


def test_resolve_project_root_returns_resolved_directory(tmp_path):
    assert resolve_project_root(str(tmp_path)) == tmp_path.resolve()


@pytest.mark.parametrize("raw", ["", "   "])
def test_resolve_project_root_rejects_blank(raw):
    with pytest.raises(PathInvalidError) as exc:
        resolve_project_root(raw)
    assert exc.value.code == "PATH_INVALID"


def test_resolve_project_root_rejects_missing_directory(tmp_path):
    with pytest.raises(PathInvalidError):
        resolve_project_root(str(tmp_path / "nope"))


def test_resolve_project_root_rejects_a_file(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(PathInvalidError):
        resolve_project_root(str(target))
```

```python
# tests/test_redact.py
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
    for fragment in ("abcdef1234567890", "sk-abcdefghijklmnop", "supersecretvalue", "ghp_abcdefghij"):
        assert fragment not in cleaned


def test_ordinary_code_is_left_alone():
    source = "def add(a, b):\n    return a + b\n"
    assert redact_text(source) == source
```

```python
# tests/test_responses.py
from jev_mcp.util.responses import SCHEMA_VERSION, tool_response


def test_envelope_carries_the_common_fields():
    out = tool_response({"branch": "main"}, request_id="fixed-id", duration_ms=10)
    assert out["schema_version"] == SCHEMA_VERSION
    assert out["request_id"] == "fixed-id"
    assert out["duration_ms"] == 10
    assert out["errors"] == []
    assert out["branch"] == "main"


def test_errors_are_passed_through():
    out = tool_response(
        {},
        request_id="r",
        duration_ms=1,
        errors=[{"code": "GIT_FAILED", "message": "boom"}],
    )
    assert out["errors"][0]["code"] == "GIT_FAILED"
```

- [ ] **Step 2: Create the isolation fixture**

This is the fixture that prevents any test from reading or deleting the developer's real key.

```python
# tests/conftest.py
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point JEV_MCP_HOME at a temp dir so no test can touch the real ~/.jev-mcp."""
    home = tmp_path / "jev-home"
    home.mkdir()
    monkeypatch.setenv("JEV_MCP_HOME", str(home))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    return home
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `poetry run pytest tests/test_errors.py tests/test_paths.py tests/test_redact.py tests/test_responses.py -v`

Expected: collection errors — `ModuleNotFoundError: No module named 'jev_mcp.errors'`.

- [ ] **Step 4: Implement `errors.py`**

```python
# src/jev_mcp/errors.py
from __future__ import annotations


class JevMcpError(Exception):
    """Base error carrying a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class NotConfiguredError(JevMcpError):
    def __init__(self) -> None:
        super().__init__(
            "NOT_CONFIGURED",
            "No TypeSafe API key. Run 'jev-mcp key add <API_KEY>' or set TYPESAFE_API_KEY.",
        )


class InvalidKeyError(JevMcpError):
    def __init__(self, message: str = "TypeSafe rejected the API key") -> None:
        super().__init__("INVALID_KEY", message)


class AuthFailedError(JevMcpError):
    def __init__(self, message: str = "TypeSafe authentication failed (401)") -> None:
        super().__init__("AUTH_FAILED", message)


class RateLimitedError(JevMcpError):
    def __init__(self, message: str = "TypeSafe rate limit reached (429)") -> None:
        super().__init__("JEV_RATE_LIMITED", message)


class JevTimeoutError(JevMcpError):
    def __init__(self, message: str = "TypeSafe request timed out") -> None:
        super().__init__("JEV_TIMEOUT", message)


class ApiUnreachableError(JevMcpError):
    def __init__(self, message: str = "Cannot reach the TypeSafe API") -> None:
        super().__init__("API_UNREACHABLE", message)


class JevError(JevMcpError):
    def __init__(self, message: str = "TypeSafe request failed") -> None:
        super().__init__("JEV_ERROR", message)


class PathInvalidError(JevMcpError):
    def __init__(self, message: str) -> None:
        super().__init__("PATH_INVALID", message)


class NotARepoError(JevMcpError):
    def __init__(self, message: str) -> None:
        super().__init__("NOT_A_REPO", message)


class GitNotFoundError(JevMcpError):
    def __init__(self) -> None:
        super().__init__("GIT_NOT_FOUND", "git was not found on PATH")


class GitFailedError(JevMcpError):
    def __init__(self, message: str) -> None:
        super().__init__("GIT_FAILED", message)


class NoTestCommandError(JevMcpError):
    def __init__(self, message: str) -> None:
        super().__init__("NO_TEST_COMMAND", message)


class TestRunnerFailedError(JevMcpError):
    def __init__(self, message: str) -> None:
        super().__init__("TEST_RUNNER_FAILED", message)


class InvalidProfileError(JevMcpError):
    def __init__(self, message: str) -> None:
        super().__init__("INVALID_PROFILE", message)
```

- [ ] **Step 5: Implement `util/redact.py`**

```python
# src/jev_mcp/util/redact.py
from __future__ import annotations

import re

PLACEHOLDER = "<REDACTED>"

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{10,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"(?i)\b[A-Z0-9_]*(?:api[_-]?key|secret|token|password|passwd)[A-Z0-9_]*\b"
        r"\s*[:=]\s*[\"']?[^\s\"',]{6,}"
    ),
)


def redact_text(text: str) -> str:
    """Replace well-known secret shapes before text reaches Jev or the logs."""
    cleaned = text
    for pattern in _PATTERNS:
        cleaned = pattern.sub(PLACEHOLDER, cleaned)
    return cleaned
```

- [ ] **Step 6: Implement `util/paths.py`**

```python
# src/jev_mcp/util/paths.py
from __future__ import annotations

import os
from pathlib import Path

from jev_mcp.errors import PathInvalidError

ENV_HOME = "JEV_MCP_HOME"


def jev_home() -> Path:
    """Root for config.yaml and credentials.yaml; overridable so tests stay isolated."""
    raw = os.getenv(ENV_HOME)
    if raw and raw.strip():
        return Path(raw).expanduser()
    return Path.home() / ".jev-mcp"


def config_path() -> Path:
    return jev_home() / "config.yaml"


def credentials_path() -> Path:
    return jev_home() / "credentials.yaml"


def resolve_project_root(raw: str) -> Path:
    if not raw or not raw.strip():
        raise PathInvalidError("project_root is empty")
    try:
        resolved = Path(raw).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PathInvalidError(f"Cannot resolve project_root: {raw}") from exc
    if not resolved.is_dir():
        raise PathInvalidError(f"project_root is not a directory: {resolved}")
    return resolved
```

```python
# src/jev_mcp/util/__init__.py
```

- [ ] **Step 7: Implement `util/responses.py`**

```python
# src/jev_mcp/util/responses.py
from __future__ import annotations

SCHEMA_VERSION = "1.0"


def tool_response(
    body: dict,
    *,
    request_id: str,
    duration_ms: int,
    errors: list[dict] | None = None,
) -> dict:
    """Wrap a tool body in the common envelope every jev-mcp response carries."""
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "duration_ms": duration_ms,
        "errors": errors or [],
        **body,
    }
```

- [ ] **Step 8: Implement `logger.py`**

```python
# src/jev_mcp/logger.py
from __future__ import annotations

import json
import logging
import sys
import uuid

from jev_mcp.util.redact import redact_text

logger = logging.getLogger("jev_mcp")

_format = "text"
_redact = True


def configure(level: str = "info", log_format: str = "text", redact: bool = True) -> None:
    """Send structured events to stderr; stdout belongs to the stdio MCP transport."""
    global _format, _redact
    _format = log_format
    _redact = redact
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False


def new_request_id() -> str:
    return str(uuid.uuid4())


def trace(event: str, **fields: object) -> None:
    clean: dict[str, object] = {}
    for key, value in fields.items():
        if value is None:
            continue
        clean[key] = redact_text(value) if _redact and isinstance(value, str) else value
    if _format == "json":
        logger.info(json.dumps({"event": event, **clean}, default=str))
        return
    rendered = " ".join(f"{key}={value}" for key, value in clean.items())
    logger.info("%s %s", event, rendered)
```

- [ ] **Step 9: Run the tests**

Run: `poetry run pytest tests/test_errors.py tests/test_paths.py tests/test_redact.py tests/test_responses.py -v`

Expected: all pass.

- [ ] **Step 10: Lint**

Run: `poetry run ruff check src tests`

Expected: `All checks passed!`

- [ ] **Step 11: Commit**

```bash
git add src/jev_mcp tests
git commit -m "feat: add errors, logging, path, redaction, and response primitives"
```
