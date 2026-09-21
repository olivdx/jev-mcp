# Task 5 — Async subprocess helper

**Deliverable:** `run_argv`, the single place where jev-mcp launches an external process: argv only, output capped, timeout handled without losing the partial output.

**Files:**
- Create: `src/jev_mcp/util/proc.py`
- Create: `tests/test_proc.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ProcResult`, `CommandNotFoundError`, `cap_output`, `run_argv`.

**Design notes:**
- Never `shell=True`. The caller always supplies an argument vector.
- A timeout kills the process and returns `timed_out=True` with whatever output arrived. It is a signal, not an exception, because `decide` uses it.
- `CommandNotFoundError` is a plain exception; collectors translate it into their own domain error (`GIT_NOT_FOUND`, `TEST_RUNNER_FAILED`).

---

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_proc.py
import sys

import pytest

from jev_mcp.util.proc import CommandNotFoundError, cap_output, run_argv

PYTHON = sys.executable


def test_cap_output_leaves_short_text_alone():
    text, truncated = cap_output("hello", 100)
    assert text == "hello"
    assert truncated is False


def test_cap_output_keeps_head_and_tail():
    text, truncated = cap_output("A" * 500 + "B" * 500, 200)
    assert truncated is True
    assert text.startswith("A")
    assert text.endswith("B")
    assert "omitted" in text
    assert len(text) < 1000


async def test_run_argv_captures_stdout_and_exit_code(tmp_path):
    result = await run_argv(
        [PYTHON, "-c", "print('hi')"],
        tmp_path,
        timeout_s=30,
        max_output_bytes=10_000,
    )
    assert result.exit_code == 0
    assert "hi" in result.stdout
    assert result.timed_out is False
    assert result.duration_s >= 0


async def test_run_argv_reports_non_zero_exit(tmp_path):
    result = await run_argv(
        [PYTHON, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"],
        tmp_path,
        timeout_s=30,
        max_output_bytes=10_000,
    )
    assert result.exit_code == 3
    assert "boom" in result.stderr


async def test_run_argv_times_out_without_raising(tmp_path):
    result = await run_argv(
        [PYTHON, "-c", "import time; time.sleep(30)"],
        tmp_path,
        timeout_s=0.5,
        max_output_bytes=10_000,
    )
    assert result.timed_out is True


async def test_run_argv_raises_for_a_missing_binary(tmp_path):
    with pytest.raises(CommandNotFoundError):
        await run_argv(
            ["definitely-not-a-real-binary-xyz"],
            tmp_path,
            timeout_s=5,
            max_output_bytes=1000,
        )


async def test_run_argv_marks_truncated_output(tmp_path):
    result = await run_argv(
        [PYTHON, "-c", "print('x' * 5000)"],
        tmp_path,
        timeout_s=30,
        max_output_bytes=500,
    )
    assert result.truncated is True
```

- [ ] **Step 2: Run and confirm failure**

Run: `poetry run pytest tests/test_proc.py -v`

Expected: `ModuleNotFoundError: No module named 'jev_mcp.util.proc'`.

- [ ] **Step 3: Implement `util/proc.py`**

```python
# src/jev_mcp/util/proc.py
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
    except FileNotFoundError as exc:
        raise CommandNotFoundError(cmd[0]) from exc
    except NotADirectoryError as exc:
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
```

- [ ] **Step 4: Run the tests**

Run: `poetry run pytest tests/test_proc.py -v`

Expected: 7 passed. On Windows the default event loop policy is already the proactor loop, which supports subprocesses.

- [ ] **Step 5: Commit**

```bash
git add src/jev_mcp/util/proc.py tests/test_proc.py
git commit -m "feat: add async argv subprocess helper with output caps"
```
