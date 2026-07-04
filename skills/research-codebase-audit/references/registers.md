# Registers — single source of truth

This file defines the audit registers: schemas, status/verdict vocabulary, ID conventions,
severity rubric, and row-lifecycle rules. Everything here is **fixed**: workers, planners, and
coordinators may not add statuses, rename columns, or define "equivalent" vocabularies.
`scripts/lint_registers.py` enforces this file mechanically at every stage boundary.

At init the conductor **generates `audit/audit_readme.md` from this file**, reproducing every
normative section (purposes, column meanings, full vocabulary, ID conventions, severity rubric,
three-part structure, shard formats, recheck ledger and vocabulary). Workers read only the
generated `audit_readme.md` inside the audited repo — never skill files. This file is also the
authoritative home for the per-check compute budget and the static-only-evidence lint warning;
prompt skeletons carry pointers, never restatements.

## ID conventions (global, all registers)

- Formats: claims `C-\d{4}`, outputs `O-\d{4}`, code errors `E-\d{4}`; CODEMAP scripts/datasets/
  boundaries `S-\d{4}` / `D-\d{4}` / `B-\d{4}`.
- **All ID ranges are global and non-overlapping across the whole run.** Planners allocate each
  worker a disjoint subrange per ID type (e.g. worker S2 gets `C-0200–C-0299`, `O-0120–O-0149`).
  There are no local or temporary IDs, and no renumbering at merge — the ID a worker assigns is
  the ID the row keeps forever.
- **Overflow rule**: a worker that exhausts its assigned range stops adding rows, records the
  overflow in its coordinator-notes footer, and marks the shard blocked (see the blocked-shard
  marker under Shard format). The conductor re-plans (splits the scope or allocates a fresh
  range). Workers never invent IDs outside their range.
- **Merge-coordinator range**: at planning time each register also gets a small reserved range
  for its merge coordinator (e.g. `C-0900–C-0949`), used *only* to mint IDs for declared row
  splits at recheck merge. Recheck **workers** never mint IDs.
- IDs are never reused, including IDs of rows later demoted to `not_error` or `duplicate_of`.

## Severity rubric (shared by claims and code errors)

Severity is anchored to **author-materiality** — what the finding could do to the paper:

| Severity | Meaning |
| --- | --- |
| 4 | Could change a headline result's sign or significance. |
| 3 | Changes a reported number or invalidates a robustness claim. |
| 2 | Reproducibility failure that does not change results (broken path, missing file, environment drift). |
| 1 | Label, cosmetic, or documentation issue; note-worthy but immaterial. |

Lineage and provenance-gap findings (an output whose producer cannot be traced) default to
severity 1–2 unless there is concrete evidence the result itself is affected.

**Issue-flagging rule** (two register-specific, lintable forms):

- Claims: `Issue Description` non-empty ⟺ `Severity` filled. A row is issue-flagged iff
  `Severity` is non-empty.
- Code errors: `Severity` filled ⟺ `Status ∈ {candidate, confirmed, confirmation_needed,
  blocked}`. `not_error` and `duplicate_of:<ID>` rows carry no Severity.

There is no `Potential Issue` column in the registers; the Excel export adds one to the
`Paper Claims` sheet only (`TRUE` iff `Severity` non-empty).

## Issue Description structure (three-part)

Every issue-flagged description follows: **(1) what the paper says or implies → (2) what the
code/output shows → (3) why it matters** for the claim, table, reproducibility, or
interpretation. Workers write it technically but complete; the dedicated rewrite pass produces
the author-facing version. Do not restate these parts as separate columns.

## Claims register — `audit/claims_register.md`

Purpose: one row per independently checkable paper assertion that rests on code or data, and
whether the code supports it.

| Claim ID | Paper Context | Paper Quote | Used in Text | Claim Type | Claim Text | Code/Data Source | Output IDs | Status | Severity | Issue Description | Related Error IDs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C-0000 | Appendix F > Table F.33 note | "excluding capital-goods suppliers" | TRUE | robustness | Table F.33's `Cap` column excludes capital-goods suppliers. | `do/data_building/expand_transaction_panel.do`; `do/analysis_jl/transact_regress_route.jl` | O-0000 | inconsistent | 4 | The table note says the `Cap` column excludes capital-goods suppliers, but the code filters the opposite sample: the builder sets `sample_excl_cap == 1` when neither party is capital-good, while the table code keeps `sample_excl_cap == 0`. This reverses the intended robustness sample, so the column does not test what the note claims. |  |

