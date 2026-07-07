"""Smoke tests for blank_tex_comments.py against the committed fixture paper."""

import regbuild as rb

PAPER = rb.FIXTURE_DIR / "planted" / "paper" / "paper.tex"

btc = rb.load_script("blank_tex_comments")


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


def test_env_name_regex_accepts_digits():
    # A custom environment whose name contains a digit (e.g. figure2) must be
    # recognised by the widened environment-name character class.
    assert btc.BEGIN_RE.search(r"\begin{figure2}").group(1) == "figure2"
    assert btc.END_RE.search(r"\end{figure2}").group(1) == "figure2"


def test_digit_env_comment_lines_blanked(tmp_path):
    src = tmp_path / "paper.tex"
    src.write_text(
        "\\begin{figure2}\n"
        "% secret_caption inside a custom digit-named env\n"
        "\\end{figure2}\n",
        encoding="utf-8",
    )
    out = tmp_path / "paper.audit.tex"
    res = rb.run_script("blank_tex_comments.py", src, "-o", out)
    assert res.returncode == 0, res.stdout + res.stderr

    blanked = out.read_text(encoding="utf-8")
    # line count preserved and the comment content is gone
    assert len(blanked.split("\n")) == len(src.read_text(encoding="utf-8").split("\n"))
    assert "secret_caption" in src.read_text(encoding="utf-8")
    assert "secret_caption" not in blanked


def test_creates_missing_output_parent_dir(tmp_path):
    out = tmp_path / "nested" / "deeper" / "paper.audit.tex"
    assert not out.parent.exists()
    res = rb.run_script("blank_tex_comments.py", PAPER, "-o", out)
    assert res.returncode == 0, res.stdout + res.stderr
    assert out.is_file()
