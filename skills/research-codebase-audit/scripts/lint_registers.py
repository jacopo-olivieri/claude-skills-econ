#!/usr/bin/env python3
"""Boundary lint for research-codebase-audit registers, plans, and shards.

Mechanical enforcement of ``references/registers.md`` at every stage boundary.
Exits 0 on pass (warnings allowed), nonzero with a findings report on failure.

Usage:
    lint_registers.py --stage STAGE [--shard PATH] [--audit-dir audit]

Stages: b0, b1-claims, b1-code, b2-claims, b2-code, b3-claims, b3-code,
        b4-claims, b4-code, b5-claims, b5-code, b6-claims, b6-code, b7, b8, b9
(b2/b5 lint one worker shard, passed with --shard; b3b-claims/b3b-code lint a
second-read shard with --shard, or the second-read merge without it).
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
# U8 (c): the evidence-level → minimum-ladder table (registers.md, section
# "Evidence levels (tied to the review ladder)"), mirrored as a dict. An
# evidence level whose minimum ladder EXCEEDS the manifest's `ladder_level`
# cannot have been produced at this run's ladder and FAILS. `targeted_rerun_
# verified` is 2 for small reruns / 3 for expensive ones; the linter mirrors the
# floor (2) it can enforce statically. `blocked_documented` is valid at any level.
EVIDENCE_MIN_LADDER = {
    "static_source_verified": 1,
    "artifact_verified": 1,
    "data_inspected_verified": 1,
    "parser_or_runtime_verified": 2,
    "synthetic_test_verified": 2,
    "targeted_rerun_verified": 2,
    "blocked_documented": 0,
}

# b3c shared-conventions artifact (advisory; consumed by the b4-code recheck grep).
CONVENTIONS_COLS = ["Convention", "Category", "Stated Definition", "Sites Already Seen"]
CONVENTION_CATEGORIES = {
    "fiscal_year_or_sample_window_boundary", "date_parse_mask",
    "missing_value_sentinel", "unit_or_scale_factor", "path_separator",
    "id_or_merge_key", "enumerated_member_list",
}
DEFUSE_MAPPING_COLS = ["Bundle ID", "Error ID", "Mapping Kind"]
DEFUSE_MAPPING_KINDS = {"new_candidate", "existing_row"}

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


# --- U1 advisory adjudication heuristic (KTD-1: advisory, never a hard fail) --
#
# A closed claims row (`confirmed`/`blocked`) whose OWN recorded evidence — its
# Issue Description or Blocked Check — describes a paper-vs-code discrepancy is
# very likely mis-adjudicated: the escalation rule in registers.md would push it
# to `inconsistent` (or `confirmation_needed`). This lexical proxy surfaces such
# rows for human review. It is deliberately advisory (a WARNING, exit code
# unchanged): the token set both over- and under-matches, so a hard fail would
# false-block legitimate closures whose prose merely contains a contradiction
# word. The reasoning gate lives in the recheck-worker checklist; this is the
# safety net.
#
# Token set — a small, inline, documented list of contradiction phrases:
ADJUDICATION_TOKENS = (
    "whereas", "but the code", "instead", "does not match",
    "should be", "contradicts",
)
# Negation guard — phrases that, when they immediately precede a token, mark it
# as a NEUTRAL/NEGATED mention that must NOT fire (e.g. "nothing visible confirms
# or contradicts the claim"). Matched case-insensitively against the text right
# before the token's start offset.
ADJUDICATION_NEGATORS = (
    "confirms or ", "confirm or ", "confirmed or ", "nor ", "neither ",
    "no ", "not ", "nothing ",
)


def adjudication_flag(text):
    """Return the first contradiction token *actively* present in *text*, or None.

    A token is skipped when it is immediately preceded (ignoring surrounding
    whitespace) by any negator phrase — so a neutral clause such as "nothing
    visible confirms or contradicts the claim" stays silent.
    """
    if not text:
        return None
    low = text.lower()
    for tok in ADJUDICATION_TOKENS:
        start = 0
        while True:
            i = low.find(tok, start)
            if i == -1:
                break
            before = low[:i].rstrip()
            if not any(before.endswith(neg.rstrip()) for neg in ADJUDICATION_NEGATORS):
                return tok
            start = i + len(tok)
    return None


def check_adjudication_advisory(lint, path, rows, cols=None):
    """Advisory-only scan of FINAL claims registers (b6-claims, b8): flag every
    `confirmed`/`blocked` row whose own Issue Description or Blocked Check carries
    contradiction language. One WARNING per flagged row; never a hard fail.

    *cols* is the actual header order of *rows* (defaults to the canonical
    ``CLAIMS_COLS``); at b8 the staging register carries extra ``*Original``
    columns, so the caller passes those headers to keep field lookup aligned."""
    cols = cols or CLAIMS_COLS
    for r in rows:
        d = dict(zip(cols, r))
        st = d.get("Status", "")
        if st not in {"confirmed", "blocked"}:
            continue
        for field in ("Issue Description", "Blocked Check"):
            tok = adjudication_flag(d.get(field, ""))
            if tok:
                lint.warn(
                    f"adjudication: {d['Claim ID']} ({st}) — {field} contains "
                    f"contradiction language ('{tok}'); review against the "
                    f"escalation rule (registers.md)"
                )
                break


# --- U4 advisory identifier-anchoring heuristic (KTD-3: advisory, ledger-only)
#
# A recheck ledger row that closes a claim `confirmed` while the claim names a
# specific identifier (a variable, file, or parameter) that its own
# `Evidence Checked` never mentions is a likely anchoring gap: the anchoring
# rule in registers.md requires each named identifier located in the code at
# the role the claim assigns it — verifying that the operation exists and
# covers SOME variables anchors the operation, not the claim. Per KTD-3 the
# check reads the LEDGER's `Evidence Checked` column, never the claims
# register's own row (a confirmed register row has no evidence column, so
# comparing against it would fire on nearly every clean row); the claims
# register is read only to fetch each ledger ID's claim text. Like the U1
# adjudication advisory, this is a lexical proxy that both over- and
# under-matches, so it is a WARNING only — exit status never changes. Pinned
# false-positive path (see test_lint_registers.py): evidence citing a
# file:line anchor without repeating the identifier's name still warns —
# advisory noise is acceptable, a silent miss is not. Coverage limit, stated
# honestly: only rechecked rows have a ledger, so this is a tripwire over the
# recheck sample, not a guarantee over every confirmed claim.
#
# Identifier extraction — narrowly code-shaped tokens in the claim text:
#   * backtick-quoted tokens without internal whitespace (`test_score_std`);
#   * bare snake_case tokens (an interior underscore);
#   * bare dotted filenames with a code/data extension (build_panel.R).
_ANCHOR_EXTENSIONS = (
    r"do|ado|py|r|jl|m|sas|sps|csv|dta|tsv|txt|tex|md|json|ya?ml|xlsx?|rds|parquet"
)
_ANCHOR_IDENTIFIER_RE = re.compile(
    r"`([^`\s]+)`"                                    # backticked, no spaces
    r"|\b([A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+)\b"  # snake_case
    r"|\b([\w./-]+\.(?:%s))\b" % _ANCHOR_EXTENSIONS,  # filename.ext
    re.IGNORECASE,
)
_ANCHOR_CONFIRMED_RE = re.compile(r"\bconfirmed\b", re.IGNORECASE)


def claim_named_identifiers(text):
    """Return the set of code-like identifiers *text* names (see regex above)."""
    found = set()
    for m in _ANCHOR_IDENTIFIER_RE.finditer(text or ""):
        found.add(next(g for g in m.groups() if g))
    return found


def check_anchoring_advisory(lint, audit, ledger_rows):
    """Advisory-only scan of a b5-claims recheck ledger: flag every row whose
    `Proposed Register Change` closes the claim `confirmed` while the claim's
    text names an identifier absent from the row's `Evidence Checked`. One
    WARNING per flagged row; never a hard fail. Skips silently when the
    canonical claims register is absent or unparsable (advisory robustness)."""
    reg_path = audit / "claims_register.md"
    if not reg_path.is_file():
        return
    try:
        reg_text = reg_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    claim_text_by_id = {}
    for headers, rows, _ in parse_tables(reg_text):
        # Tolerate extra trailing columns: the post-b8 finalize step promotes
        # the rewriter's staging register, appending `*Original` columns, so
        # the real final `claims_register.md` header is CLAIMS_COLS PLUS extras.
        # Mirror load_register(..., allow_extra=True) / score_fixture's
        # _find_claims_table, and zip each row against the ACTUAL headers so the
        # claim columns are read by name, not position.
        if set(CLAIMS_COLS) <= set(headers):
            for r in rows:
                if len(r) != len(headers):
                    continue
                d = dict(zip(headers, r))
                claim_text_by_id[d["Claim ID"]] = d["Claim Text"]
            break
    if not claim_text_by_id:
        return
    for r in ledger_rows:
        d = dict(zip(LEDGER_COLS, r))
        rid = d["ID"]
        # only a close to `confirmed` is in scope (the word-boundary regex
        # deliberately does not match `confirmation_needed`).
        if not _ANCHOR_CONFIRMED_RE.search(d["Proposed Register Change"] or ""):
            continue
        evidence = (d["Evidence Checked"] or "").lower()
        missing = sorted(
            tok for tok in claim_named_identifiers(claim_text_by_id.get(rid, ""))
            if tok.lower() not in evidence
        )
        if missing:
            lint.warn(
                f"anchoring: {rid} closes confirmed but the claim names "
                f"identifier(s) absent from 'Evidence Checked': "
                f"{', '.join('`%s`' % t for t in missing)}; verify each is "
                f"anchored at its claimed role (anchoring rule, registers.md)"
            )


# --- U5 advisory filename-parameter reconciliation (KTD-4: advisory, blocked
#     rows only, same-syntactic-shape tokens only) --------------------------
#
# A `blocked` claims row whose claim text states a numeric parameter while a
# filename the row itself cites encodes a DIFFERENT value of the same
# syntactic shape has already transcribed a visible contradiction — the
# blocked-row escalation rule in registers.md says such a row cannot rest at
# `blocked`. This lint is the finalize-stage tripwire behind the reading-side
# reconciliation sweep (section-worker.md); it attaches at b8 (the U1
# adjudication advisory's finalize sibling; U4's anchoring advisory sits at
# b5). Per KTD-4 the crude any-numeric-mismatch version is explicitly
# rejected as too noisy — filenames carry incidental years, versions, and
# resolutions, and claim text is dense with estimates and sample sizes — so
# the check is restricted to blocked rows and compares only tokens of the
# SAME syntactic shape:
#   * ratio composites — "one-in-ten" / "1 in 10" in prose vs `1in10` /
#     `1_in_10` / `1-in-10` in a filename stem; spelled-out number words in
#     the claim are normalized to digits first (vocabulary mirrors the P-14
#     signatures in scripts/score_fixture.py);
#   * keyed parameter composites — an alpha key attached to a number
#     (`rp100`, `10km`, `q99`) compared only against a filename token
#     sharing the SAME alpha key. A key present on only one side is never a
#     mismatch, so an incidental year (no key at all) or version (`v3` with
#     no `v`-keyed claim token) stays silent.
# Advisory only: one WARNING per flagged row carrying the literal token
# ``filename-parameter``; exit status never changes.

# Spelled-out number words normalized before comparison (mirrors the
# score_fixture.py P-14 vocabulary: "one-in-ten", "one in twenty", ...).
_FP_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
    "thousand": 1000,
}
_FP_NUMBER_WORD_RE = re.compile(
    r"\b(%s)\b" % "|".join(_FP_NUMBER_WORDS), re.IGNORECASE)
# filenames cited in a register cell (same extension vocabulary as the U4
# anchoring advisory above).
_FP_FILENAME_RE = re.compile(
    r"\b([\w./-]+\.(?:%s))\b" % _ANCHOR_EXTENSIONS, re.IGNORECASE)
# ratio composite in prose (after number-word normalization): "1-in-10",
# "1 in 10"; in a filename stem: "1in10", "1_in_10", "1-in-10".
_FP_PROSE_RATIO_RE = re.compile(r"\b(\d+)[\s-]+in[\s-]+(\d+)\b", re.IGNORECASE)
_FP_FNAME_RATIO_RE = re.compile(r"(\d+)[-_]?in[-_]?(\d+)", re.IGNORECASE)
# keyed composite: alpha key attached (no whitespace) to a number, either
# order — `rp100`, `rp-100`, `10km`, `q99`. Attachment (or a single
# hyphen/underscore) is required so free-standing counts ("4,832
# households") never form a token. Lookarounds rather than \b: an
# underscore is a \w character, so \b would never fire inside a filename
# stem like `grid_25km` — here `-`/`_` count as token separators.
_FP_KEYED_RES = (
    re.compile(r"(?<![A-Za-z0-9])([a-z]{1,10})[-_]?(\d+)(?![A-Za-z0-9])",
               re.IGNORECASE),   # key-first
    re.compile(r"(?<![A-Za-z0-9])(\d+)[-_]?([a-z]{1,10})(?![A-Za-z0-9])",
               re.IGNORECASE),   # number-first
)


def _fp_normalize_number_words(text):
    return _FP_NUMBER_WORD_RE.sub(
        lambda m: str(_FP_NUMBER_WORDS[m.group(1).lower()]), text)


def _fp_tokens(text, ratio_re):
    """(ratios, keyed) parameter tokens of *text*: ratios as a set of
    (numerator, denominator) int pairs; keyed composites as {key: {values}}.
    Ratio matches are masked before keyed extraction so `1in20` never also
    yields an `in`-keyed composite."""
    ratios = set()

    def mask(m):
        ratios.add((int(m.group(1)), int(m.group(2))))
        return " " * len(m.group(0))

    masked = ratio_re.sub(mask, text)
    keyed = {}
    for rx in _FP_KEYED_RES:
        for m in rx.finditer(masked):
            a, b = m.group(1), m.group(2)
            key, num = (a, b) if a[0].isalpha() else (b, a)
            keyed.setdefault(key.lower(), set()).add(int(num))
    return ratios, keyed


def _fp_claim_params(claim_text):
    """Parameter tokens the CLAIM states: cited filenames are masked out
    first (their embedded tokens belong to the filename side), then
    spelled-out number words are normalized to digits."""
    prose = _FP_FILENAME_RE.sub(lambda m: " " * len(m.group(0)), claim_text or "")
    return _fp_tokens(_fp_normalize_number_words(prose), _FP_PROSE_RATIO_RE)


def _fp_filename_params(*cells):
    """Parameter tokens embedded in every filename cited across *cells*,
    extracted from each filename's stem (basename, extension stripped)."""
    ratios, keyed = set(), {}
    for cell in cells:
        for m in _FP_FILENAME_RE.finditer(cell or ""):
            stem = m.group(1).rsplit("/", 1)[-1].rsplit(".", 1)[0]
            r, k = _fp_tokens(stem, _FP_FNAME_RATIO_RE)
            ratios |= r
            for key, vals in k.items():
                keyed.setdefault(key, set()).update(vals)
    return ratios, keyed


