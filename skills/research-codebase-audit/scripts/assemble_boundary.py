#!/usr/bin/env python3
"""Assemble worker witness outcomes into the canonical adjudication boundary."""

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

import build_detector_mapping as detector_mapping
import lint_registers as registers
import mechanism_schema as mechanisms
import verify_dismissals as verifier
import severity_tokens


CODE_LEDGER_COLS = verifier.CODE_LEDGER_COLS
WITNESS_COLS = list(mechanisms.PRE_BOUNDARY_WITNESS_COLUMNS)
POST_COLS = list(mechanisms.POST_BOUNDARY_WITNESS_COLUMNS)
LINEAGE_COLS = detector_mapping.LINEAGE_COLS
DISMISSAL_COLS = ["Error ID"]
DISMISSAL_ZERO = "No mapped Error IDs were assembled as not_error."


class BoundaryError(RuntimeError):
    """The adjudication inputs do not define a safe canonical boundary."""


def _clean(value):
    return str(value).strip().strip("`").strip()


def _blank(value):
    return _clean(value) in {"", "-", "—"}


def _list_cell(value):
    if _blank(value):
        return []
    return [_clean(part) for part in str(value).split(";") if not _blank(part)]


def _table_rows(path, columns):
    text = path.read_text(encoding="utf-8")
    found = []
    for headers, rows, _line in registers.parse_tables(text):
        if headers != columns:
            continue
        for index, row in enumerate(rows, start=1):
            if len(row) != len(columns):
                raise BoundaryError(f"{path}: malformed {'/'.join(columns)} row {index}")
            found.append(dict(zip(columns, map(_clean, row))))
    return found


def load_inputs(audit, supplementary=False):
    ledgers, outcomes, records = [], {}, {}
    root = audit / ("_code_error_recheck_supplementary"
                    if supplementary else "_code_error_recheck")
    if not root.is_dir():
        if supplementary:
            return ledgers, outcomes, records
        raise BoundaryError(f"missing code recheck shard directory: {root}")
    for path in sorted(root.rglob("*.md")):
        ledgers.extend((path, row) for row in _table_rows(path, CODE_LEDGER_COLS))
        for row in _table_rows(path, WITNESS_COLS):
            key = tuple(row[field] for field in ("Channel", "Source ID", "Witness ID"))
            if key in outcomes:
                raise BoundaryError(f"{path}: duplicate witness outcome {'/'.join(key)}")
            outcomes[key] = (path, row)
        for columns in (verifier.MF_RECORD_COLS, verifier.PROBE_RECORD_COLS):
            for row in _table_rows(path, columns):
                record_id = row["Record ID"]
                if record_id in records:
                    raise BoundaryError(f"duplicate verification Record ID {record_id}")
                records[record_id] = (path, row)
    return ledgers, outcomes, records


def load_receipts(audit, supplementary=False):
    path = audit / ("_run/code_b6b/dismissal_receipts.md"
                    if supplementary else "_run/code_b6a/dismissal_receipts.md")
    if not path.is_file() or path.stat().st_size == 0:
        raise BoundaryError(f"missing dismissal receipts artifact: {path}")
    rows = _table_rows(path, verifier.RECEIPT_COLS)
    text = path.read_text(encoding="utf-8")
    zero = (verifier.SUPPLEMENTARY_ZERO_RECEIPTS
            if supplementary else verifier.ZERO_RECEIPTS)
    if not rows and zero not in text:
        raise BoundaryError(f"{path}: missing receipt table or exact explicit-zero form")
    if rows and zero in text:
        raise BoundaryError(f"{path}: receipts table conflicts with explicit-zero form")
    ids = [row["Receipt ID"] for row in rows]
    if len(ids) != len(set(ids)):
        raise BoundaryError(f"{path}: duplicate Receipt ID")
    return rows


