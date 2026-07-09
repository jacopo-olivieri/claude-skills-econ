# Pipeline — claims stream (paper vs. code)

Conductor instructions for stages b1–b6 of the claims stream. Skeletons live in
`references/prompts/`; schemas and vocabulary in `references/registers.md` (workers see their
generated role contract). Lint stages here are `--stage b<N>-claims`.

## b1 — Plan

1. Dispatch one planner subagent with `prompts/planner-claims.md` filled; set
   `{CONTRACT_PATH}` to `audit/_run/contracts/planning.md`.
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
   worker, single message, `worker_model` from the manifest); set `{CONTRACT_PATH}` to
   `audit/_run/contracts/claims_first_pass.md`.
2. A worker is complete when its shard exists at the planned path **and** passes
   `lint_registers.py --stage b2-claims --shard <path>`.
3. On lint failure: re-dispatch that worker once with the lint report appended. Second failure:
   mark the shard blocked in the manifest, continue.

## b3 — First merge (adds rows)

1. Snapshot `claims_register.md` + `output_register.md` to `audit/_run/snapshots/claims_b3/`.
2. Dispatch one coordinator with `prompts/merge-first-pass.md` filled for the claims stream; set
   `{CONTRACT_PATH}` to `audit/_run/contracts/merge_first_pass.md`.
   It writes **staging** registers (`audit/_staging/claims_register.md`,
   `audit/_staging/output_register.md`) and `audit/_run/merge_report_claims.json`
   (per register: `shard_rows`, `dedup_removed`, `added`, `conflicts`, `coverage_gaps`,
   `blocked_shards`).
3. Run `lint_registers.py --stage b3-claims` (checks staging + report: no dup IDs, IDs ⊆ union
   of planned ranges, links C↔O bidirectional, cross-link columns blank, row-count
   reconciliation, coverage reconciled). On pass, atomically rename staging over canon.

## b3c — Shared-conventions consolidation (adds no rows; emits a cross-stream artifact)

Operationalizes standing self-consistency check 2 ("Shared and definition/use conventions agree", `registers.md`):
the merged claims register now records, across many rows, the conventions the package uses in
more than one place; this step collects them into one small list so the code-stream recheck (b4,
`pipeline-code-errors.md`) can grep the codebase for sites that violate each. Runs after the
first merge (b3), before the recheck plan (b4). Non-blocking: a package with no qualifying
convention produces an empty-or-absent artifact and nothing downstream fails.

1. Dispatch one worker with `prompts/consolidate-conventions.md` filled (claims stream); set
   `{CONTRACT_PATH}` to `audit/_run/contracts/conventions.md`. It reads the canonical
   `claims_register.md` and writes `audit/_run/conventions.md` — a small Markdown
   table, one row per stated convention the paper uses in more than one place, drawn **only** from
   the categories standing check 2 enumerates (fiscal-year or sample-window boundary, date-parse
   mask, missing-value sentinel, unit/scale factor, path separator, ID/merge key, enumerated
   member list), with columns
   `| Convention | Category | Stated Definition | Sites Already Seen |`. `Stated Definition` is
   what the paper states (with the C-ID it came from; for an `enumerated_member_list` it quotes
   the full member set verbatim); `Sites Already Seen` lists the files/rows
   already logged for it. A convention stated in only one place is **not** listed — except an
   `enumerated_member_list`, where a single register row naming the member set qualifies: the
   second side of the comparison is supplied by the code-side re-materialization sites the b4
   grep locates, not by a second register row.
2. If no convention qualifies — none is used in more than one place and no single register row
   names an enumerated member list — the worker writes the table header with no rows (or omits
   the file). Either is valid; the step never blocks and adds no register rows.
3. This step mutates no canonical register, so there is no snapshot/staging/rename. It is a
   read-only emit; the artifact is advisory input to the code-stream recheck grep. Manifest
   `claims_b3c = done`.

## b3b — Second-read recall sweep (conductor-planned, adds candidates)

A recall pass, not a recheck: re-read every file/section the first pass already flagged, to
surface the inconsistencies it missed. See `references/review-principles.md` for why. Runs after
b3, before the recheck plan (b4), so the new rows flow into the recheck automatically.

1. **Trigger set (per `review_depth`, from the SKILL.md depth-knob table).** Mechanically compute
   the set of files/sections that produced at least one issue-flagged (`inconsistent`) claim — at
   `shallow` only those with a Severity ≥ 3 issue, at `standard`/`deep` any issue-flagged claim.
   Key each trigger to the claim row's `Code/Data Source` file(s) and `Paper Context` section. If
   the set is empty, skip b3b.
