"""Behavior pins and encoded review defects for ``paper_workspace.py``.

Pins (must pass now) capture the current *correct* behavior so later units
cannot regress it. ``xfail`` tests encode the 2026-07-10 review's verified
failing inputs; each flips to passing when its fix lands (R1 in U3, robustness
in U4). All filesystem I/O stays under ``tmp_path``.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import paper_workspace as pw

SCRIPT = Path(pw.__file__)


# --------------------------------------------------------------------------- #
# Pins: current correct behavior
# --------------------------------------------------------------------------- #

def test_split_paper_happy_path_combines_intro_and_isolates_appendix():
    text = (
        "Abstract text here.\n\n"
        "# 1. Introduction\nIntro body.\n\n"
        "# 2. Data\nData body.\n\n"
        "# 3. Results\nResults body.\n\n"
        "# 7. References\nRef one.\n"
    )
    intro, sections, appendix = pw.split_paper(text)

    assert "Abstract text here." in intro
    assert "Intro body." in intro
    assert len(sections) == 2  # data, results
    names = [fn for fn, _ in sections]
    assert names[0].startswith("01_") and "data" in names[0]
    assert names[1].startswith("02_") and "results" in names[1]
    assert "Ref one." in appendix
    # main-text content must not leak into the appendix
    assert "Results body." not in appendix


def test_references_heading_starts_appendix():
    """Regression guard: a genuine References heading still opens the appendix.

    This must hold both before and after the R1 fix.
    """
    text = "# 1. Intro\nBody.\n\n# 2. Data\nData.\n\n# 6. References\nCitations.\n"
    _intro, _sections, appendix = pw.split_paper(text)
    assert "Citations." in appendix


def test_write_text_writes_into_workspace(tmp_path):
    paper_dir = tmp_path / "papers"
    workspace = paper_dir / "mypaper"
    workspace.mkdir(parents=True)
    staged = tmp_path / "staged.md"
    staged.write_text("hello notes", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable, str(SCRIPT), "write-text",
            "--workspace", str(workspace),
            "--paper-dir", str(paper_dir),
            "--relative-path", "notes.md",
            "--input-file", str(staged),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (workspace / "notes.md").read_text(encoding="utf-8") == "hello notes"


# --------------------------------------------------------------------------- #
# R1: appendix/references detection must anchor whole words at heading start
# --------------------------------------------------------------------------- #

def test_estimating_preferences_is_not_appendix():
    # A heading title whose word merely contains 'references' as a substring.
    assert pw.is_appendix_heading("2. Estimating Preferences") is False


def test_results_and_appendix_tables_is_not_appendix():
    assert pw.is_appendix_heading("3. Results and Appendix Tables") is False


def test_preferences_section_not_truncated_into_appendix():
    text = (
        "# 1. Introduction\nIntro.\n\n"
        "# 2. Estimating Preferences\nEstimation content that must survive.\n\n"
        "# 3. Results\nResults body must survive.\n\n"
        "# 7. References\nRef one.\n"
    )
    intro, sections, appendix = pw.split_paper(text)
    assert "Results body must survive." not in appendix
    assert len(sections) >= 2
    joined = "\n".join(body for _, body in sections)
    assert "Estimation content that must survive." in joined
    assert "Results body must survive." in joined


def test_results_and_appendix_tables_section_not_truncated():
    text = (
        "# 1. Intro\nIntro.\n\n"
        "# 2. Data\nData body.\n\n"
        "# 3. Results and Appendix Tables\nResults body must survive.\n\n"
        "# 8. References\nRefs.\n"
    )
    _intro, sections, appendix = pw.split_paper(text)
    assert "Results body must survive." not in appendix
    joined = "\n".join(body for _, body in sections)
    assert "Results body must survive." in joined
