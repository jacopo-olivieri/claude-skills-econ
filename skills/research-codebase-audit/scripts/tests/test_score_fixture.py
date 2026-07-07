"""Self-tests for score_fixture.py against synthetic final registers.

The HIT texts below double as documentation of the mechanism-signature
matching contract: each contains the signature terms a real run's rows have
carried in prior (hand-adjudicated) scorecards.
"""

import re

import regbuild as rb

CLEAN_SUMMARY = (
    "# Register cross-link summary\n\n"
    "## Status conflicts\n\n(none)\n\n"
    "## Escalated mapped claims\n\n(none)\n\n"
    "## Severity divergences\n\n(none)\n"
)

# Minimal U2 parser artifact (audit/_run/manifest_check.md) naming the planted
# malformed manifest — what a real b4 run of check_manifests.py leaves behind.
MANIFEST_ARTIFACT = (
    "# Manifest parseability check\n\n"
    "## Manifests checked\n\n"
    "| Manifest | Format | Problem lines |\n| --- | --- | --- |\n"
    "| `pyproject.toml` | toml | 1 |\n\n"
    "## Candidate findings\n\n"
    "| Manifest | Format | Line | Offending Text | Problem |\n"
    "| --- | --- | --- | --- | --- |\n"
    "| pyproject.toml | toml | 4 |  | invalid TOML: Expected newline or end "
    "of document after a statement (at line 4, column 14) |\n"
)

# Same artifact shape but with every manifest parsing clean — the U2 plant
# missing from the candidate findings.
MANIFEST_ARTIFACT_CLEAN = (
    "# Manifest parseability check\n\n"
    "## Manifests checked\n\n"
    "| Manifest | Format | Problem lines |\n| --- | --- | --- |\n"
    "| `pyproject.toml` | toml | 0 |\n\n"
    "## Candidate findings\n\n"
    "No candidate findings: every recognized manifest parsed clean.\n"
)

# The plant's name appears ONLY in the `## Warnings` section that render_artifact
# writes AFTER the Candidate-findings section, with ZERO candidate findings —
# the shape a run leaves when the parser could not read the manifest (e.g. a
# permission error). The plant was never actually flagged, so the U2 check must
# FAIL: bounding the search to the Candidate-findings body is what catches it.
MANIFEST_ARTIFACT_PLANT_ONLY_IN_WARNINGS = (
    "# Manifest parseability check\n\n"
    "## Manifests checked\n\n"
    "| Manifest | Format | Problem lines |\n| --- | --- | --- |\n"
    "| `pyproject.toml` | toml | 0 |\n\n"
    "## Candidate findings\n\n"
    "No candidate findings: every recognized manifest parsed clean.\n\n"
    "## Warnings\n\n"
    "- could not read pyproject.toml: [Errno 13] Permission denied\n"
)


