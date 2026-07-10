#!/usr/bin/env python3
"""Render and save an Obsidian paper note from summary text + metadata JSON.

Defaults (output directory and template path) are read from
``~/.agents/config/paper-skills.json`` (keys ``vault_papers_dir`` and
``vault_template``); the script fails loudly with a JSON error naming that path
when it is missing. Before writing, the live template is validated against a
structural contract (R10) and drift is reported as a ``template_drift`` error.
``--on-exists update`` performs a section-scoped merge that preserves
human-owned content (R11).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote


CONFIG_PATH = Path("~/.agents/config/paper-skills.json").expanduser()


class ConfigError(Exception):
    """A user-facing config error reported as JSON."""


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise ConfigError(
            f"Config file not found: {CONFIG_PATH}. Copy the repo's "
            "config.example.json there and set papers_dir, vault_papers_dir, "
            "and vault_template."
        )
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Could not read config {CONFIG_PATH}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Config {CONFIG_PATH} must be a JSON object.")
    return data


def config_value(key: str) -> str:
    value = load_config().get(key)
    if not value:
        raise ConfigError(
            f"'{key}' is not set in {CONFIG_PATH}. Add it (see config.example.json)."
        )
    return str(value)


# R2: a section marker is a single-level integer 1-5 with a `.`/`)` delimiter
# FOLLOWED BY WHITESPACE, optionally wrapped in heading hashes or bold. The
# trailing whitespace requirement means `2.1` / `4.1` (two-level subsection
# numbers) are NOT markers — the next char after the dot is a digit, not a
# space — so template subsections survive as body text.
SECTION_MARKER_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s*)?(?:\*\*|__)?\s*([1-5])[.)]\s+(.+?)\s*(?:\*\*|__)?\s*$"
)

# Canonical five-part structure. R9/KTD-8: the single source of truth lives in
# ../../paper-summary/references/summary_sections.json; these embedded values
# are the fallback so a missing/invalid file does not brick the save. The
# aliases gate section-marker acceptance (R2): a marker is accepted only when
# its title fuzzy-matches its number's aliases.
_EMBEDDED_SECTION_ALIASES = {
    1: ("research question and motivation", "research question", "motivation"),
    2: ("data and methods", "data and empirical strategy", "data and identification",
        "data", "methods", "empirical strategy", "identification strategy"),
    3: ("results: main findings", "results and discussion", "results", "main findings",
        "findings"),
    4: ("limitations and extensions", "limitations", "extensions", "future research"),
    5: ("synthesis of findings", "synthesis", "comments and ideas", "comments",
        "conclusion", "discussion"),
}
_EMBEDDED_PRIMARY_HEADERS = {
    "s1": "### 💬 Research Question and Motivation %% fold %%",
    "s2": "### 📌 Data and Empirical Strategy %% fold %%",
    "s3": "### 🎯 Results %% fold %%",
    "s4": "### ✒️ Limitations and Extensions %% fold %%",
    "s5": "### 🧩 Comments and Ideas %% fold %%",
}
_EMBEDDED_ADDITIONAL_HEADERS = [
    "### 🗺️ Background, context and connections %% fold %%",
    "### 🚧 Digging and disclaimers %% fold %%",
    "### ❓ Problem formulation %% fold %%",
]

# Canonical JSON location: sibling paper-summary skill's references directory.
SUMMARY_SECTIONS_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "paper-summary" / "references" / "summary_sections.json"
)


def load_summary_structure(path: Path | None = None) -> dict:
    """Load the five-part structure from summary_sections.json (R9/KTD-8).

    Returns a dict with ``aliases`` (int -> tuple), ``primary_headers``
    (s1..s5), ``additional_headers``, and ``warnings``. Falls back to the
    embedded constants (with a warning) when the file is missing or invalid, so
    a missing file never bricks the save.
    """
    if path is None:
        env_override = os.environ.get("PAPER_SUMMARY_SECTIONS_FILE")
        path = Path(env_override) if env_override else None
    target = path or SUMMARY_SECTIONS_PATH
    embedded = {
        "aliases": dict(_EMBEDDED_SECTION_ALIASES),
        "primary_headers": dict(_EMBEDDED_PRIMARY_HEADERS),
        "additional_headers": list(_EMBEDDED_ADDITIONAL_HEADERS),
        "synthesis_marker": "synthesis of findings",
        "warnings": [],
    }
    if not target.exists():
        embedded["warnings"].append(
            f"summary_sections.json not found at {target}; using embedded structure."
        )
        return embedded
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        sections = data["sections"]
        aliases = {int(s["number"]): tuple(s["aliases"]) for s in sections}
        primary = {f"s{int(s['number'])}": s["fold_heading"] for s in sections}
        additional = list(data["additional_headings"])
        synthesis_marker = str(data.get("synthesis_marker") or "synthesis of findings")
        if set(aliases) != {1, 2, 3, 4, 5}:
            raise ValueError("summary_sections.json must define sections 1-5")
    except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        embedded["warnings"].append(
            f"summary_sections.json at {target} is invalid ({exc}); using embedded structure."
        )
        return embedded
    return {"aliases": aliases, "primary_headers": primary,
            "additional_headers": additional, "synthesis_marker": synthesis_marker,
            "warnings": []}


def _fold_heading_text(heading: str) -> str:
    """Strip the ``### `` prefix and `` %% fold %%`` suffix from a fold heading."""
    text = re.sub(r"^#+\s*", "", heading)
    return re.sub(r"\s*%%\s*fold\s*%%\s*$", "", text).strip()


