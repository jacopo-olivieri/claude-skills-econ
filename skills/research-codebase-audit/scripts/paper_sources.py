#!/usr/bin/env python3
"""Discover and pin a complete LaTeX paper source set.

The root manifest field remains ``paper_source_path``.  For TeX roots this
module follows the local ``\\input``/``\\include`` closure, writes comment-
blanked audit twins under ``audit/_run/paper_twins``, and returns the pinned
four-field manifest entries used by every claims-side consumer.
"""

import hashlib
import re
from pathlib import Path

from blank_tex_comments import blank_lines


MAX_INCLUDE_DEPTH = 32
SOURCE_SET_KEYS = ("source_path", "source_sha256", "audit_path", "audit_sha256")
INCLUDE_RE = re.compile(r"\\(input|include)\s*\{([^{}]+)\}")
UNSUPPORTED_RE = re.compile(
    r"\\(subfile|import|subimport|includefrom|includestandalone)\s*\{"
)
COMMAND_ARG_RE = re.compile(r"\\([A-Za-z@]+)\*?\s*(?:\[[^\]]*\]\s*)?\{([^{}]+)\}")
KNOWN_FILE_COMMANDS = {
    "input", "include", "includegraphics", "bibliography", "addbibresource",
    "documentclass", "usepackage",
}


class PaperSourceError(RuntimeError):
    pass


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _tex_target(base, raw):
    value = raw.strip()
    candidate = (base / value)
    if not candidate.suffix:
        candidate = candidate.with_suffix(".tex")
    return candidate.resolve()


def _visible_line(line):
    """Strip ordinary TeX comments for inclusion discovery."""
    escaped = False
    out = []
    for char in line:
        if char == "%" and not escaped:
            break
        out.append(char)
        if char == "\\":
            escaped = not escaped
        else:
            escaped = False
    return "".join(out)


def discover_source_files(root, max_depth=MAX_INCLUDE_DEPTH):
    root = Path(root).expanduser().resolve()
    if not root.is_file():
        raise PaperSourceError(f"paper source missing: {root}")
    if root.suffix.lower() != ".tex":
        return [root]

    ordered, visited, active = [], set(), set()

    def visit(path, depth):
        if depth > max_depth:
            raise PaperSourceError(
                f"paper include depth exceeds {max_depth} at {path}"
            )
        path = path.resolve()
        if path in active:  # cycle-safe: the file is already in the closure
            return
        if path in visited:
            return
        if not path.is_file():
            raise PaperSourceError(f"included paper source missing: {path}")
        visited.add(path)
        active.add(path)
        ordered.append(path)
        text = path.read_text(encoding="utf-8", errors="strict")
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = _visible_line(raw_line)
            unsupported = UNSUPPORTED_RE.search(line)
            if unsupported:
                raise PaperSourceError(
                    f"unsupported inclusion syntax \\{unsupported.group(1)} "
                    f"at {path}:{line_number}"
                )
            supported_spans = set()
            for match in INCLUDE_RE.finditer(line):
                supported_spans.add(match.span())
                target = _tex_target(path.parent, match.group(2))
                if not target.is_file():
                    raise PaperSourceError(
                        f"included paper source missing at {path}:{line_number}: {target}"
                    )
                visit(target, depth + 1)
            for match in COMMAND_ARG_RE.finditer(line):
                command, argument = match.group(1), match.group(2)
                if command in KNOWN_FILE_COMMANDS or match.span() in supported_spans:
                    continue
                target = _tex_target(path.parent, argument)
                if target.is_file():
                    raise PaperSourceError(
                        f"unsupported inclusion-like macro \\{command} at "
                        f"{path}:{line_number} resolves to {target}"
                    )
        active.remove(path)

    visit(root, 0)
    return ordered


def build_source_set(package_root, manifest):
    """Write twins and return a complete source-set entry list.

    A missing paper field is tolerated for code-only and narrow synthetic runs;
    a present field is always validated fail-closed.
    """
    raw_root = manifest.get("paper_source_path")
    if not raw_root:
        return None
    package_root = Path(package_root).resolve()
    source_root = Path(raw_root).expanduser()
    if not source_root.is_absolute():
        source_root = package_root / source_root
    sources = discover_source_files(source_root)
    twins = package_root / "audit" / "_run" / "paper_twins"
    twins.mkdir(parents=True, exist_ok=True)
    entries = []
    for index, source in enumerate(sources, start=1):
        twin = twins / f"{index:04d}-{source.name}"
        if source.suffix.lower() == ".tex":
            text = source.read_text(encoding="utf-8", errors="strict")
            blanked = "\n".join(blank_lines(text.split("\n")))
            twin.write_text(blanked, encoding="utf-8")
        else:
            twin.write_bytes(source.read_bytes())
        entries.append({
            "source_path": str(source),
            "source_sha256": sha256_file(source),
            "audit_path": str(twin),
            "audit_sha256": sha256_file(twin),
        })
    manifest["paper_source_path"] = entries[0]["source_path"]
    manifest["paper_sha256"] = entries[0]["source_sha256"]
    manifest["paper_audit_path"] = entries[0]["audit_path"]
    manifest["paper_source_set"] = entries
    return entries


def validate_source_set(package_root, manifest):
    entries = manifest.get("paper_source_set")
    if not isinstance(entries, list) or not entries:
        raise PaperSourceError("manifest paper_source_set must be a non-empty array")
    if manifest.get("paper_source_path") != entries[0].get("source_path"):
        raise PaperSourceError("paper_source_path does not match the source-set root")
    if manifest.get("paper_sha256") != entries[0].get("source_sha256"):
        raise PaperSourceError("paper_sha256 does not match the source-set root")
    if manifest.get("paper_audit_path") != entries[0].get("audit_path"):
        raise PaperSourceError("paper_audit_path does not match the source-set root twin")
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or set(entry) != set(SOURCE_SET_KEYS):
            raise PaperSourceError(
                f"paper_source_set entry {index} must have exactly "
                + ", ".join(SOURCE_SET_KEYS)
            )
        source, twin = Path(entry["source_path"]), Path(entry["audit_path"])
        if not source.is_file() or not twin.is_file():
            raise PaperSourceError(
                f"paper_source_set entry {index} names a missing source or twin"
            )
        if sha256_file(source) != entry["source_sha256"]:
            raise PaperSourceError(f"paper source digest mismatch: {source}")
        if sha256_file(twin) != entry["audit_sha256"]:
            raise PaperSourceError(f"paper audit-twin digest mismatch: {twin}")
        if source.suffix.lower() == ".tex":
            if len(source.read_text(encoding="utf-8").split("\n")) != len(
                    twin.read_text(encoding="utf-8").split("\n")):
                raise PaperSourceError(f"paper audit-twin line count mismatch: {twin}")
        expected_root = (Path(package_root).resolve() / "audit" / "_run" / "paper_twins")
        try:
            twin.resolve().relative_to(expected_root)
        except ValueError as exc:
            raise PaperSourceError(
                f"paper audit twin must live under {expected_root}: {twin}"
            ) from exc
    discovered = discover_source_files(entries[0]["source_path"])
    if [str(path) for path in discovered] != [entry["source_path"] for entry in entries]:
        raise PaperSourceError("paper_source_set does not equal the current include closure")
    return entries
