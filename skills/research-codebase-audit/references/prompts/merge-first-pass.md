# Skeleton — first-pass merge (adds rows)

Dispatched at b3-claims / b3-code. One coordinator subagent per stream. This merge **adds**
rows to empty canon; the recheck merge (separate skeleton) mutates existing rows. Fill slots
only.

| Slot | Filled from |
| --- | --- |
| `{REVIEW_MODE_SENTENCE}` | manifest |
| `{PLAN_PATH}` | the stream's review plan |
| `{SHARD_DIR}` | `audit/_work/` (claims) or `audit/_code_errors/` (code) |
| `{REGISTER_FILES}` | claims: claims + output registers; code: code-error register |
| `{STAGING_FILES}` | matching paths under `audit/_staging/` |
| `{MERGE_REPORT}` | `audit/_run/merge_report_claims.json` or `..._code.json` |
| `{BLOCKED_SHARDS}` | conductor: list of shards marked blocked, or "none" |
| `{COVERAGE_KIND}` | claims: `per-section coverage notes reconcile: every part of the paper scope is covered by some shard or explicitly skipped with a reason`; code: `every script in the plan's inventory has a coverage row in some shard footer or a documented blocker` |

## Skeleton

```md
## CONTEXT

I am conducting a codebase review of an academic paper and its replication package. The
first pass ran in parallel worker shards under `{SHARD_DIR}`. This step merges those shards
into coherent canonical registers.

{REVIEW_MODE_SENTENCE}

## TASK

You are the first-pass merge coordinator.

Read: `{PLAN_PATH}`, `audit/CODEMAP.md`, `audit/audit_readme.md`, all shard files in
`{SHARD_DIR}`, and the current canonical registers {REGISTER_FILES}.

Blocked shards (merge without them; document the gap): {BLOCKED_SHARDS}

Write the merged registers to the STAGING paths {STAGING_FILES} — never edit the canonical
files directly. Also write `{MERGE_REPORT}` with EXACTLY this JSON shape (one top-level key
per register filename; the identity shard_rows − dedup_removed == added must hold):

    {
      "<register filename>": {
        "shard_rows": <int>, "dedup_removed": <int>, "added": <int>,
        "conflicts": ["<ID>", ...], "coverage_gaps": ["<gap>", ...],
        "blocked_shards": ["<shard path>", ...]
      }
    }

## WHAT TO DO

1. Merge all shard rows into the staging registers, preserving every worker-assigned ID
   exactly — no renumbering, ever.
2. Deduplicate per the row-lifecycle rule in `audit/audit_readme.md`: only where location AND
   mechanism both match. Dropped duplicates are counted in `dedup_removed`, keeping the row
   whose evidence is strongest.
3. Normalise statuses, types, and severities to the `audit/audit_readme.md` vocabulary. Do
   not invent rows: combining duplicate worker rows (step 2) is the only row surgery allowed
   here — splits belong to the recheck merge.
3b. Resolve every `listed` output row to `mapped`, `orphan`, or `unclear` from shard
   evidence — `listed` must not enter canon.
4. Keep claims↔outputs links bidirectional (C-x lists O-y ⟺ O-y lists C-x). Leave
   `Related Error IDs` / `Related Claim IDs` blank — cross-linking is a later stage.
5. Coverage reconciliation: {COVERAGE_KIND}. Record gaps in the merge report.
6. Do not discard uncertain rows; keep them with their uncertain status and what remains
   unresolved. Mark only concrete problems as issues — ordinary uncertainty is not an issue.
7. Where workers contradict each other, think hard about whether the rows genuinely
   conflict or are complementary evidence about the same mechanism. Preserve real conflicts:
   set the row `unclear` or `inconsistent` (claims) / keep `candidate` (code), and list it
   under `"conflicts"` — the recheck stage picks these up mechanically.

## CONSTRAINTS

- Do not edit the paper, code, data, shard files, or canonical registers.
- Prefer explicit uncertainty over false confidence.
- Repo-relative paths; Markdown tables must stay valid.

## OUTPUT

Staging registers + `{MERGE_REPORT}`. Then report: rows merged per register, duplicates
removed, conflicts preserved, coverage gaps, and the highest-priority issues found.
```
