# Skeleton — second-read recall worker (both streams)

Dispatched at b3b (after the first merge, before the recheck plan), one subagent per flagged
file. Its sole job is a **recall** pass: re-read a file that already produced a confirmed finding
and surface what the first reader missed. This is not the recheck (b4–b6 re-verifies rows that
were *found*, a precision pass); this pass looks for rows that were *missed*. New rows land as
unverified candidates and flow into the recheck. Single fire-and-forget message. Fill slots only.

| Slot | Filled from |
| --- | --- |
| `{REVIEW_MODE_SENTENCE}` | manifest |
| `{SECOND_READ_PLAN_PATH}` | `audit/plans/code_error_second_read_plan.md` or `audit/plans/claims_second_read_plan.md` |
| `{WORKER_ID}` / `{FILE_SCOPE}` / `{SHARD_FILE}` / `{ID_RANGES}` | the b3b allocation table |
| `{STREAM}` | `code-error` or `claims` |
| `{KNOWN_FINDINGS}` | conductor: the IDs and one-line mechanism of every finding the first pass already logged in this file — so the worker does not re-log them |
| `{MANDATE_LENS}` | conductor: `the same broad defect scan the first reader ran` at standard depth; a **distinct** lens (e.g. "focus on data-shape and merge-cardinality assumptions", "focus on units and scaling", "focus on sample and timing") on the second `deep`-depth pass |
| `{PAPER_PATH}` | manifest `paper_audit_path` (claims stream only) |

## Skeleton

```md
## CONTEXT

A first-pass review already flagged a finding in the file below. Findings cluster: a
file careless in one place is often careless elsewhere. Your job is a fresh second read of this
one file to surface what the first reader missed. {REVIEW_MODE_SENTENCE}

You are second-read Worker {WORKER_ID}, {STREAM} stream.

File scope: {FILE_SCOPE}
Shard: `{SHARD_FILE}`
ID range(s): {ID_RANGES}
Read lens for this pass: {MANDATE_LENS}

Already logged by the first reader in this file (do NOT re-log these — find something else):
{KNOWN_FINDINGS}

Read first: `{SECOND_READ_PLAN_PATH}`; `audit/CODEMAP.md`; `audit/audit_readme.md`; then the file
in scope in full, plus any file it directly hands off to or from. Register schema, taxonomy,
status vocabulary, and severity rubric: `audit/audit_readme.md`. Use them exactly.

## MANDATE

Assume at least one more defect exists in this file that the first reader missed, and find it.
Re-read the whole file, not just the neighbourhood of the known finding. Do not stop at the
first thing you notice. Look for the defect classes in `audit/audit_readme.md` that the known
findings above do NOT already cover.

## RULES

- Write ONLY to `{SHARD_FILE}`, using the exact canonical columns of the target register(s) for
  this stream (code stream: the code-error register; claims stream: claims first, then outputs).
- **Every new row you add is unverified.** Code-error rows take status `candidate`. Claims rows
  take status `inconsistent` (a genuine conflict you can evidence) or `unclear` (a suspected
  problem you cannot settle) — never `confirmed` or `mapped`. New output rows take `mapped`,
  `orphan`, `unclear`, or `inconsistent`, never `listed` or `confirmed`. The recheck stage
  verifies everything you add; do not pre-confirm.
- Do NOT re-log the known findings above, do not edit canonical registers, source code, data, or
  paper text, and do not run the pipeline unless the review mode allows a probe within budget.
- Use IDs only from your assigned range; if it runs out, stop and put `BLOCKED: ID range
  exhausted` in your coordinator notes.
- Leave cross-link columns (`Related Error IDs` / `Related Claim IDs`) blank.
- Repo-relative paths everywhere.

## OUTPUT

The shard: the new-row table(s), then a two-part footer per `audit/audit_readme.md` — a coverage
note stating what you re-read and whether you found a further defect (an explicit "no further
defect found" is a valid outcome and must be stated), and coordinator notes (highest-risk new
finding, any blocked check, ID-range overflow).
```
