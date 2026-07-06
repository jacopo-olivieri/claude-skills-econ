#!/usr/bin/env python3
"""Automated scorer for the planted-error fixture.

Reads ``fixture/expected_findings.json`` and a completed run's final
registers, matches each planted finding by mechanism (keyword signatures,
never by ID or wording), and prints a per-plant HIT/MISS table plus a
GATE GREEN / GATE RED verdict. Replaces the hand-adjudicated scorecard
matching for the recall/precision core; severity, status, and the P-14
branch logic are encoded exactly as the answer key's ``scoring`` field
states.

Rules encoded here:

- Recall: every ``must_find`` item needs a row in some register whose text
  matches the plant's mechanism signature, with a qualifying status
  (claims: ``inconsistent``/``confirmation_needed`` or severity-flagged;
  code errors: ``confirmed``/``confirmation_needed``) at
  Severity >= ``min_severity``.
- P-14 dual-accept (branch logic): mechanism found AND (an ``inconsistent``
  claim at qualifying severity OR a ``blocked`` claim whose NON-EMPTY
  Blocked Check itself records the one-in-ten vs 1-in-20 contradiction —
  severity floor waived in that branch). A silent block (empty Blocked
  Check, or one that does not record the contradiction) scores MISS.
- Precision: the D-01 decoy (``placebo`` / ``fig_placebo``) must be absent
  from every register and from the cross-link summary; presence turns the
  gate RED.
- SC-01 (approximation of the key's conditional rule): a claims row that
  still CONFIRMS the long-run-mean shock definition while a confirmed
  code-error row records the P-11 mechanism is an unresolved status
  conflict and turns the gate RED.

Not enforced here (still scorecard/reviewer territory): expected_type
adjudication and the ``expected_confirmed_examples`` cleanliness checks.

Usage:
    score_fixture.py --audit-dir PATH [--expected fixture/expected_findings.json]

Exit codes: 0 = GATE GREEN, 1 = GATE RED, 2 = usage/IO error.
"""

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_EXPECTED = SKILL_DIR / "fixture" / "expected_findings.json"

# Mechanism signatures: plant ID -> list of groups; a row matches when, for
# EVERY group, at least one alternative substring appears in the row's text
# (case-insensitive). Mirrors how prior scorecards hand-matched mechanisms.
SIGNATURES = {
    "P-01": [["0.083"], ["0.038"]],
    "P-02": [["cluster"], ["village"], ["household"]],
    "P-03": [["weight"],
             ["unweighted", "svy_weight", "no weight", "without weight",
              "not weighted", "omits the weight"]],
    "P-04": [["bootstrap"], ["seed"]],
    "P-05": [["waves"],
             ["keep if", "revers", "invert", "exclu", "fewer than two",
              "< 2", "<2"]],
    "P-06": [["panel_v2"]],
    "P-07": [["controls"], ["global", "comment"]],
    "P-08": [["income"], ["100"], ["thousand", "1000", "1,000", "factor"]],
    "P-09": [["rainfall_stations"]],
    "P-10": [["gps", "head_name", "coordinates", "pii"]],
    "P-11": [["rain_mean", "long-run", "long run", "climate normal", "1991",
              "in-sample", "in sample"],
             ["mean", "normal", "baseline"]],
    "P-12": [["legend"],
             ["revers", "swap", "mislabel", "backward", "wrong order",
              "shocked"]],
    "P-13": [["725"], ["30"]],
    "P-14": [["one-in-ten", "one in ten", "1-in-10", "1 in 10"],
             ["1-in-20", "one-in-twenty", "1 in 20", "one in twenty"]],
}
DECOY_TERMS = ["placebo", "fig_placebo"]
# terms indicating a claims row asserts the long-run shock definition (SC-01)
P11_DEFINITION_TERMS = ["long-run", "long run", "climate normal", "1991"]

REGISTERS = [
    ("claims_register.md", "Claim ID"),
    ("code_error_register.md", "Error ID"),
    ("output_register.md", "Output ID"),
]


