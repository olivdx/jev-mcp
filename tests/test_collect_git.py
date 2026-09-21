import subprocess

import pytest

from jev_mcp.collectors.git import collect_git
from jev_mcp.config import GitConfig
from jev_mcp.errors import NotARepoError

CFG = GitConfig()


def _commit_all(repo, message):
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True)


async def test_dirty_repo_reports_a_diff(git_repo):
    result = await collect_git(git_repo, CFG)
    assert result["is_clean"] is False
    assert result["branch"] == "main"
    assert result["head_sha"]
    assert "a.txt" in result["changed_files"]
    assert "goodbye" in result["diff"]
    assert result["truncated"] is False
    assert result["omitted_files"] == []


async def test_clean_repo_reports_clean(git_repo):
    (git_repo / "a.txt").write_text("hello\n", encoding="utf-8")
    result = await collect_git(git_repo, CFG)
    assert result["is_clean"] is True
    assert result["diff"] == ""


async def test_untracked_files_are_listed(git_repo):
    (git_repo / "new.txt").write_text("fresh\n", encoding="utf-8")
    result = await collect_git(git_repo, CFG)
    assert "new.txt" in result["untracked_files"]


async def test_untracked_files_are_listed_individually_not_as_a_directory(git_repo):
    package = git_repo / "pkg"
    package.mkdir()
    (package / "one.py").write_text("x = 1\n", encoding="utf-8")
    (package / "two.py").write_text("y = 2\n", encoding="utf-8")
    result = await collect_git(git_repo, CFG)
    assert "pkg/one.py" in result["untracked_files"]
    assert "pkg/two.py" in result["untracked_files"]
    assert "pkg/" not in result["untracked_files"]


async def test_large_file_is_omitted_whole(git_repo):
    (git_repo / "big.txt").write_text("x" * 5000 + "\n", encoding="utf-8")
    _commit_all(git_repo, "add big")
    (git_repo / "big.txt").write_text("y" * 5000 + "\n", encoding="utf-8")

    result = await collect_git(git_repo, GitConfig(max_file_diff_bytes=100))
    omitted = {entry["path"] for entry in result["omitted_files"]}
    assert "big.txt" in omitted
    assert result["truncated"] is True
    # The surviving diff still contains complete hunks only.
    assert "y" * 200 not in result["diff"]


async def test_total_budget_stops_collecting(git_repo):
    for name in ("b.txt", "c.txt"):
        (git_repo / name).write_text("data\n" * 50, encoding="utf-8")
    _commit_all(git_repo, "more")
    for name in ("b.txt", "c.txt"):
        (git_repo / name).write_text("changed\n" * 50, encoding="utf-8")

    result = await collect_git(git_repo, GitConfig(max_diff_bytes=200))
    assert result["truncated"] is True
    assert len(result["diff"].encode("utf-8")) <= 200


async def test_staged_only_sees_only_the_index(git_repo):
    (git_repo / "staged.txt").write_text("in index\n", encoding="utf-8")
    subprocess.run(["git", "add", "staged.txt"], cwd=git_repo, check=True, capture_output=True)
    result = await collect_git(git_repo, CFG, staged_only=True)
    assert "staged.txt" in result["changed_files"]
    assert "a.txt" not in result["changed_files"]


async def test_base_ref_reports_a_merge_base(git_repo):
    result = await collect_git(git_repo, CFG, base_ref="main")
    assert result["base_ref"] == "main"
    assert result["merge_base_with"]


async def test_max_diff_bytes_argument_overrides_config(git_repo):
    result = await collect_git(git_repo, CFG, max_diff_bytes=10)
    assert result["truncated"] is True
    assert result["diff"] == ""


async def test_changed_files_are_capped(git_repo):
    for index in range(5):
        (git_repo / f"f{index}.txt").write_text("v1\n", encoding="utf-8")
    _commit_all(git_repo, "many files")
    for index in range(5):
        (git_repo / f"f{index}.txt").write_text("v2\n", encoding="utf-8")

    result = await collect_git(git_repo, GitConfig(max_stat_files=2))
    assert len(result["changed_files"]) == 2
    assert result["truncated"] is True


async def test_non_repo_directory_raises(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(NotARepoError) as exc:
        await collect_git(plain, CFG)
    assert exc.value.code == "NOT_A_REPO"
