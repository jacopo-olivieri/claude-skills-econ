---
name: stata
description: "Work with Stata on this macOS installation: create and safely run `.do` files in batch mode, inspect `.dta` and `.ado` workflows, perform statistical analysis with Stata syntax, and query local help files and PDF manuals efficiently. Use when a task mentions Stata, do-files, Stata datasets, ado-files, batch execution, or local Stata documentation."
---

# Stata

Use this skill to write and run Stata work reproducibly and to consult the local documentation without loading whole manuals unnecessarily.

## Resolve this skill and Stata

Resolve the skill directory from the invoked `SKILL.md` path and reuse it as `SKILL_DIR`; do not assume a fixed installation path.

The optional private config is `~/.agents/config/stata.json`. To create it, copy `config.example.json`, replace the values you intend to configure, and remove every unused key. Partial configs are valid; do not retain placeholder paths, because the resolver validates every path present in the file. The shared resolver applies command-line/environment/config/discovery precedence and fails clearly when a selected value is invalid. Resolve only the resources needed for the current task:

```bash
STATA_BIN="$(python3 "$SKILL_DIR/scripts/stata_config.py" stata-bin)" || exit 2
STATA_DOCS_DIR="$(python3 "$SKILL_DIR/scripts/stata_config.py" docs-dir)" || exit 2
STATA_ADO_BASE_DIR="$(python3 "$SKILL_DIR/scripts/stata_config.py" ado-base-dir)" || exit 2
STATA_AUTHOR="$(python3 "$SKILL_DIR/scripts/stata_config.py" author)" || exit 2
STATA_VERSION="$(python3 "$SKILL_DIR/scripts/stata_config.py" stata-version)" || exit 2
```

Use `scripts/run_stata_do.sh` for do-files. Use the resolved `$STATA_BIN` directly only for one-off commands such as:

```bash
"$STATA_BIN" -q "help regress"
```

## Create do-files

Create `.do` files as UTF-8 text. Resolve `STATA_AUTHOR` and `STATA_VERSION` as above, then substitute their values for `<author>` and `<stata-version>` in this neutral task-specific header:

```stata
********************************************************************************
* PROJECT: <project name>
* AUTHOR: <author>
* AIM: <concise description of this do-file's purpose>
* DATE CREATED: <YYYY-MM-DD>
* LAST MODIFIED: <YYYY-MM-DD>
* INPUTS:
*   - <input dataset or source>
* OUTPUTS:
*   - <output dataset, table, or figure>
********************************************************************************

* Setup
version <stata-version>
clear all
capture log close
set more off, perm
set linesize 255
set excelxlsxlargefile on

* User-written packages used below
capture which esttab
if _rc ssc install estout, replace
```

Conventions:

- Keep the full `PROJECT` / `AUTHOR` / `AIM` / `INPUTS` / `OUTPUTS` header and update its content and dates.
- Keep one command per line, or use `///` for continuation.
- Use `*` at line start, `//` inline, and `/* */` for block comments.
- Use double quotes for strings and paths.
- Prefer project globals such as `$user/...` for stable project paths.
- Use factor variables where appropriate: `i.group`, `c.age`, and `i.group#c.age`.
- Guard user-written commands at the point of use with `capture which command` and install the providing package only when `_rc` is nonzero.

### Observation filters and missing values

Stata numeric missing values compare as larger than every nonmissing number, so guard upper-tail conditions explicitly:

```stata
summarize wage if age > 30 & !missing(age)
list in 1/10
```

### Locals and globals

Define a local with `local name value` and expand it with backtick–apostrophe syntax, `` `name' ``. Define or read a global with `global name value` and `$name`. Prefer locals for temporary values: locals die at the end of the batch run, whereas globals can leak state across commands in a session.

### Merges

After every `merge`, inspect `_merge` before dropping it—for example, `tabulate _merge` followed by an explicit assertion or handling rule for unmatched observations.

## Run do-files safely

Run do-files through the bundled wrapper, which resolves the binary, runs from the do-file directory, removes stale logs, and treats Stata error markers as failures even when Stata itself exits zero:

```bash
"$SKILL_DIR/scripts/run_stata_do.sh" /absolute/path/to/analysis.do
```

The wrapper exits nonzero and prints the log tail when it finds `r(<number>);` or when Stata fails to produce a fresh log.

If the wrapper cannot be used, run from the do-file directory, then inspect the log explicitly; the process status alone is not proof of success:

```bash
"$STATA_BIN" -q -b do analysis.do
if grep -Eq '^r\([0-9]+\);' analysis.log; then
  tail -n 80 analysis.log >&2
  exit 1
