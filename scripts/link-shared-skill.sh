#!/usr/bin/env bash
set -euo pipefail

# Safely move one repo-owned skill onto the shared discovery chain:
#
#   <repo>/skills/<name> <- ~/.agents/skills/<name>
#                           <- ~/.claude/skills/<name>
#
# Codex discovers ~/.agents/skills directly, so a separate Codex link would be
# a shadow and is refused. Existing real installations are archived before the
# pointer changes. Routine development linking remains in link-skills.sh.

usage() {
  cat <<'EOF'
usage: link-shared-skill.sh [--home PATH] [--preview] REPO_SKILL
       link-shared-skill.sh [--home PATH] [--preview] --rollback ARCHIVE REPO_SKILL

REPO_SKILL must be a committed skill directory in a clean Git checkout.
--home is intended for tests; it defaults to $HOME.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

path_exists() {
  [ -e "$1" ] || [ -L "$1" ]
}

home="${HOME:-}"
preview=0
rollback=""
source_arg=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --home)
      [ "$#" -ge 2 ] || die "--home requires a path"
      home="$2"
      shift 2
      ;;
    --preview)
      preview=1
      shift
      ;;
    --rollback)
      [ "$#" -ge 2 ] || die "--rollback requires an archive path"
      rollback="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      die "unknown option: $1"
      ;;
    *)
      [ -z "$source_arg" ] || die "expected exactly one REPO_SKILL"
      source_arg="$1"
      shift
      ;;
  esac
done