# --------------------------------------------------------------- md parsing


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
    lines = text.split("\n")
    tables, i = [], 0
    while i < len(lines) - 1:
        if lines[i].lstrip().startswith("|") and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            headers = split_row(lines[i])
            rows, j = [], i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                rows.append(split_row(lines[j]))
                j += 1
            tables.append((headers, rows))
            i = j
        else:
            i += 1
    return tables


def load_rows(path, id_col):
    """Row dicts from the first table carrying *id_col* and Status.

    Tolerates extra columns (post-b8 registers carry ``*_Original``);
    drops schema example rows ([CEO]-0000).
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    for headers, rows in parse_tables(text):
        if id_col in headers and "Status" in headers:
            out = []
            for r in rows:
                if len(r) != len(headers):
                    continue
                d = dict(zip(headers, r))
                if re.fullmatch(r"[CEO]-0000", d[id_col]):
                    continue
                out.append(d)
            return out
    return []


# --------------------------------------------------------------- matching


def row_text(d):
    return " | ".join(str(v) for v in d.values()).lower()


def sig_match(text, groups):
    return all(any(alt in text for alt in group) for group in groups)


def severity(d):
    try:
        return int((d.get("Severity") or "").strip())
    except ValueError:
        return 0


def qualifies(kind, d):
    st = (d.get("Status") or "").strip()
    if kind == "claims":
        return st in {"inconsistent", "confirmation_needed"} or bool(
            (d.get("Severity") or "").strip()
        )
    if kind == "errors":
        return st in {"confirmed", "confirmation_needed"}
    return st == "inconsistent"  # outputs


def describe(kind, id_col, d):
    return f"{d.get(id_col, '?')} ({kind}, status={d.get('Status', '')}, sev={d.get('Severity', '') or '-'})"


def score_generic(item, tagged_rows):
    """(verdict, note) for a standard must_find item."""
    sig = SIGNATURES[item["id"]]
    min_sev = int(item.get("min_severity", 1))
    matched, hits = [], []
    for kind, id_col, d in tagged_rows:
        if not sig_match(row_text(d), sig):
            continue
        matched.append((kind, id_col, d))
        if qualifies(kind, d) and severity(d) >= min_sev:
            hits.append(describe(kind, id_col, d))
    if hits:
        return "HIT", "; ".join(hits)
    if matched:
        return "MISS", ("mechanism matched but no qualifying row at "
                        f"severity >= {min_sev}: "
                        + "; ".join(describe(k, c, d) for k, c, d in matched))
    return "MISS", "no row matches the mechanism signature"


def score_p14(item, tagged_rows):
    """Dual-accept branch logic for P-14 (blocked-visible-metadata test)."""
    sig = SIGNATURES["P-14"]
    min_sev = int(item.get("min_severity", 2))
    silent, hits = [], []
    for kind, id_col, d in tagged_rows:
        text = row_text(d)
        if not sig_match(text, sig):
            continue
        st = (d.get("Status") or "").strip()
        if kind == "claims" and st == "blocked":
            # accepted branch: a non-empty Blocked Check that itself records
            # the contradiction (severity floor waived)
            bc = (d.get("Blocked Check") or "").strip()
            if bc and sig_match(bc.lower(), sig):
                hits.append(describe(kind, id_col, d)
                            + " [blocked branch: Blocked Check records the contradiction]")
            else:
                silent.append(describe(kind, id_col, d))
        elif qualifies(kind, d) and severity(d) >= min_sev:
            hits.append(describe(kind, id_col, d))
    if hits:
        return "HIT", "; ".join(hits)
    if silent:
        return "MISS", ("mechanism matched only silently-blocked row(s) — "
                        "empty Blocked Check or one that does not record the "
                        "contradiction: " + "; ".join(silent))
    return "MISS", "no row matches the mechanism signature"


def check_decoy(tagged_rows, summary_text):
    found = []
    for kind, id_col, d in tagged_rows:
        text = row_text(d)
        if any(t in text for t in DECOY_TERMS):
            found.append(describe(kind, id_col, d))
    if summary_text and any(t in summary_text.lower() for t in DECOY_TERMS):
        found.append("register_cross_link_summary.md")
    return found


def check_sc01(tagged_rows):
    """Unresolved P-11 status conflict surviving to the final registers."""
    confirmed_claim = [
        describe(k, c, d) for k, c, d in tagged_rows
        if k == "claims" and (d.get("Status") or "").strip() == "confirmed"
        and "shock" in row_text(d)
        and any(t in row_text(d) for t in P11_DEFINITION_TERMS)
    ]
    confirmed_error = [
        describe(k, c, d) for k, c, d in tagged_rows
        if k == "errors" and (d.get("Status") or "").strip() == "confirmed"
        and sig_match(row_text(d), SIGNATURES["P-11"])
    ]
    if confirmed_claim and confirmed_error:
        return ("confirmed shock-definition claim coexists with the "
                "confirmed P-11 error: "
                + "; ".join(confirmed_claim + confirmed_error))
    return None


# --------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audit-dir", type=Path, required=True,
                    help="directory holding the run's FINAL registers")
    ap.add_argument("--expected", type=Path, default=DEFAULT_EXPECTED)
    args = ap.parse_args()

    if not args.expected.is_file():
        print(f"ERROR: expected-findings file not found: {args.expected}",
              file=sys.stderr)
        return 2
    expected = json.loads(args.expected.read_text(encoding="utf-8"))

    audit = args.audit_dir
    tagged_rows = []
    for fname, id_col in REGISTERS:
        path = audit / fname
        if not path.is_file():
            if fname == "output_register.md":
                continue  # optional (code_errors_only runs)
            print(f"ERROR: register not found: {path}", file=sys.stderr)
            return 2
        kind = {"Claim ID": "claims", "Error ID": "errors",
                "Output ID": "outputs"}[id_col]
        for d in load_rows(path, id_col):
            tagged_rows.append((kind, id_col, d))

    summary_path = audit / "register_cross_link_summary.md"
    summary_text = (summary_path.read_text(encoding="utf-8", errors="replace")
                    if summary_path.is_file() else None)

    missing_sigs = [i["id"] for i in expected.get("must_find", [])
                    if i["id"] not in SIGNATURES]
    if missing_sigs:
        print("ERROR: no mechanism signature for plant(s) "
              f"{', '.join(missing_sigs)} — extend SIGNATURES in "
              "score_fixture.py", file=sys.stderr)
        return 2

    print(f"Fixture score — audit dir: {audit}")
    print(f"Answer key: {args.expected}")
    print()

    red_reasons = []
    n_hit = 0
    must_find = expected.get("must_find", [])
    for item in must_find:
        scorer = score_p14 if item["id"] == "P-14" else score_generic
        verdict, note = scorer(item, tagged_rows)
        if verdict == "HIT":
            n_hit += 1
        else:
            red_reasons.append(f"{item['id']} MISS")
        print(f"{item['id']}: {verdict} — {note}")

    print()
    decoy = check_decoy(tagged_rows, summary_text)
    if decoy:
        print(f"D-01 decoy: PRESENT — {'; '.join(decoy)}")
        red_reasons.append("D-01 decoy present")
    else:
        note = "" if summary_text is not None else \
            " (cross-link summary not found; registers only)"
        print(f"D-01 decoy: ABSENT{note}")

    sc01 = check_sc01(tagged_rows)
    if sc01:
        print(f"SC-01: FAIL — {sc01}")
        red_reasons.append("SC-01 unresolved status conflict")
    else:
        print("SC-01: PASS")

    print()
    print(f"Recall: {n_hit}/{len(must_find)}")
    if red_reasons:
        print(f"GATE RED — {'; '.join(red_reasons)}")
        return 1
    print("GATE GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
