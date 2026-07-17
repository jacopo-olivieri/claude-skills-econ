# Pipeline — code-error stream

Conductor instructions for stages b1–b6 of the code-error stream. Independent of the claims
stream — never seed, prioritise, or link code-error rows from paper findings; links happen at
cross-link. Lint stages here are `--stage b<N>-code`.

## b1 — Plan

1. Dispatch one planner subagent with `prompts/planner-code.md` filled; set
   `{CONTRACT_PATH}` to `audit/_run/contracts/planning.md`.
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

Fill `prompts/chunk-worker.md` per chunk, with `{CONTRACT_PATH}` set to
`audit/_run/contracts/code_first_pass.md` (the ERROR SCOPE lists live inside that skeleton —
they do not depend on plan quality). Completion = shard exists and passes
`lint_registers.py --stage b2-code --shard <path>`, then
`certify_stage.py set-shard --stage code_b2 --shard <path> --status done`; after the second
lint failure, use `--status blocked --reason "<lint failure>"`, then continue.

## b3 — First merge (adds rows)

Snapshot `code_error_register.md` to `audit/_run/snapshots/code_b3/`; dispatch
`prompts/merge-first-pass.md` filled for the code stream with `{CONTRACT_PATH}` set to
`audit/_run/contracts/merge_first_pass.md` → staging register +
`audit/_run/merge_report_code.json`; `lint_registers.py --stage b3-code` additionally checks
every inventory script is covered (coverage row in some shard footer) or has a documented
blocker. Atomic rename on pass.

## b3d — Deterministic detector emission and mapping (conductor-only)

Start `code_b3d`, then snapshot `code_error_register.md` to
`audit/_run/snapshots/code_b3d/`. Run
`emit_definition_use_bundles.py <package_root> --audit-dir audit` and
`check_manifests.py <package_root> --audit-dir audit`; both artifacts are required even when
their explicit standard-row count is zero. For every standard `DU-…` or `MF-…` source, record
one conductor decision in `audit/_run/detector_mapping_decisions.md` under
`| Channel | Source ID | Error ID | Mapping Kind |`, with `Mapping Kind` exactly
`new_candidate` or `existing_row`, plus one
`Declared detector Error-ID range: E-NNNN–E-NNNN` line. Advisory DU rows are not decided.

Copy the canonical code-error register to `_staging/` and append one typed `candidate` row for
each `new_candidate` decision, using only the declared detector range. Run
`build_detector_mapping.py <package_root> --audit-dir audit`; it validates the staged register,
the raw artifacts, the decisions, and the pre-b3d snapshot before atomically writing
`audit/_run/detector_mapping.md`. On success atomically rename the staged register over canon,
then run `certify_stage.py finish --stage code_b3d --outcome done`. Certification re-runs
`build_detector_mapping.py --check`, including the simple detector reproducibility check. A
missing raw artifact is never zero. The CV section uses its exact U3a explicit-zero form;
shared conventions remain at b4 until U4.

## b3b — Second-read recall sweep (conductor-planned, adds candidates)

A recall pass, not a recheck: re-read every file the first pass already flagged, to surface what
it missed. See `references/review-principles.md` for why. Runs after b3, before the recheck plan
(b4) is built, so the new candidates flow into the recheck automatically.

1. **Trigger set (per `review_depth`, from the SKILL.md depth-knob table).** Start `code_b3b` as
   required by SKILL.md, then mechanically compute the set of scripts that carry at least one
   first-pass finding — i.e. a `candidate` code-error row. (b3b runs before the recheck, so every
   first-pass code finding is still `candidate`; none
   is `confirmed` yet — keying on `confirmed` here would make the sweep always skip.) At `shallow`
   include only scripts with a `candidate` row at Severity ≥ 3; at `standard`/`deep` any script
   with a `candidate` row of any severity. Group by `Code/Data Source` script. If the set is
   empty, do not dispatch workers; certify `code_b3b` done via
   `certify_stage.py finish --stage code_b3b --outcome done` against the canonical register
   already promoted by b3.
2. **Allocation.** Write `audit/plans/code_error_second_read_plan.md` yourself: one second-read
   worker per flagged script, with columns `| Worker ID | Script Scope | Shard File | Error ID
   Range | Known Findings |` (use the header `Shard File` exactly — the b3b lint requires it — and
   put each shard path, under `audit/_code_errors_second_read/`, in the cell). Each Error ID Range
   is fresh and globally disjoint from every b1 range and the merge-coordinator range. `Known
   Findings` lists the E-IDs and one-line mechanism already logged in that script.
3. **Dispatch** `prompts/second-read-worker.md` (stream = code-error), one subagent per row,
   with `{CONTRACT_PATH}` set to `audit/_run/contracts/second_read_code.md`,
   fire-and-forget. At `deep` depth dispatch a second pass per script with a different
   `{MANDATE_LENS}` and its own disjoint range. A worker is complete when its shard exists at the
   planned path **and** passes `lint_registers.py --stage b3b-code --shard <path>`; retry-once →
   blocked-continue.
