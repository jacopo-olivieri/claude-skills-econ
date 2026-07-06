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

## b3b — Second-read recall sweep (conductor-planned, adds candidates)

A recall pass, not a recheck: re-read every file the first pass already flagged, to surface what
it missed. See `references/review-principles.md` for why. Runs after b3, before the recheck plan
(b4) is built, so the new candidates flow into the recheck automatically.

1. **Trigger set (per `review_depth`, from the SKILL.md depth-knob table).** Mechanically compute
   the set of scripts that carry at least one first-pass finding — i.e. a `candidate` code-error
   row. (b3b runs before the recheck, so every first-pass code finding is still `candidate`; none
   is `confirmed` yet — keying on `confirmed` here would make the sweep always skip.) At `shallow`
   include only scripts with a `candidate` row at Severity ≥ 3; at `standard`/`deep` any script
   with a `candidate` row of any severity. Group by `Code/Data Source` script. If the set is
   empty, skip b3b.
2. **Allocation.** Write `audit/plans/code_error_second_read_plan.md` yourself: one second-read
   worker per flagged script, with columns `| Worker ID | Script Scope | Shard File | Error ID
   Range | Known Findings |` (use the header `Shard File` exactly — the b3b lint requires it — and
   put each shard path, under `audit/_code_errors_second_read/`, in the cell). Each Error ID Range
   is fresh and globally disjoint from every b1 range and the merge-coordinator range. `Known
   Findings` lists the E-IDs and one-line mechanism already logged in that script.
3. **Dispatch** `prompts/second-read-worker.md` (stream = code-error), one subagent per row,
   fire-and-forget. At `deep` depth dispatch a second pass per script with a different
   `{MANDATE_LENS}` and its own disjoint range. Completion = shard exists; retry-once →
   blocked-continue.
4. **Merge.** Snapshot `code_error_register.md` to `audit/_run/snapshots/code_b3b/`; dispatch
   `prompts/merge-first-pass.md` filled for the code stream with `{SHARD_DIR}` =
   `audit/_code_errors_second_read/`, `{PLAN_PATH}` = the b3b allocation plan, and `{MERGE_REPORT}`
   = `audit/_run/merge_report_code_b3b.json`. The merge **adds** the new candidate rows to the
   existing canon, preserving every b3 row unchanged.
5. `lint_registers.py --stage b3b-code` (new rows in b3b ranges, all `candidate`, no b3 row
   deleted or mutated, report identity holds). Atomic rename on pass. Manifest `code_b3b = done`.

The recheck inventory (b4) then picks up every new `candidate`; the b6 no-surviving-candidate
rule is the hard backstop if one is missed.

## b4 — Recheck plan (conductor-computed, no LLM)

Inventory, mechanically:

- every `candidate` row (recheck resolves them all — none may survive b6), plus
- every `confirmed` row with Severity ≥ 3, plus
- a ~10% random sample of the remaining `confirmed` rows, stratified by Error Type (bounds
  total across strata: min 3 or all available if fewer, max 15).

Cluster per `review_depth` (manifest). At `shallow`/`standard`: cluster by Error Type, ≤ 8 IDs
per cluster. At `deep`: every **substantive ID** gets its own single-ID cluster — a substantive
ID is any inventory row that is `candidate`, or `confirmed` with Severity ≥ 3; the sampled
remaining `confirmed` rows are not substantive and may still be grouped by Error Type into
clusters of ≤ 8 IDs. Shard files under `audit/_code_error_recheck/`.
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
