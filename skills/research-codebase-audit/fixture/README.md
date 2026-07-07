# Fixture — planted-error validation package

`planted/` is a tiny synthetic replication package (mini paper, two Stata scripts, two
Python scripts, data, a TOML manifest, artifacts, README) with **20 planted findings**
(`must_find` items P-01 through P-20) spanning the error taxonomy — including the three
classes added by the design (seed, SE specification, weights), a transcription mismatch
against a shipped artifact, hygiene/PII findings, and **two decoys** that must NOT be
flagged (a commented-out figure, and an intentional subset of a stated member list).

**Behavior-test plants (added 2026-07-06)** — P-12/P-13/P-14 exist to predict the Floods
failure mode, keyed to the behavior each tests:
- **P-12** — a second, independent error (a reversed figure legend) in `py/make_figures.py`,
  whose prominent first finding is the P-06 stale path. Recovering it requires the
  **second-read recall sweep** re-reading an already-flagged file.
- **P-13** — an arithmetic slip in the paper prose (725 of 2,416 households is 30%, not the
  stated 25%). Caught by the **cheap-check arithmetic recompute**, not left located-unverified.
- **P-14** — a claim (`one-in-ten subsample`) resting on restricted data but contradicted by
  visible package metadata (the README calls `households.csv` a `1-in-20 subsample`). Tests the
  **blocked-visible-metadata discipline**: flagged inconsistent (or blocked with a Blocked Check
  note), never silently blocked.

**Failure-class plants (added 2026-07-07)** — P-15 through P-20 plant one instance of each
mechanism from the recall-determinism refactor (U1–U5), each in a domain fresh relative to
the Floods package, each tagged with a `failure_class` the scorer reports per class:
- **P-15** (`enumerated_member_list`, U1) — the paper states a four-component income list;
  `py/build_income.py` hand-retypes it as three, omitting remittances. Recovery is attributed
  to the b3c consolidation single-row carve-out plus the b4 set-difference grep.
- **P-16** (`manifest_parseability`, U2) — `pyproject.toml` is invalid TOML (unquoted
  `version = 0.4.1`), a different format/ecosystem from the Floods requirements defect;
  `check_manifests.py` must name it in `audit/_run/manifest_check.md`.
- **P-17 / P-18** (`empirical_verification`, U3) — a Stata backfill guard whose comment says
  it fills missing `hhsize` but whose `if hhsize < .` condition excludes the missing case
  (in `do/build_panel.do`, already carrying P-05/P-08/P-11), and a Python loop that
  overwrites `has_wages` each iteration so the last wave erases earlier matches (in
  `py/build_income.py`, alongside P-15/P-19) — each in a file with unrelated plants, the
  shape of the real misses.
- **P-19** (`identifier_anchoring`, U4) — the paper says `wage_earnings` is winsorised at
  the 99th percentile; the code winsorises `crop_sales`. The claim must not close confirmed.
- **P-20** (`step_parameter_filename`, U5) — Appendix A step 2 states a 15-km gauge radius;
  the shipped file is `data/village_rain_radius_25km.csv`. Dual-accept like P-14.
- **D-02 decoy** — `farm_components` in `py/build_income.py` keeps a deliberate,
  comment-signposted subset of the stated income list; flagging it is a false positive
  (exercises the U1 intentional-subset guard).

`expected_findings.json` is the answer key. It lives here, **outside the audited scope**:
when running the audit, hand the skill `fixture/planted/` as the repo root so no worker can
see this folder's other files.

## Running the validation

1. Copy `planted/` to a scratch location (the audit writes an `audit/` folder into it).
2. Invoke `research-codebase-audit` on that copy: mode = full replication audit,
   ladder level 1 (static), no exclusions.
3. When the run finishes, score `audit/code_review.xlsx` (or the registers) against
   `expected_findings.json`:
   - **Recall**: all 20 `must_find` mechanisms present as issue-flagged or confirmed rows
     (any register; matching is by mechanism, not wording), severities at or above
     `min_severity` (see `expected_findings.json` `scoring` for the P-14/P-20 dual-accept
     rule).
   - **Precision**: nothing about the placebo figure / `fig_placebo.pdf`, nothing about the
     farm-components subset (`must_not_find`), and the `expected_confirmed_examples` come
     out clean rather than flagged.

### Automated scoring

`scripts/score_fixture.py` automates the recall/precision core of the scorecard
(mechanism-signature matching, the P-14/P-20 dual-accept branch logic, the decoy
greps, an SC-01 unresolved-conflict check, per-failure-class tags, and the
artifact-layer checks: the U2 parser artifact must name `pyproject.toml`; the U4
and U5 advisory lints must have fired if the corresponding plant closed in the
failure state; the U1 conventions-artifact check is informative only, never
gate-settling — see KTD-8 in the 2026-07-07 plan). Point it at the finished run's
final registers:

```
python scripts/score_fixture.py --audit-dir /path/to/pkg/audit
```

Exit 0 = GATE GREEN, 1 = GATE RED. Type adjudication and the
`expected_confirmed_examples` cleanliness checks remain hand-scored; record the
scorer output in the dated scorecard either way.

## Test harness

The scripts' committed pytest suite (linter contract tests, scorer self-tests,
export and comment-blanking smoke tests, and a plant-drift hash check that
catches an accidental "fix" to a planted bug) runs green with one command from
the skill folder:

```
uv run --no-project --with pytest --with openpyxl -- pytest scripts/tests/
```

(or `python -m pytest scripts/tests/` if pytest and openpyxl are installed).
Builders for synthetic registers, plans, and audit directories live in
`scripts/tests/regbuild.py` — new lint checks should land with failing-first
negative tests there. If you edit anything under `planted/`, regenerate
`scripts/tests/data/planted_sha256.json` (see `scripts/tests/test_plant_drift.py`).

## When to re-score

Re-run this fixture after **any** edit to a prompt skeleton, pipeline file, `registers.md`,
or lint script. The fixture is the cheap regression; the full quality gate remains the
Floods re-run (baseline to match: 20/22 code errors, 6/18 claims confirmed — see the design
doc).

The data are fabricated; the PII-looking columns (names, GPS) are invented and planted
deliberately as finding P-10.
