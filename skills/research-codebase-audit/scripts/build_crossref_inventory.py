#!/usr/bin/env python3
"""Build or verify the deterministic cross-span paper-reference inventory."""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from claim_handoffs import (
    load_claims_allocations, owner_for_line, validate_partition,
)
from paper_sources import validate_source_set


REF_RE = re.compile(r"\\(?:ref|autoref|[cC]ref|vref)\s*\{([^{}]+)\}")
CATCHALL_REF_RE = re.compile(r"\\([A-Za-z@]*ref)\s*\{([^{}]+)\}")
PRINTED_RE = re.compile(
    r"\b(?:Figure|Fig\.?|Figs\.?|Table|Tab\.?)\s*(?:~|\s)*[A-Z]?\d+(?:[a-z])?\b",
    re.I,
)
FLOAT_TOKEN_RE = re.compile(r"\b(?:fig|figure|tab|table):[A-Za-z0-9_.:-]+\b", re.I)
LABEL_RE = re.compile(r"\\label\s*\{([^{}]+)\}")
NEWCOMMAND_RE = re.compile(
    r"\\(?:newcommand|renewcommand)\s*\{\\([A-Za-z@]+)\}\s*"
    r"\{((?:[^{}]|\{[^{}]*\})*)\}"
)
DEF_RE = re.compile(r"\\def\\([A-Za-z@]+)\s*\{((?:[^{}]|\{[^{}]*\})*)\}")
MACRO_CALL_RE = re.compile(r"\\([A-Za-z@]+)\b")
MAX_MACRO_DEPTH = 16


class CrossrefError(RuntimeError):
    pass


def _json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
            + "\n").encode("utf-8")


def _write_atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _line_for_char(text, index):
    return text.count("\n", 0, index) + 1


ABBREVIATION_END_RE = re.compile(r"(?:^|[\s~(])(?:Fig|Figs|Tab)$", re.I)


def _sentence_spans(text):
    """Conservative source spans ending at prose punctuation or EOF.

    Periods belonging to the supported printed-reference abbreviations
    (``Fig.``/``Figs.``/``Tab.``) never terminate a sentence, so a printed
    ``Fig. 2`` reference stays inside its full referencing sentence.
    """
    spans, start = [], 0
    for match in re.finditer(r"[.!?](?=\s|$)", text):
        if match.group(0) == "." and ABBREVIATION_END_RE.search(
                text[max(0, match.start() - 8):match.start()]):
            continue
        end = match.end()
        if text[start:end].strip():
            left = start + len(text[start:end]) - len(text[start:end].lstrip())
            right = end - len(text[start:end]) + len(text[start:end].rstrip())
            spans.append((left, right))
        start = end
    if text[start:].strip():
        left = start + len(text[start:]) - len(text[start:].lstrip())
        spans.append((left, len(text.rstrip())))
    return spans


def _harvest_macros(source_set):
    macros = {}
    for entry in source_set:
        text = Path(entry["audit_path"]).read_text(encoding="utf-8")
        for regex in (NEWCOMMAND_RE, DEF_RE):
            for match in regex.finditer(text):
                macros[match.group(1)] = match.group(2)
    return macros


def _expand_macros(text, macros):
    current, seen = text, {text}
    for _depth in range(MAX_MACRO_DEPTH):
        changed = False

        def replace(match):
            nonlocal changed
            body = macros.get(match.group(1))
            if body is None:
                return match.group(0)
            changed = True
            return body

        expanded = MACRO_CALL_RE.sub(replace, current)
        if not changed:
            return expanded, None
        if expanded in seen:
            return current, "macro expansion cycle"
        seen.add(expanded)
        current = expanded
    return current, f"macro expansion exceeded depth {MAX_MACRO_DEPTH}"