SUMMARY_STRUCTURE = load_summary_structure()
CANONICAL_SECTION_ALIASES = SUMMARY_STRUCTURE["aliases"]

# R9/KTD-8: the synthesis marker is single-sourced from summary_sections.json.
_SYNTHESIS_MARKER = re.escape(SUMMARY_STRUCTURE["synthesis_marker"])
SYNTHESIS_MARKER_RE = re.compile(rf"\b{_SYNTHESIS_MARKER}\b", re.IGNORECASE)
SYNTHESIS_PREFIX_RE = re.compile(
    rf"^\s*(?:[#>\-\+\*]+\s*)?(?:\*\*|__)?\s*{_SYNTHESIS_MARKER}\b[^\n]*\n?",
    re.IGNORECASE,
)
SYNTHESIS_LIST_MARKER_RE = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")
BOLD_NUMBERED_HEADER_RE = re.compile(
    r"^\s*(?:\*\*|__)\s*(\d+(?:\.\d+)*(?:[.)])?\s+.+?)\s*(?:\*\*|__)\s*$"
)
STANDALONE_BOLD_RE = re.compile(r"^\s*(?:\*\*|__)\s*(?P<body>.+?)\s*(?:\*\*|__)\s*$")
BULLET_BOLD_ONLY_RE = re.compile(
    r"^(?P<indent>\s*)[-+*]\s+(?:\*\*|__)\s*(?P<body>.+?)\s*(?:\*\*|__)\s*$"
)
BULLET_BOLD_PREFIX_RE = re.compile(
    r"^(?P<indent>\s*)[-+*]\s+(?:\*\*|__)\s*(?P<label>.+?)\s*(?:\*\*|__)(?P<tail>\s*.*)$"
)
LIST_LINE_RE = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+\S")
HEADING_LINE_RE = re.compile(r"^(?P<prefix>\s*#{1,6}\s+)(?P<body>.+?)\s*$")
SUBSECTION_HEADER_RE = re.compile(r"^\s*####\s+\S")
HORIZONTAL_RULE_RE = re.compile(r"^\s{0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")
HEADING_NUMBER_PREFIX_RE = re.compile(r"^\d+(?:\.\d+)*(?:[.)])?\s+")

PRIMARY_HEADERS = SUMMARY_STRUCTURE["primary_headers"]
ADDITIONAL_HEADERS = SUMMARY_STRUCTURE["additional_headers"]


def _pick_first(meta: dict[str, Any], keys: list[str], default: str = "") -> str:
    for key in keys:
        value = meta.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
            continue
        return str(value)
    return default


