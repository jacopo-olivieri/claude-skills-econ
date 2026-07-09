# Fixture score — 2026-07-08 — definition/use-contract (defuse) gate re-score, RUN 2

- Audit dir: `~/scratch/rca-defuse-rescore/run2/pkg/audit`
- Answer key: `fixture/expected_findings.json` (scorer default; 21 must_find incl. P-21)
- Blind audit produced: 2026-07-08 (workers ran without the answer key; audit frozen on disk)
- Scored: 2026-07-09 (resumed session; scoring the frozen artifact preserves blindness)
- Scorer exit code: **0 → GATE GREEN** (after the D-02 matcher narrowing recorded in §3 / §9)
- Branch under test: `fix/rca-defuse-contract-recall` (reworded standing check 2, definition/use contract)

## Scope note (read first)

This is **RUN 2** of the two-consecutive-green worker-dependent gate for the
reworded standing check 2 (`fixture/README.md`, Evaluation protocol). Run 1
(`score-2026-07-08-defuse-gate-run1.md`) was GREEN 21/21. This run is an
independent blind end-to-end audit of a second package copy; the two runs share
no worker state. As in run 1, this validates that the reworded check **can fire
on the plant** (P-21), not that it fires on real packages — the honest external
test remains the next Floods run. Artifact-layer outcomes (U2/U4/U5) settled on
run 1's single re-score; they are re-confirmed here for completeness.

## 1. Full scorer output

```
P-01: HIT — C-0001 (claims, inconsistent, sev=4); C-0061 (claims, inconsistent, sev=4)
P-02: HIT — C-0016 (claims, inconsistent, sev=4); C-0062 (claims, confirmation_needed, sev=4); E-0005 (errors, confirmed, sev=4)
P-03: HIT — C-0015 (claims, inconsistent, sev=3); E-0006 (errors, confirmed, sev=3)
P-04: HIT — E-0007 (errors, confirmed, sev=2); E-0241 (errors, confirmed, sev=2)
P-05: HIT — C-0006 (claims, inconsistent, sev=4); E-0002 (errors, confirmed, sev=4)
P-06: HIT — C-0065 (claims, inconsistent, sev=2); E-0010 (errors, confirmed, sev=2); E-0053 (errors, confirmed, sev=2)
P-07: HIT — C-0014/C-0015 (claims, inconsistent, sev=3); C-0062 (confirmation_needed, sev=4); C-0064 (inconsistent, sev=3); E-0004 (errors, confirmed, sev=3)
P-08: HIT — C-0004 (claims, inconsistent, sev=3); E-0003 (errors, confirmed, sev=3); E-0320 (errors, confirmed, sev=3)
P-09: HIT — E-0051 (errors, confirmed, sev=2); E-0360 (errors, confirmed, sev=2)
P-10: HIT — E-0057 (errors, confirmed, sev=2); E-0281 (errors, confirmed, sev=2)
P-11: HIT — C-0009/C-0013/C-0201 (claims, inconsistent, sev=3); E-0450 (errors, confirmed, sev=3)
P-12: HIT — C-0066 (claims, inconsistent, sev=3); C-0251 (claims, inconsistent, sev=1); E-0011 (errors, confirmed, sev=3)
P-13: HIT — C-0009 (claims, inconsistent, sev=3)
P-14: HIT — C-0010 (claims, inconsistent, sev=2)
P-15: HIT [enumerated_member_list] — C-0005 (claims, inconsistent, sev=2); E-0008 (errors, confirmed, sev=2)
P-16: HIT [manifest_parseability] — E-0054 (errors, confirmed, sev=2)
P-17: HIT [empirical_verification] — E-0200 (errors, confirmed, sev=2); E-0400 (errors, confirmed, sev=2)
P-18: HIT [empirical_verification] — E-0009 (errors, confirmed, sev=2); E-0284 (errors, confirmed, sev=1)
P-19: HIT [identifier_anchoring] — C-0017/C-0202 (claims, inconsistent, sev=3); E-0008 (errors, confirmed, sev=2)
P-20: HIT [step_parameter_filename] — C-0072 (claims, inconsistent, sev=3); E-0360 (errors, confirmed, sev=2)
P-21: HIT [definition_use_contract] — C-0006 (inconsistent, sev=4); C-0200 (inconsistent, sev=3); E-0001 (confirmed, sev=3); E-0057 (confirmed, sev=2)

D-01 decoy: ABSENT
D-02 decoy: ABSENT
SC-01: PASS

U2 manifest artifact: PASS — _run/manifest_check.md names pyproject.toml
U4 anchoring advisory: PASS — vacuous — P-19 claim closed inconsistent
U5 filename-parameter advisory: PASS — vacuous — P-20 row not blocked
U1 conventions artifact: INFO — enumerated_member_list convention PRESENT; P-15 mechanism row present

Recall: 21/21
Per-class: definition_use_contract 1/1, empirical_verification 2/2,
  enumerated_member_list 1/1, identifier_anchoring 1/1, manifest_parseability 1/1,
  step_parameter_filename 1/1, unclassified_legacy 14/14
GATE GREEN
```

