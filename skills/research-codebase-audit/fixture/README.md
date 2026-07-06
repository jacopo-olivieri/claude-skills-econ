# Fixture — planted-error validation package

`planted/` is a tiny synthetic replication package (mini paper, two Stata scripts, one
Python script, data, artifacts, README) with **14 planted findings** (`must_find` items P-01
through P-14) spanning the error taxonomy — including the three classes added by the design
(seed, SE specification, weights), a transcription mismatch against a shipped artifact,
hygiene/PII findings, and **one decoy** (a commented-out figure) that must NOT be flagged.

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

`expected_findings.json` is the answer key. It lives here, **outside the audited scope**:
when running the audit, hand the skill `fixture/planted/` as the repo root so no worker can
see this folder's other files.

## Running the validation

1. Copy `planted/` to a scratch location (the audit writes an `audit/` folder into it).
2. Invoke `research-codebase-audit` on that copy: mode = full replication audit,
   ladder level 1 (static), no exclusions.
3. When the run finishes, score `audit/code_review.xlsx` (or the registers) against
   `expected_findings.json`:
   - **Recall**: all 14 `must_find` mechanisms present as issue-flagged or confirmed rows
     (any register; matching is by mechanism, not wording), severities at or above
     `min_severity` (see `expected_findings.json` `scoring` for P-14's dual-accept rule).
   - **Precision**: nothing about the placebo figure / `fig_placebo.pdf` (`must_not_find`),
     and the `expected_confirmed_examples` come out clean rather than flagged.

## When to re-score

Re-run this fixture after **any** edit to a prompt skeleton, pipeline file, `registers.md`,
or lint script. The fixture is the cheap regression; the full quality gate remains the
Floods re-run (baseline to match: 20/22 code errors, 6/18 claims confirmed — see the design
doc).

The data are fabricated; the PII-looking columns (names, GPS) are invented and planted
deliberately as finding P-10.