2. **Allocation.** Write `audit/plans/claims_second_read_plan.md` yourself: one second-read worker
   per flagged file/section, columns `| Worker ID | File/Section Scope | Shard File | Claim ID
   Range | Output ID Range | Known Findings |` (use the header `Shard File` exactly — the b3b lint
   requires it — and put each shard path, under `audit/_work_second_read/`, in the cell). Ranges
   are fresh and globally disjoint from every b1 range and both merge-coordinator ranges. `Known
   Findings` lists the C-IDs and one-line mechanism already logged there.
3. **Dispatch** `prompts/second-read-worker.md` (stream = claims), one subagent per row,
   with `{CONTRACT_PATH}` set to `audit/_run/contracts/second_read_claims.md`,
   fire-and-forget. At `deep` depth dispatch a second pass with a different `{MANDATE_LENS}` and
   its own disjoint ranges. A worker is complete when its shard exists at the planned path **and**
   passes `lint_registers.py --stage b3b-claims --shard <path>`; retry-once → blocked-continue.
4. **Merge.** Snapshot `claims_register.md` + `output_register.md` to
   `audit/_run/snapshots/claims_b3b/`; dispatch `prompts/merge-first-pass.md` filled for the
   claims stream with `{CONTRACT_PATH}` set to `audit/_run/contracts/merge_first_pass.md`,
   `{SHARD_DIR}` = `audit/_work_second_read/`, `{PLAN_PATH}` = the b3b allocation plan, and
   `{MERGE_REPORT}` = `audit/_run/merge_report_claims_b3b.json`. The merge
   **adds** the new rows to the existing canon, preserving every b3 row unchanged.
5. `lint_registers.py --stage b3b-claims` (new claim rows in b3b ranges and `inconsistent` or
   `unclear`; new output rows not `listed`/`confirmed`; no b3 row deleted or mutated; C↔O links
   bidirectional; report identity holds). Atomic rename on pass. Manifest `claims_b3b = done`.

The recheck inventory (b4) then picks up every new issue-flagged and `unclear` row.

## b4 — Recheck plan (conductor-computed, no LLM)

Build the recheck inventory **mechanically** from the canonical claims register (claims rows
only — output rows are never rechecked directly; they change only through the claims recheck
merge):

- every issue-flagged claim row (Severity non-empty — this subsumes all `inconsistent` rows
  and all severities), plus
- every `unclear` row, plus
- a deterministic sample of `confirmed` rows, stratified by Claim Type, using the claims stream
  parameters in the deterministic recheck sampling rule (`references/registers.md`).

Cluster per `review_depth` (manifest). At `shallow`/`standard`: group the inventory by Claim
Type into clusters of ≤ 8 IDs. At `deep`: every **substantive ID** gets its own single-ID
cluster — a substantive ID is any inventory claim row that is issue-flagged (Severity
non-empty) or `unclear`; the sampled clean `confirmed` rows are not substantive and may still
be grouped by Claim Type into clusters of ≤ 8 IDs. Assign each cluster a shard file
under `audit/_recheck/`. Write `audit/plans/claims_recheck_plan.md` yourself with:
an inventory table `| ID | Reason | Likely Evidence |`; a cluster table
`| Cluster ID | Cluster Name | Assigned IDs | Shard File |`; and a pointer to the
verdict/evidence vocabulary in the recheck claims contract. There is exactly **one** recheck pass — no
looping. Run `lint_registers.py --stage b4-claims`.

## b5 — Recheck cluster workers (parallel)

Fill `prompts/recheck-cluster-worker.md` per cluster (stream = claims), with
`{CONTRACT_PATH}` set to `audit/_run/contracts/recheck_claims.md`. Completion, lint (`--stage
b5-claims --shard <path>`), retry, and blocked handling as in b2. Workers judge assigned IDs
only and mint no IDs.

## b6 — Recheck merge (mutates rows)

1. Snapshot both registers to `audit/_run/snapshots/claims_b6/`.
2. Dispatch one coordinator with `prompts/merge-recheck.md` (stream = claims), with
   `{CONTRACT_PATH}` set to `audit/_run/contracts/merge_recheck.md`. It applies the verdict →
   register mapping from that contract, writes staging registers and
   `audit/claims_recheck_summary.md`, declaring any splits/merges.
3. `lint_registers.py --stage b6-claims` (row counts vs snapshot unless declared; statuses in
   the b6+ allowed set; summary exists). On pass, atomic rename.

Stream complete: manifest `claims_b6 = done`; `confirmation_needed`/`blocked` rows survive
as-is.