def check_filename_parameter_advisory(lint, path, rows, cols=None):
    """Advisory-only scan of a FINAL claims register (b8): flag every
    `blocked` row whose claim-stated parameter disagrees with a same-shape
    token embedded in a filename the row cites (Code/Data Source, Blocked
    Check, or the claim text itself). One WARNING per flagged row; never a
    hard fail. *cols* is the actual header order of *rows* (defaults to the
    canonical ``CLAIMS_COLS``; at b8 the staging register carries extra
    ``*Original`` columns)."""
    cols = cols or CLAIMS_COLS
    for r in rows:
        d = dict(zip(cols, r))
        if d.get("Status") != "blocked":
            continue
        c_ratios, c_keyed = _fp_claim_params(d.get("Claim Text", ""))
        f_ratios, f_keyed = _fp_filename_params(
            d.get("Code/Data Source", ""), d.get("Blocked Check", ""),
            d.get("Claim Text", ""))
        mismatches = []
        if c_ratios and f_ratios and not (c_ratios & f_ratios):
            mismatches.append(
                "ratio %s vs filename %s" % (
                    "/".join(sorted("%d-in-%d" % p for p in c_ratios)),
                    "/".join(sorted("%d-in-%d" % p for p in f_ratios))))
        for key in sorted(set(c_keyed) & set(f_keyed)):
            if not (c_keyed[key] & f_keyed[key]):
                mismatches.append(
                    "'%s' %s vs filename %s" % (
                        key,
                        "/".join(str(v) for v in sorted(c_keyed[key])),
                        "/".join(str(v) for v in sorted(f_keyed[key]))))
        if mismatches:
            lint.warn(
                f"filename-parameter: {d.get('Claim ID', '?')} (blocked) — "
                f"claim-stated parameter disagrees with a same-shape token "
                f"in a cited filename ({'; '.join(mismatches)}); reconcile "
                f"per the blocked-row escalation rule (registers.md)"
            )


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
        # U8 (c): completeness of the author-facing / anchoring columns on an
        # ACTIVE code-error row (candidate or confirmed). An empty description or
        # source is a dead row that reaches the author with no content; an empty
        # Code Location loses the anchor. On `blocked`, the anchor may be genuinely
        # absent (restricted material), so an empty Code Location only WARNS there.
        if st in {"candidate", "confirmed"}:
            for c in ("Code/Data Source", "Error Description", "Why It Matters", "Code Location"):
                if not d.get(c, "").strip():
                    lint.fail(f"{path}: {eid} ({st}) has an empty '{c}'")
        elif st == "blocked" and not d.get("Code Location", "").strip():
            lint.warn(f"{path}: {eid} (blocked) has an empty 'Code Location' (anchor missing)")


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


