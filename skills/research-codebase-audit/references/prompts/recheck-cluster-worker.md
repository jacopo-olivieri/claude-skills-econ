# Skeleton — recheck cluster worker (both streams)

Dispatched at b5-claims / b5-code, one subagent per cluster, single fire-and-forget message.
This authors the recheck prompt the source methodology left as an empty heading. Fill slots
only.

| Slot | Filled from |
| --- | --- |
| `{REVIEW_MODE_SENTENCE}` | manifest |
| `{RECHECK_PLAN_PATH}` | `audit/plans/claims_recheck_plan.md` or `audit/plans/code_error_recheck_plan.md` |
| `{CLUSTER_ID}` / `{CLUSTER_NAME}` / `{ASSIGNED_IDS}` / `{SHARD_FILE}` | cluster table |
| `{REGISTER_FILES}` | claims stream: `audit/claims_register.md`, `audit/output_register.md`; code stream: `audit/code_error_register.md` |
| `{STREAM}` | `claims` or `code-error` |
| `{COMPUTE_BUDGET}` | manifest `compute_budget_minutes` |
| `{PAPER_PATH}` | manifest `paper_audit_path` (claims stream only; substituted inside `{STREAM_CHECKS}`) |
| `{STREAM_CHECKS}` | claims stream: the two-step preliminary check below, with `{PAPER_PATH}` substituted; code stream: `None.` |

Claims-stream text for `{STREAM_CHECKS}`:

> Before any code inspection, for each assigned ID: (a) search `{PAPER_PATH}` for the row's
> verbatim `Paper Quote` — if it does not appear, the claim does not exist in the manuscript:
> verdict `not_substantiated`, evidence `static_source_verified`, note "quote not found in
> manuscript"; (b) check `Used in Text` is correct — an issue about a number the text never
> uses cannot keep severity above 1.

## Skeleton

```md
## CONTEXT

I am running a cluster-level second-pass review of first-pass {STREAM} audit findings. This
is a review of the review: a first-pass finding survives only if independently checked
evidence supports it.

{REVIEW_MODE_SENTENCE}

Use: `{RECHECK_PLAN_PATH}`, `audit/CODEMAP.md`, `audit/audit_readme.md`, {REGISTER_FILES}.

## ASSIGNMENT

Cluster: {CLUSTER_ID} — {CLUSTER_NAME}
Assigned IDs: {ASSIGNED_IDS}
Shard: `{SHARD_FILE}`

## TASK

Recheck ONLY the assigned IDs. Preliminary stream checks: {STREAM_CHECKS}

For each assigned ID:
1. read the current row in the register — including its own `Issue Description` and, if present,
   its `Blocked Check`;
2. inspect only directly relevant source files, outputs, artifacts, logs, or documentation;
3. start with static inspection;
4. if static inspection cannot decide and the review mode allows it, run the SMALLEST
   parser/runtime check, synthetic test with simulated data, artifact or data inspection, or
   targeted rerun that can decide the row — at most {COMPUTE_BUDGET} minutes per check;
5. if the row cannot be decided, document the blocker precisely.

**Own-evidence adjudication (do this before choosing a verdict).** If the row's own
`Issue Description` or `Blocked Check` already records a paper-vs-code discrepancy — a recomputed
number that differs from the paper's, a shipped filename/header/shape/metadata value that
disagrees with what the paper states, or any "paper says X → code/output shows Y" mismatch — you
may **not** return `confirmed` (a substantiating clean verdict) or `blocked` unless you write a
one-line justification in `Proposed Note` naming the escalation rule (registers.md blocked-row
escalation / cheap-check caution default) and stating why it does not apply here. Absent that
justification, an unexplained numerical disagreement defaults to `inconsistent`; "probably
rounding" is not a clearance (see the caution default in `audit/audit_readme.md`).

**Blocked-visible rule (claims stream).** Before returning `blocked` on a claims row, run the
visible-material check from `audit/audit_readme.md` — filenames, README metadata, column headers,
file shapes, and shipped artifacts. If any visible material contradicts the claim, the row is not
blocked: return a substantiating verdict (`substantiated` → `inconsistent`, or
`confirmation_needed` when only absent data would confirm it), never `blocked`.

**Budget escalation.** When a check approaches {COMPUTE_BUDGET} minutes without deciding, stop and
escalate the unresolved row to `confirmation_needed` or `blocked` (blocker documented) rather than
running over budget.

**Evidence discipline.** `Evidence Checked` must cite exact anchors: a verbatim paper quote, a
repo-relative file path + line range, an artifact path/cell/value, a data header or shape, or a
command and its result. "Checked the source code" (or any anchor-free paraphrase) is not
acceptable and is treated as no evidence.

Use the {STREAM} verdict vocabulary and the evidence levels from `audit/audit_readme.md`
exactly. Think hard before each verdict; weigh the evidence for and against the first-pass
finding separately. Prefer `confirmation_needed` or `blocked` over overstating weak evidence.
For sampled `confirmed` rows, actively look for what the first pass may have waved through.

Do not perform a new broad audit, search for unrelated errors, or revisit files not needed to
decide the assigned rows. Do not mint IDs.

## CONSTRAINTS

- Write only to `{SHARD_FILE}`. Do not edit canonical registers, code, data, or paper text.
- Every assigned ID appears exactly once in the ledger.
- Repo-relative paths everywhere.

## OUTPUT

Write the shard with:
1. Cluster header
2. Files inspected
3. Commands run, if any
4. Row-level ledger:
   | ID | Current Status | Current Severity | Evidence Checked | Evidence Level | Verdict | Proposed Register Change | Pipeline/Output Impact | Proposed Note |
   `Proposed Note` follows the three-part structure (paper says → code shows → why it
   matters) whenever the verdict keeps or creates an issue.
5. Cluster summary: findings to keep / demote / needing confirmation / blocked, and
   consequences the cross-linking stage should know about.
```