def hit_claims_rows(p14_branch="inconsistent", p19_branch="inconsistent",
                    p20_branch="inconsistent"):
    rows = [
        rb.claims_row(
            "C-0001", status="inconsistent", severity="4",
            ctype="transcription",
            issue=("The prose reports a coefficient of 0.083 but the shipped "
                   "table artifact tab1.tex shows -0.038."),
        ),
        rb.claims_row(
            "C-0013", status="inconsistent", severity="2",
            ctype="sample_count",
            issue=("The paper states 725 of 2,416 households (25 percent); "
                   "725/2,416 is 30 percent, an arithmetic slip."),
        ),
    ]
    if p19_branch == "inconsistent":
        rows.append(rb.claims_row(
            "C-0019", status="inconsistent", severity="2",
            ctype="estimation_specification",
            text=("wage earnings (`wage_earnings`) are winsorised at the "
                  "99th percentile before entering total income"),
            source="`py/build_income.py`",
            issue=("The paper says wage_earnings are winsorised at the 99th "
                   "percentile; build_income.py winsorises crop_sales "
                   "instead — the named variable is untouched."),
        ))
    elif p19_branch == "confirmed":
        rows.append(rb.claims_row(
            "C-0019", status="confirmed",
            ctype="estimation_specification",
            text=("wage earnings (`wage_earnings`) are winsorised at the "
                  "99th percentile before entering total income"),
            source="`py/build_income.py`",
        ))
    if p20_branch == "inconsistent":
        rows.append(rb.claims_row(
            "C-0020", status="inconsistent", severity="2",
            ctype="data_construction",
            text=("each village is matched to every rain gauge within a "
                  "15-km radius of its centroid"),
            source="`data/village_rain_radius_25km.csv`",
            issue=("Appendix A step 2 states a 15-km gauge radius; the "
                   "shipped file village_rain_radius_25km.csv encodes "
                   "25 km."),
        ))
    elif p20_branch == "blocked_with_note":
        rows.append(rb.claims_row(
            "C-0020", status="blocked",
            ctype="data_construction",
            text=("each village is matched to every rain gauge within a "
                  "15-km radius of its centroid"),
            source="`data/village_rain_radius_25km.csv`",
            blocked_check=("Gauge coordinates are not shipped, so the match "
                           "cannot be re-run; but the paper's 15-km radius "
                           "is contradicted by the shipped filename "
                           "village_rain_radius_25km.csv (25 km)."),
        ))
    elif p20_branch == "silent_block":
        rows.append(rb.claims_row(
            "C-0020", status="blocked",
            ctype="data_construction",
            text=("each village is matched to every rain gauge within a "
                  "15-km radius of its centroid; series shipped as "
                  "village_rain_radius_25km.csv"),
            source="`data/village_rain_radius_25km.csv`",
            blocked_check="Gauge coordinates are not distributed.",
        ))
    if p14_branch == "inconsistent":
        rows.append(rb.claims_row(
            "C-0014", status="inconsistent", severity="2",
            ctype="data_construction",
            issue=("The paper says a one-in-ten subsample; the README "
                   "describes households.csv as a 1-in-20 subsample."),
        ))
    elif p14_branch == "blocked_with_note":
        rows.append(rb.claims_row(
            "C-0014", status="blocked",
            text="estimates use the public one-in-ten subsample",
            blocked_check=("The full census is restricted-access, but the "
                           "README describes households.csv as a 1-in-20 "
                           "subsample whereas the paper says one-in-ten."),
        ))
    elif p14_branch == "silent_block":
        # mechanism visible in the row, but the Blocked Check does not record
        # the contradiction — the failure mode P-14 exists to catch
        rows.append(rb.claims_row(
            "C-0014", status="blocked",
            text=("estimates use the public one-in-ten subsample of the "
                  "1-in-20 census release"),
            blocked_check="The restricted census could not be inspected.",
        ))
    elif p14_branch == "empty_blocked_check":
        rows.append(rb.claims_row(
            "C-0014", status="blocked",
            text=("estimates use the public one-in-ten subsample of the "
                  "1-in-20 census release"),
            blocked_check="",
        ))
    return rows


