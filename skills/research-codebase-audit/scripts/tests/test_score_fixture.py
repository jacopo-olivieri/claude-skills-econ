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


def hit_claims_rows(p14_branch="inconsistent"):
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
    ]


def write_final_registers(tmp_path, claims_rows, error_rows,
                          summary=CLEAN_SUMMARY):
    audit = tmp_path / "audit"
    audit.mkdir()
    (audit / "claims_register.md").write_text(
        rb.register_text("Claims register", rb.CLAIMS_COLS, claims_rows))
    (audit / "code_error_register.md").write_text(
        rb.register_text("Code-error register", rb.ERROR_COLS, error_rows))
    (audit / "output_register.md").write_text(
        rb.register_text("Output register", rb.OUTPUT_COLS, []))
    (audit / "register_cross_link_summary.md").write_text(summary)
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
    assert "Recall: 14/14" in res.stdout
    assert "MISS" not in res.stdout


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
    assert "Recall: 14/14" in res.stdout  # decoy alone flips the gate


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
