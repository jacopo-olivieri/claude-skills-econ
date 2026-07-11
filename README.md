# empirical-research-skills

This repository contains agent skills for economics and empirical research.
The skills are designed to work with both Claude Code and Codex.

## Install

**Via [skills.sh](https://skills.sh) (recommended):**

```bash
npx skills@latest add jacopo-olivieri/empirical-research-skills
```

Pick the skills and the agents (Claude Code, Codex, etc.) you want; the
installer wires them up for you.

**Manually:** clone this repo and symlink any skill folder into your skills
directory:

```bash
git clone https://github.com/jacopo-olivieri/empirical-research-skills.git
ln -s "$(pwd)/empirical-research-skills/skills/<name>" ~/.claude/skills/<name>
```

## Skills

| Skill | What it does | How to invoke |
|-------|--------------|---------------|
| [`paper-summary`](./skills/paper-summary) | Evidence-grounded summary of an academic paper: converts the PDF to markdown, analyses it section by section, and returns a structured five-part summary. | `/paper-summary` |
| [`research-codebase-audit`](./skills/research-codebase-audit) | Audits a replication package — paper–code consistency, source-code errors, and package hygiene — and exports an author-facing Excel workbook of findings. | `/research-codebase-audit` |
| [`stata`](./skills/stata) | Writes and safely runs Stata do-files in batch mode, and searches local help files and PDF manuals. Requires a local Stata installation. | automatic on Stata tasks |

## Contributing

Skills are authored in this repo and symlinked into place with
`bash scripts/link-skills.sh`, so a `git pull` keeps installed skills current.
To add a skill, write `skills/<name>/SKILL.md` from
[`TEMPLATE-SKILL.md`](./TEMPLATE-SKILL.md) and add its path to
[`.claude-plugin/plugin.json`](./.claude-plugin/plugin.json). Conventions live
in [`AGENTS.md`](./AGENTS.md).

## License

[MIT](./LICENSE) © Jacopo Olivieri. Use, adapt, and share freely.
