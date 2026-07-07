# Scorecard — 2026-07-07 adjudication & recall refactor (branch `feat/rca-adjudication-recall-v2`)

Implements `2026-07-06-003-refactor-rca-adjudication-and-recall-plan.md` (units
U1–U8 + ride-alongs). This scorecard records the **automated** gate that ran in
the implementation session. The **end-to-end LLM fixture re-score** — the plan's
true merge gate — has **not** been run yet and is REQUIRED before this branch
merges to `main` (see "Remaining merge gate" below).

## Automated gate (committed harness) — GREEN

| Check | Result |
| --- | --- |
| `pytest scripts/tests/` | **58 passed, 0 failed, 0 xfail** |
| U1 advisory-adjudication contract test | **PASS** (was the pinned strict-xfail; now green) |
| Scorer self-tests (P-14 dual-accept MISS/HIT, D-01 decoy → RED, SC-01) | **PASS** |
| `export_xlsx` formula-injection + manifest-robustness tests (U6) | **PASS** |
| U8 negative/positive pairs (b4 inventory, b3b `--shard`, evidence ladder, b9 parity) | **PASS** (28 pairs) |
| `blank_tex_comments` digit-env + parent-dir tests | **PASS** |
| `lint_registers.py --help` (all stages incl. `b3b-*`, `--shard`) | **OK** — no import/syntax error |

Run command (from the skill folder):
`uv run --no-project --with pytest --with openpyxl -- pytest scripts/tests/`
(plain `python -m pytest scripts/tests/` when pytest+openpyxl are on the interpreter).

## What the automated gate does and does not cover

The harness is the repo's first committed test suite. It exercises the three
**scripts** (`lint_registers.py`, `export_xlsx.py`, `blank_tex_comments.py`) and
the new `score_fixture.py` against **synthetic** registers/plans/ledgers/workbooks
built by `scripts/tests/regbuild.py` (whose column constants are imported from
`lint_registers.py`, so fixtures cannot drift from the schema). This proves the
mechanical checks fire correctly.

It does **not** exercise the prose/skeleton behavior changes end-to-end — U1's
recheck-worker adjudication checklist, U2's b3c consolidation + b4 grep handoff,
U4's visibility test and KTD-7 cross-link exception, U6's untrusted-content and
secret rules, U7's depth-knob behavior. Those are worker-behavior changes that
only a full audit run of the fixture package validates. There are **no committed
fixture run artifacts** in `fixture/` (only `planted/`, `expected_findings.json`,
and prior scorecards), so a mechanical per-boundary `b0…b9` lint of a completed
run cannot be produced from the repo alone — it requires running the skill.

## Remaining merge gate — end-to-end LLM fixture re-score (PENDING)

Per the skill convention (a full fixture re-run after any skeleton / pipeline /
`registers.md` / script edit) and the plan's execution posture ("run the fixture
re-score before merging"), the branch must be re-scored end-to-end before merge:

1. Run the `research-codebase-audit` skill as conductor against
   `fixture/planted/` into a fresh out-of-repo run dir (prior runs used
   `~/scratch/rca-fixture-rescore/pkg/audit/`).
2. Lint every stage boundary `b0…b9` (including `--stage b3b-<stream> --shard`
   for the new shard mode, and confirming `--stage b8` passes with `_staging/`
   populated — the b8 staging replay the v1 scorecard once caught failing).
3. Score with the new automated scorer:
   `python scripts/score_fixture.py --audit-dir <run>/audit` → expect GATE GREEN
   (14/14 must-find, decoy D-01 absent, P-13 `inconsistent`, P-14 via a dual-accept
   branch, all confirmed-examples clean).

The previous completed end-to-end run (2026-07-06, **GREEN 14/14**) predates this
refactor and no longer reflects the shipped skeletons; it is retained only as the
last-known-good baseline.

## Prior runs (archived)
- 2026-07-06 rca-improvements (end-to-end, 14/14 GREEN) — [`score-2026-07-06-rca-improvements.md`](score-2026-07-06-rca-improvements.md)
- 2026-07-05 v2 (P-01..P-10) — [`score-2026-07-05-v2.md`](score-2026-07-05-v2.md)
- 2026-07-05 v1 — [`score-2026-07-05-v1.md`](score-2026-07-05-v1.md)