[ -n "$source_arg" ] || { usage >&2; exit 2; }
[ -n "$home" ] || die "HOME is unset; pass --home explicitly"
case "$home" in
  /*) ;;
  *) die "home must be an absolute path: $home" ;;
esac
[ "$home" != "/" ] || die "refusing to use the filesystem root as home"
home="${home%/}"

[ -d "$source_arg" ] || die "repo skill source is missing or not a directory: $source_arg"
[ ! -L "$source_arg" ] || die "repo skill source must be a real directory: $source_arg"
[ -f "$source_arg/SKILL.md" ] || die "repo skill source has no SKILL.md: $source_arg"
source="$(cd "$source_arg" && pwd -P)"
name="$(basename "$source")"

repo="$(git -C "$source" rev-parse --show-toplevel 2>/dev/null)" || \
  die "repo skill source is not inside a Git checkout: $source"
repo="$(cd "$repo" && pwd -P)"
case "$source" in
  "$repo"/*) relative_source="${source#"$repo"/}" ;;
  *) die "repo skill source is outside its Git checkout: $source" ;;
esac
git -C "$repo" cat-file -e "HEAD:$relative_source/SKILL.md" 2>/dev/null || \
  die "repo skill source is not tracked at HEAD: $relative_source/SKILL.md"
[ -z "$(git -C "$repo" status --porcelain --untracked-files=all)" ] || \
  die "Git checkout is dirty; commit and review it before changing live links: $repo"

agents_target="$home/.agents/skills/$name"
claude_target="$home/.claude/skills/$name"
codex_shadow="$home/.codex/skills/$name"
command_shadow="$home/.claude/commands/$name"
command_file_shadow="$home/.claude/commands/$name.md"
backup_root="$home/.agents/backups"

path_exists "$codex_shadow" && die "Codex shadow exists; remove or archive it first: $codex_shadow"
path_exists "$command_shadow" && die "legacy command shadow exists; remove or archive it first: $command_shadow"
path_exists "$command_file_shadow" && die "legacy command shadow exists; remove or archive it first: $command_file_shadow"

agents_state="absent"
agents_link=""
if [ -L "$agents_target" ]; then
  agents_state="symlink"
  agents_link="$(readlink "$agents_target")"
  case "$agents_link" in
    /*) ;;
    *) die "relative agents symlink is unsafe; replace it with an absolute link: $agents_target -> $agents_link" ;;
  esac
  [ "$agents_link" = "$source" ] || \
    die "unexpected agents symlink target: $agents_target -> $agents_link"
elif [ -d "$agents_target" ]; then
  agents_state="directory"
elif path_exists "$agents_target"; then
  die "unexpected agents target is not a directory or symlink: $agents_target"
fi

claude_state="absent"
claude_link=""
if [ -L "$claude_target" ]; then
  claude_state="symlink"
  claude_link="$(readlink "$claude_target")"
  case "$claude_link" in
    /*) ;;
    *) die "relative Claude symlink is unsafe: $claude_target -> $claude_link" ;;
  esac
  if [ "$claude_link" != "$agents_target" ] && [ "$claude_link" != "$source" ]; then
    die "unexpected Claude symlink target: $claude_target -> $claude_link"
  fi
elif path_exists "$claude_target"; then
  die "unexpected Claude target is not a symlink: $claude_target"
fi

if [ -n "$rollback" ]; then
  [ "$(dirname "$rollback")" = "$backup_root" ] || \
    die "rollback archive must be directly inside $backup_root"
  case "$(basename "$rollback")" in
    "$name"-pre-repo-*) ;;
    *) die "rollback archive name does not match skill $name: $rollback" ;;
  esac
  [ -d "$backup_root" ] && [ ! -L "$backup_root" ] || \
    die "rollback backup root is missing or unsafe: $backup_root"
  [ -d "$rollback" ] && [ ! -L "$rollback" ] || \
    die "rollback archive is missing or unsafe: $rollback"
  [ "$agents_state" = "symlink" ] && [ "$agents_link" = "$source" ] || \
    die "rollback refused: agents link no longer matches the repo source"
  [ "$claude_state" = "symlink" ] && [ "$claude_link" = "$agents_target" ] || \
    die "rollback refused: Claude link no longer matches the shared agents pointer"

  if [ "$preview" -eq 1 ]; then
    echo "preview: restore $rollback -> $agents_target"
    echo "preview: preserve $claude_target -> $agents_target"
    exit 0
  fi

  restore_repo_link_on_rollback_error() {
    status=$?
    trap - ERR
    if ! path_exists "$agents_target"; then
      if ! ln -s "$source" "$agents_target"; then
        echo "critical: rollback failed and could not restore $agents_target -> $source" >&2
      fi
    fi
    exit "$status"
  }
  trap restore_repo_link_on_rollback_error ERR
  rm "$agents_target"
  mv "$rollback" "$agents_target"
  trap - ERR
  echo "rollback complete: restored $agents_target from $rollback"
  echo "Claude link preserved: $claude_target -> $agents_target"
  exit 0
fi

archive=""
if [ "$agents_state" = "directory" ]; then
  timestamp="${LINK_SHARED_TIMESTAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
  case "$timestamp" in
    *[!A-Za-z0-9._-]*|'') die "unsafe archive timestamp: $timestamp" ;;
  esac
  if path_exists "$backup_root" && { [ ! -d "$backup_root" ] || [ -L "$backup_root" ]; }; then
    die "backup root is not a real directory: $backup_root"
  fi
  archive="$backup_root/$name-pre-repo-$timestamp"
  suffix=0
  while path_exists "$archive"; do
    suffix=$((suffix + 1))
    archive="$backup_root/$name-pre-repo-$timestamp-$suffix"
  done
fi

claude_needs_repair=0
if [ "$claude_state" = "absent" ] || [ "$claude_link" = "$source" ]; then
  claude_needs_repair=1
fi

if [ "$preview" -eq 1 ]; then
  if [ -n "$archive" ]; then
    echo "preview: archive $agents_target -> $archive"
    echo "rollback source: $archive"
  else
    echo "preview: no installed directory needs archiving"
    echo "rollback source: none"
  fi
  [ "$agents_state" = "symlink" ] || echo "preview: link $agents_target -> $source"
  [ "$claude_needs_repair" -eq 0 ] || echo "preview: link $claude_target -> $agents_target"
  exit 0
fi

if [ "$agents_state" = "symlink" ] && [ "$claude_needs_repair" -eq 0 ]; then
  echo "already linked: $agents_target -> $source"
  echo "already linked: $claude_target -> $agents_target"
  echo "rollback source: none"
  exit 0
fi

mkdir -p "$(dirname "$agents_target")" "$(dirname "$claude_target")"
[ -z "$archive" ] || mkdir -p "$backup_root"

restore_on_error() {
  status=$?
  trap - ERR
  if [ "$agents_state" = "directory" ] && [ -n "$archive" ] && [ -d "$archive" ]; then
    [ ! -L "$agents_target" ] || rm -f "$agents_target"
    [ -e "$agents_target" ] || mv "$archive" "$agents_target"
  elif [ "$agents_state" = "absent" ] && [ -L "$agents_target" ]; then
    rm -f "$agents_target"
  fi
  if [ "$claude_state" = "absent" ]; then
    [ ! -L "$claude_target" ] || rm -f "$claude_target"
  elif [ "$claude_state" = "symlink" ]; then
    ln -sfn "$claude_link" "$claude_target"
  fi
  exit "$status"
}
trap restore_on_error ERR

if [ "$agents_state" = "directory" ]; then
  mv "$agents_target" "$archive"
fi
if [ "$agents_state" != "symlink" ]; then
  ln -s "$source" "$agents_target"
fi
if [ "$claude_needs_repair" -eq 1 ]; then
  ln -sfn "$agents_target" "$claude_target"
fi

if [ ! -L "$agents_target" ] || [ "$(readlink "$agents_target")" != "$source" ]; then
  echo "error: post-migration agents link verification failed: $agents_target" >&2
  false
fi
if [ ! -L "$claude_target" ] || [ "$(readlink "$claude_target")" != "$agents_target" ]; then
  echo "error: post-migration Claude link verification failed: $claude_target" >&2
  false
fi

trap - ERR
if [ -n "$archive" ]; then
  echo "archived installed directory: $agents_target -> $archive"
  echo "rollback source: $archive"
else
  echo "rollback source: none"
fi
echo "linked shared skill: $agents_target -> $source"
if [ "$claude_link" = "$source" ]; then
  echo "repaired Claude link: $claude_target -> $agents_target"
else
  echo "Claude link: $claude_target -> $agents_target"
fi
