# Fixture re-score — 2026-07-06 (RCA recall/precision improvements)

Scored against `expected_findings.json` (planted fixture, 14 must_find P-01..P-14
+ 1 decoy D-01), adversarial matching **by mechanism, not ID or wording**, severity
gate per each item's `min_severity`. This is the deferred fixture re-score for the
8-unit improvement plan on branch `feat/rca-recall-precision` (c5a7c89..638227d),
and also serves as the deferred validation for the residuals batch committed as
58128ea.

Registers scored (blind run's final registers, authoritative):
`/Users/jacopoolivieri/scratch/rca-fixture-rescore/pkg/audit/{claims_register.md,
code_error_register.md, output_register.md, register_cross_link_summary.md}`.
The audit uses C-/E-/O- IDs that do NOT match the key's P-/D- IDs; matched by mechanism.

## Headline

| Metric | Result |
| --- | --- |
| **Recall (must_find)** | **14 / 14** |
| **Precision (decoy D-01)** | **PASS** — `placebo`/`fig_placebo` appears nowhere in the audit directory (registers, worker files, plans — zero mentions) |
| **Expected confirmed examples** | **PASS** — both clean |
| **Status conflict SC-01** | **PASS (vacuous)** — P-11 shock-definition claim marked `inconsistent`, so no confirmed↔confirmed pair arises; rule passes on its own terms |
| **GATE VERDICT** | **GREEN** |

## Per-item recall table (P-01..P-14)

| Key ID | Mechanism (short) | min_sev | Matching audit row(s) | Type | Status | Sev awarded | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P-01 | Prose 0.083 vs artifact −0.038 (digit-level transcription) | 3 | C-0001 (also C-0003) | transcription/quantitative_result | inconsistent | 4 | **HIT** |
| P-02 | Village-level clustering claimed; code clusters on household | 3 | E-0004 (+E-0172 bootstrap), C-0024 | inference_or_se_specification / estimation_specification | confirmed / inconsistent | 3 | **HIT** |
| P-03 | Weighted claim, unweighted regressions (svy_weight unused) | 3 | E-0005, C-0023 | weighting_error / estimation_specification | confirmed / inconsistent | 3 | **HIT** |
| P-04 | Bootstrap 200 reps, no `set seed` (and no stable sort) | 2 | E-0006 | randomness_or_seed_error | confirmed | 2 | **HIT** |
| P-05 | `keep if waves < 2` inverts the ≥2-wave exclusion rule | 4 | E-0001, C-0011 (+C-0012, C-0201) | sample_filter_or_flag_error / sample_count | confirmed / inconsistent | 4 | **HIT** |
| P-06 | make_figures.py reads phantom `output/panel_v2.csv` | 2 | E-0007, C-0025 | stale_or_wrong_path / data_construction | confirmed / inconsistent | 2 | **HIT** |
| P-07 | `$controls` defined only in a commented line; runs w/o controls | 3 | E-0003, C-0008 (+C-0022) | undefined_variable_or_global / estimation_specification | confirmed / inconsistent | 3 | **HIT** |
| P-08 | Income ÷100 vs documented "thousands" (factor-of-10 unit error) | 3 | E-0002 (+E-0192 axis), C-0010 | aggregation_or_unit_error / data_construction | confirmed / inconsistent | 3 (E-0002); claim C-0010 at 2 | **HIT** |
| P-09 | README declares absent, unread `rainfall_stations.csv` | 1 | E-0051 | readme_or_package_mismatch | confirmed | 2 | **HIT** |
| P-10 | `head_name` + GPS coordinates in shipped "public" data | 2 | E-0055 | pii_or_disclosure_risk | confirmed | 3 | **HIT** |
| P-11 | Shock baseline is 2-wave in-sample mean, not 1991–2020 normal | 2 | C-0021 (reference-period facet); C-0202/E-0151 (aggregation facet) | treatment_definition / aggregation_or_unit_error | inconsistent / confirmed | 2 | **HIT** |
| P-12 | SECOND, reversed-legend error in make_figures.py | 1 | E-0008, C-0261 | output_label_or_path_mismatch / data_construction | confirmed / inconsistent | 1 (E-0008); claim C-0261 at 2 | **HIT** |
| P-13 | 725/2,416 = 30% not the stated 25% (arithmetic recompute) | 2 | C-0015 | sample_count | inconsistent | 3 | **HIT** |
| P-14 | one-in-ten (paper) vs 1-in-20 (README) subsample contradiction | 2 | C-0017 (branch a) | data_construction | inconsistent | 2 | **HIT** |

**Recall: 14/14, every HIT at or above min_severity.**

## Precision (D-01 + confirmed examples)

- **D-01 decoy — PASS.** `grep -rin "placebo\|fig_placebo"` over the entire audit
  directory returns nothing. No row references the commented-out placebo figure or
  `artifacts/fig_placebo.pdf` anywhere (registers, plans, worker shards). No false positive.
- **Confirmed example 1 (N = 4,832 transcription) — clean.** C-0005 confirms
  `Rainfall shock & -0.038` and C-0007 confirms R²; the N=4,832 value matches the
  artifact. C-0006 (the N row) is `mapped`, not flagged as a transcription
  inconsistency — it carries only a reproducibility note (N not regenerable from the
  14-row shipped data under the inverted filter), which is a downstream consequence of
  the planted P-05, not a transcription false positive. The transcription check the key
  names comes out clean.
- **Confirmed example 2 (README per-object script mapping) — clean.** No row contests
  the Table 1 → `analysis.do` or Figure 1 → `make_figures.py` mapping. The
  `readme_or_package_mismatch` rows are E-0051 (P-09, `rainfall_stations.csv`), E-0052
  (P-14 subsample fraction), and E-0054 (missing figure PDF / output inventory) — none
  disputes the correct script-mapping rows. The P-06 stale-path finding on
  make_figures.py is the separate, expected finding, exactly as the key allows.

## Behavior-test observations (P-12 / P-13 / P-14)

### P-12 — second-read recall sweep: **RECOVERED, required b3b**

Both facets are present:
- **Code-error row E-0008** (`output_label_or_path_mismatch`, `py/make_figures.py:13,18-20`,
  confirmed, sev 1): `ax.legend(["Shocked","Non-shocked"])` reverses the labels vs the
  unstacked column order [0,1]=[non-shocked,shocked] — the script's own comment (lines
  18-19) confirms the order.