def load_lineage(audit, mappings):
    path = audit / "code_error_recheck_summary.md"
    if not path.is_file():
        return {}, set()
    rows = _table_rows(path, LINEAGE_COLS)
    by_key, originals = {}, set()
    mapping_keys = {(row["Error ID"], row["Channel"], row["Source ID"],
                     row["Witness ID"]) for row in mappings}
    for row in rows:
        original, descendant = row["Original Error ID"], row["Descendant Error ID"]
        key = (original, row["Channel"], row["Source ID"], row["Witness ID"])
        if key not in mapping_keys:
            raise BoundaryError(f"{path}: lineage row names an unmapped witness {'/'.join(key)}")
        if key in by_key:
            raise BoundaryError(f"{path}: witness appears more than once in split lineage")
        if not re.fullmatch(r"E-\d{4}", descendant):
            raise BoundaryError(f"{path}: invalid descendant Error ID {descendant}")
        by_key[key] = descendant
        originals.add(original)
    for mapping in mappings:
        original = mapping["Error ID"]
        key = (original, mapping["Channel"], mapping["Source ID"], mapping["Witness ID"])
        if original in originals and key not in by_key:
            raise BoundaryError(f"{path}: split lineage drops mapped witness {'/'.join(key)}")
    return by_key, originals


def _register(path):
    lint = registers.Lint()
    loaded = registers.load_register(
        lint, path, registers.ERROR_COLS, allow_extra=True)
    if loaded is None or lint.errors:
        raise BoundaryError(" | ".join(lint.errors) or f"cannot load register: {path}")
    headers, rows = loaded
    parsed = {}
    for row in rows:
        data = dict(zip(headers, row))
        error_id = data.get("Error ID", "")
        if error_id in parsed:
            raise BoundaryError(f"{path}: Error ID {error_id} appears more than once")
        parsed[error_id] = data
    return parsed


def _ledger_by_id(ledgers):
    result = {}
    for path, row in ledgers:
        result.setdefault(row["ID"], []).append((path, row))
    return result


def _qualifying_receipts(receipts, key, record_ids):
    found = []
    for row in receipts:
        receipt_key = tuple(row[field] for field in
                            ("Channel", "Source ID", "Witness ID"))
        if receipt_key == key and row["Record ID"] in record_ids \
                and row["Accepted (yes/no)"] == "yes":
            found.append(row["Receipt ID"])
    return sorted(set(found))


def _canonical_outcome(mapping, ledger, outcome, records, receipts, register_row):
    key = tuple(mapping[field] for field in ("Channel", "Source ID", "Witness ID"))
    verdict = ledger["Verdict"]
    if verdict in {"blocked", "deferred", "confirmation_needed"}:
        return {
            "Channel": key[0], "Source ID": key[1], "Witness ID": key[2],
            "Verdict": verdict, "Mechanism": "—",
            "Proposed Severity": ledger["Proposed Severity"] or "—",
            "Receipt IDs": "—", "Duplicate Target": "—",
        }, None
    if outcome is None:
        raise BoundaryError(f"mapped witness {'/'.join(key)} has no worker outcome")
    path, row = outcome
    if row["Verdict"] != verdict:
        raise BoundaryError(
            f"{path}: witness {'/'.join(key)} verdict {row['Verdict']} disagrees with ledger {verdict}"
        )
    try:
        canonical = mechanisms.canonicalize_mechanism(
            row["Mech Class"], row["Mech Object"], row["Mech Relation"],
            row["Mech Expected"], row["Mech Actual"], register="code_errors",
            anchor=mapping["Site Anchor"], projection=mechanisms.EMPTY_PROJECTION,
        )
    except mechanisms.MechanismSchemaError as exc:
        raise BoundaryError(f"{path}: witness {'/'.join(key)} cannot be canonicalized: {exc}") from exc
    declared_record_ids = set(_list_cell(ledger["Verification Record IDs"]))
    record_ids = {
        record_id for record_id in declared_record_ids
        if record_id in records and tuple(records[record_id][1][field]
                                          for field in ("Channel", "Source ID", "Witness ID")) == key
    }
    receipt_ids = _qualifying_receipts(receipts, key, record_ids)
    if verdict == "not_error" and not receipt_ids:
        raise BoundaryError(f"mapped not_error witness {'/'.join(key)} has no qualifying receipt")
    return {
        "Channel": key[0], "Source ID": key[1], "Witness ID": key[2],
        "Verdict": verdict, "Mechanism": canonical.sidecar,
        "Proposed Severity": row["Proposed Severity"] or "—",
        "Receipt IDs": "; ".join(receipt_ids) if receipt_ids else "—",
        "Duplicate Target": row["Duplicate Target"] or "—",
    }, canonical


