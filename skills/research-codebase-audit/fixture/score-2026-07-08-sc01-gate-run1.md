# Fixture score — 2026-07-08 — SC-01 gate re-score, RUN 1

- Audit dir: `~/scratch/rca-sc01-rescore/run1/pkg/audit`
- Answer key: `fixture/expected_findings.json` (scorer default)
- Scorer exit code: **1 → GATE RED**
- Branch under test: `fix/rca-sc01-status-conflict` (quote-qualifier gate + b7 overlap advisory)

## Framing note (read first)

Per the Evaluation protocol in `fixture/README.md`, the artifact-layer outcomes
(U2/U4/U5) settle on a **single** re-score, while the worker-dependent register
outcomes (recall, and here the SC-01 Layer-1 attribution) need **two consecutive
green re-scores**. This is **RUN 1 OF 2** for the register layer. Do not merge on
this run alone — and since this run is GATE RED (P-18 severity miss + D-02 decoy
present), it does **not** count as the first green run; the two-run count has not
started.

## 1. Full scorer output

```
Fixture score — audit dir: /Users/jacopoolivieri/scratch/rca-sc01-rescore/run1/pkg/audit
Answer key: .../skills/research-codebase-audit/fixture/expected_findings.json

P-01: HIT — C-0001 (claims, status=inconsistent, sev=3); C-0002 (claims, status=inconsistent, sev=3)
P-02: HIT — C-0020 (claims, status=inconsistent, sev=4); E-0005 (errors, status=confirmed, sev=3); E-0006 (errors, status=confirmed, sev=3)
P-03: HIT — C-0019 (claims, status=inconsistent, sev=3); E-0006 (errors, status=confirmed, sev=3)
P-04: HIT — E-0007 (errors, status=confirmed, sev=2)
P-05: HIT — C-0008 (claims, status=inconsistent, sev=4); E-0003 (errors, status=confirmed, sev=4)
P-06: HIT — C-0026 (claims, status=inconsistent, sev=2); E-0010 (errors, status=confirmed, sev=2); E-0053 (errors, status=confirmed, sev=2)
P-07: HIT — C-0018 (claims, status=inconsistent, sev=3); E-0004 (errors, status=confirmed, sev=3); E-0005 (errors, status=confirmed, sev=3)
P-08: HIT — E-0002 (errors, status=confirmed, sev=3)
P-09: HIT — E-0051 (errors, status=confirmed, sev=2)
P-10: HIT — E-0057 (errors, status=confirmed, sev=2)
P-11: HIT — C-0016 (claims, status=inconsistent, sev=3); C-0150 (claims, status=inconsistent, sev=3); E-0151 (errors, status=confirmed, sev=3); E-0152 (errors, status=confirmed, sev=2)
P-12: HIT — C-0025 (claims, status=inconsistent, sev=2); E-0011 (errors, status=confirmed, sev=3); E-0212 (errors, status=confirmed, sev=2)
P-13: HIT — C-0011 (claims, status=inconsistent, sev=2)
P-14: HIT — C-0013 (claims, status=inconsistent, sev=2)
P-15: HIT [class=enumerated_member_list] — C-0006 (claims, status=inconsistent, sev=2); E-0009 (errors, status=confirmed, sev=2)
P-16: HIT [class=manifest_parseability] — E-0054 (errors, status=confirmed, sev=2)
P-17: HIT [class=empirical_verification] — E-0001 (errors, status=confirmed, sev=2)
P-18: MISS [class=empirical_verification] — mechanism matched but no qualifying row at severity >= 2: E-0008 (errors, status=confirmed, sev=1)
P-19: HIT [class=identifier_anchoring] — C-0021 (claims, status=inconsistent, sev=2); E-0192 (errors, status=confirmed, sev=2)
P-20: HIT [class=step_parameter_filename] — C-0028 (claims, status=inconsistent, sev=2)

D-01 decoy: ABSENT
D-02 decoy: PRESENT — E-0193 (errors, status=confirmed, sev=1)
SC-01: PASS

Artifact-layer checks (single-re-score layer; record separately from the register-based two-run results):
U2 manifest artifact: PASS — _run/manifest_check.md names pyproject.toml
U4 anchoring advisory: PASS — vacuous — P-19 claim not confirmed (closed inconsistent)
U5 filename-parameter advisory: PASS — vacuous — P-20 row not blocked (closed confirmation_needed/inconsistent)
U1 conventions artifact: INFO — enumerated_member_list convention PRESENT; P-15 mechanism row present (C-0006 (claims, status=inconsistent, sev=2)) (worker-dependent — informative, not gate-settling)

Recall: 19/20
Per-class:
  empirical_verification: 1/2 hit, 1 miss
  enumerated_member_list: 1/1 hit, 0 miss
  identifier_anchoring: 1/1 hit, 0 miss
  manifest_parseability: 1/1 hit, 0 miss
  step_parameter_filename: 1/1 hit, 0 miss
  unclassified_legacy: 14/14 hit, 0 miss
GATE RED — P-18 MISS; D-02 decoy present
```

