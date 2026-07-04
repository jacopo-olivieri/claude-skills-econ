# Pipeline — code-error stream

Conductor instructions for stages b1–b6 of the code-error stream. Independent of the claims
stream — never seed, prioritise, or link code-error rows from paper findings; links happen at
cross-link. Lint stages here are `--stage b<N>-code`.

## b1 — Plan

1. Dispatch one planner subagent with `prompts/planner-code.md` filled.
2. Planner writes `audit/plans/code_error_review_plan.md`: full script inventory (from `audit/CODEMAP.md`,
   minus manifest scope exclusions), and the chunk allocation table (Chunk ID · Script Scope ·
   Likely Pipeline Stage/Outputs · Shard File under `audit/_code_errors/` · Error ID Range ·
   Review Focus). **Every inventory script sits in exactly one chunk** (lint b1-code enforces).
3. The plan always includes one **hygiene chunk** — package-level, journal-agnostic, in
   scope in every mode. The plan carries the checklist below as its own `## Hygiene
   Checklist` subsection (a multi-line checklist cannot live in an allocation-table cell);
   the conductor fills the hygiene chunk's `{CHUNK_PRIORITIES}` from that subsection.
4. `lint_registers.py --stage b1-code`.

**Sizing rules (carried verbatim in the planner skeleton):**

- Chunks of 4–10 scripts or ≤ ~2,000 total lines, grouped by pipeline stage and language.
- Error ID range per chunk: `max(50, 10 × scripts in chunk)`, globally disjoint, plus a 50-ID
  merge-coordinator range.
- The hygiene chunk counts package-level files (README, manifests, config) as its scope; it
  gets an ID range like any other chunk.

**Hygiene chunk checklist** (fills the planner's `{HYGIENE_CHECKLIST}` slot and, via the
plan, the hygiene chunk worker's `{CHUNK_PRIORITIES}`):

1. README/data-availability cross-checks: every declared input actually consumed by code;
   every consumed input declared; per-table/figure script mapping present and correct;
   file inventory complete (files present but never referenced, referenced but absent).
2. Environment capture: absolute paths; unpinned package/library versions; undeclared ado/
   package/library dependencies; missing environment or requirements manifest.
3. PII scan (J-PAL `PII_stata_scan.do` logic, applied statically): scan data files, code, and
   logs for identifying variables — names, addresses, phone numbers, national IDs, GPS
   coordinates, birth dates. Record hits as `pii_or_disclosure_risk`.

Hygiene and provenance findings default to severity 1–2 per the rubric.

## b2 — Chunk workers (parallel, fire-and-forget)

Fill `prompts/chunk-worker.md` per chunk (the ERROR SCOPE lists live inside that skeleton —
they do not depend on plan quality). Completion = shard exists and passes
`lint_registers.py --stage b2-code --shard <path>`; retry-once → blocked-continue.

## b3 — First merge (adds rows)

Snapshot `code_error_register.md` to `audit/_run/snapshots/code_b3/`; dispatch
`prompts/merge-first-pass.md` filled for the code stream → staging register +
`audit/_run/merge_report_code.json`; `lint_registers.py --stage b3-code` additionally checks
every inventory script is covered (coverage row in some shard footer) or has a documented
blocker. Atomic rename on pass.

## b4 — Recheck plan (conductor-computed, no LLM)

Inventory, mechanically:

- every `candidate` row (recheck resolves them all — none may survive b6), plus
- every `confirmed` row with Severity ≥ 3, plus
- a ~10% random sample of the remaining `confirmed` rows, stratified by Error Type (bounds
  total across strata: min 3 or all available if fewer, max 15).

Cluster by Error Type, ≤ 8 IDs per cluster, shard files under `audit/_code_error_recheck/`.
Write `audit/plans/code_error_recheck_plan.md` yourself with the same table formats as the
claims recheck plan (inventory `| ID | Reason | Likely Evidence |`; clusters
`| Cluster ID | Cluster Name | Assigned IDs | Shard File |`; vocabulary pointer to
`audit_readme.md`). `lint_registers.py --stage b4-code`. One recheck pass — no looping.

## b5 — Recheck cluster workers (parallel)

`prompts/recheck-cluster-worker.md` with stream = code. Same completion/lint/retry rules
(`--stage b5-code`). No new IDs; no hunting for unrelated errors.

## b6 — Recheck merge (mutates rows)

Snapshot → `prompts/merge-recheck.md` (stream = code) → staging +
`audit/code_error_recheck_summary.md` → `lint_registers.py --stage b6-code` → atomic rename.
