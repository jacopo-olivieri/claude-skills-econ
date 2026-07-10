---
name: paper-summary
description: >-
  Produce evidence-grounded full summaries of academic economics papers using a
  staged workflow: resolve or acquire the PDF, convert the full paper to
  markdown, split it into section files, analyse sections sequentially into
  shared notes, and return a polished five-part summary. Use when the user wants
  a full paper summary.
disable-model-invocation: true
allowed-tools: Bash(python3 *) Bash(docling *) Bash(mineru *) Bash(rg *)
---

# Paper Summary

Turn an economics paper into an evidence-anchored, five-part summary held in a
reusable local workspace. The companion skill `paper-summary-obsidian` saves a
finished summary into the Obsidian vault (see Handoff below).

## Scope

Accept either an explicit local PDF path, or a paper descriptor that may be
fuzzy, such as `asher novosad 2020 india roads`.

## Paths and configuration

- Resolve this skill's own directory from the path you were invoked with; call
  it `$SKILL_DIR`. Never hardcode an install location — the skill runs from a
  shared copy under both Codex and Claude Code.
- The papers directory and other machine-specific paths live in
  `~/.agents/config/paper-skills.json` (key `papers_dir`). The helper script
  reads this automatically; you do not pass it. If the config is missing, the
  script fails with a message naming the file to create.
- The workspace for a paper is `<papers_dir>/<paper_stem>/`, holding `paper.md`,
  `sections/*.md`, and `notes.md`.
- Route every write under the papers directory through
  `python3 "$SKILL_DIR/scripts/paper_workspace.py"`. Do not use `mkdir`, `cp`,
  shell redirection, or direct edits there.

## Reasoning-effort profile

Set the effort for each stage once, here:

| Stage | Effort | Notes |
|---|---|---|
| Preparation | medium | Raise to high only when the descriptor is ambiguous, the conversion is messy, or section recovery is uncertain. |
| Main-text section analysis | high | Every section, for summary quality. |
| Appendix analysis | medium | Escalate to high only if the appendix materially changes methods, robustness, or interpretation. |
| Final structure edit | xhigh | The global consistency, synthesis, and two-tier restyle pass. |

## Workflow

### Context hygiene

- When sub-agents are available, run each stage in a **fresh sub-agent that does
  not inherit the conversation** or earlier stage context — spawn it for context
  hygiene, not parallelism. When sub-agents are unavailable, run the same stage
  as an isolated main-thread pass with the same minimal-context discipline.
- `notes.md` is the shared memory between section passes. After each section
  pass saves `notes.md`, hand the newly saved version to the next pass.
- Give each stage only the minimal inputs listed for it below.

### 1. Preparation

Complete preparation before any analysis. This stage owns paper resolution,
open-access acquisition when no local PDF is found, full-document conversion,
and workspace creation via the helper script. Follow
[references/pdf_workflow.md](references/pdf_workflow.md), which includes the
converter choice (see below) and the acquisition-hardening checks:

- confirm the chosen converter is on `PATH` before converting;
- confirm a downloaded file begins with the `%PDF` magic bytes before trusting
  it;
- after conversion, sanity-check `paper.md` with a words-per-page estimate; a
  very low count signals a scanned/image PDF the converter could not read;
- if `sections/appendix.md` is very large, skim it rather than analysing it in
  full (see the appendix guidance below).

The `init` command reports a `word_count` and any `warnings`. Use the word count
for the fast-path decision below.

### 2. Sequential section analysis

- Work through one section file at a time, strictly in order — never in
  parallel. `appendix.md` is analysed last.
- Each section pass reads only: its assigned section file, the current
  `notes.md`, and [references/notes_template.md](references/notes_template.md).
  That template holds every note-content rule; do not restate them here.
- Each pass updates `notes.md` in place: add evidence-anchored bullets, refine
  or replace weaker draft bullets when the section supplies better evidence,
  avoid duplicating captured points, and organise dense material under the
  template's subheaders.
- Stage the revised full `notes.md` in a temp file, then save it and record the
  section as processed:

