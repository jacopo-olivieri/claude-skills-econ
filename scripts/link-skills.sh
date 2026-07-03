#!/usr/bin/env bash
set -euo pipefail

# Dev-only helper for maintaining this repo.
#
# Symlinks every skill in this repo's skills/ tree into ~/.claude/skills, so you
# can author skills here (version-controlled) while Claude Code loads them live.
# A `git pull` is then all you need to keep your installed skills up to date.
#
# Moving an existing skill into the repo:
#   1. mv ~/.claude/skills/<name>  <repo>/skills/<name>
#   2. bash scripts/link-skills.sh   # replaces the old copy with a symlink
#
# Skills under skills/deprecated/ or skills/in-progress/ are intentionally NOT
# linked (they are drafts / retired and should not load).

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HOME/.claude/skills"

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
