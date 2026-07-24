# stata

This skill helps agents write and review stata code. The skill 'teaches' agents to execute do-files in batch mode, diagnose errors and unexpected behaviour from Stata logs, and consult locally installed Stata help files and manuals for syntax and implementation guidance.

## Requirements

### Required

- **A local Stata installation.** Stata/BE, Stata/SE, and Stata/MP are supported.
- **Python 3.10 or later.** The bundled helper scripts require it.

### Optional documentation tools

- **`pdfgrep`.** Searches locally installed Stata manuals quickly.
- **Docling.** Converts selected manual pages to Markdown.

## Setup

### Platform setup

- **macOS:** Standard installations are detected automatically. Configure paths only when Stata or its documentation is installed in a non-standard location.
- **Linux:** Specify the Stata executable and documentation directories when they cannot be discovered automatically.
- **Windows:** Specify the same paths and replace the bundled Bash runner with an equivalent PowerShell or batch script.

The guidance for writing, reviewing, and troubleshooting Stata code applies across all three platforms. Automatic discovery and the bundled batch runner are currently tested only on macOS.

On any platform, you can ask your agent to inspect your installation and help configure the required paths and batch runner.

### Custom configuration

To override automatic discovery or set defaults for new `.do` files, copy [`config.example.json`](./config.example.json) to:

```text
~/.agents/config/stata.json
```

Retain only the settings you need and replace the example values. For example, a non-standard macOS installation could be configured as follows:

```json
{
  "stata_bin": "~/Applications/StataSE.app/Contents/MacOS/stata-se"
}
```

The following settings are supported:

| Setting              | Purpose                                     |
| -------------------- | ------------------------------------------- |
| `stata_bin`          | Path to the Stata executable                |
| `stata_docs_dir`     | Directory containing the Stata PDF manuals  |
| `stata_ado_base_dir` | Directory containing Stata’s base ado files |
| `author`             | Default author for new `.do` file headers   |
| `stata_version`      | Default version declared in new `.do` files |

## Use

The skill activates automatically when a request involves Stata code, Stata files, batch execution, or locally installed Stata documentation. You can also invoke it directly:

```text
/stata
```

Use the skill to write, review, and run Stata code, troubleshoot errors and unexpected behaviour, and consult locally installed Stata documentation.

## Examples

* “Review `analysis.do` for fragile file paths, incorrect merges, and missing-value bugs.”
* “Run this `.do` file, inspect the log, and identify any errors or suspicious results.”
* “Explain why this Stata command is failing and suggest a robust fix.”
* “Check the local Stata documentation for the options supported by `xtreg, fe`.”
