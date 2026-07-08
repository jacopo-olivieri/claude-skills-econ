# Fixture score — 2026-07-08 — definition/use-contract (defuse) gate re-score, RUN 1

- Audit dir: `~/scratch/rca-defuse-rescore/run1/pkg/audit`
- Answer key: `fixture/expected_findings.json` (scorer default; 21 must_find incl. P-21)
- Scorer exit code: **1 → mechanically GATE RED** (sole ground: D-02 decoy match — hand-adjudicated below as a scorer-matcher false positive, not a run precision failure)
- Branch under test: `fix/rca-defuse-contract-recall` (reworded standing check 2, definition/use contract)

## Scope note (read first)

This run validates that the **reworded check can fire on the plant** (P-21 in the
fixture), not that it fires on real packages — the honest test remains the next
Floods run. Per the Evaluation protocol in `fixture/README.md`, register-layer
(worker-dependent) outcomes need two consecutive green re-scores; this is RUN 1
of that count. Artifact-layer outcomes (U2/U4/U5) settle on this single re-score.

## 1. Full scorer output

```
Fixture score — audit dir: /Users/jacopoolivieri/scratch/rca-defuse-rescore/run1/pkg/audit
Answer key: .../skills/research-codebase-audit/fixture/expected_findings.json

P-01: HIT — C-0001 (claims, status=inconsistent, sev=3)
P-02: HIT — C-0013 (claims, status=inconsistent, sev=3); C-0171 (claims, status=confirmation_needed, sev=3); E-0006 (errors, status=confirmed, sev=3)
P-03: HIT — C-0012 (claims, status=inconsistent, sev=3); C-0171 (claims, status=confirmation_needed, sev=3); E-0007 (errors, status=confirmed, sev=3)
P-04: HIT — E-0008 (errors, status=confirmed, sev=2); E-0171 (errors, status=confirmed, sev=2)
P-05: HIT — C-0007 (claims, status=inconsistent, sev=4); E-0004 (errors, status=confirmed, sev=4)
P-06: HIT — E-0012 (errors, status=confirmed, sev=2)
P-07: HIT — C-0016 (claims, status=inconsistent, sev=3); E-0005 (errors, status=confirmed, sev=3); E-0006 (errors, status=confirmed, sev=3); E-0007 (errors, status=confirmed, sev=3)
P-08: HIT — C-0004 (claims, status=inconsistent, sev=3); E-0211 (errors, status=confirmed, sev=3)
P-09: HIT — E-0051 (errors, status=confirmed, sev=2)
P-10: HIT — C-0142 (claims, status=inconsistent, sev=3); E-0056 (errors, status=confirmed, sev=3); E-0057 (errors, status=confirmed, sev=3); E-0233 (errors, status=confirmed, sev=2); E-0235 (errors, status=confirmed, sev=2); E-0236 (errors, status=confirmed, sev=3)
P-11: HIT — C-0011 (claims, status=inconsistent, sev=3); E-0151 (errors, status=confirmed, sev=3); E-0152 (errors, status=confirmed, sev=2)
P-12: HIT — E-0013 (errors, status=confirmed, sev=2)
P-13: HIT — C-0008 (claims, status=inconsistent, sev=2)
P-14: HIT — C-0010 (claims, status=inconsistent, sev=2); E-0232 (errors, status=confirmed, sev=2)
P-15: HIT [class=enumerated_member_list] — C-0003 (claims, status=inconsistent, sev=2); E-0009 (errors, status=confirmed, sev=2)
P-16: HIT [class=manifest_parseability] — E-0054 (errors, status=confirmed, sev=2); E-0231 (errors, status=confirmed, sev=2)
P-17: HIT [class=empirical_verification] — E-0002 (errors, status=confirmed, sev=2)
P-18: HIT [class=empirical_verification] — E-0011 (errors, status=confirmed, sev=2)
P-19: HIT [class=identifier_anchoring] — C-0014 (claims, status=inconsistent, sev=2); E-0010 (errors, status=confirmed, sev=2)
P-20: HIT [class=step_parameter_filename] — C-0021 (claims, status=inconsistent, sev=2); E-0235 (errors, status=confirmed, sev=2)
P-21: HIT [class=definition_use_contract] — E-0001 (errors, status=confirmed, sev=3); E-0236 (errors, status=confirmed, sev=3)

D-01 decoy: ABSENT
D-02 decoy: PRESENT — E-0009 (errors, status=confirmed, sev=2); E-0302 (errors, status=duplicate_of:E-0009, sev=-)
SC-01: PASS

Artifact-layer checks (single-re-score layer; record separately from the register-based two-run results):
U2 manifest artifact: PASS — _run/manifest_check.md names pyproject.toml
U4 anchoring advisory: PASS — vacuous — P-19 claim not confirmed (closed inconsistent)
U5 filename-parameter advisory: PASS — vacuous — P-20 row not blocked (closed inconsistent)
U1 conventions artifact: INFO — enumerated_member_list convention PRESENT; P-15 mechanism row present (C-0003 (claims, status=inconsistent, sev=2)) (worker-dependent — informative, not gate-settling)

Recall: 21/21
Per-class:
  definition_use_contract: 1/1 hit, 0 miss
  empirical_verification: 2/2 hit, 0 miss
  enumerated_member_list: 1/1 hit, 0 miss
  identifier_anchoring: 1/1 hit, 0 miss
  manifest_parseability: 1/1 hit, 0 miss
  step_parameter_filename: 1/1 hit, 0 miss
  unclassified_legacy: 14/14 hit, 0 miss
GATE RED — D-02 decoy present
```

