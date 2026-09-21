# Task 6 — `collect_git` collector

**Deliverable:** A deterministic Git snapshot whose diff is budgeted **per file**, so Jev never sees a hunk that was cut in half.

**Files:**
- Create: `src/jev_mcp/collectors/__init__.py`, `src/jev_mcp/collectors/git.py`
- Modify: `tests/conftest.py` (add the `git_repo` fixture)
- Create: `tests/test_collect_git.py`

**Interfaces:**
- Consumes: `GitConfig` (task 3), `run_argv` / `CommandNotFoundError` (task 5), git errors (task 2).
- Produces: `async def collect_git(project_root, cfg, *, base_ref=None, staged_only=False, max_diff_bytes=None) -> dict`.

**Payload contract:**

```python
{
    "branch": str,
    "head_sha": str,
    "is_clean": bool,
    "changed_files": list[str],
    "untracked_files": list[str],
    "diff_stat": str,
    "diff": str,
    "truncated": bool,
    "omitted_files": list[dict],   # [{"path": str, "bytes": int}]
    "base_ref": str | None,
    "merge_base_with": str | None, # merge-base sha when base_ref was given
}
```

---

- [ ] **Step 1: Add the repo fixture to `tests/conftest.py`**

Append to the existing file from task 2:

```python
import subprocess


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
    (repo / "a.txt").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "init")
    (repo / "a.txt").write_text("goodbye\n", encoding="utf-8")
    return repo
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_collect_git.py
import pytest

from jev_mcp.collectors.git import collect_git
from jev_mcp.config import GitConfig
from jev_mcp.errors import NotARepoError

CFG = GitConfig()


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


async def test_large_file_is_omitted_whole(git_repo):
    (git_repo / "big.txt").write_text("x" * 5000 + "\n", encoding="utf-8")
    import subprocess

    subprocess.run(["git", "add", "big.txt"], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add big"], cwd=git_repo, check=True, capture_output=True
    )
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
    import subprocess

    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "more"], cwd=git_repo, check=True, capture_output=True)
    for name in ("b.txt", "c.txt"):
        (git_repo / name).write_text("changed\n" * 50, encoding="utf-8")

    result = await collect_git(git_repo, GitConfig(max_diff_bytes=200))
    assert result["truncated"] is True
    assert len(result["diff"].encode("utf-8")) <= 200


async def test_staged_only_sees_only_the_index(git_repo):
    (git_repo / "staged.txt").write_text("in index\n", encoding="utf-8")
    import subprocess

    subprocess.run(["git", "add", "staged.txt"], cwd=git_repo, check=True, capture_output=True)
    result = await collect_git(git_repo, CFG, staged_only=True)
    assert "staged.txt" in result["changed_files"]
    assert "a.txt" not in result["changed_files"]


async def test_base_ref_reports_a_merge_base(git_repo):
    result = await collect_git(git_repo, CFG, base_ref="main")
    assert result["base_ref"] == "main"
    assert result["merge_base_with"]


async def test_non_repo_directory_raises(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(NotARepoError) as exc:
        await collect_git(plain, CFG)
    assert exc.value.code == "NOT_A_REPO"
```

- [ ] **Step 3: Run and confirm failure**

Run: `poetry run pytest tests/test_collect_git.py -v`

Expected: `ModuleNotFoundError: No module named 'jev_mcp.collectors'`.

- [ ] **Step 4: Implement `collectors/git.py`**

```python
# src/jev_mcp/collectors/__init__.py
```

```python
# src/jev_mcp/collectors/git.py
from __future__ import annotations

from pathlib import Path

from jev_mcp.config import GitConfig
from jev_mcp.errors import GitFailedError, GitNotFoundError, NotARepoError
from jev_mcp.util.proc import CommandNotFoundError, run_argv

_GIT_TIMEOUT_S = 60.0
_GIT_OUTPUT_CAP = 8 * 1024 * 1024


async def _git(cwd: Path, *args: str, allow_failure: bool = False) -> str:
    try:
        result = await run_argv(
            ["git", *args],
            cwd,
            timeout_s=_GIT_TIMEOUT_S,
            max_output_bytes=_GIT_OUTPUT_CAP,
        )
    except CommandNotFoundError as exc:
        raise GitNotFoundError() from exc
    if result.exit_code != 0 and not allow_failure:
        raise GitFailedError(f"git {' '.join(args)}: {result.stderr.strip() or 'failed'}")
    return result.stdout


def _diff_args(base_ref: str | None, staged_only: bool) -> list[str]:
    if base_ref:
        return ["diff", f"{base_ref}...HEAD"]
    if staged_only:
        return ["diff", "--cached"]
    return ["diff", "HEAD"]


def _byte_len(text: str) -> int:
    return len(text.encode("utf-8", errors="replace"))


async def _collect_diff(
    repo: Path,
    diff_args: list[str],
    names: list[str],
    total_budget: int,
    per_file_budget: int,
) -> tuple[str, list[dict], bool]:
    """Collect whole-file diffs until the budget runs out; never cut inside a hunk."""
    chunks: list[str] = []
    omitted: list[dict] = []
    used = 0
    for name in names:
        piece = await _git(repo, *diff_args, "--", name)
        size = _byte_len(piece)
        if size > per_file_budget or used + size > total_budget:
            omitted.append({"path": name, "bytes": size})
            continue
        chunks.append(piece)
        used += size
    return "".join(chunks), omitted, bool(omitted)


async def collect_git(
    project_root: Path,
    cfg: GitConfig,
    *,
    base_ref: str | None = None,
    staged_only: bool = False,
    max_diff_bytes: int | None = None,
) -> dict:
    try:
        toplevel = (await _git(project_root, "rev-parse", "--show-toplevel")).strip()
    except GitFailedError as exc:
        raise NotARepoError(f"{project_root} is not inside a git work tree") from exc
    repo = Path(toplevel) if toplevel else project_root

    branch = (await _git(repo, "branch", "--show-current")).strip()
    head_sha = (await _git(repo, "rev-parse", "HEAD", allow_failure=True)).strip()
    porcelain = await _git(repo, "status", "--porcelain")

    merge_base = None
    if base_ref:
        merge_base = (
            await _git(repo, "merge-base", base_ref, "HEAD", allow_failure=True)
        ).strip() or None

    diff_args = _diff_args(base_ref, staged_only)
    names = [line.strip() for line in (await _git(repo, *diff_args, "--name-only")).splitlines()]
    names = [name for name in names if name]
    diff_stat = await _git(repo, *diff_args, "--stat")

    untracked = [
        line[3:].strip()
        for line in porcelain.splitlines()
        if line.startswith("?? ")
    ]

    diff, omitted, truncated = await _collect_diff(
        repo,
        diff_args,
        names,
        max_diff_bytes or cfg.max_diff_bytes,
        cfg.max_file_diff_bytes,
    )

    return {
        "branch": branch,
        "head_sha": head_sha,
        "is_clean": not porcelain.strip(),
        "changed_files": names[: cfg.max_stat_files],
        "untracked_files": untracked[: cfg.max_stat_files],
        "diff_stat": diff_stat,
        "diff": diff,
        "truncated": truncated or len(names) > cfg.max_stat_files,
        "omitted_files": omitted,
        "base_ref": base_ref,
        "merge_base_with": merge_base,
    }
```

- [ ] **Step 5: Run the tests**

Run: `poetry run pytest tests/test_collect_git.py -v`

Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add src/jev_mcp/collectors tests/conftest.py tests/test_collect_git.py
git commit -m "feat: add git collector with per-file diff budgeting"
```
