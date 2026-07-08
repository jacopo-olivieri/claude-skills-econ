# Measurement — definition/use contract bundle emitter (U3, R6)

**Date:** 2026-07-08
**Plan:** `2026-07-08-001-fix-definition-use-contract-recall-plan.md`, Implementation Unit U3.
**Instrument:** scratch prototype (uncommitted, per Key Technical Decisions).
Prototype path:
`/private/tmp/claude-501/-Users-jacopoolivieri-Documents-08-dev-02-repos-claude-skills-econ/d2c49d52-7b03-4358-af0d-b0e2065a1f85/scratchpad/defuse_emitter.py`

**Input package:** `/Users/jacopoolivieri/scratch/floods-rca-run4/package` (pristine
Floods run-4 copy). 55 `.do` files scanned under `do/`.

**Excluded from scan:** the in-package audit working directory `audit/` (173
files — `_run`, `_work`, `_staging`, `_code_errors`, `_recheck`, `plans`, etc.);
these are prior-run RCA outputs, not package source. No `.rca*` / `registers`
dirs were present outside `audit/`. Non-`.do` files (paper JPEGs, logs, `.def`,
requirements/dependency text) are not scanned by the rule.

---

## Headline result

- **Total bundles emitted: 6**
- **Known-positive control: BOTH sites emitted** (see below).
- Under the plan's pre-registered thresholds this is the **"build" region**
  (<= 50 bundles AND control emitted). No narrowing pass was required.

## Per-file distribution

| Count | File (repo-relative to package) |
|------:|----------------------------------|
| 2 | `do/data_building/construct_transactions.do` |
| 2 | `do/data_building/clean_industry_codes.do` |
| 1 | `do/data_building/build_supplier_flood_status.do` |
| 1 | `do/data_building/make_sales_weighted_outcomes.do` |

Four files carry bundles; all under `do/data_building/`. The 51 other scanned
`.do` files emitted nothing.

## Ten largest files' bundle counts

Only four files emit at all; the "ten largest" list is therefore the full
distribution above followed by zeros. Largest = 2 (`construct_transactions.do`,
`clean_industry_codes.do`); all remaining 51 `.do` files = 0.

## Known-positive control — explicit result

Both flood-fill `error_nonc` sites are emitted.

1. **`do/data_building/make_sales_weighted_outcomes.do`** — flag `error_nonc`,
   definition `gen error_nonc = 0` at **L512**; consumer at **L525**:
   `replace \`var' = max_flood_extent_\`buff'b if error_nonc == 1 & !mi(\`var')`.
   The `& !mi(\`var')` conjunct is exactly the set-narrowing the check targets.

2. **`do/data_building/build_supplier_flood_status.do`** — flag `error_nonc`,
   definition `gen error_nonc = 0` at **L355**; consumer at **L368**:
   `replace \`var' = max_flood_extent if error_nonc == 1 & \`var' != .`.

(The plan's "~525 / ~368" line references point to the consumer sites; the
`gen` definition sites are ~L512 / ~L355. Both def and consumer are captured in
each bundle.)

## Readable sample (all 6 bundles)

The package yielded only 6 bundles, so the full set is the sample.

### 1. `build_supplier_flood_status.do` — flag `error_nonc` (CONTROL)
- def L355: `gen error_nonc = 0`
- comment window (~L353–357): `* Indicate when reliance on the transaction panel would produce an erroneous flood extent value`
- consumer L368: `replace \`var' = max_flood_extent if error_nonc == 1 & \`var' != .`

### 2. `make_sales_weighted_outcomes.do` — flag `error_nonc` (CONTROL)
- def L512: `gen error_nonc = 0`
- comment window (~L510–514): `*Indicate when reliance on the transaction panel would produce an erroneous flood extent value`
- consumer L525: `replace \`var' = max_flood_extent_\`buff'b if error_nonc == 1 & !mi(\`var')`

### 3. `construct_transactions.do` — flag `reported`
- def L104: `gen reported = .`
- consumers:
  - L123: `replace flag_s_with_bs_duplicate = 1 if duplicate_exact_b==1 & max_reported=="B+S":reported & reported=="S":...`
  - L142: `replace flag_s_with_bs_duplicate = 1 if duplicate_exact_b==1 & max_reported=="B+S":reported & reported=="S":...`
  - L172: `drop if flag_s_firm == 1 & duplicate_b & reported == "S":reported & yearmonth<201411`
  - L185: `replace flag_bad = 1 if confirmed_transactions==0 & duplicate_b==1 & reported == "S":reported`

### 4. `construct_transactions.do` — flag `flag_s_firm`
- def L162: `gen flag_s_firm = .`
- consumer L172: `drop if flag_s_firm == 1 & duplicate_b & reported == "S":reported & yearmonth<201411`

