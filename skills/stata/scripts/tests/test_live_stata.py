"""Opt-in, non-destructive smoke tests for this Mac's Stata installation."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


if os.environ.get("STATA_LIVE_TESTS") != "1":
    pytest.skip(
        "set STATA_LIVE_TESTS=1 to run real Stata and manual smoke tests",
        allow_module_level=True,
    )


from stata_config import (  # noqa: E402 - imported only after the opt-in gate
    StataConfigError,
    resolve_ado_base_dir,
    resolve_docs_dir,
    resolve_stata_bin,
)


SCRIPTS_DIR = Path(__file__).resolve().parent.parent
WRAPPER = SCRIPTS_DIR / "run_stata_do.sh"
SEARCH = SCRIPTS_DIR / "search_stata_docs.py"


@pytest.fixture(scope="module")
def live_resources() -> dict[str, Path]:
    try:
        resources = {
            "binary": resolve_stata_bin(),
            "docs": resolve_docs_dir(),
            "ado": resolve_ado_base_dir(),
        }
    except StataConfigError as exc:
        pytest.fail(f"live Stata setup error [{exc.code}]: {exc}")

    binary = resources["binary"]
    if not binary.is_file() or not os.access(binary, os.X_OK):
        pytest.fail(f"live Stata setup error: binary is not executable: {binary}")
    for label in ("docs", "ado"):
        if not resources[label].is_dir():
            pytest.fail(
                f"live Stata setup error: resolved {label} directory is missing: "
                f"{resources[label]}"
            )
    return resources


def isolated_live_env(tmp_path: Path, resources: dict[str, Path]) -> dict[str, str]:
    home = tmp_path / "isolated-home"
    home.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "STATA_BIN": str(resources["binary"]),
            "STATA_DOCS_DIR": str(resources["docs"]),
            "STATA_ADO_BASE_DIR": str(resources["ado"]),
        }
    )
    return env


def test_live_wrapper_runs_harmless_do_file(
    tmp_path: Path, live_resources: dict[str, Path]
) -> None:
    do_file = tmp_path / "live_success.do"
    do_file.write_text(
        'clear all\nversion 18\nnoisily display "CODEX_STATA_LIVE_OK"\nexit 0\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        [str(WRAPPER), str(do_file)],
        capture_output=True,
        text=True,
        env=isolated_live_env(tmp_path, live_resources),
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    log = do_file.with_suffix(".log")
    assert log.is_file()
    assert "CODEX_STATA_LIVE_OK" in log.read_text(encoding="utf-8")


def test_live_wrapper_surfaces_r111_despite_raw_success(
    tmp_path: Path, live_resources: dict[str, Path]
) -> None:
    source = (
        "clear all\n"
        "set obs 1\n"
        "capture noisily summarize __codex_live_missing_variable__\n"
        "local captured_rc = _rc\n"
        'noisily display as error "r(`captured_rc\');"\n'
        "exit 0\n"
    )
    raw_do = tmp_path / "raw_failure.do"
    raw_do.write_text(source, encoding="utf-8")
    env = isolated_live_env(tmp_path, live_resources)

    raw = subprocess.run(
        [str(live_resources["binary"]), "-q", "-b", "do", raw_do.name],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )

    raw_log = raw_do.with_suffix(".log")
    assert raw.returncode == 0, raw.stderr
    assert raw_log.is_file()
    assert "r(111);" in raw_log.read_text(encoding="utf-8")

    wrapped_do = tmp_path / "wrapped_failure.do"
    wrapped_do.write_text(source, encoding="utf-8")
    wrapped = subprocess.run(
        [str(WRAPPER), str(wrapped_do)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )

    assert wrapped.returncode == 1
    assert "Stata reported an error" in wrapped.stderr
    assert "r(111);" in wrapped.stderr


def test_live_installed_help_file_is_readable(live_resources: dict[str, Path]) -> None:
    help_file = live_resources["ado"] / "r" / "regress.sthlp"
    if not help_file.is_file():
        pytest.fail(f"live Stata setup error: expected help file is missing: {help_file}")

    text = help_file.read_text(encoding="utf-8", errors="replace")

    assert len(text) > 100
    assert "regress" in text.lower()


def test_live_named_manual_search_yields_readable_output(
    tmp_path: Path, live_resources: dict[str, Path]
) -> None:
    manual = live_resources["docs"] / "u.pdf"
    if not manual.is_file():
        pytest.fail(f"live Stata setup error: expected named manual is missing: {manual}")

    result = subprocess.run(
        [
            sys.executable,
            str(SEARCH),
            "Stata",
            "--pdf",
            manual.name,
            "--pages",
            "1-10",
            "--context",
            "0",
            "--max-results",
            "1",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=isolated_live_env(tmp_path, live_resources),
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert f"{manual.name}:" in result.stdout
    assert "No results found" not in result.stdout
