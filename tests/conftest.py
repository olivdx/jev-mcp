from __future__ import annotations

import subprocess
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


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A repo with one commit and one uncommitted edit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    # Keep the fixture hermetic on machines that sign commits globally.
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "a.txt").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "init")
    (repo / "a.txt").write_text("goodbye\n", encoding="utf-8")
    return repo
