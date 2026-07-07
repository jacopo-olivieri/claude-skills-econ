# Skeleton — shared-conventions consolidation (claims stream, b3c)

Dispatched at b3c, one subagent, single fire-and-forget message, after the first claims merge
(b3) and before the recheck plan (b4). It reads the merged claims register and emits one small
artifact; it adds no register rows and mutates no canonical file. Fill slots only.

| Slot | Filled from |
| --- | --- |
| `{REVIEW_MODE_SENTENCE}` | manifest |
| `{CLAIMS_REGISTER}` | `audit/claims_register.md` |
| `{CONVENTIONS_ARTIFACT}` | `audit/_run/conventions.md` |

## Skeleton

```md
## CONTEXT

We are auditing an academic paper and its replication package. The first-pass claims merge is
complete: `{CLAIMS_REGISTER}` now records, across its rows, the conventions the package uses in
more than one place. {REVIEW_MODE_SENTENCE}

Your job is to consolidate those conventions into one small list so the code-stream recheck can
grep the codebase for sites that violate each. You produce a **list, not a verdict** — the
verdicts come later from the code side.

## TASK

Read `{CLAIMS_REGISTER}` and `audit/audit_readme.md`. Write `{CONVENTIONS_ARTIFACT}` — a single
Markdown table, one row per stated convention the package uses in **more than one place**:

| Convention | Category | Stated Definition | Sites Already Seen |
| --- | --- | --- | --- |

## RULES

- **Categories are fixed** — a convention belongs to exactly one of the standing-check-2 categories
  in `audit/audit_readme.md`: `fiscal_year_or_sample_window_boundary`, `date_parse_mask`,
  `missing_value_sentinel`, `unit_or_scale_factor`, `path_separator`, `id_or_merge_key`. A
  candidate that fits none of these is not a shared convention — do not invent a category and do
  not list it.
- **Multi-site only.** List a convention only when the register shows it stated or used in **more
  than one place** (two or more rows, or one row that cites two or more sites). A convention that
  appears in a single place is out of scope for this artifact — skip it.
- `Convention`: a short name for the thing being fixed (e.g. "fiscal-year boundary",
  "flood-return-period layer", "household ID key").
- `Stated Definition`: what the paper states the convention to be, with the `C-ID` it came from
  (e.g. "fiscal year begins in July (C-0142)"). Quote the value, not a paraphrase, where the
  register has one.
- `Sites Already Seen`: the files and/or `C-ID` rows already logged for this convention
  (`;`-separated), so the code side knows where the claims stream already looked.
- **Empty is valid.** If no convention is used in more than one place, write the table header with
  no data rows. Do not fabricate rows to fill the table; a package with no multi-site convention
  correctly yields an empty artifact and nothing downstream depends on a non-empty one.

## CONSTRAINTS

- Read-only: do not edit the registers, the paper, the code, or any other file. Write only
  `{CONVENTIONS_ARTIFACT}`.
- Mint no IDs and add no register rows. This step reuses the `C-IDs` already in the register.
- Repo-relative paths everywhere; the Markdown table must stay valid.

## OUTPUT

`{CONVENTIONS_ARTIFACT}` (the table, possibly header-only). Then report: how many conventions were
listed, by category, and any convention you judged single-site and therefore omitted.
```