def hit_error_rows():
    mk = rb.error_row
    return [
        mk("E-0002", etype="inference_or_se_specification", severity="3",
           desc=("The paper claims clustering at the village level; "
                 "analysis.do clusters at the household level.")),
        mk("E-0003", etype="weighting_error", severity="3",
           desc=("Regressions run unweighted although the paper claims "
                 "survey weights; svy_weight is never used.")),
        mk("E-0004", etype="randomness_or_seed_error", severity="2",
           desc="bootstrap with 200 replications and no set seed."),
        mk("E-0005", etype="sample_filter_or_flag_error", severity="4",
           desc=("keep if waves < 2 keeps exactly the households the paper "
                 "excludes (fewer than two waves).")),
        mk("E-0006", etype="stale_or_wrong_path", severity="2",
           desc="make_figures.py reads output/panel_v2.csv which no script writes."),
        mk("E-0007", etype="undefined_variable_or_global", severity="3",
           desc=("The $controls global is defined only in a commented-out "
                 "line; regressions run without controls.")),
        mk("E-0008", etype="aggregation_or_unit_error", severity="3",
           desc=("Income is divided by 100 although the paper says thousands "
                 "of local currency units — a factor-of-10 error.")),
        mk("E-0009", etype="readme_or_package_mismatch", severity="1",
           desc="The README lists data/rainfall_stations.csv, which does not exist."),
        mk("E-0010", etype="pii_or_disclosure_risk", severity="2",
           desc="head_name and gps_lat/gps_lon ship in the public data file."),
        mk("E-0011", etype="treatment_or_event_timing_error", severity="2",
           desc=("rain_mean is computed from the two in-sample waves, not "
                 "the 1991-2020 long-run climate normal the paper defines.")),
        mk("E-0012", etype="output_label_or_path_mismatch", severity="1",
           desc=("The figure legend is reversed: ax.legend(['Shocked', "
                 "'Non-shocked']) against the unstacked column order.")),
        mk("E-0015", etype="aggregation_or_unit_error", severity="2",
           desc=("build_income.py sums only crop_sales, livestock_sales and "
                 "wage_earnings, omitting the remittances component from the "
                 "paper's four-component income list.")),
        mk("E-0016", etype="version_or_dependency_error", severity="2",
           desc=("pyproject.toml is invalid TOML (version = 0.4.1 is "
                 "unquoted), so the documented pip install -e . cannot "
                 "parse the manifest.")),
        mk("E-0017", etype="sample_filter_or_flag_error", severity="2",
           desc=("The backfill comment says missing hhsize is filled, but "
                 "`if hhsize < .` acts only on non-missing rows, so the "
                 "missing wave-2 value is never filled.")),
        mk("E-0018", etype="sample_filter_or_flag_error", severity="2",
           desc=("has_wages is overwritten on each loop iteration, so the "
                 "wave-2 pass erases wave-1 matches and the flag reflects "
                 "the last wave only.")),
    ]


def write_final_registers(tmp_path, claims_rows, error_rows,
                          summary=CLEAN_SUMMARY,
                          manifest_artifact=MANIFEST_ARTIFACT,
                          conventions=None, ledger_rows=None,
                          claims_original_cols=False):
    audit = tmp_path / "audit"
    audit.mkdir(parents=True)
    if claims_original_cols:
        # Post-b8 finalize promotes the rewriter's staging register, appending
        # an `Issue Description Original` column — the real shape of a scored
        # run's final claims register (mirrors regbuild.make_b8).
        c_cols = rb.CLAIMS_COLS + ["Issue Description Original"]
        c_rows = [list(r) + [r[rb.CLAIMS_COLS.index("Issue Description")]]
                  for r in claims_rows]
        (audit / "claims_register.md").write_text(
            rb.register_text("Claims register", c_cols, c_rows))
    else:
        (audit / "claims_register.md").write_text(
            rb.register_text("Claims register", rb.CLAIMS_COLS, claims_rows))
    (audit / "code_error_register.md").write_text(
        rb.register_text("Code-error register", rb.ERROR_COLS, error_rows))
    (audit / "output_register.md").write_text(
        rb.register_text("Output register", rb.OUTPUT_COLS, []))
    (audit / "register_cross_link_summary.md").write_text(summary)
    if manifest_artifact is not None:
        (audit / "_run").mkdir(exist_ok=True)
        (audit / "_run" / "manifest_check.md").write_text(manifest_artifact)
    if conventions is not None:
        (audit / "_run").mkdir(exist_ok=True)
        (audit / "_run" / "conventions.md").write_text(conventions)
    if ledger_rows is not None:
        (audit / "_recheck").mkdir(exist_ok=True)
        (audit / "_recheck" / "k1.md").write_text(
            rb.register_text("Recheck ledger", rb.LEDGER_COLS, ledger_rows))
    return audit


def run_scorer(audit):
    return rb.run_script("score_fixture.py", "--audit-dir", audit)


def plant_line(res, pid):
    for ln in res.stdout.splitlines():
        if ln.startswith(f"{pid}:"):
            return ln
    raise AssertionError(f"no line for {pid} in:\n{res.stdout}")


def test_gate_green_on_full_hit_set(tmp_path):
    audit = write_final_registers(tmp_path, hit_claims_rows(), hit_error_rows())
    res = run_scorer(audit)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "GATE GREEN" in res.stdout
    assert "Recall: 20/20" in res.stdout
    assert "MISS" not in res.stdout


