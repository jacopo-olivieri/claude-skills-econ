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

NOTES_TEMPLATE = "## 1. Research Question and Motivation\n\n## 5. Synthesis of findings\nLine 1.\nLine 2.\n"


def _make_workspace(tmp_path, paper_text, *, stem="mypaper", marker_subdir="marker_output/nested"):
    """Create a papers dir with a pre-Marker workspace, plus the PDF + template."""
    paper_dir = tmp_path / "papers"
    workspace = paper_dir / stem
    marker_dir = workspace / marker_subdir
    marker_dir.mkdir(parents=True)
    (marker_dir / f"{stem}.md").write_text(paper_text, encoding="utf-8")
    pdf = tmp_path / f"{stem}.pdf"
    pdf.write_text("%PDF-1.4 dummy", encoding="utf-8")
    template = tmp_path / "notes_template.md"
    template.write_text(NOTES_TEMPLATE, encoding="utf-8")
    return paper_dir, workspace, pdf, template


def _run_init(pdf, paper_dir, template, *, force=False):
    cmd = [
        sys.executable, str(SCRIPT), "init",
        "--pdf", str(pdf), "--paper-dir", str(paper_dir),
        "--notes-template", str(template),
    ]
    if force:
        cmd.append("--force")
    return subprocess.run(cmd, capture_output=True, text=True)


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


# --------------------------------------------------------------------------- #
# U4: robustness (R5 init guard/progress, R6 headings/warnings, R8 atomic/JSON)
# --------------------------------------------------------------------------- #

def test_split_accepts_no_dot_and_roman_headings():
    # R6: '# 2 Data' (no dot) and Roman '# IV. Results' must be recovered.
    text = (
        "# 1 Introduction\nIntro.\n\n"
        "# 2 Data\nData body.\n\n"
        "# 3 Methods\nMethods body.\n\n"
        "# 6. References\nRefs.\n"
    )
    _intro, sections, _appendix = pw.split_paper(text)
    joined = "\n".join(body for _, body in sections)
    assert "Data body." in joined and "Methods body." in joined
    assert pw.heading_number("IV. Results") == 4
    assert pw.heading_number("II) Data") == 2
    assert pw.heading_number("Mix Models") is None  # not a Roman section heading


def test_init_recovers_sections_and_reports_word_count(tmp_path):
    paper_text = (
        "Abstract.\n\n# 1. Introduction\nIntro.\n\n# 2. Data\nData.\n\n"
        "# 3. Results\nResults.\n\n# 7. References\nRefs.\n"
    )
    paper_dir, workspace, pdf, template = _make_workspace(tmp_path, paper_text)
    proc = _run_init(pdf, paper_dir, template)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "ok"
    assert payload["word_count"] > 0
    assert not payload["warnings"]
    assert (workspace / "sections" / "01_data.md").exists()
    assert (workspace / "notes.md").read_text(encoding="utf-8").strip() == NOTES_TEMPLATE.strip()


def test_init_finds_marker_output_in_nonstandard_nested_dir(tmp_path):
    paper_text = "# 1. Intro\nIntro.\n\n# 2. Data\nData.\n"
    paper_dir, workspace, pdf, template = _make_workspace(
        tmp_path, paper_text, marker_subdir="marker_output/weird/deep/place"
    )
    proc = _run_init(pdf, paper_dir, template)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert "weird/deep/place" in payload["marker_markdown"]


def test_init_warns_on_degenerate_split(tmp_path):
    # Only a single main-text section beyond the intro -> warning surfaced.
    paper_text = "Some abstract text with no clear headings at all.\n"
    paper_dir, _workspace, pdf, template = _make_workspace(tmp_path, paper_text)
    proc = _run_init(pdf, paper_dir, template)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["warnings"], "degenerate split must surface a warning"


def test_init_refuses_to_clobber_diverged_notes_without_force(tmp_path):
    paper_text = "# 1. Intro\nIntro.\n\n# 2. Data\nData.\n"
    paper_dir, workspace, pdf, template = _make_workspace(tmp_path, paper_text)
    # First init succeeds and creates a pristine notes.md.
    assert _run_init(pdf, paper_dir, template).returncode == 0
    # User adds work.
    (workspace / "notes.md").write_text("## 1. Research Question\n- My hard-won note [p. 3]\n", encoding="utf-8")

    proc = _run_init(pdf, paper_dir, template)  # no --force
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["status"] == "error"
    assert "diverged" in payload["message"]
    # The user's notes survived.
    assert "hard-won note" in (workspace / "notes.md").read_text(encoding="utf-8")

    # --force proceeds and resets notes.md to the template.
    proc2 = _run_init(pdf, paper_dir, template, force=True)
    assert proc2.returncode == 0
    assert (workspace / "notes.md").read_text(encoding="utf-8").strip() == NOTES_TEMPLATE.strip()


def test_missing_config_reports_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(pw, "CONFIG_PATH", tmp_path / "no-such-config.json")
    with pytest.raises(pw.WorkspaceError) as exc:
        pw.resolve_papers_dir(None)
    assert "no-such-config.json" in str(exc.value)


def test_write_text_empty_relative_path_returns_json_error(tmp_path):
    paper_dir = tmp_path / "papers"
    workspace = paper_dir / "mypaper"
    workspace.mkdir(parents=True)
    staged = tmp_path / "staged.md"
    staged.write_text("x", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "write-text",
         "--workspace", str(workspace), "--paper-dir", str(paper_dir),
         "--relative-path", "", "--input-file", str(staged)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["status"] == "error"


def test_write_text_mark_processed_appends_resume_marker(tmp_path):
    paper_dir = tmp_path / "papers"
    workspace = paper_dir / "mypaper"
    workspace.mkdir(parents=True)
    staged = tmp_path / "staged.md"
    staged.write_text("notes body", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "write-text",
         "--workspace", str(workspace), "--paper-dir", str(paper_dir),
         "--relative-path", "notes.md", "--input-file", str(staged),
         "--mark-processed", "03_results.md"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    written = (workspace / "notes.md").read_text(encoding="utf-8")
    assert pw.PROCESSED_MARKER_PREFIX + "03_results.md" in written


def test_atomic_write_leaves_original_intact_on_failure(tmp_path, monkeypatch):
    target = tmp_path / "notes.md"
    target.write_text("original content", encoding="utf-8")

    def boom(src, dst):
        raise OSError("simulated crash during replace")

    monkeypatch.setattr(pw.os, "replace", boom)
    with pytest.raises(OSError):
        pw._atomic_write(target, "new content that must not land")

    assert target.read_text(encoding="utf-8") == "original content"
    # No temp files left behind in the directory.
    assert not list(tmp_path.glob(".tmp-*"))