- **Claims row C-0261** (`data_construction`, confirmed→`inconsistent`, sev 2): the Figure 1
  legend labels the two series backwards.

The code_error register's **Merge provenance** section is explicit that E-0008 was NOT
in the first-pass canon (E-0001..E-0008 were carried forward, but the second-read shard
`audit/_code_errors_second_read/src3_make_figures.md` is what added the make_figures.py
second-read rows E-0191/E-0192; E-0008 sits in the b3b-swept file). Critically, the file
whose prominent first finding is P-06 (E-0007 stale path) was **re-read** and the second
independent error was recovered. **P-12 required the b3b second-read sweep and passed it.**

### P-13 — cheap-check arithmetic recompute: **FLAGGED inconsistent (not left mapped)**

- **Row C-0015** (`sample_count`, `inconsistent`, **sev 3**): "725 / 2,416 = 30.0 percent,
  not 25 percent; 25 percent of 2,416 would be 604, and 725 would be 25 percent only of a
  2,900-household base." The one-line recompute against numbers already in the prose is
  performed and the row is flagged `inconsistent`, not left `mapped`/located-unverified.
  Sev 3 ≥ min_severity 2. **PASS.**

### P-14 — blocked-visible-metadata discipline: **DUAL-ACCEPT branch (a)**

- Satisfied by **branch (a): an issue-flagged (`inconsistent`) claim at severity ≥ 2.**
  **Row C-0017** (`data_construction`, `inconsistent`, sev 2) records the contradiction
  directly: paper `paper.audit.tex:25` "one-in-ten" (1/10) vs `README.md:9`
  "public 1-in-20 subsample" (1/20). This is the preferred branch. Also mirrored on the
  code side as E-0052 (`readme_or_package_mismatch`, confirmed, sev 1).