def test_new_plants_present_and_hit(tmp_path):
    """Each 2026-07-07 failure-class plant is in the key and scored must-find."""
    audit = write_final_registers(tmp_path, hit_claims_rows(), hit_error_rows())
    res = run_scorer(audit)
    for pid in ("P-15", "P-16", "P-17", "P-18", "P-19", "P-20"):
        assert re.match(rf"{pid}: HIT", plant_line(res, pid)), plant_line(res, pid)


def test_per_class_tags_reported(tmp_path):
    audit = write_final_registers(tmp_path, hit_claims_rows(), hit_error_rows())
    res = run_scorer(audit)
    assert "[class=enumerated_member_list]" in plant_line(res, "P-15")
    assert "Per-class:" in res.stdout
    for cls in ("enumerated_member_list", "manifest_parseability",
                "empirical_verification", "identifier_anchoring",
                "step_parameter_filename"):
        assert cls in res.stdout


def test_per_class_breakdown_lists_every_planted_class(tmp_path):
    """U10: the per-class breakdown alongside the aggregate lists EACH planted
    class with hit/miss counts — including the pre-2026-07-07 plants
    P-01..P-14, which carry no failure_class tag and roll up in an explicit
    unclassified_legacy bucket."""
    audit = write_final_registers(tmp_path, hit_claims_rows(), hit_error_rows())
    res = run_scorer(audit)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "Per-class:" in res.stdout
    for line in (
        "enumerated_member_list: 1/1 hit, 0 miss",
        "manifest_parseability: 1/1 hit, 0 miss",
        "empirical_verification: 2/2 hit, 0 miss",
        "identifier_anchoring: 1/1 hit, 0 miss",
        "step_parameter_filename: 1/1 hit, 0 miss",
        "unclassified_legacy: 14/14 hit, 0 miss",
    ):
        assert line in res.stdout, f"missing per-class line {line!r} in:\n{res.stdout}"


def test_per_class_breakdown_counts_misses(tmp_path):
    """U10: a miss shows up in its class's hit/miss counts, and the legacy
    bucket is unaffected."""
    errors = [r for r in hit_error_rows() if r[0] != "E-0015"]  # drop P-15 hit
    audit = write_final_registers(tmp_path, hit_claims_rows(), errors)
    res = run_scorer(audit)
    assert res.returncode == 1
    assert "enumerated_member_list: 0/1 hit, 1 miss" in res.stdout
    assert "unclassified_legacy: 14/14 hit, 0 miss" in res.stdout


def test_p14_blocked_with_note_branch_is_hit(tmp_path):
    audit = write_final_registers(
        tmp_path, hit_claims_rows("blocked_with_note"), hit_error_rows())
    res = run_scorer(audit)
    assert res.returncode == 0, res.stdout + res.stderr
    assert re.match(r"P-14: HIT", plant_line(res, "P-14"))
    assert "blocked branch" in plant_line(res, "P-14")


def test_p14_silent_block_is_miss(tmp_path):
    audit = write_final_registers(
        tmp_path, hit_claims_rows("silent_block"), hit_error_rows())
    res = run_scorer(audit)
    assert res.returncode == 1
    assert re.match(r"P-14: MISS", plant_line(res, "P-14"))
    assert "silently-blocked" in plant_line(res, "P-14")
    assert "GATE RED" in res.stdout


def test_p14_empty_blocked_check_is_miss(tmp_path):
    audit = write_final_registers(
        tmp_path, hit_claims_rows("empty_blocked_check"), hit_error_rows())
    res = run_scorer(audit)
    assert res.returncode == 1
    assert re.match(r"P-14: MISS", plant_line(res, "P-14"))


def test_decoy_presence_turns_gate_red(tmp_path):
    errors = hit_error_rows() + [rb.error_row(
        "E-0099", etype="missing_input_or_output", severity="1",
        desc="artifacts/fig_placebo.pdf referenced by a placebo figure block "
             "is not produced by any script.")]
    audit = write_final_registers(tmp_path, hit_claims_rows(), errors)
    res = run_scorer(audit)
    assert res.returncode == 1
    assert "D-01 decoy: PRESENT" in res.stdout
    assert "GATE RED" in res.stdout
    assert "Recall: 20/20" in res.stdout  # decoy alone flips the gate


