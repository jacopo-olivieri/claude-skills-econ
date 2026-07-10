"""Characterization and resolver-integration tests for manual search."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import search_stata_docs as search
import stata_config as config


SKILL_PATH = Path(__file__).resolve().parents[2] / "SKILL.md"


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


def test_explicit_docs_beats_invalid_environment_and_config(
    tmp_path, monkeypatch, capsys
):
    manual = tmp_path / "d.pdf"
    manual.touch()
    invalid_config = tmp_path / "invalid.json"
    invalid_config.write_text("not json", encoding="utf-8")
    invalid_config.chmod(0o600)
    monkeypatch.setattr(config, "CONFIG_PATH", invalid_config)
    monkeypatch.setenv("STATA_DOCS_DIR", str(tmp_path / "missing env docs"))
    monkeypatch.setattr(
        search, "import_pdfplumber", lambda: FakePdfPlumber(["Merge data"])
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["search_stata_docs.py", "merge", "--docs-dir", str(tmp_path), "--pdf", "d"],
    )

    assert search.main() == 0
    assert "d.pdf:1: Merge data" in capsys.readouterr().out


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


def test_main_uses_environment_docs_without_explicit_option(
    tmp_path, monkeypatch, capsys
):
    (tmp_path / "r.pdf").touch()
    reader = FakePdfPlumber(["Merge result"])
    monkeypatch.setenv("STATA_DOCS_DIR", str(tmp_path))
    monkeypatch.setattr(search, "import_pdfplumber", lambda: reader)
    monkeypatch.setattr(
        sys, "argv", ["search_stata_docs.py", "merge", "--pdf", "r.pdf"]
    )

    assert search.main() == 0
    captured = capsys.readouterr()
    assert "r.pdf:1: Merge result" in captured.out
    assert reader.opened == [str(tmp_path / "r.pdf")]


def test_main_uses_injected_known_default_without_observing_host(
    tmp_path, monkeypatch, capsys
):
    (tmp_path / "r.pdf").touch()
    reader = FakePdfPlumber(["Known default result"])
    monkeypatch.delenv("STATA_DOCS_DIR", raising=False)
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(config, "DEFAULT_KNOWN_DOCS", (tmp_path,))
    monkeypatch.setattr(search, "import_pdfplumber", lambda: reader)
    monkeypatch.setattr(
        sys, "argv", ["search_stata_docs.py", "default", "--pdf", "r.pdf"]
    )

    assert search.main() == 0
    captured = capsys.readouterr()
    assert "r.pdf:1: Known default result" in captured.out
    assert reader.opened == [str(tmp_path / "r.pdf")]


def test_cli_uses_private_config_when_no_explicit_or_environment_value(tmp_path):
    home = tmp_path / "home"
    docs = tmp_path / "configured manuals"
    docs.mkdir()
    config_path = home / ".agents/config/stata.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps({"stata_docs_dir": str(docs)}), encoding="utf-8"
    )
    config_path.chmod(0o600)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.pop("STATA_DOCS_DIR", None)

    result = subprocess.run(
        [sys.executable, str(Path(search.__file__)), "term", "--pdf", "missing"],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 1
    assert f"PDF not found: {docs / 'missing.pdf'}" in result.stderr


def test_invalid_environment_docs_fails_without_config_fallback(
    tmp_path, monkeypatch, capsys
):
    invalid = tmp_path / "not a directory"
    invalid.write_text("x", encoding="utf-8")
    configured = tmp_path / "configured docs"
    configured.mkdir()
    config_path = tmp_path / "stata.json"
    config_path.write_text(
        json.dumps({"stata_docs_dir": str(configured)}), encoding="utf-8"
    )
    config_path.chmod(0o600)
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)
    monkeypatch.setenv("STATA_DOCS_DIR", str(invalid))
    monkeypatch.setattr(sys, "argv", ["search_stata_docs.py", "term", "--pdf", "x"])

    assert search.main() == 1
    captured = capsys.readouterr()
    assert "not-directory:" in captured.err
    assert str(invalid) in captured.err


def test_skill_routes_every_operational_resource_through_shared_resolver():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    for resource in (
        "stata-bin",
        "docs-dir",
        "ado-base-dir",
        "author",
        "stata-version",
    ):
        assert f'stata_config.py" {resource}' in skill

    assert "/Applications/Stata" not in skill
    assert "/" + "Users/" not in skill
    assert "Weathering " + "Poverty" not in skill
    assert "Jacopo " + "Olivieri" not in skill
    assert "<project name>" in skill
    assert "<author>" in skill
    assert "<stata-version>" in skill