def check_manifest_worker_shards(lint, manifest, stage_key, plan, key_col,
                                 allocations=None):
    """A done worker stage with planned work must record at least one shard.

    Only completed stages are reconciled: pending/running stages may not have
    created their shard map yet.  ``allocations`` lets b3b reuse the plan it
    already parsed; b6 supplies no allocation so the recheck cluster table is
    read here.
    """
    stages = manifest.get("stages", {}) if isinstance(manifest, dict) else {}
    entry = stages.get(stage_key) if isinstance(stages, dict) else None
    if not isinstance(entry, dict) or entry.get("status") != "done":
        return
    if allocations is None:
        allocations, _ = parse_plan(lint, plan, key_col)
    if allocations is None:
        return
    worker_count = len(allocations)
    if worker_count and not entry.get("shards"):
        lint.fail(
            f"manifest stage '{stage_key}' is done with no shards, but "
            f"{plan} lists {worker_count} planned worker(s)"
        )


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


def stage_b3b(lint, audit, stream, manifest):
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
    check_manifest_worker_shards(
        lint, manifest, f"{stream}_b3b", plan, "Worker ID", alloc,
    )
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


# --- U8 (b): b3b second-read shard boundary check ----------------------------
#
# Mirrors the b2 first-pass shard check but against the second-read allocation
# plan (`claims_second_read_plan.md` / `code_error_second_read_plan.md`, keyed by
# `Worker ID`). A b3b shard is a first-pass-shaped shard (canonical columns, a
# footer) whose new rows are all UNVERIFIED: code rows are `candidate`; claims
# rows are `inconsistent`/`unclear`; output rows use the permitted output set
# (`mapped`/`orphan`/`unclear`/`inconsistent`, never `listed`/`confirmed`). These
# match the second-read-worker skeleton and the b3b merge check in stage_b3b.

B3B_CLAIM_STATUSES = {"inconsistent", "unclear"}
B3B_OUTPUT_STATUSES = {"mapped", "orphan", "unclear", "inconsistent"}


def second_read_plan_path(audit, stream):
    return audit / "plans" / (
        "claims_second_read_plan.md" if stream == "claims"
        else "code_error_second_read_plan.md")


