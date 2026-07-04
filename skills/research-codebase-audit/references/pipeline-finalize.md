# Pipeline — finalize (cross-link, rewrite, export)

Runs after both streams (or the only stream) reach `done`/`blocked` at b6.

## Mode skip rules

| Mode | b7 cross-link | b8 rewrite | b9 export |
| --- | --- | --- | --- |
| Full replication | yes | both registers | Overview + Paper Claims + Code Errors |
| Code-errors-only | **skip** (no claims register) | code register only | Overview + Code Errors |

A stream that ended with blocked stages still finalizes: blocked rows carry their status into
the export; blocked *stages* are listed in the final report, and cross-link runs on whatever
canon exists.

## b7 — Cross-link (full replication only)

1. Snapshot both link-bearing registers to `audit/_run/snapshots/b7/`.
2. Dispatch one subagent with `prompts/cross-linker.md`. It edits **only** `Related Error IDs`
   (claims) and `Related Claim IDs` (code errors) in staging copies, and writes
   `audit/register_cross_link_summary.md`.
3. `lint_registers.py --stage b7`: non-link columns byte-identical to snapshot; every link
   resolves both ways (C-x lists E-y ⟺ E-y lists C-x); summary exists. Atomic rename.

## b8 — Author-facing rewrite

1. Snapshot to `audit/_run/snapshots/b8/`.
2. Dispatch one subagent with `prompts/rewriter.md` (register paths per mode). This is the
   dedicated clarity pass: it renames technical fields to `*_Original` and writes author-facing
   versions, armed with the five contrastive gold examples and the jargon ban carried verbatim
   in the skeleton.
3. `lint_registers.py --stage b8`: counts/IDs/statuses/paths byte-identical; `*_Original`
   columns preserve prior text; blankness pairing both directions; no `Notes` columns.
   Atomic rename.

## b9 — Export (script only — never an LLM)

1. Run `scripts/export_xlsx.py --audit-dir audit/ --manifest audit/_run/manifest.json
   --mode <mode>` → `audit/code_review.xlsx`.
   - Sheets per the mode table above; `Overview` carries the sheet guide, status legends,
     variable legends, and a **Degraded-confidence warnings** section from the manifest
     `warnings` (CODEMAP preconditions score).
   - Author-facing columns in; every `*_Original` column out; `Potential Issue` computed on
     the Paper Claims sheet only.
2. `lint_registers.py --stage b9`: workbook opens; per-sheet row counts and ID sets match the
   registers; excluded/required columns verified.

## After b9

Return to SKILL.md Phase 4 (report + targeted manual QA follow-up).
