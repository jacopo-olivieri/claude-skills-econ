# Pipeline — code-error stream

Conductor instructions for stages b1–b6 of the code-error stream. Independent of the claims
stream — never seed, prioritise, or link code-error rows from paper findings; links happen at
cross-link. Lint stages here are `--stage b<N>-code`.

## b1 — Plan

1. Dispatch one planner subagent with `prompts/planner-code.md` filled (role:
   `code_b1_planner`); set
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

Fill `prompts/chunk-worker.md` per chunk (role: `code_b2_chunk`), with `{CONTRACT_PATH}` set to
`audit/_run/contracts/code_first_pass.md` (the ERROR SCOPE lists live inside that skeleton —
they do not depend on plan quality). Completion = shard exists and passes
`lint_registers.py --stage b2-code --shard <path>`, then
`certify_stage.py set-shard --stage code_b2 --shard <path> --status done`; after the second
lint failure, use `--status blocked --reason "<lint failure>"`, then continue.

## b3 — First merge (adds rows)

Snapshot `code_error_register.md` to `audit/_run/snapshots/code_b3/`; dispatch
`prompts/merge-first-pass.md` filled for the code stream (role: `code_b3_merge`) with
`{CONTRACT_PATH}` set to
`audit/_run/contracts/merge_first_pass.md` → staging register +
`audit/_run/merge_report_code.json`; atomic rename over canon, then
`lint_registers.py --stage b3-code` (the same lint the `code_b3` certification obligation
re-runs against the promoted register) additionally checks every inventory script is covered
(coverage row in some shard footer) or has a documented blocker. On failure, restore canon from
`audit/_run/snapshots/code_b3/` and re-merge.

## b3d — Detector emission, conventions scan, and mapping

In replication mode, do not start `code_b3d` until `claims_b3c` is certified: its
`audit/_run/conventions.md` artifact is mandatory, including the header-only explicit-zero case.
An absent artifact is a refusal (“wait for claims_b3c”), never zero. In code-errors-only mode no
claims artifact exists; any conventions, CV scan, or CV decision is refused.

1. Start `code_b3d`, then snapshot `code_error_register.md` to
   `audit/_run/snapshots/code_b3d/`. Run
   `emit_definition_use_bundles.py <package_root> --audit-dir audit` and
   `check_manifests.py <package_root> --audit-dir audit`; both deterministic artifacts are
   required even when their standard-row count is zero.
2. In replication mode, if `conventions.md` has rows, dispatch one
   `prompts/conventions-scan-worker.md` worker (role: `b3d_conventions_scan`) after the detectors
   and before decisions. It writes only `audit/_run/cv_scan.md`; completion requires the parser
   contract to accept exactly one terminal verdict per convention. Retry once on failure, then
   mark `code_b3d` blocked and continue. If `conventions.md` has no rows, do not dispatch and do
   not create `cv_scan.md`.
3. For a non-empty scan, copy `audit/_run/cv_scan.md` byte-for-byte to
   `audit/_run/snapshots/code_b3d/cv_scan.md`, then run
   `build_detector_mapping.py <package_root> --audit-dir audit --list-cv-sources`. Use that
   read-only table as the sole source of CV IDs when writing decisions.
4. Record one conductor decision per standard DU/MF source and per convention in
   `audit/_run/detector_mapping_decisions.md`, under
   `| Channel | Source ID | Error ID | Mapping Kind |`, plus one
   `Declared detector Error-ID range: E-NNNN–E-NNNN` line. DU/MF and divergent CV sources use
   `new_candidate` or `existing_row`; a not_divergent CV source uses
   `reviewed_not_divergent` with Error ID exactly `—`. Advisory DU rows are not decided.
5. Copy the canonical code-error register to `_staging/` and append one typed `candidate` row
   for each `new_candidate` decision, using only the declared detector range. Run
   `build_detector_mapping.py <package_root> --audit-dir audit`; it validates the staged
   register, raw artifacts, frozen CV scan, decisions, and pre-b3d snapshot before atomically
   writing `audit/_run/detector_mapping.md`. On success atomically rename the staged register
   over canon, then finish `code_b3d`. Certification re-runs `build_detector_mapping.py --check`:
   DU/MF are rediscovered for reproducibility, while CV is checked against the frozen scan and
   its emitted section byte-for-byte. A missing required artifact is never zero.

## b3b — Second-read recall sweep (conductor-planned, adds candidates)

A recall pass, not a recheck: re-read detector/first-pass-flagged files and a deterministic
stratified sample of earned-clean files. See `references/review-principles.md` for why. Runs
after b3d, before the recheck plan
(b4) is built, so the new candidates flow into the recheck automatically.