def test_intentional_subset_decoy_turns_gate_red(tmp_path):
    """The U1 intentional-subset decoy (D-02): a finding about the
    farm-components subset is a false positive and flips the gate."""
    errors = hit_error_rows() + [rb.error_row(
        "E-0098", etype="sample_filter_or_flag_error", severity="2",
        desc=("farm_components in build_income.py lists only crop_sales and "
              "livestock_sales, diverging from the paper's four-component "
              "income list."))]
    audit = write_final_registers(tmp_path, hit_claims_rows(), errors)
    res = run_scorer(audit)
    assert res.returncode == 1
    assert "D-02 decoy: PRESENT" in res.stdout
    assert "GATE RED" in res.stdout


def test_decoy_in_summary_turns_gate_red(tmp_path):
    summary = CLEAN_SUMMARY + "\nNote: fig_placebo.pdf was inspected.\n"
    audit = write_final_registers(tmp_path, hit_claims_rows(),
                                  hit_error_rows(), summary=summary)
    res = run_scorer(audit)
    assert res.returncode == 1
    assert "D-01 decoy: PRESENT" in res.stdout


def test_sc01_unresolved_status_conflict_turns_gate_red(tmp_path):
    claims = hit_claims_rows() + [rb.claims_row(
        "C-0021", status="confirmed", ctype="treatment_definition",
        text=("the rainfall shock is the deviation from the village's "
              "long-run historical mean (the 1991-2020 climate normal)"))]
    audit = write_final_registers(tmp_path, claims, hit_error_rows())
    res = run_scorer(audit)
    assert res.returncode == 1
    assert "SC-01: FAIL" in res.stdout


def test_below_min_severity_is_miss(tmp_path):
    """P-05 requires severity >= 4; a sev-2 row matches but does not score."""
    errors = [r for r in hit_error_rows() if r[0] != "E-0005"]
    errors.append(rb.error_row(
        "E-0005", etype="sample_filter_or_flag_error", severity="2",
        desc=("keep if waves < 2 keeps exactly the households the paper "
              "excludes (fewer than two waves).")))
    audit = write_final_registers(tmp_path, hit_claims_rows(), errors)
    res = run_scorer(audit)
    assert res.returncode == 1
    assert re.match(r"P-05: MISS", plant_line(res, "P-05"))
    assert "severity >= 4" in plant_line(res, "P-05")


def test_missing_register_is_usage_error(tmp_path):
    audit = tmp_path / "audit"
    audit.mkdir()
    res = run_scorer(audit)
    assert res.returncode == 2
    assert "not found" in res.stderr


# ------------------------------------------------- artifact-layer checks (U9)


def test_missing_manifest_artifact_turns_gate_red(tmp_path):
    audit = write_final_registers(tmp_path, hit_claims_rows(),
                                  hit_error_rows(), manifest_artifact=None)
    res = run_scorer(audit)
    assert res.returncode == 1
    assert "U2 manifest artifact: FAIL" in res.stdout
    assert "GATE RED" in res.stdout


def test_manifest_artifact_without_plant_turns_gate_red(tmp_path):
    audit = write_final_registers(tmp_path, hit_claims_rows(),
                                  hit_error_rows(),
                                  manifest_artifact=MANIFEST_ARTIFACT_CLEAN)
    res = run_scorer(audit)
    assert res.returncode == 1
    assert "U2 manifest artifact: FAIL" in res.stdout


def test_u4_u5_artifact_checks_vacuous_when_claims_flagged(tmp_path):
    audit = write_final_registers(tmp_path, hit_claims_rows(), hit_error_rows())
    res = run_scorer(audit)
    assert res.returncode == 0
    assert "U4 anchoring advisory: PASS" in res.stdout
    assert "U5 filename-parameter advisory: PASS" in res.stdout


