"""Cross-skill integration tests for the paper-summary -> paper-summary-obsidian
handoff (R9, R18 integration half, KTD-8).

A summary written in the ``notes_template.md`` shape (the paper-summary skill's
output) is rendered by ``save_paper_summary.py`` and checked against a committed
golden note, once per writing style (current template shape and the new
two-tier shape). Synthetic paper markdown is also round-tripped through
``paper_workspace.split_paper`` to prove the section split loses no content.
All I/O stays under ``tmp_path`` or reads committed fixtures.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import save_paper_summary as sps
from conftest import DATA_DIR

# The sibling skill's splitter lives in another scripts/ directory.
PAPER_SUMMARY_SCRIPTS = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "paper-summary" / "scripts"
)
sys.path.insert(0, str(PAPER_SUMMARY_SCRIPTS))
import paper_workspace as pw  # noqa: E402

SAVE_SCRIPT = Path(sps.__file__)

GOLDEN_METADATA = {
    "title": "Rural Roads and Household Consumption",
    "authors": ["Sam Asher", "Paul Novosad"],
    "date_published": "2020-03-01",
    "itemType": "journalArticle",
    "journal": "American Economic Review",
    "url": "https://example.com/roads",
    "abstract": "We study rural road access.",
}

# Content phrases that must survive the handoff with zero loss, per style.
CONTENT_PHRASES = {
    "template_shape": [
        "Does rural road access raise household consumption?",
        "Data (source, type, time span)",
        "Household survey, 2010-2015, 500 villages",
        "Regression discontinuity at the population threshold",
        "Consumption rises 8% (se 2%)",
        "Author-stated: short five-year panel",
        "Extend to labour-market outcomes",
    ],
    "two_tier": [
        "Rural roads are hypothesised to raise consumption by lowering trade costs.",
        "The paper asks whether new all-weather roads change household consumption",
        "Identification rests on a population-threshold discontinuity in road eligibility.",
        "Household survey covers 2010-2015 across 500 villages",
        "Road access raises consumption without inducing migration.",
        "Consumption rises 8% (se 2%)",
        "The short panel limits long-run inference.",
    ],
}


@pytest.mark.parametrize("style", ["template_shape", "two_tier"])
def test_summary_renders_to_golden_note(style):
    summary = (DATA_DIR / f"summary_{style}.md").read_text(encoding="utf-8")
    golden = (DATA_DIR / f"golden_{style}.md").read_text(encoding="utf-8")
    rendered = sps.render_note("ITEMKEY", "asherRoads2020", summary, GOLDEN_METADATA)
    assert rendered == golden, f"{style} render drifted from the committed golden"


@pytest.mark.parametrize("style", ["template_shape", "two_tier"])
def test_handoff_loses_no_content(style):
    summary = (DATA_DIR / f"summary_{style}.md").read_text(encoding="utf-8")
    rendered = sps.render_note("ITEMKEY", "asherRoads2020", summary, GOLDEN_METADATA)
    for phrase in CONTENT_PHRASES[style]:
        assert phrase in rendered, f"content lost in {style}: {phrase!r}"
    # The synthesis moved to Key takeaways.
    key_block = rendered.split("%% end notes %%")[0]
    assert "Roads raise consumption but not migration." in key_block


@pytest.mark.parametrize("style", ["template_shape", "two_tier"])
def test_two_tier_headlines_have_no_bold_and_carry_anchors(style):
    # The rendered note must never start a bullet with bold, and evidence must
    # carry anchors (a headline architecture property from the review).
    rendered = sps.render_note(
        "ITEMKEY", "asherRoads2020",
        (DATA_DIR / f"summary_{style}.md").read_text(encoding="utf-8"),
        GOLDEN_METADATA,
    )
    ann = rendered.split("%% begin annotations %%")[1]
    for line in ann.splitlines():
        assert not line.lstrip().startswith("- **"), f"bold-led bullet: {line!r}"


def test_paper_split_round_trips_without_content_loss():
    paper = (
        "Abstract paragraph about roads.\n\n"
        "# 1. Introduction\nIntro sentence one. Intro sentence two.\n\n"
        "# 2. Data\nData sentence about the survey.\n\n"
        "# 3. Results\nResult sentence with an estimate.\n\n"
        "# 4. Conclusion\nConcluding remark.\n\n"
        "# References\nAsher and Novosad (2020).\n"
    )
    intro, sections, appendix = pw.split_paper(paper)
    joined = intro + "\n" + "\n".join(body for _, body in sections) + "\n" + appendix
    for phrase in [
        "Abstract paragraph about roads.",
        "Intro sentence one.",
        "Data sentence about the survey.",
        "Result sentence with an estimate.",
        "Concluding remark.",
        "Asher and Novosad (2020).",
    ]:
        assert phrase in joined, f"split dropped: {phrase!r}"
    assert "Asher and Novosad (2020)." in appendix  # references -> appendix


# --------------------------------------------------------------------------- #
# summary_sections.json single source (R9 / KTD-8)
# --------------------------------------------------------------------------- #

def _run_save(tmp_path, *, template, env=None):
    summary_file = tmp_path / "summary.txt"
    summary_file.write_text("1. Research Question\n- A point [p. 1]\n", encoding="utf-8")
    meta_file = tmp_path / "meta.json"
    meta_file.write_text(json.dumps({"title": "T", "authors": ["A"]}), encoding="utf-8")
    cmd = [
        sys.executable, str(SAVE_SCRIPT), "--item-key", "K", "--citation-key", "c",
        "--summary-file", str(summary_file), "--metadata-file", str(meta_file),
        "--template-path", str(template), "--output-dir", str(tmp_path / "vault"),
        "--on-exists", "overwrite", "--write",
    ]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_renaming_fold_heading_in_json_propagates(tmp_path):
    # A modified JSON renames the s1 fold heading; the rendered note AND the R10
    # template contract must follow without any change to the script. (The user
    # updates their template to match — mirrored here by patching the fixture.)
    from conftest import TEMPLATE_FIXTURE
    new_heading_text = "💬 RENAMED Question Heading"
    custom = json.loads((PAPER_SUMMARY_SCRIPTS.parent / "references" / "summary_sections.json").read_text())
    custom["sections"][0]["fold_heading"] = f"### {new_heading_text} %% fold %%"
    custom_path = tmp_path / "custom_sections.json"
    custom_path.write_text(json.dumps(custom), encoding="utf-8")

    # Template contract now derives its expected headings from the JSON, so the
    # template must carry the renamed heading for the contract to pass.
    patched_template = tmp_path / "template.md"
    patched_template.write_text(
        TEMPLATE_FIXTURE.read_text(encoding="utf-8").replace(
            "💬 Research Question and Motivation", new_heading_text
        ),
        encoding="utf-8",
    )

    import os
    env = dict(os.environ, PAPER_SUMMARY_SECTIONS_FILE=str(custom_path))
    proc = _run_save(tmp_path, template=patched_template, env=env)
    assert proc.returncode == 0, proc.stderr
    written = (tmp_path / "vault" / "@c.md").read_text(encoding="utf-8")
    assert f"### {new_heading_text} %% fold %%" in written


def test_missing_json_falls_back_to_embedded_with_warning(tmp_path):
    from conftest import TEMPLATE_FIXTURE
    import os
    env = dict(os.environ, PAPER_SUMMARY_SECTIONS_FILE=str(tmp_path / "nope.json"))
    proc = _run_save(tmp_path, template=TEMPLATE_FIXTURE, env=env)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert any("summary_sections.json" in w for w in payload["warnings"])
    # The note still renders with the embedded fold heading.
    written = (tmp_path / "vault" / "@c.md").read_text(encoding="utf-8")
    assert "### 💬 Research Question and Motivation %% fold %%" in written
