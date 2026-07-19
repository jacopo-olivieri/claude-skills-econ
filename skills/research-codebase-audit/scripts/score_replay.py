#!/usr/bin/env python3
"""Score replay output against a blind JSON answer sheet.

Answer sheets are JSON objects with ``format_version`` 1,
``mechanism_schema_version``, ``disposition_complete``, a nonnegative
``false_positive_ceiling``, an ``output_contract`` containing ledger and
witness-table globs, and ``expected_recoveries``.  Each expected recovery
declares ``key``, ``output_id``, the full ``channel`` / ``source_id`` /
``witness_id`` identity, ``disposition``, a canonical ``b64:`` mechanism,
``severity_floor``, and zero or more short ``anchors``.  For example, an
invented archaeology sheet might expect witness ``DUW-abc...`` at
``src/pottery.do:12``.  The scorer never reads a benchmark key directly.

Candidate-mode sheets replace the b5 ledger/witness legs with an
``expected_candidates`` table.  Each expectation is keyed by exact
repo-relative source path and a U1-canonical mechanism using
``EMPTY_PROJECTION``; status is candidate-family, severity is benchmark ±1,
and unexpected candidate IDs within the declared scenario files count toward
the same false-positive ceiling.

The CLI reads root configuration from ``--data-root`` or
``RCA_REPLAY_DATA_ROOT``.  ``score`` handles one run directory; ``spread``
scores every ``run-NNN`` directory for the scenario and presents all scores
side by side without aggregating them into a pass/fail batch.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import definition_use as du
import lint_registers as registers
import mechanism_schema as mechanism


FORMAT_VERSION = 1
RECORD_IDENTITY_FIELDS = (
    "model_requested", "model_reported", "cli_version", "code_commit",
    "code_dirty", "requested_effort", "observed_effort",
    "mechanism_schema_version",
)
TERMINAL_DISPOSITIONS = {
    "confirmed_error", "not_error", "duplicate", "confirmation_needed",
    "blocked", "deferred",
}


class ScoreRefusal(RuntimeError):
    """Identity or output freshness is insufficient to issue a score."""


class ScoreFormatError(RuntimeError):
    """Output or sheet content is malformed and therefore scores red."""


def _atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _append_jsonl(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _load_json(path, label, refusal=False):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        error = ScoreRefusal if refusal else ScoreFormatError
        raise error(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        error = ScoreRefusal if refusal else ScoreFormatError
        raise error(f"{label} must contain a JSON object")
    return value


def load_scenario(path):
    value = _load_json(path, "scenario")
    if value.get("format_version") != FORMAT_VERSION:
        raise ScoreFormatError("scenario format_version must be 1")
    return Path(path).expanduser().resolve(), value


def load_sheet(path, scoring_mode="b5"):
    value = _load_json(path, "answer sheet")
    if value.get("format_version") != FORMAT_VERSION:
        raise ScoreFormatError("answer sheet format_version must be 1")
    if value.get("disposition_complete") is not True:
        raise ScoreFormatError("answer sheet must declare disposition_complete true")
    ceiling = value.get("false_positive_ceiling")
    if not isinstance(ceiling, int) or ceiling < 0:
        raise ScoreFormatError("answer sheet false_positive_ceiling must be nonnegative")
    if scoring_mode == "candidate":
        return _load_candidate_sheet(value)
    if scoring_mode != "b5":
        raise ScoreFormatError(f"unknown scoring mode {scoring_mode!r}")
    recoveries = value.get("expected_recoveries")
    if not isinstance(recoveries, list) or not recoveries:
        raise ScoreFormatError("answer sheet requires expected_recoveries")
    keys, witness_keys = set(), set()
    required = {
        "key", "output_id", "channel", "source_id", "witness_id",
        "disposition", "mechanism", "severity_floor", "anchors",
    }
    for index, expected in enumerate(recoveries):
        if not isinstance(expected, dict) or not required.issubset(expected):
            raise ScoreFormatError(f"expected recovery {index} is missing required fields")
        if expected["key"] in keys:
            raise ScoreFormatError(f"duplicate expected recovery key {expected['key']}")
        keys.add(expected["key"])
        witness_key = (expected["channel"], expected["source_id"], expected["witness_id"])
        if witness_key in witness_keys:
            raise ScoreFormatError(f"duplicate expected witness identity {witness_key}")
        witness_keys.add(witness_key)
        if expected["disposition"] not in TERMINAL_DISPOSITIONS:
            raise ScoreFormatError(f"expected recovery {expected['key']} has nonterminal disposition")
        if not isinstance(expected["severity_floor"], int) or not 0 <= expected["severity_floor"] <= 4:
            raise ScoreFormatError(f"expected recovery {expected['key']} has invalid severity floor")
        if not isinstance(expected["anchors"], list) or not all(
                isinstance(anchor, str) and anchor for anchor in expected["anchors"]):
            raise ScoreFormatError(f"expected recovery {expected['key']} has invalid anchors")
        try:
            mechanism.score_expected_finding([], [expected["mechanism"]])
        except mechanism.MechanismSchemaError as exc:
            raise ScoreFormatError(
                f"expected recovery {expected['key']} has invalid canonical mechanism: {exc}"
            ) from exc
    contract = value.get("output_contract")
    if not isinstance(contract, dict):
        raise ScoreFormatError("answer sheet requires output_contract")
    for field in ("ledger_paths", "witness_paths"):
        patterns = contract.get(field)
        if not isinstance(patterns, list) or not patterns or not all(
                isinstance(pattern, str) and pattern for pattern in patterns):
            raise ScoreFormatError(f"output_contract {field} must be a non-empty string list")
    return value


def _load_candidate_sheet(value):
    expected = value.get("expected_candidates")
    if not isinstance(expected, list) or not expected:
        raise ScoreFormatError("candidate answer sheet requires expected_candidates")
    contract = value.get("output_contract")
    if not isinstance(contract, dict):
        raise ScoreFormatError("candidate answer sheet requires output_contract")
    paths = contract.get("candidate_paths")
    files = contract.get("scenario_files")
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) and p for p in paths):
        raise ScoreFormatError("candidate_paths must be a non-empty string list")
    if not isinstance(files, list) or not files or not all(
            isinstance(path, str) and path and not path.startswith("/") for path in files):
        raise ScoreFormatError("scenario_files must be non-empty repo-relative paths")
    keys, identities = set(), set()
    required = {"key", "register", "path", "mechanism", "status_family",
                "benchmark_severity", "anchors"}
    for index, row in enumerate(expected):
        if not isinstance(row, dict) or not required <= set(row):
            raise ScoreFormatError(f"expected candidate {index} is missing required fields")
        if row["key"] in keys:
            raise ScoreFormatError(f"duplicate expected candidate key {row['key']}")
        keys.add(row["key"])
        if row["register"] not in {"code_errors", "claims"}:
            raise ScoreFormatError(f"expected candidate {row['key']} has invalid register")
        if row["path"] not in files:
            raise ScoreFormatError(f"expected candidate {row['key']} path is outside scenario_files")
        if row["status_family"] != "candidate":
            raise ScoreFormatError(f"expected candidate {row['key']} status_family must be candidate")
        if not isinstance(row["benchmark_severity"], int) or not 1 <= row["benchmark_severity"] <= 4:
            raise ScoreFormatError(f"expected candidate {row['key']} has invalid benchmark severity")
        if not isinstance(row["anchors"], list) or not all(
                isinstance(anchor, str) and anchor for anchor in row["anchors"]):
            raise ScoreFormatError(f"expected candidate {row['key']} has invalid anchors")
        try:
            mechanism.score_expected_finding([], [row["mechanism"]])
        except mechanism.MechanismSchemaError as exc:
            raise ScoreFormatError(
                f"expected candidate {row['key']} has invalid canonical mechanism: {exc}"
            ) from exc
        identity = (row["path"], row["mechanism"])
        if identity in identities:
            raise ScoreFormatError(f"duplicate expected candidate identity {identity}")
        identities.add(identity)
    return value


def _validate_identity(record, scenario):
    required_top = {
        "format_version", "scenario_id", "stage", "route", "run_index",
        "timestamp", "identity", "promised_outputs_found",
    }
    missing_top = sorted(required_top - set(record))
    if missing_top:
        raise ScoreRefusal(f"replay record missing identity field(s): {missing_top}")
    identity = record.get("identity")
    if not isinstance(identity, dict):
        raise ScoreRefusal("replay record identity block is missing")
    missing = [field for field in RECORD_IDENTITY_FIELDS if field not in identity]
    if missing:
        raise ScoreRefusal(f"replay record missing identity field(s): {missing}")
    for field in RECORD_IDENTITY_FIELDS:
        if identity[field] is None or identity[field] == "":
            raise ScoreRefusal(f"replay record identity field {field} is empty")
    versions = {
        "replay record": identity["mechanism_schema_version"],
        "current checkout": mechanism.MECHANISM_SCHEMA_VERSION,
    }
    if len(set(versions.values())) != 1:
        raise ScoreRefusal(
            "mechanism_schema_version mismatch: "
            + ", ".join(f"{key}={value!r}" for key, value in versions.items())
        )
    if record["stage"] != scenario.get("stage") or record["route"] != scenario.get("route"):
        raise ScoreRefusal("replay record stage/route disagrees with scenario")
    if scenario.get("route") in {"worker", "merge"}:
        if identity["model_requested"] != scenario.get("model"):
            raise ScoreRefusal("replay record requested model disagrees with scenario pin")
        reported = identity["model_reported"]
        if reported != "absent" and reported != scenario.get("model"):
            raise ScoreRefusal(
                f"CLI-reported model {reported!r} disagrees with requested pin {scenario.get('model')!r}"
            )
        if identity["requested_effort"] != scenario.get("effort"):
            raise ScoreRefusal("replay record requested effort disagrees with scenario pin")
    return identity


def _sandbox_files(sandbox):
    if not Path(sandbox).is_dir():
        return []
    return [
        path.relative_to(sandbox).as_posix()
        for path in Path(sandbox).rglob("*") if path.is_file()
    ]


def _glob_files(sandbox, patterns):
    return sorted(
        path for path in _sandbox_files(sandbox)
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)
    )


def _promised_outputs(sandbox, scenario):
    found = _glob_files(sandbox, scenario.get("promised_outputs", []))
    if not found:
        raise ScoreRefusal("run directory contains no declared promised output")
    return found


def _table_rows(path, columns):
    text = Path(path).read_text(encoding="utf-8")
    tables = [rows for headers, rows, _line in du.parse_markdown_tables(text)
              if headers == columns]
    if len(tables) != 1:
        raise ScoreFormatError(
            f"{path}: expected exactly one {' | '.join(columns)} table"
        )
    parsed = []
    for row in tables[0]:
        if len(row) != len(columns):
            raise ScoreFormatError(f"{path}: malformed b5 table row")
        parsed.append(dict(zip(columns, [str(cell).strip().strip("`").strip() for cell in row])))
    return parsed


def _load_output_tables(sandbox, sheet):
    contract = sheet["output_contract"]
    ledger_files = _glob_files(sandbox, contract["ledger_paths"])
    witness_files = _glob_files(sandbox, contract["witness_paths"])
    if not ledger_files or not witness_files:
        raise ScoreFormatError("b5 ledger or witness-outcome output is absent")
    ledgers, witnesses = [], []
    for relative in ledger_files:
        ledgers.extend(_table_rows(Path(sandbox) / relative, registers.CODE_LEDGER_COLS))
    for relative in witness_files:
        witnesses.extend(_table_rows(Path(sandbox) / relative, registers.WITNESS_OUTCOME_COLS))
    return ledgers, witnesses, sorted(set(ledger_files + witness_files))


def _candidate_mechanism(register, row, path):
    class_col = "Error Type" if register == "code_errors" else "Claim Type"
    return mechanism.canonicalize_mechanism(
        row[class_col], path, "unresolved", "-", "-",
        register=register, anchor=path, projection=mechanism.EMPTY_PROJECTION,
    ).sidecar


def _candidate_sources(row, scenario_files):
    cell = row.get("Code/Data Source", "")
    found = []
    for path in scenario_files:
        if re.search(rf"(?<![\w./-]){re.escape(path)}(?=[:;,\s`]|$)", cell):
            found.append(path)
    return found


def _load_candidate_tables(sandbox, sheet):
    contract = sheet["output_contract"]
    files = _glob_files(sandbox, contract["candidate_paths"])
    if not files:
        raise ScoreFormatError("candidate-register output is absent")
    rows = []
    for relative in files:
        path = Path(sandbox) / relative
        text = path.read_text(encoding="utf-8")
        for register, columns, id_col in (
                ("code_errors", registers.ERROR_COLS, "Error ID"),
                ("claims", registers.CLAIMS_COLS, "Claim ID")):
            tables = [table for headers, table, _line in du.parse_markdown_tables(text)
                      if headers == columns]
            if len(tables) > 1:
                raise ScoreFormatError(f"{path}: duplicate {register} candidate tables")
            for raw in tables[0] if tables else []:
                if len(raw) != len(columns):
                    raise ScoreFormatError(f"{path}: malformed candidate row")
                row = dict(zip(columns, [str(cell).strip().strip("`").strip()
                                         for cell in raw]))
                for source in _candidate_sources(row, contract["scenario_files"]):
                    rows.append({
                        "id": row[id_col], "register": register, "path": source,
                        "mechanism": _candidate_mechanism(register, row, source),
                        "status": row["Status"], "severity": _severity(row["Severity"]),
                        "text": " ".join(row.values()),
                    })
    return rows, files


def score_candidates(sheet, rows):
    recoveries = []
    matched_ids = set()
    for expected in sheet["expected_candidates"]:
        matches = [row for row in rows if (
            row["register"] == expected["register"]
            and row["path"] == expected["path"]
            and row["mechanism"] == expected["mechanism"]
            and all(anchor in row["text"] for anchor in expected["anchors"])
        )]
        problems = []
        # Every expectation-matched row is accounted to its expectation, even
        # in the ambiguous multi-match case (already red via its problem
        # entry), so matched rows never pollute the false-positive list.
        matched_ids.update((row["register"], row["id"]) for row in matches)
        if len(matches) != 1:
            problems.append(f"expected one candidate row, found {len(matches)}")
        else:
            row = matches[0]
            valid_status = (row["status"] == "candidate" if row["register"] == "code_errors"
                            else row["status"] in {"inconsistent", "unclear"})
            if not valid_status:
                problems.append(f"status {row['status']!r} is outside candidate family")
            if row["severity"] is None or abs(
                    row["severity"] - expected["benchmark_severity"]) > 1:
                problems.append(
                    f"severity {row['severity']!r} is outside benchmark ±1 "
                    f"of {expected['benchmark_severity']}"
                )
        recoveries.append({
            "key": expected["key"], "candidate_identity": [expected["path"], expected["mechanism"]],
            "mechanism_outcome": "hit" if matches else "absent",
            "status": "score" if not problems else "red", "problems": problems,
        })
    # Dedup on (register, id): a row citing several scenario files enters the
    # table once per source path but burns the ceiling at most once (U5's
    # false-positive-ceiling semantics carried over — phase-C erratum).
    false_positive_ids = sorted({
        identity[1] for identity in
        {(row["register"], row["id"]) for row in rows} - matched_ids
    })
    ceiling = sheet["false_positive_ceiling"]
    false_positive_ok = len(false_positive_ids) <= ceiling
    return {
        "status": "score" if all(row["status"] == "score" for row in recoveries)
        and false_positive_ok else "red",
        "recoveries": recoveries, "false_positive_ids": false_positive_ids,
        "false_positive_ceiling": ceiling, "false_positive_ok": false_positive_ok,
    }


def _split_ids(value):
    return set(re.findall(r"(?:DUW|MFW|CVW)-[0-9a-f]{12}", value or ""))


def _severity(value):
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def evaluate_recovery(expected, ledgers, witnesses, comparator=None):
    comparator = comparator or mechanism.score_expected_finding
    key = (expected["channel"], expected["source_id"], expected["witness_id"])
    matching_witnesses = [row for row in witnesses if (
        row["Channel"], row["Source ID"], row["Witness ID"]
    ) == key]
    problems = []
    mechanism_outcome = "absent"
    if len(matching_witnesses) != 1:
        problems.append(f"expected one witness row for {key}, found {len(matching_witnesses)}")
    else:
        witness = matching_witnesses[0]
        if witness["Verdict"] != expected["disposition"]:
            problems.append(
                f"witness disposition {witness['Verdict']!r} != {expected['disposition']!r}"
            )
        try:
            canonical = mechanism.canonicalize_mechanism(
                witness["Mech Class"], witness["Mech Object"], witness["Mech Relation"],
                witness["Mech Expected"], witness["Mech Actual"],
                register="code_errors", anchor=(expected["anchors"] or [""])[0],
            )
            mechanism_outcome = comparator([canonical.sidecar], [expected["mechanism"]])
        except mechanism.MechanismSchemaError as exc:
            problems.append(f"worker mechanism is invalid: {exc}")
            mechanism_outcome = "invalid"
        if mechanism_outcome != "hit":
            problems.append(f"mechanism outcome is {mechanism_outcome}")
        observed_severity = _severity(witness["Proposed Severity"])
        if observed_severity is None or observed_severity < expected["severity_floor"]:
            problems.append(
                f"witness severity {witness['Proposed Severity']!r} is below floor "
                f"{expected['severity_floor']}"
            )
    matching_ledgers = [row for row in ledgers if (
        row["ID"] == expected["output_id"]
        and expected["witness_id"] in _split_ids(row["Outcome Witness IDs"])
    )]
    if len(matching_ledgers) != 1:
        problems.append(
            f"expected one ledger row for {expected['output_id']}/{expected['witness_id']}, "
            f"found {len(matching_ledgers)}"
        )
    else:
        ledger = matching_ledgers[0]
        if ledger["Verdict"] != expected["disposition"]:
            problems.append(
                f"ledger disposition {ledger['Verdict']!r} != {expected['disposition']!r}"
            )
        observed_severity = _severity(ledger["Proposed Severity"])
        if observed_severity is None or observed_severity < expected["severity_floor"]:
            problems.append(
                f"ledger severity {ledger['Proposed Severity']!r} is below floor "
                f"{expected['severity_floor']}"
            )
        for anchor in expected["anchors"]:
            if anchor not in ledger["Evidence Checked"]:
                problems.append(f"ledger evidence omits required anchor {anchor}")
    return {
        "key": expected["key"], "output_id": expected["output_id"],
        "witness_identity": list(key), "mechanism_outcome": mechanism_outcome,
        "status": "score" if not problems else "red", "problems": problems,
    }


def score_content(sheet, ledgers, witnesses, comparator=None):
    recoveries = [
        evaluate_recovery(expected, ledgers, witnesses, comparator=comparator)
        for expected in sheet["expected_recoveries"]
    ]
    expected_ids = {expected["output_id"] for expected in sheet["expected_recoveries"]}
    false_positive_ids = sorted({row["ID"] for row in ledgers if row["ID"] not in expected_ids})
    false_positive_ok = len(false_positive_ids) <= sheet["false_positive_ceiling"]
    return {
        "status": "score" if all(item["status"] == "score" for item in recoveries)
        and false_positive_ok else "red",
        "recoveries": recoveries,
        "false_positive_ids": false_positive_ids,
        "false_positive_ceiling": sheet["false_positive_ceiling"],
        "false_positive_ok": false_positive_ok,
    }


def score_run(scenario_path, scenario, sheet_path, sheet, run_dir):
    run_dir = Path(run_dir).expanduser().resolve()
    record = _load_json(run_dir / "replay-record.json", "replay record", refusal=True)
    identity = _validate_identity(record, scenario)
    versions = {
        "answer sheet": sheet.get("mechanism_schema_version"),
        "replay record": identity["mechanism_schema_version"],
        "current checkout": mechanism.MECHANISM_SCHEMA_VERSION,
    }
    if len(set(versions.values())) != 1:
        raise ScoreRefusal(
            "mechanism_schema_version mismatch: "
            + ", ".join(f"{key}={value!r}" for key, value in versions.items())
        )
    sandbox = run_dir / "sandbox"
    promised = _promised_outputs(sandbox, scenario)
    mode = scenario.get("scoring_mode", "b5")
    if mode == "candidate":
        try:
            candidates, output_paths = _load_candidate_tables(sandbox, sheet)
            content = score_candidates(sheet, candidates)
        except ScoreFormatError as exc:
            output_paths = _glob_files(
                sandbox, sheet.get("output_contract", {}).get("candidate_paths", []))
            problem = str(exc)
            content = {
                "status": "red", "recoveries": [{
                    "key": expected["key"],
                    "candidate_identity": [expected["path"], expected["mechanism"]],
                    "mechanism_outcome": "unscorable", "status": "red",
                    "problems": [problem],
                } for expected in sheet["expected_candidates"]],
                "false_positive_ids": [],
                "false_positive_ceiling": sheet["false_positive_ceiling"],
                "false_positive_ok": False, "format_problems": [problem],
            }
    else:
        try:
            ledgers, witnesses, output_paths = _load_output_tables(sandbox, sheet)
            content = score_content(sheet, ledgers, witnesses)
        except ScoreFormatError as exc:
            contract = sheet["output_contract"]
            output_paths = sorted(set(
                _glob_files(sandbox, contract["ledger_paths"])
                + _glob_files(sandbox, contract["witness_paths"])
            ))
            problem = str(exc)
            content = {
                "status": "red",
                "recoveries": [{
                    "key": expected["key"], "output_id": expected["output_id"],
                    "witness_identity": [
                        expected["channel"], expected["source_id"], expected["witness_id"],
                    ],
                    "mechanism_outcome": "unscorable",
                    "status": "red", "problems": [problem],
                } for expected in sheet["expected_recoveries"]],
                "false_positive_ids": [],
                "false_positive_ceiling": sheet["false_positive_ceiling"],
                "false_positive_ok": False,
                "format_problems": [problem],
            }
    return {
        "format_version": FORMAT_VERSION, "status": content["status"],
        "scenario_id": Path(scenario_path).stem, "run_index": record["run_index"],
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "identity": identity, "sheet_path": str(Path(sheet_path).resolve()),
        "sheet_sha256": hashlib.sha256(Path(sheet_path).read_bytes()).hexdigest(),
        "promised_outputs": promised, "scored_outputs": output_paths,
        **content,
    }


def _configured_data_root(flag):
    raw = flag or os.environ.get("RCA_REPLAY_DATA_ROOT")
    if not raw:
        raise ScoreRefusal("replay data root is required via --data-root or RCA_REPLAY_DATA_ROOT")
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise ScoreRefusal(f"replay data root is not a directory: {root}")
    return root


def _registry_label(data_root, scenario_id):
    registry = _load_json(Path(data_root) / "registry.json", "scenario registry")
    label = registry.get(scenario_id)
    if not isinstance(label, str) or not re.fullmatch(r"S-7\d{2}", label):
        raise ScoreFormatError(f"scenario registry has no valid label for {scenario_id}")
    return label


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("score")
    one.add_argument("scenario", type=Path)
    one.add_argument("run_dir", type=Path)
    spread = sub.add_parser("spread")
    spread.add_argument("scenario", type=Path)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        data_root = _configured_data_root(args.data_root)
        scenario_path, scenario = load_scenario(args.scenario)
        sheet_path = (data_root / scenario["answer_sheet"]).resolve()
        if not sheet_path.is_relative_to(data_root):
            raise ScoreFormatError("answer sheet path escapes replay data root")
        expected_digest = scenario.get("answer_sheet_sha256")
        if not isinstance(expected_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
            raise ScoreFormatError("scenario answer_sheet_sha256 is missing or invalid")
        actual_digest = hashlib.sha256(sheet_path.read_bytes()).hexdigest()
        if actual_digest != expected_digest:
            raise ScoreRefusal(
                f"answer sheet digest mismatch: expected {expected_digest}, actual {actual_digest}"
            )
        scoring_mode = scenario.get("scoring_mode", "b5")
        if scoring_mode not in {"b5", "candidate"}:
            raise ScoreFormatError(f"scenario scoring_mode must be b5 or candidate, got {scoring_mode!r}")
        sheet = load_sheet(sheet_path, scoring_mode=scoring_mode)
        label = _registry_label(data_root, scenario_path.stem)
        result_root = data_root / "results" / label
        if args.command == "score":
            report = score_run(scenario_path, scenario, sheet_path, sheet, args.run_dir)
            report_path = result_root / f"score-run-{report['run_index']:03d}.json"
            if report_path.exists():
                raise ScoreRefusal(
                    f"score report already exists (remove it deliberately to re-score): "
                    f"{report_path}"
                )
            _atomic_json(report_path, report)
            _append_jsonl(data_root / "results" / "batches.jsonl", {
                "scenario": label, "run_index": report["run_index"],
                "status": report["status"], "report": str(report_path),
            })
            print(f"SCORE {report['status'].upper()}: {report_path}")
            return 0 if report["status"] == "score" else 2
        reports = []
        for run_dir in sorted(result_root.glob("run-[0-9][0-9][0-9]")):
            report = score_run(scenario_path, scenario, sheet_path, sheet, run_dir)
            report_path = result_root / f"score-run-{report['run_index']:03d}.json"
            if report_path.exists():
                raise ScoreRefusal(
                    f"score report already exists (remove it deliberately to re-score): "
                    f"{report_path}"
                )
            _atomic_json(report_path, report)
            _append_jsonl(data_root / "results" / "batches.jsonl", {
                "scenario": label, "run_index": report["run_index"],
                "status": report["status"], "report": str(report_path),
                "spread": True,
            })
            reports.append({
                "run_index": report["run_index"], "status": report["status"],
                "report": str(report_path),
            })
        if len(reports) != scenario.get("runs"):
            raise ScoreRefusal(
                f"spread expected {scenario.get('runs')} run directories, found {len(reports)}"
            )
        spread_report = {
            "format_version": FORMAT_VERSION, "scenario": label,
            "scenario_id": scenario_path.stem,
            "reported_at": datetime.now(timezone.utc).isoformat(),
            "operator_adjudication": "pending", "runs": reports,
        }
        spread_path = result_root / "spread-report.json"
        _atomic_json(spread_path, spread_report)
        print(f"SCORE SPREAD: {spread_path}; runs={[(r['run_index'], r['status']) for r in reports]}")
        return 0
    except ScoreRefusal as exc:
        print(f"SCORE REFUSED: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        # I/O trouble means the run cannot be scored — refusal, never a red score.
        print(f"SCORE REFUSED: {exc}", file=sys.stderr)
        return 1
    except (ScoreFormatError, mechanism.MechanismSchemaError) as exc:
        print(f"SCORE RED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
