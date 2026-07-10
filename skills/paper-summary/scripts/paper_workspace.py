#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


DEFAULT_PAPER_DIR = Path("/Users/jacopoolivieri/Documents/05_sources/04_papers")


def clean_title(title: str) -> str:
    title = title.replace("\\*", "").replace("*", "").strip()
    title = re.sub(r"\s+", " ", title)
    return title


def slugify(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[^a-z0-9]+", "_", title)
    title = re.sub(r"_+", "_", title).strip("_")
    return title or "section"


def marker_markdown_path(workspace: Path, paper_stem: str) -> Path:
    return workspace / "marker_output" / paper_stem / f"{paper_stem}.md"


def heading_matches(text: str) -> list[tuple[int, int, str]]:
    pattern = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")
    return [(m.start(), m.end(), clean_title(m.group(2))) for m in pattern.finditer(text)]


def is_numbered_heading(title: str) -> bool:
    return re.match(r"^\d+\.\s+", title) is not None


def is_appendix_heading(title: str) -> bool:
    lowered = title.lower()
    return any(
        token in lowered
        for token in (
            "appendix",
            "online appendix",
            "supplementary appendix",
            "supplementary data",
            "references",
        )
    )


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

    section_two_index = next(
        (idx for idx, (_start, _end, title) in enumerate(numbered) if title.startswith("2.")),
        None,
    )

    if section_two_index is None:
        intro_end = len(main_text)
        remaining = []
    else:
        intro_end = numbered[section_two_index][0]
        remaining = numbered[section_two_index:]

    intro_text = main_text[:intro_end].strip() + "\n"

    sections: list[tuple[str, str]] = []
    for idx, (start, _end, title) in enumerate(remaining, start=1):
        content_end = remaining[idx][0] if idx < len(remaining) else len(main_text)
        body = main_text[start:content_end].strip()
        section_name = re.sub(r"^\d+\.\s*", "", title).strip()
        filename = f"{idx:02d}_{slugify(section_name)}.md"
        sections.append((filename, body + "\n"))

    appendix_text = appendix_text.strip()
    if appendix_text:
        appendix_text += "\n"

    return intro_text, sections, appendix_text


def ensure_within(base: Path, path: Path) -> Path:
    base = base.resolve()
    path = path.resolve()
    if path != base and base not in path.parents:
        raise ValueError(f"{path} is outside {base}")
    return path


def cmd_init(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf).expanduser().resolve()
    if not pdf.exists():
        raise FileNotFoundError(f"PDF not found: {pdf}")

    paper_dir = Path(args.paper_dir).expanduser().resolve()
    notes_template = Path(args.notes_template).expanduser().resolve()
    if not notes_template.exists():
        raise FileNotFoundError(f"Notes template not found: {notes_template}")

    paper_stem = pdf.stem
    workspace = paper_dir / paper_stem
    workspace.mkdir(parents=True, exist_ok=True)

    marker_md = marker_markdown_path(workspace, paper_stem)
    if not marker_md.exists():
        raise FileNotFoundError(f"Marker markdown not found: {marker_md}")

    paper_md = workspace / "paper.md"
    shutil.copy2(marker_md, paper_md)

    sections_dir = workspace / "sections"
    sections_dir.mkdir(parents=True, exist_ok=True)
    for old_file in sections_dir.glob("*.md"):
        old_file.unlink()

    paper_text = paper_md.read_text(encoding="utf-8")
    intro_text, sections, appendix_text = split_paper(paper_text)

    (sections_dir / "00_abstract_and_introduction.md").write_text(intro_text, encoding="utf-8")
    for filename, body in sections:
        (sections_dir / filename).write_text(body, encoding="utf-8")
    (sections_dir / "appendix.md").write_text(appendix_text, encoding="utf-8")

    notes_md = workspace / "notes.md"
    shutil.copy2(notes_template, notes_md)

    print(
        json.dumps(
            {
                "workspace": str(workspace),
                "paper_md": str(paper_md),
                "notes_md": str(notes_md),
                "sections_dir": str(sections_dir),
                "section_files": [
                    "00_abstract_and_introduction.md",
                    *[filename for filename, _body in sections],
                    "appendix.md",
                ],
            },
            indent=2,
        )
    )
    return 0


def cmd_write_text(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    paper_dir = Path(args.paper_dir).expanduser().resolve()
    relative_path = Path(args.relative_path)
    if relative_path.is_absolute():
        raise ValueError("--relative-path must be relative to the workspace")

    ensure_within(paper_dir, workspace)
    target = ensure_within(workspace, workspace / relative_path)
    input_file = Path(args.input_file).expanduser().resolve()
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(input_file.read_text(encoding="utf-8"), encoding="utf-8")
    print(str(target))
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
        default=str(DEFAULT_PAPER_DIR),
        help="Base directory for paper workspaces.",
    )
    init_parser.add_argument(
        "--notes-template",
        required=True,
        help="Path to the notes template used to initialise notes.md.",
    )
    init_parser.set_defaults(func=cmd_init)

    write_parser = subparsers.add_parser(
        "write-text",
        help="Write a staged text file into an existing paper workspace.",
    )
    write_parser.add_argument("--workspace", required=True, help="Paper workspace path.")
    write_parser.add_argument(
        "--paper-dir",
        default=str(DEFAULT_PAPER_DIR),
        help="Base directory that the workspace must live under.",
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
    write_parser.set_defaults(func=cmd_write_text)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
