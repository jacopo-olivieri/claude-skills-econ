# Fixture re-score gate — plan 2026-07-07-001 (branch `feat/rca-recall-determinism-v3`)

Pre-merge gate per KTD-8 / the Evaluation-protocol section of `fixture/README.md`.
Deterministic (script/lint artifact) outcomes settle in **one** re-score; worker-dependent
outcomes require **two consecutive** green re-scores. Every re-score outcome is recorded here.

Run setup (both runs): blind copy of `fixture/planted/` at `~/scratch/rca-fixture-rescore/pkg`
(answer key and scorer stay in the repo, out of worker scope); fresh Opus instance launched from
inside the copy with a minimal unbiased prompt; full replication audit, **ladder level 2**
(required so U3's empirical probe is permitted), `compute_budget_minutes: 15`, no exclusions;
scored with `scripts/score_fixture.py --audit-dir <copy>/audit`.

## Run 1 — 2026-07-07

- **Recall: 20/20.** Every `must_find` plant recovered.
- **Per-class:** empirical_verification 2/2, enumerated_member_list 1/1, identifier_anchoring 1/1,
  manifest_parseability 1/1, step_parameter_filename 1/1, unclassified_legacy 14/14.
- **Precision:** both decoys absent (D-01 placebo, D-02 intentional-subset).
- **Artifact layer (deterministic, single-re-score — SETTLED):**
  - U2 manifest artifact **PASS** — `_run/manifest_check.md` names `pyproject.toml`.
  - U4 anchoring advisory **PASS** (vacuous — P-19 claim closed `inconsistent`, not `confirmed`:
    identifier-anchoring correctly kept it out of `confirmed`).
  - U5 filename-parameter advisory **PASS** (vacuous — P-20 row closed `inconsistent`, not
    silently `blocked`).
  - U1 conventions artifact **INFO** — `enumerated_member_list` present; P-15 row present
    (worker-dependent, informative only).
- **Cycle mechanism outcomes (worker-dependent, need a 2nd run to count):** P-15 (U1 grep),
  P-17/P-18 (U3 probe — both single-statement bugs caught, the class missed on all 3 Floods runs),
  P-19 (U4), P-20 (U5) all HIT.
- **SC-01: RED** (the only RED). Pre-existing check on legacy plant P-11 (not a cycle unit).
  Workers split one paper sentence: C-0015 correctly flagged the baseline-window error
  `inconsistent` (2-wave in-sample mean ≠ the paper's 1991–2020 climate normal), while C-0014
  confirmed a narrowed structural restatement ("z-score deviation from the village mean"), dropping
  the "long-run historical" qualifier; the cross-linker did not surface C-0014↔E-0151.
  **Disposition (user, 2026-07-07): accept as diagnosed run-variance** — the cycle's deliverables
  U1–U10 all validated (recall + artifact layer), mechanism artifacts intact, no code/prompt defect;
  the flip is worker-adjudication/U4-compliance variance on a legacy plant and plausibly arose from
  claim-extraction granularity (the prior 2026-07-06 fixture run passed SC-01). If it reproduces on
  run 2 it becomes a scoped follow-up (a U4-compliance / cross-link gap: C-0014's own quote names
  "long-run historical mean" the code does not implement, so anchoring arguably should have kept it
  out of `confirmed`), **not** a merge-blocker for this cycle's work.

**Gate scorer note:** run 1 first reported U4/U5 FAIL ("claims register missing or unparsable").
Diagnosed as a gate-scorer bug, not a run outcome — `_find_claims_table` required `CLAIMS_COLS` as a
header *prefix*, but the real b8 rewrite *inserts* `Issue Description Original` after
`Issue Description`. Fixed to match on set-containment (commit `3057df6`); re-scored the same audit
dir (deterministic, no LLM re-run) → the PASS results above.

## Run 2 — PENDING

Confirmatory second re-score from a fresh blind copy. Records recall, precision, and whether the
worker-dependent cycle outcomes (and SC-01) reproduce.
