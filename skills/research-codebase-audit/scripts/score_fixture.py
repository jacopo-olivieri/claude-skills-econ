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
- P-20 reuses the P-14 dual-accept branch logic (blocked-visible plant
  family): inconsistent at qualifying severity, OR blocked with a Blocked
  Check that itself records the 15-km vs 25 km contradiction.
- Per-class breakdown (U9 tags, U10 reporting): a ``failure_class`` field on
  a must_find item is echoed on its line, and the ``Per-class:`` block under
  the aggregate recall lists EVERY planted class with hit/miss counts. The
  pre-2026-07-07 plants P-01..P-14 carry no ``failure_class`` tag in the
  answer key (they predate the class taxonomy and each tests a mechanism,
  not one of the U1-U5 failure classes); rather than back-tag them, the
  breakdown rolls them up in an explicit ``unclassified_legacy`` bucket so
  the aggregate is always the sum of the per-class lines.
- Artifact-layer checks (U9; Build Process gate, single-re-score layer per
  KTD-8 — these outcomes are produced by committed scripts/lints, so one
  re-score settles them; the gate scorecard records them separately from
  the register-based two-run results):
  * U2: ``AUDIT_DIR/_run/manifest_check.md`` must name ``pyproject.toml``
    in its Candidate findings section (gate-settling; the parser emission
    is deterministic given the plant).
  * U4: if the P-19 claim closed ``confirmed``, the anchoring advisory
    (``lint_registers.check_anchoring_advisory``) must have warned on its
    recheck-ledger row (gate-settling when a ledger row exists; a confirmed
    close outside the recheck sample is reported NOT COVERED, not FAIL —
    the advisory is a tripwire over the recheck sample by design/KTD-3).
  * U5: if the P-20 row rests ``blocked``, the filename-parameter advisory
    (``lint_registers.check_filename_parameter_advisory``) must warn on it
    (gate-settling).
  * U1: a conventions-artifact/b4-candidate presence check, INFORMATIVE
    only, never gate-settling — the b3c consolidation and grep-term choice
    are worker-dependent (KTD-8), so this line feeds diagnosis, not the
    verdict.

Not enforced here (still scorecard/reviewer territory): expected_type
adjudication and the ``expected_confirmed_examples`` cleanliness checks.

Usage:
    score_fixture.py --audit-dir PATH [--expected fixture/expected_findings.json]

Exit codes: 0 = GATE GREEN, 1 = GATE RED, 2 = usage/IO error.
"""

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_EXPECTED = SKILL_DIR / "fixture" / "expected_findings.json"


def load_lint_module():
    """Import scripts/lint_registers.py by path (scripts/ is not a package).

    The artifact-layer checks reuse the committed advisory-check functions so
    the scorer can never drift from the lint's actual behavior."""
    spec = importlib.util.spec_from_file_location(
        "lint_registers", SCRIPTS_DIR / "lint_registers.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

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
    "P-15": [["remittance"],
             ["component", "crop", "income"],
             ["omit", "miss", "excl", "without", "only", "left out",
              "not includ", "drop", "three", "absent"]],
    "P-16": [["pyproject"],
             ["toml", "parse", "invalid", "version", "malformed", "reject"]],
    "P-17": [["hhsize"], ["missing"],
             ["never", "only", "already", "non-missing", "nonmissing",
              "excl", "does not fill", "doesn't fill", "not fill", "< .",
              "present"]],
    "P-18": [["has_wages"],
             ["overwrit", "overwrite", "erase", "clobber", "last", "reset",
              "final", "each iteration", "replaces"]],
    "P-19": [["winsor"],
             ["wage_earnings", "wage earnings"],
             ["crop_sales", "crop sales"]],
    "P-20": [["15-km", "15 km", "15km", "fifteen"],
             ["25km", "25-km", "25 km", "twenty-five"]],
    "P-21": [["consent"],
             ["community"],
             ["keep if", "drop", "exclu", "omit", "narrow",
              "conjunct", "silently", "left out", "not kept",
              "removed", "restrict"]],
}
# Plants scored with the P-14 dual-accept branch logic (blocked-visible
# family): inconsistent at qualifying severity OR blocked with a Blocked
# Check that itself records the contradiction (severity floor waived).
BLOCKED_VISIBLE_PLANTS = {"P-14", "P-20"}
# Each decoy is (site_terms, qualifier_terms). A row trips the decoy when it
# matches a site term AND, if qualifier_terms is set, also a qualifier term.
# D-02's qualifier restricts it to subset-omission complaints — the planted
# bait — so an unrelated true observation inside the signposted block (e.g.
# a zero-division guard) is scored on its own merits, not condemned by site.
DECOYS = {
    "D-01": (["placebo", "fig_placebo"], None),
    "D-02": (["farm_income", "farm-income", "farm income", "farm_components",
              "farm components", "farm_share", "farm share"],
             ["omit", "subset", "diverg", "four-component", "four component",
              "four income", "remittance", "incomplete", "excludes",
              "missing component"]),
}
# --- artifact-layer constants (U9) ----------------------------------------
# the U2 plant: the malformed manifest the parser artifact must name
MANIFEST_PLANT = "pyproject.toml"
# locators for the plant CLAIM rows the conditional advisory checks key on
# (looser than the full mechanism signatures: they must find the claim row
# even when the run failed to record the contradiction)
U4_CLAIM_LOCATOR = [["winsor"], ["wage_earnings", "wage earnings"]]
U5_CLAIM_LOCATOR = [["15-km", "15 km", "15km", "fifteen"], ["radius", "km"]]
# terms identifying the U1 member-list convention in the b3c artifact
U1_CONVENTION_CATEGORY = "enumerated_member_list"
U1_MEMBER_TERMS = ["remittance", "crop", "livestock", "wage"]
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


