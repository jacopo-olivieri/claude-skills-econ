# Skeleton — chunk worker, code-error stream

Dispatched at b2-code, one subagent per chunk (the hygiene chunk uses this same skeleton with
its checklist in `{CHUNK_PRIORITIES}`). Single fire-and-forget message. Fill slots only.

| Slot | Filled from |
| --- | --- |
| `{REVIEW_MODE_SENTENCE}` | manifest |
| `{PLAN_PATH}` | `audit/plans/code_error_review_plan.md` |
| `{CHUNK_ID}` / `{SCRIPT_SCOPE}` / `{SHARD_FILE}` / `{ERROR_ID_RANGE}` / `{CHUNK_PRIORITIES}` | allocation table |

## Skeleton

```md
Review the source-code error chunk assigned below, following `{PLAN_PATH}`.
{REVIEW_MODE_SENTENCE}

You are Worker {CHUNK_ID}.

Script scope: {SCRIPT_SCOPE}
Shard: `{SHARD_FILE}`
Error ID range: {ERROR_ID_RANGE}
Chunk-specific priorities: {CHUNK_PRIORITIES}

Read first, in order: the plan; `audit/CODEMAP.md` (start with its Materials Inventory);
`audit/audit_readme.md`; then all scripts in your scope and any central docs/config the plan
names for this chunk.

Register schema, error taxonomy, status vocabulary, and severity rubric:
`audit/audit_readme.md`. Use them exactly.

## ERROR SCOPE

Look for visible source-level or pipeline-contract errors, including:
- syntax or parse errors
- missing inputs or outputs
- stale or wrong paths
- undefined variables, globals, imports, commands, or packages
- wrong filters, reversed logic, or impossible conditions
- merge-key or cardinality problems
- treatment, timing, or sample-definition mistakes
- aggregation or unit mistakes
- output path, label, or file-format mismatches
- dependency, version, or manifest drift
- stale handoffs between scripts
- unset or reset random seeds before bootstrap/simulation/imputation; unsorted data before
  seeded sampling (Stata sort stability)
- standard-error specification drift: clustering level, robust/HC type
- survey or regression weights used differently than documented
- README/package mismatches and PII exposure (record as `readme_or_package_mismatch` /
  `pii_or_disclosure_risk`)

Also run the three **standing self-consistency checks** defined in `audit/audit_readme.md`
("the package asserts X; confirm X"), applied to your scope:
- (1) each documented install/setup command in scope parses to dependencies, paths, and versions
  satisfiable from the package (static only — you do not execute it);
- (2) every shared convention your scope defines (sample-window boundary, date-parse mask,
  missing-value sentinel, unit/scale factor, path separator, ID/merge key) agrees with the same
  convention wherever else it is defined;
- (3) every cross-language or cross-script hand-off your scope touches connects — what one step
  writes is exactly where the next reads (path, name, shape).

Exclude:
- code style comments
- broad refactoring suggestions
- performance tuning
- subjective modelling criticism
- full numerical replication unless the review mode explicitly allows it

## RULES

- Write findings ONLY to `{SHARD_FILE}`: one table with the code-error register's exact
  canonical columns. Do not edit canonical registers, source code, data, paper text, or
  generated outputs. Do not run the pipeline or execute repository scripts.
- Use IDs only from your assigned range; if it runs out, stop adding rows and put
  `BLOCKED: ID range exhausted` in your coordinator notes.
- Leave `Related Claim IDs` blank; never consult the claim register to judge whether a
  finding matters.
- Repo-relative paths everywhere.

Completion criterion — exhaustive: every script in your scope appears in the coverage table.
End the shard with the two-part footer specified in `audit/audit_readme.md` (coverage table
with one row per script in scope + coordinator notes).
```
