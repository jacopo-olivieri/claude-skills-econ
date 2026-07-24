# paper-summary

Summarise an academic economics paper. The skill finds or accepts a PDF, converts the complete paper to Markdown, works through it systematically, and returns a polished five-part set of notes.

## Requirements

- A local PDF of the paper, or enough identifying information for the skill to locate an openly available copy.
- Python 3.10 or later for the workspace helper.
- A PDF-to-Markdown converter:
  - [`docling`](https://docling-project.github.io/docling/) is the default and is best for most papers.
  - [MinerU](https://github.com/opendatalab/MinerU) is useful for theory-heavy papers where equations and tables matter.
- Optional: internet access when the paper is not already stored locally and an open-access copy must be found.

The skill works on any platform where Python and the selected converter are available. The local folders it uses are configured per user, so no personal paths are included in the skill itself.

## Setup

### Install the skill

Install `paper-summary` with the skills installer, or link its folder into the skills directory used by Claude Code or Codex.

### Configure your papers directory

The skill needs one local folder in which to create paper workspaces. Copy the repository's `config.example.json` to:

```text
~/.agents/config/paper-skills.json
```

Then set `papers_dir` to a folder on your computer. For example:

```json
{
  "papers_dir": "~/Documents/papers"
}
```

The repository's full example also contains optional settings for the separate `paper-summary-obsidian` companion skill. You can leave those out if you only use `paper-summary`. Do not put another person's paths in this file: it is deliberately local to your computer.

For each paper, the skill creates a workspace inside `papers_dir` containing the original working text, the converted Markdown, section files, and the final `notes.md`. This keeps the inputs and summary together and allows an interrupted run to resume safely.

## Use

Invoke the skill explicitly with:

```text
/paper-summary
```

Then give it either a local PDF path or a paper description such as an author, year, and a few title words.

### Provide a paper

If you have the PDF, point the skill to it directly. Otherwise, describe the paper. The skill searches your configured papers directory first, then looks for an open-access copy if it cannot find a confident local match. If only a paywalled version is available, it stops and asks you to provide a local PDF rather than working from an incomplete source.

### Follow the summary workflow

The skill converts the full paper before analysing it, checks that the conversion is usable, and splits it into meaningful main-text sections. It analyses sections one at a time, building shared notes as it goes. This avoids relying on an isolated abstract or a partial reading of the paper.

For short papers, the skill may use one complete-paper pass. For longer papers, it reads the main text sequentially and considers the appendix only when it changes the interpretation, methods, robustness, or caveats.

### Resume a partial summary

If the work is interrupted, ask the skill to resume the paper. It records completed sections in the workspace notes and continues from the first unfinished section instead of discarding the work already done.

### Optional Obsidian handoff

If you also install the separately distributed `paper-summary-obsidian` skill, you can ask it to save a finished summary into an Obsidian vault. That companion skill formats and saves the completed notes; it does not replace the summarisation workflow.

## Usage examples

- “Summarise `/path/to/paper.pdf` using the paper-summary skill.”
- “Find and summarise Asher and Novosad’s 2020 paper on roads in India.”
- “Summarise this paper, but use MinerU because the structural model equations matter.”
- “Resume the summary of the paper I started yesterday.”
- “Give me a full five-part summary, with separate evidence and interpretation.”
- “Summarise this paper and flag any uncertainty caused by a poor PDF conversion.”

## Output

The final result is a polished five-part `notes.md` in the paper's workspace, as well as the full text in the chat. The notes distinguish what the paper directly establishes from interpretation, preserve supporting anchors where useful, and identify important gaps or conversion limitations rather than filling them with guesses.

The workspace also keeps the converted `paper.md` and its section files. These make it possible to inspect the source material, resume a partial run, or revisit one part of the summary later.

## How it works

The skill follows a staged, evidence-first workflow: resolve the paper, verify a usable PDF and conversion, create a workspace, analyse the text in manageable sections, then perform a final consistency and structure pass. It uses a shared notes file between section passes so the final synthesis is based on the whole paper, not on a single context window. The workflow checks for common conversion failures and keeps uncertainty visible when the source text is incomplete or unclear.
