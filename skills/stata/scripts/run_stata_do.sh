#!/usr/bin/env bash
set -u

usage() {
  printf 'Usage: %s path/to/file.do\n' "${0##*/}" >&2
}

if [ "$#" -ne 1 ]; then
  usage
  exit 2
fi

input_path=$1
if [ ! -f "$input_path" ]; then
  printf 'Do-file does not exist: %s\n' "$input_path" >&2
  exit 2
fi

do_dir=$(cd "$(dirname "$input_path")" && pwd -P) || {
  printf 'Cannot resolve do-file directory: %s\n' "$input_path" >&2
  exit 2
}
do_name=$(basename "$input_path")
log_name=${do_name%.do}.log
log_path=$do_dir/$log_name

resolve_stata_bin() {
  local known_path candidate
  local -a candidates

  if [ -n "${STATA_BIN:-}" ]; then
    if [ -x "$STATA_BIN" ]; then
      printf '%s\n' "$STATA_BIN"
      return 0
    fi
    printf 'STATA_BIN is not executable: %s\n' "$STATA_BIN" >&2
    return 1
  fi

  if command -v stata >/dev/null 2>&1; then
    command -v stata
    return 0
  fi

  known_path=/Applications/Stata/StataSE.app/Contents/MacOS/stata-se
  if [ -x "$known_path" ]; then
    printf '%s\n' "$known_path"
    return 0
  fi

  shopt -s nullglob
  candidates=(/Applications/Stata*/Stata{SE,MP,BE}.app/Contents/MacOS/stata-*)
  shopt -u nullglob
  for candidate in "${candidates[@]}"; do
    if [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  printf 'Could not resolve an executable Stata binary. Set STATA_BIN explicitly.\n' >&2
  return 1
}

stata_bin=$(resolve_stata_bin) || exit 2

rm -f "$log_path"

(
  cd "$do_dir" || exit 2
  "$stata_bin" -q -b do "$do_name"
)
stata_status=$?

if [ ! -f "$log_path" ]; then
  printf 'Stata did not produce a fresh log: %s\n' "$log_path" >&2
  exit 1
fi

if grep -Eq '^r\([0-9]+\);' "$log_path"; then
  printf 'Stata reported an error in %s:\n' "$log_path" >&2
  grep -E '^r\([0-9]+\);' "$log_path" >&2
  tail -n 80 "$log_path" >&2
  exit 1
fi

if [ "$stata_status" -ne 0 ]; then
  printf 'Stata exited with status %s. Log tail:\n' "$stata_status" >&2
  tail -n 80 "$log_path" >&2
  exit "$stata_status"
fi

exit 0