## 2. Aggregate recall and per-class breakdown

**Recall: 21/21** — first perfect recall on the expanded key. Per-class
reconciles with the aggregate: definition_use_contract 1/1 +
empirical_verification 2/2 + enumerated_member_list 1/1 + identifier_anchoring
1/1 + manifest_parseability 1/1 + step_parameter_filename 1/1 +
unclassified_legacy 14/14 = 21/21. P-18 (severity floor lowered to 1 under the
corrected key) hit at severity 2 this run, so it clears even the old floor.
P-14 and P-20 both recovered on the preferred inconsistent branch (severity 2),
no dual-accept blocked branch needed.

## 3. Precision / decoys — hand adjudication of the scorer's D-02 flag

- **D-01 (placebo figure): ABSENT — PASS.** No register row mentions the
  placebo figure or `fig_placebo.pdf`.
- **D-02 (farm_components subset): mechanically PRESENT, hand-adjudicated NOT
  TRIPPED — scorer-matcher false positive.** The two matched rows are E-0009
  and its automated duplicate E-0302, and both are the **P-15 recovery itself**
  (the total-income component list at `py/build_income.py:14` omits
  remittances), not a subset-omission complaint about `farm_components`.
  E-0009's evidence cites the farm-share comment only as proof the file itself
  asserts a four-component set: "the file's own later comment states the farm
  share is 'deliberately a subset of the four income components' (L28-30)".
  E-0302 explicitly clears the decoy site: "The `farm_components` subset at L31
  is explicitly local (farm-share diagnostic) and recorded
  reviewed-not-divergent." The narrowed D-02 rule (2026-07-08) trips only on
  complaints that the farm_components list omits/diverges from the
  four-component definition; neither row makes that complaint. The matcher in
  `scripts/score_fixture.py` (DECOYS["D-02"]) requires site terms AND qualifier
  terms anywhere in the row text, and the P-15 row necessarily contains both
  ("farm share"/"farm_components" as cited evidence, "omit"/"remittance"/
  "subset" as the true P-15 mechanism), so any P-15 hit that quotes the
  in-file signpost comment will trip the decoy. This is a matcher defect, not
  a run defect. Note E-0009 is simultaneously counted as the P-15 HIT and the
  D-02 trip — the same row cannot honestly be both. Not fixed here (scorer left
  untouched); flagged for owner decision.
- No other decoy-adjacent findings.

## 4. SC-01 status-conflict check

**PASS — vacuous branch (ideal).** The P-11 claim row C-0011 (the long-run
1991–2020 climate-normal shock definition) closed `inconsistent` at severity 3
directly in the claims review — the quote-qualifier gate fired at Layer 1 again,
reproducing the SC-01 gate-run-1 behavior. No claims-register row asserting the
long-run definition is `confirmed` anywhere. `register_cross_link_summary.md`
"## Status conflicts" reads "None. No `confirmed` claim was linked to any
`confirmed` error." The 2026-07-07 regression shape (SC-01 failing while P-11
recall stays green) did **not** recur: P-11 recall green AND no unresolved
conflict. This is the second consecutive run with SC-01 resolved at Layer 1.

## 5. Named legacy regression watch (mandatory list)

