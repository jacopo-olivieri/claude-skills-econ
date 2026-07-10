---
name: paper-summary
description: >-
  Produce evidence-grounded full summaries of academic economics papers using a
  staged workflow: resolve or acquire the PDF, convert the full paper to
  markdown with Marker, split it into section files, analyse sections
  sequentially into shared notes, and return a polished five-part summary. Use
  when the user wants a full paper summary.
disable-model-invocation: true
---

# Paper Summary

## Scope

- Accept either:
  - an explicit local PDF path
  - a paper descriptor, which may be exact or fuzzy, such as `asher novosad 2020 india roads`

## Required Paths

- Default paper directory: `/Users/jacopoolivieri/Documents/05_sources/04_papers/`
- Paper workspace: `/Users/jacopoolivieri/Documents/05_sources/04_papers/<paper_stem>/`
- Workspace helper script: `/Users/jacopoolivieri/.codex/skills/paper-summary/scripts/paper_workspace.py`
- Required workspace outputs:
  - `paper.md`
  - `sections/00_abstract_and_introduction.md`
  - `sections/01_<section_name>.md`, `sections/02_<section_name>.md`, ...
  - `sections/appendix.md`
  - `notes.md`
- Keep existing local PDFs in place.
- Save newly downloaded open-access PDFs in the default paper directory using a normalised filename.

## Workflow

### Context hygiene policy

- When sub-agents are available, spawn fresh sub-agents deliberately for context hygiene, not for parallelism.
- Do not fork the full prior conversation into section-analysis or final-editor agents. Each sub-agent should receive only the minimal files and instructions listed for its stage.
- Treat `notes.md` as the shared memory between section-analysis agents. After each section agent saves `notes.md`, pass that newly saved version to the next section agent.
- If sub-agents are unavailable, run isolated main-thread passes with the same minimal-context discipline.

### Reasoning policy

- When sub-agents are available, spawn them explicitly and pass an explicit `reasoning_effort`; otherwise use the same effort targets for the corresponding isolated main-thread pass.
- Default profile:
  - preparation pass: `medium`
  - main-text section passes: `high`
  - appendix pass: `high`
  - final structure edit: `xhigh`
- Raise the preparation pass to `high` only when the paper descriptor is ambiguous, Marker extraction is messy, or section recovery is uncertain.
- Keep main-text section passes at `high` by default for summary quality.
- Use `high` for the appendix pass by default.
- Keep the final structure edit at `xhigh` by default because it is the global consistency and synthesis pass.

### 1. Preparation pass

- Complete paper preparation before any substantive analysis begins.
- When sub-agents are available, spawn one specialised preparation sub-agent with `reasoning_effort: medium`; otherwise do it in an isolated main-thread pass.
- The preparation sub-agent may receive the user's paper descriptor or local PDF path plus [references/pdf_workflow.md](references/pdf_workflow.md).
- This pass owns:
  - paper resolution from the user descriptor
  - open-access acquisition when no local PDF is found
  - full-document Marker conversion
  - workspace creation, section splitting, and `notes.md` initialisation via the helper script
- Use [references/pdf_workflow.md](references/pdf_workflow.md) for the full preparation procedure.
- Do not begin section analysis until this pass has produced and returned the workspace artefacts.

### 2. Sequential section analysis

- Work through one section file at a time.
- When sub-agents are available, spawn one fresh section-analysis sub-agent per section file; otherwise do a fresh isolated section-analysis pass in the main thread for each file.
- Run each section sub-agent with `fork_context: false`, or the closest available equivalent, so it does not inherit the prior conversation or earlier section-agent context.
- Run the section analysis strictly sequentially, not in parallel.
- Use `reasoning_effort: high` for every section-analysis sub-agent, including `appendix.md`.
- For each section, read only:
  - its assigned section file
  - the current `notes.md`
  - [references/notes_template.md](references/notes_template.md)