def test_u4_advisory_fired_on_confirmed_unanchored_close(tmp_path):
    """P-19 wrongly closed confirmed with evidence that never names
    wage_earnings: register layer scores MISS, and the artifact layer records
    that the U4 tripwire fired."""
    ledger = [rb.ledger_row(
        "C-0019", status="confirmed", severity="",
        evidence=("`py/build_income.py:18` applies a 99th-percentile "
                  "winsorisation via clip"),
        verdict="substantiated", change="set status=confirmed")]
    audit = write_final_registers(
        tmp_path, hit_claims_rows(p19_branch="confirmed"), hit_error_rows(),
        ledger_rows=ledger)
    res = run_scorer(audit)
    assert res.returncode == 1  # P-19 register MISS reds the gate
    assert re.match(r"P-19: MISS", plant_line(res, "P-19"))
    assert "U4 anchoring advisory: PASS" in res.stdout
    assert "tripwire fired" in res.stdout


def test_u4_advisory_silent_on_confirmed_close_is_fail(tmp_path):
    """P-19 closed confirmed with evidence that DOES name wage_earnings: the
    lexical advisory stays silent, so the artifact check records FAIL."""
    ledger = [rb.ledger_row(
        "C-0019", status="confirmed", severity="",
        evidence=("wage_earnings winsorisation verified at "
                  "`py/build_income.py:18`"),
        verdict="substantiated", change="set status=confirmed")]
    audit = write_final_registers(
        tmp_path, hit_claims_rows(p19_branch="confirmed"), hit_error_rows(),
        ledger_rows=ledger)
    res = run_scorer(audit)
    assert res.returncode == 1
    assert "U4 anchoring advisory: FAIL" in res.stdout


def test_u5_blocked_with_note_branch_hit_and_advisory_fires(tmp_path):
    """P-20 dual-accept blocked branch: register HIT, advisory fires, gate can
    stay GREEN."""
    audit = write_final_registers(
        tmp_path, hit_claims_rows(p20_branch="blocked_with_note"),
        hit_error_rows())
    res = run_scorer(audit)
    assert res.returncode == 0, res.stdout + res.stderr
    assert re.match(r"P-20: HIT", plant_line(res, "P-20"))
    assert "blocked branch" in plant_line(res, "P-20")
    assert "U5 filename-parameter advisory: PASS" in res.stdout
    assert "tripwire fired" in res.stdout


def test_u5_silent_block_is_register_miss(tmp_path):
    audit = write_final_registers(
        tmp_path, hit_claims_rows(p20_branch="silent_block"), hit_error_rows())
    res = run_scorer(audit)
    assert res.returncode == 1
    assert re.match(r"P-20: MISS", plant_line(res, "P-20"))
    assert "silently-blocked" in plant_line(res, "P-20")


def test_u1_conventions_check_is_informative_only(tmp_path):
    """The U1 conventions-artifact check reports INFO and never settles the
    gate (worker-dependent per KTD-8) — the gate stays GREEN whether the
    artifact is present or absent."""
    conventions = (
        "# Shared conventions\n\n"
        "| Convention | Category | Stated Definition | Sites Already Seen |\n"
        "| --- | --- | --- | --- |\n"
        "| income components | enumerated_member_list | crop sales; "
        "livestock sales; wage earnings; remittances (C-0015) | "
        "`paper/paper.tex`; C-0015 |\n")
    with_artifact = write_final_registers(
        tmp_path / "a", hit_claims_rows(), hit_error_rows(),
        conventions=conventions)
    res = run_scorer(with_artifact)
    assert res.returncode == 0
    assert "U1 conventions artifact: INFO" in res.stdout
    assert "enumerated_member_list convention PRESENT" in res.stdout
    without_artifact = write_final_registers(
        tmp_path / "b", hit_claims_rows(), hit_error_rows())
    res = run_scorer(without_artifact)
    assert res.returncode == 0  # absence never reds the gate
    assert "U1 conventions artifact: INFO" in res.stdout