Column meanings:

- `Claim ID`: global stable ID from the worker's assigned range.
- `Paper Context`: human-navigation locator — nearest section/subsection/table/figure/equation/
  footnote **plus** a paragraph, sentence, or note cue. Format:
  `Section 2 > Household Data > paragraph beginning "In this paper..."`. Never just "Section 2".
- `Paper Quote`: **verbatim, ctrl-F-able quote from the manuscript** containing the claimed fact —
  the shortest exact string that pins the claim to the text. Required on every claim row; lint
  fails empty quotes. A claim that cannot be quoted from the manuscript is not a claim — do not
  record it.
- `Used in Text`: `TRUE` if the claimed number/object is actually used in the paper's text,
  tables, or figures; `FALSE` if it exists only in code, comments, logs, or unused artifacts.
  `FALSE` rows are recorded for completeness but cannot be issue-flagged above severity 1.
- `Claim Type`: one of `quantitative_result`, `sample_count`, `treatment_definition`,
  `estimation_specification`, `robustness`, `data_construction`, `interpretation`,
  `transcription`, `rounding_or_precision`.
  - `transcription`: a number reported in prose/table differs from the value in a shipped
    artifact (e.g. `artifacts/**/*.tex`). When artifacts exist, every reported coefficient, N,
    and hardcoded number is diffed against artifact values **at reported precision, in the
    first pass**.
  - `rounding_or_precision`: artifact and paper agree but at the wrong precision, or rounding is
    inconsistent across mentions.
- `Claim Text`: the assertion being checked, paraphrased precisely.
- `Code/Data Source`: repo-relative script(s), dataset(s), or documentation supporting or
  contradicting the claim.
- `Output IDs`: related outputs from the output register (plural, `;`-separated). Filled by the
  worker; must resolve within the run.
- `Status`: see vocabulary below.
- `Severity`: 1–4 per the rubric; filled iff issue-flagged.
- `Issue Description`: three-part structure; filled iff issue-flagged.
- `Related Error IDs`: cross-links to code errors. **Blank until the cross-link stage**; only the
  cross-linker fills it. Bidirectional after cross-link: C-x lists E-y ⟺ E-y lists C-x (lint
  enforces at b7).

**Claim unit**: one row per assertion that can be true or false on its own. A sentence bundling
three independently checkable facts gets up to three rows; several sentences restating one fact
get one row.

### Claims status vocabulary

| Status | Meaning |
| --- | --- |
| `confirmed` | Verified with evidence permitted at the run's review-ladder level. At level 1 (static) that means the code/docs/existing artifacts demonstrably support the claim. **Run-boundary rule: if you identified the relevant code but deciding requires running something beyond the ladder level or compute budget, the row is `mapped`, not `confirmed`.** |
| `mapped` | The producing code/data was identified, but the claim could not be verified within the ladder level. |
| `unclear` | Could not be verified from available materials (missing or restricted data/scripts, untraceable lineage). There is no separate `not_code_checkable` status — such rows are `unclear` with the boundary explained. |
| `inconsistent` | The claim conflicts with the code, data construction, or shipped outputs. Always issue-flagged. |
| `confirmation_needed` | Recheck could not decide within the evidence standards; survives to the final register. |
| `blocked` | The check was blocked (restricted data, environment, budget) or deferred by the ladder/off-limits list; blocker documented. Can arise at first pass or recheck. Survives to the final register. |
| `duplicate_of:<ID>` | Same location AND mechanism as claim `<ID>` (format `duplicate_of:C-\d{4}`, same-register target). Tombstone; created only by merge coordinators. |

## Output register — `audit/output_register.md`

Purpose: one row per paper table/figure/generated output, mapped to its producing script.

| Output ID | Paper Object | Paper Context | Paper Location | Output Path/Pattern | Producing Script | Input Dataset(s) | Key Spec/Sample | Claim IDs | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| O-0000 | Table F.33 | Appendix F > Table F.33 | `paper/main.tex:1415-1425`; `tab:route_robustness` | `artifacts/pairroute/rr_tab_*.tex` | `do/analysis_jl/transact_regress_route.jl` | `build/VAT_..._PairRoute.dta` | Route-level robustness: baseline, non-manufacturing, capital-goods exclusion, movers, 2015-only floods. | C-0000 | inconsistent |

