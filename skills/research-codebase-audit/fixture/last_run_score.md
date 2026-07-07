# Last fixture run score

> **⚠️ Re-score pending.** The `feat/rca-adjudication-recall-v2` refactor (units
> U1–U8, plan `2026-07-06-003`) landed on 2026-07-07 and changed skeletons,
> pipelines, `registers.md`, and the scripts. The **automated harness is GREEN
> (58 passed)** but the **end-to-end LLM fixture re-score has not been run** and
> is required before merging to `main` — see
> [`score-2026-07-07-adjudication-recall-refactor.md`](score-2026-07-07-adjudication-recall-refactor.md).
> The GREEN result below is the last completed end-to-end run and predates the refactor.

**Latest completed end-to-end run:** 2026-07-06 — see [`score-2026-07-06-rca-improvements.md`](score-2026-07-06-rca-improvements.md)

| Metric | Result |
| --- | --- |
| **Recall (must_find)** | **14 / 14** |
| **Precision (decoy D-01)** | **PASS** — no placebo/`fig_placebo` reference anywhere |
| **Expected confirmed examples** | **PASS** — both clean |
| **Status conflict SC-01** | **PASS (vacuous)** — P-11 claim `inconsistent`, no confirmed↔confirmed pair |
| **GATE VERDICT** | **GREEN** |

Behavior tests: P-12 (second-read legend swap) recovered — **required the b3b
second-read sweep**; P-13 (725/2,416 = 30% vs 25%) flagged `inconsistent` (sev 3);
P-14 (one-in-ten vs 1-in-20) recovered via DUAL-ACCEPT branch (a), an `inconsistent`
claim at sev 2 (C-0017). Scored blind run at
`~/scratch/rca-fixture-rescore/pkg/audit/`. Also serves as the deferred validation for
the residuals batch committed as 58128ea.

## Prior runs (archived)
- 2026-07-05 v2 (P-01..P-10, pre-behavior-tests): 10/10 recall, decoy clean — [`score-2026-07-05-v2.md`](score-2026-07-05-v2.md)
- 2026-07-05 v1: [`score-2026-07-05-v1.md`](score-2026-07-05-v1.md)
