# Skeleton — cross-linker

Dispatched at b7 (full replication mode only). One subagent. Fill slots only.

| Slot | Filled from |
| --- | --- |
| `{STAGING_CLAIMS}` / `{STAGING_ERRORS}` | staging copies under `audit/_staging/` (conductor copies canon there first) |

## Skeleton

```md
## CONTEXT

Two independent reviews of an academic paper replication package are complete and rechecked:

1. paper-code consistency: `audit/claims_register.md`, `audit/output_register.md`,
   `audit/claims_recheck_summary.md` (if present);
2. source-code errors: `audit/code_error_register.md`,
   `audit/code_error_recheck_summary.md` (if present).

This step cross-links the final registers where direct relationships exist. It is a linking
step, not a new audit pass.

## TASK

Edit ONLY the link fields, in the staging copies:
- `Related Error IDs` in `{STAGING_CLAIMS}`
- `Related Claim IDs` in `{STAGING_ERRORS}`

Create `audit/register_cross_link_summary.md`.

Read the registers and summaries above plus `audit/audit_readme.md`; inspect cited paper,
code, output, or artifact locations only when needed to decide whether a link is real.

## WHAT TO DO

1. Fill `Related Error IDs` on a claim only when a code error directly explains, causes, or
   materially affects that claim issue; fill `Related Claim IDs` on an error only when the
   error directly affects one or more claims.
2. **Matching rule**: match by script path, line range, output path, table/figure object,
   variable names, sample restrictions, and described mechanism — never by loose keyword
   overlap alone.
3. Every link is bidirectional: if C-x lists E-y, E-y lists C-x.
4. Leave link fields blank when the relationship is indirect, speculative, or merely
   thematic. **Do not treat an unlinked row as a problem by default** — most code errors
   have no related claim and most claim issues no code error; do not list rows merely
   because they are unlinked.
5. The summary lists the links added, grouped by ID, with brief notes only for non-obvious
   links.

## CONSTRAINTS

- Do not create, delete, or reorder rows. Do not change statuses, severities, descriptions,
  paths, locations, claim text, or output mappings — every non-link column must remain
  byte-identical.
- Preserve stable IDs; keep Markdown tables valid.

## OUTPUT

Updated link fields in the two staging files + `audit/register_cross_link_summary.md`, then
report: claims linked, errors linked, links added by ID.
```