Column meanings:

- `Output ID`: global stable ID from the worker's assigned range.
- `Paper Object`: the table, figure, appendix object, or generated output.
- `Paper Context`: as in the claims register.
- `Paper Location`: exact locator — repo-relative `path:line-line` plus LaTeX label where
  available. This column exists only in the output register: table/figure objects have nothing
  to quote, so the locator substitutes for `Paper Quote`.
- `Output Path/Pattern`: output file path or pattern, if visible.
- `Producing Script`: repo-relative script that creates the output.
- `Input Dataset(s)`: datasets consumed, if visible.
- `Key Spec/Sample`: specification, sample restriction, FE structure, or model details that
  define the output.
- `Claim IDs`: related claims (plural, `;`-separated). Bidirectional with the claims register's
  `Output IDs`: C-x lists O-y ⟺ O-y lists C-x. Lint enforces both directions.
- `Status`: see below.

### Output status vocabulary

| Status | Meaning |
| --- | --- |
| `listed` | Recorded but not yet mapped (transient; should not survive to the final register). |
| `mapped` | Producing script or paper object identified; not fully verifiable at the ladder level. |
| `confirmed` | Mapping supported by code, paths, and paper references (run-boundary rule applies). |
| `orphan` | Appears in the paper with no producing script, or in the code with no paper use. |
| `inconsistent` | Object, label, producing code, or specification conflicts with other audit evidence. |
| `unclear` | Could not be mapped from available materials. |
| `duplicate_of:<ID>` | Same object AND producer as output `<ID>` (format `duplicate_of:O-\d{4}`). Tombstone; created only by merge coordinators. |

`listed` is transient: allowed in shards and at the first merge, lint fails it from b8 (rewrite)
onward.

## Code-error register — `audit/code_error_register.md`

Purpose: one row per potential source-code or pipeline error, independent of the paper.

| Error ID | Error Type | Code/Data Source | Code Location | Status | Severity | Error Description | Why It Matters | Related Claim IDs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E-0000 | sample_filter_or_flag_error | `do/data_building/expand_transaction_panel.do`; `do/analysis_jl/transact_regress_route.jl` | `do/data_building/expand_transaction_panel.do:270-280`; `do/analysis_jl/transact_regress_route.jl:210-225` | candidate | 4 | The builder sets `sample_excl_cap == 1` when neither buyer nor seller is capital-good, but the table code uses `sample_excl_cap == 0` for the capital-goods exclusion column. | Reverses the intended robustness sample and affects the downstream table. |  |

Column meanings:

- `Error ID`: global stable ID from the worker's assigned range.
- `Error Type`: from the taxonomy below.
- `Code/Data Source`: relevant script(s), dataset, config, or output contract (repo-relative).
- `Code Location`: `path:line-line` range(s) anchoring the concern.
- `Status`: see below.
- `Severity`: 1–4 per the rubric, governed by the issue-flagging rule: filled iff
  `Status ∈ {candidate, confirmed, confirmation_needed, blocked}`.
- `Error Description`: what appears wrong, following the three-part structure where the error
  touches something the paper states.
- `Why It Matters`: likely consequence for pipeline, output, or paper claim.
- `Related Claim IDs`: cross-links. **Blank until the cross-link stage.** Bidirectional after
  cross-link with the claims register's `Related Error IDs` (lint enforces at b7).

### Error taxonomy

`syntax_or_parse_error` · `missing_input_or_output` · `stale_or_wrong_path` ·
`undefined_variable_or_global` · `merge_key_or_cardinality_error` ·
`sample_filter_or_flag_error` · `treatment_or_event_timing_error` ·
`aggregation_or_unit_error` · `output_label_or_path_mismatch` · `version_or_dependency_error` ·
`randomness_or_seed_error` · `inference_or_se_specification` · `weighting_error` ·
`readme_or_package_mismatch` · `pii_or_disclosure_risk`

The last five deserve definitions (all statically detectable):

- `randomness_or_seed_error`: unset or reset seeds before bootstrap/simulation/multiple
  imputation; unsorted data before seeded sampling (Stata sort stability).
