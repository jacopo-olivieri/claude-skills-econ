#!/usr/bin/env python3
"""Boundary lint for research-codebase-audit registers, plans, and shards.

Mechanical enforcement of ``references/registers.md`` at every stage boundary.
Exits 0 on pass (warnings allowed), nonzero with a findings report on failure.

Usage:
    lint_registers.py --stage STAGE [--shard PATH] [--audit-dir audit]

Stages: b0, b1-claims, b1-code, b2-claims, b2-code, b3-claims, b3-code,
        b4-claims, b4-code, b5-claims, b5-code, b6-claims, b6-code, b7, b8, b9
(b2/b5 lint one worker shard, passed with --shard).
"""

import argparse
import json
import re
import sys
from pathlib import Path

# --------------------------------------------------------------- constants

CLAIMS_COLS = [
    "Claim ID", "Paper Context", "Paper Quote", "Used in Text", "Claim Type",
    "Claim Text", "Code/Data Source", "Output IDs", "Status", "Severity",
    "Issue Description", "Blocked Check", "Related Error IDs",
]
OUTPUT_COLS = [
    "Output ID", "Paper Object", "Paper Context", "Paper Location",
    "Output Path/Pattern", "Producing Script", "Input Dataset(s)",
    "Key Spec/Sample", "Claim IDs", "Status",
]
ERROR_COLS = [
    "Error ID", "Error Type", "Code/Data Source", "Code Location", "Status",
    "Severity", "Error Description", "Why It Matters", "Related Claim IDs",
]
LEDGER_COLS = [
    "ID", "Current Status", "Current Severity", "Evidence Checked",
    "Evidence Level", "Verdict", "Proposed Register Change",
    "Pipeline/Output Impact", "Proposed Note",
]

CLAIM_TYPES = {
    "quantitative_result", "sample_count", "treatment_definition",
    "estimation_specification", "robustness", "data_construction",
    "interpretation", "transcription", "rounding_or_precision",
}
ERROR_TYPES = {
    "syntax_or_parse_error", "missing_input_or_output", "stale_or_wrong_path",
    "undefined_variable_or_global", "merge_key_or_cardinality_error",
    "sample_filter_or_flag_error", "treatment_or_event_timing_error",
    "aggregation_or_unit_error", "output_label_or_path_mismatch",
    "version_or_dependency_error", "randomness_or_seed_error",
    "inference_or_se_specification", "weighting_error",
    "readme_or_package_mismatch", "pii_or_disclosure_risk",
}
CLAIMS_STATUS_FIRST = {"confirmed", "mapped", "unclear", "inconsistent", "blocked"}
CLAIMS_STATUS_FINAL = CLAIMS_STATUS_FIRST | {"confirmation_needed"}
OUTPUT_STATUS_FIRST = {"listed", "mapped", "confirmed", "orphan", "inconsistent", "unclear"}
OUTPUT_STATUS_FINAL = OUTPUT_STATUS_FIRST
ERROR_STATUS_FIRST = {"candidate", "confirmed", "not_error", "blocked"}
ERROR_STATUS_FINAL = (ERROR_STATUS_FIRST | {"confirmation_needed"})

CLAIMS_VERDICTS = {
    "substantiated", "substantiated_but_reframe", "row_note_only",
    "not_substantiated", "confirmation_needed", "blocked",
}
ERROR_VERDICTS = {"confirmed_error", "not_error", "confirmation_needed", "blocked", "deferred"}
EVIDENCE_LEVELS = {
    "static_source_verified", "artifact_verified", "data_inspected_verified",
    "parser_or_runtime_verified", "synthetic_test_verified",
    "targeted_rerun_verified", "blocked_documented",
}

ID_RE = {"C": r"C-\d{4}", "O": r"O-\d{4}", "E": r"E-\d{4}"}
RANGE_RE = re.compile(r"([CEO]-\d{4})\s*[–—-]\s*([CEO]-\d{4})")
COORD_RE = re.compile(r"Merge-coordinator range:\s*([CEO]-\d{4})\s*[–—-]\s*([CEO]-\d{4})")
def has_conflict_markers(text):
    starts = re.search(r"^<{7}(\s|$)", text, re.M)
    ends = re.search(r"^>{7}(\s|$)", text, re.M)
    return bool(starts or ends)

SNAP_KEY = {
    "b3-claims": "claims_b3", "b6-claims": "claims_b6",
    "b3-code": "code_b3", "b6-code": "code_b6", "b7": "b7", "b8": "b8",
    "b3b-claims": "claims_b3b", "b3b-code": "code_b3b",
}


