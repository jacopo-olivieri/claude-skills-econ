"""U9a campaign, candidate-FP, and post-merge scoring contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import regbuild as rb


score = rb.load_script("score_replay")
mechanism = rb.load_script("mechanism_schema")

pytestmark = pytest.mark.u9

COMMIT = "a" * 40
BENCHMARK_SHA = "b" * 64
CANONICAL = mechanism.canonicalize_mechanism(
    "stale_or_wrong_path", "src/a.do", "unresolved", "-", "-",
    register="code_errors", anchor="src/a.do",
    projection=mechanism.EMPTY_PROJECTION,
).sidecar


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _campaign_tree(tmp_path):
    data = tmp_path / "data"
    scorecard = tmp_path / "scorecard.md"
    scorecard.write_text("accepted fixture re-score\n", encoding="utf-8")
    _write_json(data / "manifests/floods_expected.sha256.json", {
        "sha256": BENCHMARK_SHA,
    })
    registry = {}
    records = []
    for number in range(1, 9):
        label = f"S-70{number}"
        stem = f"stem-{number}"
        sheet_sha = f"{number}" * 64
        registry[stem] = label
        _write_json(data / f"scenarios/{stem}.json", {
            "format_version": 1,
            "answer_sheet_sha256": sheet_sha,
            "runs": 2,
        })
        spread_runs = []
        for run_index in (1, 2):
            report_path = data / f"results/{label}/score-run-{run_index:03d}.json"
            _write_json(report_path, {
                "scenario_id": stem,
                "run_index": run_index,
                "status": "score",
                "sheet_sha256": sheet_sha,
                "identity": {"code_commit": COMMIT, "code_dirty": False},
            })
            spread_runs.append({
                "run_index": run_index,
                "status": "score",
                "report": str(report_path),
            })
        spread_path = data / f"results/{label}/spread-report.json"
        _write_json(spread_path, {
            "format_version": 1,
            "scenario": label,
            "scenario_id": stem,
            "operator_adjudication": "accepted",
            "runs": spread_runs,
        })
        records.append({
            "scenario_label": label,
            "scenario_stem": stem,
            "answer_sheet_sha256": sheet_sha,
            "status": "accepted",
            "spread_report": str(spread_path.relative_to(data)),
            "code_commit": COMMIT,
            "adjudicated_on": "2026-07-21",
            "note": "",
        })
    _write_json(data / "registry.json", registry)
    campaign = {
        "campaign_commit": COMMIT,
        "mechanism_schema_version": mechanism.MECHANISM_SCHEMA_VERSION,
        "benchmark_sha256": BENCHMARK_SHA,
        "fixture_rescore": {
            "status": "accepted", "scorecard": str(scorecard), "note": "",
        },
        "scenarios": records,
    }
    _write_json(data / "acceptance/campaign.json", campaign)
    return data, campaign


def _save_campaign(data, campaign):
    _write_json(data / "acceptance/campaign.json", campaign)


def _campaign_cli(data):
    return rb.run_script("score_replay.py", "--data-root", data, "campaign")


def test_campaign_cli_accepts_complete_evidence_and_prints_one_page_summary(tmp_path):
    data, _campaign = _campaign_tree(tmp_path)
    result = _campaign_cli(data)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CAMPAIGN COMPLETE" in result.stdout
    assert all(f"S-70{number}: accepted; runs=001=score, 002=score" in result.stdout
               for number in range(1, 9))


def test_campaign_accepts_noted_adjudication_and_recorded_downgrade(tmp_path):
    data, campaign = _campaign_tree(tmp_path)
    noted = campaign["scenarios"][0]
    noted["status"] = "accepted_with_note"
    noted["note"] = "operator accepted the split spread with a recorded explanation"
    spread = json.loads((data / noted["spread_report"]).read_text(encoding="utf-8"))
    spread["operator_adjudication"] = "accepted_with_note"
    _write_json(data / noted["spread_report"], spread)
    downgraded = campaign["scenarios"][1]
    downgraded.update({
        "status": "downgraded", "spread_report": "", "code_commit": "",
        "note": "operator removed this scenario from the gate with a named reason",
    })
    _save_campaign(data, campaign)
    result = _campaign_cli(data)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "S-702: downgraded" in result.stdout


def test_tier1_campaign_cli_refuses_a_missing_frozen_scenario(tmp_path):
    data, campaign = _campaign_tree(tmp_path)
    campaign["scenarios"].pop()
    _save_campaign(data, campaign)
    result = _campaign_cli(data)
    assert result.returncode == 1
    assert "SCORE REFUSED: campaign must contain every frozen scenario exactly once" in result.stderr


def test_tier1_campaign_completeness_oracle_notices_disabled_frozen_member(
        tmp_path, monkeypatch):
    data, campaign = _campaign_tree(tmp_path)
    campaign["scenarios"].pop()
    _save_campaign(data, campaign)

    def negative_oracle():
        try:
            score.validate_campaign(data)
        except score.ScoreRefusal as exc:
            assert "every frozen scenario exactly once" in str(exc)
        else:
            assert False, "campaign completeness check did not refuse a missing member"

    negative_oracle()
    monkeypatch.setattr(score, "FROZEN_CAMPAIGN_LABELS", score.FROZEN_CAMPAIGN_LABELS[:-1])
    with pytest.raises(AssertionError):
        negative_oracle()


def test_tier1_campaign_cli_refuses_a_deleted_spread(tmp_path):
    data, campaign = _campaign_tree(tmp_path)
    (data / campaign["scenarios"][0]["spread_report"]).unlink()
    result = _campaign_cli(data)
    assert result.returncode == 1
    assert "SCORE REFUSED:" in result.stderr and "spread report S-701" in result.stderr


def test_tier1_campaign_cli_refuses_registry_accept_with_pending_spread(tmp_path):
    data, campaign = _campaign_tree(tmp_path)
    record = campaign["scenarios"][0]
    spread_path = data / record["spread_report"]
    spread = json.loads(spread_path.read_text(encoding="utf-8"))
    spread["operator_adjudication"] = "pending"
    _write_json(spread_path, spread)
    result = _campaign_cli(data)
    assert result.returncode == 1
    assert "disagrees with spread operator_adjudication 'pending'" in result.stderr


def test_campaign_refuses_unknown_spread_adjudication(tmp_path):
    data, campaign = _campaign_tree(tmp_path)
    record = campaign["scenarios"][0]
    spread_path = data / record["spread_report"]
    spread = json.loads(spread_path.read_text(encoding="utf-8"))
    spread["operator_adjudication"] = "approved"
    _write_json(spread_path, spread)
    result = _campaign_cli(data)
    assert result.returncode == 1
    assert "invalid operator_adjudication 'approved'" in result.stderr


@pytest.mark.parametrize("mutation, token", [
    (lambda report: report["identity"].update(code_commit="c" * 40), "wrong code_commit"),
    (lambda report: report["identity"].update(code_dirty=True), "not scored from a clean tree"),
])
def test_tier1_campaign_cli_refuses_wrong_commit_or_dirty_tree(
        tmp_path, mutation, token):
    data, campaign = _campaign_tree(tmp_path)
    spread = json.loads(
        (data / campaign["scenarios"][0]["spread_report"]).read_text(encoding="utf-8"))
    report_path = Path(spread["runs"][0]["report"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    mutation(report)
    _write_json(report_path, report)
    result = _campaign_cli(data)
    assert result.returncode == 1
    assert token in result.stderr


def test_tier1_campaign_cli_refuses_pending_fixture_rescore(tmp_path):
    data, campaign = _campaign_tree(tmp_path)
    campaign["campaign_commit"] = ""
    campaign["fixture_rescore"].update(status="pending", scorecard="")
    _save_campaign(data, campaign)
    result = _campaign_cli(data)
    assert result.returncode == 1
    assert "fixture_rescore status must be accepted" in result.stderr


def test_campaign_empty_commit_is_allowed_only_while_pending(tmp_path):
    data, campaign = _campaign_tree(tmp_path)
    campaign["campaign_commit"] = ""
    _save_campaign(data, campaign)
    result = _campaign_cli(data)
    assert result.returncode == 1
    assert "campaign_commit must be a 40-character" in result.stderr


@pytest.mark.parametrize("index,field,value,token", [
    (0, "scenario_label", "S-799", "every frozen scenario exactly once"),
    (1, "scenario_stem", "stem-1", "duplicate scenario_stem"),
])
def test_campaign_identity_joins_refuse_mismatches(
        tmp_path, index, field, value, token):
    data, campaign = _campaign_tree(tmp_path)
    campaign["scenarios"][index][field] = value
    _save_campaign(data, campaign)
    result = _campaign_cli(data)
    assert result.returncode == 1
    assert token in result.stderr


@pytest.mark.parametrize("location", ["scenario", "report"])
def test_campaign_sheet_digest_is_bound_to_scenario_and_score_reports(tmp_path, location):
    data, campaign = _campaign_tree(tmp_path)
    record = campaign["scenarios"][0]
    if location == "scenario":
        scenario_path = data / f"scenarios/{record['scenario_stem']}.json"
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        scenario["answer_sheet_sha256"] = "f" * 64
        _write_json(scenario_path, scenario)
    else:
        spread = json.loads((data / record["spread_report"]).read_text(encoding="utf-8"))
        report_path = Path(spread["runs"][0]["report"])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["sheet_sha256"] = "f" * 64
        _write_json(report_path, report)
    result = _campaign_cli(data)
    assert result.returncode == 1
    assert "sheet" in result.stderr


def test_campaign_refuses_spread_identity_and_run_count_mismatches(tmp_path):
    data, campaign = _campaign_tree(tmp_path)
    record = campaign["scenarios"][0]
    spread_path = data / record["spread_report"]
    spread = json.loads(spread_path.read_text(encoding="utf-8"))
    spread["scenario_id"] = "other-stem"
    _write_json(spread_path, spread)
    result = _campaign_cli(data)
    assert result.returncode == 1 and "identity disagrees" in result.stderr
    spread["scenario_id"] = record["scenario_stem"]
    spread["runs"].pop()
    _write_json(spread_path, spread)
    result = _campaign_cli(data)
    assert result.returncode == 1 and "expected 2 runs, found 1" in result.stderr


@pytest.mark.parametrize("status,note,token", [
    ("pending", "", "is pending"),
    ("rejected", "operator rejection", "is rejected"),
    ("accepted_with_note", "", "requires a note"),
    ("accepted", "unexpected", "requires an empty note"),
])
def test_campaign_status_and_note_contract_refuses_incomplete_records(
        tmp_path, status, note, token):
    data, campaign = _campaign_tree(tmp_path)
    campaign["scenarios"][0].update(status=status, note=note)
    _save_campaign(data, campaign)
    result = _campaign_cli(data)
    assert result.returncode == 1
    assert token in result.stderr


@pytest.mark.parametrize("field,value,token", [
    ("mechanism_schema_version", "9.9.9", "mechanism_schema_version mismatch"),
    ("benchmark_sha256", "f" * 64, "benchmark_sha256"),
])
def test_campaign_schema_and_benchmark_anchors_refuse_drift(
        tmp_path, field, value, token):
    data, campaign = _campaign_tree(tmp_path)
    campaign[field] = value
    _save_campaign(data, campaign)
    result = _campaign_cli(data)
    assert result.returncode == 1
    assert token in result.stderr


def test_campaign_scorecard_must_be_absolute_and_exist(tmp_path):
    data, campaign = _campaign_tree(tmp_path)
    campaign["fixture_rescore"]["scorecard"] = "relative.md"
    _save_campaign(data, campaign)
    result = _campaign_cli(data)
    assert result.returncode == 1 and "absolute path" in result.stderr
    campaign["fixture_rescore"]["scorecard"] = str(tmp_path / "missing.md")
    _save_campaign(data, campaign)
    result = _campaign_cli(data)
    assert result.returncode == 1 and "does not exist" in result.stderr


def _claim_candidate():
    return {
        "id": "C-7201", "register": "claims", "path": "paper.md",
        "mechanism": "claim-mechanism", "status": "inconsistent",
        "severity": 4, "text": "target assertion",
    }


def test_obligation_matched_claim_is_subtracted_but_nonrow_routes_are_ignored():
    sheet = {"false_positive_ceiling": 0, "expected_candidates": []}
    recovery = [{"key": "target", "status": "score"}]
    row = _claim_candidate()
    matched = {("claim_row", "C-7201"), ("covered_x", "X-0001"),
               ("filed_h", "H-0001")}
    result = score.score_candidates(sheet, [row], recovery, matched)
    assert result["status"] == "score"
    assert result["false_positive_ids"] == []
    control = score.score_candidates(
        sheet, [row], recovery, {("covered_x", "C-7201"), ("filed_h", "C-7201")})
    assert control["status"] == "red"
    assert control["false_positive_ids"] == ["C-7201"]


def test_tier1_fp_projection_test_oracle_notices_literal_tuple_passthrough(monkeypatch):
    sheet = {"false_positive_ceiling": 0, "expected_candidates": []}
    row = _claim_candidate()

    def negative_oracle():
        result = score.score_candidates(
            sheet, [row], [{"key": "target", "status": "score"}],
            {("claim_row", "C-7201")})
        assert result["false_positive_ids"] == []
        assert result["status"] == "score"

    negative_oracle()
    monkeypatch.setattr(score, "_project_obligation_matches", lambda matched: set(matched))
    with pytest.raises(AssertionError):
        negative_oracle()


def _candidate_sheet(status_family="candidate", expected_status=None):
    expected = {
        "key": "target", "register": "code_errors", "path": "src/a.do",
        "mechanism": CANONICAL, "status_family": status_family,
        "benchmark_severity": 2, "anchors": ["anchor"],
    }
    if expected_status is not None:
        expected["expected_status"] = expected_status
    return {"false_positive_ceiling": 0, "expected_candidates": [expected]}


def _candidate_row(status="candidate"):
    return {
        "id": "E-0001", "register": "code_errors", "path": "src/a.do",
        "mechanism": CANONICAL, "status": status, "severity": 2,
        "text": "the anchor is present",
    }


def test_post_merge_status_family_scores_exact_status_with_missing_and_wrong_controls():
    sheet = _candidate_sheet("post_merge", "confirmed")
    assert score.score_candidates(sheet, [_candidate_row("confirmed")])["status"] == "score"
    wrong = score.score_candidates(sheet, [_candidate_row("confirmation_needed")])
    assert wrong["status"] == "red"
    assert "expected post-merge status" in wrong["recoveries"][0]["problems"][0]
    assert score.score_candidates(sheet, [])["status"] == "red"


def test_post_merge_extension_is_opt_in_and_ordinary_candidate_bytes_are_unchanged(tmp_path):
    value = {
        "format_version": 1,
        "disposition_complete": True,
        "false_positive_ceiling": 0,
        "output_contract": {
            "candidate_paths": ["audit/out.md"], "scenario_files": ["src/a.do"],
        },
        **_candidate_sheet("post_merge", "confirmed"),
    }
    path = _write_json(tmp_path / "sheet.json", value)
    with pytest.raises(score.ScoreFormatError, match="status_family must be candidate"):
        score.load_sheet(path, scoring_mode="candidate")
    loaded = score.load_sheet(
        path, scoring_mode="candidate", status_family="post_merge")
    assert loaded["expected_candidates"][0]["expected_status"] == "confirmed"

    ordinary = score.score_candidates(
        _candidate_sheet(), [_candidate_row()])
    assert ordinary == {
        "status": "score",
        "recoveries": [{
            "key": "target", "candidate_identity": ["src/a.do", CANONICAL],
            "mechanism_outcome": "hit", "status": "score", "problems": [],
        }],
        "false_positive_ids": [], "false_positive_ceiling": 0,
        "false_positive_ok": True,
    }


def test_fp_subtraction_drills_through_production_score_cli(tmp_path):
    data = tmp_path / "data"
    stem = "claim-fp"
    sheet_path = data / "answers/sheet.json"
    paper = "A benchmark-neutral target assertion."
    sheet = {
        "format_version": 1,
        "mechanism_schema_version": mechanism.MECHANISM_SCHEMA_VERSION,
        "disposition_complete": True,
        "false_positive_ceiling": 0,
        "output_contract": {
            "candidate_paths": ["audit/shard.md"],
            "obligation_paths": ["audit/shard.md"],
            "scenario_files": ["paper.md"],
        },
        "expected_candidates": [],
        "expected_claim_obligations": [{
            "key": "target", "target_anchor": "paper.md:1", "target_quote": paper,
        }],
    }
    _write_json(sheet_path, sheet)
    sheet_sha = hashlib.sha256(sheet_path.read_bytes()).hexdigest()
    scenario_path = data / f"scenarios/{stem}.json"
    _write_json(scenario_path, {
        "format_version": 1, "stage": "claims_b2", "route": "deterministic_stage",
        "scoring_mode": "candidate", "promised_outputs": ["audit/shard.md"],
        "answer_sheet": "answers/sheet.json", "answer_sheet_sha256": sheet_sha,
        "runs": 1,
    })
    _write_json(data / "registry.json", {stem: "S-701"})
    run_dir = data / "results/S-701/run-001"
    sandbox = run_dir / "sandbox"
    (sandbox / "audit").mkdir(parents=True)
    (sandbox / "paper.md").write_text(paper + "\n", encoding="utf-8")
    _write_json(sandbox / "audit/_run/manifest.json", {
        "paper_source_set": [{
            "source_path": "paper.md", "audit_path": "paper.md",
            "source_sha256": "unused", "audit_sha256": "unused",
        }],
    })
    claim = rb.claims_row(
        "C-7201", quote=paper, text=paper, source="`paper.md`",
        status="inconsistent", severity="4", issue="target survives")
    (sandbox / "audit/shard.md").write_text(
        rb.register_text("Claims", rb.CLAIMS_COLS, [claim]), encoding="utf-8")
    _write_json(run_dir / "replay-record.json", {
        "format_version": 1, "scenario_id": stem, "stage": "claims_b2",
        "route": "deterministic_stage", "run_index": 1,
        "timestamp": "2026-07-21T00:00:00+00:00",
        "identity": {
            "model_requested": "not-applicable", "model_reported": "not-applicable",
            "cli_version": "not-applicable", "code_commit": COMMIT,
            "code_dirty": True, "requested_effort": "not-applicable",
            "observed_effort": "not-applicable",
            "mechanism_schema_version": mechanism.MECHANISM_SCHEMA_VERSION,
        },
        "promised_outputs_found": ["audit/shard.md"],
    })
    result = rb.run_script(
        "score_replay.py", "--data-root", data, "score", scenario_path, run_dir)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((data / "results/S-701/score-run-001.json").read_text())
    assert report["status"] == "score" and report["false_positive_ids"] == []


def test_campaign_refuses_stem_that_disagrees_with_scenario_registry(tmp_path):
    data, _campaign = _campaign_tree(tmp_path)
    registry = json.loads((data / "registry.json").read_text(encoding="utf-8"))
    registry["stem-1"] = "S-799"
    _write_json(data / "registry.json", registry)
    result = _campaign_cli(data)
    assert result.returncode == 1
    assert "disagrees with scenario registry" in result.stderr


def test_status_family_is_refused_outside_candidate_scoring_mode(tmp_path):
    data = tmp_path / "data"
    sheet_path = _write_json(data / "answers/sheet.json", {"format_version": 1})
    scenario_path = _write_json(data / "scenarios/plain.json", {
        "format_version": 1, "scoring_mode": "b5",
        "status_family": "post_merge", "answer_sheet": "answers/sheet.json",
        "answer_sheet_sha256": hashlib.sha256(sheet_path.read_bytes()).hexdigest(),
    })
    result = rb.run_script(
        "score_replay.py", "--data-root", data, "score",
        scenario_path, data / "results/none/run-001")
    # Scenario-configuration defects are the SCORE RED class (exit 2), like
    # the neighboring scoring_mode vocabulary check.
    assert result.returncode == 2
    assert "SCORE RED: status_family is valid only for candidate" in result.stderr
