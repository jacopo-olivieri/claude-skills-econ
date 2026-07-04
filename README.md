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

## Developing / maintaining

Skills are authored in this repo and symlinked into `~/.claude/skills`, so a
`git pull` keeps installed skills current.

```bash
# symlink every skill in skills/ into ~/.claude/skills
bash scripts/link-skills.sh
```

To add a skill: create `skills/<name>/SKILL.md` (see
[`TEMPLATE-SKILL.md`](./TEMPLATE-SKILL.md)), add `"./skills/<name>"` to
[`.claude-plugin/plugin.json`](./.claude-plugin/plugin.json), then run the link
script. Conventions live in [`CLAUDE.md`](./CLAUDE.md).

## License

[MIT](./LICENSE) © Jacopo Olivieri. Use, adapt, and share freely.
