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
   `audit/register_cross_link_summary.md` — including a `## Status conflicts` section for
   every link pairing a `confirmed` claim with a `confirmed` code error, a
   `## Escalated mapped claims` section for every link pairing a `confirmed` code error with a
   `mapped` claim it contradicts, and a `## Severity divergences` section for every link whose
   two rows carry filled, differing severities. Before dispatch, compute the
   confirmed-claim↔confirmed-error code-location overlaps and pass the pair list in the
   dispatch as the floor of the worker's step-2 overlap enumeration; the worker adjudicates
   every overlap candidate individually, and no sibling's judgment call clears another row
   citing the same lines. Obtain the list by running `lint_registers.py --stage b7` right
   after the step-1 snapshot and reading its `overlap-conflict` WARNING lines — at that
   point the cross-link summary does not exist yet, so the stage prints the warnings and
   then FAILS on the missing summary; that pre-dispatch failure is expected, and only the
   WARNING lines are consumed. The floor is ranged-only (a bare-file citation never appears
   in it); whole-file overlap coverage is the worker's own addition per its step-2 rule.
3. `lint_registers.py --stage b7`: non-link columns byte-identical to snapshot; every link
   resolves both ways (C-x lists E-y ⟺ E-y lists C-x); summary exists; every
   confirmed-claim↔confirmed-error link is listed under `## Status conflicts`; every
   mapped-claim↔confirmed-error contradiction is listed under `## Escalated mapped claims`;
   every divergent-severity link is listed under `## Severity divergences`. Atomic rename.
4. **Status-conflict resolution** (only when the summary lists conflicts): dispatch one
   recheck-cluster-worker over the conflicted claim rows, with the linked error rows named as
   evidence to check. Apply the standard verdict→register mapping (registers.md) to the
   claims register mechanically. Whenever the recheck chooses between `inconsistent` and
   `confirmation_needed`, apply the visibility test in `references/registers.md`. If a verdict
   leaves the claim `confirmed` (the error does
   not actually contradict it), the link itself was wrong: remove it from both rows and note
   the removal in the summary. No confirmed-claim↔confirmed-error link may survive into b8
   (lint b8 enforces).
5. **Escalated-mapped-claim second look** (only when the summary lists escalated mapped
   claims; may share the step-4 dispatch): the recheck revisits each `mapped` claim with the
   linked error named as evidence and returns a verdict; the conductor applies the
   verdict→register mapping mechanically. The outcome is open — the claim may become
   `inconsistent` (the error settles it) or legitimately stay `mapped` (the error does not
   settle it); an escalation to `inconsistent` must pass the visibility test (step 4).
   Unlike a status conflict, a `mapped`-and-linked pair may survive to b8: b8
   requires only that the second look happened (a recheck ledger entry for the claim), not a
   particular status. Record the second look in the summary line.
6. **Severity-divergence resolution** (only when the summary lists divergences; may share
   the step-4 dispatch): the recheck revisits each listed pair and returns a verdict; the
   conductor then either aligns the two severities (verdict→register mapping, mechanically
   applied) or appends a one-line justification for the gap — taken from the ledger's
   `Proposed Note` — to the pair's line in the summary. The recheck worker writes only its
   shard, never the summary. Where the verdict also moves a status, the
   `inconsistent`/`confirmation_needed` choice follows the visibility test (step 4).
   Legitimate gaps exist (a claim row may assert something
   narrower than the error breaks) but are never left silent. Pairs still divergent at b8
   must remain listed in the section (lint b8 enforces listing; the justification is a
   prose obligation on the conductor).
7. Whenever step 4, 5, or 6 changed any register row, refresh the b7 snapshot and re-run
   the b7 lint before moving on (otherwise post-run `--stage b7` replay fails on the
   changed rows).

## b8 — Author-facing rewrite

1. Snapshot to `audit/_run/snapshots/b8/`.
2. Dispatch one subagent with `prompts/rewriter.md` (register paths per mode). This is the
   dedicated clarity pass: it renames technical fields to `*_Original` and writes author-facing
   versions, armed with the five contrastive gold examples and the jargon ban carried verbatim
   in the skeleton.
3. `lint_registers.py --stage b8`: counts/IDs/statuses/paths byte-identical; `*_Original`
   columns preserve prior text; blankness pairing both directions; no `Notes` columns; any
   linked pair with differing severities listed under `## Severity divergences`.
4. **Promote by copy, not move**: copy the staging registers over canon — each register
   written via temp file + atomic rename on the canon side, so a crash mid-promotion cannot
   leave canon half-updated — and leave the copies in `_staging/` untouched as
   the frozen b8 boundary state, so `lint_registers.py --stage b8` stays replayable after
   the run. Add one line to `audit_readme.md`: `_staging/` holds the frozen b8 registers,
   superseded by the root registers.

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
