#!/usr/bin/env python3
"""Blank LaTeX comments while preserving line numbers.

Produces a copy of a .tex file in which comment content is removed so that only
PDF-visible text is audited, without shifting any line number:

- text after an unescaped ``%`` on a line is removed (the ``%`` itself too);
- lines inside ``\\begin{comment}``/``\\end{comment}`` become empty lines;
- ``%`` inside ``verbatim``/``lstlisting``/``minted`` environments is kept
  (it is visible content there).

The output always has exactly as many lines as the input; the script verifies
this and exits nonzero otherwise.

Usage:
    blank_tex_comments.py INPUT.tex [-o OUTPUT.tex]

Default output path: INPUT with extension replaced by ``.audit.tex``.
"""

import argparse
import re
import sys
from pathlib import Path

VERBATIM_ENVS = ("verbatim", "verbatim*", "lstlisting", "minted", "Verbatim")

BEGIN_RE = re.compile(r"\\begin\{([A-Za-z*]+)\}")
END_RE = re.compile(r"\\end\{([A-Za-z*]+)\}")


def first_unescaped_percent(line: str) -> int:
    """Index of the first ``%`` not preceded by a backslash, or -1."""
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\":
            i += 2  # skip escaped character (\% \\ etc.)
            continue
        if ch == "%":
            return i
        i += 1
    return -1


def strip_comment(s: str) -> str:
    idx = first_unescaped_percent(s)
    return s[:idx] if idx >= 0 else s


def blank_lines(lines):
    out = []
    in_comment_env = False
    verbatim_stack = []
    for line in lines:
        stripped = line.rstrip("\n")
        if in_comment_env:
            if re.search(r"\\end\{comment\}", stripped):
                in_comment_env = False
            out.append("")
            continue

        if verbatim_stack:
            m = END_RE.search(stripped)
            if m and m.group(1) == verbatim_stack[-1]:
                verbatim_stack.pop()
                # text after the closing tag is ordinary LaTeX again
                out.append(stripped[: m.end()] + strip_comment(stripped[m.end():]))
            else:
                out.append(stripped)
            continue

        # Outside verbatim/comment envs, comment content is dead — env markers
        # inside a comment (e.g. "% \begin{comment}") must NOT toggle state.
        visible = strip_comment(stripped)

        if re.search(r"\\begin\{comment\}", visible):
            if not re.search(r"\\end\{comment\}", visible):
                in_comment_env = True
            out.append("")
            continue

        m = BEGIN_RE.search(visible)
        if m and m.group(1) in VERBATIM_ENVS:
            env = m.group(1)
            # same-line close? (\begin{verbatim}...\end{verbatim}) — do not push
            m_end = END_RE.search(stripped[m.end():])
            if m_end and m_end.group(1) == env:
                close = m.end() + m_end.end()
                out.append(stripped[:close] + strip_comment(stripped[close:]))
            else:
                verbatim_stack.append(env)
                # any % here sits after \begin{env} (else the begin would have
                # been comment-stripped), i.e. it is verbatim content — keep raw
                out.append(stripped)
            continue

        out.append(visible)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    args = ap.parse_args()

    if not args.input.is_file():
        print(f"ERROR: input not found: {args.input}", file=sys.stderr)
        return 2
    output = args.output or args.input.with_suffix(".audit.tex")
    if output.resolve() == args.input.resolve():
        print("ERROR: output path equals input path", file=sys.stderr)
        return 2

    src = args.input.read_text(encoding="utf-8", errors="strict")
    lines = src.split("\n")
    blanked = blank_lines(lines)

    if len(blanked) != len(lines):
        print(
            f"ERROR: line count changed ({len(lines)} -> {len(blanked)}); "
            "refusing to write output",
            file=sys.stderr,
        )
        return 1

    output.write_text("\n".join(blanked), encoding="utf-8")
    print(f"OK: wrote {output} ({len(blanked)} lines, count preserved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
