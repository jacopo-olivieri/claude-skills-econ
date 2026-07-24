# stata

Work with local Stata installations more reliably. The skill helps an agent write and review `.do` files, run them in batch mode, diagnose failures from their logs, and find answers in the Stata help files and manuals installed on your computer.

## Requirements

- A local Stata installation. The skill works out of the box on macOS when Stata SE, MP, or BE is installed in the usual Applications location.
- Python 3.10 or later for the bundled helpers.
- Optional tools for documentation search: `pdfgrep` for fast manual searches, and Docling for converting selected manual pages to Markdown.

The Stata guidance is useful on macOS, Linux, and Windows. The current automation is tested on macOS: it discovers a standard local Stata installation automatically, so you do not need to provide paths unless Stata is installed somewhere non-standard or you want to configure documentation search explicitly.

### Linux and Windows

Linux and Windows users can use the skill, but should ask their agent to adapt the machine-specific setup first. On Linux, that normally means configuring the Stata executable and local manual directories if automatic discovery does not find them. On Windows, it also means replacing the bundled Bash runner with an equivalent PowerShell or batch-script workflow and configuring the Windows Stata executable and documentation paths.

The core guidance for writing, reviewing, and debugging Stata code is platform-independent. Until the platform-specific setup has been adapted and tested on a given machine, treat automated execution and documentation search as setup work rather than a guaranteed out-of-the-box feature.

## Setup

### Install the skill

Install `stata` with the skills installer, or link its folder into the skills directory used by Claude Code or Codex. Once installed, the skill can normally find Stata without further setup.

### Optional local configuration

If your Stata installation, manuals, or ado files live outside the standard macOS location, create a private configuration file at `~/.agents/config/stata.json`. Start by copying the skill's `config.example.json`, then keep only the entries you need and replace their placeholder values. On Linux or Windows, ask the agent to create the equivalent local configuration with paths appropriate for your installation.

For example, a minimal setup that specifies only a non-standard Stata binary is:

```json
{
  "stata_bin": "~/Applications/StataSE.app/Contents/MacOS/stata-se"
}
```

You can also provide `stata_docs_dir` and `stata_ado_base_dir` for local-documentation search, plus optional `author` and `stata_version` defaults for newly created do-files. Do not leave placeholder paths in the file: every path that is present is validated. Partial configurations are valid.

The resolver prefers an explicit command-line choice, then environment variables, then this local configuration, then automatic discovery. It reports a clear error if the selected resource does not exist or cannot be used.

## Use

The skill loads automatically for requests mentioning Stata, `.do` files, `.dta` datasets, ado files, batch execution, or local Stata documentation. You can also invoke it explicitly with:

```text
/stata
```

### Writing and reviewing do-files

Ask the agent to create or improve a do-file. It follows a reproducible structure: a clear file header, an explicit Stata version, deterministic session settings, documented inputs and outputs, and guarded installation of user-written packages when needed.

For reviews, the skill checks common Stata-specific risks such as unguarded missing values, merge results that are dropped without inspection, fragile globals, and unclear data or output paths.

### Running do-files safely

The skill runs do-files in **batch mode**: non-interactively from start to finish, with a log of what happened. Its bundled wrapper runs from the do-file's own directory, removes stale logs, and treats Stata error markers in a fresh log as failures rather than trusting Stata's process exit code alone. When a run fails, it surfaces the useful end of the log for diagnosis.

### Troubleshooting errors

Share the do-file, the relevant log excerpt, and the expected result. The skill can distinguish syntax errors, missing packages, unavailable input files, merge and variable problems, and errors caused by the working directory or version differences.

### Searching local Stata documentation

Ask a question about command syntax, options, estimation details, macros, or programming. The skill searches the installed command help first, then selects a relevant PDF manual, and only converts targeted pages when raw help or search context is not enough.

## Usage examples

- “Write a do-file that imports this CSV, cleans the variables, and saves an analysis dataset.”
- “Review `analysis.do` for fragile paths, merge mistakes, and missing-value bugs.”
- “Run this do-file safely and explain any errors in the log.”
- “Why is my `merge` producing unmatched observations? Check the relevant Stata documentation.”
- “Find the correct syntax for clustered standard errors with `reghdfe`.”
- “Search my local manuals for the options of `xtreg, fe` and explain the relevant ones.”

## How it works

The skill resolves only the local Stata resources needed for the task, using portable discovery with optional per-user overrides. It uses guarded batch execution and log inspection so a superficially successful Stata process is not mistaken for a successful analysis. For documentation, it narrows from installed help files to one relevant manual and then to specific pages, keeping searches quick and focused.
