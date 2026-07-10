# Notes Template

This file is the single source of every note-content rule. Initialise `notes.md`
from the skeleton at the bottom, then replace the template bullets with
paper-specific content as the section-analysis passes work through the paper.
The five-part structure itself (section numbers, names, fold headings) is defined
once in [summary_sections.json](summary_sections.json); keep the headings below
consistent with it.

## Content rules

- Keep the exact heading structure shown in the skeleton. Keep the numbered
  section headings as written, and keep or add the internal `####` subheaders
  when they help organise material.
- Update the shared `notes.md` in place. Do not create section-specific scratch
  notes.
- Use UK British English.
- Ground every substantive claim with an inline anchor such as `[p. 12, Section 4.2]`.
  If only the page can be verified, use `[p. 12]`; if only the section, use
  `[Section 4.2]`. If an important detail cannot be verified, write an explicit
  `Gap flag: ...` rather than guessing. Never invent page numbers, section
  names, coefficients, methods, or sample definitions.
- Keep direct evidence separate from interpretation.
- In `### 4.1 Limitations`, label each limit as `Author-stated:` or `Inferred:`.
- In `## 5. Synthesis of findings`, write exactly two plain-text lines, not
  bullets.
- The final editing pass removes any template bullets that were not replaced
  with paper-specific content.

## Two-tier bullet style

Write each subsection as a small set of **headline bullets** with **nested
evidence** beneath them. This replaces flat walls of same-weight bullets.

- A headline bullet is a plain-text sentence stating **one interpretive claim**.
  - No bold, no leading label, no sigils or emoji. Just the sentence.
  - It carries the reading — what the reader should take away — not raw numbers.
- Under each headline, nest the supporting evidence as sub-bullets. Every
  evidence sub-bullet **ends in an anchor** (or a `Gap flag:`).
- Coverage is preserved, not cut: keep every point the flat version would have
  had, but arrange it under the claim it supports. Add hierarchy; do not drop
  content.
- Use at most one `Intuition:` line per subsection, and only when a model,
  estimand, decomposition, or regression design is hard to parse without it. If
  the paper does not state the intuition, infer it conservatively and keep it
  clearly marked as interpretation.
- Split an overloaded headline into two headlines rather than stacking several
  claims onto one line.

### Worked exemplar

```md
### 2.2 Method

#### Design
- Identification comes from a population threshold in the road-eligibility rule.
  - Villages just above the 500-person threshold became eligible for an
    all-weather road; those just below did not [p. 6, Section 3.1].
  - The running variable is 2001 census population; the estimates use a 100-person
    bandwidth [p. 7, Table 2].
  - Intuition: villages on either side of an arbitrary cutoff are otherwise
    similar, so road access near the threshold is as good as randomly assigned.
- The design cannot speak to villages far from the threshold.
  - Effects are local to the cutoff and need not extend to much larger or
    smaller villages [p. 8].

## 3. Results: Main Findings

#### Main estimates
- Road access raises consumption without pulling workers out of the village.
  - Household consumption rises about 8% (se 2%) after a road arrives
    [p. 11, Table 4].
  - Out-migration is flat: the coefficient is 0.01 (se 0.03) and not significant
    [p. 12, Table 5].
```

## Shared `notes.md` skeleton

```md
## 1. Research Question and Motivation

#### Question
- State the central question as one plain-text claim, with the paper's framing
  beneath it as evidence.

#### Why it matters
- State why the question matters for policy or the literature.

#### Audience and contribution
- Name the sub-community that cares and what the paper adds for them.

## 2. Data and Methods

### 2.1 Data (source, type, time span)

#### Core datasets
- For each key dataset, state the reading in a headline, with source, unit of
  observation, geography, and period nested beneath as anchored evidence.

#### Sample and construction
- Report sample size and any linkage, matching, or validation steps.

### 2.2 Method

#### Design
- State the identification strategy as a headline claim; nest the identifying
  variation, treatment definition, and (if useful) one intuition line beneath.

#### Assumptions and threats
- State the identifying assumptions and how the paper addresses likely
  violations.

## 3. Results: Main Findings

#### Main estimates
- State what the results mean as headlines; nest key coefficients and standard
  errors as anchored evidence.

#### Mechanisms, heterogeneity, and robustness
- Group findings under the buckets that fit this paper (direct effects,
  spillovers, mechanisms, heterogeneity, welfare, robustness, counterfactuals).

#### Contribution
- State what is now known that was not known before.

## 4. Limitations and Extensions

### 4.1 Limitations (including plausible ones beyond the authors)
- State each limitation as a headline; label it `Author-stated:` or `Inferred:`
  in the nested evidence.

### 4.2 Concrete directions for future research
- Give actionable follow-on designs or data extensions tied to the limitations.

## 5. Synthesis of findings
Line 1.
Line 2.
```
