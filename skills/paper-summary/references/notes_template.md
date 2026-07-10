# Notes Template

Use this file to initialise `notes.md`, then replace the template bullets with paper-specific content as the section analysis passes work through the paper.

## Rules

- Keep the exact heading structure shown below.
- Keep the numbered section headings exactly as written, but add or retain the internal `####` subheaders shown below when they help organise material.
- Update the shared `notes.md` in place rather than creating section-specific scratch notes.
- Every substantive bullet should include an inline anchor or an explicit `Gap flag: ...`.
- Use UK British English.
- Distinguish direct evidence from interpretation.
- Keep most bullets evidence-first and concise; split dense bullets rather than stacking several claims into one line.
- Add `Intuition:` bullets selectively for technically dense models, estimands, decompositions, or regression designs. If the paper does not spell out the intuition, infer it conservatively and keep it clearly separate from direct evidence.
- In `### 4.1 Limitations`, label limits clearly as `Author-stated:` or `Inferred:` where relevant.
- In `## 5. Synthesis of findings`, write exactly two plain-text lines, not bullets.
- The final editing pass should remove any template bullets that were not replaced with paper-specific content.

## Shared `notes.md` template

```md
## 1. Research Question and Motivation

#### Question
- State the central causal question precisely.
  - Separate the question into outcome blocks when relevant, for example reduced-form impacts and welfare or willingness-to-pay impacts.

#### Why it matters
- Explain why the question matters for policy and for the existing literature.

#### Audience and contribution
- Audience: which sub-community of researchers cares about this?

## 2. Data and Methods

### 2.1 Data (source, type, time span)

#### Core datasets
- For each key dataset, report source, unit of observation, geography, and period, plus any other detail that is needed for interpretation.
- Report where the data comes from.

#### Sample and construction
- Report sample size and scale where available.
- If important, describe data linkage or matching steps and any validation checks.

### 2.2 Method

#### Design
- How do the authors answer the question they set out?
- What is the identification strategy?
- What is the identifying variation, if empirical?
- If there is an empirical intervention, describe the institutional intervention and treatment definition.

#### Assumptions and threats
- What are the identifying assumptions?
- How does the paper address likely violations?

#### Intuition
- Only add this subheader if the design is technically dense.
- Give brief intuition for the design or key estimating equation when that would materially improve readability.

## 3. Results: Main Findings

#### Main estimates
- What are the main results? Include key coefficient estimates and standard errors where reported.

#### Mechanisms, heterogeneity, and robustness
- Organise findings into the subset of relevant buckets for that paper, for example direct effects, spillovers, mechanisms, heterogeneity, welfare estimates, robustness, and policy counterfactuals.
- Include robustness-sensitive findings and caveats when they materially affect interpretation.

#### Contribution
- Contributions: what is learned from this exercise that we did not know before?

#### Intuition
- Only add this subheader if a result, estimand, or decomposition is hard to parse without a brief explanation of what is moving and why.

## 4. Limitations and Extensions

### 4.1 Limitations (including plausible ones beyond the authors)

#### Design and data limits
- Include author-stated limitations and additional plausible limitations grounded in the design and data.
- Flag which limitations are directly stated versus inferred.

### 4.2 Concrete directions for future research

#### Next empirical steps
- Provide actionable follow-on designs or data extensions tied to the limitations above.

## 5. Synthesis of findings
Line 1.
Line 2.
```