def score_blocked_visible(item, tagged_rows):
    """Dual-accept branch logic for the blocked-visible plant family
    (P-14, P-20): mechanism found AND (a qualifying flagged row OR a blocked
    claim whose non-empty Blocked Check itself records the contradiction)."""
    sig = SIGNATURES[item["id"]]
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


def check_decoy(terms, quals, tagged_rows, summary_text):
    def trips(text):
        return any(t in text for t in terms) and (
            quals is None or any(q in text for q in quals))
    found = []
    for kind, id_col, d in tagged_rows:
        if trips(row_text(d)):
            found.append(describe(kind, id_col, d))
    if summary_text and trips(summary_text.lower()):
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


# ------------------------------------------------- artifact-layer checks (U9)
#
# The register score reads the FINAL registers, downstream of worker
# disposition, so a candidate emitted and dispositioned away is
# indistinguishable from no emission. These checks read the deterministic
# layer directly (the U2 parser artifact; the U4/U5 advisory lints re-run on
# the run's own tables), so the Build Process gate can record the
# single-re-score outcomes separately from the register-based two-run
# outcomes (KTD-8). Each returns (status, note): status "FAIL" adds a red
# reason; "PASS"/"NOT COVERED" does not; the U1 check returns "INFO" always.


def check_artifact_manifest(audit):
    """U2 (gate-settling): the parser artifact names the malformed manifest."""
    path = audit / "_run" / "manifest_check.md"
    if not path.is_file():
        return "FAIL", f"artifact not found: {path} (run check_manifests.py at b4)"
    text = path.read_text(encoding="utf-8", errors="replace")
    _, _, findings = text.partition("## Candidate findings")
    # Bound the search to the Candidate-findings section body only: render_artifact
    # writes a `## Warnings` section AFTER the candidate findings, and a run that
    # could not parse the plant emits a warning line naming pyproject.toml with
    # ZERO candidate findings — so the plant must appear in the findings proper.
    findings = findings.split("\n## ")[0]
    if MANIFEST_PLANT.lower() in findings.lower():
        return "PASS", f"_run/manifest_check.md names {MANIFEST_PLANT}"
    return "FAIL", (f"_run/manifest_check.md does not name {MANIFEST_PLANT} "
                    "in its Candidate findings")


def _find_claims_table(lint_mod, audit):
    """(headers, rows) of the final claims register's table, tolerating the
    post-b8 ``*_Original`` extra columns; (None, None) if unparsable.

    The b8 rewrite pass inserts each ``*_Original`` column immediately after
    its source column (e.g. ``Issue Description | Issue Description Original``),
    so the canonical columns are a subset of the header, NOT a prefix of it.
    Match on set-containment and zip rows against the actual header, mirroring
    ``lint_registers.load_register(allow_extra=True)`` and the containment fix
    in ``check_anchoring_advisory``."""
    path = audit / "claims_register.md"
    if not path.is_file():
        return None, None
    text = path.read_text(encoding="utf-8", errors="replace")
    for headers, rows, _ in lint_mod.parse_tables(text):
        if set(lint_mod.CLAIMS_COLS) <= set(headers):
            return headers, [r for r in rows if len(r) == len(headers)]
    return None, None


