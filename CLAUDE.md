# Repo conventions — claude-skills-econ

This repo is a shareable, plugin-installable collection of Claude Code skills for
economics/research. When working in it:

## Layout
- One skill per folder: `skills/<kebab-name>/SKILL.md`. Folder name == skill name.
- Optional per-skill `scripts/`, `references/`, `GLOSSARY.md`.
- Drafts go in `skills/in-progress/`, retired skills in `skills/deprecated/` —
  both are ignored by `scripts/link-skills.sh` and should NOT be listed in the
  plugin manifest.

## The plugin manifest is hand-maintained
- `.claude-plugin/plugin.json` has a `"skills"` array listing each **published**
  skill's path (e.g. `"./skills/<name>"`). Add a skill's path here when it's
  ready to ship; remove it if you deprecate the skill.

## Adding / editing a skill
1. Write `skills/<name>/SKILL.md` (frontmatter `name` + `description`; see
   `TEMPLATE-SKILL.md`). Make `description` trigger-focused ("Use when …").
2. Add its path to `plugin.json`.
3. Run `bash scripts/link-skills.sh` to symlink it into `~/.claude/skills`.

## Only publish self-authored skills
`~/.claude/skills` on this machine also contains third-party skills installed
from other people's plugins (e.g. Matt Pocock's). **Do not** copy those into this
repo — publish only skills authored here.
