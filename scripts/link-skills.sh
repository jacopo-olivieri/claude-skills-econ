#!/usr/bin/env bash
set -euo pipefail

# Dev-only helper for maintaining this repo.
#
# Symlinks every skill in this repo's skills/ tree into ~/.claude/skills, so you
# can author skills here (version-controlled) while Claude Code loads them live.
# A `git pull` is then all you need to keep your installed skills up to date.
#
# Moving an existing Claude-only skill into the repo:
#   1. mv ~/.claude/skills/<name>  <repo>/skills/<name>
#   2. bash scripts/link-skills.sh   # replaces the old copy with a symlink
# For a skill shared by Claude and Codex, do not move or delete live state by
# hand. Preview and run scripts/link-shared-skill.sh instead; it archives the
# installed directory and owns rollback for the ~/.agents indirection chain.
#
# Skills under skills/deprecated/ or skills/in-progress/ are intentionally NOT
# linked (they are drafts / retired and should not load).
#
# Two link mechanisms coexist, and this script owns only one of them:
#   1. Direct link (this script): skills/<name> -> ~/.claude/skills/<name>.
#      The default for Claude-only skills (e.g. research-codebase-audit).
#   2. ~/.agents indirection chain (owned elsewhere, e.g. paper-summary):
#      skills/<name> <- ~/.agents/skills/<name> <- ~/.claude/skills/<name>.
#      Codex discovers ~/.agents/skills directly; a ~/.codex shadow is invalid.
# To avoid the two mechanisms fighting, this script SKIPS any skill that is
# already wired through ~/.agents/skills/<name> (a symlink into this repo).
# scripts/link-shared-skill.sh owns guarded migration and rollback for that
# topology. This routine linker never archives or migrates shared skills.

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HOME/.claude/skills"
AGENTS_SKILLS="$HOME/.agents/skills"

# Guard: if $DEST is itself a symlink into this repo, linking would write the
# per-skill symlinks back into skills/. Bail rather than pollute the working copy.
if [ -L "$DEST" ]; then
  resolved="$(readlink "$DEST")"
  case "$resolved" in
    "$REPO"|"$REPO"/*)
      echo "error: $DEST is a symlink into this repo ($resolved)." >&2
      echo "Remove it (rm \"$DEST\") and re-run; the script recreates it as a real dir." >&2
      exit 1
      ;;
  esac
fi

mkdir -p "$DEST"

linked=0
while IFS= read -r -d '' skill_md; do
  src="$(dirname "$skill_md")"
  name="$(basename "$src")"
  target="$DEST/$name"

  # Skip skills wired through the ~/.agents indirection chain: if
  # ~/.agents/skills/<name> is a symlink pointing into this repo, that chain
  # owns the skill's installation. Direct-linking it here would fight the chain.
  agents_link="$AGENTS_SKILLS/$name"
  if [ -L "$agents_link" ]; then
    resolved="$(readlink "$agents_link")"
    case "$resolved" in
      "$REPO"|"$REPO"/*)
        echo "skipped $name (wired via ~/.agents/skills)"
        continue
        ;;
    esac
  fi

  # Replace a real dir of the same name with a symlink to the repo copy.
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    rm -rf "$target"
  fi

  ln -sfn "$src" "$target"
  echo "linked $name -> $src"
  linked=$((linked + 1))
done < <(
  find "$REPO/skills" -name SKILL.md \
    -not -path '*/deprecated/*' \
    -not -path '*/in-progress/*' \
    -not -path '*/node_modules/*' \
    -print0
)

echo "done: $linked skill(s) linked into $DEST"

# Link any Claude subagent definitions (skills/*/agents/claude/*.md) into
# ~/.claude/agents so Claude Code can invoke them by name. These are install-time
# artifacts, not part of the plugin manifest.
AGENTS_DEST="$HOME/.claude/agents"
mkdir -p "$AGENTS_DEST"
agents_linked=0
while IFS= read -r -d '' agent_md; do
  ln -sfn "$agent_md" "$AGENTS_DEST/$(basename "$agent_md")"
  agents_linked=$((agents_linked + 1))
done < <(
  find "$REPO/skills" -path '*/agents/claude/*.md' \
    -not -path '*/deprecated/*' \
    -not -path '*/in-progress/*' \
    -print0
)
echo "done: $agents_linked Claude agent definition(s) linked into $AGENTS_DEST"
