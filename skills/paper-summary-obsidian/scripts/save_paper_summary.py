#!/usr/bin/env python3
"""Render and save an Obsidian paper note from summary text + metadata JSON."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SECTION_HEADER_RE = re.compile(r"^\s{0,3}(?:#+\s*)?([1-5])(?:\s*[\.\)])\s*(.*)$")
SYNTHESIS_MARKER_RE = re.compile(r"\bsynthesis of findings\b", re.IGNORECASE)
SYNTHESIS_PREFIX_RE = re.compile(
    r"^\s*(?:[#>\-\+\*]+\s*)?(?:\*\*|__)?\s*synthesis of findings\b[^\n]*\n?",
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

PRIMARY_HEADERS = {
    "s1": "### 💬 Research Question and Motivation %% fold %%",
    "s2": "### 📌 Data and Empirical Strategy %% fold %%",
    "s3": "### 🎯 Results %% fold %%",
    "s4": "### ✒️ Limitations and Extensions %% fold %%",
    "s5": "### 🧩 Comments and Ideas %% fold %%",
}

ADDITIONAL_HEADERS = [
    "### 🗺️ Background, context and connections %% fold %%",
    "### 🚧 Digging and disclaimers %% fold %%",
    "### ❓ Problem formulation %% fold %%",
]


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
    if not date_value:
        return ""
    match = re.match(r"^(\d{4})", date_value)
    return match.group(1) if match else ""


def _format_blockquote(text: str) -> str:
    text = text.strip()
    if not text:
        return "> "
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def _split_summary_sections(summary_text: str) -> dict[str, str]:
    result = {"s1": "", "s2": "", "s3": "", "s4": "", "s5": ""}
    current_key: str | None = None
    saw_markers = False
    preamble: list[str] = []

    for line in summary_text.splitlines():
        marker = SECTION_HEADER_RE.match(line)
        if marker:
            saw_markers = True
            current_key = f"s{marker.group(1)}"
            title = marker.group(2).strip()
            if title and current_key == "s5":
                result[current_key] += f"**{title}**\n"
            continue

        if current_key is None:
            preamble.append(line)
            continue

        result[current_key] += f"{line}\n"

    if saw_markers:
        preamble_text = "\n".join(preamble).strip()
        if preamble_text:
            if result["s1"].strip():
                result["s1"] = f"{preamble_text}\n\n{result['s1'].strip()}\n"
            else:
                result["s1"] = f"{preamble_text}\n"
    else:
        result["s5"] = summary_text.strip()

    for key, value in result.items():
        result[key] = value.strip()

    return result


def _extract_synthesis_summary(section_text: str) -> tuple[str, bool]:
    text = section_text.strip()
    if not text:
        return "", False
    if not SYNTHESIS_MARKER_RE.search(text):
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
            if not bullet_bold.group("indent") and heading_text:
                converted_lines.append(f"#### {heading_text}" if heading_text else "")
                continue

        bullet_bold_prefix = BULLET_BOLD_PREFIX_RE.match(line)
        if bullet_bold_prefix and not bullet_bold_prefix.group("indent"):
            label = _strip_markdown_emphasis(bullet_bold_prefix.group("label")).strip()
            label = HEADING_NUMBER_PREFIX_RE.sub("", label).strip()
            tail = bullet_bold_prefix.group("tail")

            if label.lower() == "paper":
                continue

            if label and _should_convert_bold_prefix_tail(tail):
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
            encoded_path = str(attachment["path"]).replace(" ", "%20")
            info_links.append(f"[**PDF-{idx}**](file:///{encoded_path})")

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
            frontmatter.append(f"  - {author}")

    frontmatter.extend(
        [
            f"year: {year}" if year else "year: ",
            f"date_published: {date_published}" if date_published else "date_published: ",
            f"citekey: {citation_key}",
            f"itemType: {item_type}" if item_type else "itemType: ",
            f"url: {url}" if url else "url: ",
            "cssclasses: lit-note",
            "links:",
            "lit_review:",
        ]
    )

    if doi:
        frontmatter.append(f"doi: {doi}")
    if journal:
        frontmatter.append(f"journal: {journal}")
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


def _prepare_output_path(output_dir: Path, citation_key: str, mode: str) -> tuple[Path, str]:
    base = output_dir / f"@{citation_key}.md"
    if not base.exists():
        return base, "new"
    if mode == "overwrite":
        return base, "overwrite"
    if mode == "versioned":
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        return output_dir / f"@{citation_key}-{stamp}.md", "versioned"
    return base, "skip"


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
        default="/Users/jacopoolivieri/Documents/poodle_obsidian_db/sources/papers",
        help="Directory for rendered Obsidian notes.",
    )
    parser.add_argument(
        "--template-path",
        default="/Users/jacopoolivieri/Documents/poodle_obsidian_db/templates/template zotero.md",
        help="Path to the live template reference file.",
    )
    parser.add_argument(
        "--on-exists",
        choices=["skip", "overwrite", "versioned"],
        default="skip",
        help="How to handle existing @citation_key.md files.",
    )
    parser.add_argument("--write", action="store_true", help="Write file. Without this, dry-run only.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    template_path = Path(args.template_path)
    if not template_path.exists():
        print(
            json.dumps(
                {"status": "error", "message": f"Template not found: {template_path}"},
                indent=2,
            )
        )
        return 1

    template_text = template_path.read_text(encoding="utf-8")
    if "## Reading notes" not in template_text:
        print(
            json.dumps(
                {"status": "error", "message": "Template missing expected '## Reading notes' section."},
                indent=2,
            )
        )
        return 1

    summary_path = Path(args.summary_file)
    metadata_path = Path(args.metadata_file)
    output_dir = Path(args.output_dir)

    if not summary_path.exists():
        print(json.dumps({"status": "error", "message": f"Summary file not found: {summary_path}"}, indent=2))
        return 1
    if not metadata_path.exists():
        print(json.dumps({"status": "error", "message": f"Metadata file not found: {metadata_path}"}, indent=2))
        return 1

    try:
        summary_text = summary_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(json.dumps({"status": "error", "message": f"Failed to read summary file: {exc}"}, indent=2))
        return 1

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("metadata root must be an object")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": f"Invalid metadata JSON: {exc}"}, indent=2))
        return 1

    rendered = render_note(args.item_key, args.citation_key, summary_text, metadata)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path, action = _prepare_output_path(output_dir, args.citation_key, args.on_exists)

    if action == "skip":
        print(
            json.dumps(
                {
                    "status": "skipped",
                    "path": str(output_path),
                    "item_key": args.item_key,
                    "citation_key": args.citation_key,
                    "message": "File exists and --on-exists=skip.",
                },
                indent=2,
            )
        )
        return 0

    if args.write:
        output_path.write_text(rendered, encoding="utf-8")
        print(
            json.dumps(
                {
                    "status": "written",
                    "path": str(output_path),
                    "item_key": args.item_key,
                    "citation_key": args.citation_key,
                    "mode": action,
                },
                indent=2,
            )
        )
        return 0

    print(
        json.dumps(
            {
                "status": "dry_run",
                "path": str(output_path),
                "item_key": args.item_key,
                "citation_key": args.citation_key,
                "mode": action,
                "chars": len(rendered),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
