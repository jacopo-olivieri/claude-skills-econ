"""Contract tests for the shared definition/use wire-format parser."""

import re

import pytest

import regbuild as rb


du = rb.load_script("definition_use")


def artifact(*, standard=("DU-aaa111",), advisory=("DU-bbb222",)):
    return rb.definition_use_artifact(
        standard_bundle_ids=standard,
        advisory_bundle_ids=advisory,
        files_scanned=3,
        producer_groups=1,
    )


def test_exact_bundle_tokens_do_not_accept_prefix_substrings():
    text = "checked DU-abc123; rejected DU-abc1234 and XDU-abc123"
    assert du.extract_bundle_tokens(text) == {"DU-abc123", "DU-abc1234"}
    assert "DU-abc123" not in du.extract_bundle_tokens("checked DU-abc1234")


def test_parse_positive_artifact_preserves_counts_and_categories():
    parsed = du.parse_artifact(artifact())

    assert parsed.files_scanned == 3
    assert parsed.standard_producer_groups == 1
    assert [row["Bundle ID"] for row in parsed.standard_rows] == ["DU-aaa111"]
    assert [row["Bundle ID"] for row in parsed.advisory_rows] == ["DU-bbb222"]


def test_parse_explicit_zero_bundle_artifact():
    parsed = du.parse_artifact(artifact(standard=(), advisory=()))

    assert parsed.standard_rows == []
    assert parsed.advisory_rows == []


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda text: text.replace("## Candidate findings", "## Findings"),
         "Candidate findings"),
        (lambda text: text.replace("- Standard candidates: 1",
                                   "- Standard candidates: 2"),
         "Standard candidates count"),
        (lambda text: text.replace("DU-bbb222", "DU-aaa111"),
         "duplicate Bundle ID"),
        (lambda text: text.replace("DU-aaa111", "not-a-bundle"),
         "invalid Bundle ID"),
        (lambda text: text.replace("| review narrowing |", "|"),
         "malformed"),
    ],
)
def test_parse_artifact_rejects_malformed_wire_formats(mutate, message):
    with pytest.raises(du.DefinitionUseFormatError, match=message):
        du.parse_artifact(mutate(artifact()))


def test_parse_mappings_normalizes_cells_and_ignores_blank_placeholder():
    text = (
        "## Definition/use bundle mapping\n\n"
        + rb.md_table(
            du.MAPPING_COLS,
            [["`DU-aaa111`", "`E-0101`", " existing_row "], ["", "", ""]],
        )
    )

    assert du.parse_mappings(text) == [{
        "Bundle ID": "DU-aaa111",
        "Error ID": "E-0101",
        "Mapping Kind": "existing_row",
    }]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("# no table\n", "mapping table"),
        ("| Bundle ID | Error ID | Mapping Kind |\n"
         "| --- | --- | --- |\n| DU-aaa111 | E-0101 |\n", "malformed"),
        ("| Bundle ID | Error ID | Mapping Kind |\n"
         "| --- | --- | --- |\n| bad | E-0101 | existing_row |\n",
         "invalid Bundle ID"),
    ],
)
def test_parse_mappings_rejects_malformed_tables(text, message):
    with pytest.raises(du.DefinitionUseFormatError, match=message):
        du.parse_mappings(text)


def test_active_definition_use_surfaces_have_no_legacy_names():
    legacy = "de" + "fuse"
    forbidden = [
        re.compile(legacy + r"_bundles"),
        re.compile(("DEF" + "USE") + r"_"),
        re.compile(rf"(?:check|parse|test)_[A-Za-z0-9_]*{legacy}"),
    ]
    active = [
        rb.SKILL_DIR / "SKILL.md",
        rb.SKILL_DIR / "references" / "pipeline-code-errors.md",
        rb.SKILL_DIR / "fixture" / "README.md",
        *rb.SCRIPTS_DIR.glob("*.py"),
        *rb.TESTS_DIR.glob("*.py"),
    ]
    stale = []
    for path in active:
        text = path.read_text(encoding="utf-8")
        if any(pattern.search(text) for pattern in forbidden):
            stale.append(path.relative_to(rb.SKILL_DIR).as_posix())
    assert stale == []
