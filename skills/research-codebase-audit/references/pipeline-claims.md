# Pipeline — claims stream (paper vs. code)

Conductor instructions for stages b1–b6 of the claims stream. Skeletons live in
`references/prompts/`; schemas and vocabulary in `references/registers.md` (workers see the
generated `audit/audit_readme.md`). Lint stages here are `--stage b<N>-claims`.

## b1 — Plan

1. Dispatch one planner subagent with `prompts/planner-claims.md` filled.
2. Planner writes `audit/plans/claims_review_plan.md` with the worker allocation table
   (Worker ID · Paper Scope · Likely Code Scope · Shard File under `audit/_work/` ·
   Claim ID Range · Output ID Range · Review Focus).
3. Run `lint_registers.py --stage b1-claims`. Retry-once → blocked-continue as always.

**Sizing rules (the planner skeleton carries these verbatim; you verify the plan obeys them):**

- Paper scope per worker: one coherent section or ≤ ~10 paper pages; split longer sections.
- Expected claims per worker: 15–35. If a scope would exceed that, split it.
- ID ranges are generous: per worker, `max(50, 3 × expected claims)` claim IDs and
  `max(30, 3 × expected outputs)` output IDs, globally disjoint. Reserve a 50-ID
  merge-coordinator range per register on top.
- Support passes are **dropped in v1**: worker contradictions are preserved as
  `unclear`/`inconsistent` at merge and flow mechanically into the recheck inventory.

## b2 — Section workers (parallel, fire-and-forget)

1. For each row of the allocation table, fill `prompts/section-worker.md` (one subagent per
   worker, single message, `worker_model` from the manifest).
2. A worker is complete when its shard exists at the planned path **and** passes
   `lint_registers.py --stage b2-claims --shard <path>`.
3. On lint failure: re-dispatch that worker once with the lint report appended. Second failure:
   mark the shard blocked in the manifest, continue.

## b3 — First merge (adds rows)

1. Snapshot `claims_register.md` + `output_register.md` to `audit/_run/snapshots/claims_b3/`.
2. Dispatch one coordinator with `prompts/merge-first-pass.md` filled for the claims stream.
   It writes **staging** registers (`audit/_staging/claims_register.md`,
   `audit/_staging/output_register.md`) and `audit/_run/merge_report_claims.json`
   (per register: `shard_rows`, `dedup_removed`, `added`, `conflicts`, `coverage_gaps`,
   `blocked_shards`).
3. Run `lint_registers.py --stage b3-claims` (checks staging + report: no dup IDs, IDs ⊆ union
   of planned ranges, links C↔O bidirectional, cross-link columns blank, row-count
   reconciliation, coverage reconciled). On pass, atomically rename staging over canon.

## b4 — Recheck plan (conductor-computed, no LLM)

Build the recheck inventory **mechanically** from the canonical claims register (claims rows
only — output rows are never rechecked directly; they change only through the claims recheck
merge):

- every issue-flagged claim row (Severity non-empty — this subsumes all `inconsistent` rows
  and all severities), plus
- every `unclear` row, plus
- a ~10% random sample of `confirmed` rows, stratified by Claim Type (bounds total across
  strata: min 3 or all available if fewer, max 15).

Group the inventory by Claim Type into clusters of ≤ 8 IDs; assign each cluster a shard file
under `audit/_recheck/`. Write `audit/plans/claims_recheck_plan.md` yourself with:
an inventory table `| ID | Reason | Likely Evidence |`; a cluster table
`| Cluster ID | Cluster Name | Assigned IDs | Shard File |`; and a pointer to the
verdict/evidence vocabulary in `audit_readme.md`. There is exactly **one** recheck pass — no
looping. Run `lint_registers.py --stage b4-claims`.

## b5 — Recheck cluster workers (parallel)

Fill `prompts/recheck-cluster-worker.md` per cluster (stream = claims). Completion, lint
(`--stage b5-claims --shard <path>`), retry, and blocked handling as in b2. Workers judge
assigned IDs only and mint no IDs.

## b6 — Recheck merge (mutates rows)

1. Snapshot both registers to `audit/_run/snapshots/claims_b6/`.
2. Dispatch one coordinator with `prompts/merge-recheck.md` (stream = claims). It applies the
   verdict → register mapping from `audit_readme.md`, writes staging registers and
   `audit/claims_recheck_summary.md`, declaring any splits/merges.
3. `lint_registers.py --stage b6-claims` (row counts vs snapshot unless declared; statuses in
   the b6+ allowed set; summary exists). On pass, atomic rename.

Stream complete: manifest `claims_b6 = done`; `confirmation_needed`/`blocked` rows survive
as-is.
