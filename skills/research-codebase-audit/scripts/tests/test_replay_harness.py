"""U5 trimmed replay driver, b5 scorer, and Tier-1 test oracles."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

import regbuild as rb


replay = rb.load_script("replay_stage")
score = rb.load_script("score_replay")
mechanism = rb.load_script("mechanism_schema")
emitter = rb.load_script("emit_definition_use_bundles")

pytestmark = pytest.mark.u5

REPLAY_CLI = rb.SCRIPTS_DIR / "replay_stage.py"
SCORE_CLI = rb.SCRIPTS_DIR / "score_replay.py"
SOURCE = "DU-aaaaaaaaaaaa"
WITNESS = "DUW-111111111111"
SOURCE_2 = "DU-bbbbbbbbbbbb"
WITNESS_2 = "DUW-222222222222"
ANCHOR = "src/analyse.do:12"
MECH_COLS = (
    "conditional_guard", "flag", "never_fires", "[flag == 1]",
    "flag == 1 & x > 0",
)
CANONICAL = mechanism.canonicalize_mechanism(
    *MECH_COLS, register="code_errors", anchor=ANCHOR).sidecar


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _archive(tmp_path, files=None):
    root = tmp_path / "archive"
    root.mkdir()
    files = files or {"src/input.do": "display 1\n"}
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    # Exercise every frozen-archive mode class in the positive fixture.
    directories = sorted((path for path in root.rglob("*") if path.is_dir()),
                         key=lambda path: len(path.parts), reverse=True)
    regular = sorted(path for path in root.rglob("*") if path.is_file())
    for index, path in enumerate(regular):
        path.chmod(0o400 if index % 2 == 0 else 0o444)
    for index, path in enumerate(directories):
        path.chmod(0o500 if index % 2 == 0 else 0o555)
    entries, total = [], 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        mode = f"{stat.S_IMODE(path.stat().st_mode):04o}"
        if path.is_dir():
            entries.append({"path": relative, "mode": mode, "type": "dir"})
        else:
            size = path.stat().st_size
            total += size
            entries.append({
                "path": relative, "mode": mode, "type": "file", "size": size,
                "sha256": _sha(path),
            })
    manifest = {
        "manifest_version": 1, "hash_algorithm": "sha256",
        "entry_count": len(entries), "total_file_bytes": total, "entries": entries,
    }
    manifest_path = tmp_path / "tree-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return root, manifest_path, manifest


def _restore_owner_write(root):
    for path in sorted(Path(root).rglob("*"), key=lambda item: len(item.parts)):
        path.chmod(stat.S_IMODE(path.stat().st_mode) | stat.S_IWUSR | (stat.S_IXUSR if path.is_dir() else 0))


def _data_tree(tmp_path, archive_manifest, *, scenario_id="opaque-a1"):
    data = tmp_path / "data"
    (data / "manifests").mkdir(parents=True)
    (data / "scenarios").mkdir()
    (data / "answers").mkdir()
    (data / "results").mkdir()
    (data / "scenario-material" / scenario_id).mkdir(parents=True)
    copied_manifest = data / "manifests" / "archive.json"
    copied_manifest.write_bytes(Path(archive_manifest).read_bytes())
    (data / "registry.json").write_text(
        json.dumps({scenario_id: "S-701"}), encoding="utf-8")
    return data


def _scenario(data, archive, *, scenario_id="opaque-a1", route="deterministic_stage",
              files=("src/input.do",), exclusions=("audit/out.md",),
              promised=("audit/out.md",), authored=()):
    cut = [{"kind": "archive", "path": relative,
            "sha256": _sha(archive / relative)} for relative in files]
    cut.extend(authored)
    answer_path = data / "answers/sheet.json"
    if not answer_path.exists():
        answer_path.write_text("{}\n", encoding="utf-8")
    value = {
        "format_version": 1, "stage": "code_b3d", "route": route,
        "archive_manifest": "manifests/archive.json", "dependency_cut": cut,
        "promised_outputs": list(promised),
        "downstream_exclusions": list(exclusions),
        "deterministic_prefix": [], "stage_commands": [],
        "certifier_command": {"argv": [sys.executable, "-c", "pass"]},
        "answer_sheet": "answers/sheet.json", "answer_sheet_sha256": _sha(answer_path),
        "runs": 1,
    }
    if route in {"worker", "merge"}:
        value.update({"runs": 2, "model": "claude-test", "effort": "high",
                      "role_key": "code_b5_recheck_cluster"})
    path = data / "scenarios" / f"{scenario_id}.json"
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    return path, value


def _pin_sheet(scenario_path, scenario, sheet_path):
    scenario["answer_sheet_sha256"] = _sha(sheet_path)
    Path(scenario_path).write_text(json.dumps(scenario, indent=2), encoding="utf-8")


def _ledger_row(*, witness_ids=WITNESS, disposition="confirmed_error",
                severity="4", evidence=ANCHOR, output_id="E-7000"):
    values = {
        "ID": output_id, "Current Status": "candidate", "Current Severity": "4",
        "Evidence Checked": evidence, "Evidence Level": "static_source_verified",
        "Verdict": disposition, "Proposed Register Change": "keep",
        "Pipeline/Output Impact": "wrong values survive", "Proposed Note": "guard excludes repair",
        "Proposed Status": "confirmed", "Proposed Severity": severity,
        "Accepted Error Type": "sample_filter_or_flag_error",
        "Accepted Mechanism": CANONICAL, "Outcome Witness IDs": witness_ids,
        "Duplicate Target": "—", "Proposed Field Patches": "—",
        "Verification Record IDs": "—",
    }
    return [values[column] for column in rb.CODE_LEDGER_COLS]


def _witness_row(*, source=SOURCE, witness=WITNESS, disposition="confirmed_error",
                 severity="4", mech_cols=MECH_COLS):
    return [source.startswith("DU-") and "DU" or "MF", source, witness,
            disposition, *mech_cols, severity, "—"]


def _sheet(expected=None, *, ceiling=0):
    expected = expected or [{
        "key": "site-a", "output_id": "E-7000", "channel": "DU",
        "source_id": SOURCE, "witness_id": WITNESS,
        "disposition": "confirmed_error", "mechanism": CANONICAL,
        "severity_floor": 4, "anchors": [ANCHOR],
    }]
    return {
        "format_version": 1,
        "mechanism_schema_version": mechanism.MECHANISM_SCHEMA_VERSION,
        "disposition_complete": True, "false_positive_ceiling": ceiling,
        "output_contract": {
            "ledger_paths": ["audit/shard.md"],
            "witness_paths": ["audit/shard.md"],
        },
        "expected_recoveries": expected,
    }


def _write_output(run_dir, ledgers=None, witnesses=None):
    sandbox = Path(run_dir) / "sandbox"
    (sandbox / "audit").mkdir(parents=True)
    text = rb.register_text("Recheck ledger", rb.CODE_LEDGER_COLS,
                            ledgers or [_ledger_row()])
    text += "\n### Witness outcomes\n\n" + rb.md_table(
        rb.WITNESS_OUTCOME_COLS, witnesses or [_witness_row()])
    (sandbox / "audit" / "shard.md").write_text(text, encoding="utf-8")
    return sandbox


def _record(run_dir, scenario_id="opaque-a1", *, version=None, identity_patch=None):
    identity = {
        "model_requested": "not-applicable", "model_reported": "not-applicable",
        "cli_version": "not-applicable", "code_commit": "a" * 40,
        "code_dirty": True, "requested_effort": "not-applicable",
        "observed_effort": "not-applicable",
        "mechanism_schema_version": version or mechanism.MECHANISM_SCHEMA_VERSION,
    }
    identity.update(identity_patch or {})
    value = {
        "format_version": 1, "scenario_id": scenario_id, "stage": "code_b3d",
        "route": "deterministic_stage", "run_index": 1,
        "timestamp": "2026-07-18T00:00:00+00:00", "identity": identity,
        "promised_outputs_found": ["audit/shard.md"],
    }
    (Path(run_dir) / "replay-record.json").write_text(
        json.dumps(value, indent=2), encoding="utf-8")
    return value


def _score_case(tmp_path, *, sheet=None, ledgers=None, witnesses=None,
                record_patch=None, version=None):
    scenario_path = tmp_path / "opaque-a1.json"
    scenario = {
        "format_version": 1, "stage": "code_b3d", "route": "deterministic_stage",
        "promised_outputs": ["audit/shard.md"], "answer_sheet": "answers/sheet.json",
        "runs": 1,
    }
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
    sheet_path = tmp_path / "sheet.json"
    sheet_value = sheet or _sheet()
    sheet_path.write_text(json.dumps(sheet_value), encoding="utf-8")
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _write_output(run_dir, ledgers, witnesses)
    record = _record(run_dir, version=version, identity_patch=record_patch)
    return scenario_path, scenario, sheet_path, sheet_value, run_dir, record


def test_archive_verifier_accepts_all_four_recorded_mode_classes(tmp_path):
    root, manifest_path, manifest = _archive(
        tmp_path, {"a/one.do": "1\n", "b/two.do": "2\n"})
    # Ensure the positive fixture actually contains the four promised classes.
    modes = {(entry["type"], entry["mode"]) for entry in manifest["entries"]}
    assert {("file", "0400"), ("file", "0444"),
            ("dir", "0500"), ("dir", "0555")} <= modes
    assert replay.verify_archive(root, manifest_path)["entry_count"] == len(manifest["entries"])
    _restore_owner_write(root)


@pytest.mark.parametrize("mutation, token", [
    (lambda m: m.update(entry_count=m["entry_count"] + 1), "entry_count"),
    (lambda m: m.update(hash_algorithm="md5"), "hash_algorithm"),
    (lambda m: (m["entries"].append(deepcopy(m["entries"][0])),
                m.update(entry_count=m["entry_count"] + 1)), "duplicate path"),
    (lambda m: m.update(total_file_bytes=m["total_file_bytes"] + 1), "total_file_bytes"),
])
def test_archive_manifest_metadata_negatives(tmp_path, mutation, token):
    root, manifest_path, manifest = _archive(tmp_path)
    mutation(manifest)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(replay.ReplayError, match=token):
        replay.verify_archive(root, manifest_path)
    _restore_owner_write(root)


@pytest.mark.parametrize("kind, mode, token", [
    ("file", "0644", "0400, 0444, 0500, or 0555"),
    ("dir", "0755", "0500 or 0555"),
])
def test_archive_manifest_rejects_unfrozen_mode(tmp_path, kind, mode, token):
    root, manifest_path, manifest = _archive(tmp_path)
    next(entry for entry in manifest["entries"] if entry["type"] == kind)["mode"] = mode
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(replay.ReplayError, match=token):
        replay.verify_archive(root, manifest_path)
    _restore_owner_write(root)


def test_archive_root_must_exist_and_be_directory(tmp_path):
    root, manifest_path, _manifest = _archive(tmp_path)
    with pytest.raises(replay.ReplayError, match="does not exist"):
        replay.verify_archive(tmp_path / "absent", manifest_path)
    ordinary_file = tmp_path / "ordinary"
    ordinary_file.write_text("x", encoding="utf-8")
    with pytest.raises(replay.ReplayError, match="not a directory"):
        replay.verify_archive(ordinary_file, manifest_path)
    _restore_owner_write(root)


def test_archive_verifier_surfaces_directory_walk_errors(tmp_path, monkeypatch):
    root, manifest_path, _manifest = _archive(tmp_path)
    real_scandir = replay.os.scandir
    monkeypatch.setattr(replay.os, "scandir", lambda path: (_ for _ in ()).throw(
        PermissionError("walk denied")) if Path(path) == root else real_scandir(path))
    with pytest.raises(replay.ReplayError, match="walk failed.*walk denied"):
        replay.verify_archive(root, manifest_path)
    _restore_owner_write(root)


def test_archive_verifier_detects_byte_and_path_drift(tmp_path):
    root, manifest_path, _manifest = _archive(tmp_path)
    path = root / "src/input.do"
    path.chmod(0o600)
    path.write_text("changed\n", encoding="utf-8")
    path.chmod(0o400)
    with pytest.raises(replay.ReplayError, match="entry differs"):
        replay.verify_archive(root, manifest_path)
    _restore_owner_write(root)


def test_cut_isolation_refuses_downstream_and_accepts_clean_cut(tmp_path):
    archive, manifest_path, _ = _archive(
        tmp_path, {"src/input.do": "x\n", "audit/out.md": "copied answer\n"})
    data = _data_tree(tmp_path, manifest_path)
    clean_path, clean = _scenario(data, archive)
    replay.prepare_sandbox(clean, data, archive, tmp_path / "clean-sandbox")
    bad_path, bad = _scenario(data, archive, scenario_id="opaque-bad",
                              files=("src/input.do", "audit/out.md"))
    with pytest.raises(replay.ReplayError, match="refuses downstream artifact"):
        replay.prepare_sandbox(bad, data, archive, tmp_path / "bad-sandbox")
    assert clean_path.is_file() and bad_path.is_file()
    _restore_owner_write(archive)


def test_cut_isolation_refuses_post_materialization_plant(tmp_path):
    archive, manifest_path, _ = _archive(tmp_path)
    data = _data_tree(tmp_path, manifest_path)
    _path, scenario = _scenario(data, archive)
    sandbox = tmp_path / "sandbox"
    destinations = replay.prepare_sandbox(scenario, data, archive, sandbox)
    planted = sandbox / "audit/out.md"
    planted.parent.mkdir(parents=True)
    planted.write_text("precomputed recovery\n", encoding="utf-8")
    with pytest.raises(replay.ReplayError, match="does not exactly match.*extra"):
        replay.verify_declared_cut(sandbox, destinations)
    _restore_owner_write(archive)


def test_cut_isolation_refuses_parent_and_symlink_escape(tmp_path):
    archive, manifest_path, _ = _archive(tmp_path)
    data = _data_tree(tmp_path, manifest_path)
    _path, scenario = _scenario(data, archive)
    scenario["dependency_cut"][0]["path"] = "../outside.do"
    with pytest.raises(replay.ReplayError, match="escapes its root"):
        replay.prepare_sandbox(scenario, data, archive, tmp_path / "sandbox")
    scenario["dependency_cut"][0]["path"] = "link.do"
    outside = tmp_path / "outside.do"
    outside.write_text("outside\n", encoding="utf-8")
    (archive / "link.do").symlink_to(outside)
    scenario["dependency_cut"][0]["sha256"] = "0" * 64
    with pytest.raises(replay.ReplayError, match="escapes archive root"):
        replay.prepare_sandbox(scenario, data, archive, tmp_path / "sandbox2")
    (archive / "link.do").unlink()
    _restore_owner_write(archive)


def test_authored_cut_allowlists_scenario_material_only(tmp_path):
    archive, manifest_path, _ = _archive(tmp_path)
    data = _data_tree(tmp_path, manifest_path)
    answer = data / "answers/sheet.json"
    answer.write_text("{}", encoding="utf-8")
    entry = {"kind": "authored", "source": "answers/sheet.json",
             "path": "audit/_run/manifest.json", "sha256": _sha(answer),
             "classification": "conductor"}
    _path, scenario = _scenario(data, archive, authored=(entry,))
    # Anything outside scenario-material/ is refused: answer sheets, the
    # S-7## legend registry, and prior results alike.
    for source in ("answers/sheet.json", "registry.json", "results/old-report.json"):
        candidate = data / source
        candidate.parent.mkdir(parents=True, exist_ok=True)
        if not candidate.exists():
            candidate.write_text("{}", encoding="utf-8")
        entry["source"] = source
        entry["sha256"] = _sha(candidate)
        with pytest.raises(replay.ReplayError, match="must live under scenario-material/"):
            replay.prepare_sandbox(scenario, data, archive, tmp_path / "sandbox")
    entry["source"] = "scenario-material/opaque-a1/input.json"
    authored = data / entry["source"]
    authored.write_text("{}", encoding="utf-8")
    entry["sha256"] = _sha(authored)
    entry["classification"] = "answer"
    with pytest.raises(replay.ReplayError, match="classified conductor"):
        replay.prepare_sandbox(scenario, data, archive, tmp_path / "sandbox2")
    entry["classification"] = "conductor"
    replay.prepare_sandbox(scenario, data, archive, tmp_path / "sandbox3")
    _restore_owner_write(archive)


def test_scenario_stage_must_be_known_stage_key(tmp_path):
    path = tmp_path / "scenario.json"
    value = {"format_version": 1, "stage": "code_b5x", "route": "deterministic_stage",
             "dependency_cut": [{}], "promised_outputs": ["out.md"],
             "downstream_exclusions": ["out.md"], "runs": 1}
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(replay.ReplayError, match="stage key certify_stage.py knows"):
        replay.load_scenario(path)
    value["stage"] = "code_b5"
    path.write_text(json.dumps(value), encoding="utf-8")
    assert replay.load_scenario(path)[1]["stage"] == "code_b5"


def test_rendered_prompt_is_persisted_with_digest(tmp_path):
    run_dir = tmp_path / "run-001"
    digest = replay._persist_prompt(run_dir, "RCA-DISPATCH role=r stage=s\n\nbody\n")
    persisted = (run_dir / "worker-prompt.md").read_text(encoding="utf-8")
    assert persisted == "RCA-DISPATCH role=r stage=s\n\nbody\n"
    assert digest == hashlib.sha256(persisted.encode("utf-8")).hexdigest()


def test_tier1_cut_test_oracle_notices_broken_exclusion_match(tmp_path, monkeypatch):
    archive, manifest_path, _ = _archive(
        tmp_path, {"src/input.do": "x\n", "audit/out.md": "copied\n"})
    data = _data_tree(tmp_path, manifest_path)
    _path, scenario = _scenario(data, archive, files=("audit/out.md",))

    def negative_oracle():
        with pytest.raises(replay.ReplayError, match="downstream"):
            replay.prepare_sandbox(scenario, data, archive, tmp_path / "sandbox")

    negative_oracle()
    monkeypatch.setattr(replay, "_matches", lambda _path, _patterns: False)
    with pytest.raises(pytest.fail.Exception):
        negative_oracle()
    _restore_owner_write(archive)


def test_portable_cli_prepares_with_both_roots_relocated(tmp_path):
    archive, manifest_path, _ = _archive(tmp_path)
    data = _data_tree(tmp_path, manifest_path)
    scenario_path, _scenario_value = _scenario(data, archive)
    result = subprocess.run([
        sys.executable, str(REPLAY_CLI), "--data-root", str(data),
        "--archive-root", str(archive), "prepare", str(scenario_path),
        "--sandbox", str(tmp_path / "relocated-sandbox"),
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "REPLAY OK: sandbox prepared" in result.stdout
    _restore_owner_write(archive)


def test_scenario_routes_and_run_counts_are_closed(tmp_path):
    path = tmp_path / "scenario.json"
    base = {"format_version": 1, "stage": "code_b5", "dependency_cut": [{}],
            "promised_outputs": ["out.md"], "downstream_exclusions": ["out.md"]}
    for route, runs, accepted in [
        ("deterministic_stage", 1, True), ("worker", 2, True), ("merge", 3, True),
        ("worker", 1, False), ("full_run", 1, False),
    ]:
        value = {**base, "route": route, "runs": runs}
        path.write_text(json.dumps(value), encoding="utf-8")
        if accepted:
            assert replay.load_scenario(path)[1]["route"] == route
        else:
            with pytest.raises(replay.ReplayError):
                replay.load_scenario(path)


def test_prompt_renderer_fills_exact_production_slot_contract(tmp_path):
    template = tmp_path / "skill/references/prompts/recheck.md"
    template.parent.mkdir(parents=True)
    template.write_text("# slots\n\n```md\nRead {FILE}. Write {OUTPUT}.\n```\n", encoding="utf-8")
    scenario = {"prompt_template": "references/prompts/recheck.md",
                "prompt_slots": {"FILE": "src/a.do", "OUTPUT": "audit/shard.md"},
                "role_key": "code_b5_recheck_cluster", "stage": "code_b5"}
    rendered = replay.render_worker_prompt(scenario, template.parents[2])
    assert rendered.endswith("Read src/a.do. Write audit/shard.md.\n")
    assert rendered.startswith("RCA-DISPATCH role=code_b5_recheck_cluster stage=code_b5")
    scenario["prompt_slots"].pop("OUTPUT")
    with pytest.raises(replay.ReplayError, match="exactly fill"):
        replay.render_worker_prompt(scenario, template.parents[2])


def test_deterministic_expectations_require_exact_emission_identity_and_anchor(tmp_path):
    sandbox = tmp_path / "sandbox"
    source = sandbox / "do/probe.do"
    source.parent.mkdir(parents=True)
    source.write_text(
        "gen flag = 0\nreplace flag = 1 if x > 0\ndrop if flag == 1 & y > 0\n",
        encoding="utf-8",
    )
    audit = sandbox / "audit/_run"
    audit.mkdir(parents=True)
    results = emitter.scan_package(sandbox)
    artifact_text = emitter.render_artifact(results)
    (audit / "definition_use_bundles.md").write_text(artifact_text, encoding="utf-8")
    row = replay.definition_use.parse_artifact(artifact_text).standard_rows[0]
    mapping = {
        "Channel": "DU", "Source ID": row["Bundle ID"],
        "Witness ID": row["Witness ID"], "Error ID": "E-7000",
        "Mapping Kind": "new_candidate", "Site Anchor": row["Consumer Site"],
    }
    (audit / "detector_mapping.md").write_text(
        replay.detector_mapping.render_mapping(
            "E-7000–E-7099", {"DU": [mapping], "MF": [], "CV": []}),
        encoding="utf-8",
    )
    scenario = {"deterministic_expectations": {
        "bundle_path": "audit/_run/definition_use_bundles.md",
        "mapping_path": "audit/_run/detector_mapping.md",
        "detector_rows": [{
            "channel": "DU", "source_id": row["Bundle ID"],
            "witness_id": row["Witness ID"], "site_anchor": row["Consumer Site"],
        }],
    }}
    assert replay.verify_deterministic_expectations(scenario, sandbox)["status"] == "score"
    scenario["deterministic_expectations"]["detector_rows"][0]["site_anchor"] = "do/probe.do:99"
    with pytest.raises(replay.ReplayError, match="detector mapping differs"):
        replay.verify_deterministic_expectations(scenario, sandbox)


def test_answer_sheet_digest_pin_accepts_original_and_refuses_backfit(tmp_path):
    data = tmp_path / "data"
    (data / "answers").mkdir(parents=True)
    sheet = data / "answers/sheet.json"
    sheet.write_text('{"blind":true}\n', encoding="utf-8")
    scenario = {"answer_sheet": "answers/sheet.json", "answer_sheet_sha256": _sha(sheet)}
    assert replay.verify_answer_sheet_pin(scenario, data) == sheet
    sheet.write_text('{"backfit":true}\n', encoding="utf-8")
    with pytest.raises(replay.ReplayError, match="digest mismatch"):
        replay.verify_answer_sheet_pin(scenario, data)


def test_observed_effort_absence_is_recorded_not_refused(tmp_path):
    assert replay._observed_effort(tmp_path) == {
        "status": "absent", "dispatch_ledger": [], "hook_events": [],
    }


def test_faithful_b5_output_scores_green(tmp_path):
    scenario_path, scenario, sheet_path, sheet, run_dir, _ = _score_case(tmp_path)
    report = score.score_run(scenario_path, scenario, sheet_path, sheet, run_dir)
    assert report["status"] == "score"
    assert report["recoveries"][0]["mechanism_outcome"] == "hit"


@pytest.mark.parametrize("case", [
    "dismissal_repeating_anchors", "wrong_mechanism_at_right_line", "one_site_only",
    "cross_site_duplicate_abuse", "severity_demotion",
])
def test_five_adversarial_self_tests_score_red_with_faithful_controls(tmp_path, case):
    expected = _sheet()["expected_recoveries"]
    ledgers = [_ledger_row()]
    witnesses = [_witness_row()]
    if case == "dismissal_repeating_anchors":
        ledgers = [_ledger_row(disposition="not_error", evidence=ANCHOR)]
        witnesses = [_witness_row(
            disposition="not_error", mech_cols=("conditional_guard", "flag", "matches", "-", "-"))]
    elif case == "wrong_mechanism_at_right_line":
        witnesses = [_witness_row(mech_cols=(
            "conditional_guard", "flag", "never_fires", "[flag == 1]", "flag == 1 & x >= 0"))]
    elif case in {"one_site_only", "cross_site_duplicate_abuse"}:
        expected = expected + [{
            **expected[0], "key": "site-b", "source_id": SOURCE_2,
            "witness_id": WITNESS_2, "anchors": ["src/other.do:30"],
        }]
    elif case == "severity_demotion":
        ledgers = [_ledger_row(severity="3")]
        witnesses = [_witness_row(severity="3")]
    sheet = _sheet(expected)
    scenario_path, scenario, sheet_path, sheet, run_dir, _ = _score_case(
        tmp_path, sheet=sheet, ledgers=ledgers, witnesses=witnesses)
    report = score.score_run(scenario_path, scenario, sheet_path, sheet, run_dir)
    assert report["status"] == "red"
    # Each adversarial fixture has a faithful control with the same parser path.
    control_dir = tmp_path / "control"
    control_dir.mkdir()
    control_expected = expected
    control_ledgers = [_ledger_row()]
    control_witnesses = [_witness_row()]
    if len(expected) == 2:
        control_ledgers = [_ledger_row(
            witness_ids=f"{WITNESS}; {WITNESS_2}",
            evidence=f"{ANCHOR}; src/other.do:30")]
        control_witnesses.append(_witness_row(source=SOURCE_2, witness=WITNESS_2))
    control_sheet = _sheet(control_expected)
    args = _score_case(control_dir, sheet=control_sheet,
                       ledgers=control_ledgers, witnesses=control_witnesses)
    assert score.score_run(*args[:5])["status"] == "score"


def test_tier1_mechanism_test_oracle_notices_broken_comparison():
    sheet = _sheet()
    wrong = [_witness_row(mech_cols=(
        "conditional_guard", "flag", "never_fires", "[flag == 1]", "flag == 1 & x >= 0"))]

    def negative_oracle(comparator=None):
        result = score.score_content(sheet, [dict(zip(rb.CODE_LEDGER_COLS, _ledger_row()))],
                                     [dict(zip(rb.WITNESS_OUTCOME_COLS, wrong[0]))],
                                     comparator=comparator)
        assert result["status"] == "red"

    negative_oracle()
    with pytest.raises(AssertionError):
        negative_oracle(lambda _run, _accepted: "hit")


def test_false_positive_ceiling_scores_red_and_allows_declared_ceiling():
    ledgers = [dict(zip(rb.CODE_LEDGER_COLS, _ledger_row())),
               dict(zip(rb.CODE_LEDGER_COLS, _ledger_row(output_id="E-7999")))]
    witnesses = [dict(zip(rb.WITNESS_OUTCOME_COLS, _witness_row()))]
    assert score.score_content(_sheet(ceiling=0), ledgers, witnesses)["status"] == "red"
    assert score.score_content(_sheet(ceiling=1), ledgers, witnesses)["status"] == "score"


@pytest.mark.parametrize("mutation, token", [
    ({"code_commit": None}, "code_commit"),
    ({"mechanism_schema_version": "9.9.9"}, "mechanism_schema_version mismatch"),
])
def test_attributability_refuses_missing_or_mismatched_identity(tmp_path, mutation, token):
    args = _score_case(tmp_path, record_patch=mutation)
    with pytest.raises(score.ScoreRefusal, match=token):
        score.score_run(*args[:5])


def test_attributability_test_oracle_notices_disabled_required_field_check(tmp_path, monkeypatch):
    args = _score_case(tmp_path, record_patch={"code_commit": None})

    def negative_oracle():
        with pytest.raises(score.ScoreRefusal):
            score.score_run(*args[:5])

    negative_oracle()
    monkeypatch.setattr(score, "RECORD_IDENTITY_FIELDS", tuple(
        field for field in score.RECORD_IDENTITY_FIELDS if field != "code_commit"))
    # The weakened check now permits the report, so the refusal oracle notices.
    with pytest.raises(pytest.fail.Exception):
        negative_oracle()


def test_reported_model_absence_is_allowed_but_contradiction_refuses():
    scenario = {"stage": "code_b5", "route": "worker", "model": "claude-pinned",
                "effort": "high"}
    record = {"format_version": 1, "scenario_id": "opaque", "stage": "code_b5",
              "route": "worker", "run_index": 1, "timestamp": "now",
              "promised_outputs_found": ["audit/x.md"], "identity": {
                  "model_requested": "claude-pinned", "model_reported": "absent",
                  "cli_version": "2.1", "code_commit": "a" * 40, "code_dirty": True,
                  "requested_effort": "high", "observed_effort": {"status": "absent"},
                  "mechanism_schema_version": mechanism.MECHANISM_SCHEMA_VERSION,
              }}
    assert score._validate_identity(record, scenario)["model_reported"] == "absent"
    record["identity"]["model_reported"] = "claude-other"
    with pytest.raises(score.ScoreRefusal, match="CLI-reported model"):
        score._validate_identity(record, scenario)


def test_missing_promised_output_refuses_before_content_scoring(tmp_path):
    args = _score_case(tmp_path)
    (args[4] / "sandbox/audit/shard.md").unlink()
    with pytest.raises(score.ScoreRefusal, match="no declared promised output"):
        score.score_run(*args[:5])


def test_present_but_malformed_b5_output_emits_attributable_red_report(tmp_path):
    args = _score_case(tmp_path)
    shard = args[4] / "sandbox/audit/shard.md"
    shard.write_text(
        "# Worker output\n\n| ID | Verdict |\n| --- | --- |\n"
        "| E-7000 | not_error |\n",
        encoding="utf-8",
    )
    report = score.score_run(*args[:5])
    assert report["status"] == "red"
    assert report["recoveries"][0]["mechanism_outcome"] == "unscorable"
    assert "expected exactly one" in report["format_problems"][0]


def test_score_cli_writes_score_and_append_only_grouping_log(tmp_path):
    archive, manifest_path, _ = _archive(tmp_path)
    data = _data_tree(tmp_path, manifest_path)
    scenario_path, scenario = _scenario(data, archive, promised=("audit/shard.md",))
    sheet = _sheet()
    (data / scenario["answer_sheet"]).write_text(json.dumps(sheet), encoding="utf-8")
    _pin_sheet(scenario_path, scenario, data / scenario["answer_sheet"])
    run_dir = data / "results/S-701/run-001"
    run_dir.mkdir(parents=True)
    _write_output(run_dir)
    _record(run_dir)
    result = subprocess.run([
        sys.executable, str(SCORE_CLI), "--data-root", str(data), "score",
        str(scenario_path), str(run_dir),
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SCORE SCORE:" in result.stdout
    assert (data / "results/S-701/score-run-001.json").is_file()
    lines = (data / "results/batches.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["status"] == "score"
    # Re-scoring the same run index refuses rather than overwriting the report.
    rescore = subprocess.run([
        sys.executable, str(SCORE_CLI), "--data-root", str(data), "score",
        str(scenario_path), str(run_dir),
    ], capture_output=True, text=True)
    assert rescore.returncode == 1
    assert "already exists" in rescore.stderr
    _restore_owner_write(archive)


def test_io_error_during_scoring_refuses_never_red(tmp_path, monkeypatch):
    monkeypatch.setenv("RCA_REPLAY_DATA_ROOT", str(tmp_path))
    (tmp_path / "registry.json").write_text(json.dumps({"opaque-a1": "S-701"}))
    scenario_path, _scenario_value, sheet_path, _sheet, run_dir, _record = _score_case(tmp_path)
    (tmp_path / "answers").mkdir()
    answer = tmp_path / "answers/sheet.json"
    answer.write_bytes(sheet_path.read_bytes())
    scenario = json.loads(scenario_path.read_text())
    scenario["answer_sheet"] = "answers/sheet.json"
    scenario["answer_sheet_sha256"] = _sha(answer)
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
    shard = run_dir / "sandbox/audit/shard.md"
    shard.chmod(0o000)
    try:
        result = subprocess.run([
            sys.executable, str(SCORE_CLI), "score", str(scenario_path), str(run_dir),
        ], capture_output=True, text=True, env={**os.environ,
                                                "RCA_REPLAY_DATA_ROOT": str(tmp_path)})
    finally:
        shard.chmod(0o644)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "SCORE REFUSED" in result.stderr and "SCORE RED" not in result.stderr


def test_spread_report_presents_every_run_without_aggregate_status(tmp_path):
    archive, manifest_path, _ = _archive(tmp_path)
    data = _data_tree(tmp_path, manifest_path)
    scenario_path, scenario = _scenario(
        data, archive, route="worker", promised=("audit/shard.md",))
    (data / scenario["answer_sheet"]).write_text(json.dumps(_sheet()), encoding="utf-8")
    _pin_sheet(scenario_path, scenario, data / scenario["answer_sheet"])
    for index in (1, 2):
        run_dir = data / f"results/S-701/run-{index:03d}"
        run_dir.mkdir(parents=True)
        _write_output(run_dir)
        record = _record(run_dir)
        record.update(route="worker", run_index=index)
        record["identity"].update(
            model_requested="claude-test", model_reported="absent",
            cli_version="2.1", requested_effort="high",
            observed_effort={"status": "absent"})
        (run_dir / "replay-record.json").write_text(json.dumps(record), encoding="utf-8")
    result = subprocess.run([
        sys.executable, str(SCORE_CLI), "--data-root", str(data), "spread",
        str(scenario_path),
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    spread = json.loads((data / "results/S-701/spread-report.json").read_text())
    assert [run["run_index"] for run in spread["runs"]] == [1, 2]
    assert "status" not in spread and spread["operator_adjudication"] == "pending"
    _restore_owner_write(archive)
