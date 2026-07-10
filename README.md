# claude-skills-econ

My personal collection of [Claude Code](https://claude.com/claude-code) skills
for **economics and empirical research** — the small, composable workflows I use
for reviewing papers, wrangling data, and writing. Built to be shared, adapted,
and made your own.

> Skills are still being added. See [`TEMPLATE-SKILL.md`](./TEMPLATE-SKILL.md)
> for the format if you'd like to contribute or fork.

## Install

**Via [skills.sh](https://skills.sh) (recommended):**

```bash
npx skills@latest add jacopo-olivieri/claude-skills-econ
```

Pick the skills and the agents (Claude Code, etc.) you want; the installer wires
them up for you.

**Manually:** clone this repo and copy or symlink any skill folder into your
skills directory:

```bash
git clone https://github.com/jacopo-olivieri/claude-skills-econ.git
ln -s "$(pwd)/claude-skills-econ/skills/<name>" ~/.claude/skills/<name>
```

## What's inside

| Skill | What it does |
|-------|--------------|
| [`research-codebase-audit`](./skills/research-codebase-audit) | Static-first audit of a replication package: paper-code consistency, source-code errors, and package hygiene via parallel subagents writing to lint-gated registers, exported to an author-facing Excel workbook. User-invoked (`/research-codebase-audit`). |
| [`stata`](./skills/stata) | Write and safely run Stata do-files, resolve local installation paths, inspect installed `.sthlp` files, and search named PDF manuals. |

## Developing / maintaining

Skills are authored in this repo and symlinked into `~/.claude/skills`, so a
`git pull` keeps installed skills current.

```bash
# symlink every skill in skills/ into ~/.claude/skills
bash scripts/link-skills.sh
```

Skills used by both Claude and Codex can instead share one repo-owned copy via
`~/.agents/skills`. The guarded migration helper archives an existing installed
directory, makes the `~/.agents` link, and keeps Claude pointed through that
single rollback seam:

```bash
# The checkout must be clean and the skill must be tracked at HEAD.
bash scripts/link-shared-skill.sh --preview skills/<name>
bash scripts/link-shared-skill.sh skills/<name>

# Use the exact archive path printed as "rollback source" if rollback is needed.
bash scripts/link-shared-skill.sh --rollback ~/.agents/backups/<archive> skills/<name>
```

The helper refuses unexpected agent, Claude, Codex, or legacy-command state
before making changes. It never deletes the archive. Once linked, both harnesses
execute the active checkout directly: branch switches and uncommitted edits are
immediately live. Cut over only from a clean, reviewed commit, retain the archive
until fresh Claude and Codex sessions pass, and use `scripts/link-skills.sh` only
for routine linking—it deliberately skips skills already owned by the shared
chain.

The Stata skill keeps its default tests host-independent. Its real-machine
checks are explicit and non-destructive: they run do-files only under pytest's
temporary directory, make no package or permanent preference changes, and are
skipped unless enabled.

```bash
# Portable default (the live module skips before resolving local resources)
uv run --no-project --with pytest -- pytest skills/stata/scripts/tests/

# Opt-in smoke test for the configured or discovered Stata binary and manuals
STATA_LIVE_TESTS=1 uv run --no-project --with pytest --with pdfplumber -- \
  pytest skills/stata/scripts/tests/test_live_stata.py
```

To add a skill: create `skills/<name>/SKILL.md` (see
[`TEMPLATE-SKILL.md`](./TEMPLATE-SKILL.md)), add `"./skills/<name>"` to
[`.claude-plugin/plugin.json`](./.claude-plugin/plugin.json), then run the link
script. Conventions live in [`AGENTS.md`](./AGENTS.md).

## License

[MIT](./LICENSE) © Jacopo Olivieri. Use, adapt, and share freely.