4. **Merge.** Snapshot `code_error_register.md` to `audit/_run/snapshots/code_b3b/`; dispatch
   `prompts/merge-first-pass.md` filled for the code stream with `{CONTRACT_PATH}` set to
   `audit/_run/contracts/merge_first_pass.md`, `{SHARD_DIR}` = `audit/_code_errors_second_read/`,
   `{PLAN_PATH}` = the b3b allocation plan, and `{MERGE_REPORT}` =
   `audit/_run/merge_report_code_b3b.json`. The merge **adds** the new candidate rows to the
   existing canon, preserving every b3 row unchanged.
5. `lint_registers.py --stage b3b-code` (new rows in b3b ranges, all `candidate`, no b3 row
   deleted or mutated, report identity holds). Atomic rename on pass, then certify with
   `certify_stage.py finish --stage code_b3b --outcome done`.

The recheck inventory (b4) then picks up every new `candidate`; the b6 no-surviving-candidate
rule is the hard backstop if one is missed.

## b4 — Recheck plan (conductor-computed, no LLM)

Inventory, mechanically:

- every `candidate` row (recheck resolves them all — none may survive b6), plus
- every `confirmed` row with Severity ≥ 3, plus
- a deterministic sample of the remaining `confirmed` rows (Severity ≤ 2), stratified by Error
  Type, using the code-error stream parameters in the deterministic recheck sampling rule
  (`references/registers.md`).

Cluster per `review_depth` (manifest). At `shallow`/`standard`: cluster by Error Type, ≤ 8 IDs
per cluster. At `deep`: every **substantive ID** gets its own single-ID cluster — a substantive
ID is any inventory row that is `candidate`, or `confirmed` with Severity ≥ 3; the sampled
remaining `confirmed` rows are not substantive and may still be grouped by Error Type into
clusters of ≤ 8 IDs. Shard files under `audit/_code_error_recheck/`.
Write `audit/plans/code_error_recheck_plan.md` yourself with the same table formats as the
claims recheck plan (inventory `| ID | Reason | Likely Evidence |`; clusters
`| Cluster ID | Cluster Name | Assigned IDs | Shard File |`; vocabulary pointer to
the recheck code contract). `lint_registers.py --stage b4-code`. One recheck pass — no looping.

**Shared-conventions grep (consumes the b3c artifact; adds candidates before the plan is frozen).**
If `audit/_run/conventions.md` exists and lists any convention, then before writing the recheck
plan, for each listed convention grep the codebase for its definition sites — search the code for
the boundary literal, sentinel, unit/scale factor, path separator, date mask, or ID/merge key the
`Stated Definition` column records (e.g. a fiscal-year boundary "July" → grep for month/quarter
literals and cutoff comparisons in the date-construction scripts; a missing-value sentinel → grep
for the sentinel value and the replace/recode calls that set it; an enumerated member list
(`enumerated_member_list`) → locate each site that re-materializes the stated list by hand —
hand-written category or level lists in keep-or-drop conditions, value-label definitions, list or
dictionary literals in any language, column-selection vectors, legend or axis label arrays — and
take the set difference between each materialized set and the stated set, typing any missing,
extra, or renamed member by its mechanism). Guard for enumerated member lists: a site that
materializes a strict subset of the stated list with explicit local subsetting intent — a named
sub-sample, a figure- or table-specific filter, a commented restriction — is recorded as
reviewed-not-divergent, not emitted as a candidate. Any site whose definition
disagrees with the stated one becomes a new `candidate` code-error row, typed by its mechanism per
the taxonomy (a boundary literal mismatch is `treatment_or_event_timing_error`, a sentinel or
scale mismatch is `aggregation_or_unit_error`, a divergent merge key is
`merge_key_or_cardinality_error`, and so on), minted from an unused error-ID range and folded into
the b4 inventory so the recheck resolves it. If the artifact is absent or lists no convention,
skip this grep — it is non-blocking. This is the cross-stream handoff: a convention confirmed on
the claims side reaches the code side as a concrete grep target.

Detector-minted candidates already exist as ordinary canonical `candidate` rows before this plan
is built, so the ordinary every-candidate inventory rule includes them. The b4-code lint also
reads `audit/_run/detector_mapping.md`: every mapped Error ID must occur in the inventory, and its
`Likely Evidence` must name every mapped DU or MF source ID. The detector mapping table does not
live in `code_error_recheck_plan.md`.

## b5 — Recheck cluster workers (parallel)

`prompts/recheck-cluster-worker.md` with stream = code and `{CONTRACT_PATH}` set to
`audit/_run/contracts/recheck_code.md`. Same completion/lint/retry rules (`--stage b5-code`).
Record each passing shard with `certify_stage.py set-shard --stage code_b5 --shard <path> --status
done`, or a twice-failing shard with `--status blocked --reason "<lint failure>"`.
No new IDs; no hunting for unrelated errors.

## b6 — Recheck merge (mutates rows)

Snapshot → `prompts/merge-recheck.md` (stream = code, `{CONTRACT_PATH}` =
`audit/_run/contracts/merge_recheck.md`) → staging +
`audit/code_error_recheck_summary.md` → `lint_registers.py --stage b6-code` → atomic rename.
The b6 lint also closes the definition/use channel: every mapped Bundle ID must occur in the
mapped Error ID's ledger `Evidence Checked`, that Error ID must have exactly one ledger
disposition, and the final register status must agree with it. A duplicate disposition must name
the equivalent canonical confirmed issue row explicitly. Advisory bundles are excluded.
After promotion, certify with `certify_stage.py finish --stage code_b6 --outcome done`.