fi
```

## Consult Stata documentation

Resolve `STATA_DOCS_DIR` and `STATA_ADO_BASE_DIR` with `stata_config.py` as shown above. Use `references/docs_index.md` to choose a PDF. Follow this order.

### 1. Read the command help file

Check the installed `.sthlp` file first; it is the fastest source for syntax and options:

```bash
# General pattern: $STATA_ADO_BASE_DIR/<letter>/<command>.sthlp
sed -n '1,240p' "$STATA_ADO_BASE_DIR/r/regress.sthlp"
```

The first directory letter normally matches the command name. Help files contain SMCL markup, so expect braces and directives in the raw text. For derivations, methods, or formulas, continue to the PDF manuals.

### 2. Search one named PDF with pdfgrep

Choose the manual from the index, then search it directly:

```bash
pdfgrep -n -i -C 3 "xtreg" "$STATA_DOCS_DIR/xt.pdf"
```

Only if the index cannot identify a likely manual, fall back to an all-manual scan, which takes roughly 45 seconds:

```bash
pdfgrep -Hn -i -m 20 "search term" "$STATA_DOCS_DIR"/*.pdf
```

Common manuals:

- `r.pdf` — Base Reference: `regress`, `logit`, `summarize`, `tabulate`, `correlate`, `test`, `predict`
- `d.pdf` — Data Management: `import`, `export`, `reshape`, `merge`, `append`
- `u.pdf` — User's Guide: syntax, data types, do-files, estimation basics
- `g.pdf` — Graphics
- `ts.pdf` — Time Series
- `xt.pdf` — Longitudinal and panel data
- `p.pdf` — Programming, ado-files, and macros
- `i.pdf` — Combined index

### 3. Get page-numbered context with the bundled script

Use the script after selecting one manual:

```bash
python3 "$SKILL_DIR/scripts/search_stata_docs.py" "merge" --pdf d.pdf --context 2 --max-results 15
python3 "$SKILL_DIR/scripts/search_stata_docs.py" "xtreg" --pdf xt.pdf --pages 1-200
```

Searches are literal and case-insensitive by default. Use `--regex` for regular expressions and `--case-sensitive` when capitalization matters. An all-manual invocation remains available but prints a warning because it is slow.

### 4. Convert targeted pages with Docling

When search context is insufficient, extract only the relevant page or pages to
temporary PDFs, then convert those small files with Docling. This avoids
converting an entire manual for a narrow question. `pdfseparate` page numbers
are one-based:

```bash
pdfseparate -f 121 -l 121 "$STATA_DOCS_DIR/d.pdf" /tmp/stata-manual-page-%d.pdf
docling /tmp/stata-manual-page-121.pdf \
  --to md \
  --no-ocr \
  --output /tmp/stata-manual-snippets
```

For a few adjacent pages, extract them and convert each page separately. Read
the resulting Markdown files in order.

### 5. Read known PDF pages

When the prior steps identify exact pages, use the available PDF reading tool with a page range. Avoid loading a complete manual.

## Check tools at use time

Do not rely on a cached installation table. Check each dependency when needed:

```bash
command -v pdfgrep >/dev/null 2>&1 || brew install pdfgrep
command -v docling >/dev/null 2>&1 || uv tool install docling
test -x "$STATA_BIN"
```

For the search script, check the Python module and use an ephemeral dependency when absent:

```bash
if python3 -c 'import pdfplumber' >/dev/null 2>&1; then
  python3 "$SKILL_DIR/scripts/search_stata_docs.py" "merge" --pdf d.pdf
else
  uv run --with pdfplumber python3 "$SKILL_DIR/scripts/search_stata_docs.py" "merge" --pdf d.pdf
fi
```

## References

Read `references/docs_index.md` when selecting the most relevant manual.
