# empirical-research-skills

This repository contains agent skills for economics and empirical research. The skills are designed to work with both Claude Code and Codex.

## Installation

### Recommended: install with `skills.sh`

Run the following command:

```bash
npx skills@latest add jacopo-olivieri/empirical-research-skills
```

The installer will guide you through selecting:

* which skills to install;
* which supported agents—such as Claude Code or Codex—should have access to them.

It will then install and configure the selected skills automatically.

### Manual installation

1. Clone the repository:

```bash
git clone https://github.com/jacopo-olivieri/empirical-research-skills.git
cd empirical-research-skills
```

2. Symlink each skill you want to use into the skills directory recognised by your agent. You can create the symlinks yourself or ask your agent to configure them for you.

## Skills

| Skill | What it does | Invocation |
|-------|--------------|------------|
| [`paper-summary`](./skills/paper-summary) | Summarise an academic research paper. | User-invoked: `/paper-summary` |
| [`research-codebase-audit`](./skills/research-codebase-audit) | Audit an empirical research project codebase for errors, inconsistencies, and reproducibility issues. | User-invoked: `/research-codebase-audit` |
| [`stata`](./skills/stata) | Improve agents' ability to write, run, and troubleshoot Stata. | Model-invoked, or `/stata` |

User-invoked skills run only when you type their slash command. Model-invoked skills are loaded by the agent automatically when the task matches their description, and can also be invoked explicitly by slash command.

Each skill has its own README with usage examples and setup instructions — see the linked directories above.

## Contributing

Suggestions and improvements are welcome. See [`TEMPLATE-SKILL.md`](./TEMPLATE-SKILL.md) and [`AGENTS.md`](./AGENTS.md) if you would like to contribute.

## License

[MIT](./LICENSE) © Jacopo Olivieri. Use, adapt, and share freely.