def test_manifest_plant_only_in_warnings_turns_gate_red(tmp_path):
    """Finding-5 regression: the plant's name appears only in the `## Warnings`
    section (zero candidate findings) — it was never actually flagged, so the
    U2 check must FAIL and red the gate rather than falsely pass on the warning
    line that names pyproject.toml outside the Candidate-findings body."""
    audit = write_final_registers(
        tmp_path, hit_claims_rows(), hit_error_rows(),
        manifest_artifact=MANIFEST_ARTIFACT_PLANT_ONLY_IN_WARNINGS)
    res = run_scorer(audit)
    assert res.returncode == 1
    assert "U2 manifest artifact: FAIL" in res.stdout
    assert "GATE RED" in res.stdout


def test_u4_advisory_tolerates_post_b8_original_columns(tmp_path):
    """Finding-1 regression: the finalized claims register carries the post-b8
    `Issue Description Original` extra column (the rewriter's staging register is
    promoted at finalize). The U4 anchoring advisory must still locate the claims
    table and fire on a confirmed-but-unanchored P-19 close. Fails before the
    header-tolerance fix (the advisory silently no-ops against the exact-header
    match -> U4 reports FAIL); passes after (the tripwire fires -> PASS)."""
    ledger = [rb.ledger_row(
        "C-0019", status="confirmed", severity="",
        evidence=("`py/build_income.py:18` applies a 99th-percentile "
                  "winsorisation via clip"),
        verdict="substantiated", change="set status=confirmed")]
    audit = write_final_registers(
        tmp_path, hit_claims_rows(p19_branch="confirmed"), hit_error_rows(),
        ledger_rows=ledger, claims_original_cols=True)
    res = run_scorer(audit)
    assert "U4 anchoring advisory: PASS" in res.stdout, res.stdout
    assert "tripwire fired" in res.stdout


def test_u4_anchoring_not_covered_when_confirmed_close_has_no_ledger_row(tmp_path):
    """NOT COVERED branch: the P-19 claim is closed confirmed but no recheck
    ledger row covers it, so the tripwire never saw it. The line reads NOT
    COVERED and contributes no red reason of its own (the register layer's P-19
    MISS is what reds the gate)."""
    audit = write_final_registers(
        tmp_path, hit_claims_rows(p19_branch="confirmed"), hit_error_rows())
    res = run_scorer(audit)
    assert "U4 anchoring advisory: NOT COVERED" in res.stdout
    assert "U4 anchoring advisory check failed" not in res.stdout
    assert re.match(r"P-19: MISS", plant_line(res, "P-19"))


def test_u5_filename_parameter_not_covered_when_row_misses_locator(tmp_path):
    """NOT COVERED branch: a blocked P-20-family row whose text does not match
    the U5 claim locator leaves the advisory with nothing to key on. The line
    reads NOT COVERED and adds no red reason of its own."""
    claims = [r for r in hit_claims_rows() if r[0] != "C-0020"]
    claims.append(rb.claims_row(
        "C-0020", status="blocked", ctype="data_construction",
        text="each village is matched to nearby rain gauges by centroid",
        source="`data/village_rain.csv`",
        blocked_check="Gauge coordinates are not shipped, so the match cannot "
                      "be re-run."))
    audit = write_final_registers(tmp_path, claims, hit_error_rows())
    res = run_scorer(audit)
    assert "U5 filename-parameter advisory: NOT COVERED" in res.stdout
    assert "U5 filename-parameter advisory check failed" not in res.stdout


def test_artifact_checks_fail_when_claims_register_unparsable(tmp_path):
    """FAIL branch: the claims register exists but carries no parsable claims
    table, so both conditional artifact checks report FAIL and red the gate."""
    audit = write_final_registers(tmp_path, hit_claims_rows(), hit_error_rows())
    (audit / "claims_register.md").write_text(
        "# Claims register\n\n| Foo | Bar |\n| --- | --- |\n| a | b |\n")
    res = run_scorer(audit)
    assert res.returncode == 1
    assert ("U4 anchoring advisory: FAIL — claims register missing or "
            "unparsable") in res.stdout
    assert ("U5 filename-parameter advisory: FAIL — claims register missing or "
            "unparsable") in res.stdout