def stage_b3b_shard(lint, audit, stream, shard):
    plan = second_read_plan_path(audit, stream)
    alloc, _ = parse_plan(lint, plan, "Worker ID")
    text = read_text(lint, shard)
    if text is None:
        return
    a = find_alloc_for_shard(alloc, shard)
    if a is None:
        lint.fail(f"{shard}: not found in the second-read plan's allocation table")
        return
    if stream == "claims":
        ranges = [r for r in (parse_range(a.get("Claim ID Range", "")),
                              parse_range(a.get("Output ID Range", ""))) if r]
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
                lint.fail(f"{shard}: {i} outside the second-read-allocated ranges")
        for r in c_rows:
            d = dict(zip(CLAIMS_COLS, r))
            if d["Status"] not in B3B_CLAIM_STATUSES:
                lint.fail(f"{shard}: second-read claim {d['Claim ID']} status "
                          f"'{d['Status']}' (must be 'inconsistent' or 'unclear')")
        for r in o_rows:
            d = dict(zip(OUTPUT_COLS, r))
            if d["Status"] not in B3B_OUTPUT_STATUSES:
                lint.fail(f"{shard}: second-read output {d['Output ID']} status "
                          f"'{d['Status']}' (must be mapped/orphan/unclear/inconsistent)")
        for v in col(c_rows, CLAIMS_COLS, "Related Error IDs"):
            if v:
                lint.fail(f"{shard}: Related Error IDs must be blank at b3b (cross-link is a later stage)")
        check_abs_paths(lint, shard, c_rows, CLAIMS_COLS, ["Code/Data Source"])
        check_abs_paths(lint, shard, o_rows, OUTPUT_COLS, ["Output Path/Pattern", "Producing Script"])
    else:
        ranges = [r for r in (parse_range(a.get("Error ID Range", "")),) if r]
        e_rows = table_by_cols(lint, shard, text, ERROR_COLS, "code errors")
        if e_rows is None:
            return
        check_error_rows(lint, shard, e_rows)
        eids = col(e_rows, ERROR_COLS, "Error ID")
        check_unique(lint, shard, eids, "Error ID")
        for i in eids:
            if not in_ranges(i, ranges):
                lint.fail(f"{shard}: {i} outside the second-read-allocated range")
        for r in e_rows:
            d = dict(zip(ERROR_COLS, r))
            if d["Status"] != "candidate":
                lint.fail(f"{shard}: second-read code row {d['Error ID']} status "
                          f"'{d['Status']}' (must be 'candidate')")
        for v in col(e_rows, ERROR_COLS, "Related Claim IDs"):
            if v:
                lint.fail(f"{shard}: Related Claim IDs must be blank at b3b (cross-link is a later stage)")
        check_abs_paths(lint, shard, e_rows, ERROR_COLS, ["Code/Data Source", "Code Location"])
    shard_footer(lint, shard, text)


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


def _clean_code(value):
    return value.strip().strip("`").strip()


def _du_tokens(text):
    """Extract complete DU identifiers without accepting prefix substrings."""
    return set(re.findall(
        r"(?<![A-Za-z0-9_-])DU-[A-Za-z0-9]+(?![A-Za-z0-9_-])",
        text or "",
    ))


def parse_defuse_artifact(lint, audit):
    """Return standard Bundle IDs from the required b4 detector artifact."""
    path = audit / "_run" / "defuse_bundles.md"
    text = read_text(lint, path)
    if text is None:
        lint.fail(f"{path}: missing required b4 definition/use artifact")
        return None
    match = re.search(r"^- Standard candidates:\s*(\d+)\s*$", text, re.M)
    if not match:
        lint.fail(f"{path}: missing machine-readable 'Standard candidates: <n>' count")
        return None
    section = text.partition("## Candidate findings")[2]
    if not section:
        lint.fail(f"{path}: missing '## Candidate findings' section")
        return None
    section = section.split("\n## ", 1)[0]
    rows = None
    for headers, candidate_rows, _ in parse_tables(section):
        if "Bundle ID" in headers and "Identity Tuple" in headers:
            rows = candidate_rows
            break
    if rows is None:
        lint.fail(f"{path}: standard candidate table not found")
        return None
    ids = []
    id_index = headers.index("Bundle ID")
    for row in rows:
        if len(row) != len(headers):
            lint.fail(f"{path}: malformed standard candidate row")
            continue
        bid = _clean_code(row[id_index])
        if re.fullmatch(r"DU-[0-9A-Za-z]+", bid):
            ids.append(bid)
    if len(ids) != int(match.group(1)):
        lint.fail(f"{path}: Standard candidates count is {match.group(1)} but "
                  f"the table contains {len(ids)} Bundle IDs")
    check_unique(lint, path, ids, "standard Bundle ID")
    return ids


def parse_defuse_mappings(lint, plan):
    """Return rows from the code recheck plan's exact mapping table."""
    text = read_text(lint, plan)
    if text is None:
        return []
    rows = None
    for headers, candidate_rows, _ in parse_tables(text):
        if headers == DEFUSE_MAPPING_COLS:
            rows = candidate_rows
            break
    if rows is None:
        lint.fail(f"{plan}: missing Definition/use bundle mapping table with columns "
                  f"{' | '.join(DEFUSE_MAPPING_COLS)}")
        return []
    out = []
    for row in rows:
        if len(row) != len(DEFUSE_MAPPING_COLS):
            lint.fail(f"{plan}: malformed definition/use mapping row")
            continue
        d = dict(zip(DEFUSE_MAPPING_COLS, row))
        d = {key: _clean_code(value) for key, value in d.items()}
        # Empty markdown tables may contain no rows; ignore an explicit
        # all-blank placeholder if an authoring tool inserted one.
        if not any(d.values()):
            continue
        out.append(d)
    return out


def check_defuse_b4(lint, audit, plan, inventory):
    bundle_ids = parse_defuse_artifact(lint, audit)
    if bundle_ids is None:
        return
    mappings = parse_defuse_mappings(lint, plan)
    by_bundle = {}
    for row in mappings:
        bid, eid, kind = row["Bundle ID"], row["Error ID"], row["Mapping Kind"]
        by_bundle.setdefault(bid, []).append(row)
        if kind not in DEFUSE_MAPPING_KINDS:
            lint.fail(f"{plan}: Bundle ID {bid} has invalid Mapping Kind '{kind}'")
        if not re.fullmatch(ID_RE["E"], eid):
            lint.fail(f"{plan}: Bundle ID {bid} has invalid Error ID '{eid}'")
        if bid not in bundle_ids:
            lint.fail(f"{plan}: mapping names {bid}, which is not a standard bundle "
                      "in defuse_bundles.md")
    for bid in bundle_ids:
        count = len(by_bundle.get(bid, []))
        if count == 0:
            lint.fail(f"{plan}: standard Bundle ID {bid} is unmapped")
        elif count != 1:
            lint.fail(f"{plan}: standard Bundle ID {bid} is mapped {count} times "
                      "(expected exactly once)")

    inv_by_id = {}
    for row in inventory:
        inv_by_id.setdefault(row.get("ID", ""), []).append(row)
    register = load_register(lint, audit / "code_error_register.md", ERROR_COLS)
    canonical = {}
    if register:
        canonical = {dict(zip(ERROR_COLS, row))["Error ID"]:
                     dict(zip(ERROR_COLS, row)) for row in register[1]}
    for bid, rows in by_bundle.items():
        if len(rows) != 1 or bid not in bundle_ids:
            continue
        eid = rows[0]["Error ID"]
        inv_rows = inv_by_id.get(eid, [])
        if len(inv_rows) != 1:
            lint.fail(f"{plan}: Bundle ID {bid} maps to {eid}, which is absent "
                      "from the b4 inventory")
            continue
        if bid not in _du_tokens(inv_rows[0].get("Likely Evidence", "")):
            lint.fail(f"{plan}: inventory row {eid} Likely Evidence does not name "
                      f"mapped Bundle ID {bid}")
        if rows[0]["Mapping Kind"] == "new_candidate":
            canonical_row = canonical.get(eid)
            if canonical_row is None:
                continue  # canon_ids reports this independently
            if canonical_row.get("Status") != "candidate":
                lint.fail(f"{plan}: new_candidate mapping {bid} -> {eid} must be a "
                          "candidate canonical row")
            if canonical_row.get("Error Type") != "sample_filter_or_flag_error":
                lint.fail(f"{plan}: new_candidate mapping {bid} -> {eid} must be typed "
                          "sample_filter_or_flag_error")


