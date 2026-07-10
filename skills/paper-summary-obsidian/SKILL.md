---
name: paper-summary-obsidian
description: >-
  Save an already-written paper summary into the Obsidian papers vault as a
  literature note, using Zotero metadata and the live Zotero note template. Use
  when the user already has the summary text and asks to save, store, create,
  update, or sync an Obsidian paper note from a Zotero item; do not use to
  summarise a paper from scratch.
disable-model-invocation: true
allowed-tools: Bash(python3 *)
---

# Paper Summary Obsidian

Save an existing summary into an Obsidian paper note. This skill does not
summarise a paper — that is the `paper-summary` skill. The typical input is the
`notes.md` that `paper-summary` produced, plus the paper's Zotero item key.

## Paths and configuration

- Resolve this skill's own directory from the invocation path; call it
  `$SKILL_DIR`. Do not assume a fixed install location.
- The vault papers directory and the live template path come from
  `~/.agents/config/paper-skills.json` (keys `vault_papers_dir`,
  `vault_template`). `scripts/save_paper_summary.py` reads them automatically —
  do not re-pass them unless you are deliberately overriding. If the config is
  missing, the script fails with a message naming the file to create.
- The five-part structure is defined in the sibling skill's
  `paper-summary/references/summary_sections.json`; the script reads it (with an
  embedded fallback) and needs no argument for it.

## Workflow

### 1. Resolve Zotero metadata

- If you have the Zotero `item_key`, fetch the item's metadata and child
  attachments with the available Zotero tools.
- **If you were given a title/author instead of an item key**, search Zotero for
  it. If exactly one item matches, use it. If several plausibly match, show them
  and ask which one. If none match, stop and tell the user to add the item to
  Zotero first.
- Resolve the Zotero `citationKey` and build a compact metadata JSON file that
  matches [references/metadata_schema.md](references/metadata_schema.md). Keep
  the `item_key` for URI construction.

### 2. Stage the summary text

Write the summary text (the `paper-summary` `notes.md`) to a temp file **exactly
as given** — do not rewrite or reformat it. The save script performs the note
formatting itself (see "What the script does" below).

### 3. Dry-run, then write

Run the script once as a dry-run, read the reported output, then re-run with
`--write`. The output directory and template default from config, so pass only
what identifies this note:

```bash
python3 "$SKILL_DIR/scripts/save_paper_summary.py" \
  --item-key "$ITEM_KEY" \
  --citation-key "$CITATION_KEY" \
  --summary-file /tmp/paper-summary.txt \
  --metadata-file /tmp/paper-metadata.json \
  --on-exists skip
# review the dry-run JSON (status, path, sections_found, warnings), then:
#   add --write to the same command to save.
```

The JSON reports `status`, `path`, `mode`, `sections_found`, and `warnings`.
A `sections_found: 0` with a warning means the summary did not use the numbered
five-part structure — check the input before writing. A `template_drift` error
means the live template no longer matches the expected structure; it names each
missing landmark.

### 4. Collision handling

`--on-exists` controls what happens when `@<citationKey>.md` already exists:

- `skip` (default) — report and do nothing.
- `overwrite` — replace the whole note.
- `versioned` — write a timestamped sibling, leaving the original.
- `update` — **section-scoped merge**, invoked only on explicit user request.
  It replaces only the four generated fold-heading bodies (Research Question,
  Data, Results, Limitations) and the synthesis block, fills only empty
  frontmatter fields, and preserves all human-owned content (your Comments, the
  extra headings, your `contribution::` line) byte-for-byte. If the existing
  note is missing an anchor it needs, it refuses and names the anchor — fix the
  note by hand or use `versioned`.

### 5. Report

Always report whether the run was a dry-run, skip, overwrite, versioned write,
or update, and the full output path.

## What the script does (so you don't pre-apply it)

Pass the summary through verbatim. The script — not you — performs these
transforms, and you can verify them in the dry-run output:

- Quotes YAML frontmatter scalars so values containing `:` cannot break the
  frontmatter; emits the vault-dominant `date-published` and plain author names.
- Places summary sections 1–4 under their fold headings, and lifts a
  section-5 "Synthesis of findings" into `## Key takeaways` (plain text, list
  markers and emphasis stripped). Non-synthesis section-5 content goes under
  Comments and Ideas.
- Converts header-like bold labels into plain `####` subheaders, but leaves
  evidence bullets (e.g. `- **Main estimate**: 0.31`) as bullets.
- Leaves `project` and `links` frontmatter empty, and missing bibliography/PDF
  metadata blank.
- Always includes the additional headings (Background, Digging, Problem
  formulation) even when empty.

Because the script owns this cleanup, do not hand-format the summary to match the
note — that risks fighting the script. Require the Zotero `item_key` and
`citationKey`; the citation key is both the `citekey` field and the `@<key>.md`
filename stem.

## References

- Metadata JSON shape: [references/metadata_schema.md](references/metadata_schema.md)
