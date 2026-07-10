"""Characterization tests for the deployed Stata batch wrapper."""

import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "run_stata_do.sh"


def _fake_stata(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "fake Stata bin"
    bin_dir.mkdir()
    executable = bin_dir / "stata fake"
    executable.write_text(
        """#!/usr/bin/env bash
set -u
printf '%s\\n' "$PWD" > "$FAKE_CAPTURE"
printf '<%s>\\n' "$@" >> "$FAKE_CAPTURE"
if [ "${FAKE_WRITE_LOG:-1}" = 1 ]; then
  printf '%b' "${FAKE_LOG_CONTENT:-clean log\\n}" > "${4%.do}.log"
fi
exit "${FAKE_STATUS:-0}"
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _run(
    tmp_path: Path,
    *,
    do_name: str = "analysis.do",
    log_content: str = "clean log\\n",
    status: int = 0,
    write_log: bool = True,
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    work_dir = tmp_path / "project with spaces"
    work_dir.mkdir()
    do_file = work_dir / do_name
    do_file.write_text("display 1\n", encoding="utf-8")
    capture = tmp_path / "argv.txt"
    env = os.environ.copy()
    env.update(
        {
            "STATA_BIN": str(_fake_stata(tmp_path)),
            "FAKE_CAPTURE": str(capture),
            "FAKE_LOG_CONTENT": log_content,
            "FAKE_STATUS": str(status),
            "FAKE_WRITE_LOG": "1" if write_log else "0",
        }
    )
    result = subprocess.run(
        [str(SCRIPT), str(do_file)],
        capture_output=True,
        text=True,
        env=env,
    )
    return result, do_file, do_file.with_suffix(".log"), capture


def test_clean_fresh_log_and_zero_status_succeeds(tmp_path):
    result, _do_file, log_file, _capture = _run(tmp_path)

    assert result.returncode == 0
    assert log_file.read_text(encoding="utf-8") == "clean log\n"


def test_line_start_stata_error_fails_even_when_process_exits_zero(tmp_path):
    result, _do_file, _log_file, _capture = _run(
        tmp_path, log_content="command output\\nr(111);\\n"
    )

    assert result.returncode == 1
    assert "Stata reported an error" in result.stderr
    assert "r(111);" in result.stderr


def test_nonzero_process_status_with_clean_log_is_propagated(tmp_path):
    result, _do_file, _log_file, _capture = _run(tmp_path, status=7)

    assert result.returncode == 7
    assert "Stata exited with status 7" in result.stderr


def test_missing_fresh_log_fails(tmp_path):
    result, _do_file, log_file, _capture = _run(tmp_path, write_log=False)

    assert result.returncode == 1
    assert not log_file.exists()
    assert "did not produce a fresh log" in result.stderr


def test_stale_log_is_deleted_before_stata_runs(tmp_path):
    work_dir = tmp_path / "project with spaces"
    work_dir.mkdir()
    do_file = work_dir / "analysis.do"
    do_file.write_text("display 1\n", encoding="utf-8")
    log_file = do_file.with_suffix(".log")
    log_file.write_text("r(999); stale\n", encoding="utf-8")
    capture = tmp_path / "argv.txt"
    env = os.environ.copy()
    env.update(
        {
            "STATA_BIN": str(_fake_stata(tmp_path)),
            "FAKE_CAPTURE": str(capture),
            "FAKE_WRITE_LOG": "0",
        }
    )

    result = subprocess.run(
        [str(SCRIPT), str(do_file)], capture_output=True, text=True, env=env
    )

    assert result.returncode == 1
    assert not log_file.exists()
    assert "did not produce a fresh log" in result.stderr


def test_wrong_arity_returns_usage_error():
    result = subprocess.run([str(SCRIPT)], capture_output=True, text=True)

    assert result.returncode == 2
    assert "Usage:" in result.stderr


def test_nonexistent_do_file_returns_usage_error(tmp_path):
    missing = tmp_path / "missing.do"
    result = subprocess.run(
        [str(SCRIPT), str(missing)], capture_output=True, text=True
    )

    assert result.returncode == 2
    assert f"Do-file does not exist: {missing}" in result.stderr


def test_paths_with_spaces_are_quoted_and_run_from_do_file_directory(tmp_path):
    result, do_file, _log_file, capture = _run(
        tmp_path, do_name="analysis file.do"
    )

    assert result.returncode == 0
    assert capture.read_text(encoding="utf-8").splitlines() == [
        str(do_file.parent),
        "<-q>",
        "<-b>",
        "<do>",
        "<analysis file.do>",
    ]
