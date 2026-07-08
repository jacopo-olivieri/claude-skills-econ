# Fixture score — 2026-07-07 — v3 re-score, run 1

- Audit dir scored: `~/scratch/rca-fixture-rescore/pkg/audit`
- Answer key: `fixture/expected_findings.json` (scorer default)
- Scorer: `scripts/score_fixture.py`, exit code **1 → GATE RED**

## Evaluation-protocol framing (KTD-8)

Per KTD-8 (fixture/README.md, "Evaluation protocol"), the artifact-layer outcomes
(U2 / U4 / U5) are **single-re-score settling**, while the worker-dependent
register outcomes (U1's grep recovery, the U3/U8 reading recoveries, and recall)
need **two consecutive green re-scores**. This is **RUN 1 OF 2** for the
worker-dependent layer. **Do not merge on this run alone.**

## Provenance caveat: reconstructed audit dir

Per `audit/REBUILD_NOTE.md` in the scored directory, the original pipeline output
(completed ~21:13) was deleted when an external process reset the whole `pkg/`
tree at ~21:31. The scored `audit/` was reconstructed deterministically (b8
rewriter's `transform.py` over the b7-final register backups; non-LLM re-exports
for the workbook and run artifacts; no findings re-derived by an LLM). The
reconstruction did **not** regenerate `_run/manifest_check.md`, which is the
direct cause of the U2 FAIL below.

## Full scorer output

```
Fixture score — audit dir: /Users/jacopoolivieri/scratch/rca-fixture-rescore/pkg/audit
Answer key: /Users/jacopoolivieri/Documents/08_dev/02_repos/claude-skills-econ/skills/research-codebase-audit/fixture/expected_findings.json

P-01: HIT — C-0001 (claims, status=inconsistent, sev=4); C-0061 (claims, status=inconsistent, sev=3)
P-02: HIT — C-0019 (claims, status=inconsistent, sev=3); E-0005 (errors, status=confirmed, sev=3)
P-03: HIT — C-0018 (claims, status=inconsistent, sev=3); E-0171 (errors, status=confirmed, sev=3)
P-04: HIT — E-0006 (errors, status=confirmed, sev=2)
P-05: HIT — C-0006 (claims, status=inconsistent, sev=4); E-0001 (errors, status=confirmed, sev=4)
P-06: HIT — C-0065 (claims, status=inconsistent, sev=2); E-0007 (errors, status=confirmed, sev=2)
P-07: HIT — C-0016 (claims, status=inconsistent, sev=3); C-0063 (claims, status=inconsistent, sev=3); E-0004 (errors, status=confirmed, sev=3); E-0171 (errors, status=confirmed, sev=3)
P-08: HIT — E-0002 (errors, status=confirmed, sev=3); E-0191 (errors, status=confirmed, sev=3)
P-09: HIT — E-0052 (errors, status=confirmed, sev=2)
P-10: HIT — E-0057 (errors, status=confirmed, sev=3); E-0232 (errors, status=confirmed, sev=2)
P-11: HIT — C-0015 (claims, status=inconsistent, sev=3); E-0151 (errors, status=confirmed, sev=3); E-0152 (errors, status=confirmed, sev=2)
P-12: HIT — C-0065 (claims, status=inconsistent, sev=2); E-0008 (errors, status=confirmed, sev=3)
P-13: HIT — C-0009 (claims, status=inconsistent, sev=2)
P-14: HIT — C-0011 (claims, status=inconsistent, sev=2)
P-15: HIT [class=enumerated_member_list] — C-0005 (claims, status=inconsistent, sev=2); E-0009 (errors, status=confirmed, sev=2); E-0211 (errors, status=confirmed, sev=2); E-0232 (errors, status=confirmed, sev=2)
P-16: HIT [class=manifest_parseability] — E-0051 (errors, status=confirmed, sev=2); E-0231 (errors, status=confirmed, sev=2)
P-17: HIT [class=empirical_verification] — E-0003 (errors, status=confirmed, sev=2)
P-18: HIT [class=empirical_verification] — E-0010 (errors, status=confirmed, sev=2)
P-19: HIT [class=identifier_anchoring] — C-0020 (claims, status=inconsistent, sev=2); C-0161 (claims, status=inconsistent, sev=3); E-0211 (errors, status=confirmed, sev=2)
P-20: HIT [class=step_parameter_filename] — C-0070 (claims, status=inconsistent, sev=2)

D-01 decoy: ABSENT
D-02 decoy: ABSENT
SC-01: FAIL — confirmed shock-definition claim coexists with the confirmed P-11 error: C-0014 (claims, status=confirmed, sev=-); E-0151 (errors, status=confirmed, sev=3); E-0152 (errors, status=confirmed, sev=2)

Artifact-layer checks (single-re-score layer; record separately from the register-based two-run results):
U2 manifest artifact: FAIL — artifact not found: /Users/jacopoolivieri/scratch/rca-fixture-rescore/pkg/audit/_run/manifest_check.md (run check_manifests.py at b4)
U4 anchoring advisory: PASS — vacuous — P-19 claim not confirmed (closed inconsistent/inconsistent)
U5 filename-parameter advisory: PASS — vacuous — P-20 row not blocked (closed inconsistent)
U1 conventions artifact: INFO — enumerated_member_list convention PRESENT; P-15 mechanism row present (C-0005 (claims, status=inconsistent, sev=2)) (worker-dependent — informative, not gate-settling)

Recall: 20/20
Per-class:
  empirical_verification: 2/2 hit, 0 miss
  enumerated_member_list: 1/1 hit, 0 miss
  identifier_anchoring: 1/1 hit, 0 miss
  manifest_parseability: 1/1 hit, 0 miss
  step_parameter_filename: 1/1 hit, 0 miss
  unclassified_legacy: 14/14 hit, 0 miss
GATE RED — SC-01 unresolved status conflict; U2 manifest artifact check failed
```

## Plain-language reading

### Gate

**GATE RED** (exit 1). Two independent failures: the SC-01 status conflict and
the missing U2 manifest artifact. Everything else — recall, decoys, U4/U5, U1 —
is clean.

### Recall

**20/20** must-find plants recovered, every one at or above its `min_severity`.
The aggregate equals the per-class sum: 2 (empirical_verification) + 1
(enumerated_member_list) + 1 (identifier_anchoring) + 1 (manifest_parseability)
+ 1 (step_parameter_filename) + 14 (unclassified_legacy, P-01..P-14) = 20.
**No failure class regressed** — every class is at full recovery, including the
five new-mechanism classes P-15..P-20.

### Artifact layer (single-re-score settling per KTD-8)

- **U2: FAIL.** `audit/_run/manifest_check.md` does not exist, so the scorer
  cannot verify that `check_manifests.py` named `pyproject.toml`. Per the
  rebuild note this artifact was simply not regenerated after the external
  wipe of `pkg/` — the P-16 register rows (E-0051 confirmed sev 2, plus the
  E-0231 twin, with the E-0301 `duplicate_of:E-0051` tombstone) show the b4
  fold-in minted and confirmed the manifest candidate in the original run, but
  the artifact itself cannot be inspected. As scored, U2 is RED; whether the
  original run produced the artifact is unverifiable from what survives.
- **U4: PASS (vacuous).** The P-19 winsorisation claim closed `inconsistent`
  (both C-0020 and C-0161), so the anchoring advisory had nothing to warn on —
  the correct outcome, since the whole point of P-19 is that the claim must not
  close confirmed.
- **U5: PASS (vacuous).** The P-20 row (C-0070) closed `inconsistent` at sev 2
  — the preferred branch of the dual-accept — so the blocked-row advisory had
  nothing to fire on.
- **U1: INFO only** (never gate-settling). The conventions artifact records the
  `enumerated_member_list` convention and the P-15 mechanism row (C-0005) is
  present in the register.

### Precision (decoys)

Both decoys **ABSENT** from every register, as required. Independent grep of
the final claims and code-error registers finds zero mentions of
`fig_placebo`/placebo (D-01) and zero of `farm_components`/farm share (D-02).

### SC-01: FAIL (real, and worker-behavioral, not a scorer artifact)

The claims review split the shock-definition sentence into two rows: C-0015
("the 1991–2020 climate normal") closed `inconsistent` sev 3, but **C-0014**
("standardised deviation of wave rainfall from the village's long-run
historical mean") closed **confirmed**, citing the very `do/build_panel.do:21-23`
lines that E-0151 (confirmed sev 3) flags as a two-wave in-sample mean. The b7
cross-linker surfaced and resolved the other two status conflicts
(C-0062↔E-0005/E-0171, C-0075↔E-0053) but never linked C-0014 to E-0151 — its
documented judgment call only weighed E-0151 against C-0015 ("distinct
mechanisms") and missed the confirmed C-0014 sitting on the same code lines. So
condition (a) confirmed long-run-mean claim + condition (b) confirmed P-11
error held, the conflict was never listed under "## Status conflicts", and the
claim rests confirmed → SC-01 fails on its own terms. P-11 recall passes
regardless (carried by C-0015/E-0151).

## Hand-scored items (not covered by the automated scorer)

### Type adjudication

Every recovered plant carries a plausible `expected_type` (dual-accept branches
checked against the key):

| Plant | Register row(s) and type | Verdict |
| --- | --- | --- |
| P-01 | C-0001, C-0061 `transcription` | match |
| P-02 | C-0019 `estimation_specification` (accepted claim equivalent); E-0005 `inference_or_se_specification` | match |
| P-03 | C-0018 `estimation_specification`; E-0171 `weighting_error` | match |
| P-04 | E-0006 `randomness_or_seed_error` | match |
| P-05 | C-0006 `sample_count` (accepted); E-0001 `sample_filter_or_flag_error` | match |
| P-06 | E-0007 `stale_or_wrong_path` | match |
| P-07 | E-0004 `undefined_variable_or_global` | match |
| P-08 | E-0002 `aggregation_or_unit_error` (E-0191 same type, figure-axis twin) | match |
| P-09 | E-0052 `readme_or_package_mismatch` | match |
| P-10 | E-0057, E-0232 `pii_or_disclosure_risk` | match |
| P-11 | C-0015 `treatment_definition` (claim equivalent of `treatment_or_event_timing_error`); E-0151 `aggregation_or_unit_error` (explicitly dual-accepted) | match |
| P-12 | E-0008 `output_label_or_path_mismatch` | match |
| P-13 | C-0009 `sample_count` | **divergence — see note 1** |
| P-14 | C-0011 `data_construction`, inconsistent sev 2 (preferred branch) | match |
| P-15 | C-0005 `data_construction` (accepted); E-0009 `aggregation_or_unit_error` | match |
| P-16 | E-0051, E-0231 `version_or_dependency_error` | match |
| P-17 | E-0003 `sample_filter_or_flag_error` | match |
| P-18 | E-0010 `sample_filter_or_flag_error` | match |
| P-19 | C-0020, C-0161 `data_construction` (accepted); E-0211 `aggregation_or_unit_error` (code-side accepted) | match |
| P-20 | C-0070 `data_construction`, inconsistent sev 2 (preferred branch) | match |

**Note 1 (P-13 type):** the key accepts `interpretation` (or
`rounding_or_precision` / `quantitative_result`); C-0009 is typed
`sample_count`. The mechanism match is exact (725/2,416 = 30%, not 25%,
recomputed in the row) and `sample_count` is a defensible reading of a
sample-share arithmetic slip, but it is strictly outside the key's listed
accepted types. Non-gating; recorded as the run's only type divergence.

**Note 2 (E-0152 attribution):** the scorer counts E-0152 among the P-11 hits,
but its mechanism is the adjacent missing-comparison hazard on the `shocked`
flag (`. < 0` false under Stata's missing-is-largest rule), not the wrong
baseline itself. P-11 recall properly rests on C-0015 and E-0151, so nothing
turns on this; noted for the record.

### expected_confirmed_examples cleanliness

Both clean:

1. **N = 4,832 transcription check:** C-0007 closed `confirmed` — the prose
   count matches the shipped Table 1. The row carries a sev-1 contingency note
   (the count is not independently reproducible because of the P-05 reversed
   filter), which is a caveat, not a spurious flag.
2. **README per-object script mapping:** the register's four
   `readme_or_package_mismatch` rows are E-0052 (P-09, expected), E-0053
   (village file never merged), E-0054 (subsample-rate mismatch, P-14-adjacent),
   and E-0233 (no LICENSE / data-availability statement). None flags the
   Table 1 → analysis.do or Figure 1 → make_figures.py mapping rows themselves.

## Verdict for the record

- **GATE RED** on this run: SC-01 (worker-behavioral: claim-splitting left
  C-0014 confirmed and the cross-linker missed the pair) and U2 (artifact
  missing, attributable to the external `pkg/` wipe + reconstruction gap, not
  to worker behavior).
- **Recall layer: green, 20/20, no per-class regression** — but per KTD-8 this
  is run 1 of the 2 consecutive green re-scores that layer requires.
- Not mergeable on this run: the gate is RED, and even the green
  worker-dependent layer needs a second consecutive green run.
