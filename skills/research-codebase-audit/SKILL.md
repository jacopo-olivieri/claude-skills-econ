---
name: research-codebase-audit
description: Audit a research replication package — paper-code consistency, source-code errors, and package hygiene — producing an author-facing Excel workbook of findings.
disable-model-invocation: true
---

# research-codebase-audit

Static-first audit of a research codebase/replication package. You are the **thin conductor**:
run an interactive intake, then drive a fully autonomous pipeline of clean-context subagents.
Registers are the interface between stages; bundled Python scripts gate every stage boundary;
the run ends at `audit/code_review.xlsx`.

Reference files (all paths relative to this skill's folder):

- `references/registers.md` — schemas, vocabulary, IDs, severity. Single source of truth.
- `references/pipeline-claims.md`, `references/pipeline-code-errors.md`,
  `references/pipeline-finalize.md` — stage-by-stage pipeline instructions and sizing rules.
- `references/prompts/` — fixed prompt skeletons with slot tables.
- `scripts/lint_registers.py`, `scripts/blank_tex_comments.py`, `scripts/export_xlsx.py`.

Invariants you never break:

- **Workers get filled prompts, never skill files.** Inside the audited repo a worker reads only
  its plan, the generated `audit/audit_readme.md`, `audit/CODEMAP.md`, the paper, and the code,
  shipped artifacts, and data in scope.
- **Skeleton text is invariant** — you and the planner subagents fill the designated slots only.
- **Every canonical register mutation** goes write-to-staging (`audit/_staging/`) → lint →
  atomic rename (`mv`), with a pre-stage snapshot of the register under
  `audit/_run/snapshots/<stage-key>/`. Exception: the final b8 promotion copies instead of
  renaming and leaves `_staging/` in place as the frozen b8 state (see pipeline-finalize.md).
- **Lint gate**: after every stage, run `lint_registers.py --stage <lint-stage>` (lint stages
  are stream-qualified: `b0`, `b1-claims`…`b6-claims`, `b1-code`…`b6-code`, `b7`, `b8`, `b9`;
  worker-shard checks add `--shard <path>`). On failure, re-dispatch the producing agent once
  with the lint report appended to its prompt. On second failure, mark that shard/stage
  `blocked` in the manifest and continue everything that does not depend on it. **Merges
  proceed over the non-blocked shards** and document blocked ones in the merge report.
- **After intake the run is unsupervised** — no user questions until the export exists.

## Phase 1 — Intake (interactive)

Converge with the user on the points below, then write the manifest. Ask concisely; propose
defaults and let the user correct.

1. **Materials inventory.** Locate: repo root, paper source, README, master scripts, shipped
   artifacts (e.g. `artifacts/**/*.tex`), existing `audit/` folder (offer resume — see Resume).
   The paper must be machine-readable: LaTeX or Markdown. PDF-only: if `marker` is available,
   convert to Markdown and use the conversion as the paper source; **no `marker` → warn and
   stop** (offer to proceed once the user converts it).
2. **Mode** — branch table:

   | Mode | Pipeline |
   | --- | --- |
   | Full replication audit | claims stream ∥ code-error stream → cross-link → rewrite → export |
   | Code-errors-only | code-error stream → rewrite → export (skip claims, cross-link; see pipeline-finalize skip rules) |
   | WIP review | **Not supported in v1.** Say so, offer code-errors-only or stop. |

3. **Review ladder + off-limits list.** Level 1 = static inspection only (code, docs, existing
   artifacts, read-only data inspection). Level 2 = adds parser/runtime checks, unit tests with
   simulated data, targeted reruns, each under a per-check compute budget (default per
   `references/registers.md`: 15 min). Level 3 = unrestricted. Record the level, the budget,
   and an explicit off-limits list (scripts/data/commands the run must not touch).
4. **Scope exclusions.** Propose exclusions from a quick look at the repo (archives, obviously
   exploratory folders); the user corrects. Record the final exclusion list.
5. **Known context.** Anything the user already knows: fragile areas, known issues, restricted
   data, quirks (e.g. mirror folders that are import-only).
6. **Output preferences and worker model tier** (default: inherit the session model).

Write `audit/_run/manifest.json`:

```json
{
  "mode": "replication | code_errors_only",
  "ladder_level": 1,
  "compute_budget_minutes": 15,
  "off_limits": [],
  "scope_exclusions": [],
  "known_context": "…",
  "output_prefs": "…",
  "worker_model": "inherit",
  "review_mode_sentence": "…",
  "paper_source_path": "…", "paper_sha256": "<sha256 of paper_source_path>",
  "paper_audit_path": "<blanked/converted copy, set at init>",
  "git_head": "… | null",
  "warnings": [],
  "stages": {
    "<stage-key>": {
      "status": "pending|running|done|blocked", "retries": 0,
      "shards": { "<shard path>": { "status": "pending|done|blocked", "retries": 0 } }
    }
  }
}
```

Stage keys are stream-qualified: `b0`, `claims_b1`…`claims_b6`, `code_b1`…`code_b6`, `b7`,
`b8`, `b9` (finalize keys exist only where the mode runs them). `shards` appears on worker
stages only; a worker stage is `done` when every shard is `done` or `blocked` and at least one
is `done`.

`review_mode_sentence` is the single source for the review-mode text every skeleton slot
receives — compose it once from mode + ladder + budget + off-limits.

Completion: manifest written and every field above resolved with the user.

## Phase 2 — Init (boundary B0)

1. Create `audit/` with empty registers per `references/registers.md`, plus
   `audit/_work/`, `audit/_code_errors/`, `audit/_recheck/`, `audit/_code_error_recheck/`,
   `audit/_staging/`, `audit/_run/snapshots/`, and `audit/plans/`.
2. **Generate `audit/audit_readme.md`** per the generation instruction at the top of
   `references/registers.md` (reproduce every normative section). Workers read this file,
   never the skill's own references.
3. If the paper is LaTeX: run `scripts/blank_tex_comments.py` to produce the audit copy —
   comments blanked, line numbers preserved, so only PDF-visible content is audited. Record it
   as `paper_audit_path` (`paper_source_path`/`paper_sha256` keep pointing at the source).
4. Dispatch the **CODEMAP subagent** (`references/prompts/codemap.md`): produces
   `audit/CODEMAP.md` with `S-/D-/B-` ID tables, materials inventory, and a **preconditions
   score** (README present? unique output↔script mapping? documented data sources?). Low
   scores are recorded as degraded-confidence `warnings` in the manifest — they surface in the
   export; they never stop the run.
5. Run `lint_registers.py --stage b0`.

Completion: lint passes; manifest stage `b0 = done`.

## Phase 3 — Conductor loop (autonomous)

Drive the stage DAG for the chosen mode. Stage-by-stage instructions, sizing rules, and which
skeleton each stage uses live in the pipeline files — read the relevant one before dispatching
each stream:

| Stage keys | Lint stages | Instructions |
| --- | --- | --- |
| `claims_b1`–`claims_b3` (plan → section workers → merge) | `b1-claims`–`b3-claims` | `references/pipeline-claims.md` |
| `claims_b4`–`claims_b6` (recheck plan → cluster workers → merge) | `b4-claims`–`b6-claims` | `references/pipeline-claims.md` |
| `code_b1`–`code_b3` (plan → chunk workers incl. hygiene → merge) | `b1-code`–`b3-code` | `references/pipeline-code-errors.md` |
| `code_b4`–`code_b6` (recheck plan → cluster workers → merge) | `b4-code`–`b6-code` | `references/pipeline-code-errors.md` |
| `b7` cross-link | `b7` | `references/pipeline-finalize.md` |
| `b8` author-facing rewrite | `b8` | `references/pipeline-finalize.md` |
| `b9` Excel export (`scripts/export_xlsx.py`, never an LLM) | `b9` | `references/pipeline-finalize.md` |

Mechanics:

- The two streams are independent — run them in parallel. Within a stream, workers of the same
  stage run in parallel (one subagent per worker/cluster, single fire-and-forget message each).
- Update the manifest at every transition; a worker is complete only when **its shard exists AND
  lints** at the stage's boundary.
- Dispatch with the user's `worker_model` if set. Skeletons for judgment-heavy stages (recheck,
  merge conflicts, claims logic) carry their own thinking cues — do not add more.
