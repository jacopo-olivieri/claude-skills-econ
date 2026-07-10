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

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) || {
  printf 'Cannot resolve wrapper directory: %s\n' "$0" >&2
  exit 2
}
stata_bin=$(python3 "$script_dir/stata_config.py" stata-bin) || exit 2

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
