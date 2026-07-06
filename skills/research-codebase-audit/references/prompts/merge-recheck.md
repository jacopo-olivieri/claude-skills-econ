# Skeleton — recheck merge (mutates rows)

Dispatched at b6-claims / b6-code. One coordinator subagent per stream. This merge **mutates**
existing canonical rows per the verdict mapping; it adds rows only for declared splits. Fill
slots only.

| Slot | Filled from |
| --- | --- |
| `{REVIEW_MODE_SENTENCE}` | manifest |
| `{RECHECK_PLAN_PATH}` | the stream's recheck plan |
| `{SHARD_DIR}` | `audit/_recheck/` (claims) or `audit/_code_error_recheck/` (code) |
| `{REGISTER_FILES}` / `{STAGING_FILES}` | as in merge-first-pass |
| `{SUMMARY_FILE}` | `audit/claims_recheck_summary.md` or `audit/code_error_recheck_summary.md` |
| `{COORD_ID_RANGE}` | the plan's `Merge-coordinator range:` line(s) — claims stream passes both the C- and O- ranges, code stream the E- range |
| `{BLOCKED_SHARDS}` | conductor: blocked cluster shards, or "none" |

## Skeleton

```md
## CONTEXT

The first-pass findings in {REGISTER_FILES} have been rechecked in cluster-level ledger
shards under `{SHARD_DIR}`. This step applies the second-pass evidence to the canonical
registers.

{REVIEW_MODE_SENTENCE}

## TASK

You are the recheck merge coordinator.

Read: `{RECHECK_PLAN_PATH}`, `audit/audit_readme.md`, all shards in `{SHARD_DIR}`, and the
canonical registers {REGISTER_FILES}.

Blocked cluster shards (noted in the summary; their rows keep first-pass state EXCEPT
`candidate` code-error rows, which become `blocked` with the note "recheck cluster shard
blocked" — no `candidate` may survive this merge): {BLOCKED_SHARDS}

Write updated registers to the STAGING paths {STAGING_FILES}, and a reconciliation summary
to `{SUMMARY_FILE}`.

## WHAT TO DO

1. Check every ID in the recheck plan's inventory appears in exactly one cluster ledger;
   list any missing ones in the summary.
2. Apply each verdict with the **verdict → register mapping table** in
   `audit/audit_readme.md` — mechanically: status, severity, and description columns change
   exactly as the table says, including writing escalated issues from the ledger's
   `Proposed Note`. Where cluster evidence sharpened a mechanism, tighten the description
   (three-part structure). When a verdict sets a claim row to `blocked`, populate its
   `Blocked Check` column from the ledger (what stayed checkable from visible material and the
   result) — it is required non-empty on every `blocked` claim.
3. Follow the row-lifecycle rules in `audit/audit_readme.md`: never delete; demotions follow
   the mapping; cross-cluster duplicates become tombstones; splits/merges only when required
   to represent the evidence faithfully, each declared in the summary, with split rows
   taking fresh IDs from {COORD_ID_RANGE} — no other new IDs.
4. Apply ledger-proposed corrections to evidence columns (`Used in Text`, `Code/Data
   Source`, `Code Location`) from `Proposed Register Change`; never change IDs, `Paper
   Quote`, or cross-link columns.
5. Keep rows untouched when their IDs were not in the recheck inventory.
6. Resolve conflicting verdicts on the same ID conservatively (the weaker claim about the
   evidence wins: `confirmation_needed` over `confirmed`); think hard about each such
   conflict and record the reasoning in the summary.

## CONSTRAINTS

- Do not edit code, data, paper text, shard files, or the canonical files directly.
- Row counts must equal the pre-merge registers except for declared splits/merges.
- Repo-relative paths; Markdown tables stay valid.

## OUTPUT

Staging registers + `{SUMMARY_FILE}` reporting: rows updated, kept as substantive, demoted,
still needing confirmation, blocked, splits/merges declared, and rows not reconciled and why.
The summary MUST contain the exact machine-readable lines `Splits declared: <n>` and
`Merges declared: <n>` (0 when none) — the boundary lint reconciles row counts against them.
```
