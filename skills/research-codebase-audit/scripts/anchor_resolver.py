#!/usr/bin/env python3
"""Shared exact quote-to-paper-anchor resolver for U7 claim handoffs."""

import re
from pathlib import Path


ANCHOR_RE = re.compile(r"^(.*):(\d+)(?:\s*[–—-]\s*(\d+))?$")


class AnchorError(ValueError):
    pass


def parse_anchor(value):
    match = ANCHOR_RE.fullmatch(str(value or "").strip().strip("`"))
    if not match:
        raise AnchorError(f"anchor must be path:line or path:start-end, got {value!r}")
    start = int(match.group(2))
    end = int(match.group(3) or start)
    if start < 1 or end < start:
        raise AnchorError(f"invalid anchor line range {start}-{end}")
    if end - start + 1 > 5:
        raise AnchorError("anchor range may span at most five source lines")
    return match.group(1), start, end


def _entry_aliases(entry, package_root=None):
    aliases = set()
    for key in ("source_path", "audit_path"):
        path = Path(entry[key])
        aliases.update({str(path), path.as_posix(), path.name})
        if package_root is not None:
            try:
                rel = path.resolve().relative_to(Path(package_root).resolve())
                aliases.update({str(rel), rel.as_posix()})
            except ValueError:
                pass
    return aliases


def source_entry(source_set, file_value, package_root=None):
    matches = [entry for entry in source_set
               if file_value in _entry_aliases(entry, package_root)]
    if len(matches) != 1:
        raise AnchorError(
            f"anchor file {file_value!r} resolves to {len(matches)} paper source files"
        )
    return matches[0]


def _normalize_with_map(text, offset=0):
    normalized, raw_positions = [], []
    in_space = False
    for index, char in enumerate(text):
        if char.isspace():
            if normalized and not in_space:
                normalized.append(" ")
                raw_positions.append(offset + index)
            in_space = True
        else:
            normalized.append(char)
            raw_positions.append(offset + index)
            in_space = False
    if normalized and normalized[-1] == " ":
        normalized.pop()
        raw_positions.pop()
    return "".join(normalized), raw_positions


def normalize_quote(quote):
    return re.sub(r"\s+", " ", str(quote or "")).strip()


def _line_col(text, index):
    return text.count("\n", 0, index) + 1, index - text.rfind("\n", 0, index)


def resolve_quote(source_set, anchor, quote, package_root=None):
    file_value, start_line, end_line = parse_anchor(anchor)
    entry = source_entry(source_set, file_value, package_root)
    text = Path(entry["audit_path"]).read_text(encoding="utf-8", errors="strict")
    lines = text.splitlines(keepends=True)
    if start_line > len(lines) or end_line > len(lines):
        raise AnchorError(
            f"anchor {anchor!r} exceeds {len(lines)} lines in {file_value}"
        )
    start_offset = sum(len(line) for line in lines[:start_line - 1])
    end_offset = sum(len(line) for line in lines[:end_line])
    haystack, positions = _normalize_with_map(text[start_offset:end_offset], start_offset)
    needle = normalize_quote(quote)
    if not needle:
        raise AnchorError("quote must be non-empty")
    hits, cursor = [], 0
    while True:
        found = haystack.find(needle, cursor)
        if found < 0:
            break
        hits.append(found)
        cursor = found + 1
    if len(hits) != 1:
        raise AnchorError(
            f"quote resolves to {len(hits)} occurrences in {anchor!r}; exactly one required"
        )
    hit = hits[0]
    raw_start = positions[hit]
    raw_end = positions[hit + len(needle) - 1] + 1
    start_line_actual, start_column = _line_col(text, raw_start)
    end_line_actual, end_column = _line_col(text, raw_end)
    return {
        "source_path": entry["source_path"],
        "audit_path": entry["audit_path"],
        "start_char": raw_start,
        "end_char": raw_end,
        "start_line": start_line_actual,
        "start_column": start_column,
        "end_line": end_line_actual,
        "end_column": end_column,
    }


def contains(container, contained):
    return (Path(container["source_path"]).resolve() ==
            Path(contained["source_path"]).resolve()
            and container["start_char"] <= contained["start_char"]
            and container["end_char"] >= contained["end_char"])
