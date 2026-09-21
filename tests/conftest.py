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