class Lint:
    def __init__(self):
        self.errors, self.warnings = [], []

    def fail(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def finish(self, stage):
        for w in self.warnings:
            print(f"WARNING [{stage}]: {w}")
        if self.errors:
            print(f"LINT FAIL [{stage}] — {len(self.errors)} finding(s):")
            for e in self.errors:
                print(f"  - {e}")
            return 1
        print(f"LINT PASS [{stage}]")
        return 0


# --------------------------------------------------------------- md parsing


def read_text(lint, path):
    if not path.is_file() or path.stat().st_size == 0:
        lint.fail(f"missing or empty file: {path}")
        return None
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        lint.fail(f"not valid UTF-8: {path}")
        return None
    if has_conflict_markers(text):
        lint.fail(f"conflict marker in {path}")
    return text


def split_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    cells, cur, esc = [], [], False
    for ch in line:
        if esc:
            cur.append(ch)
            esc = False
        elif ch == "\\":
            cur.append(ch)
            esc = True
        elif ch == "|":
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    cells.append("".join(cur).strip())
    return cells


def parse_tables(text):
    """All Markdown tables in *text* -> list of (headers, rows, start_line)."""
    lines = text.split("\n")
    tables, i = [], 0
    while i < len(lines) - 1:
        if lines[i].lstrip().startswith("|") and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            headers = split_row(lines[i])
            rows, j = [], i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                rows.append(split_row(lines[j]))
                j += 1
            tables.append((headers, rows, i + 1))
            i = j
        else:
            i += 1
    return tables


def table_by_cols(lint, path, text, expected_cols, label):
    for headers, rows, line in parse_tables(text):
        if headers == expected_cols:
            bad = [k for k, r in enumerate(rows) if len(r) != len(headers)]
            for k in bad:
                lint.fail(f"{path}: {label} row {k + 1} has {len(rows[k])} cells, expected {len(headers)}")
            return [r for k, r in enumerate(rows) if k not in bad]
    lint.fail(f"{path}: no table with exact {label} columns found")
    return None


def col(rows, cols, name):
    i = cols.index(name)
    return [r[i] for r in rows]


def ids_in(text, letter):
    return re.findall(rf"\b{ID_RE[letter]}\b", text)


def parse_range(s):
    m = RANGE_RE.search(s or "")
    if not m or m.group(1)[0] != m.group(2)[0]:
        return None
    return m.group(1)[0], int(m.group(1)[2:]), int(m.group(2)[2:])


def in_ranges(idstr, ranges):
    letter, num = idstr[0], int(idstr[2:])
    return any(l == letter and a <= num <= b for l, a, b in ranges)


def is_example_row(row):
    return any(re.fullmatch(r"[CEO]-0000", c) for c in row[:1])


def check_abs_paths(lint, path, rows, cols, path_cols):
    for name in path_cols:
        if name not in cols:
            continue
        for v in col(rows, cols, name):
            for token in re.split(r"[;,\s]+", v):
                if token.startswith("/") or token.startswith("~") or re.match(r"^[A-Za-z]:\\", token):
                    lint.fail(f"{path}: absolute path '{token}' in column '{name}' (repo-relative required)")


# --------------------------------------------------------------- vocab checks


def check_claims_rows(lint, path, rows, final=False):
    statuses = CLAIMS_STATUS_FINAL if final else CLAIMS_STATUS_FIRST
    for r in rows:
        d = dict(zip(CLAIMS_COLS, r))
        cid = d["Claim ID"]
        if not re.fullmatch(ID_RE["C"], cid):
            lint.fail(f"{path}: bad Claim ID '{cid}'")
        st = d["Status"]
        ok = st in statuses or (final and re.fullmatch(r"duplicate_of:C-\d{4}", st))
        if not ok:
            lint.fail(f"{path}: {cid} invalid status '{st}'")
        if d["Claim Type"] not in CLAIM_TYPES:
            lint.fail(f"{path}: {cid} invalid claim type '{d['Claim Type']}'")
        if not d["Paper Quote"]:
            lint.fail(f"{path}: {cid} empty Paper Quote")
        if d["Used in Text"] not in {"TRUE", "FALSE"}:
            lint.fail(f"{path}: {cid} Used in Text must be TRUE/FALSE")
        sev, issue = d["Severity"], d["Issue Description"]
        if bool(sev) != bool(issue):
            lint.fail(f"{path}: {cid} Severity/Issue Description biconditional violated")
        if (st == "blocked") != bool(d["Blocked Check"]):
            lint.fail(f"{path}: {cid} Blocked Check must be non-empty iff Status is 'blocked' (status='{st}')")
        if sev and sev not in {"1", "2", "3", "4"}:
            lint.fail(f"{path}: {cid} Severity '{sev}' not in 1-4")
        if d["Used in Text"] == "FALSE" and sev and sev != "1":
            lint.fail(f"{path}: {cid} Used in Text=FALSE cannot carry Severity > 1")


def check_output_rows(lint, path, rows, final=False):
    statuses = OUTPUT_STATUS_FINAL if final else OUTPUT_STATUS_FIRST
    for r in rows:
        d = dict(zip(OUTPUT_COLS, r))
        oid = d["Output ID"]
        if not re.fullmatch(ID_RE["O"], oid):
            lint.fail(f"{path}: bad Output ID '{oid}'")
        st = d["Status"]
        ok = st in statuses or (final and re.fullmatch(r"duplicate_of:O-\d{4}", st))
        if not ok:
            lint.fail(f"{path}: {oid} invalid status '{st}'")


def check_error_rows(lint, path, rows, final=False):
    statuses = ERROR_STATUS_FINAL if final else ERROR_STATUS_FIRST
    for r in rows:
        d = dict(zip(ERROR_COLS, r))
        eid = d["Error ID"]
        if not re.fullmatch(ID_RE["E"], eid):
            lint.fail(f"{path}: bad Error ID '{eid}'")
        st = d["Status"]
        is_dup = bool(re.fullmatch(r"duplicate_of:E-\d{4}", st))
        if not (st in statuses or (final and is_dup)):
            lint.fail(f"{path}: {eid} invalid status '{st}'")
        if d["Error Type"] not in ERROR_TYPES:
            lint.fail(f"{path}: {eid} invalid error type '{d['Error Type']}'")
        sev = d["Severity"]
        needs_sev = st in {"candidate", "confirmed", "confirmation_needed", "blocked"}
        if needs_sev != bool(sev):
            lint.fail(f"{path}: {eid} Severity must be filled iff status is candidate/confirmed/confirmation_needed/blocked (status='{st}')")
        if sev and sev not in {"1", "2", "3", "4"}:
            lint.fail(f"{path}: {eid} Severity '{sev}' not in 1-4")


def check_unique(lint, path, ids, label):
    seen = set()
    for i in ids:
        if i in seen:
            lint.fail(f"{path}: duplicate {label} '{i}'")
        seen.add(i)


def check_bidirectional(lint, a_rows, a_cols, a_id, a_link, b_rows, b_cols, b_id, b_link, label):
    def links(rows, cols, idc, linkc):
        out = {}
        for r in rows:
            d = dict(zip(cols, r))
            out[d[idc]] = set(re.findall(r"[CEO]-\d{4}", d[linkc]))
        return out

    fwd, back = links(a_rows, a_cols, a_id, a_link), links(b_rows, b_cols, b_id, b_link)
    for aid, targets in fwd.items():
        for t in targets:
            if t not in back:
                lint.fail(f"{label}: {aid} links {t}, which does not exist")
            elif aid not in back[t]:
                lint.fail(f"{label}: one-way link {aid} -> {t} (reverse missing)")
    for bid, targets in back.items():
        for t in targets:
            if t not in fwd:
                lint.fail(f"{label}: {bid} links {t}, which does not exist")
            elif bid not in fwd[t]:
                lint.fail(f"{label}: one-way link {bid} -> {t} (reverse missing)")


# --------------------------------------------------------------- plan parsing


def parse_plan(lint, path, key_col):
    """Parse an allocation table keyed by *key_col*; return list of row dicts + coord ranges."""
    text = read_text(lint, path)
    if text is None:
        return None, []
    for headers, rows, _ in parse_tables(text):
        if key_col in headers and "Shard File" in headers:
            alloc = []
            for k, r in enumerate(rows):
                if len(r) != len(headers):
                    lint.fail(f"{path}: allocation row {k + 1} has {len(r)} cells, expected {len(headers)}")
                else:
                    alloc.append(dict(zip(headers, r)))
            coord = [parse_range(f"{a}–{b}") for a, b in COORD_RE.findall(text)]
            return alloc, [c for c in coord if c]
    lint.fail(f"{path}: allocation table with '{key_col}' and 'Shard File' not found")
    return None, []


def alloc_ranges(lint, path, alloc, range_cols):
    ranges = []
    for row in alloc:
        for rc in range_cols:
            pr = parse_range(row.get(rc, ""))
            if pr is None:
                lint.fail(f"{path}: unparseable {rc} '{row.get(rc, '')}' for {row.get('Worker ID') or row.get('Chunk ID')}")
            else:
                ranges.append(pr)
    return ranges


def check_disjoint(lint, path, ranges):
    by_letter = {}
    for l, a, b in ranges:
        by_letter.setdefault(l, []).append((a, b))
    for l, spans in by_letter.items():
        spans.sort()
        for (a1, b1), (a2, b2) in zip(spans, spans[1:]):
            if a2 <= b1:
                lint.fail(f"{path}: overlapping {l}- ID ranges {a1}-{b1} and {a2}-{b2}")


def scope_tokens(cell):
    return {t.strip().strip("`") for t in re.split(r"[;,]", cell or "") if t.strip()}


# --------------------------------------------------------------- stage checks


def stage_b0(lint, audit, manifest):
    for f, cols in [
        ("claims_register.md", CLAIMS_COLS),
        ("output_register.md", OUTPUT_COLS),
        ("code_error_register.md", ERROR_COLS),
    ]:
        text = read_text(lint, audit / f)
        if text is None:
            continue
        rows = table_by_cols(lint, audit / f, text, cols, f)
        if rows:
            real = [r for r in rows if not is_example_row(r)]
            if real:
                lint.fail(f"{audit / f}: register must be empty at b0 (found {len(real)} rows)")
    if read_text(lint, audit / "audit_readme.md") is None:
        pass
    cm = read_text(lint, audit / "CODEMAP.md")
    if cm is not None:
        for letter in "SDB":
            found = re.findall(rf"\b{letter}-\d{{4}}\b", cm)
            check_unique(lint, audit / "CODEMAP.md", found, f"{letter}- ID")
        if not re.search(r"PRECONDITIONS:\s*\d\s*/\s*5", cm):
            lint.fail(f"{audit / 'CODEMAP.md'}: missing 'PRECONDITIONS: <n>/5' score line")
    if manifest:
        src, blanked = manifest.get("paper_source_path"), manifest.get("paper_audit_path")
        if src and Path(src).suffix == ".tex":
            if not blanked or blanked == src:
                lint.fail("manifest: .tex paper requires a distinct paper_audit_path (blanked copy)")
            elif not Path(blanked).is_file():
                lint.fail(f"blanked paper missing: {blanked}")
            elif not Path(src).is_file():
                lint.fail(f"paper source missing: {src}")
            else:
                n_src = Path(src).read_text(encoding="utf-8").count("\n")
                n_bl = Path(blanked).read_text(encoding="utf-8").count("\n")
                if n_src != n_bl:
                    lint.fail(f"blanked paper line count {n_bl} != source {n_src}")


def stage_b1(lint, audit, stream):
    if stream == "claims":
        plan = audit / "plans" / "claims_review_plan.md"
        alloc, coord = parse_plan(lint, plan, "Worker ID")
        if alloc is None:
            return
        check_unique(lint, plan, [a["Worker ID"] for a in alloc], "Worker ID")
        check_unique(lint, plan, [a["Shard File"] for a in alloc], "Shard File")
        ranges = alloc_ranges(lint, plan, alloc, ["Claim ID Range", "Output ID Range"])
        check_disjoint(lint, plan, ranges + coord)
        if len([c for c in coord if c[0] == "C"]) != 1 or len([c for c in coord if c[0] == "O"]) != 1:
            lint.fail(f"{plan}: expected exactly one merge-coordinator range each for C- and O-")
    else:
        plan = audit / "plans" / "code_error_review_plan.md"
        alloc, coord = parse_plan(lint, plan, "Chunk ID")
        if alloc is None:
            return
        check_unique(lint, plan, [a["Chunk ID"] for a in alloc], "Chunk ID")
        check_unique(lint, plan, [a["Shard File"] for a in alloc], "Shard File")
        ranges = alloc_ranges(lint, plan, alloc, ["Error ID Range"])
        check_disjoint(lint, plan, ranges + coord)
        if len([c for c in coord if c[0] == "E"]) != 1:
            lint.fail(f"{plan}: expected exactly one merge-coordinator range for E-")
        # every inventory script in exactly one chunk (token match, not substring)
        text = plan.read_text(encoding="utf-8")
        inv = None
        for headers, rows, _ in parse_tables(text):
            if "Script" in headers and "Chunk" in headers:
                inv = []
                for k, r in enumerate(rows):
                    if len(r) != len(headers):
                        lint.fail(f"{plan}: inventory row {k + 1} has {len(r)} cells, expected {len(headers)}")
                    else:
                        inv.append(dict(zip(headers, r)))
                break
        if inv is None:
            lint.fail(f"{plan}: script inventory table (with 'Script' and 'Chunk' columns) not found")
        else:
            for row in inv:
                script = row["Script"].strip("`")
                n = sum(1 for a in alloc if script in scope_tokens(a["Script Scope"]))
                if n != 1:
                    lint.fail(f"{plan}: inventory script '{script}' appears in {n} chunks (expected exactly 1)")


def shard_footer(lint, path, text):
    low = text.lower()
    if "coverage" not in low:
        lint.fail(f"{path}: missing coverage note in shard footer")
    if "coordinator notes" not in low:
        lint.fail(f"{path}: missing coordinator-notes footer")


def find_alloc_for_shard(alloc, shard):
    for a in alloc or []:
        if a["Shard File"].strip("`") == str(shard) or str(shard).endswith(a["Shard File"].strip("`")):
            return a
    return None


def stage_b2(lint, audit, stream, shard):
    if shard is None:
        lint.fail("b2 requires --shard")
        return
    text = read_text(lint, shard)
    if text is None:
        return
    if stream == "claims":
        alloc, _ = parse_plan(lint, audit / "plans" / "claims_review_plan.md", "Worker ID")
        a = find_alloc_for_shard(alloc, shard)
        if a is None:
            lint.fail(f"{shard}: not found in the plan's allocation table")
            return
        ranges = [parse_range(a["Claim ID Range"]), parse_range(a["Output ID Range"])]
        ranges = [r for r in ranges if r]
        c_rows = table_by_cols(lint, shard, text, CLAIMS_COLS, "claims")
        o_rows = table_by_cols(lint, shard, text, OUTPUT_COLS, "outputs")
        if c_rows is None or o_rows is None:
            return
        check_claims_rows(lint, shard, c_rows)
        check_output_rows(lint, shard, o_rows)
        cids = col(c_rows, CLAIMS_COLS, "Claim ID")
        oids = col(o_rows, OUTPUT_COLS, "Output ID")
        check_unique(lint, shard, cids + oids, "ID")
        for i in cids + oids:
            if not in_ranges(i, ranges):
                lint.fail(f"{shard}: {i} outside assigned ranges")
        for v in col(c_rows, CLAIMS_COLS, "Related Error IDs"):
            if v:
                lint.fail(f"{shard}: Related Error IDs must be empty at b2")
        oset = set(oids)
        for r in c_rows:
            d = dict(zip(CLAIMS_COLS, r))
            for o in re.findall(r"O-\d{4}", d["Output IDs"]):
                if o not in oset:
                    lint.fail(f"{shard}: {d['Claim ID']} references {o} not present in shard")
        check_bidirectional(
            lint, c_rows, CLAIMS_COLS, "Claim ID", "Output IDs",
            o_rows, OUTPUT_COLS, "Output ID", "Claim IDs", f"{shard} C<->O",
        )
        check_abs_paths(lint, shard, c_rows, CLAIMS_COLS, ["Code/Data Source"])
        check_abs_paths(lint, shard, o_rows, OUTPUT_COLS, ["Output Path/Pattern", "Producing Script"])
    else:
        alloc, _ = parse_plan(lint, audit / "plans" / "code_error_review_plan.md", "Chunk ID")
        a = find_alloc_for_shard(alloc, shard)
        if a is None:
            lint.fail(f"{shard}: not found in the plan's allocation table")
            return
        ranges = [r for r in [parse_range(a["Error ID Range"])] if r]
        e_rows = table_by_cols(lint, shard, text, ERROR_COLS, "code errors")
        if e_rows is None:
            return
        check_error_rows(lint, shard, e_rows)
        eids = col(e_rows, ERROR_COLS, "Error ID")
        check_unique(lint, shard, eids, "Error ID")
        for i in eids:
            if not in_ranges(i, ranges):
                lint.fail(f"{shard}: {i} outside assigned range")
        for v in col(e_rows, ERROR_COLS, "Related Claim IDs"):
            if v:
                lint.fail(f"{shard}: Related Claim IDs must be empty at b2")
        check_abs_paths(lint, shard, e_rows, ERROR_COLS, ["Code/Data Source", "Code Location"])
    shard_footer(lint, shard, text)


def load_register(lint, path, cols, allow_extra=False):
    text = read_text(lint, path)
    if text is None:
        return None
    if allow_extra:
        for headers, rows, _ in parse_tables(text):
            if set(cols) <= set(headers):
                return headers, rows
        lint.fail(f"{path}: no table containing required columns")
        return None
    rows = table_by_cols(lint, path, text, cols, path.name)
    if rows is None:
        return None
    return cols, [r for r in rows if not is_example_row(r)]


def stage_b3(lint, audit, stream):
    staging = audit / "_staging"
    if stream == "claims":
        plan = audit / "plans" / "claims_review_plan.md"
        alloc, _ = parse_plan(lint, plan, "Worker ID")
        ranges = alloc_ranges(lint, plan, alloc or [], ["Claim ID Range", "Output ID Range"]) if alloc else []
        c = load_register(lint, staging / "claims_register.md", CLAIMS_COLS)
        o = load_register(lint, staging / "output_register.md", OUTPUT_COLS)
        report_path = audit / "_run" / "merge_report_claims.json"
        if c is None or o is None:
            return
        _, c_rows = c
        _, o_rows = o
        check_claims_rows(lint, staging / "claims_register.md", c_rows)
        check_output_rows(lint, staging / "output_register.md", o_rows)
        cids = col(c_rows, CLAIMS_COLS, "Claim ID")
        oids = col(o_rows, OUTPUT_COLS, "Output ID")
        check_unique(lint, staging, cids + oids, "ID")
        for i in cids + oids:
            if ranges and not in_ranges(i, ranges):
                lint.fail(f"staging: {i} outside union of planned worker ranges")
        for v in col(c_rows, CLAIMS_COLS, "Related Error IDs"):
            if v:
                lint.fail("staging claims: Related Error IDs must still be blank at b3")
        check_bidirectional(
            lint, c_rows, CLAIMS_COLS, "Claim ID", "Output IDs",
            o_rows, OUTPUT_COLS, "Output ID", "Claim IDs", "b3 C<->O",
        )
        counts = {"claims_register.md": len(c_rows), "output_register.md": len(o_rows)}
    else:
        plan = audit / "plans" / "code_error_review_plan.md"
        alloc, _ = parse_plan(lint, plan, "Chunk ID")
        ranges = alloc_ranges(lint, plan, alloc or [], ["Error ID Range"]) if alloc else []
        e = load_register(lint, staging / "code_error_register.md", ERROR_COLS)
        report_path = audit / "_run" / "merge_report_code.json"
        if e is None:
            return
        _, e_rows = e
        check_error_rows(lint, staging / "code_error_register.md", e_rows)
        eids = col(e_rows, ERROR_COLS, "Error ID")
        check_unique(lint, staging, eids, "Error ID")
        for i in eids:
            if ranges and not in_ranges(i, ranges):
                lint.fail(f"staging: {i} outside union of planned chunk ranges")
        for v in col(e_rows, ERROR_COLS, "Related Claim IDs"):
            if v:
                lint.fail("staging errors: Related Claim IDs must still be blank at b3")
        # coverage: every inventory script has a coverage-table row in some shard
        text = plan.read_text(encoding="utf-8") if plan.is_file() else ""
        scripts = []
        for headers, rows, _ in parse_tables(text):
            if "Script" in headers and "Chunk" in headers:
                scripts = [dict(zip(headers, r))["Script"].strip("`") for r in rows if len(r) == len(headers)]
                break
        covered = set()
        for p in sorted((audit / "_code_errors").glob("*.md")):
            for headers, rows, _ in parse_tables(p.read_text(encoding="utf-8", errors="replace")):
                if "Script" in headers and "Outcome" in headers:
                    si = headers.index("Script")
                    covered |= {r[si].strip().strip("`") for r in rows if len(r) == len(headers)}
        for s in scripts:
            if s and s not in covered:
                lint.fail(f"coverage: inventory script '{s}' has no coverage-table row in any code shard")
        counts = {"code_error_register.md": len(e_rows)}
    rep_text = read_text(lint, report_path)
    if rep_text is None:
        return
    try:
        rep = json.loads(rep_text)
    except json.JSONDecodeError as exc:
        lint.fail(f"{report_path}: invalid JSON ({exc})")
        return
    for reg, n in counts.items():
        entry = rep.get(reg)
        if not isinstance(entry, dict):
            lint.fail(f"{report_path}: missing per-register entry '{reg}'")
            continue
        try:
            sr, dd, ad = int(entry["shard_rows"]), int(entry["dedup_removed"]), int(entry["added"])
        except (KeyError, ValueError, TypeError):
            lint.fail(f"{report_path}: '{reg}' must carry integer shard_rows/dedup_removed/added")
            continue
        if sr - dd != ad:
            lint.fail(f"{report_path}: '{reg}' identity violated: {sr} - {dd} != {ad}")
        if ad != n:
            lint.fail(f"{report_path}: '{reg}' added={ad} but staging register has {n} rows")
        for key in ("conflicts", "coverage_gaps", "blocked_shards"):
            if not isinstance(entry.get(key), list):
                lint.fail(f"{report_path}: '{reg}' must carry list-valued '{key}'")


def stage_b3b(lint, audit, stream):
    """Second-read recall sweep merge: new rows only, all unverified candidates, no b3 row
    deleted or mutated. Compares staging against the pre-sweep (b3b) snapshot."""
    snap = audit / "_run" / "snapshots" / SNAP_KEY[f"b3b-{stream}"]
    staging = audit / "_staging"
    if stream == "claims":
        plan = audit / "plans" / "claims_second_read_plan.md"
        alloc, _ = parse_plan(lint, plan, "Worker ID")
        ranges = alloc_ranges(lint, plan, alloc or [], ["Claim ID Range", "Output ID Range"]) if alloc else []
        files = [("claims_register.md", CLAIMS_COLS, "Claim ID"), ("output_register.md", OUTPUT_COLS, "Output ID")]
        report_path = audit / "_run" / "merge_report_claims_b3b.json"
        b1_plan = audit / "plans" / "claims_review_plan.md"
        b1_alloc, b1_coord = parse_plan(lint, b1_plan, "Worker ID")
        b1_ranges = alloc_ranges(lint, b1_plan, b1_alloc or [], ["Claim ID Range", "Output ID Range"]) if b1_alloc else []
    else:
        plan = audit / "plans" / "code_error_second_read_plan.md"
        alloc, _ = parse_plan(lint, plan, "Worker ID")
        ranges = alloc_ranges(lint, plan, alloc or [], ["Error ID Range"]) if alloc else []
        files = [("code_error_register.md", ERROR_COLS, "Error ID")]
        report_path = audit / "_run" / "merge_report_code_b3b.json"
        b1_plan = audit / "plans" / "code_error_review_plan.md"
        b1_alloc, b1_coord = parse_plan(lint, b1_plan, "Chunk ID")
        b1_ranges = alloc_ranges(lint, b1_plan, b1_alloc or [], ["Error ID Range"]) if b1_alloc else []
    # machinery (a): b3b ranges disjoint from b1 ranges, the merge-coordinator range, and each other
    check_disjoint(lint, plan, ranges + b1_ranges + b1_coord)

    total_new = 0
    for f, cols, idc in files:
        st = load_register(lint, staging / f, cols)
        sn = load_register(lint, snap / f, cols)
        if st is None or sn is None:
            continue
        _, st_rows = st
        _, sn_rows = sn
        if f == "claims_register.md":
            check_claims_rows(lint, staging / f, st_rows)
        elif f == "output_register.md":
            check_output_rows(lint, staging / f, st_rows)
        else:
            check_error_rows(lint, staging / f, st_rows)
        st_ids = col(st_rows, cols, idc)
        check_unique(lint, staging / f, st_ids, idc)
        st_by = {dict(zip(cols, r))[idc]: dict(zip(cols, r)) for r in st_rows}
        sn_by = {dict(zip(cols, r))[idc]: dict(zip(cols, r)) for r in sn_rows}
        st_set, sn_set = set(st_by), set(sn_by)
        for i in sorted(sn_set - st_set):
            lint.fail(f"{staging / f}: b3 row {i} deleted at second-read merge (rows are never deleted)")
        for i in sorted(sn_set & st_set):
            for c in cols:
                if st_by[i][c] != sn_by[i][c]:
                    lint.fail(f"{staging / f}: b3 row {i} column '{c}' changed at second-read merge (the sweep only adds rows)")
        new_ids = st_set - sn_set
        total_new += len(new_ids)
        for i in sorted(new_ids):
            if ranges and not in_ranges(i, ranges):
                lint.fail(f"{staging / f}: new second-read row {i} outside the b3b-allocated ranges")
            status = st_by[i]["Status"]
            if f == "code_error_register.md" and status != "candidate":
                lint.fail(f"{staging / f}: new second-read row {i} status '{status}' (must be 'candidate')")
            elif f == "claims_register.md" and status not in {"inconsistent", "unclear"}:
                lint.fail(f"{staging / f}: new second-read claim {i} status '{status}' (must be 'inconsistent' or 'unclear')")
            elif f == "output_register.md" and status not in {"mapped", "orphan", "unclear", "inconsistent"}:
                lint.fail(f"{staging / f}: new second-read output {i} status '{status}' (must be mapped/orphan/unclear/inconsistent)")
        link_col = {"claims_register.md": "Related Error IDs", "code_error_register.md": "Related Claim IDs"}.get(f)
        if link_col:
            for v in col(st_rows, cols, link_col):
                if v:
                    lint.fail(f"{staging / f}: {link_col} must still be blank at b3b (cross-link is a later stage)")
    if stream == "claims":
        c = load_register(lint, staging / "claims_register.md", CLAIMS_COLS)
        o = load_register(lint, staging / "output_register.md", OUTPUT_COLS)
        if c and o:
            check_bidirectional(
                lint, c[1], CLAIMS_COLS, "Claim ID", "Output IDs",
                o[1], OUTPUT_COLS, "Output ID", "Claim IDs", "b3b C<->O",
            )
    rep_text = read_text(lint, report_path)
    if rep_text is None:
        return
    try:
        rep = json.loads(rep_text)
    except json.JSONDecodeError as exc:
        lint.fail(f"{report_path}: invalid JSON ({exc})")
        return
    added_total = 0
    for f, cols, idc in files:
        entry = rep.get(f)
        if not isinstance(entry, dict):
            lint.fail(f"{report_path}: missing per-register entry '{f}'")
            continue
        try:
            sr, dd, ad = int(entry["shard_rows"]), int(entry["dedup_removed"]), int(entry["added"])
        except (KeyError, ValueError, TypeError):
            lint.fail(f"{report_path}: '{f}' must carry integer shard_rows/dedup_removed/added")
            continue
        if sr - dd != ad:
            lint.fail(f"{report_path}: '{f}' identity violated: {sr} - {dd} != {ad}")
        added_total += ad
    if added_total != total_new:
        lint.fail(f"{report_path}: added total {added_total} != {total_new} new row(s) in staging")


def recheck_plan_path(audit, stream):
    return audit / "plans" / ("claims_recheck_plan.md" if stream == "claims" else "code_error_recheck_plan.md")


def parse_recheck_plan(lint, audit, stream):
    plan = recheck_plan_path(audit, stream)
    text = read_text(lint, plan)
    if text is None:
        return None
    inventory, clusters = [], []
    for headers, rows, _ in parse_tables(text):
        if "Reason" in headers and any(h == "ID" for h in headers):
            inventory = [dict(zip(headers, r)) for r in rows if len(r) == len(headers)]
        if "Cluster ID" in headers and "Assigned IDs" in headers and "Shard File" in headers:
            clusters = [dict(zip(headers, r)) for r in rows if len(r) == len(headers)]
    if not inventory:
        lint.fail(f"{plan}: inventory table (columns incl. 'ID' and 'Reason') not found")
    if not clusters:
        lint.fail(f"{plan}: cluster table (Cluster ID / Assigned IDs / Shard File) not found")
    if "audit_readme.md" not in text:
        lint.fail(f"{plan}: missing pointer to the verdict/evidence vocabulary in audit_readme.md")
    return plan, inventory, clusters


def canon_ids(lint, audit, stream):
    ids = set()
    if stream == "claims":
        for f, cols, idc in [("claims_register.md", CLAIMS_COLS, "Claim ID"), ("output_register.md", OUTPUT_COLS, "Output ID")]:
            reg = load_register(lint, audit / f, cols)
            if reg:
                ids |= set(col(reg[1], cols, idc))
    else:
        reg = load_register(lint, audit / "code_error_register.md", ERROR_COLS)
        if reg:
            ids |= set(col(reg[1], ERROR_COLS, "Error ID"))
    return ids


def stage_b4(lint, audit, stream):
    parsed = parse_recheck_plan(lint, audit, stream)
    if parsed is None:
        return
    plan, inventory, clusters = parsed
    canon = canon_ids(lint, audit, stream)
    assignments = {}
    for c in clusters:
        for i in re.findall(r"[CEO]-\d{4}", c["Assigned IDs"]):
            assignments.setdefault(i, []).append(c["Cluster ID"])
    for row in inventory:
        i = row.get("ID", "")
        if i not in canon:
            lint.fail(f"{plan}: inventory ID {i} not found in canonical registers")
        n = len(assignments.get(i, []))
        if n != 1:
            lint.fail(f"{plan}: inventory ID {i} assigned to {n} clusters (expected exactly 1)")
    check_unique(lint, plan, [c["Shard File"] for c in clusters], "cluster Shard File")


def stage_b5(lint, audit, stream, shard, manifest):
    if shard is None:
        lint.fail("b5 requires --shard")
        return
    parsed = parse_recheck_plan(lint, audit, stream)
    if parsed is None:
        return
    plan, _, clusters = parsed
    cluster = None
    for c in clusters:
        if c["Shard File"].strip("`") == str(shard) or str(shard).endswith(c["Shard File"].strip("`")):
            cluster = c
            break
    if cluster is None:
        lint.fail(f"{shard}: not found in the recheck plan's cluster table")
        return
    assigned = set(re.findall(r"[CEO]-\d{4}", cluster["Assigned IDs"]))
    text = read_text(lint, shard)
    if text is None:
        return
    rows = table_by_cols(lint, shard, text, LEDGER_COLS, "recheck ledger")
    if rows is None:
        return
    verdicts = CLAIMS_VERDICTS if stream == "claims" else ERROR_VERDICTS
    seen = []
    evidence_levels = set()
    for r in rows:
        d = dict(zip(LEDGER_COLS, r))
        seen.append(d["ID"])
        if d["ID"] not in assigned:
            lint.fail(f"{shard}: ledger contains unassigned/new ID {d['ID']} (no new IDs at recheck)")
        if d["Verdict"] not in verdicts:
            lint.fail(f"{shard}: {d['ID']} invalid verdict '{d['Verdict']}'")
        if d["Evidence Level"] not in EVIDENCE_LEVELS:
            lint.fail(f"{shard}: {d['ID']} invalid evidence level '{d['Evidence Level']}'")
        evidence_levels.add(d["Evidence Level"])
    check_unique(lint, shard, seen, "ledger ID")
    for i in assigned:
        if i not in seen:
            lint.fail(f"{shard}: assigned ID {i} missing from ledger")
    ladder = int(manifest.get("ladder_level", 1)) if manifest else 1
    if ladder >= 2 and evidence_levels == {"static_source_verified"}:
        lint.warn(f"{shard}: ladder level {ladder} but every check is static_source_verified")


def register_files(audit, stream):
    if stream == "claims":
        return [("claims_register.md", CLAIMS_COLS, "Claim ID"), ("output_register.md", OUTPUT_COLS, "Output ID")]
    return [("code_error_register.md", ERROR_COLS, "Error ID")]


def stage_b6(lint, audit, stream, manifest):
    snap = audit / "_run" / "snapshots" / SNAP_KEY[f"b6-{stream}"]
    staging = audit / "_staging"
    summary = audit / ("claims_recheck_summary.md" if stream == "claims" else "code_error_recheck_summary.md")
    stext = read_text(lint, summary)
    splits = 0
    if stext is not None:
        m = re.search(r"Splits declared:\s*(\d+)", stext)
        m2 = re.search(r"Merges declared:\s*(\d+)", stext)
        if not m or not m2:
            lint.fail(f"{summary}: missing machine-readable 'Splits declared: <n>' / 'Merges declared: <n>' lines")
        else:
            splits = int(m.group(1))
    # merge-coordinator ranges from the stream's b1 plan — the only legal source of new IDs
    if stream == "claims":
        _, coord = parse_plan(lint, audit / "plans" / "claims_review_plan.md", "Worker ID")
    else:
        _, coord = parse_plan(lint, audit / "plans" / "code_error_review_plan.md", "Chunk ID")
    total_new = 0
    for f, cols, idc in register_files(audit, stream):
        st = load_register(lint, staging / f, cols)
        sn = load_register(lint, snap / f, cols)
        if st is None or sn is None:
            continue
        _, st_rows = st
        _, sn_rows = sn
        st_ids = col(st_rows, cols, idc)
        check_unique(lint, staging / f, st_ids, idc)
        st_set, sn_set = set(st_ids), set(col(sn_rows, cols, idc))
        for i in sorted(sn_set - st_set):
            lint.fail(f"{staging / f}: row {i} deleted at recheck merge (rows are never deleted)")
        new_ids = st_set - sn_set
        for i in sorted(new_ids):
            if not coord or not in_ranges(i, coord):
                lint.fail(f"{staging / f}: new ID {i} outside the merge-coordinator range")
        total_new += len(new_ids)
        for r in st_rows:
            s = dict(zip(cols, r))["Status"]
            m_dup = re.fullmatch(r"duplicate_of:([CEO]-\d{4})", s)
            if m_dup and m_dup.group(1) not in st_set:
                lint.fail(f"{staging / f}: duplicate_of target {m_dup.group(1)} not in register")
        if f == "claims_register.md":
            check_claims_rows(lint, staging / f, st_rows, final=True)
        elif f == "output_register.md":
            check_output_rows(lint, staging / f, st_rows, final=True)
        else:
            check_error_rows(lint, staging / f, st_rows, final=True)
            for s in col(st_rows, cols, "Status"):
                if s == "candidate":
                    lint.fail(f"{staging / f}: 'candidate' status must not survive the recheck merge")
    if total_new != splits:
        lint.fail(f"recheck merge: {total_new} new row(s) across registers but 'Splits declared: {splits}'")


def non_link_identical(lint, staging_reg, snap_reg, cols, idc, link_col, label):
    st = {dict(zip(cols, r))[idc]: dict(zip(cols, r)) for r in staging_reg}
    sn = {dict(zip(cols, r))[idc]: dict(zip(cols, r)) for r in snap_reg}
    if set(st) != set(sn):
        lint.fail(f"{label}: ID sets differ between staging and snapshot")
        return
    for i, row in st.items():
        for c in cols:
            if c == link_col:
                continue
            if row[c] != sn[i][c]:
                lint.fail(f"{label}: {i} non-link column '{c}' changed at cross-link")


def confirmed_conflict_links(claim_rows, error_rows, claim_cols=None, error_cols=None):
    """Links pairing a confirmed claim with a confirmed code error (status conflicts)."""
    ccols = claim_cols or CLAIMS_COLS
    ecols = error_cols or ERROR_COLS
    err_status = {
        d["Error ID"]: d.get("Status")
        for d in (dict(zip(ecols, r)) for r in error_rows if not is_example_row(r))
        if d.get("Error ID")
    }
    pairs = []
    for r in claim_rows:
        if is_example_row(r):
            continue
        d = dict(zip(ccols, r))
        if d.get("Status") != "confirmed" or not d.get("Claim ID"):
            continue
        for eid in ids_in(d.get("Related Error IDs", ""), "E"):
            if err_status.get(eid) == "confirmed":
                pairs.append((d["Claim ID"], eid))
    return pairs


def severity_divergence_links(claim_rows, error_rows, claim_cols=None, error_cols=None):
    """Links whose two rows carry filled, differing severities (severity divergences)."""
    ccols = claim_cols or CLAIMS_COLS
    ecols = error_cols or ERROR_COLS
    err_sev = {
        d["Error ID"]: d.get("Severity")
        for d in (dict(zip(ecols, r)) for r in error_rows if not is_example_row(r))
        if d.get("Error ID")
    }
    pairs = []
    for r in claim_rows:
        if is_example_row(r):
            continue
        d = dict(zip(ccols, r))
        if not d.get("Severity") or not d.get("Claim ID"):
            continue
        for eid in ids_in(d.get("Related Error IDs", ""), "E"):
            es = err_sev.get(eid)
            if es and es != d["Severity"]:
                pairs.append((d["Claim ID"], eid))
    return pairs


def check_pairs_listed(lint, summary, section, pairs, stage, reason):
    m = re.search(
        rf"^##\s*{re.escape(section)}\b(.*?)(?=^##\s|\Z)", summary or "", re.M | re.S
    )
    lines = (m.group(1) if m else "").split("\n")
    for cid, eid in pairs:
        if not any(cid in ln and eid in ln for ln in lines):
            lint.fail(
                f"{stage}: {reason} ({cid} <-> {eid}) but no line under "
                f"'## {section}' in register_cross_link_summary.md lists the pair"
            )


def stage_b7(lint, audit):
    snap = audit / "_run" / "snapshots" / "b7"
    staging = audit / "_staging"
    c = load_register(lint, staging / "claims_register.md", CLAIMS_COLS)
    e = load_register(lint, staging / "code_error_register.md", ERROR_COLS)
    cs = load_register(lint, snap / "claims_register.md", CLAIMS_COLS)
    es = load_register(lint, snap / "code_error_register.md", ERROR_COLS)
    if None in (c, e, cs, es):
        return
    non_link_identical(lint, c[1], cs[1], CLAIMS_COLS, "Claim ID", "Related Error IDs", "b7 claims")
    non_link_identical(lint, e[1], es[1], ERROR_COLS, "Error ID", "Related Claim IDs", "b7 errors")
    check_bidirectional(
        lint, c[1], CLAIMS_COLS, "Claim ID", "Related Error IDs",
        e[1], ERROR_COLS, "Error ID", "Related Claim IDs", "b7 C<->E",
    )
    summary = read_text(lint, audit / "register_cross_link_summary.md")
    check_pairs_listed(
        lint, summary, "Status conflicts", confirmed_conflict_links(c[1], e[1]),
        "b7", "confirmed claim linked to confirmed error",
    )
    check_pairs_listed(
        lint, summary, "Severity divergences", severity_divergence_links(c[1], e[1]),
        "b7", "linked pair with differing severities",
    )


REWRITE_PAIRS = {
    "claims_register.md": [("Issue Description", "Issue Description Original")],
    "code_error_register.md": [
        ("Error Description", "Error Description Original"),
        ("Why It Matters", "Why It Matters Original"),
    ],
}


def stage_b8(lint, audit, manifest):
    snap = audit / "_run" / "snapshots" / "b8"
    staging = audit / "_staging"
    mode = (manifest or {}).get("mode", "replication")
    files = ["code_error_register.md"] if mode == "code_errors_only" else ["claims_register.md", "code_error_register.md"]
    if mode != "code_errors_only":
        # the rewrite never touches the output register, but `listed` must be gone by now
        out_reg = load_register(lint, audit / "output_register.md", OUTPUT_COLS)
        if out_reg is not None:
            for r in out_reg[1]:
                d = dict(zip(OUTPUT_COLS, r))
                if d["Status"] == "listed":
                    lint.fail(f"{audit / 'output_register.md'}: {d['Output ID']} still 'listed' at b8 (transient status)")
    base_cols = {"claims_register.md": CLAIMS_COLS, "code_error_register.md": ERROR_COLS}
    idc = {"claims_register.md": "Claim ID", "code_error_register.md": "Error ID"}
    for f in files:
        st = load_register(lint, staging / f, base_cols[f], allow_extra=True)
        sn = load_register(lint, snap / f, base_cols[f])
        if st is None or sn is None:
            continue
        st_headers, st_rows = st
        st_rows = [r for r in st_rows if not is_example_row(r)]
        _, sn_rows = sn
        if any(h in ("Notes", "Notes Original") for h in st_headers):
            lint.fail(f"{staging / f}: Notes columns are forbidden")
        for new_col, orig_col in REWRITE_PAIRS[f]:
            if orig_col not in st_headers:
                lint.fail(f"{staging / f}: missing column '{orig_col}'")
        if len(st_rows) != len(sn_rows):
            lint.fail(f"{staging / f}: row count changed at rewrite ({len(st_rows)} vs {len(sn_rows)})")
            continue
        st_by = {dict(zip(st_headers, r))[idc[f]]: dict(zip(st_headers, r)) for r in st_rows}
        sn_by = {dict(zip(base_cols[f], r))[idc[f]]: dict(zip(base_cols[f], r)) for r in sn_rows}
        if set(st_by) != set(sn_by):
            lint.fail(f"{staging / f}: ID set changed at rewrite")
            continue
        frozen = [c for c in base_cols[f] if c not in [p[0] for p in REWRITE_PAIRS[f]]]
        for i, row in st_by.items():
            for c in frozen:
                if row.get(c, "") != sn_by[i][c]:
                    lint.fail(f"{staging / f}: {i} column '{c}' changed at rewrite")
            for new_col, orig_col in REWRITE_PAIRS[f]:
                orig_val, prior = row.get(orig_col, ""), sn_by[i][new_col]
                if orig_val != prior:
                    lint.fail(f"{staging / f}: {i} '{orig_col}' does not preserve prior text")
                if bool(row.get(new_col, "")) != bool(orig_val):
                    lint.fail(f"{staging / f}: {i} blankness pairing violated for '{new_col}'")
    if mode != "code_errors_only":
        st_c = load_register(lint, staging / "claims_register.md", CLAIMS_COLS, allow_extra=True)
        st_e = load_register(lint, staging / "code_error_register.md", ERROR_COLS, allow_extra=True)
        if st_c is not None and st_e is not None:
            for cid, eid in confirmed_conflict_links(st_c[1], st_e[1], st_c[0], st_e[0]):
                lint.fail(
                    f"{staging / 'claims_register.md'}: confirmed claim {cid} still linked to "
                    f"confirmed error {eid} at b8 (unresolved status conflict)"
                )
            summary = read_text(lint, audit / "register_cross_link_summary.md")
            check_pairs_listed(
                lint, summary, "Severity divergences",
                severity_divergence_links(st_c[1], st_e[1], st_c[0], st_e[0]),
                "b8", "linked pair with differing severities",
            )


def stage_b9(lint, audit, manifest):
    try:
        from openpyxl import load_workbook
    except ImportError:
        lint.fail("b9 requires openpyxl")
        return
    wb_path = audit / "code_review.xlsx"
    if not wb_path.is_file():
        lint.fail(f"missing {wb_path}")
        return
    wb = load_workbook(wb_path, read_only=True)
    mode = (manifest or {}).get("mode", "replication")
    expect = {"Overview", "Code Errors"} | ({"Paper Claims"} if mode == "replication" else set())
    if set(wb.sheetnames) != expect:
        lint.fail(f"workbook sheets {wb.sheetnames} != expected {sorted(expect)}")
    checks = [("Code Errors", "code_error_register.md", ERROR_COLS, "Error ID", ["Error Description", "Why It Matters"])]
    if mode == "replication":
        checks.append(("Paper Claims", "claims_register.md", CLAIMS_COLS, "Claim ID", ["Issue Description", "Potential Issue"]))
    for sheet, f, cols, idc, required in checks:
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        data = list(ws.values)
        if not data:
            lint.fail(f"{sheet}: sheet is empty")
            continue
        headers = [str(h) if h is not None else "" for h in data[0]]
        if any(h.endswith("Original") for h in headers):
            lint.fail(f"{sheet}: *_Original column leaked into export")
        for req in required:
            if req not in headers:
                lint.fail(f"{sheet}: required author-facing column '{req}' missing")
        if idc not in headers:
            lint.fail(f"{sheet}: ID column '{idc}' missing")
            continue
        reg = load_register(lint, audit / f, cols, allow_extra=True)
        if reg is None:
            continue
        reg_headers, reg_rows = reg
        reg_rows = [r for r in reg_rows if not is_example_row(r)]
        reg_ids = set(col(reg_rows, list(reg_headers), idc)) if idc in reg_headers else set()
        id_i = headers.index(idc)
        sheet_rows = [r for r in data[1:] if r[id_i] is not None]
        sheet_ids = {str(r[id_i]) for r in sheet_rows}
        if sheet_ids != reg_ids:
            lint.fail(f"{sheet}: ID set differs from {f} ({len(sheet_ids)} vs {len(reg_ids)})")
        if len(sheet_rows) != len(reg_rows):
            lint.fail(f"{sheet}: {len(sheet_rows)} rows vs {len(reg_rows)} register rows")


# --------------------------------------------------------------- main

STAGES = (
    ["b0"]
    + [f"b{n}-{s}" for n in range(1, 4) for s in ("claims", "code")]
    + [f"b3b-{s}" for s in ("claims", "code")]
    + [f"b{n}-{s}" for n in range(4, 7) for s in ("claims", "code")]
    + ["b7", "b8", "b9"]
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", required=True, choices=STAGES)
    ap.add_argument("--shard", type=Path, default=None)
    ap.add_argument("--audit-dir", type=Path, default=Path("audit"))
    args = ap.parse_args()

    lint = Lint()
    audit = args.audit_dir
    manifest = {}
    mpath = audit / "_run" / "manifest.json"
    if mpath.is_file():
        try:
            manifest = json.loads(mpath.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            lint.fail(f"{mpath}: invalid JSON")

    stage = args.stage
    n, _, stream = stage.partition("-")
    if stage == "b0":
        stage_b0(lint, audit, manifest)
    elif n == "b1":
        stage_b1(lint, audit, stream)
    elif n == "b2":
        stage_b2(lint, audit, stream, args.shard)
    elif n == "b3":
        stage_b3(lint, audit, stream)
    elif n == "b3b":
        stage_b3b(lint, audit, stream)
    elif n == "b4":
        stage_b4(lint, audit, stream)
    elif n == "b5":
        stage_b5(lint, audit, stream, args.shard, manifest)
    elif n == "b6":
        stage_b6(lint, audit, stream, manifest)
    elif stage == "b7":
        stage_b7(lint, audit)
    elif stage == "b8":
        stage_b8(lint, audit, manifest)
    elif stage == "b9":
        stage_b9(lint, audit, manifest)
    return lint.finish(stage)


if __name__ == "__main__":
    sys.exit(main())
