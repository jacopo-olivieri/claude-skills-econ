#!/usr/bin/env python3
r"""Parse the frozen conventions-scan artifact and construct stable CV identities.

Serialization contract
======================

``cv_scan.md`` contains exactly one ``<!-- CV-SCAN:VERDICTS -->`` marker
followed by one Markdown table with ``VERDICT_COLS``, then exactly one
``<!-- CV-SCAN:WITNESSES -->`` marker followed by one Markdown table with
``WITNESS_COLS``.  Markdown cells escape a literal pipe as ``\|``.  A verdict
row exists exactly once for every convention.  ``divergent`` rows use ``—``
for Checked Sites and Rationale and have one or more witness rows;
``not_divergent`` rows have no witness rows and carry non-empty Checked Sites
(``path@anchor`` entries separated by semicolons) plus a rationale.

Convention identity normalizes name and category with Unicode NFKC, trims and
collapses whitespace, then case-folds.  A source ID hashes the normalized
``category NUL name`` tuple.  A divergent witness hashes its source ID and
``path:anchor``; a not-divergent witness hashes its source ID and a content
anchor derived from the canonical verdict record.  Traversal order and Error
ID allocation therefore never enter an identity.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import definition_use as du


VERDICTS_MARKER = "<!-- CV-SCAN:VERDICTS -->"
WITNESSES_MARKER = "<!-- CV-SCAN:WITNESSES -->"
VERDICT_COLS = ["Convention", "Category", "Verdict", "Checked Sites", "Rationale"]
WITNESS_COLS = ["Convention", "Category", "File Path", "Site Anchor", "Divergence"]
CONVENTION_COLS = ["Convention", "Category", "Stated Definition", "Sites Already Seen"]
VERDICTS = {"divergent", "not_divergent"}
BLANKS = {"", "-", "—"}


class CVScanError(RuntimeError):
    """The conventions or scan artifact violates the declared wire format."""


@dataclass(frozen=True)
class CVWitness:
    witness_id: str
    anchor: str
    file_path: str
    detail: str


@dataclass(frozen=True)
class CVSource:
    convention: str
    category: str
    source_id: str
    verdict: str
    witnesses: tuple[CVWitness, ...]
    checked_sites: str
    rationale: str


def _clean(value):
    return str(value).strip().strip("`").strip()


def normalize_identity(value):
    normalized = unicodedata.normalize("NFKC", _clean(value))
    return " ".join(normalized.split()).casefold()


def _identity_key(convention, category):
    return normalize_identity(category), normalize_identity(convention)


def _short_hash(payload):
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _source_id(key):
    category, convention = key
    return "CV-" + _short_hash(category + "\0" + convention)


def _witness_id(source_id, anchor):
    return "CVW-" + _short_hash(source_id + "\0" + normalize_identity(anchor))


def _table(text, columns, label):
    matches = [rows for headers, rows, _line in du.parse_markdown_tables(text)
               if headers == columns]
    if len(matches) != 1:
        raise CVScanError(
            f"{label}: expected exactly one {' | '.join(columns)} table"
        )
    result = []
    for index, row in enumerate(matches[0], start=1):
        if len(row) != len(columns):
            raise CVScanError(f"{label}: malformed row {index}")
        result.append(dict(zip(columns, map(_clean, row))))
    return result


def parse_conventions(path):
    path = Path(path)
    if not path.is_file():
        raise CVScanError(
            f"missing conventions artifact: {path}; wait for claims_b3c"
        )
    rows = _table(path.read_text(encoding="utf-8"), CONVENTION_COLS, str(path))
    result = {}
    for row in rows:
        key = _identity_key(row["Convention"], row["Category"])
        if not all(key):
            raise CVScanError(f"{path}: convention name and category must be non-empty")
        if key in result:
            raise CVScanError(
                f"{path}: duplicate normalized convention {row['Convention']!r}"
            )
        result[key] = row
    return result


def _split_sections(text, label):
    for marker in (VERDICTS_MARKER, WITNESSES_MARKER):
        if text.count(marker) != 1:
            raise CVScanError(f"{label}: marker {marker} must appear exactly once")
    first, second = text.index(VERDICTS_MARKER), text.index(WITNESSES_MARKER)
    if first > second:
        raise CVScanError(f"{label}: CV scan markers are out of order")
    return text[first + len(VERDICTS_MARKER):second], \
        text[second + len(WITNESSES_MARKER):]


def parse_scan(path):
    path = Path(path)
    if not path.is_file():
        raise CVScanError(f"missing conventions scan artifact: {path}")
    text = path.read_text(encoding="utf-8")
    verdict_text, witness_text = _split_sections(text, str(path))
    verdict_rows = _table(verdict_text, VERDICT_COLS, f"{path} verdicts")
    witness_rows = _table(witness_text, WITNESS_COLS, f"{path} witnesses")

    verdicts = {}
    for row in verdict_rows:
        key = _identity_key(row["Convention"], row["Category"])
        if not all(key):
            raise CVScanError(f"{path}: verdict convention and category must be non-empty")
        if key in verdicts:
            raise CVScanError(
                f"{path}: convention {row['Convention']!r} has more than one terminal verdict"
            )
        if row["Verdict"] not in VERDICTS:
            raise CVScanError(
                f"{path}: convention {row['Convention']!r} has invalid verdict {row['Verdict']!r}"
            )
        verdicts[key] = row

    witnesses = {}
    for row in witness_rows:
        key = _identity_key(row["Convention"], row["Category"])
        if key not in verdicts:
            raise CVScanError(
                f"{path}: witness names convention absent from verdicts: {row['Convention']!r}"
            )
        for field in ("File Path", "Site Anchor", "Divergence"):
            if row[field] in BLANKS:
                raise CVScanError(
                    f"{path}: witness for {row['Convention']!r} has empty {field}"
                )
        witnesses.setdefault(key, []).append(row)

    sources = []
    source_ids = {}
    witness_ids = {}
    for key, verdict_row in verdicts.items():
        source_id = _source_id(key)
        if source_id in source_ids and source_ids[source_id] != key:
            raise CVScanError(
                f"{path}: CV source identity collision for {source_id}"
            )
        source_ids[source_id] = key
        rows = witnesses.get(key, [])
        verdict = verdict_row["Verdict"]
        checked_sites = verdict_row["Checked Sites"]
        rationale = verdict_row["Rationale"]
        if verdict == "divergent":
            if not rows:
                raise CVScanError(
                    f"{path}: divergent convention {verdict_row['Convention']!r} has no witnesses"
                )
            if checked_sites not in BLANKS or rationale not in BLANKS:
                raise CVScanError(
                    f"{path}: divergent convention {verdict_row['Convention']!r} must use — "
                    "for Checked Sites and Rationale"
                )
            entries = []
            for row in rows:
                anchor = f"{row['File Path']}:{row['Site Anchor']}"
                wid = _witness_id(source_id, anchor)
                if wid in witness_ids:
                    raise CVScanError(f"{path}: CV witness identity collision for {wid}")
                witness_ids[wid] = (source_id, anchor)
                entries.append(CVWitness(
                    wid, anchor, row["File Path"], row["Divergence"]
                ))
        else:
            if rows:
                raise CVScanError(
                    f"{path}: not_divergent convention {verdict_row['Convention']!r} "
                    "must not carry divergent witnesses"
                )
            if checked_sites in BLANKS or rationale in BLANKS:
                raise CVScanError(
                    f"{path}: not_divergent convention {verdict_row['Convention']!r} "
                    "requires checked sites and rationale"
                )
            sites = [item.strip() for item in checked_sites.split(";") if item.strip()]
            if not sites or any("@" not in item for item in sites):
                raise CVScanError(
                    f"{path}: checked sites must be semicolon-separated path@anchor entries"
                )
            canonical = "\0".join([
                normalize_identity(verdict_row[column]) for column in VERDICT_COLS
            ])
            anchor = "audit/_run/cv_scan.md:verdict:" + _short_hash(canonical)
            wid = _witness_id(source_id, anchor)
            if wid in witness_ids:
                raise CVScanError(f"{path}: CV witness identity collision for {wid}")
            witness_ids[wid] = (source_id, anchor)
            entries = [CVWitness(wid, anchor, "audit/_run/cv_scan.md", rationale)]
        sources.append(CVSource(
            verdict_row["Convention"], verdict_row["Category"], source_id,
            verdict, tuple(entries), checked_sites, rationale,
        ))
    return tuple(sorted(sources, key=lambda source: source.source_id))


def validate_closure(conventions, sources, label="cv_scan.md"):
    by_key = {_identity_key(source.convention, source.category): source
              for source in sources}
    missing = sorted(set(conventions) - set(by_key))
    extra = sorted(set(by_key) - set(conventions))
    if missing:
        names = ", ".join(conventions[key]["Convention"] for key in missing)
        raise CVScanError(f"{label}: convention(s) lack a terminal verdict: {names}")
    if extra:
        names = ", ".join(by_key[key].convention for key in extra)
        raise CVScanError(f"{label}: verdict names unknown convention(s): {names}")
    return sources


def render_source_listing(sources):
    columns = ["Convention", "Source ID", "Witness IDs", "Verdict"]
    lines = ["| " + " | ".join(columns) + " |",
             "| " + " | ".join(["---"] * len(columns)) + " |"]
    for source in sources:
        values = [
            source.convention, source.source_id,
            "; ".join(witness.witness_id for witness in source.witnesses),
            source.verdict,
        ]
        lines.append("| " + " | ".join(value.replace("|", "\\|")
                                             for value in values) + " |")
    return "\n".join(lines) + "\n"
