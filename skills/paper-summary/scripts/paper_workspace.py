#!/usr/bin/env python3
"""Manage paper-summary workspace files inside the papers directory.

Commands
--------
``init``
    Create or refresh a paper workspace from a PDF-to-markdown conversion. The
    converter (docling by default, mineru for theory-heavy papers) writes into
    ``<workspace>/conversion/``; init copies the primary markdown to
    ``paper.md``, splits it into ``sections/*.md``, and initialises ``notes.md``
    from the notes template. It is converter-agnostic — it picks the largest
    ``.md`` under the conversion directory. Refuses to clobber a ``notes.md``
    that has diverged from the template unless ``--force`` is passed. Emits a
    JSON report including ``word_count`` (feeds the short-paper fast path) and
    any ``warnings``.
``write-text``
    Write a staged text file into an existing workspace atomically. With
    ``--mark-processed <name>`` it appends a machine-readable progress marker so
    an interrupted run can resume from the first unprocessed section.

All defaults are read from ``~/.agents/config/paper-skills.json`` (key
``papers_dir``); the script fails loudly with a JSON error naming that path when
it is missing. Errors are reported as ``{"status": "error", "message": ...}``
JSON rather than raw tracebacks.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
from pathlib import Path


CONFIG_PATH = Path("~/.agents/config/paper-skills.json").expanduser()

# Marker written to notes.md by `write-text --mark-processed <name>` so an
# interrupted run can resume from the first unprocessed section.
PROCESSED_MARKER_PREFIX = "<!-- paper-summary:processed "


class WorkspaceError(Exception):
    """A user-facing error that is reported as JSON, not a traceback."""


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise WorkspaceError(
            f"Config file not found: {CONFIG_PATH}. Copy the repo's "
            "config.example.json there and set papers_dir, vault_papers_dir, "
            "and vault_template."
        )
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceError(f"Could not read config {CONFIG_PATH}: {exc}") from exc
    if not isinstance(data, dict):
        raise WorkspaceError(f"Config {CONFIG_PATH} must be a JSON object.")
    return data


def resolve_papers_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    value = load_config().get("papers_dir")
    if not value:
        raise WorkspaceError(
            f"'papers_dir' is not set in {CONFIG_PATH}. Add it (see "
            "config.example.json)."
        )
    return Path(value).expanduser().resolve()


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #

def clean_title(title: str) -> str:
    title = title.replace("\\*", "").replace("*", "").strip()
    title = re.sub(r"\s+", " ", title)
    return title


def slugify(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[^a-z0-9]+", "_", title)
    title = re.sub(r"_+", "_", title).strip("_")
    return title or "section"


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (temp file in same dir + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# Directories a PDF-to-markdown converter may write into, in preference order.
# ``conversion`` is the standard target; ``marker_output`` is accepted for
# backward compatibility with older Marker-based runs.
CONVERSION_DIRS = ("conversion", "marker_output")


def find_converted_markdown(workspace: Path) -> Path | None:
    """Find the primary converted markdown by globbing, not by assuming a layout.

    Converters (docling, mineru, Marker) nest their output differently and do not
    all name the file ``<stem>.md``. The largest ``.md`` under the conversion
    directory is the converted paper, so this is converter-agnostic.
    """
    candidates: list[Path] = []
    for sub in CONVERSION_DIRS:
        candidates += [p for p in workspace.glob(f"{sub}/**/*.md") if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_size)


# --------------------------------------------------------------------------- #
# Section splitting (R1 appendix anchoring, R6 Roman/no-dot headings)
# --------------------------------------------------------------------------- #

def heading_matches(text: str) -> list[tuple[int, int, str]]:
    pattern = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")
    return [(m.start(), m.end(), clean_title(m.group(2))) for m in pattern.finditer(text)]


_ARABIC_HEADING_RE = re.compile(r"^(\d+)[.)]?\s")
# Roman requires a `.`/`)` delimiter (not a bare space) to avoid matching
# ordinary words that happen to be Roman letters (e.g. "Mix Models").
_ROMAN_HEADING_RE = re.compile(
    r"^(m{0,4}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3}))[.)]\s",
    re.IGNORECASE,
)
_LEADING_SECTION_NUMBER_RE = re.compile(r"^(?:\d+|[ivxlcdm]+)[.)]?\s*", re.IGNORECASE)

_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def _roman_to_int(roman: str) -> int:
    total = 0
    prev = 0
    for ch in reversed(roman.lower()):
        value = _ROMAN_VALUES[ch]
        if value < prev:
            total -= value
        else:
            total += value
            prev = value
    return total


def heading_number(title: str) -> int | None:
    """Return the leading section number (Arabic or Roman), or None."""
    m = _ARABIC_HEADING_RE.match(title)
    if m:
        return int(m.group(1))
    m = _ROMAN_HEADING_RE.match(title)
    if m and m.group(1):
        value = _roman_to_int(m.group(1))
        # Cap at a plausible section count so ordinary words that happen to be
        # valid Roman numerals + a delimiter (e.g. "C. elegans" -> 100,
        # "MMXV. Overview" -> 2015) are not mistaken for section numbers.
        if 1 <= value <= 49:
            return value
    return None


def is_numbered_heading(title: str) -> bool:
    return heading_number(title) is not None


# Appendix/references tokens. R1: match as whole words anchored at the start of
# the heading title (after any leading Arabic section number), so headings like
# "2. Estimating Preferences" (contains "references") or "3. Results and
# Appendix Tables" (mid-title "Appendix") no longer truncate the main text.
APPENDIX_START_TOKENS = (
    "online appendix",
    "supplementary appendix",
    "supplementary data",
    "appendix",
    "references",
)

# Strip a leading section number before anchoring: Arabic (optional delimiter)
# or a Roman numeral that carries a `.`/`)` delimiter (so ordinary words are
# left intact). This mirrors the splitter's heading-number handling.
_LEADING_NUMBER_RE = re.compile(
    r"^\s*(?:\d+[.)]?|(?:m{0,4}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3}))[.)])\s*",
    re.IGNORECASE,
)


def is_appendix_heading(title: str) -> bool:
    stripped = _LEADING_NUMBER_RE.sub("", title.lower()).strip()
    return any(
        re.match(rf"{re.escape(token)}\b", stripped) is not None
        for token in APPENDIX_START_TOKENS
    )


def _section_name(title: str) -> str:
    return _LEADING_SECTION_NUMBER_RE.sub("", title).strip()


def split_paper(text: str) -> tuple[str, list[tuple[str, str]], str]:
    matches = heading_matches(text)
    if not matches:
        return text.strip() + "\n", [], ""

    appendix_start = None
    for start, _end, title in matches:
        if is_appendix_heading(title):
            appendix_start = start
            break

    main_text = text[:appendix_start] if appendix_start is not None else text
    appendix_text = text[appendix_start:] if appendix_start is not None else ""

    numbered = [
        (start, end, title)
        for start, end, title in heading_matches(main_text)
        if is_numbered_heading(title)
    ]
    if not numbered:
        return main_text.strip() + "\n", [], appendix_text.strip() + ("\n" if appendix_text else "")

    # Intro (00) is everything before the first heading numbered 2 (Arabic 2 or
    # Roman II); each subsequent numbered heading becomes its own section file.
    section_two_index = next(
        (idx for idx, (_start, _end, title) in enumerate(numbered) if heading_number(title) == 2),
        None,
    )

    if section_two_index is None:
        intro_end = len(main_text)
        remaining: list[tuple[int, int, str]] = []
    else:
        intro_end = numbered[section_two_index][0]
        remaining = numbered[section_two_index:]

    intro_text = main_text[:intro_end].strip() + "\n"

    sections: list[tuple[str, str]] = []
    for idx, (start, _end, title) in enumerate(remaining, start=1):
        content_end = remaining[idx][0] if idx < len(remaining) else len(main_text)
        body = main_text[start:content_end].strip()
        filename = f"{idx:02d}_{slugify(_section_name(title))}.md"
        sections.append((filename, body + "\n"))

    appendix_text = appendix_text.strip()
    if appendix_text:
        appendix_text += "\n"

    return intro_text, sections, appendix_text


def ensure_within(base: Path, path: Path) -> Path:
    base = base.resolve()
    path = path.resolve()
    if path != base and base not in path.parents:
        raise WorkspaceError(f"{path} is outside {base}")
    return path


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #

def cmd_init(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf).expanduser().resolve()
    if not pdf.exists():
        raise WorkspaceError(f"PDF not found: {pdf}")

    paper_dir = resolve_papers_dir(args.paper_dir)
    notes_template = Path(args.notes_template).expanduser().resolve()
    if not notes_template.exists():
        raise WorkspaceError(f"Notes template not found: {notes_template}")
    template_text = notes_template.read_text(encoding="utf-8")

    paper_stem = pdf.stem
    workspace = paper_dir / paper_stem
    workspace.mkdir(parents=True, exist_ok=True)

    # R5: refuse to overwrite a notes.md that has diverged from the template
    # (i.e. contains accumulated work) unless --force is passed.
    notes_md = workspace / "notes.md"
    if notes_md.exists() and not args.force:
        existing = notes_md.read_text(encoding="utf-8")
        if existing.strip() != template_text.strip():
            raise WorkspaceError(
                f"{notes_md} has diverged from the template (it contains notes). "
                "Re-run with --force to discard it, or continue the existing run."
            )

    converted_md = find_converted_markdown(workspace)
    if converted_md is None:
        raise WorkspaceError(
            f"No converted markdown found under {workspace / 'conversion'}. "
            "Convert the PDF first (docling by default, or mineru for theory papers)."
        )

    paper_md = workspace / "paper.md"
    shutil.copy2(converted_md, paper_md)

    sections_dir = workspace / "sections"
    sections_dir.mkdir(parents=True, exist_ok=True)
    for old_file in sections_dir.glob("*.md"):
        old_file.unlink()

    paper_text = paper_md.read_text(encoding="utf-8")
    word_count = len(paper_text.split())
    intro_text, sections, appendix_text = split_paper(paper_text)

    _atomic_write(sections_dir / "00_abstract_and_introduction.md", intro_text)
    for filename, body in sections:
        _atomic_write(sections_dir / filename, body)
    _atomic_write(sections_dir / "appendix.md", appendix_text)

    _atomic_write(notes_md, template_text)

    warnings: list[str] = []
    if len(sections) <= 1:
        warnings.append(
            f"Recovered only {len(sections)} main-text section(s) beyond the "
            "introduction; heading detection may be weak. Inspect paper.md and "
            "record the limitation in notes.md."
        )

    print(
        json.dumps(
            {
                "status": "ok",
                "workspace": str(workspace),
                "paper_md": str(paper_md),
                "notes_md": str(notes_md),
                "sections_dir": str(sections_dir),
                "converted_markdown": str(converted_md),
                "word_count": word_count,
                "section_files": [
                    "00_abstract_and_introduction.md",
                    *[filename for filename, _body in sections],
                    "appendix.md",
                ],
                "warnings": warnings,
            },
            indent=2,
        )
    )
    return 0


def cmd_write_text(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    paper_dir = resolve_papers_dir(args.paper_dir)
    relative = args.relative_path.strip()
    if not relative:
        raise WorkspaceError("--relative-path must name a file inside the workspace.")
    relative_path = Path(relative)
    if relative_path.is_absolute():
        raise WorkspaceError("--relative-path must be relative to the workspace.")

    ensure_within(paper_dir, workspace)
    target = ensure_within(workspace, workspace / relative_path)
    if target == workspace.resolve():
        raise WorkspaceError("--relative-path must name a file, not the workspace root.")

    input_file = Path(args.input_file).expanduser().resolve()
    if not input_file.exists():
        raise WorkspaceError(f"Input file not found: {input_file}")

    text = input_file.read_text(encoding="utf-8")
    if args.mark_processed:
        marker = f"{PROCESSED_MARKER_PREFIX}{args.mark_processed} -->"
        if marker not in text:
            text = text.rstrip("\n") + f"\n\n{marker}\n"

    _atomic_write(target, text)
    print(json.dumps({"status": "ok", "path": str(target)}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage paper-summary workspace files inside the papers directory."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Create or refresh a paper workspace from Marker output.",
    )
    init_parser.add_argument("--pdf", required=True, help="Absolute path to the source PDF.")
    init_parser.add_argument(
        "--paper-dir",
        default=None,
        help="Base directory for paper workspaces (default: papers_dir from config).",
    )
    init_parser.add_argument(
        "--notes-template",
        required=True,
        help="Path to the notes template used to initialise notes.md.",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing notes.md even if it has diverged from the template.",
    )
    init_parser.set_defaults(func=cmd_init)

    write_parser = subparsers.add_parser(
        "write-text",
        help="Write a staged text file into an existing paper workspace (atomic).",
    )
    write_parser.add_argument("--workspace", required=True, help="Paper workspace path.")
    write_parser.add_argument(
        "--paper-dir",
        default=None,
        help="Base directory the workspace must live under (default: papers_dir from config).",
    )
    write_parser.add_argument(
        "--relative-path",
        required=True,
        help="Relative path inside the workspace to overwrite.",
    )
    write_parser.add_argument(
        "--input-file",
        required=True,
        help="Staged text file whose contents will be copied into the workspace.",
    )
    write_parser.add_argument(
        "--mark-processed",
        default=None,
        help="Section file name to record as processed (appends a resume marker).",
    )
    write_parser.set_defaults(func=cmd_write_text)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except WorkspaceError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1
    except OSError as exc:
        # Filesystem/permission failures are reported as JSON, not a traceback.
        print(json.dumps({"status": "error", "message": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
