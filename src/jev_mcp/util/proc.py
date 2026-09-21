from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_s: float
    truncated: bool


class CommandNotFoundError(Exception):
    """The executable is missing; callers translate this into a domain error."""


def cap_output(text: str, max_bytes: int) -> tuple[str, bool]:
    """Keep the head and the tail of long output; the middle is where noise lives."""
    data = text.encode("utf-8", errors="replace")
    if len(data) <= max_bytes:
        return text, False
    half = max_bytes // 2
    head = data[:half].decode("utf-8", errors="ignore")
    tail = data[-half:].decode("utf-8", errors="ignore")
    omitted = len(data) - (2 * half)
    return f"{head}\n... [{omitted} bytes omitted] ...\n{tail}", True


async def run_argv(
    cmd: list[str],
    cwd: Path,
    *,
    timeout_s: float,
    max_output_bytes: int,
    env: dict[str, str] | None = None,
) -> ProcResult:
    started = time.monotonic()
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise CommandNotFoundError(cmd[0]) from exc

    timed_out = False
    try:
        raw_stdout, raw_stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        timed_out = True
        process.kill()
        raw_stdout, raw_stderr = await process.communicate()

    stdout, stdout_truncated = cap_output(
        raw_stdout.decode("utf-8", errors="replace"), max_output_bytes
    )
    stderr, stderr_truncated = cap_output(
        raw_stderr.decode("utf-8", errors="replace"), max_output_bytes
    )

    return ProcResult(
        exit_code=process.returncode if process.returncode is not None else -1,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        duration_s=round(time.monotonic() - started, 3),
        truncated=stdout_truncated or stderr_truncated,
    )