def _all_code_recheck_ledger_rows(lint, audit):
    rows = []
    root = audit / "_code_error_recheck"
    if not root.is_dir():
        return rows
    for path in sorted(root.rglob("*.md")):
        text = read_text(lint, path)
        if text is None:
            continue
        for headers, table_rows, _ in parse_tables(text):
            if headers == LEDGER_COLS:
                rows.extend((path, dict(zip(headers, row)))
                            for row in table_rows if len(row) == len(headers))
    return rows


def check_defuse_b6(lint, audit):
    plan = recheck_plan_path(audit, "code")
    mappings = parse_defuse_mappings(lint, plan)
    if not mappings:
        return
    mapped = {}
    for row in mappings:
        mapped.setdefault(row["Error ID"], []).append(row["Bundle ID"])
    ledger_rows = _all_code_recheck_ledger_rows(lint, audit)
    ledgers_by_id = {}
    for path, row in ledger_rows:
        ledgers_by_id.setdefault(row.get("ID", ""), []).append((path, row))
    final = load_register(lint, audit / "_staging" / "code_error_register.md",
                          ERROR_COLS)
    final_by_id = {}
    if final:
        final_by_id = {dict(zip(ERROR_COLS, row))["Error ID"]:
                       dict(zip(ERROR_COLS, row)) for row in final[1]}

    expected_status = {
        "confirmed_error": "confirmed",
        "not_error": "not_error",
        "confirmation_needed": "confirmation_needed",
        "blocked": "blocked",
        "deferred": "blocked",
    }
    for eid, bundle_ids in mapped.items():
        dispositions = ledgers_by_id.get(eid, [])
        if len(dispositions) != 1:
            lint.fail(f"{plan}: mapped Error ID {eid} has {len(dispositions)} ledger "
                      "rows (expected exactly one disposition)")
            continue
        path, ledger = dispositions[0]
        evidence = ledger.get("Evidence Checked", "")
        evidence_du_ids = _du_tokens(evidence)
        for bid in bundle_ids:
            if bid not in evidence_du_ids:
                lint.fail(f"{path}: mapped Bundle ID {bid} missing from {eid} "
                          "Evidence Checked")
        final_row = final_by_id.get(eid)
        if final_row is None:
            lint.fail(f"{plan}: mapped Error ID {eid} absent from final staging register")
            continue
        status = final_row.get("Status", "")
        verdict = ledger.get("Verdict", "")
        duplicate = re.fullmatch(r"duplicate_of:(E-\d{4})", status)
        if duplicate:
            target = duplicate.group(1)
            proposal = (ledger.get("Proposed Register Change", "") + " "
                        + ledger.get("Proposed Note", ""))
            target_row = final_by_id.get(target)
            if verdict != "confirmed_error":
                lint.fail(f"{path}: duplicate disposition for {eid} requires ledger "
                          f"verdict 'confirmed_error', found '{verdict}'")
            if status not in proposal:
                lint.fail(f"{path}: duplicate disposition for {eid} does not explicitly "
                          f"name equivalent canonical issue row {target}")
            if target_row is None or target_row.get("Status") != "confirmed":
                lint.fail(f"{path}: duplicate target {target} is not a confirmed final "
                          "code-error issue row")
            continue
        wanted = expected_status.get(verdict)
        if wanted is None:
            lint.fail(f"{path}: mapped Error ID {eid} has invalid code verdict '{verdict}'")
        elif status != wanted:
            lint.fail(f"{path}: mapped Error ID {eid} verdict '{verdict}' requires "
                      f"final status '{wanted}', found final status '{status}'")


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


# --- U8 (a): the b4 mandatory-recheck inventory computed from canon ----------
#
# A recall guarantee upstream of everything U1 fixes: the recheck can only
# adjudicate rows that actually entered it. The REQUIRED inventory (rows that
# MUST be rechecked) mirrors the pipeline's mechanical inventory rule exactly:
#   * claims  (pipeline-claims.md b4): every severity-bearing row OR every
#     `unclear` row — `Severity != "" OR status == unclear`.
#   * code (pipeline-code-errors.md b4): every `candidate`, plus every
#     `confirmed` with Severity >= 3 — `status == candidate OR (status ==
#     confirmed AND severity >= 3)`.
# The SUBSTANTIVE subset (used only by the `deep` single-ID-cluster rule) is a
# subset of the required set with the SAME predicate on the code side and, on
# the claims side, the U7 definition (issue-flagged OR `unclear`, i.e. exactly
# the required predicate — sampled clean `confirmed` rows are never required and
# never substantive). Sampled clean `confirmed` rows are neither required nor
# substantive here: they may be added to the inventory by the conductor and may
# be grouped, so this check does not fail on their presence, only on the absence
# of a REQUIRED id and on wrong-typed / over-clustered ids.


def _sev_int(sev):
    try:
        return int(sev)
    except (TypeError, ValueError):
        return 0


def required_recheck_ids(lint, audit, stream):
    """Return (required_ids: set, substantive_ids: set) for the b4 inventory.

    `required` = rows the inventory MUST contain (a recall floor).
    `substantive` = the subset that must sit in its own single-ID cluster at
    `deep` depth (U7 definition, mirrored exactly)."""
    required, substantive = set(), set()
    if stream == "claims":
        reg = load_register(lint, audit / "claims_register.md", CLAIMS_COLS)
        if reg:
            for r in reg[1]:
                d = dict(zip(CLAIMS_COLS, r))
                cid, sev, st = d["Claim ID"], d["Severity"], d["Status"]
                if sev or st == "unclear":
                    required.add(cid)
                    substantive.add(cid)  # issue-flagged OR unclear == U7 substantive
    else:
        reg = load_register(lint, audit / "code_error_register.md", ERROR_COLS)
        if reg:
            for r in reg[1]:
                d = dict(zip(ERROR_COLS, r))
                eid, sev, st = d["Error ID"], d["Severity"], d["Status"]
                is_candidate = st == "candidate"
                is_conf_high = st == "confirmed" and _sev_int(sev) >= 3
                if is_candidate or is_conf_high:
                    required.add(eid)
                    substantive.add(eid)  # candidate OR confirmed>=3 == U7 substantive
    return required, substantive


