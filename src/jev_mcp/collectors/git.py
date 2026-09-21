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
    # -uall lists untracked files individually; the default collapses them to a directory name.
    porcelain = await _git(repo, "status", "--porcelain", "-uall")

    merge_base = None
    if base_ref:
        merge_base = (
            await _git(repo, "merge-base", base_ref, "HEAD", allow_failure=True)
        ).strip() or None

    diff_args = _diff_args(base_ref, staged_only)
    names = [line.strip() for line in (await _git(repo, *diff_args, "--name-only")).splitlines()]
    names = [name for name in names if name]
    diff_stat = await _git(repo, *diff_args, "--stat")

    untracked = [line[3:].strip() for line in porcelain.splitlines() if line.startswith("?? ")]

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
