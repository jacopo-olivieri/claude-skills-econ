# Last fixture run score

**Latest completed gate:** 2026-07-08/09 — **definition/use-contract (defuse) two-run gate, PASS** — RUN 1 [`score-2026-07-08-defuse-gate-run1.md`](score-2026-07-08-defuse-gate-run1.md) + RUN 2 [`score-2026-07-08-defuse-gate-run2.md`](score-2026-07-08-defuse-gate-run2.md)

| Metric | Run 1 | Run 2 |
| --- | --- | --- |
| **Recall (must_find, incl. P-21)** | **21 / 21** | **21 / 21** |
| **Precision (decoys D-01, D-02)** | **PASS** (D-02 matcher fix `05b54ff`) | **PASS** (D-02 matcher narrowing 2026-07-09 — bare `"subset"` dropped) |
| **Expected confirmed examples** | **PASS** | **PASS** |
| **Status conflict SC-01** | **PASS at LAYER 1** | **PASS** — no confirmed↔confirmed link survives |
| **Artifact layer (U2/U4/U5)** | **PASS** | **PASS** |
| **P-21 worker evidence** | **PASS** — producer-vs-consumer reasoning (E-0001) | **PASS** — same reasoning, independent workers (E-0001) |
| **GATE VERDICT** | **GREEN** | **GREEN** |

**Two-consecutive-green worker-dependent gate: PASS.** The reworded standing
check 2 (definition/use contracts) and plant P-21 are validated at the fixture
layer with no legacy regression across both runs. Blind audits scored at
`~/scratch/rca-defuse-rescore/run{1,2}/pkg/audit/`. Harness: 147 passed.

**Worker-pass decision (R7): BUILD.** The U3 emitter measurement
([`measurement-2026-07-08-defuse-emitter.md`](measurement-2026-07-08-defuse-emitter.md))
yields 10 bundles on the real Floods package (≤ 50 threshold) with both
flood-fill controls emitted — both pre-registered build conditions met. The
dedicated bundle-review worker pass is follow-up work with its own plan.

The honest external test of the class remains the next (fifth) Floods run.

## Prior runs (archived)
- 2026-07-08 SC-01 gate run 1 (SC-01 fix + v3 refactor; two-green waived at merge): [`score-2026-07-08-sc01-gate-run1.md`](score-2026-07-08-sc01-gate-run1.md)
- 2026-07-07 v3 rescore run 1 (SC-01 FAIL, led to the fix branch): [`score-2026-07-07-v3-rescore-run1.md`](score-2026-07-07-v3-rescore-run1.md)
- 2026-07-07 recall-determinism v3 build record: [`score-2026-07-07-recall-determinism-v3.md`](score-2026-07-07-recall-determinism-v3.md)
- 2026-07-07 adjudication-recall refactor (harness-only, no end-to-end run): [`score-2026-07-07-adjudication-recall-refactor.md`](score-2026-07-07-adjudication-recall-refactor.md)
- 2026-07-06 improvements run (14/14): [`score-2026-07-06-rca-improvements.md`](score-2026-07-06-rca-improvements.md)
- 2026-07-05 v2 (P-01..P-10, pre-behavior-tests): 10/10 recall, decoy clean — [`score-2026-07-05-v2.md`](score-2026-07-05-v2.md)
- 2026-07-05 v1: [`score-2026-07-05-v1.md`](score-2026-07-05-v1.md)