- Blocked work never stalls the run: merges run over the non-blocked shards (documenting the
  blocked ones), a blocked claims stage does not stop the code stream, and vice versa. Blocked
  stages/shards are reported at the end, not retried in a loop.

Completion: `b9 = done` — `audit/code_review.xlsx` exists and passes the b9 lint.

## Phase 4 — Report and follow-up (interactive again)

Report to the user: row counts per register and status, issue-flagged rows by severity,
blocked/`confirmation_needed` rows, degraded-confidence warnings, and the workbook path.

Offer the documented follow-up: **targeted manual QA** — the user picks specific IDs, you run an
interactive recheck of just those rows (same evidence standards as the recheck stage) and
propose replacement author-facing notes. Do not edit registers in this phase without explicit
user approval.

## Resume

If `audit/_run/manifest.json` exists at intake, offer to resume:

1. Re-hash `paper_source_path` and compare to `paper_sha256`. **If the manuscript changed,
   warn and offer a scoped register-update pass** (re-run only claims workers whose sections
   changed) instead of silently continuing.
2. Resume at the first stage key whose status ≠ `done` (stream order: each stream
   independently, then finalize). Within a worker stage, re-dispatch only workers whose shards
   are missing or failing lint — completed shards are never re-run.
3. Registers are only ever mutated via staging + atomic rename, so a crashed run leaves canon
   consistent; stale staging files can be deleted.
