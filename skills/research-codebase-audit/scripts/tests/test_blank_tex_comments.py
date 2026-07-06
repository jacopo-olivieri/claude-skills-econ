"""Smoke tests for blank_tex_comments.py against the committed fixture paper."""

import regbuild as rb

PAPER = rb.FIXTURE_DIR / "planted" / "paper" / "paper.tex"


def test_blank_fixture_paper_preserves_lines_and_removes_decoy(tmp_path):
    out = tmp_path / "paper.audit.tex"
    res = rb.run_script("blank_tex_comments.py", PAPER, "-o", out)
    assert res.returncode == 0, res.stdout + res.stderr

    src = PAPER.read_text(encoding="utf-8")
    blanked = out.read_text(encoding="utf-8")
    # line numbers must be preserved exactly
    assert len(blanked.split("\n")) == len(src.split("\n"))
    # the D-01 decoy lives only in comments: present in the source,
    # gone after blanking
    assert "fig_placebo" in src
    assert "fig_placebo" not in blanked


def test_refuses_output_equal_to_input(tmp_path):
    copy = tmp_path / "paper.tex"
    copy.write_text(PAPER.read_text(encoding="utf-8"), encoding="utf-8")
    res = rb.run_script("blank_tex_comments.py", copy, "-o", copy)
    assert res.returncode == 2
    assert "output path equals input path" in res.stderr
