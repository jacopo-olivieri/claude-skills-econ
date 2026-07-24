"""U9c diagnosed-fix cycle: register handoffs, bands, and replay parity."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import regbuild as rb
import test_replay_harness as replay_helpers
import test_u6_supplementary as u6


ac = rb.load_script("check_argument_contracts")
dm = rb.load_script("build_detector_mapping")
lintmod = rb.load_script("lint_registers")
mechanism = rb.load_script("mechanism_schema")
replay = rb.load_script("replay_stage")
rulings = rb.load_script("severity_token_rulings")
score_fixture = rb.load_script("score_fixture")
tokens = rb.load_script("severity_tokens")
verifier = rb.load_script("verify_dismissals")

pytestmark = pytest.mark.u9

AC_SOURCE_ID = ac.source_id("source.py", 1, 0)


def _ac_artifact(source_id=AC_SOURCE_ID, witnesses=("argpos:2",)):
    call = ac.CallSite(
        source_id, "source.py:1@call=0", "shell", "python", "source.py",
        "source.py", "direct", tuple(int(w.split(":")[1]) for w in witnesses),
        (1,), "contract_mismatch",
    )
    findings = tuple(
        ac.Finding(
            source_id, witness, "passed_but_unread", witness.split(":")[1],
            "source.py", "source.py:1@call=0",
        )
        for witness in witnesses
    )
    return ac.Artifact("a" * 64, (call,), findings)


def _mapping_row(channel, source_id, witness_id, error_id, anchor):
    return {
        "Channel": channel, "Source ID": source_id, "Witness ID": witness_id,
        "Error ID": error_id, "Mapping Kind": "new_candidate",
        "Site Anchor": anchor,
    }


def _write_mapping(a, rows):
    by_channel = {"DU": [], "MF": [], "CV": [], "AC": []}
    for row in rows:
        by_channel[row["Channel"]].append(row)
    a.write("_run/detector_mapping.md", dm.render_mapping(
        "E-7000–E-7099", by_channel))


def _minimal_b6_case(tmp_path, *, channel, source_id, witness_id, verdict,
                     accepted, rule=None, stamp=None):
    root = tmp_path / "package"
    root.mkdir()
    (root / "source.py").write_text("value = 1\n", encoding="utf-8")
    (root / "environment.yml").write_text(
        "name: empty\nprefix: /tmp/example\n", encoding="utf-8")
    a = rb.AuditDir(root)
    a.write("_run/definition_use_bundles.md", rb.definition_use_artifact([]))
    error_id = "E-7000"
    anchor = (
        "source.py:1@call=0" if channel == "AC" else "environment.yml:2")
    mapping = _mapping_row(channel, source_id, witness_id, error_id, anchor)
    _write_mapping(a, [mapping])
    if channel == "AC":
        artifact = _ac_artifact(source_id, (witness_id,))
        a.write("_run/argument_contracts.md", ac.render(artifact))
    if channel == "MF":
        a.write(
            "_run/manifest_check.md",
            "# Manifest check\n\n"
            + rb.md_table(
                ["Source ID", "Witness ID", "Site Anchor", "Rule Slug",
                 "Offending Text", "Problem"],
                [[source_id, witness_id, anchor, rule or "conda-malformed-line",
                  "prefix: /tmp/example", "oracle adjudication"]],
            ),
        )
    else:
        a.write(
            "_run/manifest_check.md",
            "# Manifest parseability check\n\n"
            + verifier.manifests.NO_FINDINGS_LINE + "\n"
            + verifier.manifests.MF_ZERO_LINE + "\n",
        )
    status = "not_error" if verdict == "not_error" else "confirmed"
    severity = "" if verdict == "not_error" else "2"
    description = stamp or "detector candidate description"
    final = rb.error_row(
        error_id, etype="missing_input_or_output", source="`source.py`",
        location=anchor, status=status, severity=severity, desc=description,
    )
    a.write_register("code_error_register.md", rb.ERROR_COLS, [final])
    a.write_register(
        "_run/snapshots/code_b6a/code_error_register.md",
        rb.ERROR_COLS, [final],
    )
    record_id = "VR-0001"
    ledger = rb.code_ledger_row(
        error_id, evidence=source_id, verdict=verdict,
        proposed_status=status, proposed_severity=severity or "—",
        accepted_type="missing_input_or_output", witness_ids=witness_id,
        record_ids=record_id,
    )
    a.write(
        "_code_error_recheck/k1.md",
        rb.register_text("Recheck ledger", rb.CODE_LEDGER_COLS, [ledger]),
    )
    a.write("code_error_recheck_summary.md", "# Recheck summary\n")
    sidecar = mechanism.canonicalize_mechanism(
        "missing_input_or_output", "source.py", "omits", "[argument]", "-",
        register="code_errors", anchor=anchor,
        projection=mechanism.EMPTY_PROJECTION,
    ).sidecar
    a.write(
        "_run/code_b6a/witness_outcomes.md",
        "# Witness outcomes\n\n"
        + rb.md_table(rb.POST_WITNESS_COLS, [[
            channel, source_id, witness_id, verdict, sidecar,
            severity or "—", ("RCP-test" if accepted else "—"), "—",
        ]])
        + "\n### Assembled dismissals\n\n"
        + (rb.md_table(["Error ID"], [[error_id]])
           if verdict == "not_error"
           else "No mapped Error IDs were assembled as not_error.\n"),
    )
    receipt = [
        channel, "RCP-test", source_id, witness_id, record_id, "micromamba",
        "test", "a" * 64, "micromamba env create", "0" if accepted else "1",
        "yes" if accepted else "no", "b" * 64,
    ]
    a.write(
        "_run/code_b6a/dismissal_receipts.md",
        "# Dismissal receipts\n\n"
        + rb.md_table(verifier.RECEIPT_COLS, [receipt]),
    )
    return root, a


def test_p26_builder_stamps_every_argument_contract_witness(tmp_path):
    root = tmp_path / "package"
    root.mkdir()
    (root / "source.py").write_text("value = 1\n", encoding="utf-8")
    a = rb.AuditDir(root)
    source_id = AC_SOURCE_ID
    artifact = _ac_artifact(source_id, ("argpos:2", "argpos:3"))
    a.write("_run/argument_contracts.md", ac.render(artifact))
    a.write("_run/definition_use_bundles.md", rb.definition_use_artifact([]))
    a.write(
        "_run/manifest_check.md",
        "# Manifest parseability check\n\n"
        + verifier.manifests.NO_FINDINGS_LINE + "\n"
        + verifier.manifests.MF_ZERO_LINE + "\n",
    )
    a.write_manifest(mode="code_errors_only", scope_exclusions=[], off_limits=[])
    candidate = rb.error_row(
        "E-7000", etype="missing_input_or_output", source="`source.py`",
        location="source.py:1@call=0", status="candidate", severity="2",
    )
    a.write_register("_staging/code_error_register.md", rb.ERROR_COLS, [candidate])
    a.write_register(
        "_run/snapshots/code_b3d/code_error_register.md", rb.ERROR_COLS, [])
    a.write(
        "_run/detector_mapping_decisions.md",
        "# Decisions\n\nDeclared detector Error-ID range: E-7000–E-7099\n\n"
        + rb.md_table(dm.DECISION_COLS, [[
            "AC", source_id, "E-7000", "new_candidate",
        ]]),
    )
    result = rb.run_script(
        "build_detector_mapping.py", root, "--audit-dir", a.audit)
    assert result.returncode == 0, result.stdout + result.stderr
    row = dm.parse_register(a.audit / "_staging/code_error_register.md")["E-7000"]
    expected = [
        dm.argument_contract_stamp(
            finding.finding_kind, finding.witness_id, "source.py",
            finding.callee_path, finding.argument_position,
            finding.site_anchor,
        )
        for finding in artifact.findings
    ]
    assert all(sentence in row["Error Description"] for sentence in expected)
    assert row["Error Description"].count("Argument-contract finding") == 2


def test_p26_b6_binding_fires_on_stripped_stamp_and_is_quiet_when_preserved(
        tmp_path):
    source_id, witness_id = AC_SOURCE_ID, "argpos:2"
    stamp = dm.argument_contract_stamp(
        "passed_but_unread", witness_id, "source.py", "source.py", "2",
        "source.py:1@call=0")
    _root, a = _minimal_b6_case(
        tmp_path, channel="AC", source_id=source_id, witness_id=witness_id,
        verdict="confirmed_error", accepted=False, stamp=stamp,
    )
    clean = lintmod.Lint()
    lintmod.check_detector_mapping_b6(clean, a.audit)
    assert not any("machine-written stamp" in error for error in clean.errors)
    register = a.audit / "code_error_register.md"
    register.write_text(
        register.read_text(encoding="utf-8").replace(stamp, ""),
        encoding="utf-8",
    )
    stripped = lintmod.Lint()
    lintmod.check_detector_mapping_b6(stripped, a.audit)
    assert any("machine-written stamp" in error for error in stripped.errors)


def test_tier1_p26_survival_test_oracle_notices_disabled_binding(
        tmp_path, monkeypatch):
    source_id, witness_id = AC_SOURCE_ID, "argpos:2"
    stamp = dm.argument_contract_stamp(
        "passed_but_unread", witness_id, "source.py", "source.py", "2",
        "source.py:1@call=0")
    _root, a = _minimal_b6_case(
        tmp_path, channel="AC", source_id=source_id, witness_id=witness_id,
        verdict="confirmed_error", accepted=False, stamp=stamp,
    )
    register = a.audit / "code_error_register.md"
    register.write_text(
        register.read_text(encoding="utf-8").replace(stamp, ""),
        encoding="utf-8",
    )

    def negative_oracle():
        state = lintmod.Lint()
        lintmod.check_detector_mapping_b6(state, a.audit)
        assert any("machine-written stamp" in error for error in state.errors)

    negative_oracle()
    monkeypatch.setattr(
        lintmod.detector_mapping, "expected_ac_stamps",
        lambda *_args, **_kwargs: {},
    )
    with pytest.raises(AssertionError):
        negative_oracle()


def test_tier1_p26_post_b6a_strip_fails_b6b_and_verify_run_clis(tmp_path):
    root, a, _shard = u6.make_wave(tmp_path, discovery=False)
    source_id, witness_id = AC_SOURCE_ID, "argpos:2"
    artifact = _ac_artifact(source_id, (witness_id,))
    a.write("_run/argument_contracts.md", ac.render(artifact))
    a.write("_run/definition_use_bundles.md", rb.definition_use_artifact([]))
    a.write(
        "_run/manifest_check.md",
        "# Manifest parseability check\n\n"
        + verifier.manifests.NO_FINDINGS_LINE + "\n"
        + verifier.manifests.MF_ZERO_LINE + "\n",
    )
    _write_mapping(a, [
        _mapping_row(
            "AC", source_id, witness_id, "E-0100",
            "source.py:1@call=0",
        ),
    ])
    stamp = dm.argument_contract_stamp(
        "passed_but_unread", witness_id, "source.py", "source.py", "2",
        "source.py:1@call=0")
    sidecar = mechanism.canonicalize_mechanism(
        "missing_input_or_output", "source.py", "omits", "[argument]", "-",
        register="code_errors", anchor="source.py:1@call=0",
        projection=mechanism.EMPTY_PROJECTION,
    ).sidecar
    ledger = rb.code_ledger_row(
        "E-0100", evidence=source_id, verdict="confirmed_error",
        proposed_status="confirmed", proposed_severity="2",
        accepted_type="missing_input_or_output",
        accepted_mechanism=sidecar, witness_ids=witness_id,
    )
    outcome = rb.witness_outcome_row(
        "AC", source_id, witness_id, verdict="confirmed_error",
        severity="2", mech_class="missing_input_or_output",
        mech_object="source.py", relation="omits",
        expected="[argument]", actual="-",
    )
    a.write(
        "_code_error_recheck/k1.md",
        rb.register_text("Recheck ledger", rb.CODE_LEDGER_COLS, [ledger])
        + "\n### Witness outcomes\n\n"
        + rb.md_table(rb.WITNESS_OUTCOME_COLS, [outcome])
        + "\n### Verification records\n\nNo verification records.\n"
        + u6.footer(),
    )
    stamped = rb.error_row(
        "E-0100", etype="missing_input_or_output", source="`source.py`",
        location="source.py:1@call=0", status="confirmed", severity="2",
        desc=stamp,
    )
    a.write_register(
        "_run/snapshots/code_b6b/code_error_register.md",
        rb.ERROR_COLS, [stamped],
    )
    a.write_register("code_error_register.md", rb.ERROR_COLS, [stamped])
    assembler_text = rb.md_table(rb.POST_WITNESS_COLS, [[
        "AC", source_id, witness_id, "confirmed_error", sidecar, "2",
        "—", "—",
    ]])
    a.write(
        "_run/code_b6a/witness_outcomes.md",
        "# Witness outcomes\n\n" + assembler_text
        + "\n### Assembled dismissals\n\n"
        "No mapped Error IDs were assembled as not_error.\n",
    )
    u6.certify_to_b5s(root, discovery=False)
    started = u6.cli(root, "start", "--stage", "code_b6b")
    assert started.returncode == 0, started.stdout + started.stderr
    register = a.audit / "code_error_register.md"
    register.write_text(
        register.read_text(encoding="utf-8").replace(stamp, ""),
        encoding="utf-8",
    )
    direct = rb.lint(a, "b6b-code")
    assert direct.returncode == 1
    assert "machine-written stamp" in direct.stdout
    refused = u6.cli(
        root, "finish", "--stage", "code_b6b", "--outcome", "done")
    assert refused.returncode == 1
    assert "machine-written stamp" in refused.stderr
    manifest = json.loads((a.audit / "_run/manifest.json").read_text())
    manifest["stages"]["code_b6b"]["status"] = "done"
    u6.certify.write_manifest_atomic(root, manifest)
    verified = u6.cli(root, "verify-run")
    assert verified.returncode == 1
    assert "code_b6b" in verified.stderr


def test_d03_matcher_stays_quiet_on_preserved_p18_row_and_keeps_plant_hits():
    # Verbatim from the preserved gate run 1 register
    # (~/scratch/rca-u9b-gate-run1-pkg/audit/code_error_register.md).
    preserved = {
        "Error ID": "E-0010",
        "Error Type": "sample_filter_or_flag_error",
        "Code/Data Source": "`py/build_income.py`",
        "Code Location": "`py/build_income.py:24-26`",
        "Status": "confirmed", "Severity": "2",
        "Error Description": (
            'Line 24 comment says "Flag households reporting wage earnings '
            'in any wave." Lines 25-26 loop over waves `(1, 2)` and assign '
            '`df["has_wages"] = (df["wave"] == wave) & '
            '(df["wage_earnings"] > 0)` each iteration. Each iteration '
            "overwrites the column entirely, so after the loop completes "
            "only wave 2 status is retained. Synthetic probe confirmed: a "
            "household with wage_earnings > 0 only in wave 1 is flagged "
            "False for both of its rows."),
        "Why It Matters": (
            "The has_wages diagnostic flag is incorrect for any household "
            "whose wage status differs between waves. The flag only "
            'reflects wave 2 status, not "any wave" as the comment '
            "documents."),
    }
    # Verbatim from the preserved invalid-config run register
    # (~/scratch/rca-u9b-invalid-config-run-20260722-pkg/audit/).
    preserved_e0051 = {
        "Error ID": "E-0051",
        "Error Type": "sample_filter_or_flag_error",
        "Code/Data Source": "`py/build_income.py`",
        "Code Location": "`py/build_income.py:25-26`",
        "Status": "confirmed", "Severity": "2",
        "Error Description": (
            'The comment on line 24 says "Flag households reporting wage '
            'earnings in any wave." The loop `for wave in (1, 2): '
            'df["has_wages"] = ...` overwrites `has_wages` on each '
            "iteration, so after the loop completes only the wave-2 "
            "condition survives. Households with wage earnings in wave 1 "
            "but not wave 2 are incorrectly flagged False. Synthetic probe "
            "confirmed: a household with wage_earnings > 0 only in wave 1 "
            "gets has_wages = False after the loop."),
        "Why It Matters": (
            "The has_wages flag in output/income_check.csv is incorrect "
            "for all wave-1-only wage earners; the diagnostic output does "
            "not match its stated intent."),
    }
    assert score_fixture.is_d03(preserved) is False
    assert score_fixture.is_d03(preserved_e0051) is False
    assert score_fixture.is_d03({
        **preserved, "Code/Data Source": "`do/analysis.do`",
        "Code Location": "`do/analysis.do:41`",
        "Error Description": (
            "The first-wave diagnostic restricts the analytic sample by "
            "dropping baseline observations."),
    }) is True
    assert score_fixture.is_d03({
        **preserved, "Code/Data Source": "`do/analysis.do`",
        "Code Location": "`do/analysis.do:13`",
    }) is True


@pytest.mark.parametrize(
    "accepted,verdict,expected_failure",
    [(True, "confirmed_error", True),
     (False, "confirmed_error", False),
     (True, "not_error", False)],
)
def test_d04_b6_oracle_accept_obligation(
        tmp_path, accepted, verdict, expected_failure):
    _root, a = _minimal_b6_case(
        tmp_path, channel="MF", source_id="MF-aaaaaaaaaaaa",
        witness_id="MFW-bbbbbbbbbbbb", verdict=verdict, accepted=accepted,
        rule="conda-malformed-line",
    )
    state = lintmod.Lint()
    lintmod.check_detector_mapping_b6(state, a.audit)
    failures = [
        error for error in state.errors
        if "required disposition is mechanical not_error" in error
    ]
    assert bool(failures) is expected_failure


def test_d04_receipt_obligation_skips_duplicate_verdict(tmp_path):
    # verify_dismissals mints pinned-oracle receipts only for not_error and
    # confirmed_error dispositions, so the b6 cardinality check must stay
    # quiet on a duplicate verdict — otherwise the failure is unsatisfiable.
    _root, a = _minimal_b6_case(
        tmp_path, channel="MF", source_id="MF-aaaaaaaaaaaa",
        witness_id="MFW-bbbbbbbbbbbb", verdict="confirmed_error",
        accepted=False, rule="conda-malformed-line",
    )
    shard = a.audit / "_code_error_recheck/k1.md"
    shard.write_text(
        shard.read_text(encoding="utf-8").replace(
            "| confirmed_error |", "| duplicate |"),
        encoding="utf-8",
    )
    a.write(
        "_run/code_b6a/dismissal_receipts.md",
        "# Dismissal receipts\n\n" + verifier.ZERO_RECEIPTS + "\n",
    )
    state = lintmod.Lint()
    lintmod.check_detector_mapping_b6(state, a.audit)
    assert not any("pinned-oracle receipt" in error for error in state.errors)
    assert not any(
        "required disposition is mechanical not_error" in error
        for error in state.errors
    )


def test_d04_verifier_receipts_confirmed_conda_candidate(
        tmp_path, monkeypatch):
    root, a = _minimal_b6_case(
        tmp_path, channel="MF", source_id="MF-aaaaaaaaaaaa",
        witness_id="MFW-bbbbbbbbbbbb", verdict="confirmed_error",
        accepted=True, rule="conda-malformed-line",
    )
    record = [
        "MF", "VR-0001", "MF-aaaaaaaaaaaa", "MFW-bbbbbbbbbbbb",
        "a" * 64, "micromamba", "test", "micromamba env create",
        "accepted", "yes",
    ]
    shard = a.audit / "_code_error_recheck/k1.md"
    shard.write_text(
        shard.read_text(encoding="utf-8")
        + "\n" + rb.md_table(verifier.MF_RECORD_COLS, [record]),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        verifier, "_manifest_run",
        lambda *_args: (
            "micromamba", "test", "micromamba env create",
            SimpleNamespace(returncode=0, stdout=b"", stderr=b""),
        ),
    )
    receipts = verifier.verify(root, a.audit)
    assert len(receipts) == 1
    assert receipts[0]["Accepted (yes/no)"] == "yes"


def _p28_fixture(tmp_path, *, cv=True, covering=False, verdict="upheld"):
    root = tmp_path / "package"
    root.mkdir(parents=True)
    a = rb.AuditDir(root)
    a.write_manifest(mode="replication")
    py = root / "py"
    py.mkdir()
    capita = ["pass"] * 20
    capita[13] = 'income_pc = income / age_head'
    capita[16] = 'wage_pc = wage_earnings / age_head'
    capita[19] = 'crop_pc = crop_sales / age_head'
    (py / "build_capita.py").write_text("\n".join(capita) + "\n", encoding="utf-8")
    (py / "table.py").write_text("print(age_head)\n", encoding="utf-8")
    row = rb.error_row(
        "E-0011", etype="aggregation_or_unit_error",
        source="`py/build_capita.py`; `py/table.py`",
        location="py/build_capita.py:14", status="confirmed", severity="3",
        desc="wage_pc divides by age_head",
        why="reported output is affected output:O-0121",
    )
    a.write_register("code_error_register.md", rb.ERROR_COLS, [row])
    a.write_register("_staging/code_error_register.md", rb.ERROR_COLS, [row])
    a.write_register("claims_register.md", rb.CLAIMS_COLS, [])
    a.write_register("output_register.md", rb.OUTPUT_COLS, [
        rb.output_row(
            "O-0121", script="`py/table.py`",
            location="`paper/paper.tex:1`"),
    ])
    witness = "CVW-774f1d1f861f" if cv else "DUW-774f1d1f861f"
    channel = "CV" if cv else "DU"
    source_id = "CV-267217db96d3" if cv else "DU-267217db96d3"
    mapping = _mapping_row(
        channel, source_id, witness, "E-0011",
        ('py/build_capita.py:line 17: `wage_pc = wage_earnings / age_head`'
         if cv else "py/build_capita.py:17"),
    )
    _write_mapping(a, [mapping])
    sidecar = mechanism.canonicalize_mechanism(
        "variable_substitution", "age_head", "wrong_value", "hhsize",
        "age_head", register="code_errors", anchor="py/build_capita.py:17",
        projection=mechanism.EMPTY_PROJECTION,
    ).sidecar
    lineage = [{"anchor": "py/build_capita.py:14", "carries": "age_head"}]
    if covering:
        lineage.append({
            "anchor": "py/build_capita.py:17", "carries": "wage_pc"})
    lineage.append({"anchor": "py/table.py:1", "carries": "age_head"})
    digest = tokens.obligation_digest(
        "E-0011", "output:O-0121", sidecar, witness,
        "py/build_capita.py:14", "age_head",
    )
    record = {
        "Record Type": "token_verification", "Error ID": "E-0011",
        "Token": "output:O-0121", "Obligation Digest": digest,
        "Mechanism": sidecar, "Witness IDs": witness,
        "Error Location": "py/build_capita.py:14",
        "Flawed Identifier": "age_head", "Cited Target": "O-0121",
        "Lineage JSON": json.dumps(lineage, separators=(",", ":")),
        "Probe Path": "probe.py",
        "Probe Output SHA256": tokens.result_digest(0, b"", b""),
        "Verdict": "verified", "Derived From Receipt ID": "—",
    }
    ledger = rb.code_ledger_row(
        "E-0011", status="confirmed", severity="3",
        proposed_status="confirmed", proposed_severity="3",
        accepted_type="aggregation_or_unit_error",
        accepted_mechanism=sidecar, witness_ids=witness,
    )
    shard = a.audit / "_code_error_recheck/k1.md"
    shard.parent.mkdir(parents=True, exist_ok=True)
    (shard.parent / "probe.py").write_text("pass\n", encoding="utf-8")
    a.write(
        "_code_error_recheck/k1.md",
        rb.register_text("Recheck ledger", rb.CODE_LEDGER_COLS, [ledger])
        + "\n### Token verification records\n\n"
        + rb.md_table(tokens.TOKEN_RECORD_COLS, [[
            record[column] for column in tokens.TOKEN_RECORD_COLS
        ]]),
    )
    manifest = json.loads((a.audit / "_run/manifest.json").read_text())
    receipts, failures = tokens.verify_token_records(
        root, a.audit, manifest, "code_b6b")
    assert failures == []
    tokens.write_atomic(
        tokens.receipt_path(a.audit, "code_b6b"),
        tokens.render_receipts(receipts),
    )
    a.write(
        "register_cross_link_summary.md",
        "# Cross-link summary\n\n## Severity-token adjudications\n\n"
        + rb.md_table(tokens.ADJUDICATION_COLS, [[
            "E-0011 output:O-0121", "O-0121", verdict, "py/table.py:1",
        ]]),
    )
    return root, a, manifest


def test_p28_b7_refuses_borrowed_tie_allows_covering_lineage_and_ignores_non_cv(
        tmp_path):
    root, a, manifest = _p28_fixture(tmp_path / "borrowed")
    _rejected, failures = rulings.validate_b7(root, a.audit, manifest)
    assert any("mapped CV witness-site mismatch cannot be upheld" in f
               for f in failures)
    root, a, manifest = _p28_fixture(tmp_path / "cover", covering=True)
    _rejected, failures = rulings.validate_b7(root, a.audit, manifest)
    assert not any("witness-site" in f for f in failures)
    root, a, manifest = _p28_fixture(tmp_path / "non-cv", cv=False)
    _rejected, failures = rulings.validate_b7(root, a.audit, manifest)
    assert not any("witness-site" in f for f in failures)


def test_tier1_p28_b7_to_rulings_cli_caps_borrowed_tie(tmp_path):
    root, a, _manifest = _p28_fixture(
        tmp_path, verdict="rejected")
    checked = rb.run_script(
        "severity_token_rulings.py", "check-b7", root,
        "--audit-dir", a.audit)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    snap = rb.run_script(
        "severity_token_rulings.py", "snapshot", root,
        "--audit-dir", a.audit)
    assert snap.returncode == 0, snap.stdout + snap.stderr
    worklist = json.loads(
        (a.audit / rulings.WORKLIST_PATH).read_text(encoding="utf-8"))
    a.write("_run/severity_token_rulings.json", json.dumps({
        "schema": rulings.RULINGS_SCHEMA,
        "cycle": "main",
        "b7_certification_sha256": worklist["b7_certification_sha256"],
        "rulings": [{
            "error_id": "E-0011", "token": "output:O-0121",
            "b7_verdict": "rejected", "ruling": "cap",
            "resulting_status": "confirmed", "resulting_severity": 2,
            "rationale": "borrowed tie omits the wage_pc witness site",
            "decision_identity": "operator-test",
        }],
    }, indent=2) + "\n")
    applied = rb.run_script(
        "severity_token_rulings.py", "apply", root,
        "--audit-dir", a.audit)
    assert applied.returncode == 0, applied.stdout + applied.stderr
    checked = rb.run_script(
        "severity_token_rulings.py", "check", root,
        "--audit-dir", a.audit)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    final = tokens._load_register_error_rows(a.audit)
    assert final["E-0011"]["Severity"] == "2"


def test_tier1_p28_test_oracle_notices_disabled_witness_binding(
        tmp_path, monkeypatch):
    root, a, manifest = _p28_fixture(tmp_path)

    def negative_oracle():
        _rejected, failures = rulings.validate_b7(root, a.audit, manifest)
        assert any(
            "mapped CV witness-site mismatch cannot be upheld" in failure
            for failure in failures
        )

    negative_oracle()
    monkeypatch.setattr(
        rulings, "_cv_witness_binding_failure",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(AssertionError):
        negative_oracle()


def _b5_relation_case(tmp_path, relation, *, mapped=True):
    ledger = rb.code_ledger_row(
        "E-0100", witness_ids="DUW-000000000001",
        evidence="DU-aaaaaaaaaaaa",
    )
    a, shard = rb.make_b5(
        tmp_path, "code", ledger_rows=[ledger], assigned_ids=["E-0100"])
    mappings = ([("DU-aaaaaaaaaaaa", "E-0100", "new_candidate")]
                if mapped else [])
    a.write("_run/detector_mapping.md", rb.detector_mapping_artifact(mappings))
    outcome = rb.witness_outcome_row(
        "DU", "DU-aaaaaaaaaaaa", "DUW-000000000001",
        relation=relation,
    )
    shard.write_text(
        rb.register_text("Recheck ledger", rb.CODE_LEDGER_COLS, [ledger])
        + "\n### Witness outcomes\n\n"
        + rb.md_table(rb.WITNESS_OUTCOME_COLS, [outcome])
        + "\n### Verification records\n\nNo verification records.\n",
        encoding="utf-8",
    )
    return a, shard


def test_s702_relation_lint_names_closed_list_and_no_longer_skips_unmapped(
        tmp_path):
    a, shard = _b5_relation_case(
        tmp_path / "mapped", "present_in", mapped=True)
    failed = rb.lint(a, "b5-code", shard)
    assert failed.returncode == 1
    assert "outside the closed code_errors list" in failed.stdout
    assert "never_fires" in failed.stdout and "unresolved" in failed.stdout
    a, shard = _b5_relation_case(
        tmp_path / "unmapped", "missing_version_operator", mapped=False)
    failed = rb.lint(a, "b5-code", shard)
    assert "outside the closed code_errors list" in failed.stdout


def test_s702_canonical_relation_is_quiet(tmp_path):
    a, shard = _b5_relation_case(tmp_path, "wrong_value", mapped=True)
    result = rb.lint(a, "b5-code", shard)
    assert result.returncode == 0, result.stdout + result.stderr


def test_tier1_s702_relation_test_oracle_notices_reopened_vocabulary(
        tmp_path, monkeypatch):
    a, shard = _b5_relation_case(tmp_path, "present_in", mapped=True)
    text = shard.read_text(encoding="utf-8")
    rows = [
        row for headers, table_rows, _line in lintmod.parse_tables(text)
        if headers == rb.CODE_LEDGER_COLS for row in table_rows
    ]

    def negative_oracle():
        state = lintmod.Lint()
        lintmod._validate_code_adjudication_shard(
            state, a.audit, shard, text, rows, {"E-0100"})
        assert any("closed code_errors list" in error for error in state.errors)

    negative_oracle()
    monkeypatch.setattr(
        lintmod, "_check_code_relation",
        lambda *_args, **_kwargs: True,
    )
    with pytest.raises(AssertionError):
        negative_oracle()


def test_replay_retry_records_both_attempts_and_scores_second_failure_as_is(
        tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    run_dir = tmp_path / "run"
    (sandbox / "audit/_code_error_recheck").mkdir(parents=True)
    run_dir.mkdir()
    scenario = {
        "stage": "code_b5", "route": "worker", "model": "fake",
        "effort": "high", "role_key": "code_b5_recheck_cluster",
        "owner": "audit/_code_error_recheck/k1.md",
        "promised_outputs": ["audit/_code_error_recheck/k1.md"],
        "downstream_exclusions": [],
    }
    monkeypatch.setattr(replay, "verify_declared_cut", lambda *_args: None)
    monkeypatch.setattr(
        replay, "_cut_sources", lambda *_args: {})
    monkeypatch.setattr(
        replay, "verify_deterministic_expectations",
        lambda *_args: "not-declared")
    monkeypatch.setattr(replay, "verify_no_downstream", lambda *_args: None)
    monkeypatch.setattr(
        replay, "render_worker_prompt",
        lambda *_args: "RCA-DISPATCH role=x stage=code_b5\n")
    monkeypatch.setattr(replay, "_claude_version", lambda: "fake")
    monkeypatch.setattr(replay, "_git_identity", lambda *_args: ("a" * 40, False))
    monkeypatch.setattr(replay, "_observed_effort", lambda *_args: "observed")
    attempts = []

    def fake_worker(*args):
        attempt = args[-1]
        attempts.append(attempt)
        return {"model": "fake"}, {
            "attempt": attempt, "argv": ["claude"], "cwd": str(sandbox),
            "returncode": 0, "prompt": f"worker-prompt-attempt-{attempt}.md",
            "prompt_sha256": "a" * 64,
            "response": f"worker-response-attempt-{attempt}.json",
        }

    monkeypatch.setattr(replay, "_run_worker_attempt", fake_worker)

    def failing_lint(_scenario, _sandbox, _run_dir, _skill_root, attempt):
        report = f"LINT FAIL attempt {attempt}\n"
        return SimpleNamespace(
            returncode=1, stdout=report, stderr=""), {
                "argv": ["lint"], "cwd": str(sandbox), "returncode": 1,
                "report": f"worker-lint-attempt-{attempt}.txt",
            }

    monkeypatch.setattr(replay, "_run_worker_shard_lint", failing_lint)
    monkeypatch.setattr(
        replay, "_promised_matches",
        lambda *_args: ["audit/_code_error_recheck/k1.md"])
    record = replay.execute_sandbox(
        tmp_path / "scenario.json", scenario, tmp_path, tmp_path, sandbox,
        run_dir, 1, rb.SKILL_DIR,
    )
    assert attempts == [1, 2]
    assert [
        item["returncode"] for item in record["route_commands"]
        if "report" in item
    ] == [1, 1]
    assert [
        item["attempt"] for item in record["route_commands"]
        if "prompt" in item
    ] == [1, 2]
    persisted = json.loads(
        (run_dir / "replay-record.json").read_text(encoding="utf-8"))
    assert len([
        item for item in persisted["route_commands"] if "prompt" in item
    ]) == 2
    # The record's top-level prompt sha must match the persisted final
    # prompt beside it (the retry prompt after a re-dispatch).
    assert record["prompt_sha256"] == hashlib.sha256(
        (run_dir / "worker-prompt.md").read_bytes()).hexdigest()
    assert (run_dir / "worker-prompt.md").read_text(
        encoding="utf-8") == (
        run_dir / "worker-prompt-attempt-2.md").read_text(encoding="utf-8")

    def negative_oracle():
        attempts.clear()
        record = replay.execute_sandbox(
            tmp_path / "scenario.json", scenario, tmp_path, tmp_path, sandbox,
            tmp_path / "reblinded-run", 2, rb.SKILL_DIR,
        )
        assert len([
            item for item in record["route_commands"] if "prompt" in item
        ]) == 2

    monkeypatch.setattr(
        replay, "_run_worker_shard_lint",
        lambda *_args: (
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            {
                "argv": ["lint"], "cwd": str(sandbox), "returncode": 0,
                "report": "worker-lint-attempt-1.txt",
            },
        ),
    )
    with pytest.raises(AssertionError):
        negative_oracle()


def test_tier1_s702_replay_driver_cli_redispatches_bad_worker_once(tmp_path):
    replay_root = tmp_path / "replay-cli"
    replay_root.mkdir()
    archive, archive_manifest, _manifest = replay_helpers._archive(replay_root)
    scenario_id = "opaque-u9c"
    data = replay_helpers._data_tree(
        replay_root, archive_manifest, scenario_id=scenario_id)
    base_root = tmp_path / "b5-base"
    a, shard = _b5_relation_case(base_root, "wrong_value", mapped=True)
    good_shard = tmp_path / "good-shard.md"
    bad_shard = tmp_path / "bad-shard.md"
    good_text = shard.read_text(encoding="utf-8")
    good_shard.write_text(good_text, encoding="utf-8")
    bad_shard.write_text(
        good_text.replace("wrong_value", "present_in"),
        encoding="utf-8",
    )
    shard.unlink()

    material = data / "scenario-material" / scenario_id
    cut = []
    for source in sorted(path for path in base_root.rglob("*") if path.is_file()):
        relative = source.relative_to(base_root).as_posix()
        authored = material / relative
        authored.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, authored)
        cut.append({
            "kind": "authored",
            "source": f"scenario-material/{scenario_id}/{relative}",
            "path": relative,
            "sha256": replay.sha256_file(authored),
            "classification": "conductor",
        })
    answer = data / "answers/sheet.json"
    answer.write_text("{}\n", encoding="utf-8")
    template = (
        rb.SKILL_DIR / "references/prompts/recheck-cluster-worker.md")
    skeleton = re.search(
        r"```md\n(.*?)\n```",
        template.read_text(encoding="utf-8"),
        re.DOTALL,
    ).group(1)
    slot_names = set(re.findall(
        r"\{([A-Z][A-Z0-9_]*)\}", skeleton))
    slots = {name: "synthetic" for name in slot_names}
    slots.update({
        "CONTRACT_PATH": "audit/_run/contracts/recheck_code.md",
        "RECHECK_PLAN_PATH": "audit/plans/code_error_recheck_plan.md",
        "SHARD_FILE": "audit/_code_error_recheck/k1.md",
        "REGISTER_FILES": "audit/code_error_register.md",
        "STREAM": "code-error",
        "ASSIGNED_IDS": "E-0100",
        "OFF_LIMITS": "none",
        "COMPUTE_BUDGET": "1",
    })
    scenario = {
        "format_version": 1, "stage": "code_b5", "route": "worker",
        "archive_manifest": "manifests/archive.json",
        "dependency_cut": cut,
        "promised_outputs": ["audit/_code_error_recheck/k1.md"],
        "downstream_exclusions": ["audit/_code_error_recheck/k1.md"],
        "deterministic_prefix": [],
        "prompt_template": "references/prompts/recheck-cluster-worker.md",
        "prompt_slots": slots, "model": "fake-u9c", "effort": "high",
        "role_key": "code_b5_recheck_cluster",
        "owner": "audit/_code_error_recheck/k1.md",
        "answer_sheet": "answers/sheet.json",
        "answer_sheet_sha256": replay.sha256_file(answer),
        "runs": 2,
    }
    scenario_path = data / "scenarios" / f"{scenario_id}.json"
    scenario_path.write_text(json.dumps(scenario, indent=2), encoding="utf-8")

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_claude = fake_bin / "claude"
    fake_claude.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "if '--version' in sys.argv:\n"
        "    print('fake-claude 1.0')\n"
        "    raise SystemExit(0)\n"
        "root = Path.cwd()\n"
        "counter = root / '.fake-claude-attempt'\n"
        "attempt = int(counter.read_text()) + 1 if counter.exists() else 1\n"
        "counter.write_text(str(attempt))\n"
        "source = Path(os.environ['FAKE_BAD_SHARD' if attempt == 1 "
        "else 'FAKE_GOOD_SHARD'])\n"
        "target = root / 'audit/_code_error_recheck/k1.md'\n"
        "target.parent.mkdir(parents=True, exist_ok=True)\n"
        "target.write_bytes(source.read_bytes())\n"
        "print(json.dumps({'model': 'fake-u9c'}))\n",
        encoding="utf-8",
    )
    fake_claude.chmod(0o755)
    sandbox = tmp_path / "replay-sandbox"
    run_dir = tmp_path / "replay-run"
    base_command = [
        sys.executable, str(rb.SCRIPTS_DIR / "replay_stage.py"),
        "--data-root", str(data), "--archive-root", str(archive),
    ]
    prepared = subprocess.run(
        base_command + [
            "prepare", str(scenario_path), "--sandbox", str(sandbox),
        ],
        capture_output=True, text=True,
    )
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr
    env = {
        **os.environ,
        "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
        "FAKE_BAD_SHARD": str(bad_shard),
        "FAKE_GOOD_SHARD": str(good_shard),
    }
    executed = subprocess.run(
        base_command + [
            "execute", str(scenario_path), "--sandbox", str(sandbox),
            "--run-dir", str(run_dir), "--run-index", "1",
        ],
        capture_output=True, text=True, env=env,
    )
    assert executed.returncode == 0, executed.stdout + executed.stderr
    record = json.loads(
        (run_dir / "replay-record.json").read_text(encoding="utf-8"))
    assert [
        item["returncode"] for item in record["route_commands"]
        if "report" in item
    ] == [1, 0]
    assert [
        item["attempt"] for item in record["route_commands"]
        if "prompt" in item
    ] == [1, 2]
    retry_prompt = (
        run_dir / "worker-prompt-attempt-2.md").read_text(encoding="utf-8")
    assert "Production shard-lint report" in retry_prompt
    assert "outside the closed code_errors list" in retry_prompt
    assert (
        sandbox / "audit/_code_error_recheck/k1.md"
    ).read_text(encoding="utf-8") == good_text
