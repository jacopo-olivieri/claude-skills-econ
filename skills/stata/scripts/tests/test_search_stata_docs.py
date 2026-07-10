"""Characterization tests for the deployed Stata manual search helper."""

import sys
from pathlib import Path

import pytest

import search_stata_docs as search


class FakePage:
    def __init__(self, text):
        self.text = text

    def extract_text(self):
        return self.text


class FakePdf:
    def __init__(self, pages):
        self.pages = [FakePage(text) for text in pages]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakePdfPlumber:
    def __init__(self, pages):
        self.pages = pages
        self.opened = []

    def open(self, path):
        self.opened.append(path)
        return FakePdf(self.pages)


def test_parse_pages_uses_one_based_bounds_and_clips_to_document():
    assert search.parse_pages(None, 10) is None
    assert search.parse_pages("1-3,5,9-12,99", 10) == {0, 1, 2, 4, 8, 9}


@pytest.mark.parametrize("value", ["0", "3-2", "a", "1-x"])
def test_parse_pages_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        search.parse_pages(value, 10)


def test_literal_and_regex_modes_and_case_sensitivity():
    literal = search.build_pattern("a.b", regex=False, ignore_case=True)
    assert literal.search("A.B")
    assert not literal.search("axb")

    regex = search.build_pattern("a.b", regex=True, ignore_case=False)
    assert regex.search("axb")
    assert not regex.search("AXB")

    with pytest.raises(ValueError, match="Invalid regex"):
        search.build_pattern("[", regex=True, ignore_case=True)


def test_named_pdf_selection_appends_suffix_and_all_pdf_selection_is_sorted(tmp_path):
    (tmp_path / "z.pdf").touch()
    (tmp_path / "a.pdf").touch()
    (tmp_path / "ignore.txt").touch()

    assert search.iter_pdf_paths(tmp_path, "z") == [tmp_path / "z.pdf"]
    assert search.iter_pdf_paths(tmp_path, "z.pdf") == [tmp_path / "z.pdf"]
    assert search.iter_pdf_paths(tmp_path, None) == [
        tmp_path / "a.pdf",
        tmp_path / "z.pdf",
    ]

    with pytest.raises(FileNotFoundError, match="PDF not found"):
        search.iter_pdf_paths(tmp_path, "missing")


def test_search_respects_page_filter_context_and_result_limit(tmp_path):
    reader = FakePdfPlumber(
        [
            "before one\nMerge first\nafter one",
            "Merge skipped page",
            "before three\nmerge second\nafter three\nMERGE third",
        ]
    )
    pattern = search.build_pattern("merge", regex=False, ignore_case=True)

    matches = search.search_pdf(
        reader, tmp_path / "d.pdf", pattern, context=1, pages_arg="1,3", remaining=2
    )

    assert matches == [
        (1, "Merge first", ["before one", "Merge first", "after one"]),
        (3, "merge second", ["before three", "merge second", "after three"]),
    ]


def test_main_named_pdf_has_no_warning_and_prints_results(tmp_path, monkeypatch, capsys):
    manual = tmp_path / "d.pdf"
    manual.touch()
    reader = FakePdfPlumber(["before\nMerge data\nafter"])
    monkeypatch.setattr(search, "import_pdfplumber", lambda: reader)
    monkeypatch.setattr(
        sys,
        "argv",
        ["search_stata_docs.py", "merge", "--docs-dir", str(tmp_path), "--pdf", "d"],
    )

    assert search.main() == 0
    captured = capsys.readouterr()
    assert "d.pdf:1: Merge data" in captured.out
    assert "Warning:" not in captured.err


def test_main_all_manual_scan_prints_slow_warning(tmp_path, monkeypatch, capsys):
    (tmp_path / "r.pdf").touch()
    monkeypatch.setattr(
        search, "import_pdfplumber", lambda: FakePdfPlumber(["no matching text"])
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["search_stata_docs.py", "merge", "--docs-dir", str(tmp_path)],
    )

    assert search.main() == 0
    captured = capsys.readouterr()
    assert "scanning all Stata manuals is slow" in captured.err
    assert "No results found for: merge" in captured.out


def test_main_case_sensitive_regex_mode(tmp_path, monkeypatch, capsys):
    (tmp_path / "r.pdf").touch()
    monkeypatch.setattr(
        search, "import_pdfplumber", lambda: FakePdfPlumber(["merge\nMERGE"])
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "search_stata_docs.py",
            "^MERGE$",
            "--docs-dir",
            str(tmp_path),
            "--pdf",
            "r.pdf",
            "--regex",
            "--case-sensitive",
            "--context",
            "0",
        ],
    )

    assert search.main() == 0
    captured = capsys.readouterr()
    assert "r.pdf:1: MERGE" in captured.out
    assert "r.pdf:1: merge" not in captured.out
