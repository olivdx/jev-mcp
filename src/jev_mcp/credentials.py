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
