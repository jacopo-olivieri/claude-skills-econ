"""Behavior pins and encoded review defects for ``save_paper_summary.py``.

Pins capture current correct behavior. ``xfail`` tests encode the 2026-07-10
review's verified failing inputs: R2/R3 flip in U3, the R8 save-half items flip
in U5. All filesystem I/O stays under ``tmp_path``.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import save_paper_summary as sps
from conftest import TEMPLATE_FIXTURE

SCRIPT = Path(sps.__file__)


def _run_script(tmp_path, *, summary, metadata, output_dir, on_exists="skip", write=False,
                citation_key="cite", template=TEMPLATE_FIXTURE):
    summary_file = tmp_path / "summary.txt"
    summary_file.write_text(summary, encoding="utf-8")
    metadata_file = tmp_path / "metadata.json"
    metadata_file.write_text(json.dumps(metadata), encoding="utf-8")
    cmd = [
        sys.executable, str(SCRIPT),
        "--item-key", "ITEMKEY",
        "--citation-key", citation_key,
        "--summary-file", str(summary_file),
        "--metadata-file", str(metadata_file),
        "--template-path", str(template),
        "--output-dir", str(output_dir),
        "--on-exists", on_exists,
    ]
    if write:
        cmd.append("--write")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc


def _frontmatter(note_text):
    parts = note_text.split("---")
    # note starts with '---\n<frontmatter>\n---'
    return parts[1]


# --------------------------------------------------------------------------- #
# Pins: current correct behavior
# --------------------------------------------------------------------------- #

def test_split_summary_happy_path_assigns_sections():
    summary = (
        "1. Research Question\nRQ body.\n"
        "2. Data and Methods\nData body.\n"
        "3. Results\nResults body.\n"
        "4. Limitations\nLimits body.\n"
        "5. Synthesis of findings\nLine one.\nLine two.\n"
    )
    d = sps._split_summary_sections(summary)
    assert "RQ body." in d["s1"]
    assert "Data body." in d["s2"]
    assert "Results body." in d["s3"]
    assert "Limits body." in d["s4"]


def test_render_note_has_all_primary_and_additional_headers():
    meta = {"title": "A Title", "authors": ["Jane Doe"]}
    note = sps.render_note("K", "cite", "1. RQ\nbody\n", meta)
    for header in sps.PRIMARY_HEADERS.values():
        assert header in note
    for header in sps.ADDITIONAL_HEADERS:
        assert header in note


def test_render_note_project_and_links_default_empty():
    meta = {"title": "A Title", "authors": ["Jane Doe"]}
    note = sps.render_note("K", "cite", "1. RQ\nbody\n", meta)
    lines = note.splitlines()
    assert "project:" in lines           # bare key, empty value
    assert "links:" in lines             # bare key, empty value


def test_synthesis_first_line_marker_moves_to_key_takeaways():
    summary = "5. Comments\nSynthesis of findings\nOne.\nTwo.\n"
    note = sps.render_note("K", "cite", summary, {"title": "T", "authors": ["A"]})
    key_block = note.split("%% end notes %%")[0]
    assert "One." in key_block and "Two." in key_block


def test_dry_run_against_existing_dir_reports_dry_run(tmp_path):
    out = tmp_path / "vault"
    out.mkdir()
    proc = _run_script(
        tmp_path, summary="1. RQ\nbody\n", metadata={"title": "T", "authors": ["A"]},
        output_dir=out, on_exists="overwrite", write=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "dry_run"


# --------------------------------------------------------------------------- #
# R2 (U3): section-marker parsing must not eat body text or subheadings
# --------------------------------------------------------------------------- #

def test_out_of_order_numbered_list_stays_body():
    # '1.' and '2.' appear inside the Results section as an enumerated list.
    summary = "3. Results\nKey effects:\n1. Effect is large\n2. Effect persists\n"
    d = sps._split_summary_sections(summary)
    assert not d["s1"], f"s1 should be empty, got {d['s1']!r}"
    assert not d["s2"], f"s2 should be empty, got {d['s2']!r}"
    assert "Effect is large" in d["s3"]
    assert "Effect persists" in d["s3"]


def test_subsection_numbers_survive_as_content():
    summary = (
        "2. Data and Methods\n"
        "### 2.1 Data (source, type, time span)\nDataset details.\n"
        "4. Limitations\n"
        "#### 4.1 Limitations\nLimit details.\n"
    )
    d = sps._split_summary_sections(summary)
    assert "2.1 Data" in d["s2"]
    assert "Dataset details." in d["s2"]
    assert "4.1 Limitations" in d["s4"]
    assert "Limit details." in d["s4"]


def test_enumeration_starting_with_section_word_stays_body():
    # Regression guard (R2): a numbered list whose items begin with a section
    # word must not be promoted to markers and lose its text.
    summary = (
        "3. Results\n"
        "We highlight several points:\n"
        "4. Extensions to neighboring markets replicate the effect (see Table 5).\n"
        "5. Discussion of mechanisms suggests search frictions.\n"
    )
    d, meta = sps.analyze_summary_sections(summary)
    assert meta["sections_found"] == 1
    assert "Extensions to neighboring markets replicate the effect" in d["s3"]
    assert "Discussion of mechanisms suggests search frictions" in d["s3"]
    assert not d["s4"]
    assert not d["s5"]


def test_bold_markers_detectable_or_warned():
    # analyze_summary_sections is introduced in U3; it returns (sections, meta)
    # with meta['sections_found'] and meta['warnings'].
    summary = "**1. Research Question and Motivation**\nWhy this matters.\n"
    _sections, meta = sps.analyze_summary_sections(summary)
    assert meta["sections_found"] >= 1 or meta["warnings"], (
        "a degenerate parse (0 sections) must surface a warning"
    )


# --------------------------------------------------------------------------- #
# R3 (U3): every emitted frontmatter scalar must be quoted
# --------------------------------------------------------------------------- #

def test_frontmatter_scalars_with_colons_are_quoted():
    meta = {
        "title": "A Title",
        "authors": ["O'Brien, Conan: Jr"],
        "journal": "Science: Advances",
        "date_published": "2020-01-01",
    }
    note = sps.render_note("K", "cite", "1. RQ\nbody\n", meta)
    fm = _frontmatter(note)
    fm_lines = fm.splitlines()
    journal_line = next(ln for ln in fm_lines if ln.startswith("journal:"))
    # The author entry is the first list item after the `author:` key — distinct
    # from the (already-quoted) `aliases:` entry that also contains "O'Brien".
    author_idx = fm_lines.index("author:")
    author_line = fm_lines[author_idx + 1]
    assert "O'Brien" in author_line, f"unexpected author line: {author_line!r}"
    assert '"' in journal_line, f"journal not quoted: {journal_line!r}"
    assert '"' in author_line, f"author not quoted: {author_line!r}"


def test_frontmatter_parses_as_yaml():
    yaml = pytest.importorskip("yaml")
    meta = {
        "title": "A Title",
        "authors": ["O'Brien, Conan: Jr"],
        "journal": "Science: Advances",
        "date_published": "2020-01-01",
        "url": "https://example.com/a:b",
    }
    note = sps.render_note("K", "cite", "1. RQ\nbody\n", meta)
    fm = _frontmatter(note)
    yaml.safe_load(fm)  # must not raise


# --------------------------------------------------------------------------- #
# R4 (U3): emit the vault-dominant 'date-published' (hyphen)
# --------------------------------------------------------------------------- #

def test_emits_date_published_hyphen():
    meta = {"title": "T", "authors": ["A"], "date_published": "2020-07-31"}
    note = sps.render_note("K", "cite", "1. RQ\nbody\n", meta)
    fm = _frontmatter(note)
    assert any(ln.startswith("date-published:") for ln in fm.splitlines())
    assert not any(ln.startswith("date_published:") for ln in fm.splitlines())


# --------------------------------------------------------------------------- #
# R8 (U5): save-script robustness items
# --------------------------------------------------------------------------- #

@pytest.mark.xfail(reason="R8 (U5): year only extracted from string start", strict=True)
def test_year_extracted_from_anywhere():
    assert sps._extract_year("July 2020") == "2020"


@pytest.mark.xfail(reason="R8 (U5): bold-labelled bullet promoted to a header", strict=True)
def test_bold_labelled_bullet_stays_bullet():
    out = sps._normalize_section_markdown("- **Main estimate**: beta = 0.31 (se 0.05)")
    assert not out.lstrip().startswith("####"), f"should stay a bullet: {out!r}"


@pytest.mark.xfail(reason="R8 (U5): mid-prose synthesis relocated", strict=True)
def test_synthesis_only_triggers_on_first_line():
    text = "Some prose mentioning the synthesis of findings in Smith (2020) here."
    _summary, moved = sps._extract_synthesis_summary(text)
    assert moved is False


@pytest.mark.xfail(reason="R8 (U5): file:// link has four slashes", strict=True)
def test_pdf_link_is_well_formed():
    meta = {"title": "T", "authors": ["A"],
            "attachments": [{"path": "/Users/x/paper.pdf", "is_pdf": True}]}
    note = sps.render_note("K", "cite", "1. RQ", meta)
    link_line = next(ln for ln in note.splitlines() if "file:" in ln)
    assert "file:////" not in link_line, f"malformed link: {link_line!r}"
    assert "file:///Users/x/paper.pdf" in link_line


@pytest.mark.xfail(reason="R8 (U5): special chars in PDF path not URL-encoded", strict=True)
def test_pdf_link_encodes_special_chars():
    meta = {"title": "T", "authors": ["A"],
            "attachments": [{"path": "/Users/x/paper#2 100%.pdf", "is_pdf": True}]}
    note = sps.render_note("K", "cite", "1. RQ", meta)
    link_line = next(ln for ln in note.splitlines() if "file:" in ln)
    assert "%23" in link_line, f"'#' not encoded: {link_line!r}"
    assert "%25" in link_line, f"'%' not encoded: {link_line!r}"


@pytest.mark.xfail(reason="R8 (U5): citation key with '/' escapes the output dir", strict=True)
def test_citation_key_path_separator_sanitized(tmp_path):
    p, _action = sps._prepare_output_path(tmp_path, "a/b", "skip")
    assert p.parent == tmp_path, f"path escaped output dir: {p}"


@pytest.mark.xfail(reason="R8 (U5): versioned stamp lacks seconds", strict=True)
def test_versioned_stamp_includes_seconds(tmp_path):
    (tmp_path / "@k.md").write_text("existing", encoding="utf-8")
    p, _action = sps._prepare_output_path(tmp_path, "k", "versioned")
    assert re.search(r"-\d{8}-\d{6}\.md$", p.name), f"no seconds in stamp: {p.name}"


@pytest.mark.xfail(reason="R8 (U5): dry-run creates the output directory", strict=True)
def test_dry_run_has_no_side_effects(tmp_path):
    out = tmp_path / "does_not_exist_yet"
    proc = _run_script(
        tmp_path, summary="1. RQ\nbody\n", metadata={"title": "T", "authors": ["A"]},
        output_dir=out, on_exists="overwrite", write=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert not out.exists(), "dry-run must not create the output directory"