- `inference_or_se_specification`: paper says clustered at X, code clusters at Y; wrong
  robust/HC type; SE specification drift between paper and code.
- `weighting_error`: survey or regression weights used in code differ from what the paper
  states (or weights stated but absent, or vice versa).
- `readme_or_package_mismatch`: README/data-availability statements contradict the package —
  declared inputs never consumed, undocumented inputs required, per-table script mapping wrong
  or missing, file inventory incomplete. Also covers environment-capture gaps: absolute paths,
  unpinned packages, undeclared ado/library dependencies (use the more specific
  `stale_or_wrong_path`/`version_or_dependency_error` when only one script is affected).
- `pii_or_disclosure_risk`: personally identifiable information in data files, code, logs, or
  outputs (names, addresses, national IDs, GPS coordinates, birth dates — J-PAL PII scan logic).

### Code-error status vocabulary

| Status | Meaning |
| --- | --- |
| `candidate` | Possible error, not yet rechecked (transient; recheck resolves every candidate). |
| `confirmed` | Verified at the run's ladder level (run-boundary rule applies: static-unverifiable candidates become `confirmation_needed`, not `confirmed`). |
| `not_error` | Reviewed and judged not an error. Row kept; Severity cleared; description explains why it is not an active error. |
| `duplicate_of:<ID>` | Same location AND mechanism as error `<ID>` (format `duplicate_of:E-\d{4}`). Tombstone; created only by merge coordinators. Severity cleared. |
| `confirmation_needed` | Recheck could not decide within the evidence standards; survives to the final register. |
| `blocked` | Check blocked or deferred (restricted data, environment, ladder/off-limits, budget); blocker documented. Can arise at first pass or recheck. Survives to the final register. |

### Allowed statuses by stage (lint enforces)

| Register | First-pass shards & first merge (b2–b3) | Recheck merge onward (b6+) |
| --- | --- | --- |
| Claims | `confirmed`, `mapped`, `unclear`, `inconsistent`, `blocked` | + `confirmation_needed`, `duplicate_of:<ID>` |
| Outputs | `listed`, `mapped`, `confirmed`, `orphan`, `inconsistent`, `unclear` | + `duplicate_of:<ID>`; `listed` fails from b8 |
| Code errors | `candidate`, `confirmed`, `not_error`, `blocked` | + `confirmation_needed`, `duplicate_of:<ID>`; `candidate` must not survive b6 (recheck resolves every candidate) |

## Row lifecycle: never delete, dedup on location+mechanism

- **Rows are never deleted** from a canonical register. Wrong findings are demoted
  (`not_error`, cleared issue-flag); duplicates become `duplicate_of:<ID>`. Removal destroys
  the audit trail and lets persistent shards resurrect demoted findings.
- **Merge two rows only when location AND mechanism both match** — same script/lines and same
  causal story. Topic overlap ("both about weights") is not a duplicate.
- At the **first merge**, duplicate shard rows are simply not added to canon; the merge report
  accounts for every drop (`shard_rows − dedup_removed == added`). `duplicate_of:<ID>`
  tombstones arise only when a **recheck merge** collapses rows already in canon.
- Recheck merges may split or merge rows only when required to represent the evidence
  faithfully, and must declare every split/merge in the merge summary (lint reconciles counts).
  Split rows take new IDs from the merge-coordinator range.

## Recheck vocabulary

Recheck workers judge existing rows only — **no new IDs at recheck**. Every assigned ID gets
exactly one ledger row.

### Verdicts — claims recheck

| Verdict | Meaning |
| --- | --- |
| `substantiated` | Independent evidence supports an issue on this row. (For sampled `confirmed` rows: an issue was found where none was flagged — escalate.) |
| `substantiated_but_reframe` | An issue is real but the first-pass description misstates the mechanism; rewrite it. |
| `row_note_only` | No material issue, but a note is worth keeping at severity 1. |
| `not_substantiated` | The first-pass issue does not survive independent checking. |
| `confirmation_needed` | Cannot be decided within the evidence standards. |
| `blocked` | Evidence inaccessible at this ladder level/budget; blocker documented. |

### Verdicts — code-error recheck

`confirmed_error` · `not_error` · `confirmation_needed` · `blocked` · `deferred`
(`deferred` = deliberately not pursued under the ladder/off-limits list.)

### Evidence levels (tied to the review ladder)

