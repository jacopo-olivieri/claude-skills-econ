#!/usr/bin/env python3
"""Search local Stata PDF manuals with optional context windows.

Examples:
    python3 scripts/search_stata_docs.py "merge" --pdf d.pdf
    python3 scripts/search_stata_docs.py "xtreg" --pdf xt.pdf --pages 1-200
    python3 scripts/search_stata_docs.py "teffects" --max-results 20 --context 3
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_DOCS_DIR = Path("/Applications/Stata/docs")


def parse_pages(pages_arg: str | None, total_pages: int) -> set[int] | None:
    """Parse 1-based page ranges like '1-10,20,25-30'."""
    if not pages_arg:
        return None

    pages: set[int] = set()
    for chunk in pages_arg.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue

        if "-" in chunk:
            try:
                start_s, end_s = chunk.split("-", 1)
                start = int(start_s)
                end = int(end_s)
            except ValueError as exc:
                raise ValueError(f"Invalid range: {chunk}") from exc
            if start < 1 or end < 1 or end < start:
                raise ValueError(f"Invalid range bounds: {chunk}")
            pages.update(range(start - 1, min(end, total_pages)))
        else:
            try:
                page = int(chunk)
            except ValueError as exc:
                raise ValueError(f"Invalid page number: {chunk}") from exc
            if page < 1:
                raise ValueError(f"Page numbers must be >= 1: {chunk}")
            if page <= total_pages:
                pages.add(page - 1)

    return pages


def import_pdfplumber():
    """Import pdfplumber lazily and print actionable guidance if missing."""
    try:
        import pdfplumber  # type: ignore
    except ModuleNotFoundError:
        print("pdfplumber is not installed.", file=sys.stderr)
        print("Install with: python3 -m pip install --user pdfplumber", file=sys.stderr)
        print(
            "Or run once with: uv run --with pdfplumber python3 scripts/search_stata_docs.py \"term\"",
            file=sys.stderr,
        )
        sys.exit(2)
    return pdfplumber


def iter_pdf_paths(docs_dir: Path, pdf_name: str | None) -> list[Path]:
    if pdf_name:
        normalized = pdf_name if pdf_name.endswith(".pdf") else f"{pdf_name}.pdf"
        path = docs_dir / normalized
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")
        return [path]

    pdfs = sorted(docs_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDFs found under {docs_dir}")
    return pdfs


def build_pattern(term: str, regex: bool, ignore_case: bool) -> re.Pattern[str]:
    flags = re.IGNORECASE if ignore_case else 0
    pattern = term if regex else re.escape(term)
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        raise ValueError(f"Invalid regex: {exc}") from exc


def search_pdf(pdfplumber, pdf_path: Path, pattern: re.Pattern[str], context: int, pages_arg: str | None,
               remaining: int) -> list[tuple[int, str, list[str]]]:
    matches: list[tuple[int, str, list[str]]] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        page_filter = parse_pages(pages_arg, len(pdf.pages))
        for page_idx, page in enumerate(pdf.pages):
            if page_filter is not None and page_idx not in page_filter:
                continue

            text = page.extract_text() or ""
            if not text:
                continue

            lines = [line.rstrip() for line in text.splitlines()]
            for line_idx, line in enumerate(lines):
                if not pattern.search(line):
                    continue

                start = max(0, line_idx - context)
                end = min(len(lines), line_idx + context + 1)
                context_lines = lines[start:end]

                matches.append((page_idx + 1, line.strip(), context_lines))
                if len(matches) >= remaining:
                    return matches

    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description="Search local Stata PDF manuals")
    parser.add_argument("search_term", help="Text or regex to search for")
    parser.add_argument("--pdf", help="Single manual filename, e.g. d.pdf or r.pdf")
    parser.add_argument("--docs-dir", default=str(DEFAULT_DOCS_DIR), help=f"Manual directory (default: {DEFAULT_DOCS_DIR})")
    parser.add_argument("--pages", help="1-based page list/range, e.g. 1-50,120,140-160")
    parser.add_argument("--context", type=int, default=2, help="Lines before/after each hit (default: 2)")
    parser.add_argument("--max-results", type=int, default=30, help="Maximum hits to print (default: 30)")
    parser.add_argument("--regex", action="store_true", help="Treat search_term as regex")
    parser.add_argument("--case-sensitive", action="store_true", help="Use case-sensitive matching")
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir)
    if not docs_dir.exists():
        print(f"Docs directory not found: {docs_dir}", file=sys.stderr)
        return 1

    if not args.pdf:
        print(
            "Warning: scanning all Stata manuals is slow (roughly 45 seconds); "
            "prefer --pdf <manual> when possible.",
            file=sys.stderr,
        )

    try:
        pdf_paths = iter_pdf_paths(docs_dir, args.pdf)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        pattern = build_pattern(args.search_term, args.regex, not args.case_sensitive)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    pdfplumber = import_pdfplumber()

    printed = 0
    for pdf_path in pdf_paths:
        if printed >= args.max_results:
            break

        remaining = args.max_results - printed
        try:
            matches = search_pdf(pdfplumber, pdf_path, pattern, max(args.context, 0), args.pages, remaining)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except Exception as exc:  # Keep search resilient across mixed PDF quality
            print(f"Failed reading {pdf_path.name}: {exc}", file=sys.stderr)
            continue

        for page_num, line, context_lines in matches:
            print(f"{pdf_path.name}:{page_num}: {line}")
            if args.context > 0:
                for ctx in context_lines:
                    print(f"    {ctx}")
            print()

        printed += len(matches)

    if printed == 0:
        print(f"No results found for: {args.search_term}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
