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
