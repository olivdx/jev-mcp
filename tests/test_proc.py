import os
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


async def test_run_argv_runs_in_the_given_directory(tmp_path):
    result = await run_argv(
        [PYTHON, "-c", "import os; print(os.getcwd())"],
        tmp_path,
        timeout_s=30,
        max_output_bytes=10_000,
    )
    assert str(tmp_path.resolve()) in result.stdout


async def test_run_argv_passes_the_given_environment(tmp_path):
    result = await run_argv(
        [PYTHON, "-c", "import os; print(os.getenv('JEV_PROBE'))"],
        tmp_path,
        timeout_s=30,
        max_output_bytes=10_000,
        env={**os.environ, "JEV_PROBE": "marker"},
    )
    assert "marker" in result.stdout