def _locate_claim_rows(headers, rows, locator):
    """Claim-row dicts whose full text matches *locator* (signature groups)."""
    out = []
    for r in rows:
        d = dict(zip(headers, r))
        if sig_match(row_text(d), locator):
            out.append(d)
    return out


def check_artifact_anchoring(lint_mod, audit):
    """U4 (conditional, gate-settling): if the P-19 claim closed confirmed,
    the anchoring advisory must have warned on its recheck-ledger row."""
    headers, rows = _find_claims_table(lint_mod, audit)
    if headers is None:
        return "FAIL", "claims register missing or unparsable"
    matches = _locate_claim_rows(headers, rows, U4_CLAIM_LOCATOR)
    if not matches:
        return ("NOT COVERED",
                "no claim row locates the P-19 plant (register layer scores it)")
    confirmed = [d for d in matches
                 if (d.get("Status") or "").strip() == "confirmed"]
    if not confirmed:
        return "PASS", ("vacuous — P-19 claim not confirmed "
                        "(closed " + "/".join(sorted(
                            (d.get("Status") or "?").strip() for d in matches))
                        + ")")
    ledger_rows = []
    recheck_dir = audit / "_recheck"
    if recheck_dir.is_dir():
        for p in sorted(recheck_dir.rglob("*.md")):
            text = p.read_text(encoding="utf-8", errors="replace")
            for h, rws, _ in lint_mod.parse_tables(text):
                if h == lint_mod.LEDGER_COLS:
                    ledger_rows.extend(r for r in rws if len(r) == len(h))
    ids = {d.get("Claim ID", "") for d in confirmed}
    covered = [r for r in ledger_rows
               if dict(zip(lint_mod.LEDGER_COLS, r)).get("ID") in ids]
    if not covered:
        return ("NOT COVERED",
                "P-19 claim closed confirmed with no recheck-ledger row — the "
                "advisory is a tripwire over the recheck sample (KTD-3) and "
                "never saw it; the register layer scores the miss")
    lint = lint_mod.Lint()
    lint_mod.check_anchoring_advisory(lint, audit, covered)
    fired = [w for w in lint.warnings
             if "anchoring:" in w and any(i in w for i in ids)]
    if fired:
        return "PASS", "tripwire fired — " + "; ".join(fired)
    return "FAIL", ("P-19 claim closed confirmed but the anchoring advisory "
                    "stayed silent on its ledger row(s): " + ", ".join(sorted(ids)))


def check_artifact_filename_parameter(lint_mod, audit):
    """U5 (conditional, gate-settling): if the P-20 row rests blocked, the
    filename-parameter advisory must warn on it."""
    headers, rows = _find_claims_table(lint_mod, audit)
    if headers is None:
        return "FAIL", "claims register missing or unparsable"
    matches = _locate_claim_rows(headers, rows, U5_CLAIM_LOCATOR)
    if not matches:
        return ("NOT COVERED",
                "no claim row locates the P-20 plant (register layer scores it)")
    blocked = [d for d in matches
               if (d.get("Status") or "").strip() == "blocked"]
    if not blocked:
        return "PASS", ("vacuous — P-20 row not blocked "
                        "(closed " + "/".join(sorted(
                            (d.get("Status") or "?").strip() for d in matches))
                        + ")")
    ids = {d.get("Claim ID", "") for d in blocked}
    lint = lint_mod.Lint()
    raw = [[d.get(c, "") for c in headers] for d in blocked]
    lint_mod.check_filename_parameter_advisory(
        lint, audit / "claims_register.md", raw, cols=headers)
    fired = [w for w in lint.warnings
             if "filename-parameter" in w and any(i in w for i in ids)]
    if fired:
        return "PASS", "tripwire fired — " + "; ".join(fired)
    return "FAIL", ("P-20 row rests blocked but the filename-parameter "
                    "advisory stayed silent on: " + ", ".join(sorted(ids)))


