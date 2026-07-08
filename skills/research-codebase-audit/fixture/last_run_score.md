# Last fixture run score

**Latest completed end-to-end run:** 2026-07-08 — see [`score-2026-07-08-sc01-gate-run1.md`](score-2026-07-08-sc01-gate-run1.md)

| Metric | Result |
| --- | --- |
| **Recall (must_find)** | **20 / 20** (under the corrected key; 19/20 under the pre-correction key — the P-18 severity floor was a key defect, see the scorecard addendum) |
| **Precision (decoys D-01, D-02)** | **PASS** — D-01 absent; the initial D-02 hit (E-0193) was a key over-breadth, decoy rule narrowed to subset-omission complaints |
| **Expected confirmed examples** | **PASS** — both clean |
| **Status conflict SC-01** | **PASS at LAYER 1** — the shock-definition claim closed `inconsistent` at first pass via the quote-qualifier rule; not listed under `## Status conflicts`; the b7 overlap advisory correctly stayed silent for the pair |
| **Artifact layer (U2/U4/U5)** | **PASS** (U4/U5 vacuous — plants closed in the non-firing state); U1 informative-only, convention present |
| **GATE VERDICT** | **GREEN** (under corrected key) |

Scored blind run at `~/scratch/rca-sc01-rescore/run1/pkg/audit/`. This run
validated the SC-01 fix branch (`fix/rca-sc01-status-conflict`) and the
`feat/rca-recall-determinism-v3` refactor together.

**Protocol note:** the two-consecutive-green requirement for worker-dependent
outcomes was consciously waived at merge (2026-07-08, Jacopo's decision) — the
SC-01 Layer-1 fix demonstrably fired, the RED grounds were answer-key defects
(corrected and pinned by harness tests, 129 passed), and further validation
moves to the fourth Floods run on the real package. KTD-5 settled the same day:
the overlap-conflict advisory ships as an advisory (measured precision 1/20
then 0/16); the reserved hard gate is dropped. Details in the scorecard
addendum.

## Prior runs (archived)
- 2026-07-07 v3 rescore run 1 (SC-01 FAIL, led to the fix branch): [`score-2026-07-07-v3-rescore-run1.md`](score-2026-07-07-v3-rescore-run1.md)
- 2026-07-07 recall-determinism v3 build record: [`score-2026-07-07-recall-determinism-v3.md`](score-2026-07-07-recall-determinism-v3.md)
- 2026-07-07 adjudication-recall refactor (harness-only, no end-to-end run): [`score-2026-07-07-adjudication-recall-refactor.md`](score-2026-07-07-adjudication-recall-refactor.md)
- 2026-07-06 improvements run (14/14): [`score-2026-07-06-rca-improvements.md`](score-2026-07-06-rca-improvements.md)
- 2026-07-05 v2 (P-01..P-10, pre-behavior-tests): 10/10 recall, decoy clean — [`score-2026-07-05-v2.md`](score-2026-07-05-v2.md)
- 2026-07-05 v1: [`score-2026-07-05-v1.md`](score-2026-07-05-v1.md)
