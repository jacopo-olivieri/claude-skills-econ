#!/usr/bin/env python3
"""Shared schemas and allocation helpers for U7 claim handoffs."""

import re
from pathlib import Path

import lint_registers as registers


CLAIMS_PLAN_COLS = [
    "Worker ID", "Paper Scope", "Paper File", "Line Intervals",
    "Likely Code Scope", "Shard File", "Claim ID Range", "Output ID Range",
    "H ID Range", "Review Focus",
]
HANDOFF_COLS = [
    "H ID", "Anchor", "Quote", "Asserted Substance", "Referenced Objects",
]
X_COVERAGE_COLS = [
    "X ID", "Outcome", "C-ID / Reason", "Evidence", "Covering Range",
    "Covering Quote",
]
HANDOFF_RESOLUTION_COLS = HANDOFF_COLS + [
    "Resolution", "C-ID / Reason", "Evidence", "Covering Range", "Covering Quote",
]
H_RANGE_RE = re.compile(r"^(H-\d{4})\s*[–—-]\s*(H-\d{4})$")
LINE_INTERVAL_RE = re.compile(r"^(\d+)\s*[–—-]\s*(\d+)$")
ADJUDICATION_RANGE_RE = re.compile(
    r"^Adjudication range:\s*(C-\d{4})\s*[–—-]\s*(C-\d{4})\s*$", re.M
)
DISPOSITION_FIELDS = {
    "bare_pointer": {"sentence", "no_checkable_predicate"},
    "duplicate_of_covered": {"covering_obligation", "covering_c_id"},
    "non_checkable": {"sentence", "why_no_artifact"},
    "out_of_audit_scope": {"points_to"},
}


def parse_h_range(value):
    match = H_RANGE_RE.fullmatch(str(value or "").strip())
    if not match:
        return None
    start, end = int(match.group(1)[2:]), int(match.group(2)[2:])
    return ("H", start, end) if start <= end else None


def parse_line_intervals(value):
    intervals = []
    for part in str(value or "").split(","):
        match = LINE_INTERVAL_RE.fullmatch(part.strip())
        if not match:
            raise ValueError(f"invalid line interval {part.strip()!r}")
        start, end = int(match.group(1)), int(match.group(2))
        if start < 1 or end < start:
            raise ValueError(f"invalid line interval {part.strip()!r}")
        intervals.append((start, end))
    if not intervals:
        raise ValueError("line intervals cannot be empty")
    return intervals


def load_claims_allocations(plan_path, exact=True):
    plan_path = Path(plan_path)
    text = plan_path.read_text(encoding="utf-8")
    matches = []
    for headers, rows, _line in registers.parse_tables(text):
        if headers == CLAIMS_PLAN_COLS or (not exact and "Worker ID" in headers
                                          and "Shard File" in headers):
            matches.append((headers, rows))
    if len(matches) != 1:
        raise ValueError(
            f"{plan_path}: expected exactly one claims allocation table with columns "
            + " | ".join(CLAIMS_PLAN_COLS)
        )
    headers, rows = matches[0]
    allocations = []
    for index, row in enumerate(rows, start=1):
        if len(row) != len(headers):
            raise ValueError(f"{plan_path}: malformed allocation row {index}")
        allocations.append(dict(zip(headers, row)))
    return allocations, text


def source_aliases(entry, package_root=None):
    path = Path(entry["source_path"])
    aliases = {str(path), path.as_posix(), path.name}
    if package_root is not None:
        try:
            rel = path.resolve().relative_to(Path(package_root).resolve())
            aliases.update({str(rel), rel.as_posix()})
        except ValueError:
            pass
    return aliases


def allocation_source_entry(allocation, source_set, package_root=None):
    matches = [entry for entry in source_set
               if allocation["Paper File"].strip().strip("`") in
               source_aliases(entry, package_root)]
    if len(matches) != 1:
        raise ValueError(
            f"{allocation['Worker ID']} Paper File resolves to {len(matches)} source files"
        )
    return matches[0]


def validate_partition(allocations, source_set, package_root=None):
    owners = {}
    for entry in source_set:
        line_count = len(Path(entry["audit_path"]).read_text(
            encoding="utf-8").splitlines())
        owners[entry["source_path"]] = [None] * line_count
    for allocation in allocations:
        entry = allocation_source_entry(allocation, source_set, package_root)
        try:
            intervals = parse_line_intervals(allocation["Line Intervals"])
        except ValueError as exc:
            raise ValueError(f"{allocation['Worker ID']}: {exc}") from exc
        line_owners = owners[entry["source_path"]]
        for start, end in intervals:
            if end > len(line_owners):
                raise ValueError(
                    f"{allocation['Worker ID']} interval {start}-{end} exceeds "
                    f"{len(line_owners)} lines in {entry['source_path']}"
                )
            for line_number in range(start, end + 1):
                old = line_owners[line_number - 1]
                if old is not None:
                    raise ValueError(
                        f"line overlap in {entry['source_path']}:{line_number}: "
                        f"{old} and {allocation['Worker ID']}"
                    )
                line_owners[line_number - 1] = allocation["Worker ID"]
    gaps = []
    for path, line_owners in owners.items():
        gaps.extend(f"{path}:{index}" for index, owner in enumerate(line_owners, start=1)
                    if owner is None)
    if gaps:
        preview = ", ".join(gaps[:10]) + (" ..." if len(gaps) > 10 else "")
        raise ValueError(f"paper allocation has unowned line(s): {preview}")
    return owners


def owner_for_line(allocations, source_set, source_path, line, package_root=None):
    matches = []
    for allocation in allocations:
        entry = allocation_source_entry(allocation, source_set, package_root)
        if Path(entry["source_path"]).resolve() != Path(source_path).resolve():
            continue
        if any(start <= line <= end for start, end in
               parse_line_intervals(allocation["Line Intervals"])):
            matches.append(allocation["Worker ID"])
    if len(matches) != 1:
        raise ValueError(
            f"{source_path}:{line} has {len(matches)} allocation owners"
        )
    return matches[0]


def parse_evidence(value):
    fields = {}
    for part in str(value or "").split(";"):
        if not part.strip():
            continue
        if ":" not in part:
            raise ValueError(f"malformed evidence field {part.strip()!r}")
        key, raw = part.split(":", 1)
        key, raw = key.strip(), raw.strip()
        if not key or not raw or key in fields:
            raise ValueError(f"malformed or duplicate evidence field {key!r}")
        fields[key] = raw
    return fields


def validate_disposition(reason, evidence):
    if reason not in DISPOSITION_FIELDS:
        raise ValueError(f"unknown disposition reason {reason!r}")
    fields = parse_evidence(evidence)
    missing = DISPOSITION_FIELDS[reason] - set(fields)
    if missing:
        raise ValueError(
            f"disposition {reason} missing evidence field(s): {', '.join(sorted(missing))}"
        )
    return fields