def check_artifact_conventions(lint_mod, audit, tagged_rows):
    """U1 (INFORMATIVE only, never gate-settling per KTD-8): is the
    enumerated-member-list convention in the b3c artifact, and does any final
    register row carry the P-15 mechanism?"""
    path = audit / "_run" / "conventions.md"
    conv = "artifact absent"
    if path.is_file():
        conv = f"{U1_CONVENTION_CATEGORY} convention ABSENT from the artifact"
        text = path.read_text(encoding="utf-8", errors="replace")
        for headers, rows, _ in lint_mod.parse_tables(text):
            for r in rows:
                joined = " | ".join(r).lower()
                if (U1_CONVENTION_CATEGORY in joined
                        and any(t in joined for t in U1_MEMBER_TERMS)):
                    conv = f"{U1_CONVENTION_CATEGORY} convention PRESENT"
                    break
    reg = "no register row matches the P-15 mechanism"
    for kind, id_col, d in tagged_rows:
        if sig_match(row_text(d), SIGNATURES["P-15"]):
            reg = f"P-15 mechanism row present ({describe(kind, id_col, d)})"
            break
    return "INFO", f"{conv}; {reg} (worker-dependent — informative, not gate-settling)"


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
    class_totals, class_hits = {}, {}
    must_find = expected.get("must_find", [])
    for item in must_find:
        scorer = (score_blocked_visible if item["id"] in BLOCKED_VISIBLE_PLANTS
                  else score_generic)
        verdict, note = scorer(item, tagged_rows)
        cls = item.get("failure_class")
        # untagged plants (the pre-2026-07-07 P-01..P-14) roll up in an
        # explicit legacy bucket so every planted item appears in the
        # per-class breakdown and the aggregate equals the per-class sum
        bucket = cls or "unclassified_legacy"
        class_totals[bucket] = class_totals.get(bucket, 0) + 1
        if verdict == "HIT":
            n_hit += 1
            class_hits[bucket] = class_hits.get(bucket, 0) + 1
        else:
            red_reasons.append(f"{item['id']} MISS")
        tag = f" [class={cls}]" if cls else ""
        print(f"{item['id']}: {verdict}{tag} — {note}")

    print()
    for did, (terms, quals) in DECOYS.items():
        found = check_decoy(terms, quals, tagged_rows, summary_text)
        if found:
            print(f"{did} decoy: PRESENT — {'; '.join(found)}")
            red_reasons.append(f"{did} decoy present")
        else:
            note = "" if summary_text is not None else \
                " (cross-link summary not found; registers only)"
            print(f"{did} decoy: ABSENT{note}")

    sc01 = check_sc01(tagged_rows)
    if sc01:
        print(f"SC-01: FAIL — {sc01}")
        red_reasons.append("SC-01 unresolved status conflict")
    else:
        print("SC-01: PASS")

    # artifact-layer checks (U9; single-re-score layer per KTD-8)
    print()
    print("Artifact-layer checks (single-re-score layer; record separately "
          "from the register-based two-run results):")
    lint_mod = None
    try:
        lint_mod = load_lint_module()
    except Exception as exc:  # never crash the register score
        print(f"WARNING: could not load lint_registers.py "
              f"({exc.__class__.__name__}: {exc}); the gate-settling U4/U5 "
              "artifact checks did not run (red), and the U1 INFO check is "
              "skipped")
        red_reasons.append("U4/U5 artifact checks unrun: lint_registers.py "
                           "failed to load")
    status, note = check_artifact_manifest(audit)
    print(f"U2 manifest artifact: {status} — {note}")
    if status == "FAIL":
        red_reasons.append("U2 manifest artifact check failed")
    if lint_mod is not None:
        for label, fn, red in (
            ("U4 anchoring advisory", check_artifact_anchoring,
             "U4 anchoring advisory check failed"),
            ("U5 filename-parameter advisory",
             check_artifact_filename_parameter,
             "U5 filename-parameter advisory check failed"),
        ):
            status, note = fn(lint_mod, audit)
            print(f"{label}: {status} — {note}")
            if status == "FAIL":
                red_reasons.append(red)
        status, note = check_artifact_conventions(lint_mod, audit, tagged_rows)
        print(f"U1 conventions artifact: {status} — {note}")

    print()
    print(f"Recall: {n_hit}/{len(must_find)}")
    if class_totals:
        print("Per-class:")
        for bucket, tot in sorted(class_totals.items()):
            hits = class_hits.get(bucket, 0)
            print(f"  {bucket}: {hits}/{tot} hit, {tot - hits} miss")
    if red_reasons:
        print(f"GATE RED — {'; '.join(red_reasons)}")
        return 1
    print("GATE GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
