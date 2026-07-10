"""Characterization tests for the deployed Stata batch wrapper."""

import json
import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "run_stata_do.sh"


def _fake_stata(
    tmp_path: Path,
    *,
    directory: str = "fake Stata bin",
    name: str = "stata fake",
    label: str = "default",
) -> Path:
    bin_dir = tmp_path / directory
    bin_dir.mkdir()
    executable = bin_dir / name
    executable.write_text(
        """#!/usr/bin/env bash
set -u
if [ -n "${FAKE_SELECTED:-}" ]; then
  printf '%s\n' "__LABEL__" > "$FAKE_SELECTED"
fi
printf '%s\\n' "$PWD" > "$FAKE_CAPTURE"
printf '<%s>\\n' "$@" >> "$FAKE_CAPTURE"
if [ "${FAKE_WRITE_LOG:-1}" = 1 ]; then
  printf '%b' "${FAKE_LOG_CONTENT:-clean log\\n}" > "${4%.do}.log"
fi
exit "${FAKE_STATUS:-0}"
""".replace("__LABEL__", label),
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


def test_stale_log_cleanup_failure_stops_before_stata_runs(tmp_path):
    work_dir = tmp_path / "project"
    work_dir.mkdir()
    do_file = work_dir / "analysis.do"
    do_file.write_text("display 1\n", encoding="utf-8")
    log_file = do_file.with_suffix(".log")
    log_file.write_text("clean stale log\n", encoding="utf-8")

    fake_bin = tmp_path / "fake system bin"
    fake_bin.mkdir()
    fake_rm = fake_bin / "rm"
    fake_rm.write_text("#!/usr/bin/env bash\nexit 77\n", encoding="utf-8")
    fake_rm.chmod(0o755)

    capture = tmp_path / "argv.txt"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "STATA_BIN": str(_fake_stata(tmp_path)),
            "FAKE_CAPTURE": str(capture),
        }
    )

    result = subprocess.run(
        [str(SCRIPT), str(do_file)], capture_output=True, text=True, env=env
    )

    assert result.returncode == 1
    assert f"Cannot remove stale Stata log: {log_file}" in result.stderr
    assert log_file.read_text(encoding="utf-8") == "clean stale log\n"
    assert not capture.exists()


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


def test_wrapper_uses_config_before_path_through_resolver_and_two_hop_link(tmp_path):
    configured = _fake_stata(
        tmp_path,
        directory="configured Stata",
        name="stata configured",
        label="configured",
    )
    path_fallback = _fake_stata(
        tmp_path, directory="path fallback", name="stata", label="path"
    )
    home = tmp_path / "home"
    config_path = home / ".agents/config/stata.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps({"stata_bin": str(configured)}), encoding="utf-8"
    )
    config_path.chmod(0o600)

    agents_skill = tmp_path / "agents/skills/stata"
    agents_skill.parent.mkdir(parents=True)
    agents_skill.symlink_to(SCRIPT.parent.parent, target_is_directory=True)
    claude_skill = tmp_path / "claude/skills/stata"
    claude_skill.parent.mkdir(parents=True)
    claude_skill.symlink_to(agents_skill, target_is_directory=True)
    linked_script = claude_skill / "scripts/run_stata_do.sh"

    work_dir = tmp_path / "linked project"
    work_dir.mkdir()
    do_file = work_dir / "analysis.do"
    do_file.write_text("display 1\n", encoding="utf-8")
    capture = tmp_path / "argv.txt"
    selected = tmp_path / "selected.txt"
    env = os.environ.copy()
    env.pop("STATA_BIN", None)
    env.update(
        {
            "HOME": str(home),
            "PATH": f"{path_fallback.parent}{os.pathsep}{env['PATH']}",
            "FAKE_CAPTURE": str(capture),
            "FAKE_SELECTED": str(selected),
            "FAKE_LOG_CONTENT": "clean log\\n",
        }
    )

    result = subprocess.run(
        [str(linked_script), str(do_file)], capture_output=True, text=True, env=env
    )

    assert result.returncode == 0, result.stderr
    assert selected.read_text(encoding="utf-8").strip() == "configured"


def test_invalid_reached_config_fails_without_using_path_fallback(tmp_path):
    path_fallback = _fake_stata(
        tmp_path, directory="path fallback", name="stata", label="path"
    )
    home = tmp_path / "home"
    config_path = home / ".agents/config/stata.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("not json", encoding="utf-8")
    config_path.chmod(0o600)
    work_dir = tmp_path / "project"
    work_dir.mkdir()
    do_file = work_dir / "analysis.do"
    do_file.write_text("display 1\n", encoding="utf-8")
    selected = tmp_path / "selected.txt"
    env = os.environ.copy()
    env.pop("STATA_BIN", None)
    env.update(
        {
            "HOME": str(home),
            "PATH": f"{path_fallback.parent}{os.pathsep}{env['PATH']}",
            "FAKE_CAPTURE": str(tmp_path / "argv.txt"),
            "FAKE_SELECTED": str(selected),
        }
    )

    result = subprocess.run(
        [str(SCRIPT), str(do_file)], capture_output=True, text=True, env=env
    )

    assert result.returncode == 2
    assert "malformed-config:" in result.stderr
    assert not selected.exists()
