# Skeleton — planner, claims stream

Dispatched at b1-claims. One subagent. Fill slots only.

| Slot | Filled from |
| --- | --- |
| `{REVIEW_MODE_SENTENCE}` | manifest |
| `{PAPER_PATH}` | manifest `paper_audit_path` |
| `{KNOWN_CONTEXT}` | manifest (or "none") |
| `{ID_ALLOCATION_START}` | conductor: first free C-/O- numbers (normally `C-0001`, `O-0001`) |

## Skeleton

```md
## CONTEXT

I am preparing a code review of an academic paper and its replication package.
{REVIEW_MODE_SENTENCE}

Previous setup steps are complete:
- Paper: `{PAPER_PATH}` (comment-blanked copy; audit only what is PDF-visible).
- Pipeline map: `audit/CODEMAP.md` (includes a Materials Inventory — read it first).
- Audit folder: `audit/` with registers and `audit/audit_readme.md`.

Known context: {KNOWN_CONTEXT}

The goal is to check whether the paper's claims, tables, figures, data descriptions,
treatment definitions, specifications, and robustness checks can be traced to the code, data
documentation, and generated outputs.

## TASK

Create `audit/plans/claims_review_plan.md` dividing the paper into parallel-safe section-worker
assignments. Read the paper, `audit/CODEMAP.md`, and `audit/audit_readme.md` first. Do not populate
registers; do not edit paper or code.

## SIZING RULES (fixed)

- One coherent section or ≤ ~10 paper pages per worker; split longer sections.
- Expected claims per worker: 15–35; split scopes that would exceed this.
- Count expected claims at the claim-unit rule's granularity (`audit/audit_readme.md`),
  including its enumerated-procedure corollary: a procedure whose steps state checkable
  parameters yields one claim per parameter-bearing step, so a scope carrying long enumerated
  procedures (appendix data-construction recipes especially) is sized on its step count, not
  its sentence count. When that count pressures the budget, split the scope across workers —
  the sizing budget must never collapse a procedure's steps into a single expected claim.
- Claim ID range per worker: max(50, 3 × expected claims); output ID range:
  max(30, 3 × expected outputs). Ranges globally disjoint, allocated upward from
  {ID_ALLOCATION_START}. Additionally reserve a 50-ID merge-coordinator range per register,
  after the last worker range.
- Every part of the paper (including appendices, footnotes, and table/figure notes) belongs
  to exactly one worker scope.

## PLAN STRUCTURE

1. **Summary** — what this review verifies; repeat the review-mode sentence.
2. **Scope Boundaries** — in-scope paper parts; exclusions with reasons; deferred items.
3. **Context** — materials found (from CODEMAP's inventory), preconditions score, known
   context.
4. **Key Decisions** — how the paper was split and why; where code scopes overlap.
5. **Worker Allocation Table** —
   | Worker ID | Paper Scope | Likely Code Scope | Shard File | Claim ID Range | Output ID Range | Review Focus |
   Shard files under `audit/_work/`, unique per worker. Review Focus: section-specific
   priorities (treatment definitions, main tables, robustness, event timing, sample
   restrictions, artifact number-diffing where artifacts exist). Write ID ranges exactly as
   `C-0200–C-0299`. Directly below the table add one line per register:
   `Merge-coordinator range: C-…–C-…` and `Merge-coordinator range: O-…–O-…`.
6. **Risks & Mitigations** — restricted data, dynamic output names, conversion artifacts,
   duplicate findings across sections, unclear definitions.
7. **Completion Criteria** — every worker scope reviewed with a coverage note; every shard
   linting; merge reconciles coverage across sections.

## CONSTRAINTS

- Use the status vocabulary and ID conventions from `audit/audit_readme.md` exactly; do not
  define new vocab.
- Workers write only to their own shard; deduplication belongs to the merge coordinator, so
  do NOT instruct workers to dedup against the canonical registers.
- Do not write worker prompt templates — worker prompts are fixed elsewhere; your allocation
  table supplies their slot values.
- Repo-relative paths throughout.
```