| Item | Result | Notes |
| --- | --- | --- |
| P-01 | HIT | C-0001 inconsistent sev 3 |
| P-02 | HIT | E-0006 confirmed sev 3 + claim rows |
| P-03 | HIT | E-0007 confirmed sev 3 + claim rows |
| P-04 | HIT | E-0008 confirmed sev 2 |
| P-05 | HIT | C-0007 sev 4 / E-0004 sev 4 |
| P-06 | HIT | E-0012 confirmed sev 2 |
| P-07 | HIT | E-0005 confirmed sev 3 |
| P-08 | HIT | E-0211 confirmed sev 3 |
| P-09 | HIT | E-0051 confirmed sev 2 |
| P-10 | HIT | E-0056/E-0057 sev 3, plus bonus E-0236 consent-adequacy PII row |
| P-11 | HIT | C-0011 inconsistent sev 3; E-0151 confirmed sev 3 |
| P-12 | HIT | E-0013 confirmed sev 2 (second-read sweep held) |
| P-13 | HIT | C-0008 inconsistent sev 2 (arithmetic recompute held) |
| P-14 | HIT | C-0010 inconsistent sev 2 (preferred branch) |
| P-15 | HIT | C-0003 / E-0009 sev 2 |
| P-16 | HIT | E-0054 sev 2 + README-facing E-0231 |
| P-17 | HIT | E-0002 confirmed sev 2 |
| P-18 | HIT | E-0011 confirmed sev 2 (above even the retired floor of 2) |
| P-19 | HIT | C-0014 inconsistent sev 2; not confirmed (anchoring held) |
| P-20 | HIT | C-0021 inconsistent sev 2 (preferred branch) |
| SC-01 | PASS | Layer-1 demotion, vacuous conflict rule; no 2026-07-07 shape |
| D-01 | PASS | absent |
| D-02 | PASS (hand) / FAIL (mechanical) | matcher false positive on the P-15 row — see §3 |
| U2 manifest artifact | PASS | `_run/manifest_check.md` names `pyproject.toml` |
| U4 anchoring advisory | PASS | vacuous — P-19 closed inconsistent |
| U5 filename advisory | PASS | vacuous — P-20 not blocked |
| U1 conventions artifact | INFO | convention present, P-15 row present |

No legacy regression. Instruction growth from the reworded standing check 2 did
not cost any prior plant.

## 6. P-21 worker evidence (required for the gate, beyond the mechanical hit)

Primary row **E-0001** (`sample_filter_or_flag_error`, `do/build_panel.do:11-18`,
confirmed, severity 3). Its verification text demonstrably compares the
producer-defined coverage against the consumer's effective predicate — the exact
reasoning the reworded check asks for:

