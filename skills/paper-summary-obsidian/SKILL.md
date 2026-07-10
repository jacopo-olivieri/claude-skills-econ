---
name: paper-summary-obsidian
description: Save an already-written paper summary into the Obsidian papers vault at /Users/jacopoolivieri/Documents/poodle_obsidian_db/sources/papers using Zotero metadata and the live Zotero note template at /Users/jacopoolivieri/Documents/poodle_obsidian_db/templates/template zotero.md. Use when the user already has the summary text and asks Codex to save, store, create, update, or sync an Obsidian paper note from a Zotero item; do not use to summarise a paper from scratch.
disable-model-invocation: true
---

# Paper Summary Obsidian

Save an existing summary into an Obsidian paper note. Do not summarise the paper in this skill.

## Use the bundled resources

- Resolve the skill directory from the provided skill path. Do not assume a fixed install location.
- Run `scripts/save_paper_summary.py` from this skill for rendering, note placement, and collision handling.
- Read `references/metadata_schema.md` only when preparing or debugging the metadata JSON.
- Write notes to `/Users/jacopoolivieri/Documents/poodle_obsidian_db/sources/papers`.
- Use the live template at `/Users/jacopoolivieri/Documents/poodle_obsidian_db/templates/template zotero.md`.

## Workflow

1. Resolve metadata from Zotero by `item_key`.
- Use the available Zotero metadata tools or MCP server to fetch item metadata and child attachments.
- If the item does not exist in Zotero, stop and tell the user to add it first.
- Resolve the Zotero `citationKey` and pass it explicitly to the script.
- Build a compact metadata JSON file that matches `references/metadata_schema.md`.
- Keep Zotero `item_key` for metadata lookup and URI construction.

2. Save summary text to a temporary file.
- Use the summary text already provided by the user.
- Preserve user text as-is; do not rewrite content in this skill.

3. Run dry-run first (no write).
```bash
SKILL_DIR="/absolute/path/to/paper-summary-obsidian"

python3 "$SKILL_DIR/scripts/save_paper_summary.py" \
  --item-key "$ITEM_KEY" \
  --citation-key "$CITATION_KEY" \
  --summary-file /tmp/paper-summary.txt \
  --metadata-file /tmp/paper-metadata.json \
  --template-path "/Users/jacopoolivieri/Documents/poodle_obsidian_db/templates/template zotero.md" \
  --output-dir "/Users/jacopoolivieri/Documents/poodle_obsidian_db/sources/papers" \
  --on-exists skip
```

4. Write the file after dry-run succeeds.
```bash
SKILL_DIR="/absolute/path/to/paper-summary-obsidian"

python3 "$SKILL_DIR/scripts/save_paper_summary.py" \
  --item-key "$ITEM_KEY" \
  --citation-key "$CITATION_KEY" \
  --summary-file /tmp/paper-summary.txt \
  --metadata-file /tmp/paper-metadata.json \
  --template-path "/Users/jacopoolivieri/Documents/poodle_obsidian_db/templates/template zotero.md" \
  --output-dir "/Users/jacopoolivieri/Documents/poodle_obsidian_db/sources/papers" \
  --on-exists skip \
  --write
```

5. Return the result.
- Always return whether the run was a dry-run, skip, overwrite, versioned write, or write.
- Always return the full output path.
- If the file already exists, default to skip and report it.

## Rules

- Require Zotero `item_key` and `citationKey`.
- Use `citationKey` as both `citekey` and note filename stem (`@<citationKey>.md`).
- Default collision policy: `skip` (`--on-exists skip`).
- `project` and `links` frontmatter fields must default to empty.
- Use `date_published` (underscore), not `date-published`.
- Keep missing bibliography and PDF metadata blank without adding placeholder text or gap notes.
- Insert summary sections `1` to `4` in `## Reading notes` under these fold headings:
  - `### 💬 Research Question and Motivation %% fold %%`
  - `### 📌 Data and Empirical Strategy %% fold %%`
  - `### 🎯 Results %% fold %%`
  - `### ✒️ Limitations and Extensions %% fold %%`
  - do not re-insert section marker titles (for example `1. Research Question and Motivation`) as extra `####` headers in section bodies `1` to `4`.
- Apply formatting-only markdown cleanup to section bodies `1` to `4`:
  - remove trailing whitespace and repeated blank lines,
  - normalize list spacing (no blank lines between adjacent/nested list items),
  - convert header-like bold labels to plain, unnumbered `####` headers with no bold/italic markup (including numbered labels like `**1 Data ...**` and top-level header bullets like `* **Empirical strategy**`),
  - remove redundant paper identifier lines in section bodies (for example `* **Paper**: ...`),
  - remove markdown horizontal-rule separators (`---`, `***`, `___`) from section bodies,
  - do not leave a blank line directly under `####` headers (start bullets/text immediately below).
- If section `5` is `Synthesis of findings`, place that text in `## Key takeaways` immediately after `contribution::` and do not duplicate it under `### 🧩 Comments and Ideas %% fold %%`.
- For that synthesis block in `## Key takeaways`, render plain text only: strip list markers and markdown emphasis (`*`, `**`, `_`, `__`).
- Use `### 🧩 Comments and Ideas %% fold %%` for non-synthesis section `5` content.
- Always include these additional headings even if empty:
  - `### 🗺️ Background, context and connections %% fold %%`
  - `### 🚧 Digging and disclaimers %% fold %%`
  - `### ❓ Problem formulation %% fold %%`
