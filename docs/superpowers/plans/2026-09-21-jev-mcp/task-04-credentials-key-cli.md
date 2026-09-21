# Task 4 — Credentials and the `jev-mcp key` commands

**Deliverable:** API key storage with env-over-file precedence, verification against TypeSafe before persisting, and the `key add|status|remove` CLI group.

**Files:**
- Create: `src/jev_mcp/credentials.py`
- Create: `src/jev_mcp/cli/key.py`
- Modify: `src/jev_mcp/cli/main.py` (register the `key` group)
- Create: `tests/test_credentials.py`, `tests/test_cli_key.py`

**Interfaces:**
- Consumes: `credentials_path()` (task 2), `InvalidKeyError`, `ApiUnreachableError` (task 2).
- Produces: `resolve_api_key`, `save_api_key`, `remove_api_key`, `mask`, `verify_api_key`, `key_app`.

**Safety rule:** every function takes an explicit `path` keyword. Tests must never call these against the real home — the autouse `isolated_home` fixture from task 2 redirects `JEV_MCP_HOME`, and tests still pass `path=` where they can.

---

- [ ] **Step 1: Write the failing credential tests**

```python
# tests/test_credentials.py
import os
import sys

import pytest

from jev_mcp.credentials import mask, remove_api_key, resolve_api_key, save_api_key, verify_api_key
from jev_mcp.errors import ApiUnreachableError, InvalidKeyError


def test_no_key_reports_none(isolated_home):
    key, source = resolve_api_key()
    assert key is None
    assert source == "none"


def test_file_key_is_found(isolated_home):
    save_api_key("file-key")
    key, source = resolve_api_key()
    assert key == "file-key"
    assert source == "file"


def test_env_overrides_file(isolated_home, monkeypatch):
    save_api_key("file-key")
    monkeypatch.setenv("TYPESAFE_API_KEY", "env-key")
    key, source = resolve_api_key()
    assert key == "env-key"
    assert source == "env"


def test_save_uses_the_given_path(tmp_path):
    target = tmp_path / "creds.yaml"
    save_api_key("abc", path=target)
    key, source = resolve_api_key(path=target)
    assert (key, source) == ("abc", "file")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file mode")
def test_file_is_owner_only(isolated_home):
    path = save_api_key("abc")
    assert oct(os.stat(path).st_mode)[-3:] == "600"


def test_remove_reports_whether_a_file_was_deleted(isolated_home):
    assert remove_api_key() is False
    save_api_key("abc")
    assert remove_api_key() is True
    assert resolve_api_key()[0] is None


def test_mask_shows_only_the_tail():
    assert mask("typesafe-key-a1b2") == "…a1b2"


def test_verify_rejects_an_empty_key():
    with pytest.raises(InvalidKeyError):
        verify_api_key("   ")


def test_verify_maps_authentication_failure(monkeypatch):
    import typesafe_sdk

    class FailingClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @property
        def models(self):
            raise typesafe_sdk.TypeSafeAuthenticationError(401, None, {}, None)

    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient", FailingClient)
    with pytest.raises(InvalidKeyError):
        verify_api_key("bad-key")


def test_verify_maps_connection_failure(monkeypatch):
    import typesafe_sdk

    class OfflineClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @property
        def models(self):
            raise typesafe_sdk.TypeSafeAPIConnectionError("offline")

    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient", OfflineClient)
    with pytest.raises(ApiUnreachableError):
        verify_api_key("some-key")
```

> If the SDK's exception constructors differ from the positional arguments above, construct them with whatever the installed version accepts — the assertion under test is the mapping, not the constructor shape. Check with `poetry run python -c "import typesafe_sdk, inspect; print(inspect.signature(typesafe_sdk.TypeSafeAuthenticationError.__init__))"`.

- [ ] **Step 2: Run and confirm failure**

Run: `poetry run pytest tests/test_credentials.py -v`

Expected: `ModuleNotFoundError: No module named 'jev_mcp.credentials'`.

- [ ] **Step 3: Implement `credentials.py`**

```python
# src/jev_mcp/credentials.py
from __future__ import annotations

import os
import stat
from pathlib import Path

import yaml

from jev_mcp.errors import ApiUnreachableError, InvalidKeyError
from jev_mcp.util.paths import credentials_path

ENV_VAR = "TYPESAFE_API_KEY"


def resolve_api_key(*, path: Path | None = None) -> tuple[str | None, str]:
    """Return (key, source) where source is 'env', 'file', or 'none'."""
    env_value = (os.getenv(ENV_VAR) or "").strip()
    if env_value:
        return env_value, "env"

    target = path or credentials_path()
    if target.exists():
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        stored = str(raw.get("api_key", "")).strip() if isinstance(raw, dict) else ""
        if stored:
            return stored, "file"
    return None, "none"


def save_api_key(api_key: str, *, path: Path | None = None) -> Path:
    target = path or credentials_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(target.name + ".tmp")
    staging.write_text(yaml.safe_dump({"api_key": api_key}), encoding="utf-8")
    os.replace(staging, target)
    if os.name == "posix":
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)
        os.chmod(target.parent, stat.S_IRWXU)
    return target


def remove_api_key(*, path: Path | None = None) -> bool:
    target = path or credentials_path()
    if target.exists():
        target.unlink()
        return True
    return False


def mask(api_key: str) -> str:
    tail = api_key[-4:] if len(api_key) >= 4 else "?"
    return f"…{tail}"


def verify_api_key(api_key: str) -> None:
    """Confirm the key works before it is written to disk."""
    import typesafe_sdk

    candidate = (api_key or "").strip()
    if not candidate:
        raise InvalidKeyError("API key is empty")

    try:
        with typesafe_sdk.TypeSafeClient(api_key=candidate) as client:
            client.models.list()
    except typesafe_sdk.TypeSafeAuthenticationError as exc:
        raise InvalidKeyError("TypeSafe rejected the API key (401)") from exc
    except typesafe_sdk.TypeSafeAPIConnectionError as exc:
        raise ApiUnreachableError("Cannot reach the TypeSafe API") from exc
    except typesafe_sdk.TypeSafeError as exc:
        raise InvalidKeyError(f"Key verification failed: {exc}") from exc
```

