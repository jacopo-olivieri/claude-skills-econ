# Preparation Workflow

## Contents

- Goal
- Inputs
- Required outputs
- 1. Resolve the paper locally first
- 2. Acquire an open-access copy if no local PDF exists
- 3. Create or refresh the paper workspace
- 4. Convert the full PDF with Marker
- 5. Split `paper.md` into section files
- 6. Initialise and update `notes.md`
- Verification and anti-hallucination rules

## Goal

Resolve or acquire the paper and create a reusable local workspace before any substantive analysis starts.

## Inputs

- An explicit local PDF path, or
- a fuzzy paper descriptor such as `asher novosad 2020 india roads`

## Required Outputs

- A resolved local PDF path
- A paper workspace under `/Users/jacopoolivieri/Documents/05_sources/04_papers/<paper_stem>/`
- `paper.md`
- `sections/*.md`
- `notes.md`

## 1. Resolve the paper locally first

- If the user provides an explicit path, verify that it exists and use it.
- Otherwise search `/Users/jacopoolivieri/Documents/05_sources/04_papers/` for matching PDFs.
- Build fuzzy search patterns from author surnames, year, and distinctive title keywords.
- Treat spaces, punctuation, hyphens, and underscores as interchangeable when matching filenames.
- Accept a single high-confidence match automatically.
- Ask for disambiguation only when more than one candidate remains plausibly correct.

Example lookup command:

```bash
rg --files "/Users/jacopoolivieri/Documents/05_sources/04_papers" -g '*.pdf' \
  | rg -i 'asher.*novosad|novosad.*asher|2020|rural|roads|india'
```

Resolution preference order:

1. Exact author and year match
2. Strong overlap on rare title words
3. Supportive geography or topic tokens

Canonical example:

- `asher novosad 2020 india roads` should resolve to `asher_novosad_2020_rural_roads_and_local_economic_development.pdf` when that file exists locally.

## 2. Acquire an open-access copy if no local PDF exists

- Search the web for an open-access PDF only after local search fails.
- Prioritise sources in this order:
  1. author webpage
  2. working-paper series or repository copy
  3. ungated journal PDF
  4. other clearly open mirror or archive
- Download the paper only when you have a direct PDF or clearly open file.
- Save new open-access PDFs into `/Users/jacopoolivieri/Documents/05_sources/04_papers/` using a normalised filename.
- If no open-access PDF is available, return the publisher or landing-page URL and stop so the user can download it manually with institutional access.
- Do not continue to analysis without a local PDF.

## 3. Create or refresh the paper workspace

- Set `paper_stem` to the selected PDF filename without the `.pdf` suffix.
- Create or refresh the workspace with:

```bash
python3 /Users/jacopoolivieri/.codex/skills/paper-summary/scripts/paper_workspace.py init \
  --pdf "$PDF" \
  --notes-template /Users/jacopoolivieri/.codex/skills/paper-summary/references/notes_template.md
```

- The helper script owns:
  - workspace directory creation
  - copying the primary Marker markdown output to `paper.md`
  - rewriting `sections/*.md`
  - reinitialising `notes.md` from [notes_template.md](notes_template.md)
- Reinitialise `notes.md` for each new summary run unless the user explicitly asks to continue or revise an existing summary.

## 4. Convert the full PDF with Marker

```bash
marker_single "$PDF" \
  --output_format markdown \
  --output_dir "$WORKSPACE/marker_output" \
  --disable_multiprocessing
```

- Always convert the full document.
- Treat the Marker markdown as the canonical working text for the summary.
- Save or copy the primary Marker markdown output to `$WORKSPACE/paper.md`.
- Keep supplementary Marker artefacts inside `marker_output/`.
- You may use direct PDF inspection or `pdfplumber` only to verify obvious extraction problems. Do not replace `paper.md` with a non-Marker extraction.

## 5. Split `paper.md` into section files

- Do not split sections manually when the helper script can recover the headings faithfully.
- The helper script should split the markdown by the paper's actual top-level main-text sections.
- Keep subsection material nested inside its parent top-level section file.
- Name main-text section files with a two-digit prefix and a normalised snake_case section name.

Required split policy:

- `00_abstract_and_introduction.md`
  - abstract
  - introduction
  - front-matter motivation text before the first main section
- `01_<section_name>.md`, `02_<section_name>.md`, ...
  - one file per top-level main-text section
- `appendix.md`
  - all appendix material, online appendix material, and appendix tables or figures

If Marker headings are weak:

1. Use the paper table of contents if available.
2. Otherwise use major numbered headings.
3. If heading recovery is still weak, create the coarsest faithful section split possible and record that limitation in `notes.md`.

## 6. Initialise and update `notes.md`

- Initialise `notes.md` from [notes_template.md](notes_template.md) via the helper script.
- Keep the exact heading structure.
- Leave sections blank or partial rather than filling them with guesses.
- Treat `notes.md` as the shared working summary that each section pass updates in place.
- For subsequent saves into the paper workspace, stage revised text in `/tmp` and write it back with:

```bash
python3 /Users/jacopoolivieri/.codex/skills/paper-summary/scripts/paper_workspace.py write-text \
  --workspace "$WORKSPACE" \
  --relative-path notes.md \
  --input-file /tmp/paper-summary-notes.md
```

## Verification and anti-hallucination rules

- Every substantive claim in `notes.md` should carry an inline anchor or an explicit gap flag.
- Never invent page numbers, section names, coefficients, methods, or sample definitions.
- When the evidence is ambiguous, mark the uncertainty explicitly instead of smoothing it away.