def assemble(audit, register_path, supplementary=False):
    if supplementary:
        lint = registers.Lint()
        mappings = registers.supplementary_detector_mappings(lint, audit)
        if lint.errors:
            raise BoundaryError(" | ".join(lint.errors))
    else:
        _declared, _display, mappings = detector_mapping.load_mapping(
            audit / "_run/detector_mapping.md")
        mappings = detector_mapping.actionable_rows(mappings)
    ledgers, outcomes, records = load_inputs(audit, supplementary)
    receipts = load_receipts(audit, supplementary)
    register = _register(register_path)
    token_authorized = set()
    token_home = "code_b6b" if supplementary else "code_b6a"
    token_receipts = audit / f"_run/{token_home}/token_receipts.md"
    # Severe-eligible rows make the gate mandatory even when no token
    # artifact was ever written: a conductor that omits the token workflow
    # must fail here, never fall back to the pre-U8 boundary.
    if token_receipts.is_file() or severity_tokens.gate_required(register.values()):
        try:
            manifest = __import__("json").loads(
                (audit / "_run/manifest.json").read_text(encoding="utf-8"))
            classifications, token_failures = severity_tokens.gate_rows(
                audit.parent, audit, manifest, list(register.values()), token_home)
            allowed_uncovered = set()
            tokenless_ok = set()
            if not supplementary:
                plan = audit / "plans/code_error_supplementary_recheck_plan.md"
                if plan.is_file():
                    allowed_uncovered = {
                        row["Error ID"] for row in severity_tokens.rows_for_columns(
                            plan, severity_tokens.SUPPLEMENTARY_TOKEN_COLS)
                        if set(part.strip() for part in row["Reasons"].split(","))
                        & {"late_token", "split_token"}
                    }
            else:
                residual = audit / "_run/late_severity_residuals.md"
                if residual.is_file():
                    tokenless_ok = {
                        row["Error ID"] for row in severity_tokens.rows_for_columns(
                            residual, severity_tokens.RESIDUAL_COLS)
                    }
            remaining = severity_tokens.excuse_uncovered_failures(
                audit.parent, audit, manifest, list(register.values()),
                token_failures, allowed_uncovered, tokenless_ok)
            if remaining:
                raise BoundaryError("severity-token gate: " + " | ".join(remaining))
            token_authorized = {
                eid for eid, state in classifications.items()
                if state in {"live", "target_not_live"}
            } | allowed_uncovered | tokenless_ok
        except (OSError, __import__("json").JSONDecodeError,
                severity_tokens.SeverityTokenError) as exc:
            raise BoundaryError(f"cannot resolve severity-token boundary: {exc}") from exc
    ledgers_by_id = _ledger_by_id(ledgers)
    lineage, split_originals = ({}, set()) if supplementary else load_lineage(audit, mappings)
    mapped_ids = {row["Error ID"] for row in mappings} | set(lineage.values())
    post_rows, groups, canonical_by_group = [], {}, {}
    group_ledgers = {}
    for mapping in mappings:
        original = mapping["Error ID"]
        key4 = (original, mapping["Channel"], mapping["Source ID"], mapping["Witness ID"])
        effective = lineage.get(key4, original)
        dispositions = ledgers_by_id.get(effective) or ledgers_by_id.get(original, [])
        if len(dispositions) != 1:
            raise BoundaryError(
                f"mapped Error ID {effective} has {len(dispositions)} ledger rows; expected one"
            )
        ledger_path, ledger = dispositions[0]
        register_row = register.get(effective) or register.get(original)
        if register_row is None:
            raise BoundaryError(f"mapped Error ID {effective} is absent from the register")
        key = (mapping["Channel"], mapping["Source ID"], mapping["Witness ID"])
        post, canonical = _canonical_outcome(
            mapping, ledger, outcomes.get(key), records, receipts, register_row)
        post_rows.append(post)
        groups.setdefault(effective, []).append(post)
        group_ledgers.setdefault(effective, (ledger_path, ledger))
        if canonical is not None:
            canonical_by_group.setdefault(effective, set()).add(canonical.sidecar)
    dispositions = {}
    for error_id, (ledger_path, ledger) in group_ledgers.items():
        expected = registers.expected_code_disposition(
            ledger, severe_authorized=error_id in token_authorized)
        if expected is None:
            raise BoundaryError(
                f"{ledger_path}: mapped Error ID {error_id} has invalid code verdict "
                f"{ledger['Verdict']!r}"
            )
        dispositions[error_id] = expected
    dismissals = []
    snapshot_path = audit / ("_run/snapshots/code_b6b/code_error_register.md"
                             if supplementary else
                             "_run/snapshots/code_b6a/code_error_register.md")
    premerge = (_register(snapshot_path) if snapshot_path.is_file() else register)
    for error_id, rows in groups.items():
        aggregate = mechanisms.aggregate_row_mechanism([
            (row["Mechanism"], row["Verdict"], row["Proposed Severity"],
             row["Duplicate Target"]) for row in rows if row["Mechanism"] != "—"
        ]) if any(row["Mechanism"] != "—" for row in rows) else "—"
        if aggregate == mechanisms.MIXED and error_id not in split_originals:
            raise BoundaryError(f"mapped Error ID {error_id} is heterogeneous and must be split")
        verdicts = {row["Verdict"] for row in rows}
        if verdicts == {"not_error"}:
            dismissals.append(error_id)
    # Guard mapped-to-mapped duplicates on canonical bytes at the boundary.
    for error_id, rows in groups.items():
        targets = {_clean(row["Duplicate Target"]) for row in rows
                   if row["Verdict"] == "duplicate"}
        if not targets:
            continue
        if len(targets) != 1 or next(iter(targets)) not in mapped_ids:
            raise BoundaryError(f"mapped duplicate {error_id} must name one mechanically mapped target")
        target = next(iter(targets))
        if canonical_by_group.get(error_id) != canonical_by_group.get(target):
            raise BoundaryError(f"mapped duplicate {error_id} mechanism differs from target {target}")
        source_row = premerge.get(error_id) or register.get(error_id)
        target_row = premerge.get(target) or register.get(target)
        if source_row is None or target_row is None:
            raise BoundaryError(f"mapped duplicate {error_id} or target {target} is absent from pre-merge rows")
        if source_row["Error Type"] != target_row["Error Type"]:
            raise BoundaryError(f"mapped duplicate {error_id} error type differs from target {target}")
        target_locations = target_row["Code Location"] + " " + target_row["Code/Data Source"]
        for mapping in mappings:
            if mapping["Error ID"] == error_id:
                anchor_path = mapping["Site Anchor"].rsplit(":", 1)[0]
                if anchor_path not in target_locations:
                    raise BoundaryError(
                        f"mapped duplicate target {target} does not cover anchor {mapping['Site Anchor']}"
                    )
    return sorted(post_rows, key=lambda row: (
        row["Channel"], row["Source ID"], row["Witness ID"])), sorted(dismissals), \
        dispositions


