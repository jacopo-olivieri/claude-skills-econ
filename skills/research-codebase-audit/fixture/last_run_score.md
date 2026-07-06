# Fixture run scorecard — ~/scratch/rca-run/audit/ (v2, post-skeleton-fixes)

Scored 2026-07-05 against `expected_findings.json` (planted fixture), adversarial
matching on mechanism + location, severity gate per the key's `min_severity`.
Registers scored: `claims_register.md`, `code_error_register.md`,
`output_register.md`, `code_review.xlsx` (all three content sheets verified
cell-for-cell against the markdown registers; no `*_Original` columns exported).
This run follows two skeleton fixes: (1) severity calibration for the unit
error, (2) cross-link consistency / status-conflict surfacing.

## Headline

| Metric | Result |
| --- | --- |
| **Recall (must_find)** | **10 / 10** |
| **Precision (decoy)** | **PASS** — `fig_placebo` appears nowhere in the audit directory (registers, xlsx, worker files, plans — zero mentions) |
| **Expected confirmed examples** | **PASS** — both clean (see caveat on N = 4,832 below) |

## Per-item results

| Key ID | Mechanism (short) | min_sev | Matching rows | Severity awarded | Verdict |
| --- | --- | --- | --- | --- | --- |
| P-01 | Prose 0.083 vs artifact −0.038 transcription | 3 | C-0001 (`transcription`, `inconsistent`) — cites both abstract and §3, quotes both values | 3 | **FOUND** |
| P-02 | Village vs household clustering | 3 | E-0004 (`inference_or_se_specification`), C-0012 (`estimation_specification`) — both cite `analysis.do:16,24` `vce(cluster household_id)` | 3 | **FOUND** |
| P-03 | Weighted claim, unweighted code | 3 | E-0005 (`weighting_error`), C-0011 — notes `svy_weight` exists but is never used | 3 | **FOUND** |
| P-04 | Bootstrap 200 reps, no `set seed`/stable sort | 2 | E-0006 (`randomness_or_seed_error`), C-0018 — names both the missing seed and the missing deterministic sort | 2 | **FOUND** |
| P-05 | `keep if waves < 2` inverts the exclusion rule | 4 | E-0002 (`sample_filter_or_flag_error`, sev 4), C-0005 (sev 4), C-0006/C-0007 (downstream) | 4 | **FOUND** |
| P-06 | make_figures.py reads phantom `panel_v2.csv` | 2 | E-0007 (`stale_or_wrong_path`), C-0017 — correctly notes `build_panel.do:28` writes `panel.csv` | 2 | **FOUND** |
| P-07 | `$controls` defined only in a commented line | 3 | E-0003 (`undefined_variable_or_global`), C-0010, C-0014 (Table 1 "Yes" row) | 3 | **FOUND** |
| P-08 | Income ÷100 vs "thousands" (factor-of-10 unit error) | 3 | E-0001 (`aggregation_or_unit_error`, **sev 3**), C-0004 (sev 2) — exact mechanism, location, ×10 diagnosis, Figure-1 axis propagation | 3 | **FOUND** |
| P-09 | README declares absent, unread `rainfall_stations.csv` | 1 | E-0051 (`readme_or_package_mismatch`) — confirms file absent AND unread; notes shock built from `rain_mm` | 2 | **FOUND** |
| P-10 | `head_name` + GPS coordinates in shipped data | 2 | E-0055 (`pii_or_disclosure_risk`) — names, ~5-decimal GPS, `age_head` quasi-identifier, propagation into `output/panel.*` | 3 | **FOUND** |

All matches are at the planted location with the planted mechanism; none rely
on generous type-mapping (each code-error row carries exactly the key's
`expected_type`).

## Decoy check (D-01)

`grep -rni placebo` over the entire audit directory returns **nothing** — the
decoy is absent not just from the registers and xlsx but from every plan,
worker, and boundary file. (v1 still mentioned it in three non-register files
as explicit exclusions.) Comment-blanking plus scope discipline fully held.
**Pass.**

## Expected confirmed examples

1. **N = 4,832 prose vs artifact** — the transcription check passes explicitly:
   C-0007's issue text states the value "matches the shipped table artifact (so
   it is not a transcription slip)". *Caveat:* the row's status is
   `inconsistent` (sev 2) anyway, on reproducibility grounds — N cannot be
   regenerated from the 14-row fixture data, and the row is cross-linked to
   E-0002 (the P-05 filter inversion). That is a legitimate downstream
   consequence of a planted error, not a false transcription finding, and the
   key does not penalize extra findings. Scored **clean**, but a stricter key
   wording ("row status must be `confirmed`") would flip this — worth deciding
   which reading the key intends.
2. **README per-object script mapping** — no row contests the
   Table 1 → `analysis.do` or Figure 1 → `make_figures.py` mapping. The four
   `readme_or_package_mismatch` rows are the planted P-09 (E-0051), the missing
   figure artifact (E-0052), and two environment-capture gaps (E-0053/E-0054).
   **Clean.**

## Fix verification

### Fix 1 — severity calibration on the unit error: **VERIFIED**

E-0001 now scores **severity 3** (v1: 2), and its "Why It Matters" text uses
exactly the calibration rationale from the v1 feedback: every reported/plotted
income level is off by 10× and "a reported quantity's units are misstated" —
severity anchored on the wrong reported numbers, not on the unaffected
regression slope (which the row still correctly notes as a mitigant rather
than a downgrade reason).