### 5. `clean_industry_codes.do` — flag `pref_ind_code`
- def L318: `gen pref_ind_code=""`
- consumers (source-tagging cascade): L319, L324, L347, L349, L351, L463, L473,
  each `replace source = "...":source if pref_ind_code=="" & <extra>!=""`

### 6. `clean_industry_codes.do` — flag `psic6_from_name`
- def L356: `gen psic6_from_name = ""`
- consumer L463: `replace source = "5: PSIC from Name":source if pref_ind_code=="" & psic6_from_name!=""`

Quality note: bundles 5/6 are cascading `replace source = ...` fill-forward
tag assignments — genuine derived-flag/gated-consumer shape, plausibly worth a
worker glance but likely benign. Bundles 3/4 are `reported`/`flag_s_firm`
duplicate-resolution guards. All 6 are legible; none are noise from macro
false-positives. Value labels rendered as `"...":source` are Stata label
syntax, matched textually without issue.

## Exact emission rule as implemented

1. **Flag definition.** `gen`/`generate` (optionally `byte|int|long|float|double|str*`)
   `X = <constant>`, where the RHS before any `if`/comment is a numeric literal,
   `.`, or a quoted string — AND the same file later contains a
   `replace X = ... if ...` (the conditional set that makes `X` a derived flag
   rather than a plain constant column).
2. **Consumers.** Logical lines *after* the definition line that are
   data-mutating — `replace`, `drop`, `keep`, `merge`, `collapse`, or a weight
   application `[aw=/fw=/pw=/iw= ...]` — whose `if` condition (a) contains flag
   `X` as a whole token and (b) has **at least one extra conjunct** (>=2
   conjuncts when the condition is split on top-level `&`, one being the flag,
   at least one other). Statements whose `replace` target is `X` itself are
   excluded (they complete the flag definition, they do not consume it).
3. **Bundle.** Definition site (file, line, text) + comment lines within +/-5
   raw lines of the definition + each consumer's file/line and full
   continuation-joined condition.

### Tolerances / exclusions
- Scans `*.do` only; `audit/` excluded via `--exclude`.
- `///` line continuations joined; inline `/* */` and `//` comments stripped
  before condition matching.
- Extra-conjunct split is paren-depth-aware (`&` inside `(...)` not split on).
- Macro-heavy conditions matched textually; false negatives tolerated
  everywhere except the control. `#delimit ;` blocks are not specially handled
  (none affected the control or observed bundles).
- The load-bearing narrowing is the extra-conjunct requirement: a consumer
  gated by the flag alone (no additional conjunct) is not emitted, having no
  set-narrowing to audit.

## Secondary sanity input — fixture P-21

The fixture tree `skills/research-codebase-audit/fixture/planted/` exists but
**P-21 is not planted yet** (U2 has not landed). Running the emitter over it
yields **0 bundles**, and no `P-21` marker is present in `fixture/`. Re-run this
check after U2 to confirm the P-21 definition/use site is emitted.

## Rule-shape iteration

None required. The rule emitted both control sites on the first run with the
mechanical shape as specified in the plan; no shape bug was found or fixed.

## Addendum (post-U2): boolean-gen extension and re-measurement

After U2 planted P-21, the original rule emitted **0 fixture bundles**: P-21's
flag is defined in one boolean expression
(`gen consent_ok = (consent == "individual") | (consent == "community")`),
while the original rule required `gen X = <constant>` followed by a
`replace X = ... if ...`. The plan expected the P-21 site to be emitted, so the
prototype was extended with one additional producer shape: a `gen` whose RHS is
itself a condition (contains `==`, `!=`, `~=`, `<=`, `>=`, `inlist(`, or
`inrange(`) counts as a derived-flag definition directly, with no `replace`
required. The constant+replace path and the consumer rule (data-mutating
statement, flag token plus at least one extra top-level conjunct) are unchanged.

Re-measurement with the extended rule:

- **Fixture** `fixture/planted/`: **1 bundle** — the P-21 site
  (`do/build_panel.do`, flag `consent_ok`, def line 15 (logical), consumer
  line 18 (logical); raw lines 17/20). Secondary sanity check now passes.
- **Floods run-4 package** (same exclusions): **10 bundles** (was 6). The four
  new bundles are boolean-gen flags in `construct_transactions.do` (+2),
  `supplier_riskiness_did_additional.do` (+1), and `clean_firm_geocodes.do`
  (+1). **Both known-positive control sites remain emitted.**

Decision-threshold placement is unchanged: 10 <= 50 with the control emitted —
still the "build" region. This extension counts as a rule-shape fix driven by a
known-positive (the P-21 plant), not as the pre-registered narrowing iteration
(which addresses over-emission; the count moved 6 -> 10, nowhere near 150).
If the decision is "build", the committed emitter should include the boolean-gen
producer shape and consider adding `recode` to the mutator list (one real gated
`recode` consumer exists in the package; see advisory in the U3 verification).