def render(post_rows, dismissals, supplementary=False):
    if supplementary and not post_rows and not dismissals:
        return ("# Supplementary witness outcomes\n\n"
                "No supplementary mapped witness outcomes.\n")
    lines = ["# Supplementary witness outcomes" if supplementary
             else "# Witness outcomes", "",
             "| " + " | ".join(POST_COLS) + " |",
             "| " + " | ".join(["---"] * len(POST_COLS)) + " |"]
    for row in post_rows:
        lines.append("| " + " | ".join(str(row[col]).replace("|", "\\|")
                                           for col in POST_COLS) + " |")
    lines += ["", "### Assembled dismissals", ""]
    if dismissals:
        lines += ["| Error ID |", "| --- |"] + [f"| {eid} |" for eid in dismissals]
    else:
        lines.append(DISMISSAL_ZERO)
    return "\n".join(lines) + "\n"


def _write_atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _apply_dismissals(register_path, dismissals):
    text = register_path.read_text(encoding="utf-8")
    tables = registers.parse_tables(text)
    target = next(((headers, rows) for headers, rows, _line in tables
                   if headers == registers.ERROR_COLS), None)
    if target is None:
        raise BoundaryError(f"{register_path}: code-error register table not found")
    headers, rows = target
    changed = []
    for row in rows:
        values = list(row)
        data = dict(zip(headers, values))
        if data["Error ID"] in dismissals:
            values[headers.index("Status")] = "not_error"
            values[headers.index("Severity")] = ""
        changed.append(values)
    replacement = registers_table(headers, changed)
    old = registers_table(headers, rows)
    if old not in text:
        raise BoundaryError(f"{register_path}: cannot locate exact register table for update")
    _write_atomic(register_path, text.replace(old, replacement, 1))