> "The producer `consent_ok = (consent == "individual") | (consent ==
> "community")` is defined (and its comment L11-14 states) to clear households
> under either the individual OR the community consent route ('both consent
> routes are approved for release'). The consumer L18 `keep if consent_ok == 1
> & consent == "individual"` adds the predicate `consent == "individual"`,
> which narrows the covered set to individual-consent households only and drops
> every community-consent household. No companion consumer covers the excluded
> community households, and the extra predicate makes `consent_ok` redundant on
> its own terms."

The materiality chain is also traced ("changing N (reported 4,832) and the
estimation sample feeding Table 1"), matching the key's on-path severity-floor
rationale; severity 3 clears the floor of 2. The second matched row, E-0236, is
a genuine bonus finding downstream of the same defect (community-consent
households ship with full PII in the raw file), not a duplicate — evidence the
worker reasoned about the excluded case family, not just the predicate.
**P-21 worker-evidence check: PASS.**

## 7. Hand-scored items

**Type adjudication: PASS.** Code side: E-0004 sample_filter_or_flag_error
(P-05), E-0006 inference_or_se_specification (P-02), E-0007 weighting_error
(P-03), E-0008 randomness_or_seed_error (P-04), E-0005
undefined_variable_or_global (P-07), E-0211 aggregation_or_unit_error (P-08),
E-0051 readme_or_package_mismatch (P-09), E-0056/E-0057 pii_or_disclosure_risk
(P-10), E-0151 aggregation_or_unit_error (P-11, accepted dual type), E-0013
output_label_or_path_mismatch (P-12), E-0009 aggregation_or_unit_error (P-15),
E-0054 version_or_dependency_error (P-16, exact), E-0002 and E-0011
sample_filter_or_flag_error (P-17/P-18), E-0010 aggregation_or_unit_error
(P-19, accepted code-side type), E-0001 sample_filter_or_flag_error (P-21,
exact expected type). Claim side: C-0001 transcription (P-01), C-0013/C-0012
estimation_specification (P-02/P-03), C-0007 sample_count (P-05), C-0004
data_construction (P-08), C-0011 treatment_definition (P-11), C-0008
interpretation (P-13, exact), C-0010/C-0021/C-0014/C-0003 data_construction
(P-14/P-20/P-19/P-15, all accepted). One defensible-adjacent coding, noted, not
a failure: E-0012 typed missing_input_or_output where the key nominally says
stale_or_wrong_path (P-06 — same mechanism, the figure script reads a
nonexistent `panel_v2.csv`; same adjacency accepted in the sc01 gate run).

**expected_confirmed_examples cleanliness: PASS.**
- "N = 4,832 matches the artifact": C-0005 ("a balanced panel of 4,832
  household-year observations" vs `artifacts/tab1.tex:9`) closed `confirmed`,
  no spurious flag; C-0006 (2,416 households) also confirmed. (C-0141 flags the
  separate "balanced" descriptor against the shipped unbalanced data — a
  distinct mechanism, not penalized under the key's beyond-must_find rule.)
- README per-object mapping: no readme_or_package_mismatch row touches the
  Table 1 → analysis.do or Figure 1 → make_figures.py mapping rows. The README
  rows present (E-0051 rainfall_stations, E-0231 pip install, E-0232 1-in-20
  vs one-in-ten, E-0233/E-0234 data blanks/unbalance, E-0235 radius filename,
  E-0237 income_check.csv omitted from the mapping table) are all different
  mechanisms.

## 8. Verdict

| Check | Result |
| --- | --- |
| Scorer exit | 1 → **mechanically RED** |
| Recall | **21/21** (first perfect run; P-21 included) |
| Precision | D-01 clean; D-02 mechanical flag **overturned on hand review** (scorer-matcher false positive on the P-15 row) |
| SC-01 | PASS — Layer 1, second consecutive run |
| Artifact layer U2/U4/U5 | PASS (settled — single-re-score layer) |
| Legacy P-01..P-20 | all HIT — no regression |
| P-21 worker evidence | PASS — quoted producer-vs-consumer reasoning in E-0001 |
| Type adjudication (hand) | PASS |
| Confirmed-examples cleanliness (hand) | PASS |
| **Gate verdict (hand-adjudicated)** | **GREEN** — the run itself has no recall or precision failure; the only RED ground is a defect in the scorer's D-02 matcher, not in the audit output |

## 9. Anomalies

1. **D-02 matcher defect (harness, not run):** the site-AND-qualifier match in
   `scripts/score_fixture.py` trips on the P-15 recovery row whenever it quotes
   the in-file "deliberately a subset of the four income components" signpost
   comment as evidence — site terms ("farm share") and qualifier terms
   ("omit"/"remittance"/"subset") then co-occur in a row that makes no
   farm_components complaint at all. E-0009 is simultaneously credited as the
   P-15 HIT and condemned as the D-02 trip. Needs an owner decision and a
   matcher fix (e.g. exclude rows whose location anchors L12-14 / the total
   list, or require the omission qualifier to attach to the farm_components
   site) plus a pinning harness test. Scorer and key left untouched by this
   scoring session.
2. **C-0171 at confirmation_needed** (P-02/P-03 escalated-mapped row): properly
   adjudicated in the cross-link summary (contradiction fails the visibility
   test); the inconsistent primary rows carry the recall. No action.
3. Bonus findings beyond the key (E-0236 consent-adequacy PII, E-0234
   unbalanced-data disclosure, E-0237 mapping-table omission) are true
   positives under hand review — precision beyond the decoys looks healthy.

Per the two-run protocol this is RUN 1 for the worker-dependent register layer;
a second consecutive green re-score is required before merge unless the owner
records a waiver. The artifact-layer results above are settled by this single
run. The honest external test remains the fourth Floods run.

## Addendum — mechanical GREEN after D-02 matcher fix (same day)

The hand-adjudicated D-02 overturn above was diagnosed as a scorer matcher
defect (site-AND-qualifier co-occurrence matched a P-15 recovery row quoting
the signpost comment as evidence). Fixed in commit `05b54ff` (sentence-level
co-occurrence plus an exculpation-vocabulary override; two new tests, harness
146 green). Re-scored mechanically after the fix:

- This run: **Recall 21/21, D-01/D-02 ABSENT, SC-01 PASS, all artifact checks
  PASS/INFO, GATE GREEN, exit 0** — the hand adjudication is now the
  mechanical verdict.
- Regression check on the pre-P-21 blind run (`rca-sc01-rescore/run1`):
  unchanged (20/21, P-21 the only MISS, D-02 ABSENT as before).

Run 1 of the two-run worker-dependent gate therefore stands GREEN.