```bash
python3 "$SKILL_DIR/scripts/paper_workspace.py" write-text \
  --workspace "$WORKSPACE" \
  --relative-path notes.md \
  --input-file /tmp/paper-summary-notes.md \
  --mark-processed "$SECTION_FILE"
```

- **Appendix pass:** pull in appendix evidence only when it materially clarifies
  methods, robustness, caveats, or detail that changes interpretation; escalate
  the effort per the profile above when it does. If `appendix.md` is oversized,
  skim for such material rather than analysing every table.

### Fast path for short papers

If preparation reports a `word_count` under ~6000 words, skip the per-section
loop and run a single whole-paper analysis pass at high effort that writes the
full `notes.md` in one go. Longer papers use the sequential per-section passes.

### Resume after interruption

Each saved section appends a `<!-- paper-summary:processed <name> -->` marker to
`notes.md`. If a run is interrupted, read the current `notes.md`, note which
section files are already marked processed, and resume from the first unmarked
section — do not re-run `init` (that would discard accumulated notes; it refuses
to anyway without `--force`).

### 3. Final structure edit

Run one final pass at xhigh effort. It reads only the current `notes.md` and
[references/notes_template.md](references/notes_template.md) — **not** the
section files. Its mandate:

- remove duplication, resolve inconsistencies, improve logic and flow;
- preserve every anchor and gap flag;
- ensure the notes follow the template's exact heading structure;
- **restructure flat, same-weight bullet walls into the template's two-tier
  shape** — plain headline bullets stating one interpretive claim each, with the
  evidence nested beneath as anchored sub-bullets. Coverage is preserved, not
  cut; hierarchy is added.

Return the final `notes.md` content in chat and include the saved path.

## PDF-to-markdown converter

- **Default: `docling` (fast).** It is ~40× faster than Marker on this hardware
  with the cleanest section-heading structure (which the splitter depends on):

  ```bash
  docling "$PDF" --to md --no-ocr --image-export-mode placeholder \
    --output "$WORKSPACE/conversion"
  ```

- **Theory-heavy papers: `mineru`.** When a paper's structural-model equations
  need to be in the notes, use mineru instead — it preserves LaTeX equations and
  tables (docling flattens display equations):

  ```bash
  mineru -p "$PDF" -o "$WORKSPACE/conversion" -m txt -b pipeline
  ```

- **User override:** if the user names a converter (e.g. "summarise this paper
  and use MinerU", or "use docling"), use the one they name, regardless of the
  default.
- Whichever you use, write the output under `$WORKSPACE/conversion/`; the `init`
  helper is converter-agnostic and picks the largest `.md` there. Convert the
  full document — never page-targeted extraction — and treat the converted
  markdown as the canonical working text.

## Non-negotiable workflow rules
- Split the paper by its actual top-level main-text sections; combine abstract
  and introduction into one file; collapse all appendix material into
  `appendix.md`.
- Every note-content rule (anchors, UK English, evidence vs interpretation,
  `Intuition:` use, synthesis length, two-tier style) lives in
  [references/notes_template.md](references/notes_template.md). Follow it there.

## Handoff to paper-summary-obsidian

To save a finished summary into the Obsidian vault, hand off to the
`paper-summary-obsidian` skill with:

- the summary text — the workspace's `notes.md`;
- the paper's Zotero item key (and citation key).

That skill renders and saves the note; it does not summarise.

## Allowed shell commands

Prefer tool-native file reads/writes. Use shell only for:

- `rg` for local PDF discovery;
- `curl` for open-access PDF download;
- `docling` (default) or `mineru` (theory papers) for full-document conversion;
- `python3 "$SKILL_DIR/scripts/paper_workspace.py"` for all writes under the
  papers directory.

If the first helper-script call needs approval, request a reusable prefix rule
for `["python3", "$SKILL_DIR/scripts/paper_workspace.py"]`. Do not assume
permission for broader shell use such as arbitrary `find`, `mv`, or destructive
commands.

## References

- Preparation workflow: [references/pdf_workflow.md](references/pdf_workflow.md)
- Note-content rules and two-tier style: [references/notes_template.md](references/notes_template.md)
- Five-part structure (single source): [references/summary_sections.json](references/summary_sections.json)
