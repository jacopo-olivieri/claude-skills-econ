# Skeleton — planner, code-error stream

Dispatched at b1-code. One subagent. Fill slots only.

| Slot | Filled from |
| --- | --- |
| `{REVIEW_MODE_SENTENCE}` | manifest |
| `{CONTRACT_PATH}` | `audit/_run/contracts/planning.md` |
| `{SCOPE_EXCLUSIONS}` | manifest (or "none") |
| `{KNOWN_CONTEXT}` | manifest (or "none") |
| `{ID_ALLOCATION_START}` | conductor: first free E- number (normally `E-0001`) |
| `{HYGIENE_CHECKLIST}` | the hygiene chunk checklist from `pipeline-code-errors.md`, verbatim |

## Skeleton

```md
## CONTEXT

I am reviewing an academic paper replication package. The paper-code consistency review is
handled separately and may be running in parallel. This pass starts from the source code
itself and checks whether the scripts contain visible errors that could affect
reproducibility, generated outputs, samples, variables, or package execution.

{REVIEW_MODE_SENTENCE}

Previous setup steps are complete: `audit/CODEMAP.md`, `{CONTRACT_PATH}`, and the audit folder
exist.

Out of scope: {SCOPE_EXCLUSIONS}
Known context: {KNOWN_CONTEXT}

## TASK

Create `audit/plans/code_error_review_plan.md`. Read `audit/CODEMAP.md`,
`{CONTRACT_PATH}`, central README/config files, and master scripts/entry points first.
Do not populate registers; do not edit code, data, or paper text.

Start from the source code; ignore paper claims and paper-review findings.

## SIZING RULES (fixed)

- Script inventory: every executable script from CODEMAP minus the exclusions above. Every
  inventory script sits in exactly one chunk.
- Chunks of 4–10 scripts or ≤ ~2,000 total lines, grouped by pipeline stage and language.
- Error ID range per chunk: max(50, 10 × scripts in chunk), globally disjoint, allocated
  upward from {ID_ALLOCATION_START}, plus a 50-ID merge-coordinator range after the last
  chunk range.
- One additional **hygiene chunk** is mandatory. Scope: package-level files (README, data
  availability statements, manifests, environment/config files) plus a package-wide lens on
  data files and logs. Include in the plan a dedicated subsection `## Hygiene Checklist`
  containing exactly the checklist below; the hygiene chunk's Review Focus cell reads
  `hygiene: see Hygiene Checklist section`.
  {HYGIENE_CHECKLIST}

## PLAN STRUCTURE

1. **Summary** — what this code-error review verifies; repeat the review-mode sentence.
2. **Scope Boundaries** — inventory inclusions/exclusions with reasons; deferred items.
3. **Script Inventory** — table: | Script | Language | Pipeline role | ~Lines | Chunk |.
4. **Key Decisions** — chunking logic.
5. **Chunk Allocation Table** —
   | Chunk ID | Script Scope | Likely Pipeline Stage/Outputs | Shard File | Error ID Range | Review Focus |
   Shard files under `audit/_code_errors/`, unique per chunk. Chunk IDs `CE-01`, `CE-02`, …
   Write ID ranges exactly as `E-0100–E-0199`. Directly below the table add:
   `Merge-coordinator range: E-…–E-…`.
6. **Risks & Mitigations**.
7. **Completion Criteria** — every inventory script covered by a shard coverage row or a
   documented blocker; every shard linting.

## CONSTRAINTS

- Use the taxonomy, status vocabulary, and ID conventions from `{CONTRACT_PATH}`
  exactly; do not define new vocab or severity rules.
- Do not restate what workers should look for — the worker prompt carries its own ERROR
  SCOPE; your Review Focus column adds only chunk-specific priorities.
- Do not write worker prompt templates.
- Repo-relative paths throughout.
```