## 2. Aggregate recall and per-class breakdown

**Recall: 21/21** — second consecutive perfect run on the expanded key. Per-class
reconciles with the aggregate (1+2+1+1+1+1+14 = 21). Independent of run 1: this
package copy was audited by separate workers, and the ID assignments differ
(e.g. the P-21 code row is E-0001 in both runs but the surrounding numbering
diverges), confirming the two greens are two draws, not one artifact scored twice.

## 3. Precision / decoys

- **D-01 (placebo figure): ABSENT — PASS.** No register row mentions the placebo
  figure or `fig_placebo.pdf`.
- **D-02 (farm_components subset): ABSENT — PASS** (after the matcher narrowing
  in §9). The pre-fix scorer flagged **E-0283** as a D-02 trip; hand review found
  this a matcher false positive, now also the mechanical verdict. E-0283 is a
  severity-1 finding that the `farm_share` ratio at `py/build_income.py:31-32`
  divides a component-sum numerator by the survey-total `income` denominator
  (different bases) with no zero-guard (`inf` on `income == 0`). It **accepts**
  the subset framing ("the comment frames `farm_share` as the farm subset's
  share") and makes **no** complaint that `farm_components` omits or diverges from
  the four-component list — it is exactly the "true zero-income division guard
  observation … scored on its own merits" the D-02 spec names as non-tripping.
  The trip came solely from the qualifier term `"subset"` matching the
  descriptive noun phrase "the farm **subset's** share". `"subset"` is the
  signpost comment's own descriptive word, not the omission grievance; it is
  dropped from the qualifier set (§9). No genuine bait is weakened — every
  bait phrasing carries `omit`/`diverg`/`incomplete`/`excludes`/`remittance`/
  `four-component` (all four D-02 tests still pass, and the fix ships with a new
  pinning test built from E-0283's shape).
- No other decoy-adjacent findings.

## 4. SC-01 status-conflict check

**PASS.** `register_cross_link_summary.md` "## Status conflicts" records that the
P-02/P-03 significance claim C-0062 was moved to `confirmation_needed` (severity
4) after a targeted post-b7 recheck — escalation to `inconsistent` failed the
visibility test — and states "No confirmed-claim ↔ confirmed-error link
survives". No claims-register row asserting the long-run 1991–2020 shock
definition is `confirmed`. The 2026-07-07 regression shape (SC-01 failing while
recall stays green) did not recur. Third consecutive run with SC-01 resolved.

## 5. Named legacy regression watch (mandatory list)

| Item | Result | Notes |
| --- | --- | --- |
| P-01 | HIT | C-0001 inconsistent sev 4 |
| P-02 | HIT | E-0005 confirmed sev 4 + claim rows |
| P-03 | HIT | E-0006 confirmed sev 3 |
| P-04 | HIT | E-0007 confirmed sev 2 |
| P-05 | HIT | C-0006 sev 4 / E-0002 sev 4 |
| P-06 | HIT | E-0010/E-0053 confirmed sev 2 |
| P-07 | HIT | E-0004 confirmed sev 3 |
| P-08 | HIT | E-0003 confirmed sev 3 |
| P-09 | HIT | E-0051 confirmed sev 2 |
| P-10 | HIT | E-0057 confirmed sev 2 (PII) |
| P-11 | HIT | C-0201 inconsistent sev 3; E-0450 confirmed sev 3 |
| P-12 | HIT | E-0011 confirmed sev 3 (second-read sweep held) |
| P-13 | HIT | C-0009 inconsistent sev 3 (arithmetic recompute held) |
| P-14 | HIT | C-0010 inconsistent sev 2 (preferred branch) |
| P-15 | HIT | C-0005 / E-0008 sev 2 |
| P-16 | HIT | E-0054 sev 2 |
| P-17 | HIT | E-0200 confirmed sev 2 |
| P-18 | HIT | E-0009 confirmed sev 2 |
| P-19 | HIT | C-0017 inconsistent sev 3; not confirmed (anchoring held) |
| P-20 | HIT | C-0072 inconsistent sev 3 (preferred branch) |
| SC-01 | PASS | vacuous conflict rule; no 2026-07-07 shape |
| D-01 | PASS | absent |
| D-02 | PASS | absent (matcher narrowed — §9) |
| U2 manifest artifact | PASS | names `pyproject.toml` |
| U4 anchoring advisory | PASS | vacuous — P-19 closed inconsistent |
| U5 filename advisory | PASS | vacuous — P-20 not blocked |
| U1 conventions artifact | INFO | convention present, P-15 row present |

No legacy regression. Instruction growth from the reworded standing check 2 did
not cost any prior plant in either gate run.

## 6. P-21 worker evidence (required for the gate, beyond the mechanical hit)

The reworded check **demonstrably drove** the recovery, independently of run 1.
Code-side row **E-0001** (`sample_filter_or_flag_error`, `do/build_panel.do:11-18`,
confirmed, severity 3):

> "The producer defines `consent_ok = (consent == "individual") | (consent ==
> "community")` with a comment stating both consent routes are cleared for
> release, but the sole consumer narrows the set: `keep if consent_ok == 1 &
> consent == "individual"` drops all community-consent households despite
> `consent_ok == 1`. **No companion consumer covers the excluded cases and no
> independent eligibility restriction is stated.** Retyped synthetic Stata probe
> (3 rows) confirmed the community row is deleted while carrying
> `consent_ok == 1`."

The bolded sentence is the reworded check's escape-clause test applied verbatim
(an extra consumer predicate is acceptable only when independently defined
eligibility or a companion consumer covers the excluded cases — neither holds).
Materiality is traced to an on-path output ("3 of 14 rows … changing N and all
downstream estimates in `do/analysis.do` (Table 1)"), clearing the severity-2
floor at severity 3. The claims-side row **C-0200** carries the same
producer-vs-consumer comparison against the paper's undisclosed-restriction
angle. **P-21 worker-evidence check: PASS.**

That two blind runs both recovered P-21 with the producer-set-vs-consumer-predicate
reasoning — not a keyword or a surface pattern — is the evidence the two-run gate
exists to produce.

## 7. Hand-scored items

**Type adjudication: PASS.** P-21 code row E-0001 is the exact expected type
(`sample_filter_or_flag_error`); C-0200 is the accepted claim-side
`data_construction`. Legacy code/claim types match by mechanism as in run 1
(spot-checked: E-0005 inference/SE P-02; E-0006 weighting P-03; E-0002
sample/count P-05; E-0450 aggregation P-11; E-0008 aggregation P-15/P-19 shared
row). Accepted adjacencies unchanged from run 1.

**expected_confirmed_examples cleanliness: PASS.** No spurious flag on the
N = 4,832 artifact match or the README per-object mapping rows; the README rows
present are distinct mechanisms, not the protected mappings.

## 8. Verdict

| Check | Result |
| --- | --- |
| Scorer exit | 0 → **GATE GREEN** |
| Recall | **21/21** (second consecutive perfect run; P-21 included) |
| Precision | D-01 clean; D-02 clean (matcher narrowed — see §9) |
| SC-01 | PASS — no unresolved conflict, third consecutive run |
| Artifact layer U2/U4/U5 | PASS |
| Legacy P-01..P-20 | all HIT — no regression |
| P-21 worker evidence | PASS — producer-vs-consumer reasoning in E-0001, independent of run 1 |
| Type adjudication (hand) | PASS |
| Confirmed-examples cleanliness (hand) | PASS |
| **Gate verdict** | **GREEN** |

**Two-run worker-dependent gate: run 1 GREEN + run 2 GREEN = PASS.** The reworded
standing check 2 is validated at the fixture layer under the two-consecutive-green
protocol, with no legacy regression across both runs.

## 9. D-02 matcher narrowing (harness, 2026-07-09)

The pre-fix scorer flagged E-0283 (§3) because the D-02 qualifier list contained
bare `"subset"`, which matched the descriptive noun phrase "the farm subset's
share". `"subset"` is the signpost comment's own word for the block's intentional
nature — it is not the omission grievance the decoy targets. Fix: drop `"subset"`
from `DECOYS["D-02"]` qualifier terms in `scripts/score_fixture.py`; the grievance
is carried by `omit`/`diverg`/`four-component`/`four income`/`remittance`/
`incomplete`/`excludes`/`missing component`. Verified:

- All four pre-existing D-02 tests pass unchanged — the two positive-bait tests
  trip on `diverging`/`four-component`/`omits`/`remittance`; the two negatives
  stay absent.
- New pinning test `test_descriptive_subset_noun_in_ratio_finding_is_not_decoy`
  reproduces E-0283's shape (a ratio-basis finding that names "the farm subset's
  share" while flagging an unrelated denominator defect) and asserts ABSENT.
- Full harness: **147 passed**.
- Regression re-score: run 1 unchanged (GREEN 21/21, D-02 ABSENT); pre-P-21
  baseline (`rca-sc01-rescore/run1`) unchanged (20/21, P-21 the only MISS, D-02
  ABSENT).

This is the second D-02 matcher narrowing on this branch (the first, commit
`05b54ff`, added sentence-level co-occurrence and the exculpation override). Both
narrow the same over-broad direction — the decoy trips only on a genuine
"the list is incomplete" grievance, never on a legitimate finding that merely
names or quotes the signposted block. The planted bait itself is unchanged and
still trips (positive tests).

## 10. Decision record — dedicated bundle-review worker pass (R7)

Applying the pre-registered thresholds (plan Key Technical Decisions) to U3's
measurement (`measurement-2026-07-08-defuse-emitter.md`): the emitter yields
**10 bundles** on the real Floods package (well under the build threshold of 50)
**and both known-positive flood-fill controls are emitted**
(`make_sales_weighted_outcomes.do` and `build_supplier_flood_status.do`).

**Decision: BUILD** the dedicated definition/use bundle-review worker pass. Both
build conditions are met (≤ 50 bundles AND control emitted); no narrowing branch
is needed. Per the plan's Scope Boundaries, building the pass (the emitter as a
committed script with symlink guards, its stage wiring, a worker prompt, and its
own fixture validation) is follow-up work with its own plan — out of scope here.
The rewording (U1) and plant (U2) validated in this gate stand on their own as a
recall improvement regardless of the emitter follow-up.