## 2. Plain-language reading of the automated score

**Gate: RED** (exit code 1), on two independent grounds — a recall miss and a
precision (decoy) failure.

**Recall: 19/20.** The one miss is P-18 (empirical_verification class): the
worker DID find the mechanism — E-0008 correctly diagnoses that the `has_wages`
loop reassigns the whole column each iteration so the flag reflects only the last
wave, and even ran a synthetic probe confirming a wave-1-only earner ends up
False — but rated it severity 1 on the grounds that `has_wages` only feeds the
off-path diagnostic `output/income_check.csv`. The answer key's floor for P-18 is
severity 2, so this is a severity-calibration miss, not a detection miss.

**Per-class breakdown reconciles with the aggregate:** empirical_verification
1/2 + enumerated_member_list 1/1 + identifier_anchoring 1/1 +
manifest_parseability 1/1 + step_parameter_filename 1/1 + unclassified_legacy
14/14 = 19/20. Consistent.

**Artifact layer (single-re-score layer, all green):**
- U2: PASS — `_run/manifest_check.md` names `pyproject.toml`.
- U4: PASS vacuously — the P-19 claim closed `inconsistent`, so the anchoring
  advisory had no confirmed-claim state to fire on.
- U5: PASS vacuously — the P-20 row did not close blocked, so the
  filename-parameter advisory had nothing to fire on.
- U1: INFO only (never gate-settling) — the enumerated_member_list convention is
  present and the P-15 row exists.

**Precision: FAILED on D-02.** D-01 (placebo figure) is absent from every
register — good. But D-02 is present as E-0193 (confirmed, sev 1): a finding
about `farm_share` in the `py/build_income.py` farm_components block (winsorised
numerator over raw denominator, no zero-income guard). The answer key is
explicit: the farm_components subset is a deliberate, locally-signposted
farm-only descriptive share, and "any finding about the farm components or farm
share is a false positive." E-0193 is squarely such a finding, so the scorer's
RED is correct on hand review too. Note the failure mode: the worker did not
flag the *subset* itself (the U1 intentional-subset guard apparently held for
the member-list aspect), but flagged an adjacent computation nit *inside the
decoy block* — the decoy still catches it.

## 3. Hand-scored items (not covered by the scorer)