- Each section pass must update `notes.md` in place:
  - add evidence-backed bullets
  - refine or replace weaker draft bullets when the new section supplies better evidence
  - avoid duplicating points already captured
  - organise dense material under the most relevant subheaders from the template before adding more bullets
  - add a short `Intuition:` bullet only for conceptually dense claims, models, estimands, decompositions, or regression designs that would otherwise be hard to parse
- Stage the revised full `notes.md` in `/tmp` first, then save it into the paper workspace with:
```bash
python3 /Users/jacopoolivieri/.codex/skills/paper-summary/scripts/paper_workspace.py write-text \
  --workspace "$WORKSPACE" \
  --relative-path notes.md \
  --input-file /tmp/paper-summary-notes.md
```
- Appendix evidence should only be used when it materially clarifies methods, robustness, caveats, or extra detail that changes interpretation.

### 3. Final structure editing pass

- After all section passes finish, do one final editing pass.
- When sub-agents are available, spawn one fresh editor sub-agent with `reasoning_effort: xhigh`; otherwise do a fresh isolated final editing pass in the main thread.
- Run the editor sub-agent with `fork_context: false`, or the closest available equivalent, so it does not rely on section-agent conversation context.
- In this pass, read only all section files, the current `notes.md`, and [references/notes_template.md](references/notes_template.md).
- The final editing pass must:
  - remove duplication
  - resolve inconsistencies
  - improve logic and flow
  - preserve anchors and gap flags
  - ensure the notes follow the exact heading structure in [references/notes_template.md](references/notes_template.md)
  - enforce the template's internal subheaders where they improve scanability
  - split overloaded bullets into shorter evidence-first bullets
  - retain selective `Intuition:` bullets only where they add real explanatory value
  - stage the polished result in `/tmp` and save it back to `notes.md` with the helper script
- Return the final `notes.md` content in chat and include the saved path.

## Non-negotiable Rules

- Always convert the full PDF to markdown with `marker_single`.
- Do not use page-targeted extraction in this skill.
- Treat the Marker markdown as the canonical working text.
- Split the paper by its actual top-level main-text sections.
- Combine abstract and introduction into one section file.
- Collapse all appendix material into one `appendix.md`.
- Use UK British English.
- Ground substantive claims with inline anchors such as `[p. 12, Section 4.2]`.
- If only the page can be verified, use `[p. 12]`.
- If only the section can be verified, use `[Section 4.2]`.
- If an important detail cannot be verified, use an explicit gap flag rather than guessing.
- Keep direct evidence separate from interpretation.
- Use short subheaders under the existing section headings when needed to group related bullets, especially for data, identification, findings, limitations, and extensions.
- Use `Intuition:` sparingly and only for hard-to-parse technical content. If the paper does not state the intuition explicitly, infer it conservatively from the design and label it as interpretation rather than direct evidence.
- Keep `## 5. Synthesis of findings` to exactly two lines.

## Allowed Shell Commands

- Prefer tool-native file operations for reading and writing text files.
- Use shell commands only for the minimal external commands this skill depends on:
  - `rg` for local PDF discovery
  - `curl` for open-access PDF download
  - `marker_single` for full-document conversion
  - `python3 /Users/jacopoolivieri/.codex/skills/paper-summary/scripts/paper_workspace.py` for all writes under `/Users/jacopoolivieri/Documents/05_sources/04_papers/`, including workspace creation, `paper.md` refresh, section splitting, and staged text writes back to `notes.md`
- Route every write under `/Users/jacopoolivieri/Documents/05_sources/04_papers/` through the helper script rather than `mkdir`, `cp`, shell redirection, or direct edits in that directory.
- If the first helper-script invocation requires approval, request a reusable prefix rule for:
  - `["python3", "/Users/jacopoolivieri/.codex/skills/paper-summary/scripts/paper_workspace.py"]`
- Do not assume permission for broader shell usage such as arbitrary `find`, `mv`, or destructive commands.

## References

- Preparation workflow: [references/pdf_workflow.md](references/pdf_workflow.md)
- Shared notes template: [references/notes_template.md](references/notes_template.md)