def _check_dispositions(register_path, dispositions):
    """Symmetric b9 check: every mapped/descendant row carries its ledger disposition.

    Both directions are refused — a dismissal that was not applied, and a row
    hand-flipped to a status (or severity) its sole ledger disposition never
    authorized, `not_error` included.
    """
    register = _register(register_path)
    for error_id, (status, severity) in sorted(dispositions.items()):
        row = register.get(error_id)
        if row is None:
            raise BoundaryError(
                f"{register_path}: mapped Error ID {error_id} is absent from the canonical register"
            )
        actual_status = (row.get("Status") or "").strip()
        actual_severity = (row.get("Severity") or "").strip()
        if actual_status != status:
            raise BoundaryError(
                f"{register_path}: mapped Error ID {error_id} final status {actual_status!r} "
                f"disagrees with its ledger disposition {status!r}"
            )
        if _blank(severity):
            if not _blank(actual_severity):
                raise BoundaryError(
                    f"{register_path}: mapped Error ID {error_id} final severity "
                    f"{actual_severity!r} disagrees with its ledger disposition (must be empty)"
                )
        elif actual_severity != severity:
            raise BoundaryError(
                f"{register_path}: mapped Error ID {error_id} final severity "
                f"{actual_severity!r} disagrees with its ledger disposition {severity!r}"
            )


def check_boundary(audit, supplementary=False):
    """Re-derive the boundary from promotion-surviving inputs and verify it."""
    if supplementary:
        register_path = next((
            audit / "_run/snapshots" / stage / "code_error_register.md"
            for stage in ("b7", "b8", "bC")
            if (audit / "_run/snapshots" / stage / "code_error_register.md").is_file()
        ), audit / "code_error_register.md")
    else:
        frozen = audit / "_run/snapshots/code_b6b/code_error_register.md"
        register_path = frozen if frozen.is_file() else audit / "code_error_register.md"
    rows, dismissals, dispositions = assemble(audit, register_path, supplementary)
    payload = render(rows, dismissals, supplementary)
    output = audit / ("_run/code_b6b/witness_outcomes.md"
                      if supplementary else "_run/code_b6a/witness_outcomes.md")
    if not output.is_file() or output.read_text(encoding="utf-8") != payload:
        raise BoundaryError(f"{output}: persisted boundary disagrees with re-derived inputs")
    _check_dispositions(register_path, dispositions)
    return output


def registers_table(columns, rows):
    lines = ["| " + " | ".join(columns) + " |",
             "| " + " | ".join(["---"] * len(columns)) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_root", type=Path)
    parser.add_argument("--audit-dir", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--supplementary", action="store_true")
    args = parser.parse_args()
    root = args.package_root.expanduser().resolve()
    audit = (args.audit_dir or root / "audit").expanduser().resolve()
    output = audit / ("_run/code_b6b/witness_outcomes.md"
                      if args.supplementary else "_run/code_b6a/witness_outcomes.md")
    try:
        if args.check:
            check_boundary(audit, args.supplementary)
        else:
            register_path = audit / "_staging/code_error_register.md"
            rows, dismissals, _dispositions = assemble(
                audit, register_path, args.supplementary)
            _apply_dismissals(register_path, dismissals)
            _write_atomic(output, render(rows, dismissals, args.supplementary))
    except (BoundaryError, detector_mapping.MappingError,
            mechanisms.MechanismSchemaError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{'checked' if args.check else 'assembled'} boundary: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