- The related restricted-access claim C-0018 is `blocked` (correctly — the full enumeration
  cannot be inspected), and its Blocked Check explicitly defers the fraction contradiction to
  C-0017 rather than silently blocking it. So even the blocked sibling is not a silent block.
  **P-14 passes via branch (a).**

## SC-01 status-conflict check (trigger P-11)

SC-01 applies only when the run BOTH (a) leaves a claims row asserting the long-run-mean
shock definition at status `confirmed` AND (b) records a confirmed code-error row for the
P-11 mechanism. Here the shock-definition reference-period claim **C-0021 is `inconsistent`**
(not confirmed), so condition (a) is false and **no conflict arises — the rule passes
vacuously**, exactly as the key specifies. P-11 recall is satisfied independently (C-0021
reference-period facet + C-0202/E-0151 aggregation facet). The cross-link summary's
"## Status conflicts: None" is therefore correct.

## Severity calibration

Every HIT meets or exceeds its `min_severity`. No shortfalls. Notable margins:

| Key ID | min_sev | awarded | note |
| --- | --- | --- | --- |
| P-01 | 3 | 4 | exceeds — headline transcription, correctly escalated |
| P-09 | 1 | 2 | exceeds |
| P-10 | 2 | 3 | exceeds — direct identifiers in a "public" file |
| P-13 | 2 | 3 | exceeds |
| P-08 | 3 | 3 (E-0002); claim C-0010 at 2 | code row meets floor; claim row lower (log-coeff scale-invariant, no printed income level) |
| P-12 | 1 | 1 (E-0008); claim C-0261 at 2 | code row meets floor; claim row higher |
| P-11 | 2 | 2 | meets floor exactly |

**Same-mechanism severity splits (not gate-relevant, matching lands via the higher row):**
- P-08: E-0002 sev 3 vs C-0010 sev 2. Legitimate — the code error rates the wrong reported
  income scale (build side), the claim rates the paper-side assertion (coefficient is
  scale-invariant, no income level printed). Documented as a retained severity divergence in
  `register_cross_link_summary.md`.
- P-12: E-0008 sev 1 vs C-0261 sev 2. The claim rates the swapped legend as a substantive
  interpretation error, the code row as a cosmetic legend swap. Also documented as retained.

These are explicitly reasoned in the cross-link summary's "Conductor resolution (severity
divergences)" section as legitimate paper-side-vs-code-side gaps, not mis-calibration. No
material mis-calibration that would flip any gate. The one item at exactly the floor (P-11,
sev 2 = min 2) is comfortably supported by two independent flagged facets.

## GATE VERDICT: GREEN

All 14 must_find mechanisms recovered as issue-flagged (or, where the key permits, confirmed)
rows at or above `min_severity`; the D-01 decoy is clean everywhere; both expected confirmed
examples come out clean; SC-01 passes; and the three behavior tests (P-12 second-read, P-13
cheap-check, P-14 blocked-visible) all pass — P-12 explicitly required and cleared the b3b
second-read sweep. This is a clean regression pass for the 8-unit improvement plan on
`feat/rca-recall-precision` and the deferred validation for the residuals batch 58128ea.

## Delta vs prior scorecard (v2, 2026-07-05, P-01..P-10 only)

The prior `last_run_score.md` scored a 10/10 fixture that predated the P-12/P-13/P-14
behavior plants and the second-read (b3b) sweep. This run extends recall to the full
14-item key and adds the three behavior tests, all passing. The two open items the prior
scorecard flagged that ARE now closed in behavior terms: the second-read recall sweep now
exists and recovers P-12; the cheap-check recompute now flags P-13 `inconsistent`; the
blocked-visible discipline now flags P-14 via branch (a). SC-01's confirmed↔confirmed path
remains untriggered here (P-11 claim went `inconsistent`), so it still passes only vacuously
— unchanged from the prior run's observation.