1. **Trigger set and allocation.** Start `code_b3b`, then run
   `scripts/build_second_read_plan.py <package_root> --audit-dir audit`. The builder owns the
   generated allocation block in `audit/plans/code_error_second_read_plan.md`: columns
   `| Worker ID | Script Scope | Shard File | Error ID Range | Reason | Known Findings |
   Assigned Handoff IDs |`. Reason precedence is `detector > flagged > clean_sample`; `handoff`
   is reserved and Assigned Handoff IDs remains empty until U7. It rereads detector files at
   every depth, applies the SKILL.md flagged threshold, and draws the coverage-based clean sample
   with the documented hash/stratum/two-pass cap algorithm. Its sampler log names unreviewed
   files and unserved strata. If the computed flagged set and sample are both empty, do not
   dispatch workers; instead freeze the zero-work evidence the b3b certification obligation
   verifies — snapshot the post-b3d `code_error_register.md` to `audit/_run/snapshots/code_b3b/`
   and write a zero-work `audit/_run/merge_report_code_b3b.json`
   (`{"code_error_register.md": {"shard_rows": 0, "dedup_removed": 0, "added": 0},
   "footer_dispositions": []}`) — then certify `code_b3b` done via
   `certify_stage.py finish --stage code_b3b --outcome done` against the canonical register
   already promoted by b3.
2. **Dispatch** `prompts/second-read-worker.md` (stream = code-error; role:
   `code_b3b_second_read`), one subagent per row,
   with `{CONTRACT_PATH}` set to `audit/_run/contracts/second_read_code.md`,
   fire-and-forget. At `deep` depth the generated plan already carries two allocation rows per
   detector/flagged file — the second row IS the second pass; dispatch one worker per row and
   give the second row a different `{MANDATE_LENS}` (never dispatch extra workers beyond the
   plan's rows). A worker is complete when its shard exists at the
   planned path **and** passes `lint_registers.py --stage b3b-code --shard <path>`; retry-once →
   blocked-continue.
3. **Merge.** Snapshot the post-b3d `code_error_register.md` to
   `audit/_run/snapshots/code_b3b/`; dispatch
   `prompts/merge-first-pass.md` filled for the code stream (role: `code_b3b_merge`) with
   `{CONTRACT_PATH}` set to
   `audit/_run/contracts/merge_first_pass.md`, `{SHARD_DIR}` = `audit/_code_errors_second_read/`,
   `{PLAN_PATH}` = the b3b allocation plan, and `{MERGE_REPORT}` =
   `audit/_run/merge_report_code_b3b.json`. The merge **adds** the new candidate rows to the
   existing canon, preserving every b3 row unchanged.
4. Atomic rename over canon, then `lint_registers.py --stage b3b-code` (recomputes the
   generated plan against the frozen `code_b3b` snapshot and the skip predicate; new rows in
   b3b ranges, all `candidate`, no baseline row deleted or mutated, report identity and
   typed-footer dispositions hold — the same lint the certification obligation re-runs). On
   failure, restore canon from `audit/_run/snapshots/code_b3b/` and re-merge; on pass certify
   with `certify_stage.py finish --stage code_b3b --outcome done`.

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

Conventions are scanned and mapped at b3d; b4 performs no shared-conventions grep.

Detector-minted candidates already exist as ordinary canonical `candidate` rows before this plan
is built, so the ordinary every-candidate inventory rule includes them. The b4-code lint also
reads `audit/_run/detector_mapping.md`: every mapped Error ID must occur in the inventory, and its
`Likely Evidence` must name every mapped detector source ID — DU, MF, or divergent CV.
`reviewed_not_divergent` CV rows need no inventory row. The detector mapping table does not
live in `code_error_recheck_plan.md`.

## b5 — Recheck cluster workers (parallel)

`prompts/recheck-cluster-worker.md` with stream = code (role: `code_b5_recheck_cluster`) and
`{CONTRACT_PATH}` set to
`audit/_run/contracts/recheck_code.md`. Same completion/lint/retry rules (`--stage b5-code`).
Record each passing shard with `certify_stage.py set-shard --stage code_b5 --shard <path> --status
done`, or a twice-failing shard with `--status blocked --reason "<lint failure>"`.
The blocked command writes one conductor fallback ledger row per assigned ID. After every shard is
terminal, run `scripts/verify_dismissals.py <package-root> --audit-dir audit`; it always writes
`audit/_run/dismissal_receipts.md`, using the explicit-zero form when no mapped `not_error` is
proposed. No new IDs; no hunting for unrelated errors.

## b6 — Recheck merge (mutates rows)

Snapshot → `prompts/merge-recheck.md` (stream = code, role: `code_b6_merge`, `{CONTRACT_PATH}` =
`audit/_run/contracts/merge_recheck.md`) → staging +
`audit/code_error_recheck_summary.md`. Then run `scripts/assemble_boundary.py <package-root>
--audit-dir audit` before `lint_registers.py --stage b6-code`; only the assembler may apply a
mechanically mapped `not_error`. The lint re-joins every mapping, witness outcome, verification
record, receipt, split-lineage row, and duplicate on the full channel/source/witness key; it
requires exactly one disposition and final-status agreement. After the lint passes, atomically
promote the staged register.
After promotion, certify with `certify_stage.py finish --stage code_b6 --outcome done`.