def check_conventions_artifact(lint, audit):
    """Advisory well-formedness check on the optional b3c shared-conventions
    artifact `audit/_run/conventions.md`, consumed by the b4-code recheck grep.

    Non-blocking by design: absent → silent (a package with no multi-site
    convention correctly produces no artifact); present → warn (never fail) if it
    is not a table with the expected header or carries an out-of-vocabulary
    Category. The verdicts come from the code-stream grep, not from lint."""
    path = audit / "_run" / "conventions.md"
    if not path.is_file() or path.stat().st_size == 0:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        lint.warn(f"{path}: could not read the conventions artifact (unreadable)")
        return
    table = None
    for headers, rows, _ in parse_tables(text):
        if headers == CONVENTIONS_COLS:
            table = rows
            break
    if table is None:
        lint.warn(
            f"{path}: no table with the expected header "
            f"{' | '.join(CONVENTIONS_COLS)} (conventions grep may skip it)"
        )
        return
    for r in table:
        d = dict(zip(CONVENTIONS_COLS, r))
        cat = d.get("Category", "")
        if cat and cat not in CONVENTION_CATEGORIES:
            lint.warn(
                f"{path}: convention '{d.get('Convention', '')}' has "
                f"out-of-vocabulary Category '{cat}'"
            )


def stage_b4(lint, audit, stream, manifest=None):
    if stream == "code":
        check_conventions_artifact(lint, audit)  # U2 (preserved — must run first, code only)
    parsed = parse_recheck_plan(lint, audit, stream)
    if parsed is None:
        return
    plan, inventory, clusters = parsed
    if stream == "code":
        check_defuse_b4(lint, audit, plan, inventory)
    canon = canon_ids(lint, audit, stream)
    # U8 (a): the required inventory computed from canon (a recall floor).
    required, substantive = required_recheck_ids(lint, audit, stream)
    id_letter = "C" if stream == "claims" else "E"  # the inventory's own ID letter
    inv_ids = {row.get("ID", "") for row in inventory}
    assignments = {}
    for c in clusters:
        for i in re.findall(r"[CEO]-\d{4}", c["Assigned IDs"]):
            assignments.setdefault(i, []).append(c["Cluster ID"])
    # (a1) every REQUIRED id must actually be in the inventory (recall guarantee).
    for i in sorted(required - inv_ids):
        lint.fail(f"{plan}: required recheck ID {i} absent from the b4 inventory "
                  f"(a mandatory row would silently skip the recheck)")
    for row in inventory:
        i = row.get("ID", "")
        # (a2) wrong-typed inventory IDs: a claims recheck inventory carries only
        #      C- ids (outputs are never rechecked directly); a code inventory only E-.
        if i and i[0] != id_letter:
            lint.fail(f"{plan}: wrong-typed inventory ID {i} in the {stream} recheck plan "
                      f"(expected a {id_letter}- ID)")
        if i not in canon:
            lint.fail(f"{plan}: inventory ID {i} not found in canonical registers")
        n = len(assignments.get(i, []))
        if n != 1:
            lint.fail(f"{plan}: inventory ID {i} assigned to {n} clusters (expected exactly 1)")
    # (a3) cluster size ceiling, at every depth.
    depth = (manifest or {}).get("review_depth", "standard")
    for c in clusters:
        ids = re.findall(r"[CEO]-\d{4}", c["Assigned IDs"])
        if len(ids) > 8:
            lint.fail(f"{plan}: cluster {c['Cluster ID']} groups {len(ids)} IDs (max 8)")
        # (a4) at deep, a cluster may hold at most one SUBSTANTIVE id.
        if depth == "deep":
            n_sub = sum(1 for i in ids if i in substantive)
            if n_sub > 1:
                lint.fail(f"{plan}: cluster {c['Cluster ID']} groups {n_sub} substantive IDs "
                          f"at deep depth (each substantive ID needs its own cluster)")
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
    ladder = int(manifest.get("ladder_level", 1)) if manifest else 1
    # U8 (c): verdicts whose ledger row must carry blocker text in a proposal column.
    BLOCKER_VERDICTS = {"blocked", "confirmation_needed", "deferred"}
    seen = []
    evidence_levels = set()
    for r in rows:
        d = dict(zip(LEDGER_COLS, r))
        seen.append(d["ID"])
        if d["ID"] not in assigned:
            lint.fail(f"{shard}: ledger contains unassigned/new ID {d['ID']} (no new IDs at recheck)")
        if d["Verdict"] not in verdicts:
            lint.fail(f"{shard}: {d['ID']} invalid verdict '{d['Verdict']}'")
        level = d["Evidence Level"]
        if level not in EVIDENCE_LEVELS:
            lint.fail(f"{shard}: {d['ID']} invalid evidence level '{level}'")
        else:
            # U8 (c): an evidence level whose minimum ladder exceeds the run's
            # ladder cannot have been produced — fail it.
            min_ladder = EVIDENCE_MIN_LADDER[level]
            if min_ladder > ladder:
                lint.fail(f"{shard}: {d['ID']} evidence level '{level}' needs ladder "
                          f">= {min_ladder} but the run is at ladder {ladder}")
        evidence_levels.add(level)
        # U8 (c): Evidence Checked must be non-empty on every ledger row.
        if not d["Evidence Checked"].strip():
            lint.fail(f"{shard}: {d['ID']} has an empty 'Evidence Checked' "
                      f"(every rechecked row must record what was inspected)")
        # U8 (c): a blocked/confirmation_needed/deferred verdict must name the
        # blocker in either proposal column (Proposed Register Change / Proposed Note).
        if d["Verdict"] in BLOCKER_VERDICTS:
            blocker = (d["Proposed Register Change"].strip()
                       or d["Proposed Note"].strip())
            if not blocker:
                lint.fail(f"{shard}: {d['ID']} verdict '{d['Verdict']}' but neither "
                          f"'Proposed Register Change' nor 'Proposed Note' records a blocker")
    check_unique(lint, shard, seen, "ledger ID")
    if stream == "claims":
        # U4 advisory: identifier anchoring on rows closing `confirmed`.
        check_anchoring_advisory(lint, audit, rows)
    for i in assigned:
        if i not in seen:
            lint.fail(f"{shard}: assigned ID {i} missing from ledger")
    if ladder >= 2 and evidence_levels == {"static_source_verified"}:
        lint.warn(f"{shard}: ladder level {ladder} but every check is static_source_verified")


def register_files(audit, stream):
    if stream == "claims":
        return [("claims_register.md", CLAIMS_COLS, "Claim ID"), ("output_register.md", OUTPUT_COLS, "Output ID")]
    return [("code_error_register.md", ERROR_COLS, "Error ID")]


