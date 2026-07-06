# Skeleton — section worker, claims stream

Dispatched at b2-claims, one subagent per allocation-table row, single fire-and-forget
message. Fill slots only.

| Slot | Filled from |
| --- | --- |
| `{REVIEW_MODE_SENTENCE}` | manifest |
| `{PLAN_PATH}` | `audit/plans/claims_review_plan.md` |
| `{WORKER_ID}` / `{PAPER_SECTION}` / `{SHARD_FILE}` / `{CLAIM_ID_RANGE}` / `{OUTPUT_ID_RANGE}` / `{SECTION_PRIORITIES}` | allocation table |
| `{PAPER_PATH}` | manifest `paper_audit_path` |
| `{ARTIFACTS_INSTRUCTION}` | conductor, from CODEMAP's Materials Inventory. Artifacts exist → `Shipped artifacts exist at <paths>. Diff every reported coefficient, sample size, and hardcoded number in your section against the artifact values at reported precision, recording mismatches as transcription or rounding_or_precision claims.` No artifacts → `No shipped artifacts were found; transcription checks are limited to values visible in code, logs, and documentation.` |

## Skeleton

```md
We are preparing a code review of this academic paper and replication package. Use
`{PLAN_PATH}`. {REVIEW_MODE_SENTENCE}

You are Worker {WORKER_ID}.

Scope: {PAPER_SECTION} of `{PAPER_PATH}`
Shard: `{SHARD_FILE}`
ID ranges: {CLAIM_ID_RANGE}, {OUTPUT_ID_RANGE}
Focus on: {SECTION_PRIORITIES}

Read first, in order: the plan; your assigned paper section; `audit/CODEMAP.md` (start with its
Materials Inventory); then only the code and documentation relevant to your section.

Register schemas, status vocabulary, ID conventions, and severity rubric:
`audit/audit_readme.md`. Use them exactly.

Produce candidate rows for the claims and output registers, written ONLY to your shard file:
two tables, claims first then outputs, each with its register's exact canonical columns.

Rules:
- Apply the claim-unit, `Paper Quote`, and `Used in Text` rules from `audit/audit_readme.md`
  exactly.
- {ARTIFACTS_INSTRUCTION}
- Link claims to outputs (`Output IDs` / `Claim IDs`) within your shard; both directions.
- Think carefully about whether the code actually supports each claim before setting
  `Status` — identifying the right script is mapping, not confirmation.
- Apply the **standing self-consistency checks** from `audit/audit_readme.md` where your section
  makes them paper-relevant: when the paper states a shared convention (a sample-window boundary,
  unit/scale, date mask, missing-value sentinel), confirm the code defines it the same way and
  consistently across files (check 2); when a claim depends on a cross-language or cross-script
  hand-off, confirm what one step writes is where the next reads (check 3). A divergence is an
  `inconsistent` claim.
- If a claim issue appears to have a code mechanism, describe the mechanism in
  `Issue Description`, but never assign or reference `E-*` IDs; leave `Related Error IDs`
  blank.
- Use IDs only from your assigned ranges. If a range runs out, stop adding rows and put
  `BLOCKED: ID range exhausted` in your coordinator notes.
- Repo-relative paths everywhere.

Completion criterion — exhaustive: every table, figure, footnote, equation, and quantitative
sentence in your scope has a register row or an explicit skip note with a reason. End the
shard with the two-part footer specified in `audit/audit_readme.md` (coverage note +
coordinator notes); the coverage note must prove the criterion above, and section overlaps
go in the coordinator notes — deduplication is the coordinator's job, not yours.

Parallel-safety: you may read any file, but write only to your shard. Do not edit canonical
registers, code, paper text, plans, or other workers' shards. Do not run the pipeline.
```
