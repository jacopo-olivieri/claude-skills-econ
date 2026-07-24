# paper-summary

Create a structured summary of an academic economics paper from a PDF. The skill can either locate the paper online or use a PDF supplied by the user. It converts the paper to Markdown and produces concise notes covering:

* the research question and motivation;
* the data and empirical strategy;
* the main results;
* limitations and possible extensions; and
* critical comments and ideas for further research.

## Requirements

To use the skill, you need:

- **Access to the paper**, either as:
  - a local PDF; or
  - enough bibliographic information to identify it—such as the title, authors, DOI, or publication link—plus internet access to locate an open-access copy.
- **Python 3.10 or later** to organise the paper files and generated notes.
- **One PDF-to-Markdown converter**:
  - [`docling`](https://docling-project.github.io/docling/) is the default and is recommended for most papers.
  - [MinerU](https://github.com/opendatalab/MinerU) is a useful alternative for theory-heavy papers or when preserving equations and tables is especially important.

## Setup

### 1. Install a PDF-to-Markdown converter

Install one of the [supported converters](#requirements), or ask Claude Code or Codex to install one for you.

The skill uses `docling` by default. Use MinerU when preserving complex equations or tables is especially important, such as for theory papers.

### 2. Configure the papers directory

The skill uses a local directory to find papers and store their converted Markdown and generated notes.

For example:

```text
~/Documents/papers
```

You can ask Claude Code or Codex to configure it:

```text
/paper-summary Configure the papers directory as ~/Documents/papers.
```

Alternatively, configure it manually:

1. Copy [`config.example.json`](../../config.example.json) to:

   ```text
   ~/.agents/config/paper-skills.json
   ```

2. Set `papers_dir` to your chosen directory:

   ```json
   {
     "papers_dir": "~/Documents/papers"
   }
   ```

The skill searches this directory recursively, so you can organise papers into subdirectories.

### Optional: integrate with Zotero

Zotero can manage papers alongside the skill. For Zotero 7, the [ZotMoov plugin](https://github.com/wileyyugioh/zotmoov) can move imported PDFs into a directory you choose while retaining links to them in Zotero.

For the simplest setup, configure ZotMoov and `papers_dir` to use the same directory. You can also place ZotMoov’s directory anywhere inside `papers_dir`, because the skill searches its subdirectories.

## Use

Invoke the skill explicitly, followed by either a local PDF path or enough information to identify the paper:

```text
/paper-summary
```

### Examples

- `/paper-summary Summarise /path/to/paper.pdf`
- `/paper-summary Summarise Asher and Novosad’s 2020 paper on roads in India`
- `/paper-summary Summarise this theory paper, converting the PDF with MinerU.`

### Resume an interrupted summary

The skill saves its progress as it works. To resume an interrupted summary, invoke it again and identify the paper:

```text
/paper-summary Resume the summary of Asher and Novosad’s 2020 paper on roads in India.
```

The skill retains completed notes and resumes from the first unfinished section.

### Output

Once complete, the skill returns the summary in the chat and saves a copy as `notes.md` in the paper’s workspace.

The summary contains five sections:

1. **Research Question and Motivation**
2. **Data and Methods**
3. **Results: Main Findings**
4. **Limitations and Extensions**
5. **Synthesis of findings**

Within each section, the principal conclusions appear as headline points, followed by supporting evidence and references to the relevant pages or sections of the paper.

The workspace also retains the converted source text, including `paper.md` and its section files. You can use these files to verify citations, inspect the underlying text, or revisit individual parts of the analysis.

## How the skill works

The skill follows a five-stage workflow, from locating the paper to producing the final summary.

1. **Locates the full PDF.** If you provide a local path, the skill uses that file. Otherwise, it searches `papers_dir` and then looks online for an open-access copy. If it cannot find a complete version of the paper, it asks you to provide the PDF.

2. **Prepares the paper for analysis.** The skill creates a dedicated workspace, converts the PDF to Markdown, checks the extracted text for obvious quality or completeness problems, and splits the main text according to the paper’s top-level section headings.

3. **Analyses the main text.** If the extracted text contains fewer than about 6,000 words, the skill analyses the whole paper in one pass. For longer papers, it analyses each top-level section in order. After each section, it adds the findings to `notes.md`, which informs the analysis of the remaining sections.

4. **Consults the appendix where necessary.** The skill reviews appendix material when it is needed to understand the paper’s methods, results, robustness checks, interpretation, or limitations.

5. **Reviews and finalises the summary.** The skill checks the accumulated notes against the full converted paper. It resolves inconsistencies and repetition, checks that the main findings are covered, separates what the paper establishes from additional interpretation, and flags anything it cannot verify. It then organises the notes into the final five-part summary.