def stage_b6(lint, audit, stream, manifest):
    check_manifest_worker_shards(
        lint, manifest, f"{stream}_b5", recheck_plan_path(audit, stream),
        "Cluster ID",
    )
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
            # U1 advisory: this is a FINAL claims register (recheck merge).
            check_adjudication_advisory(lint, staging / f, st_rows)
        elif f == "output_register.md":
            check_output_rows(lint, staging / f, st_rows, final=True)
        else:
            check_error_rows(lint, staging / f, st_rows, final=True)
            for s in col(st_rows, cols, "Status"):
                if s == "candidate":
                    lint.fail(f"{staging / f}: 'candidate' status must not survive the recheck merge")
    if total_new != splits:
        lint.fail(f"recheck merge: {total_new} new row(s) across registers but 'Splits declared: {splits}'")
    if stream == "code":
        check_defuse_b6(lint, audit)


def non_link_identical(lint, st_rows, st_cols, sn_rows, base_cols, idc, link_col, rewrite_pairs, label):
    """Every non-link column must still match the b7 snapshot. Replay-aware: after b8 has run,
    staging carries the `*Original` columns and its base rewrite-pair columns are rewritten in
    place — so when a rewrite-pair's `*Original` column is present, compare the snapshot's base
    value against that `*Original` (the frozen text) rather than the rewritten base column. Every
    other non-link column compares directly. Staging rows are read under their own header order
    (`st_cols`) so extra `*Original` columns never misalign the values."""
    st = {dict(zip(st_cols, r))[idc]: dict(zip(st_cols, r)) for r in st_rows}
    sn = {dict(zip(base_cols, r))[idc]: dict(zip(base_cols, r)) for r in sn_rows}
    if set(st) != set(sn):
        lint.fail(f"{label}: ID sets differ between staging and snapshot")
        return
    rewrite_base = {base: orig for base, orig in rewrite_pairs}
    for i, row in st.items():
        for c in base_cols:
            if c == link_col:
                continue
            orig_col = rewrite_base.get(c)
            if orig_col and orig_col in st_cols:
                if row.get(orig_col, "") != sn[i][c]:
                    lint.fail(f"{label}: {i} rewrite-pair '{c}' — '{orig_col}' does not match the b7 snapshot")
            elif row.get(c, "") != sn[i][c]:
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


# SC-01 overlap-conflict advisory (plan 2026-07-07-001, U5). Code-line citation
# forms observed in real registers: the documented colon form (`path:21-23`,
# `path:11,16-20`) plus the space-L form (`path L21-23`) seen as worker drift.
# RANGE_RE above matches identifier ranges (C-0001–C-0005), not code lines.
CODE_LOC_RE = re.compile(
    r"([A-Za-z0-9_][A-Za-z0-9_./-]*\.[A-Za-z0-9_]+)"  # repo-relative path with extension
    r"(?::(?=\d)|\s+L\s*)"  # colon form (digit must follow — 'path: 3 vars' is prose) or space-L
    r"(\d+(?:\s*[–—-]\s*\d+)?(?:\s*,\s*\d+(?:\s*[–—-]\s*\d+)?)*)"
)
_SPAN_RE = re.compile(r"(\d+)(?:\s*[–—-]\s*(\d+))?")


def code_line_ranges(cell):
    """Extract ``(path, (lo, hi))`` tuples from a citation cell.

    Handles the colon form (``path:21-23``, ``path:11,16-20``) and the space-L
    form (``path L21-23``), comma-separated multi-ranges, hyphen/en-dash/
    em-dash, and backticked paths. Ranged-only matching (KTD-4): a bare file
    with no line spec contributes no range and never overlaps — whole-file
    coverage belongs to the b7 worker rule, not this parser. Single lines
    yield ``(n, n)``; reversed bounds are normalized.
    """
    out = []
    # strip (not blank) backticks so `path`:21-23 keeps the colon abutting the path
    for m in CODE_LOC_RE.finditer((cell or "").replace("`", "")):
        path = m.group(1)
        for span in _SPAN_RE.finditer(m.group(2)):
            lo = int(span.group(1))
            hi = int(span.group(2)) if span.group(2) else lo
            out.append((path, (min(lo, hi), max(lo, hi))))
    return out


def overlapping_confirmed_pairs(claim_rows, error_rows, claim_cols=None, error_cols=None):
    """Confirmed-claim↔confirmed-error pairs whose cited code lines overlap.

    The claim side parses the claims register's Code/Data Source cell; the
    error side parses the code-error register's Code Location cell (the ranged
    column — the error Code/Data Source carries bare script paths that parse
    to no ranges). Example rows are skipped. Pairs already linked via Related
    Error IDs are the hard check's territory (``confirmed_conflict_links``);
    callers subtract that set before advising.
    """
    ccols = claim_cols or CLAIMS_COLS
    ecols = error_cols or ERROR_COLS
    err_ranges = []
    for r in error_rows:
        if is_example_row(r):
            continue
        d = dict(zip(ecols, r))
        if d.get("Status") != "confirmed" or not d.get("Error ID"):
            continue
        spans = code_line_ranges(d.get("Code Location", ""))
        if spans:
            err_ranges.append((d["Error ID"], spans))
    pairs = []
    for r in claim_rows:
        if is_example_row(r):
            continue
        d = dict(zip(ccols, r))
        if d.get("Status") != "confirmed" or not d.get("Claim ID"):
            continue
        cspans = code_line_ranges(d.get("Code/Data Source", ""))
        if not cspans:
            continue
        for eid, espans in err_ranges:
            if any(cp == ep and clo <= ehi and elo <= chi
                   for cp, (clo, chi) in cspans
                   for ep, (elo, ehi) in espans):
                pairs.append((d["Claim ID"], eid))
    return pairs


