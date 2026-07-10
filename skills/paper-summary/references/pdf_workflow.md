# Preparation Workflow

Resolve or acquire the paper and create a reusable local workspace before any
analysis starts. `$SKILL_DIR` is this skill's directory; the papers directory
comes from `~/.agents/config/paper-skills.json` (key `papers_dir`) — never a
hardcoded path.

## Inputs and outputs

- **Input:** an explicit local PDF path, or a fuzzy descriptor such as
  `asher novosad 2020 india roads`.
- **Output:** a resolved local PDF, a workspace at `<papers_dir>/<paper_stem>/`,
  and `paper.md`, `sections/*.md`, and `notes.md` inside it.

## 1. Resolve the paper locally first

- If the user gives an explicit path, verify it exists and use it.
- Otherwise search the papers directory for matching PDFs. Build fuzzy patterns
  from author surnames, year, and distinctive title words; treat spaces,
  punctuation, hyphens, and underscores as interchangeable.
- Accept a single high-confidence match automatically. Ask for disambiguation
  only when more than one candidate is plausible.

Example lookup (substitute the configured papers directory for `$PAPERS_DIR`):

```bash
rg --files "$PAPERS_DIR" -g '*.pdf' \
  | rg -i 'asher.*novosad|novosad.*asher|2020|rural|roads|india'
```

Resolution preference: exact author+year, then strong overlap on rare title
words, then supportive geography or topic tokens.

## 2. Acquire an open-access copy if no local PDF exists

- Search the web only after local search fails. Prioritise: author webpage,
  then working-paper/repository copy, then ungated journal PDF, then a clearly
  open mirror or archive.
- Download only a direct PDF or clearly open file, and save it into the papers
  directory with a normalised filename.
- If no open-access copy exists, return the publisher or landing-page URL and
  stop so the user can download it with institutional access. Do not continue to
  analysis without a local PDF.

## 3. Convert the full PDF to markdown

Conversion must run **before** the workspace `init` step: `init` reads the
converted markdown, so it has to exist first.

- Set `paper_stem` to the PDF filename without `.pdf`, and `WORKSPACE` to
  `<papers_dir>/<paper_stem>`.
- **Preflight:** confirm the chosen converter is on `PATH`. If a copy was just
  downloaded, confirm the file begins with the `%PDF` magic bytes before
  trusting it.

**Default — `docling` (fast, best heading structure):**

```bash
docling "$PDF" --to md --no-ocr --image-export-mode placeholder \
  --output "$WORKSPACE/conversion"
```

**Theory-heavy papers — `mineru` (preserves LaTeX equations + tables):**

```bash
mineru -p "$PDF" -o "$WORKSPACE/conversion" -m txt -b pipeline
```

Use `mineru` when the paper's structural-model equations need to be in the
notes; docling flattens display equations to text. If the user names a converter
("use MinerU", "use docling"), honour that regardless of the default.

- Always convert the full document into `$WORKSPACE/conversion/` and treat the
  result as the canonical working text. The `init` helper is converter-agnostic
  (it picks the largest `.md` under the conversion directory).
- You may use direct PDF inspection or `pdfplumber` only to diagnose obvious
  extraction problems. Do not replace `paper.md` with a hand extraction.

## 4. Create or refresh the paper workspace

After the converter has written `$WORKSPACE/conversion/`:

```bash
python3 "$SKILL_DIR/scripts/paper_workspace.py" init \
  --pdf "$PDF" \
  --notes-template "$SKILL_DIR/references/notes_template.md"
```

The helper script locates the primary converted markdown (the largest `.md`
under `conversion/`) and copies it to `paper.md`, rewrites `sections/*.md`, and
reinitialises `notes.md` from [notes_template.md](notes_template.md). It reports
a `word_count` and any `warnings` as JSON.

- `init` refuses to overwrite a `notes.md` that has diverged from the template
  unless `--force` is passed, so an accidental re-run does not wipe accumulated
  notes. Reinitialise for each new run unless the user asks to continue an
  existing one.
- **Scanned-PDF sanity check:** divide `word_count` by the paper's page count.
  A very low words-per-page estimate (well under ~150) usually means a
  scanned/image PDF the converter could not read as text. Flag this and stop
  rather than summarising an empty extraction.
- If the split `warnings` report that ≤1 main-text section was recovered, treat
  heading recovery as weak (see below).

## 5. Section split policy

The helper script splits `paper.md` by its top-level main-text sections; do not
split manually when it recovers headings faithfully. It produces:

- `00_abstract_and_introduction.md` — abstract, introduction, and front-matter
  motivation before the first main section;
- `01_<section_name>.md`, `02_<section_name>.md`, … — one per top-level main-text
  section, with subsection material nested inside its parent;
- `appendix.md` — all appendix, online-appendix, and appendix table/figure
  material.

If headings are weak (few sections recovered): prefer the paper's table
of contents, then major numbered headings; if recovery is still poor, accept the
coarsest faithful split and record the limitation in `notes.md`. If `appendix.md`
is very large, skim it for material that changes interpretation rather than
analysing every table.

## 6. Update `notes.md` during analysis

Keep the exact heading structure from [notes_template.md](notes_template.md).
Leave sections blank or partial rather than filling them with guesses. Each
section pass updates the shared `notes.md` in place; stage the revised text in a
temp file and write it back (recording the section as processed for resume):

```bash
python3 "$SKILL_DIR/scripts/paper_workspace.py" write-text \
  --workspace "$WORKSPACE" \
  --relative-path notes.md \
  --input-file /tmp/paper-summary-notes.md \
  --mark-processed "$SECTION_FILE"
```

## Verification and anti-hallucination

The anchoring and never-invent rules for `notes.md` content live in
[notes_template.md](notes_template.md) — follow them there. During preparation,
the relevant point is upstream: do not trust an extraction you have not verified
(the `%PDF` check and the words-per-page sanity check above), so that the notes
are anchored to a faithful `paper.md`.