- [ ] **Step 4: Run the credential tests**

Run: `poetry run pytest tests/test_credentials.py -v`

Expected: all pass (the POSIX mode test is skipped on Windows).

- [ ] **Step 5: Write the failing CLI tests**

```python
# tests/test_cli_key.py
import pytest
from typer.testing import CliRunner

from jev_mcp.cli.main import app
from jev_mcp.credentials import resolve_api_key, save_api_key
from jev_mcp.errors import InvalidKeyError

runner = CliRunner()


def test_key_add_verifies_then_saves(isolated_home, monkeypatch):
    seen = {}
    monkeypatch.setattr("jev_mcp.cli.key.verify_api_key", lambda key: seen.setdefault("key", key))
    result = runner.invoke(app, ["key", "add", "  live-key  "])
    assert result.exit_code == 0
    assert seen["key"] == "live-key"
    assert resolve_api_key()[0] == "live-key"


def test_key_add_does_not_write_when_verification_fails(isolated_home, monkeypatch):
    def reject(_key):
        raise InvalidKeyError("nope")

    monkeypatch.setattr("jev_mcp.cli.key.verify_api_key", reject)
    result = runner.invoke(app, ["key", "add", "bad-key"])
    assert result.exit_code == 1
    assert "INVALID_KEY" in result.output
    assert resolve_api_key()[0] is None


def test_key_add_never_echoes_the_key(isolated_home, monkeypatch):
    monkeypatch.setattr("jev_mcp.cli.key.verify_api_key", lambda key: None)
    result = runner.invoke(app, ["key", "add", "super-secret-value"])
    assert "super-secret-value" not in result.output


def test_key_status_reports_source_and_hint(isolated_home):
    save_api_key("typesafe-key-a1b2")
    result = runner.invoke(app, ["key", "status"])
    assert result.exit_code == 0
    assert "file" in result.output
    assert "a1b2" in result.output
    assert "typesafe-key" not in result.output


def test_key_status_without_a_key(isolated_home):
    result = runner.invoke(app, ["key", "status"])
    assert "none" in result.output


def test_key_remove(isolated_home):
    save_api_key("abc")
    assert runner.invoke(app, ["key", "remove"]).exit_code == 0
    assert resolve_api_key()[0] is None
```

- [ ] **Step 6: Implement `cli/key.py`**

```python
# src/jev_mcp/cli/key.py
from __future__ import annotations

import os

import typer

from jev_mcp.credentials import mask, remove_api_key, resolve_api_key, save_api_key, verify_api_key
from jev_mcp.errors import JevMcpError
from jev_mcp.util.paths import credentials_path

key_app = typer.Typer(name="key", help="Manage the TypeSafe API key used by jev-mcp")


@key_app.command("add")
def key_add(api_key: str = typer.Argument(..., help="TypeSafe API key")) -> None:
    """Verify the key against TypeSafe, then store it locally."""
    candidate = api_key.strip()
    try:
        verify_api_key(candidate)
    except JevMcpError as exc:
        typer.echo(f"[{exc.code}] {exc.message}", err=True)
        raise typer.Exit(code=1) from exc

    path = save_api_key(candidate)
    typer.echo(f"Key saved to {path}", err=True)
    if os.name != "posix":
        typer.echo(
            "Note: on Windows the file is protected only by your user profile ACL. "
            "On a shared machine prefer the TYPESAFE_API_KEY environment variable.",
            err=True,
        )
    typer.echo("Run 'jev-mcp key status' to confirm.", err=True)


@key_app.command("status")
def key_status() -> None:
    """Show where the key comes from, without revealing it."""
    api_key, source = resolve_api_key()
    if api_key is None:
        typer.echo("key: none")
        typer.echo(f"looked in: TYPESAFE_API_KEY, {credentials_path()}")
        return
    typer.echo(f"key: {mask(api_key)}")
    typer.echo(f"source: {source}")


@key_app.command("remove")
def key_remove() -> None:
    """Delete the locally stored key."""
    if remove_api_key():
        typer.echo("Key removed.", err=True)
        return
    typer.echo("No stored key to remove.", err=True)
```

- [ ] **Step 7: Register the group in `cli/main.py`**

Add the import and the registration line next to the existing `serve` command:

```python
from jev_mcp.cli.key import key_app

app.command("serve")(serve_cmd)
app.add_typer(key_app)
```

- [ ] **Step 8: Run the CLI tests**

Run: `poetry run pytest tests/test_cli_key.py -v`

Expected: 6 passed.

- [ ] **Step 9: Lint and commit**

```bash
poetry run ruff check src tests
git add src/jev_mcp/credentials.py src/jev_mcp/cli tests/test_credentials.py tests/test_cli_key.py
git commit -m "feat: add credential storage and jev-mcp key commands"
```