# NOTE (U6/U7 open question): the "downstream-use severities must cite a search" rule is NOT
# mechanized here. Detecting that a severity "rests on downstream use" requires interpreting free
# text (Issue/Error Description), which is not cleanly lintable; it stays review guidance
# (registers.md severity rubric), not a lint check.
def escalated_mapped_links(claim_rows, error_rows, claim_cols=None, error_cols=None):
    """Links pairing a `mapped` claim with a `confirmed` code error (escalated mapped claims).
    The cross-linker only links a claim to an error that breaks what it asserts, so a
    mapped-claim↔confirmed-error link is the located-but-unverified miss to escalate for a
    second look. Unlike a status conflict, such a pair may legitimately survive to b8."""
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
        if d.get("Status") != "mapped" or not d.get("Claim ID"):
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
    # Replay mode: load staging with allow_extra=True so a post-b8 re-run (staging carries the
    # `*Original` rewrite columns) still finds the table; the snapshot keeps the exact base cols.
    c = load_register(lint, staging / "claims_register.md", CLAIMS_COLS, allow_extra=True)
    e = load_register(lint, staging / "code_error_register.md", ERROR_COLS, allow_extra=True)
    cs = load_register(lint, snap / "claims_register.md", CLAIMS_COLS)
    es = load_register(lint, snap / "code_error_register.md", ERROR_COLS)
    if None in (c, e, cs, es):
        return
    # the allow_extra path does not drop schema example rows — filter them here so ID sets match
    c_headers, c_rows = list(c[0]), [r for r in c[1] if not is_example_row(r)]
    e_headers, e_rows = list(e[0]), [r for r in e[1] if not is_example_row(r)]
    non_link_identical(
        lint, c_rows, c_headers, cs[1], CLAIMS_COLS, "Claim ID", "Related Error IDs",
        REWRITE_PAIRS["claims_register.md"], "b7 claims",
    )
    non_link_identical(
        lint, e_rows, e_headers, es[1], ERROR_COLS, "Error ID", "Related Claim IDs",
        REWRITE_PAIRS["code_error_register.md"], "b7 errors",
    )
    check_bidirectional(
        lint, c_rows, c_headers, "Claim ID", "Related Error IDs",
        e_rows, e_headers, "Error ID", "Related Claim IDs", "b7 C<->E",
    )
    summary = read_text(lint, audit / "register_cross_link_summary.md")
    check_pairs_listed(
        lint, summary, "Status conflicts",
        confirmed_conflict_links(c_rows, e_rows, c_headers, e_headers),
        "b7", "confirmed claim linked to confirmed error",
    )
    check_pairs_listed(
        lint, summary, "Escalated mapped claims",
        escalated_mapped_links(c_rows, e_rows, c_headers, e_headers),
        "b7", "mapped claim linked to confirmed error",
    )
    check_pairs_listed(
        lint, summary, "Severity divergences",
        severity_divergence_links(c_rows, e_rows, c_headers, e_headers),
        "b7", "linked pair with differing severities",
    )
    # SC-01 overlap-conflict advisory (U5): warn on confirmed-vs-confirmed pairs
    # whose cited code lines overlap but that no one linked — the case the hard
    # checks above cannot see (they only inspect links a worker already created).
    # Advisory only; the exit code is driven by lint.errors alone.
    linked = set(confirmed_conflict_links(c_rows, e_rows, c_headers, e_headers))
    for cid, eid in overlapping_confirmed_pairs(c_rows, e_rows, c_headers, e_headers):
        if (cid, eid) in linked:
            continue
        lint.warn(
            f"overlap-conflict: confirmed claim {cid} cites code lines overlapping "
            f"confirmed error {eid}, but the pair is not linked and listed under "
            f"'## Status conflicts' — adjudicate against the b7 status-conflict rule "
            f"(registers.md, Cross-link consistency); overlap alone is not proof of conflict"
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
        if f == "claims_register.md":
            # U1 advisory: b8 also lints a FINAL claims register. Read under the
            # staging header order (extra `*Original` cols) so field lookup aligns.
            check_adjudication_advisory(lint, staging / f, st_rows, list(st_headers))
            # U5 advisory: filename-parameter reconciliation on blocked rows
            # (attaches at finalize per KTD-4).
            check_filename_parameter_advisory(lint, staging / f, st_rows, list(st_headers))
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
            # A mapped-claim↔confirmed-error pair may legitimately survive to b8 (unlike a status
            # conflict), but a surviving one must remain documented — b8 checks only that it stays
            # listed, not any status outcome. Verifying the second look actually ran (a recheck
            # ledger entry) is a prose obligation on the conductor (pipeline-finalize b7 step 5).
            check_pairs_listed(
                lint, summary, "Escalated mapped claims",
                escalated_mapped_links(st_c[1], st_e[1], st_c[0], st_e[0]),
                "b8", "mapped claim linked to confirmed error",
            )
            check_pairs_listed(
                lint, summary, "Severity divergences",
                severity_divergence_links(st_c[1], st_e[1], st_c[0], st_e[0]),
                "b8", "linked pair with differing severities",
            )


def export_expected_headers(reg_headers, add_potential_issue):
    """The header row export_xlsx.py writes for a sheet, from the register's own
    headers. Mirrors export_xlsx.drop_and_augment: drop every `*Original` column
    (order preserved), then — on Paper Claims — insert `Potential Issue` right
    after `Status`."""
    keep = [h for h in reg_headers if not h.endswith("Original")]
    if add_potential_issue and "Status" in keep:
        keep = list(keep)
        keep.insert(keep.index("Status") + 1, "Potential Issue")
    return keep


def check_staging_frozen(lint, audit, mode):
    """U8 (d): a `done` b8 leaves `_staging/` populated as the frozen b8 state.
    Export must not precede b8 — so the frozen registers must exist and be
    non-empty at b9."""
    staging = audit / "_staging"
    files = ["code_error_register.md"]
    if mode != "code_errors_only":
        files.insert(0, "claims_register.md")
    for f in files:
        p = staging / f
        if not p.is_file() or p.stat().st_size == 0:
            lint.fail(f"{p}: b8 must leave a non-empty frozen register in _staging/ "
                      f"(else export precedes b8 — rerun b8 before b9)")


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
    # U8 (d): the frozen b8 staging registers must still be present and non-empty.
    check_staging_frozen(lint, audit, mode)
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
        # U8 (d): exact header parity with the register minus `*Original` (+
        # `Potential Issue` after `Status` on Paper Claims).
        expected_headers = export_expected_headers(
            list(reg_headers), add_potential_issue=(sheet == "Paper Claims"))
        if headers != expected_headers:
            lint.fail(f"{sheet}: export header parity failure — {headers} != {expected_headers}")
        reg_ids = set(col(reg_rows, list(reg_headers), idc)) if idc in reg_headers else set()
        id_i = headers.index(idc)
        sheet_rows = [r for r in data[1:] if r[id_i] is not None]
        sheet_ids = {str(r[id_i]) for r in sheet_rows}
        if sheet_ids != reg_ids:
            lint.fail(f"{sheet}: ID set differs from {f} ({len(sheet_ids)} vs {len(reg_ids)})")
        if len(sheet_rows) != len(reg_rows):
            lint.fail(f"{sheet}: {len(sheet_rows)} rows vs {len(reg_rows)} register rows")
        # U8 (d): Potential Issue = TRUE iff Severity non-empty, per row.
        if sheet == "Paper Claims" and "Potential Issue" in headers and "Severity" in headers:
            pi_i, sev_i = headers.index("Potential Issue"), headers.index("Severity")
            id_j = headers.index(idc)
            for r in sheet_rows:
                sev = str(r[sev_i]).strip() if r[sev_i] is not None else ""
                pi = str(r[pi_i]).strip() if r[pi_i] is not None else ""
                expected = "TRUE" if sev else "FALSE"
                if pi != expected:
                    lint.fail(f"{sheet}: {r[id_j]} Potential Issue '{pi}' disagrees with "
                              f"Severity ('{sev}'): must be '{expected}' "
                              f"(Potential Issue = TRUE iff Severity non-empty)")


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
        if args.shard is not None:
            stage_b3b_shard(lint, audit, stream, args.shard)
        else:
            stage_b3b(lint, audit, stream, manifest)
    elif n == "b4":
        stage_b4(lint, audit, stream, manifest)
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
