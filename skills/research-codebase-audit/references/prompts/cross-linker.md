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
2. **Mandatory sweep**: for every code error with status `confirmed` or
   `confirmation_needed`, ask "which claim rows assert the thing this error breaks?" and
   link every such pair — including claims whose status is `confirmed` or `mapped`. Never
   skip a link because the claim row is unflagged. **Direct assertion only**: link the
   claim rows that assert the broken thing itself; claims about downstream results
   (significance, magnitudes, R²) that merely depend on the broken quantity are covered
   via the directly-asserting claim and are NOT linked. When you deliberately leave such a
   dependent claim unlinked, cite this rule in the summary rather than stating that no
   error affects it.
3. **Matching rule**: match by script path, line range, output path, table/figure object,
   variable names, sample restrictions, and described mechanism — never by loose keyword
   overlap alone.
4. Every link is bidirectional: if C-x lists E-y, E-y lists C-x.
5. Leave link fields blank when the relationship is indirect, speculative, or merely
   thematic. **Do not treat an unlinked row as a problem by default** — most code errors
   have no related claim and most claim issues no code error; do not list rows merely
   because they are unlinked.
6. **Status conflicts**: every link that pairs a `confirmed` code error with a claim whose
   status is `confirmed` is a status conflict — the registers currently assert both that
   the claim holds and that a verified error breaks it. List each such pair under a
   `## Status conflicts` section of the summary, one line per pair
   (`C-xxxx <-> E-xxxx — one-line reason`). Do NOT change any status yourself; the
   conductor resolves listed conflicts with a targeted recheck. Omit the section if there
   are none.
7. **Escalated mapped claims**: every link that pairs a `confirmed` code error with a claim
   whose status is `mapped`, where the error contradicts what the claim asserts, is an
   escalated mapped claim — the error suggests the located-but-unverified claim is actually
   false. List each such pair under its **own** `## Escalated mapped claims` section (never
   under `## Status conflicts`), one line per pair
   (`C-xxxx (mapped) <-> E-xxxx — one-line reason the error contradicts the claim`). Do NOT
   change any status yourself; the conductor gives each a second-look recheck whose outcome is
   open (the claim may end `inconsistent` or legitimately stay `mapped`). Omit the section if
   there are none.
8. **Severity divergences**: every link whose two rows carry filled, differing severities
   is a severity divergence. List each pair under a `## Severity divergences` section of
   the summary, one line per pair
   (`C-xxxx (sev a) <-> E-xxxx (sev b) — one-line note on the apparent reason`). Do NOT
   change any severity yourself; the conductor resolves each listed pair (align or
   justify). Omit the section if there are none.
9. The summary lists the links added, grouped by ID, with brief notes only for non-obvious
   links.

## CONSTRAINTS

- Do not create, delete, or reorder rows. Do not change statuses, severities, descriptions,
  paths, locations, claim text, or output mappings — every non-link column must remain
  byte-identical.
- Preserve stable IDs; keep Markdown tables valid.

## OUTPUT

Updated link fields in the two staging files + `audit/register_cross_link_summary.md`, then
report: claims linked, errors linked, links added by ID, status conflicts (if any), escalated
mapped claims (if any), severity divergences (if any).
```
