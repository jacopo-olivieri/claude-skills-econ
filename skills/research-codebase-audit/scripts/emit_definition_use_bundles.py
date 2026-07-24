#!/usr/bin/env python3
"""Emit mechanical Stata definition/use candidates at certified b3d.

The detector deliberately recognizes surface shape, not semantic error.  It
scans only ``PACKAGE_ROOT/do/**/*.do`` for a derived flag producer followed by
a mutating consumer whose ``if`` guard mentions the flag and at least one
additional top-level conjunct.  Standard candidates must be mapped into the
code recheck; ``recode`` consumers are advisory only.

Usage:
    emit_definition_use_bundles.py PACKAGE_ROOT [--audit-dir audit] [-o OUTPUT.md]
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from source_projection import audited_regular_files


STANDARD_MUTATORS = {"replace", "drop", "keep", "merge", "collapse"}
BOOLEAN_RHS_RE = re.compile(r"(?:==|!=|~=|<=|>=|\binlist\s*\(|\binrange\s*\()",
                            re.IGNORECASE)
GEN_RE = re.compile(
    r"^\s*(?:capture\s+|cap\s+)?(?:quietly\s*:?[ \t]*|qui\s*:?[ \t]*)?"
    r"(?:generate|gen)\s+"
    r"(?:(?:byte|int|long|float|double|str\d*|strL)\s+)?"
    r"(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<rhs>.+)$",
    re.IGNORECASE,
)
REPLACE_TARGET_RE = re.compile(
    r"^\s*(?:capture\s+|cap\s+)?(?:quietly\s*:?[ \t]*|qui\s*:?[ \t]*)?"
    r"replace\s+(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*=",
    re.IGNORECASE,
)
CONSTANT_RE = re.compile(
    r"(?:[-+]?(?:\d+(?:\.\d*)?|\.\d+)|\.|\"[^\"]*\"|'[^']*')\s*$"
)


def short_hash(identity):
    """Return the stable short digest used in a Bundle ID."""
    payload = "\x1f".join(str(v) for v in identity).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def _strip_comments(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    out, quote, i = [], None, 0
    while i < len(text):
        ch = text[i]
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch == '"':
            quote = ch
            out.append(ch)
            i += 1
            continue
        if text[i:i + 2] == "//":
            break
        out.append(ch)
        i += 1
    return "".join(out).strip()


def _mask_block_comments(raw_lines):
    """Mask block comments while carrying their state across raw lines."""
    masked_lines = []
    in_block = False
    for raw in raw_lines:
        if not in_block and re.match(r"^\s*\*", raw):
            masked_lines.append(raw)
            continue
        masked = list(raw)
        index = 0
        quote = None
        while index < len(raw):
            marker = raw[index:index + 2]
            if in_block:
                masked[index] = " "
                if marker == "*/":
                    if index + 1 < len(masked):
                        masked[index + 1] = " "
                    in_block = False
                    index += 2
                else:
                    index += 1
            elif quote:
                if raw[index] == quote:
                    quote = None
                index += 1
            elif raw[index] == '"':
                quote = raw[index]
                index += 1
            elif marker == "//":
                break
            elif marker == "/*":
                masked[index] = " "
                if index + 1 < len(masked):
                    masked[index + 1] = " "
                in_block = True
                index += 2
            else:
                index += 1
        masked_lines.append("".join(masked))
    return masked_lines


def _logical_lines(raw_lines):
    """Return continuation-joined statements with their first raw line."""
    logical, parts, code_parts, start = [], [], [], None
    masked_lines = _mask_block_comments(raw_lines)
    for lineno, (raw, masked) in enumerate(zip(raw_lines, masked_lines), start=1):
        line = raw.rstrip("\n")
        code_line = masked.rstrip("\n")
        if start is None:
            start = lineno
        continued = bool(re.search(r"///\s*$", line))
        parts.append(re.sub(r"///\s*$", "", line).strip())
        code_parts.append(re.sub(r"///\s*$", "", code_line).strip())
        if continued:
            continue
        raw_text = " ".join(p for p in parts if p).strip()
        code_text = " ".join(p for p in code_parts if p).strip()
        logical.append({"line": start, "raw": raw_text,
                        "code": _strip_comments(code_text)})
        parts, code_parts, start = [], [], None
    if parts:
        raw_text = " ".join(p for p in parts if p).strip()
        code_text = " ".join(p for p in code_parts if p).strip()
        logical.append({"line": start, "raw": raw_text,
                        "code": _strip_comments(code_text)})
    return logical


def _strip_outer_parens(expr):
    s = expr.strip()
    while s.startswith("(") and s.endswith(")"):
        depth, quote, closes_at_end = 0, None, False
        for i, ch in enumerate(s):
            if quote:
                if ch == quote:
                    quote = None
                continue
            if ch == '"':
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    closes_at_end = i == len(s) - 1
                    break
        if not closes_at_end:
            break
        s = s[1:-1].strip()
    return s


def top_level_conjuncts(expr):
    """Split a Stata condition on ``&`` only at parenthesis depth zero."""
    s = _strip_outer_parens(expr)
    parts, cur, depth, quote = [], [], 0, None
    for ch in s:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch == '"':
            quote = ch
            cur.append(ch)
        elif ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            cur.append(ch)
        elif ch == "&" and depth == 0:
            part = "".join(cur).strip()
            if part:
                parts.append(part)
            cur = []
        else:
            cur.append(ch)
    part = "".join(cur).strip()
    if part:
        parts.append(part)
    return parts


def _if_guard(code):
    match = re.search(r"\bif\b\s+(.+)$", code, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _consumer_kind(code):
    stripped = re.sub(
        r"^\s*(?:(?:capture|cap|quietly|qui)\s*:?[ \t]*)+", "", code,
        flags=re.IGNORECASE,
    )
    match = re.match(r"([A-Za-z]+)\b", stripped)
    command = match.group(1).lower() if match else ""
    if command in STANDARD_MUTATORS:
        return "standard", command
    if command == "recode":
        return "advisory", command
    if re.search(r"\[(?:a|f|p|i)w\s*=", stripped, re.IGNORECASE):
        return "standard", "weight"
    return None, None


def _context(raw_lines, def_line, consumer_line):
    indexes = set()
    for center, radius in ((def_line, 5), (consumer_line, 2)):
        indexes.update(range(max(1, center - radius),
                             min(len(raw_lines), center + radius) + 1))
    return " / ".join(
        f"L{i}: {raw_lines[i - 1].strip()}" for i in sorted(indexes)
        if raw_lines[i - 1].strip()
    )


def _scan_file(root, path):
    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    logical = _logical_lines(raw_lines)
    rel = path.relative_to(root).as_posix()
    producers = []
    for index, statement in enumerate(logical):
        match = GEN_RE.match(statement["code"])
        if not match:
            continue
        var, rhs = match.group("var"), match.group("rhs")
        rhs = re.split(r"\s+if\s+", rhs, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        shape = None
        if BOOLEAN_RHS_RE.search(rhs):
            shape = "boolean_gen"
        elif CONSTANT_RE.fullmatch(rhs):
            later = logical[index + 1:]
            if any((m := REPLACE_TARGET_RE.match(item["code"]))
                   and m.group("var").lower() == var.lower()
                   and _if_guard(item["code"]) is not None
                   for item in later):
                shape = "constant_then_replace"
        if shape:
            producers.append((index, var, shape, statement))

    bundles = []
    for def_index, var, shape, definition in producers:
        token = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(var)}(?![A-Za-z0-9_])",
                           re.IGNORECASE)
        for consumer in logical[def_index + 1:]:
            category, command = _consumer_kind(consumer["code"])
            if category is None:
                continue
            if command == "replace":
                match = REPLACE_TARGET_RE.match(consumer["code"])
                if match and match.group("var").lower() == var.lower():
                    continue
            guard = _if_guard(consumer["code"])
            if not guard or not token.search(guard):
                continue
            conjuncts = top_level_conjuncts(guard)
            if len(conjuncts) < 2 or not any(token.search(c) for c in conjuncts):
                continue
            identity = (rel, definition["line"], consumer["line"], var)
            bundles.append({
                "identity": identity,
                "file": rel,
                "variable": var,
                "producer_shape": shape,
                "definition_line": definition["line"],
                "definition": definition["raw"],
                "consumer_line": consumer["line"],
                "consumer": consumer["raw"],
                "guard": guard,
                "context": _context(raw_lines, definition["line"],
                                    consumer["line"]),
                "category": category,
            })
    return bundles


def scan_package(root):
    """Scan a package and return files/counts/bundles for artifact rendering."""
    root = Path(root)
    try:
        manifest = json.loads(
            (root / "audit" / "_run" / "manifest.json").read_text(encoding="utf-8")
        )
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        manifest = {}
    files = [path for path in audited_regular_files(root, manifest)
             if path.suffix.lower() == ".do" and path.relative_to(root).parts[0] == "do"]

    bundles = []
    for path in files:
        bundles.extend(_scan_file(root, path))
    seen = {}
    seen_witnesses = {}
    for bundle in bundles:
        digest = short_hash(bundle["identity"])
        prior = seen.get(digest)
        if prior is not None and prior != bundle["identity"]:
            raise RuntimeError(
                f"Bundle ID hash collision DU-{digest}: {prior!r} vs "
                f"{bundle['identity']!r}"
            )
        seen[digest] = bundle["identity"]
        bundle["id"] = f"DU-{digest}"
        witness_identity = bundle["identity"] + (bundle["guard"],)
        witness_digest = short_hash(witness_identity)
        prior_witness = seen_witnesses.get(witness_digest)
        if prior_witness is not None and prior_witness != witness_identity:
            raise RuntimeError(
                f"Witness ID hash collision DUW-{witness_digest}: "
                f"{prior_witness!r} vs {witness_identity!r}"
            )
        seen_witnesses[witness_digest] = witness_identity
        bundle["witness_id"] = f"DUW-{witness_digest}"
    bundles.sort(key=lambda b: (b["file"], b["definition_line"],
                                b["consumer_line"], b["variable"]))
    return {"files": [p.relative_to(root).as_posix() for p in files],
            "bundles": bundles}


def _cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


TABLE_HEADER = (
    "| Bundle ID | Witness ID | Identity Tuple | Variable | Producer Shape | Definition Site | "
    "Producer Statement | Consumer Site | Consumer Statement | Full Guard | "
    "Code/Comment Context | Obligation Question |"
)
TABLE_RULE = "| " + " | ".join(["---"] * 12) + " |"


def _render_table(lines, rows, empty_line):
    lines += [TABLE_HEADER, TABLE_RULE]
    if not rows:
        lines += [f"| {empty_line} | " + " | ".join([""] * 10) + " | |"]
        return
    for b in rows:
        identity = (f"({_cell(b['file'])}, {b['definition_line']}, "
                    f"{b['consumer_line']}, {_cell(b['variable'])})")
        question = ("Does the added guard conjunct narrow cases the producer "
                    "defines as covered, or is it an independently justified restriction?")
        cells = [f"`{b['id']}`", f"`{b['witness_id']}`", f"`{identity}`", b["variable"],
                 b["producer_shape"], f"`{b['file']}:{b['definition_line']}`",
                 f"`{_cell(b['definition'])}`",
                 f"`{b['file']}:{b['consumer_line']}`",
                 f"`{_cell(b['consumer'])}`", f"`{_cell(b['guard'])}`",
                 _cell(b["context"]), question]
        lines.append("| " + " | ".join(cells) + " |")


def render_artifact(results):
    standard = [b for b in results["bundles"] if b["category"] == "standard"]
    advisory = [b for b in results["bundles"] if b["category"] == "advisory"]
    producer_groups = {(b["file"], b["variable"]) for b in standard}
    lines = [
        "# Stata definition/use bundles", "",
        "Generated by `scripts/emit_definition_use_bundles.py` at b3d. This is a mechanical",
        "candidate emitter; recheck decides semantic intent. Every standard Bundle ID",
        "must be mapped exactly once in `audit/_run/detector_mapping.md`. Recode rows are",
        "advisory and excluded from mandatory mapping.", "",
        "## Scan summary", "",
        f"- Stata files scanned: {len(results['files'])}",
        f"- Standard producer groups (file + variable): {len(producer_groups)}",
        f"- Standard candidates: {len(standard)}",
        f"- Advisory candidates: {len(advisory)}", "",
        "## Files scanned", "",
    ]
    lines += ([f"- `{p}`" for p in results["files"]]
              or ["No Stata files found under `do/`."])
    lines += ["", "## Candidate findings", ""]
    _render_table(lines, standard, "No standard definition/use bundles found.")
    lines += ["", "## Advisory candidates", ""]
    _render_table(lines, advisory, "No advisory definition/use bundles found.")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_root", type=Path)
    parser.add_argument("--audit-dir", type=Path, default=Path("audit"))
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    if not args.package_root.is_dir():
        print(f"error: package root is not a directory: {args.package_root}",
              file=sys.stderr)
        return 2
    try:
        results = scan_package(args.package_root)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    out = args.output or args.audit_dir / "_run" / "definition_use_bundles.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_artifact(results), encoding="utf-8")
    standard = sum(b["category"] == "standard" for b in results["bundles"])
    advisory = sum(b["category"] == "advisory" for b in results["bundles"])
    print(f"scanned {len(results['files'])} Stata file(s); {standard} standard, "
          f"{advisory} advisory bundle(s) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