| Evidence level | Minimum ladder level |
| --- | --- |
| `static_source_verified` | 1 |
| `artifact_verified` (pre-existing artifacts) | 1 |
| `data_inspected_verified` (read-only inspection of shipped data) | 1 |
| `parser_or_runtime_verified` | 2 |
| `synthetic_test_verified` (unit test with simulated data) | 2 |
| `targeted_rerun_verified` | 2 (small reruns) / 3 (anything expensive) |
| `blocked_documented` | any |

Level 2–3 checks carry a per-check compute budget (default 15 minutes) and must prefer the
smallest script/section/query that can decide the row. A recheck ledger that is 100%
`static_source_verified` at ladder level 2–3 draws a lint *warning* (evidence levels available
but unused).

### Verdict → register mapping (applied by the recheck merge, mechanically)

Claims:

| Verdict | Status becomes | Severity | Issue Description |
| --- | --- | --- | --- |
| `substantiated` | `inconsistent` | per rubric (recalibrate) | kept (tighten if evidence sharpened it) |
| `substantiated_but_reframe` | `inconsistent` | per rubric | rewritten to the verified mechanism |
| `row_note_only` | per evidence (`confirmed`/`mapped`) | 1 | trimmed to the note |
| `not_substantiated` | per evidence (`confirmed` if verified sound, else `mapped`/`unclear`) | cleared | cleared |
| `confirmation_needed` | `confirmation_needed` | kept | kept |
| `blocked` | `blocked` | kept | kept, blocker appended |

For a sampled `confirmed` row escalated by verdict `substantiated`, the row had no issue text:
the merge writes `Issue Description` from the ledger's `Proposed Note` (three-part structure)
and sets `Severity` per the rubric.

Code errors:

| Verdict | Status becomes | Severity |
| --- | --- | --- |
| `confirmed_error` | `confirmed` | per rubric (recalibrate) |
| `not_error` | `not_error` | cleared |
| `confirmation_needed` | `confirmation_needed` | kept |
| `blocked` | `blocked` | kept |
| `deferred` | `blocked` (note: deferred under ladder/off-limits) | kept |

## Shard format (worker outputs under `audit/_work/`, `audit/_code_errors/`, `audit/_recheck/`, `audit/_code_error_recheck/`)

- First-pass shards use **exactly the canonical column set** of their target register(s). A
  claims-stream shard under `audit/_work/` contains two tables — claims first, then outputs —
  each with its register's canonical columns; a code-stream shard contains one code-error
  table. Cross-link columns (`Related Error IDs`, `Related Claim IDs`) stay empty until the
  cross-link stage; claims↔outputs links are filled by the worker and must resolve within the
  worker's own shard or assigned ranges.
- Every first-pass shard — both streams — ends with a footer (lint b2 requires it):
  - **Coverage note** — claims shards: a per-section checklist confirming every table, figure,
    footnote, equation, and quantitative sentence in scope has a register row or an explicit
    skip note (with reason). Code shards: a table `| Script | Outcome |` with outcome `clean`,
    `findings: <E-IDs>`, or `blocked: <reason>` for every script in scope.
  - **Coordinator notes** — highest-risk findings, likely duplicates, blocked checks, ID-range
    overflow if any, cross-shard handoffs.
- **Blocked-shard marker**: a shard is blocked iff its coordinator notes contain a line
  starting `BLOCKED:` followed by the reason. This is the mechanical signal the conductor and
  lint read (e.g. on ID-range overflow).
- Recheck shards contain the row-level ledger
  `| ID | Current Status | Current Severity | Evidence Checked | Evidence Level | Verdict | Proposed Register Change | Pipeline/Output Impact | Proposed Note |`
  plus files inspected, commands run, and a cluster summary.

## Rewrite-pass columns

The rewrite pass (pipeline-finalize) renames technical fields to `*_Original` and writes
author-facing versions under the original names:

- Claims: `Issue Description` → `Issue Description Original` + new author-facing
  `Issue Description`.
- Code errors: `Error Description` → `Error Description Original` + new `Error Description`;
  `Why It Matters` → `Why It Matters Original` + new `Why It Matters`.
- **Blankness pairing (both directions)**: original cell empty ⟺ author-facing cell empty.
- No `Notes` or `Notes Original` columns, ever.

The Excel export ships the author-facing columns and excludes every `*_Original` column.
