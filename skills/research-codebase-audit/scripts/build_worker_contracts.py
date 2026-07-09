"""Build the generated audit readme and per-role worker contracts.

The source of truth is ``references/registers.md``. The conductor-only
``Worker contract mapping`` table in that file maps each role to exact section
headings, and this script extracts those sections verbatim into small role
contracts under ``audit/_run/contracts/``.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path
from typing import NamedTuple


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_REGISTERS = SKILL_DIR / "references" / "registers.md"
MAPPING_HEADING = "Worker contract mapping"

HEADING_RE = re.compile(r"^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*$", re.MULTILINE)


class BuildError(RuntimeError):
    """Raised for deterministic build input errors."""


class RoleContract(NamedTuple):
    role: str
    skeleton_files: tuple[str, ...]
    section_headings: tuple[str, ...]


def _heading_spans(text: str) -> dict[str, list[tuple[int, int, int]]]:
    matches = list(HEADING_RE.finditer(text))
    spans: dict[str, list[tuple[int, int, int]]] = {}
    for index, match in enumerate(matches):
        level = len(match.group("marks"))
        title = match.group("title").strip()
        end = len(text)
        for later in matches[index + 1:]:
            if len(later.group("marks")) <= level:
                end = later.start()
                break
        spans.setdefault(title, []).append((level, match.start(), end))
    return spans


def extract_section(text: str, heading: str) -> str:
    """Return the exact Markdown section rooted at *heading*."""
    matches = _heading_spans(text).get(heading, [])
    if not matches:
        raise BuildError(f"mapped heading not found: {heading}")
    if len(matches) > 1:
        raise BuildError(f"mapped heading is ambiguous: {heading}")
    _, start, end = matches[0]
    return text[start:end]


def without_section(text: str, heading: str) -> str:
    """Return *text* with the exact section rooted at *heading* removed."""
    section = extract_section(text, heading)
    return text.replace(section, "", 1)


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def _split_cell_list(cell: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in cell.split(";") if part.strip())


def _split_section_headings(cell: str) -> tuple[str, ...]:
    return tuple(
        part.strip()
        for part in re.split(r";\s+(?=[A-Z])", cell)
        if part.strip()
    )


def load_contract_mapping(registers_text: str) -> tuple[RoleContract, ...]:
    section = extract_section(registers_text, MAPPING_HEADING)
    rows = [_split_table_row(line) for line in section.splitlines()]
    rows = [row for row in rows if row]
    if len(rows) < 3:
        raise BuildError("worker contract mapping table is missing")

    header = [cell.lower() for cell in rows[0]]
    expected = ["role", "skeleton files", "section headings"]
    if header != expected:
        raise BuildError(
            "worker contract mapping header must be: "
            "| Role | Skeleton files | Section headings |"
        )

    contracts: list[RoleContract] = []
    seen_roles: set[str] = set()
    for row in rows[2:]:
        if len(row) != 3:
            raise BuildError(f"bad worker contract mapping row: {row}")
        role, skeleton_cell, heading_cell = row
        if not re.fullmatch(r"[a-z0-9_]+", role):
            raise BuildError(f"bad worker contract role: {role}")
        if role in seen_roles:
            raise BuildError(f"duplicate worker contract role: {role}")
        seen_roles.add(role)

        skeleton_files = _split_cell_list(skeleton_cell)
        section_headings = _split_section_headings(heading_cell)
        if not skeleton_files:
            raise BuildError(f"{role}: no skeleton files mapped")
        if not section_headings:
            raise BuildError(f"{role}: no section headings mapped")
        contracts.append(RoleContract(role, skeleton_files, section_headings))

    return tuple(contracts)


def compose_readme(registers_text: str) -> str:
    """Full readme content, excluding conductor-only contract wiring."""
    return without_section(registers_text, MAPPING_HEADING)


def compose_contract(registers_text: str, contract: RoleContract) -> str:
    lines = [
        f"# Worker contract: {contract.role}",
        "",
        "Generated from `references/registers.md`; do not edit by hand.",
        "Mapped skeletons: " + ", ".join(contract.skeleton_files),
        "",
    ]
    body = "\n".join(lines)
    for heading in contract.section_headings:
        body += extract_section(registers_text, heading).rstrip() + "\n\n"
    return body


def build_artifacts(registers_path: Path, audit_dir: Path) -> dict[str, Path]:
    registers_text = registers_path.read_text(encoding="utf-8")
    contracts = load_contract_mapping(registers_text)

    # Validate every mapped heading before writing anything.
    for contract in contracts:
        for heading in contract.section_headings:
            extract_section(registers_text, heading)

    audit_dir.mkdir(parents=True, exist_ok=True)
    contracts_dir = audit_dir / "_run" / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, Path] = {}
    readme_path = audit_dir / "audit_readme.md"
    readme_path.write_text(compose_readme(registers_text), encoding="utf-8")
    artifacts["audit_readme.md"] = readme_path

    for contract in contracts:
        rel = f"_run/contracts/{contract.role}.md"
        path = audit_dir / rel
        path.write_text(compose_contract(registers_text, contract), encoding="utf-8")
        artifacts[rel] = path

    return artifacts


def measurement_rows(artifacts: dict[str, Path]) -> list[tuple[str, int, int]]:
    rows = []
    for rel in sorted(artifacts):
        chars = len(artifacts[rel].read_text(encoding="utf-8"))
        rows.append((rel, chars, math.ceil(chars / 4)))
    return rows


def print_measurements(artifacts: dict[str, Path]) -> None:
    print("artifact\tchars\tapprox_tokens")
    for rel, chars, tokens in measurement_rows(artifacts):
        print(f"{rel}\t{chars}\t{tokens}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registers",
        type=Path,
        default=DEFAULT_REGISTERS,
        help="Path to references/registers.md.",
    )
    parser.add_argument(
        "--audit-dir",
        type=Path,
        default=Path("audit"),
        help="Audit directory to write into.",
    )
    parser.add_argument(
        "--measure",
        action="store_true",
        help="Print character and approximate-token sizes after building.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        artifacts = build_artifacts(args.registers, args.audit_dir)
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.measure:
        print_measurements(artifacts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
