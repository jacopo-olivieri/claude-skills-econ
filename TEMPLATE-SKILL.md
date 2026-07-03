# Skill template

Copy this to start a new skill. A skill is a folder under `skills/` containing a
`SKILL.md`. The folder name **is** the skill name (kebab-case).

```
skills/my-skill-name/
└── SKILL.md            # required
    scripts/            # optional: helper scripts the skill runs
    references/         # optional: docs the skill reads on demand
    GLOSSARY.md         # optional: domain terms the skill relies on
```

## `SKILL.md` skeleton

```markdown
---
name: my-skill-name
description: One line. What it does AND when to use it — e.g. "Use when the user asks to review an econ manuscript / check a paper's claims-evidence alignment."
---

# My Skill Name

What this skill does and the discipline/steps it follows.

## Phase 1 — ...

## Phase 2 — ...
```

## Authoring tips

- **`name`** must match the folder name exactly (kebab-case).
- **`description`** is the trigger. Lead with what it does, then an explicit
  "Use when the user …" clause naming concrete phrases — this is what decides
  whether the skill fires. Keep it to one or two sentences.
- Keep the body **imperative and concrete**. Describe the process, not chatter.
- Put anything long or reference-only (checklists, manuals, examples) under
  `references/` and have the skill read it only when needed.

## After adding a skill

1. Add its path to `.claude-plugin/plugin.json` → `"skills"` (e.g.
   `"./skills/my-skill-name"`), so it ships when others install the plugin.
2. Run `bash scripts/link-skills.sh` to symlink it into `~/.claude/skills` so
   Claude Code loads it locally.
3. Only add skills you authored yourself — see `CLAUDE.md`.