**Type adjudication: PASS.** Every recovered must-find carries a plausible type:
- Code-side exact matches to the key: E-0005 inference_or_se_specification
  (P-02), E-0006 weighting_error (P-03), E-0007 randomness_or_seed_error (P-04),
  E-0003 sample_filter_or_flag_error (P-05), E-0004 undefined_variable_or_global
  (P-07), E-0002 aggregation_or_unit_error (P-08), E-0051
  readme_or_package_mismatch (P-09), E-0057 pii_or_disclosure_risk (P-10),
  E-0151 aggregation_or_unit_error (P-11, the key's accepted dual type),
  E-0011/E-0212 output_label_or_path_mismatch (P-12), E-0009
  aggregation_or_unit_error (P-15), E-0054 syntax_or_parse_error (P-16, accepted
  alternate), E-0001 sample_filter_or_flag_error (P-17), E-0192
  aggregation_or_unit_error (P-19, accepted code-side type).
- Claim-side equivalents where the key allows them: C-0016 treatment_definition
  (P-11), C-0008 sample_count (P-05), C-0006 data_construction (P-15), C-0028
  data_construction (P-20), C-0021 estimation_specification (P-19).
- Two defensible-adjacent codings, noted but not failures: E-0010 is typed
  missing_input_or_output where the key nominally says stale_or_wrong_path
  (P-06 — same mechanism, the figure script reads a nonexistent
  `panel_v2.csv`); C-0011 is typed sample_count where the key lists
  interpretation/rounding/quantitative_result (P-13 — the 725-of-2,416
  arithmetic recompute; a count typing is an equivalent claim type under the
  key's mechanism-first rule).

**expected_confirmed_examples cleanliness: PASS.** C-0009 ("balanced panel of
4,832 household-year observations") and C-0010 ("2,416 households across the two
waves") both closed `confirmed` with no spurious flag. No
readme_or_package_mismatch finding touches the Table 1 → analysis.do or
Figure 1 → make_figures.py mapping rows (the only README-mapping error rows are
the expected E-0051/E-0053).

## 4. SC-01 layer attribution — **LAYER 1 (root fix worked)**

The P-11 pair in this run is claim **C-0016** (worker-assigned ID; the ticket's
"C-0014" was the ID in the earlier run) versus confirmed error **E-0151** on
`do/build_panel.do`.

a. **Claims register:** C-0016 closed `inconsistent`, severity 3. Its Issue
   Description is genuine Layer-1 reasoning, not a cross-link note: "the paper
   defines the shock as the standardised deviation from each village's
   1991–2020 climate normal, but `do/build_panel.do:21-23` computes the mean and
   standard deviation only over the two in-sample waves, not a 1991–2020 normal
   — the treatment variable is built from a different reference period than the
   paper states." That is exactly the long-run/climate-normal-vs-in-sample-mean
   qualifier mismatch the quote-qualifier gate was written to catch.

b. **Cross-link summary:** C-0016 <-> E-0151 appears under "## Links added"
   (linked as an inconsistent claim to its confirmed error) and is **NOT**
   listed under "## Status conflicts" — the only status conflicts are
   C-0003 <-> E-0005 and C-0031 <-> E-0052, both properly resolved by the
   conductor. So C-0016 never reached b7 in the `confirmed` state; Layer 2 had
   nothing to rescue.

c. **b7 linter re-run:** `LINT PASS [b7]`, exit 0. Sixteen advisory
   overlap-conflict WARNINGs fired, and **none names the C-0016/E-0151 pair**
   — correct, because the advisory only screens *confirmed* claims and C-0016
   is already `inconsistent`. (One warning names C-0012 <-> E-0151, but the
   cross-link summary explicitly adjudicated that pair as not a genuine
   conflict: the sign-coding definition C-0012 asserts is not broken by how
   `rain_mean`/`rain_sd` are computed.)

Per the answer key, SC-01's conditional rule passes **vacuously** in this run —
the claims review demoted the claim directly, so no conflict ever arose. That is
the ideal branch: **the first-pass quote-qualifier rule caught the defect at the
root.** No U1/U2 wording review is triggered by this run.

**Advisory-precision side note** (relevant to the open KTD-5 question): all 16
overlap-conflict advisories in this run were adjudicated benign in the b7
summary — 0 true positives out of 16 in this run (the two real status conflicts
were found by the cross-linker itself, not the advisory). Further evidence
against hardening the advisory into a gate.

## Verdict

| Check | Result |
| --- | --- |
| Gate (scorer exit) | **RED** |
| Recall | 19/20 (P-18 severity-calibration miss) |
| Precision | **FAILED** — D-02 present as E-0193 |
| Artifact layer U2/U4/U5 | PASS (settled — single-re-score layer) |
| SC-01 | PASS — resolved at **LAYER 1** |
| Type adjudication (hand) | PASS |
| Confirmed-examples cleanliness (hand) | PASS |

The SC-01 fix demonstrably worked at Layer 1, but the run as a whole is RED on
two unrelated grounds (P-18 severity floor, D-02 decoy). This run does not count
toward the two-consecutive-green requirement for the register layer; a fresh
run is needed, and the P-18/D-02 failure modes (severity calibration on off-path
diagnostics; adjacent findings inside a signposted decoy block) are the things
to watch in it.

## Addendum (2026-07-08, post-review, decision by Jacopo)

Hand review of the two RED grounds found both to be answer-key defects, not
product defects, and the key was corrected:

1. **P-18 floor lowered from severity 2 to 1.** The worker detected the
   `has_wages` loop-overwrite, proved it with a synthetic probe, and rated it
   severity 1 because the flag feeds only the off-path diagnostic
   `output/income_check.csv`. That rating is a correct application of the
   registers.md author-materiality rubric (severity 1 = note-worthy but
   immaterial; no reported quantity or reproduction step is affected). The
   key's floor of 2 conflicted with the skill's own rubric. The key already
   uses a floor of 1 for P-09 and P-12.
2. **D-02 narrowed to subset-omission complaints.** The blanket rule ("any
   finding about the farm components or farm share is a false positive")
   condemned E-0193, a technically true observation (no zero-income guard;
   `farm_share == inf` on a zero-income row) that did not take the planted
   bait. The decoy now trips only on complaints that the farm_components list
   omits/diverges from the four-component definition. Scorer matcher updated
   (site terms AND qualifier terms); pinned by a new harness test
   (`test_non_omission_finding_in_subset_block_is_not_decoy`); the original
   bait-complaint test still passes. Harness: 129 passed.

**Re-score under the corrected key: GATE GREEN, recall 20/20, all decoys
absent, exit 0.**

**Protocol waiver and merge decision.** The pre-registered evaluation protocol
requires two consecutive green worker-dependent re-scores before merge. Jacopo
waived the second run on 2026-07-08: the branch's purpose (the SC-01 Layer-1
fix) demonstrably fired in this run, the RED grounds were key defects now
fixed, and the better validation instrument is the fourth Floods run on the
real package. Recorded so this merge is not later read as a passed two-run
gate. The key corrections were made after seeing the run's output; the
justification is the rubric, not the desire to pass — but this is noted
explicitly per the no-harvesting rule.

**KTD-5 settled.** The overlap-conflict advisory ships as an advisory; the
reserved hard accounting gate is dropped. Measured precision: 1 true pair in
20 fired (recovered run-1 registers), then 0 true in 16 fired (this run; both
real status conflicts were found by the cross-linker itself).