def _normalize_authors(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    text = str(value).strip()
    if not text:
        return []
    if ";" in text:
        return [part.strip() for part in text.split(";") if part.strip()]
    return [text]


def _yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _extract_year(date_value: str) -> str:
    # R8: extract a 4-digit year from anywhere in the string (e.g. "July 2020"),
    # not only from the start.
    if not date_value:
        return ""
    match = re.search(r"(?<!\d)(\d{4})(?!\d)", date_value)
    return match.group(1) if match else ""


def _format_blockquote(text: str) -> str:
    text = text.strip()
    if not text:
        return "> "
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def _title_matches_section(number: int, title: str) -> bool:
    """R2: does the marker title fuzzy-match the canonical name for `number`?

    Matching is deliberately tight so a numbered *list item* whose text merely
    begins with a section word (e.g. ``4. Extensions to neighboring markets
    replicate the effect``) is NOT promoted to a section marker and its text is
    not lost. A trailing subtitle after ``:``/``-``/``—`` is ignored, then:
    a single-word alias must equal the whole title head; a multi-word alias may
    match as a prefix (tolerating extra trailing words like "and Discussion").
    """
    norm = re.sub(r"\s+", " ", title).strip().lower().rstrip(":").strip()
    if not norm:
        return False
    head = re.split(r"\s*[:\-–—]\s+", norm, maxsplit=1)[0].strip()
    for alias in CANONICAL_SECTION_ALIASES.get(number, ()):
        if head == alias:
            return True
        if " " in alias and head.startswith(alias):
            return True
    return False


def analyze_summary_sections(summary_text: str) -> tuple[dict[str, str], dict[str, Any]]:
    """Split summary text into s1..s5 and report parse metadata.

    R2: a line is accepted as a section marker only when it is a single-level
    1-5 number whose title fuzzy-matches that section's canonical name, the
    number strictly increases, and the section has not already been seen.
    Everything else — numbered list items, `N.M` subheadings, prose — is body
    text. R8 (surfaced in the JSON by U5): a degenerate parse is detectable via
    ``sections_found`` and ``warnings``.
    """
    result = {"s1": "", "s2": "", "s3": "", "s4": "", "s5": ""}
    current_key: str | None = None
    preamble: list[str] = []
    last_number = 0
    seen: set[int] = set()
    sections_found = 0
    warnings: list[str] = []

    for line in summary_text.splitlines():
        marker = SECTION_MARKER_RE.match(line)
        accepted = False
        if marker:
            number = int(marker.group(1))
            title = marker.group(2).strip()
            if number > last_number and number not in seen and _title_matches_section(number, title):
                accepted = True

        if accepted:
            last_number = number
            seen.add(number)
            sections_found += 1
            current_key = f"s{number}"
            if title and current_key == "s5":
                result[current_key] += f"**{title}**\n"
            continue

        if current_key is None:
            preamble.append(line)
            continue

        result[current_key] += f"{line}\n"

    if sections_found:
        preamble_text = "\n".join(preamble).strip()
        if preamble_text:
            if result["s1"].strip():
                result["s1"] = f"{preamble_text}\n\n{result['s1'].strip()}\n"
            else:
                result["s1"] = f"{preamble_text}\n"
    else:
        if summary_text.strip():
            warnings.append(
                "No section markers detected; the entire summary was placed under "
                "Comments and Ideas. Check that the summary uses the numbered "
                "five-part structure."
            )
        result["s5"] = summary_text.strip()

    for key, value in result.items():
        result[key] = value.strip()

    meta = {"sections_found": sections_found, "warnings": warnings}
    return result, meta


def _split_summary_sections(summary_text: str) -> dict[str, str]:
    sections, _meta = analyze_summary_sections(summary_text)
    return sections


def _extract_synthesis_summary(section_text: str) -> tuple[str, bool]:
    # R8: only lift the synthesis when the synthesis marker is the FIRST
    # non-blank line of the section, so a mid-prose mention of "synthesis of
    # findings" no longer relocates the surrounding text into Key takeaways.
    text = section_text.strip()
    if not text:
        return "", False
    if not SYNTHESIS_PREFIX_RE.match(text):
        return "", False
    text = SYNTHESIS_PREFIX_RE.sub("", text, count=1).strip()
    return text, True


def _strip_markdown_emphasis(text: str) -> str:
    out = text
    patterns = [
        r"\*\*\*(.+?)\*\*\*",
        r"___(.+?)___",
        r"\*\*(.+?)\*\*",
        r"__(.+?)__",
        r"\*(.+?)\*",
        r"_(.+?)_",
    ]
    for _ in range(3):
        prev = out
        for pattern in patterns:
            out = re.sub(pattern, r"\1", out)
        if out == prev:
            break
    out = re.sub(r"(?<!\w)[*_]+|[*_]+(?!\w)", "", out)
    return out


def _normalize_synthesis_text(text: str) -> str:
    normalized_lines: list[str] = []
    prev_blank = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if normalized_lines and not prev_blank:
                normalized_lines.append("")
            prev_blank = True
            continue
        line = SYNTHESIS_LIST_MARKER_RE.sub("", line)
        line = _strip_markdown_emphasis(line).strip()
        if not line:
            continue
        normalized_lines.append(line)
        prev_blank = False
    return "\n".join(normalized_lines).strip()


def _is_subsection_header_candidate(text: str) -> bool:
    title = re.sub(r"\s+", " ", text).strip()
    if not title or len(title) > 120:
        return False

    lower = title.lower()
    starts = (
        "research question",
        "data",
        "empirical strategy",
        "identification strategy",
        "results",
        "limitations",
        "concrete directions",
        "synthesis",
    )
    if lower.startswith(starts):
        return True

    contains = (
        "main findings",
        "identification strategy",
        "empirical strategy",
        "future research",
        "limitations",
        "synthesis of findings",
    )
    return any(token in lower for token in contains)


def _should_convert_bold_prefix_tail(tail: str) -> bool:
    stripped = tail.strip()
    if not stripped:
        return True
    return stripped.startswith(":") or stripped.startswith("(")


def _normalize_section_markdown(text: str) -> str:
    if not text.strip():
        return ""

    converted_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if HORIZONTAL_RULE_RE.match(line):
            continue

        numbered_header = BOLD_NUMBERED_HEADER_RE.match(line)
        if numbered_header:
            heading_text = _strip_markdown_emphasis(numbered_header.group(1)).strip()
            heading_text = HEADING_NUMBER_PREFIX_RE.sub("", heading_text).strip()
            converted_lines.append(f"#### {heading_text}" if heading_text else "")
            continue

        standalone_bold = STANDALONE_BOLD_RE.match(line)
        if standalone_bold:
            heading_text = _strip_markdown_emphasis(standalone_bold.group("body")).strip()
            heading_text = HEADING_NUMBER_PREFIX_RE.sub("", heading_text).strip()
            if _is_subsection_header_candidate(heading_text):
                converted_lines.append(f"#### {heading_text}" if heading_text else "")
                continue

        bullet_bold = BULLET_BOLD_ONLY_RE.match(line)
        if bullet_bold:
            heading_text = _strip_markdown_emphasis(bullet_bold.group("body")).strip()
            heading_text = HEADING_NUMBER_PREFIX_RE.sub("", heading_text).strip()
            # R8: only promote a bold bullet to a subsection header when its text
            # is a header candidate; otherwise it is an evidence bullet and must
            # stay a bullet (e.g. "- **Main estimate**: beta = 0.31").
            if not bullet_bold.group("indent") and heading_text and _is_subsection_header_candidate(heading_text):
                converted_lines.append(f"#### {heading_text}")
                continue

        bullet_bold_prefix = BULLET_BOLD_PREFIX_RE.match(line)
        if bullet_bold_prefix and not bullet_bold_prefix.group("indent"):
            label = _strip_markdown_emphasis(bullet_bold_prefix.group("label")).strip()
            label = HEADING_NUMBER_PREFIX_RE.sub("", label).strip()
            tail = bullet_bold_prefix.group("tail")

            if label.lower() == "paper":
                continue

            if label and _is_subsection_header_candidate(label) and _should_convert_bold_prefix_tail(tail):
                tail_text = _strip_markdown_emphasis(tail.strip()).strip()
                if tail_text.startswith(":"):
                    tail_text = tail_text[1:].strip()
                heading_text = " ".join(part for part in [label, tail_text] if part).strip()
                if heading_text:
                    converted_lines.append(f"#### {heading_text}")
                    continue

        heading = HEADING_LINE_RE.match(line)
        if heading:
            prefix = heading.group("prefix")
            heading_text = _strip_markdown_emphasis(heading.group("body")).strip()
            hash_token = prefix.lstrip().split()[0]
            if len(hash_token) >= 3:
                heading_text = HEADING_NUMBER_PREFIX_RE.sub("", heading_text).strip()
            if heading_text:
                if len(hash_token) >= 3:
                    converted_lines.append(f"#### {heading_text}")
                else:
                    converted_lines.append(f"{prefix}{heading_text}")
            else:
                converted_lines.append("####" if len(hash_token) >= 3 else prefix.rstrip())
            continue

        converted_lines.append(line)

    normalized_lines: list[str] = []
    for idx, line in enumerate(converted_lines):
        if line.strip():
            normalized_lines.append(line)
            continue

        prev_non_empty = ""
        for candidate in reversed(normalized_lines):
            if candidate.strip():
                prev_non_empty = candidate
                break
        if not prev_non_empty:
            continue

        next_non_empty = ""
        for candidate in converted_lines[idx + 1 :]:
            if candidate.strip():
                next_non_empty = candidate
                break
        if not next_non_empty:
            continue

        if normalized_lines and normalized_lines[-1] == "":
            continue

        if SUBSECTION_HEADER_RE.match(prev_non_empty):
            continue

        if LIST_LINE_RE.match(prev_non_empty) and LIST_LINE_RE.match(next_non_empty):
            continue

        normalized_lines.append("")

    while normalized_lines and not normalized_lines[-1].strip():
        normalized_lines.pop()

    return "\n".join(normalized_lines)


def _is_pdf_attachment(attachment: dict[str, Any]) -> bool:
    if bool(attachment.get("is_pdf")):
        return True
    title = str(attachment.get("title", "")).lower()
    path = str(attachment.get("path", "")).lower()
    mime = str(attachment.get("contentType", "")).lower()
    return title.endswith(".pdf") or path.endswith(".pdf") or mime == "application/pdf"


def _build_alias(authors: list[str], year: str, title: str) -> str:
    left = ", ".join(authors).strip()
    if left and year and title:
        return f"{left} ({year}) {title}"
    if left and title:
        return f"{left} {title}"
    return title


def render_note(item_key: str, citation_key: str, summary_text: str, metadata: dict[str, Any]) -> str:
    title = _pick_first(metadata, ["title"])
    authors = _normalize_authors(metadata.get("authors"))
    date_published = _pick_first(metadata, ["date_published", "date-published", "date"])
    year = _extract_year(date_published)
    item_type = _pick_first(metadata, ["itemType", "item_type", "type"])
    url = _pick_first(metadata, ["url"])
    doi = _pick_first(metadata, ["doi", "DOI"])
    journal = _pick_first(metadata, ["journal", "publicationTitle", "repository"])
    abstract = _pick_first(metadata, ["abstract", "abstractNote"])
    bibliography = _pick_first(metadata, ["bibliography"])
    zotero_uri = _pick_first(
        metadata,
        ["zotero_uri", "desktop_uri", "zotero_select_uri"],
        default=f"zotero://select/library/items/{item_key}",
    )

    attachments = metadata.get("attachments")
    if not isinstance(attachments, list):
        attachments = []
    pdf_attachments = [a for a in attachments if isinstance(a, dict) and _is_pdf_attachment(a)]

    alias = _build_alias(authors, year, title)
    sections = _split_summary_sections(summary_text)
    for key in ("s1", "s2", "s3", "s4"):
        sections[key] = _normalize_section_markdown(sections[key])
    synthesis_summary, moved_from_section5 = _extract_synthesis_summary(sections["s5"])
    synthesis_summary = _normalize_synthesis_text(synthesis_summary)
    if moved_from_section5:
        sections["s5"] = ""

    info_links = [f"[**Zotero**]({zotero_uri})"]
    if doi:
        info_links.append(f"[**DOI**](https://doi.org/{doi})")
    for idx, attachment in enumerate(pdf_attachments, start=1):
        if attachment.get("path"):
            # R8: URL-encode the path (keeping '/' as separators) and build a
            # well-formed file:// URI. An absolute path already starts with '/',
            # so `file://` + `/abs/...` yields the correct `file:///abs/...`.
            encoded_path = quote(str(attachment["path"]), safe="/")
            if not encoded_path.startswith("/"):
                encoded_path = "/" + encoded_path
            info_links.append(f"[**PDF-{idx}**](file://{encoded_path})")

    if pdf_attachments:
        first_pdf = pdf_attachments[0]
        pdf_title = str(first_pdf.get("title", "")).strip()
        pdf_key = str(first_pdf.get("key", "")).strip()
        if pdf_title and pdf_key:
            pdf_line = f"> pdf:: [{pdf_title}](zotero://select/library/items/{pdf_key})"
        elif pdf_title:
            pdf_line = f"> pdf:: {pdf_title}"
        else:
            pdf_line = "> pdf:: "
    else:
        pdf_line = "> pdf:: "

    bibliography_line = f"> bibliography:: {_yaml_quote(bibliography)}" if bibliography else "> bibliography:: "

    frontmatter: list[str] = [
        "---",
        "project:",
        "class: lit_note",
        "aliases:",
        f"  - {_yaml_quote(alias)}" if alias else "  - \"\"",
        f"title: {_yaml_quote(title)}" if title else 'title: ""',
        "author:",
    ]

    if authors:
        for author in authors:
            frontmatter.append(f"  - {_yaml_quote(author)}")

    # R3: quote every scalar that could contain a `: ` or other YAML-breaking
    # character (authors above, plus dates/itemType/url/journal here). R4: emit
    # the vault-dominant `date-published` (hyphen), not `date_published`.
    frontmatter.extend(
        [
            f"year: {year}" if year else "year: ",
            f"date-published: {_yaml_quote(date_published)}" if date_published else "date-published: ",
            f"citekey: {citation_key}",
            f"itemType: {_yaml_quote(item_type)}" if item_type else "itemType: ",
            f"url: {_yaml_quote(url)}" if url else "url: ",
            "cssclasses: lit-note",
            "links:",
            "lit_review:",
        ]
    )

    if doi:
        frontmatter.append(f"doi: {doi}")
    if journal:
        frontmatter.append(f"journal: {_yaml_quote(journal)}")
    frontmatter.append("---")

    lines: list[str] = []
    lines.extend(frontmatter)
    note_block = [
        "",
        "%% begin notes %%",
        "",
        "## Key takeaways",
        "",
        "contribution:: ",
        "",
    ]
    if synthesis_summary:
        note_block.extend(synthesis_summary.splitlines())
        note_block.append("")
    note_block.extend(
        [
            "%% end notes %%",
            "",
            "> [!abstract]+",
            "> ",
            _format_blockquote(abstract),
            "> ",
            "",
            f"> [!info]- Additional Metadata 🔗 {' | '.join(info_links)}",
            pdf_line,
            bibliography_line,
            "",
            "",
            "> [!quote]- Citations",
            "> ",
            "> ```query",
            f"> content: \"@{citation_key}\" -file:@{citation_key}",
            "> ```",
            "",
            "___",
            "",
            "## Reading notes",
            "",
            "%% begin annotations %%",
            "",
        ]
    )
    lines.extend(note_block)

    for key in ("s1", "s2", "s3", "s4", "s5"):
        lines.append(PRIMARY_HEADERS[key])
        lines.append("")
        if sections[key]:
            lines.append(sections[key])
            lines.append("")

    for header in ADDITIONAL_HEADERS:
        lines.append(header)
        lines.append("")

    lines.extend(
        [
            "%% end annotations %%",
            "",
        ]
    )

    return "\n".join(lines)


def _sanitize_citation_key(citation_key: str) -> str:
    # R8: strip path separators (and other filename-hostile characters) so a
    # citation key cannot escape the output directory when used as a filename.
    safe = re.sub(r"[/\\\x00]+", "_", citation_key).strip().strip(".")
    return safe or "note"


def _prepare_output_path(output_dir: Path, citation_key: str, mode: str) -> tuple[Path, str]:
    stem = _sanitize_citation_key(citation_key)
    base = output_dir / f"@{stem}.md"
    if not base.exists():
        return base, "new"
    if mode == "overwrite":
        return base, "overwrite"
    if mode == "update":
        return base, "update"
    if mode == "versioned":
        # R8: seconds included so two versioned writes in the same minute do not
        # collide.
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return output_dir / f"@{stem}-{stamp}.md", "versioned"
    return base, "skip"


# --------------------------------------------------------------------------- #
# R10: structural template contract
# --------------------------------------------------------------------------- #

# Fold-heading strings the rendered note relies on (matches the live template's
# colorValueMap headings). Derived from the single source (R9/KTD-8) so a
# heading rename in summary_sections.json propagates to the R10 contract too.
TEMPLATE_FOLD_HEADINGS = [
    _fold_heading_text(h)
    for h in list(PRIMARY_HEADERS.values()) + list(ADDITIONAL_HEADERS)
]
TEMPLATE_FRONTMATTER_KEYS = [
    "title", "author", "date-published", "citekey", "itemType", "url", "journal",
]
TEMPLATE_STRUCTURAL_MARKERS = [
    "%% fold %%", "## Reading notes", "## Key takeaways", "contribution::",
]


def check_template_contract(template_text: str) -> list[str]:
    """Return a list of structural landmarks missing from the live template."""
    missing: list[str] = []
    for heading in TEMPLATE_FOLD_HEADINGS:
        if heading not in template_text:
            missing.append(f"fold heading: {heading}")
    for key in TEMPLATE_FRONTMATTER_KEYS:
        if f'"{key}"' not in template_text and f"{key}:" not in template_text:
            missing.append(f"frontmatter key: {key}")
    for marker in TEMPLATE_STRUCTURAL_MARKERS:
        if marker not in template_text:
            missing.append(f"marker: {marker}")
    return missing


# --------------------------------------------------------------------------- #
# R11: section-scoped update merge
# --------------------------------------------------------------------------- #

class UpdateError(Exception):
    """A generated anchor is missing, so a safe update is impossible."""


_FOLD_HEADING_RE = re.compile(r"^###\s+.+?%%\s*fold\s*%%\s*$")
# The four fold-heading bodies that the pipeline generates (s1-s4). The 🧩
# Comments body and the three additional headings are human-owned and preserved.
GENERATED_FOLD_HEADINGS = [PRIMARY_HEADERS[k] for k in ("s1", "s2", "s3", "s4")]


def _find_line(lines: list[str], target: str, name: str) -> int:
    for i, line in enumerate(lines):
        if line.strip() == target:
            return i
    raise UpdateError(name)


def _frontmatter_close(lines: list[str]) -> int:
    if not lines or lines[0].strip() != "---":
        raise UpdateError("frontmatter opening '---'")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return i
    raise UpdateError("frontmatter closing '---'")


def _scalar_frontmatter(lines: list[str], close: int) -> dict[str, tuple[int, str]]:
    out: dict[str, tuple[int, str]] = {}
    for i in range(1, close):
        m = re.match(r"^([A-Za-z][\w-]*):(.*)$", lines[i])
        if m:
            out[m.group(1)] = (i, m.group(2).strip())
    return out


def _trim_blank(block: list[str]) -> list[str]:
    start, end = 0, len(block)
    while start < end and not block[start].strip():
        start += 1
    while end > start and not block[end - 1].strip():
        end -= 1
    return block[start:end]


def _fold_body_map(lines: list[str]) -> dict[str, list[str]]:
    """Map each fold-heading line to its body (up to the next fold heading)."""
    fold_idxs = [i for i, line in enumerate(lines) if _FOLD_HEADING_RE.match(line)]
    try:
        end_idx = _find_line(lines, "%% end annotations %%", "%% end annotations %%")
    except UpdateError:
        end_idx = len(lines)
    result: dict[str, list[str]] = {}
    for j, idx in enumerate(fold_idxs):
        nxt = fold_idxs[j + 1] if j + 1 < len(fold_idxs) else end_idx
        result[lines[idx].strip()] = lines[idx + 1:nxt]
    return result


def _synthesis_body(lines: list[str]) -> list[str]:
    notes_begin = _find_line(lines, "%% begin notes %%", "%% begin notes %%")
    notes_end = _find_line(lines, "%% end notes %%", "%% end notes %%")
    contrib = next(
        (i for i in range(notes_begin, notes_end) if lines[i].startswith("contribution::")),
        None,
    )
    if contrib is None:
        raise UpdateError("contribution::")
    return _trim_blank(lines[contrib + 1:notes_end])


def update_existing_note(existing_text: str, rendered_text: str) -> str:
    """Merge freshly rendered generated regions into an existing note (R11).

    Replaces only the four generated fold-heading bodies (s1-s4) and the
    synthesis block, fills only empty frontmatter scalars, and preserves all
    other (human-owned) content byte-for-byte. Raises ``UpdateError`` naming the
    missing anchor when the existing note cannot be parsed safely.
    """
    ex = existing_text.split("\n")
    new = rendered_text.split("\n")

    # Validate the anchors we depend on before changing anything.
    ex_close = _frontmatter_close(ex)
    ex_notes_begin = _find_line(ex, "%% begin notes %%", "%% begin notes %%")
    ex_notes_end = _find_line(ex, "%% end notes %%", "%% end notes %%")
    _find_line(ex, "%% begin annotations %%", "%% begin annotations %%")
    _find_line(ex, "%% end annotations %%", "%% end annotations %%")
    if not any(ex[i].startswith("contribution::") for i in range(ex_notes_begin, ex_notes_end)):
        raise UpdateError("contribution::")
    ex_fold = _fold_body_map(ex)
    for heading in GENERATED_FOLD_HEADINGS:
        if heading not in ex_fold:
            raise UpdateError(f"fold heading: {heading}")

    new_fold = _fold_body_map(new)
    new_synth = _synthesis_body(new)

    # 1. Frontmatter: fill only empty scalar keys.
    new_close = _frontmatter_close(new)
    ex_fm = _scalar_frontmatter(ex, ex_close)
    new_fm = _scalar_frontmatter(new, new_close)
    for key, (idx, value) in ex_fm.items():
        if value:
            continue  # never overwrite a non-empty (possibly hand-edited) value
        if key in new_fm and new_fm[key][1]:
            ex[idx] = new[new_fm[key][0]]

    # 2. Rebuild the body, replacing generated regions only.
    out: list[str] = ex[:ex_close + 1]
    i = ex_close + 1
    n = len(ex)
    contrib_seen = False
    while i < n:
        line = ex[i]
        stripped = line.strip()

        # Synthesis: after the contribution:: field, replace the generated
        # synthesis block up to %% end notes %%. The user's contribution value
        # (including any multi-line continuation up to the first blank line) is
        # preserved; only the generated synthesis that follows is regenerated.
        if not contrib_seen and line.startswith("contribution::"):
            contrib_seen = True
            out.append(line)
            i += 1
            # Preserve a multi-line contribution value (until the blank line
            # that separates it from the generated synthesis).
            while i < n and ex[i].strip() and ex[i].strip() != "%% end notes %%":
                out.append(ex[i])
                i += 1
            if new_synth:
                out.append("")
                out.extend(new_synth)
            out.append("")
            # Skip the old generated synthesis up to %% end notes %%.
            while i < n and ex[i].strip() != "%% end notes %%":
                i += 1
            continue

        # Generated fold-heading body: replace with the freshly rendered body.
        if _FOLD_HEADING_RE.match(line) and stripped in GENERATED_FOLD_HEADINGS:
            out.append(line)
            out.extend(new_fold.get(stripped, [""]))
            # skip the old body until the next fold heading or end-of-annotations
            i += 1
            while i < n and not _FOLD_HEADING_RE.match(ex[i]) and ex[i].strip() != "%% end annotations %%":
                i += 1
            continue

        out.append(line)
        i += 1

    return "\n".join(out)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Save Obsidian paper summary note.")
    parser.add_argument(
        "--item-key",
        required=True,
        help="Zotero item_key (used for URI defaults and reporting).",
    )
    parser.add_argument(
        "--citation-key",
        required=True,
        help="Citation key used for frontmatter `citekey`, citation query, and output filename.",
    )
    parser.add_argument("--summary-file", required=True, help="Path to plain-text summary content.")
    parser.add_argument(
        "--metadata-file",
        required=True,
        help="Path to metadata JSON (see references/metadata_schema.md).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for rendered notes (default: vault_papers_dir from config).",
    )
    parser.add_argument(
        "--template-path",
        default=None,
        help="Path to the live template reference file (default: vault_template from config).",
    )
    parser.add_argument(
        "--on-exists",
        choices=["skip", "overwrite", "versioned", "update"],
        default="skip",
        help="How to handle existing @citation_key.md files. 'update' does a "
             "section-scoped merge that preserves human-owned content.",
    )
    parser.add_argument("--write", action="store_true", help="Write file. Without this, dry-run only.")
    return parser.parse_args()


def _error(message: str, **extra: Any) -> int:
    print(json.dumps({"status": "error", "message": message, **extra}, indent=2))
    return 1


def main() -> int:
    args = parse_args()

    # R15: resolve defaults from config; loud, named error when missing.
    try:
        output_dir = Path(args.output_dir).expanduser() if args.output_dir else Path(config_value("vault_papers_dir")).expanduser()
        template_path = Path(args.template_path).expanduser() if args.template_path else Path(config_value("vault_template")).expanduser()
    except ConfigError as exc:
        return _error(str(exc))

    if not template_path.exists():
        return _error(f"Template not found: {template_path}")
    template_text = template_path.read_text(encoding="utf-8")

    # R10: structural template contract; name every divergence.
    drift = check_template_contract(template_text)
    if drift:
        return _error(
            "template_drift: the live template is missing expected structure.",
            missing=drift,
        )

    summary_path = Path(args.summary_file)
    metadata_path = Path(args.metadata_file)
    if not summary_path.exists():
        return _error(f"Summary file not found: {summary_path}")
    if not metadata_path.exists():
        return _error(f"Metadata file not found: {metadata_path}")

    try:
        summary_text = summary_path.read_text(encoding="utf-8")
    except OSError as exc:
        return _error(f"Failed to read summary file: {exc}")

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("metadata root must be an object")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return _error(f"Invalid metadata JSON: {exc}")

    _sections, sections_meta = analyze_summary_sections(summary_text)
    warnings = list(SUMMARY_STRUCTURE["warnings"]) + list(sections_meta["warnings"])
    if not metadata:
        warnings.append("Metadata JSON is empty; frontmatter will be mostly blank.")

    rendered = render_note(args.item_key, args.citation_key, summary_text, metadata)
    output_path, action = _prepare_output_path(output_dir, args.citation_key, args.on_exists)

    base_report = {
        "item_key": args.item_key,
        "citation_key": args.citation_key,
        "path": str(output_path),
        "mode": action,
        "sections_found": sections_meta["sections_found"],
        "warnings": warnings,
    }

    if action == "skip":
        print(json.dumps({"status": "skipped", **base_report,
                          "message": "File exists and --on-exists=skip."}, indent=2))
        return 0

    # R11: build the merged note for update mode (needs the existing note).
    if action == "update":
        if not output_path.exists():
            action = "new"
            base_report["mode"] = "new"
        else:
            try:
                merged = update_existing_note(output_path.read_text(encoding="utf-8"), rendered)
            except UpdateError as exc:
                return _error(
                    f"update refused: existing note is missing anchor '{exc}'. "
                    "Fix the note by hand or use --on-exists versioned.",
                    **base_report,
                )
            rendered = merged

    if args.write:
        try:
            output_dir.mkdir(parents=True, exist_ok=True)  # R8: only on write
            output_path.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            return _error(f"Failed to write note: {exc}", **base_report)
        print(json.dumps({"status": "written", **base_report}, indent=2))
        return 0

    print(json.dumps({"status": "dry_run", **base_report, "chars": len(rendered)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