def derive(package_root, audit):
    package_root, audit = Path(package_root).resolve(), Path(audit).resolve()
    manifest_path = audit / "_run" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        source_set = validate_source_set(package_root, manifest)
        plan_path = audit / "plans" / "claims_review_plan.md"
        allocations, _plan_text = load_claims_allocations(plan_path)
        validate_partition(allocations, source_set, package_root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise CrossrefError(str(exc)) from exc

    digest = {
        "paper_files": [
            {
                "source_path": entry["source_path"],
                "source_sha256": entry["source_sha256"],
                "audit_sha256": entry["audit_sha256"],
            }
            for entry in source_set
        ],
        "claims_allocation_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
    }
    macros = _harvest_macros(source_set)
    labels, files = {}, []
    for file_index, entry in enumerate(source_set):
        text = Path(entry["audit_path"]).read_text(encoding="utf-8")
        files.append((file_index, entry, text))
        for match in LABEL_RE.finditer(text):
            line = _line_for_char(text, match.start())
            labels[match.group(1)] = {
                "source_path": entry["source_path"],
                "line": line,
                "owner": owner_for_line(
                    allocations, source_set, entry["source_path"], line, package_root
                ),
            }

    candidates, warnings = [], []
    for file_index, entry, text in files:
        for start, end in _sentence_spans(text):
            sentence = text[start:end].strip()
            if re.search(r"\\(?:newcommand|renewcommand|def)\b", sentence):
                continue
            expanded, expansion_warning = _expand_macros(sentence, macros)
            if expansion_warning:
                warnings.append({
                    "source_path": entry["source_path"],
                    "line": _line_for_char(text, start),
                    "macro": expansion_warning,
                })
            unknown_macros = sorted({
                name for name in MACRO_CALL_RE.findall(sentence)
                if name not in macros and re.search(r"(?:fig|tab|ref)", name, re.I)
                and name not in {"ref", "autoref", "cref", "Cref", "vref"}
            })
            for name in unknown_macros:
                warnings.append({
                    "source_path": entry["source_path"],
                    "line": _line_for_char(text, start),
                    "macro": f"unexpanded package macro \\{name}",
                })
            line = _line_for_char(text, start)
            owner = owner_for_line(
                allocations, source_set, entry["source_path"], line, package_root
            )
            supported_labels = []
            for match in REF_RE.finditer(expanded):
                supported_labels.extend(
                    label.strip() for label in match.group(1).split(",") if label.strip()
                )
            unknown_ref = [match.group(0) for match in CATCHALL_REF_RE.finditer(expanded)
                           if not REF_RE.fullmatch(match.group(0))]
            # Label declarations locate destinations; they are not assertion-
            # side float-label tokens and must not mint obligations themselves.
            float_tokens = FLOAT_TOKEN_RE.findall(LABEL_RE.sub("", expanded))
            printed = PRINTED_RE.findall(expanded)
            cross_span = [label for label in supported_labels
                          if label in labels and labels[label]["owner"] != owner]
            missing_labels = [label for label in supported_labels if label not in labels]
            unresolved = bool(unknown_ref or missing_labels or
                              (float_tokens and not supported_labels))
            if not (cross_span or printed or unresolved):
                continue
            kind = ("unresolved_reference" if unresolved else
                    "printed_reference" if printed and not cross_span else
                    "cross_span_reference")
            candidates.append({
                "_sort": (file_index, start),
                "kind": kind,
                "referencing_sentence": sentence,
                "anchor": {
                    "source_path": entry["source_path"],
                    "start_char": start,
                    "end_char": end,
                    "start_line": line,
                    "end_line": _line_for_char(text, max(start, end - 1)),
                },
                "referenced_float_labels": sorted(set(supported_labels)),
                "destination_worker": owner,
                "unresolved_tokens": sorted(set(unknown_ref + missing_labels + float_tokens)),
            })
            for token in unknown_ref:
                warnings.append({
                    "source_path": entry["source_path"], "line": line,
                    "macro": token,
                })
    entries = []
    for index, candidate in enumerate(sorted(candidates, key=lambda item: item["_sort"]),
                                      start=1):
        candidate = dict(candidate)
        candidate.pop("_sort")
        candidate["id"] = f"X-{index:04d}"
        entries.append(candidate)
    inventory = {
        "format_version": 1,
        "source_set_digest": digest,
        "entries": entries,
        "macro_warnings": sorted(warnings, key=lambda item: (
            item["source_path"], item["line"], item["macro"]
        )),
    }
    assignments = {
        "format_version": 1,
        "source_set_digest": digest,
        "assignments": {entry["id"]: entry["destination_worker"] for entry in entries},
    }
    return inventory, assignments


def paths(audit):
    run_dir = Path(audit) / "_run"
    return run_dir / "crossref_inventory.json", run_dir / "crossref_assignments.json"


def build(package_root, audit):
    inventory, assignments = derive(package_root, audit)
    inventory_path, assignments_path = paths(audit)
    _write_atomic(inventory_path, _json_bytes(inventory))
    _write_atomic(assignments_path, _json_bytes(assignments))


def check(package_root, audit):
    inventory, assignments = derive(package_root, audit)
    expected = (_json_bytes(inventory), _json_bytes(assignments))
    for path, payload in zip(paths(audit), expected):
        try:
            actual = path.read_bytes()
        except OSError as exc:
            raise CrossrefError(f"missing crossref artifact {path}: {exc}") from exc
        if actual != payload:
            raise CrossrefError(f"crossref artifact is absent, stale, or edited: {path}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_root", type=Path)
    parser.add_argument("--audit-dir", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    audit = args.audit_dir or args.package_root / "audit"
    try:
        (check if args.check else build)(args.package_root, audit)
    except (CrossrefError, OSError, json.JSONDecodeError) as exc:
        print(f"CROSSREF REFUSED: {exc}", file=sys.stderr)
        return 1
    print("CROSSREF OK: " + ("check" if args.check else "build"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