*Residual wobble:* the linked claim row C-0004 still carries severity 2 with
the old "coefficient is unaffected" reasoning. The key matches via E-0001, so
recall is unaffected, but the same mechanism now has two different severities
across registers. If claim-side severity is supposed to track the same rubric,
the calibration note should be extended to the claims skeleton too.

### Fix 2 — cross-link consistency: **VERIFIED (structurally); conflict path exercised only vacuously**

- Every confirmed code error that breaks a claim is bidirectionally linked:
  E-0001↔C-0004, E-0002↔C-0005/6/7, E-0003↔C-0010/C-0014, E-0004↔C-0012
  (clustering), E-0005↔C-0011 (weighting), E-0006↔C-0018 (bootstrap CI — the
  exact gap flagged in v1 issue #3, now closed), E-0007↔C-0017,
  E-0052↔C-0017. Links are mirrored identically in both registers and the xlsx.
- `register_cross_link_summary.md` now has an explicit **Mandatory sweep**
  section (every confirmed error checked against every claim) and a **Status
  conflicts** section. It reports "None", which is correct for this run's rows:
  every linked claim is `inconsistent` or `confirmation_needed`; no confirmed
  claim is paired with a confirmed error.
- The summary also documents *deliberate* non-links with reasons (E-0051,
  E-0053/54, E-0055, C-0001) — a real improvement in auditability over v1.
- **Caveat:** the run never actually hit a confirmed↔confirmed conflict,
  because the v1 finding that created one (the "long-run mean is really a
  two-wave in-sample mean" error that contradicted confirmed C-0008) does not
  exist in this run at all. So the conflict-resolution path before b8 remains
  untested by a live conflict — the fixture has no planted item that forces
  one. See quality note 3.

## Delta vs v1 scorecard (`score-2026-07-05-v1.md`)

| Dimension | v1 | v2 |
| --- | --- | --- |
| Recall | 9/10 (P-08 under-severity) | **10/10** |
| Precision (decoy) | pass (3 benign mentions in non-register files) | **pass (zero mentions anywhere)** |
| Confirmed examples | pass | pass (N-row caveat noted) |
| Unit-error severity (fix 1) | E sev 2 | **E sev 3** (claim row still 2) |
| Bootstrap cross-link (v1 issue #3) | missing | **linked E-0006↔C-0018** |
| Confirmed↔confirmed conflict handling (v1 issue #2) | contradiction present, unlinked, unsurfaced | conflict absent this run — sweep exists, path untested |
| Codename leakage in `*_Original` (v1 issue #4) | present (CE-01/CE-02 refs) | **none found** (grepped both registers) |
| b8 staging replayability (v1 issue #5) | `--stage b8` FAIL, `_staging/` bare | **unchanged: still FAIL** |
| Extra (non-key) findings | shock-mean finding, others | that finding gone; 3 environment/package rows added (E-0052/53/54) |

## Register-quality problems the key doesn't capture

1. **b8 lint still fails** (`lint_registers.py --stage b8`): `_staging/` exists
   but is empty, so the b8 boundary is not replayable; `--stage b9` passes and
   the final registers are lint-clean. Same defect as v1 issue #5, carried
   over unfixed — either the pipeline should stop emptying `_staging/` after
   promotion, or the b8 lint contract should be relaxed to "at promotion time".
2. **Severity split on the same mechanism**: E-0001 sev 3 vs C-0004 sev 2
   (unit error), and E-0003 sev 3 vs C-0014 sev 2 (controls "Yes" label). The
   second split is defensible (the table label is a narrower assertion), the
   first looks like the fix-1 calibration reaching only the code-error
   skeleton. A one-line rule — "linked rows describing the same mechanism
   justify any severity difference explicitly" — would catch both.
3. **The fixture cannot exercise the status-conflict path.** Fix 2's
   confirmed-claim↔confirmed-error machinery reported "None" and that is
   genuinely correct here. To regression-test it, the fixture needs a planted
   pair designed to collide (e.g. a claim a naive reviewer confirms that a
   code error demonstrably breaks). Until then, "conflicts: None" is
   indistinguishable from "conflict sweep silently skipped".
4. **A v1 extra finding vanished without trace**: v1 flagged that the shock's
   "long-run mean" is computed from only the two in-sample waves; v2 confirms
   C-0009 with no mention. Not key-penalized (it isn't planted), but a
   substantive borderline finding appearing in one run and not the next is
   run-to-run variance worth watching — it is exactly the row that would have
   triggered the status-conflict path.
5. **C-0013 (5% significance, `mapped`) is not linked to E-0004** even though
   E-0004's own text says household-level clustering "can affect the 5%
   significance of the headline estimate", and C-0012's issue text says the
   significance claim "rests on clustering that does not match the paper". The
   cross-link summary files C-0013 under "assert nothing that a registered
   error breaks", which its own sibling rows contradict. Minor, but it is a
   real miss of the fix-2 sweep rule ("link the claim rows that assert the
   thing the error breaks") — the significance assertion is broken by the
   clustering error as directly as C-0012 is.
6. **xlsx parity**: verified — sheet row counts (19 claims, 12 errors), IDs,
   types, statuses, severities, and link columns all match the markdown
   registers exactly; the Overview sheet and the extra `Potential Issue`
   column are additive only. No issue.

## Net assessment

Clean 10/10 recall, perfect decoy hygiene, both fixes demonstrably landed in
the output. The remaining feedback for the skeletons is second-order:
propagate severity calibration to claim rows (note 2), close the
significance-claim link rule (note 5), stop dropping `_staging/` (note 1), and
— for the fixture itself — plant a confirmed↔confirmed collision so fix 2's
conflict path gets a real regression test (note 3).
