# Fixture score — 2026-07-09 — worker-contract rewiring gate re-score, RUN 1

- Audit dir: `~/scratch/rca-contract-rescore-run1-pkg/audit`
- Answer key: `fixture/expected_findings.json` (scorer default; 21 must_find incl. P-21)
- Blind audit produced: 2026-07-09 (fresh session in the package copy; workers ran without the
  answer key)
- Scored: 2026-07-09
- Scorer exit code: **0 → GATE GREEN**
- Branch under test: `refactor/worker-contract-token-efficiency` — workers read generated
  per-role contracts (`audit/_run/contracts/<role>.md`) instead of the full
  `audit/audit_readme.md`; contracts assembled deterministically by
  `scripts/build_worker_contracts.py` from `references/registers.md`.

## Scope note (read first)

This is the **single-green gate** for the contract rewiring, per the plan decision recorded in
`docs/plans/2026-07-09-001-refactor-worker-contracts-token-efficiency-plan.md` (gate weakened
from the two-consecutive-green protocol to one green run, with escalation to a second run on
any near-miss). The near-miss inspection (§4) found none, so this single run settles the gate.
This validates that every planted mechanism still fires with workers on role contracts; the
honest external test remains the next Floods run.

## 1. Full scorer output

```
P-01: HIT — C-0001 (claims, inconsistent, sev=3); C-0019 (claims, inconsistent, sev=3)
P-02: HIT — C-0017 (claims, inconsistent, sev=4); C-0020 (claims, confirmation_needed, sev=4); C-0023 (claims, confirmation_needed, sev=4); E-0105 (errors, confirmed, sev=4)
P-03: HIT — C-0016 (claims, inconsistent, sev=3); E-0106 (errors, confirmed, sev=3); E-0300 (errors, confirmed, sev=3)
P-04: HIT — E-0107 (errors, confirmed, sev=2)
P-05: HIT — C-0005 (claims, inconsistent, sev=4); E-0103 (errors, confirmed, sev=4)
P-06: HIT — E-0110 (errors, confirmed, sev=2)
P-07: HIT — C-0015 (claims, inconsistent, sev=3); E-0104 (errors, confirmed, sev=3); E-0105 (errors, confirmed, sev=4); E-0106 (errors, confirmed, sev=3)
P-08: HIT — E-0102 (errors, confirmed, sev=3)
P-09: HIT — E-0203 (errors, confirmed, sev=2)
P-10: HIT — E-0205 (errors, confirmed, sev=3)
P-11: HIT — C-0013 (claims, inconsistent, sev=4); E-0300 (errors, confirmed, sev=3); E-0301 (errors, confirmed, sev=2)
P-12: HIT — C-0102 (claims, inconsistent, sev=2); E-0111 (errors, confirmed, sev=3)
P-13: HIT — C-0008 (claims, inconsistent, sev=3)
P-14: HIT — C-0010 (claims, inconsistent, sev=2)
P-15: HIT [enumerated_member_list] — C-0004 (claims, inconsistent, sev=2); E-0108 (errors, confirmed, sev=2)
P-16: HIT [manifest_parseability] — E-0200 (errors, confirmed, sev=2); E-0201 (errors, confirmed, sev=2); E-0202 (errors, confirmed, sev=2)
P-17: HIT [empirical_verification] — E-0101 (errors, confirmed, sev=2); E-0503 (errors, confirmed, sev=2)
P-18: HIT [empirical_verification] — E-0109 (errors, confirmed, sev=2)
P-19: HIT [identifier_anchoring] — C-0018 (claims, inconsistent, sev=2); E-0400 (errors, confirmed, sev=2)
P-20: HIT [step_parameter_filename] — C-0026 (claims, inconsistent, sev=2)
P-21: HIT [definition_use_contract] — E-0100 (errors, confirmed, sev=3)

D-01 decoy: ABSENT
D-02 decoy: ABSENT
SC-01: PASS

Artifact-layer checks:
U2 manifest artifact: PASS — _run/manifest_check.md names pyproject.toml
U4 anchoring advisory: PASS — vacuous — P-19 claim not confirmed (closed inconsistent)
U5 filename-parameter advisory: PASS — vacuous — P-20 row not blocked (closed inconsistent)
U1 conventions artifact: INFO — enumerated_member_list convention PRESENT; P-15 mechanism row
present (C-0004) (worker-dependent — informative, not gate-settling)

Recall: 21/21
Per-class: definition_use_contract 1/1; empirical_verification 2/2; enumerated_member_list 1/1;
identifier_anchoring 1/1; manifest_parseability 1/1; step_parameter_filename 1/1;
unclassified_legacy 14/14
GATE GREEN
```

## 2. Hand-scored: expected_confirmed_examples — CLEAN

- "N = 4,832 in prose matches the artifact table": C-0006 closed `confirmed` with no flag,
  anchored to `artifacts/tab1.tex`. CLEAN.
- README per-object mapping (Table 1 → `analysis.do`, Figure 1 → `make_figures.py`): no
  `readme_or_package_mismatch` finding targets the mapping rows. The readme-adjacent findings
  (E-0202 install target, E-0451 docstring-vs-code, E-0500 esttab dependency, E-0402 output
  dir) are planted defects, distinct in location and mechanism. CLEAN.

## 3. Hand-scored: type adjudication — PASS

Spot-checked hit rows carry appropriate types: P-21 → `sample_filter_or_flag_error`; P-17 →
`sample_filter_or_flag_error` with runtime probe; P-08 → `aggregation_or_unit_error`; P-16 →
`syntax_or_parse_error` / `version_or_dependency_error` / `readme_or_package_mismatch` across
its three rows. No misfiled mechanism found.

## 4. Near-miss inspection — NONE FOUND (no escalation to a second run)

- P-21 (E-0100) recovered with the full required reasoning pattern: the evidence chain states
  the producer-defined eligible set {individual, community} against the consumer-effective
  predicate {individual} explicitly. Not a lucky-path recovery.
- P-17 (E-0101) recovered via a worker-retyped synthetic Stata probe — the empirical
  verification guardrail fired as designed under the contract context.
- Both decoys are fully ABSENT from all registers (clean refusals, not hedged rows).
- SC-01 and the artifact layer pass without qualification.

## 5. Verdict

GATE GREEN on a single blind run with no near-miss: the U3 contract-rewiring gate defined in
the 2026-07-09 plan is satisfied. The rewiring (workers on per-role contracts) preserved
21/21 recall including the definition/use-contract plant, both precision decoys, the
status-conflict discipline, and the artifact layer.
