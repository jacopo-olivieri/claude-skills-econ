#!/usr/bin/env python3
"""Emit or re-check the b3d detector mapping closure artifact."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import check_manifests as mf
import cv_scan
import definition_use as du


MAPPING_COLS = [
    "Channel", "Source ID", "Witness ID", "Error ID", "Mapping Kind",
    "Site Anchor",
]
DECISION_COLS = ["Channel", "Source ID", "Error ID", "Mapping Kind"]
MAPPING_KINDS = {"new_candidate", "existing_row", "reviewed_not_divergent"}
MARKERS = ["<!-- GENERATED:DU -->", "<!-- GENERATED:MF -->", "<!-- CONDUCTOR:CV -->"]
DU_ZERO = "No standard DU rows: the definition/use detector emitted zero standard candidates."
MF_ZERO = "No standard MF rows: the manifest detector emitted zero standard candidates."
CV_ZERO = "No channel-mapped CV rows: no conventions were consolidated for this run."
RANGE_RE = re.compile(r"^Declared detector Error-ID range:\s*(E-\d{4})[–-](E-\d{4})\s*$", re.M)
ERROR_COLS = [
    "Error ID", "Error Type", "Code/Data Source", "Code Location", "Status",
    "Severity", "Error Description", "Why It Matters", "Related Claim IDs",
]
LINEAGE_COLS = [
    "Original Error ID", "Descendant Error ID", "Channel", "Source ID",
    "Witness ID",
]


class MappingError(RuntimeError):
    """Detector closure is incomplete or malformed."""


def _norm(value):
    return str(value).strip().strip("`").strip()


def _table(text, columns, label):
    matches = []
    for headers, rows, _line in du.parse_markdown_tables(text):
        if headers == columns:
            matches.append(rows)
    if len(matches) != 1:
        raise MappingError(f"{label}: expected exactly one {' | '.join(columns)} table")
    parsed = []
    for index, row in enumerate(matches[0], start=1):
        if len(row) != len(columns):
            raise MappingError(f"{label}: malformed row {index}")
        parsed.append(dict(zip(columns, [_norm(cell) for cell in row])))
    return parsed


def _parse_range(text, label):
    matches = RANGE_RE.findall(text)
    if len(matches) != 1:
        raise MappingError(f"{label}: expected one declared detector Error-ID range")
    start, end = matches[0]
    a, b = int(start[2:]), int(end[2:])
    if a > b:
        raise MappingError(f"{label}: detector range starts after it ends")
    if b >= 9999:
        raise MappingError(
            f"{label}: code-error register identifier space exhausted at E-9999 "
            "(four-digit IDs cannot wrap)"
        )
    return ("E", a, b), f"E-{a:04d}–E-{b:04d}"


def _in_range(error_id, declared):
    return bool(re.fullmatch(r"E-\d{4}", error_id)) and declared[1] <= int(error_id[2:]) <= declared[2]


def parse_raw_sources(audit):
    du_path = audit / "_run" / "definition_use_bundles.md"
    mf_path = audit / "_run" / "manifest_check.md"
    for path in (du_path, mf_path):
        if not path.is_file():
            raise MappingError(f"missing raw detector artifact: {path}")
    try:
        du_artifact = du.parse_artifact(du_path.read_text(encoding="utf-8"))
    except du.DefinitionUseFormatError as exc:
        raise MappingError(f"{du_path}: {exc}") from exc
    sources = {"DU": {}, "MF": {}}
    for row in du_artifact.standard_rows:
        source_id = row["Bundle ID"]
        witness_id = row["Witness ID"]
        if not re.fullmatch(r"DU-[0-9a-f]{12}", source_id):
            raise MappingError(f"invalid DU source ID {source_id}")
        if not re.fullmatch(r"DUW-[0-9a-f]{12}", witness_id):
            raise MappingError(f"invalid DU witness ID {witness_id}")
        sources["DU"].setdefault(source_id, []).append(
            {"witness_id": witness_id, "anchor": row["Consumer Site"]}
        )

    mf_text = mf_path.read_text(encoding="utf-8")
    if mf.MF_ZERO_LINE in mf_text:
        if "| Source ID | Manifest | Format | Consumer Role | Witness Count |" in mf_text:
            raise MappingError(f"{mf_path}: explicit zero conflicts with an MF source table")
    else:
        candidates = _table(
            mf_text, ["Source ID", "Manifest", "Format", "Consumer Role", "Witness Count"],
            str(mf_path),
        )
        witnesses = _table(
            mf_text, ["Source ID", "Witness ID", "Site Anchor", "Rule Slug", "Offending Text", "Problem"],
            str(mf_path),
        )
        counts = {}
        for row in candidates:
            source_id = row["Source ID"]
            if not re.fullmatch(r"MF-[0-9a-f]{12}", source_id):
                raise MappingError(f"invalid MF source ID {source_id}")
            if source_id in counts:
                raise MappingError(f"duplicate MF source ID {source_id}")
            try:
                counts[source_id] = int(row["Witness Count"])
            except ValueError as exc:
                raise MappingError(f"MF source {source_id} has invalid witness count") from exc
            sources["MF"][source_id] = []
        seen_witnesses = set()
        for row in witnesses:
            source_id, witness_id = row["Source ID"], row["Witness ID"]
            if source_id not in sources["MF"]:
                raise MappingError(f"MF witness {witness_id} names unknown source {source_id}")
            if not re.fullmatch(r"MFW-[0-9a-f]{12}", witness_id):
                raise MappingError(f"invalid MF witness ID {witness_id}")
            if witness_id in seen_witnesses:
                raise MappingError(f"duplicate MF witness ID {witness_id}")
            seen_witnesses.add(witness_id)
            if row["Rule Slug"] not in mf.RULE_SLUGS:
                raise MappingError(f"MF witness {witness_id} has unknown rule slug {row['Rule Slug']}")
            sources["MF"][source_id].append(
                {"witness_id": witness_id, "anchor": row["Site Anchor"]}
            )
        for source_id, expected in counts.items():
            actual = len(sources["MF"][source_id])
            if actual != expected:
                raise MappingError(
                    f"MF source {source_id} declares {expected} witnesses but has {actual}"
                )
    return sources


def parse_decisions(path):
    if not path.is_file():
        raise MappingError(f"missing detector decisions table: {path}")
    text = path.read_text(encoding="utf-8")
    declared, display = _parse_range(text, str(path))
    rows = _table(text, DECISION_COLS, str(path))
    decisions = {}
    for row in rows:
        channel, source_id = row["Channel"], row["Source ID"]
        key = (channel, source_id)
        if channel not in {"DU", "MF", "CV"}:
            raise MappingError(f"decision names unsupported channel {channel}")
        if key in decisions:
            raise MappingError(f"duplicate decision for {source_id}")
        if row["Mapping Kind"] not in MAPPING_KINDS:
            raise MappingError(f"decision for {source_id} has invalid Mapping Kind {row['Mapping Kind']}")
        kind = row["Mapping Kind"]
        if kind == "reviewed_not_divergent":
            if channel != "CV":
                raise MappingError(
                    f"reviewed_not_divergent is legal only on CV, not {channel}"
                )
            if row["Error ID"] != "—":
                raise MappingError(
                    f"reviewed_not_divergent decision for {source_id} must use Error ID —"
                )
        elif not re.fullmatch(r"E-\d{4}", row["Error ID"]):
            raise MappingError(f"decision for {source_id} has invalid Error ID {row['Error ID']}")
        decisions[key] = row
    return declared, display, decisions


def _manifest_mode(audit):
    path = audit / "_run" / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MappingError(f"cannot read manifest mode from {path}: {exc}") from exc
    mode = manifest.get("mode") if isinstance(manifest, dict) else None
    if mode not in {"replication", "code_errors_only"}:
        raise MappingError(f"{path}: unsupported manifest mode {mode!r}")
    return mode


def _validate_cv_closure(conventions, parsed, label):
    """Tier-1 closure seam: every consolidated convention has one scan verdict."""
    return cv_scan.validate_closure(conventions, parsed, label)


def _validate_cv_decision(source_id, source, kind):
    """Tier-1 receipt seam for the CV-only dismissal mapping kind."""
    verdict = source["verdict"]
    if verdict == "divergent" and kind == "reviewed_not_divergent":
        raise MappingError(
            f"reviewed_not_divergent decision for {source_id} conflicts with divergent verdict"
        )
    if verdict == "not_divergent" and kind != "reviewed_not_divergent":
        raise MappingError(
            f"not_divergent verdict for {source_id} requires reviewed_not_divergent decision"
        )


def parse_cv_sources(audit):
    """Load CV identities from the frozen scan, enforcing mode and freeze rules."""
    mode = _manifest_mode(audit)
    conventions_path = audit / "_run" / "conventions.md"
    live_scan = audit / "_run" / "cv_scan.md"
    frozen_scan = audit / "_run" / "snapshots" / "code_b3d" / "cv_scan.md"
    if mode == "code_errors_only":
        stray = [path for path in (conventions_path, live_scan, frozen_scan) if path.exists()]
        if stray:
            raise MappingError(
                "code-errors-only mode refuses conventions/CV artifact: "
                + ", ".join(str(path) for path in stray)
            )
        return {}
    try:
        conventions = cv_scan.parse_conventions(conventions_path)
    except cv_scan.CVScanError as exc:
        raise MappingError(str(exc)) from exc
    if not conventions:
        stray = [path for path in (live_scan, frozen_scan) if path.exists()]
        if stray:
            raise MappingError(
                "empty conventions artifact requires exact CV explicit-zero; stray scan: "
                + ", ".join(str(path) for path in stray)
            )
        return {}
    if not live_scan.is_file():
        raise MappingError(f"missing conventions scan artifact: {live_scan}")
    if not frozen_scan.is_file():
        raise MappingError(f"missing frozen conventions scan artifact: {frozen_scan}")
    if live_scan.read_bytes() != frozen_scan.read_bytes():
        raise MappingError(
            f"live conventions scan differs from frozen code_b3d snapshot: {live_scan}"
        )
    try:
        parsed = cv_scan.parse_scan(frozen_scan)
        _validate_cv_closure(conventions, parsed, str(frozen_scan))
    except cv_scan.CVScanError as exc:
        raise MappingError(str(exc)) from exc
    return {
        source.source_id: {
            "verdict": source.verdict,
            "convention": source.convention,
            "category": source.category,
            "witnesses": [
                {"witness_id": witness.witness_id, "anchor": witness.anchor}
                for witness in source.witnesses
            ],
        }
        for source in parsed
    }


def parse_register(path):
    if not path.is_file():
        raise MappingError(f"missing code-error register: {path}")
    rows = _table(path.read_text(encoding="utf-8"), ERROR_COLS, str(path))
    by_id = {}
    for row in rows:
        error_id = row["Error ID"]
        if error_id in by_id:
            raise MappingError(f"{path}: Error ID {error_id} appears more than once")
        by_id[error_id] = row
    return by_id


def _raw_register_rows(path):
    """Return Error-ID -> exact Markdown row bytes for the canonical table."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    wanted = "| " + " | ".join(ERROR_COLS) + " |"
    for index, line in enumerate(lines[:-1]):
        if line.rstrip("\r\n").strip() != wanted:
            continue
        rows = {}
        for raw in lines[index + 2:]:
            if not raw.lstrip().startswith("|"):
                break
            cells = du.split_markdown_row(raw.rstrip("\r\n"))
            if len(cells) != len(ERROR_COLS):
                raise MappingError(f"{path}: malformed code-error register row")
            error_id = _norm(cells[0])
            if error_id in rows:
                raise MappingError(f"{path}: Error ID {error_id} appears more than once")
            rows[error_id] = raw.encode("utf-8")
        return rows
    raise MappingError(f"{path}: expected exactly one {' | '.join(ERROR_COLS)} table")


def _validate_staging_converse(register_path, snapshot_path, decisions, register,
                               snapshot):
    new_ids = {row["Error ID"] for row in decisions.values()
               if row["Mapping Kind"] == "new_candidate"}
    expected = set(snapshot) | new_ids
    actual = set(register)
    if actual != expected:
        extra = sorted(actual - expected)
        missing = sorted(expected - actual)
        detail = []
        if extra:
            detail.append("stray staged row(s): " + ", ".join(extra))
        if missing:
            detail.append("deleted or missing staged row(s): " + ", ".join(missing))
        raise MappingError("b3d staged-register key closure failed: " + "; ".join(detail))
    staged_bytes = _raw_register_rows(register_path)
    snapshot_bytes = _raw_register_rows(snapshot_path)
    mutated = sorted(eid for eid in snapshot if staged_bytes[eid] != snapshot_bytes[eid])
    if mutated:
        raise MappingError(
            "b3d staged register mutated pre-existing row(s): " + ", ".join(mutated)
        )


def _validate_replay_key_closure(audit, register, snapshot, decisions):
    new_ids = {row["Error ID"] for row in decisions.values()
               if row["Mapping Kind"] == "new_candidate"}
    # ``register`` is the frozen post-b3b image during replay.  Later b6a/bC
    # discoveries and split descendants are intentionally outside b3d's era.
    expected = set(snapshot) | new_ids
    actual = set(register)
    if actual != expected:
        extra = sorted(actual - expected)
        missing = sorted(expected - actual)
        detail = []
        if extra:
            detail.append("undeclared canonical row(s): " + ", ".join(extra))
        if missing:
            detail.append("missing canonical row(s): " + ", ".join(missing))
        raise MappingError("b3d replay key closure failed: " + "; ".join(detail))


def _expected_rows(sources, decisions, declared, register, snapshot,
                   enforce_candidate):
    source_keys = {(channel, source_id) for channel, values in sources.items()
                   for source_id in values}
    for channel, source_id in sorted(set(decisions) - source_keys):
        raise MappingError(f"decision names unknown detector source {source_id}")
    for channel, source_id in sorted(source_keys - set(decisions)):
        raise MappingError(f"unmapped detector source {source_id}")
    rows = {"DU": [], "MF": [], "CV": []}
    for key in sorted(decisions):
        channel, source_id = key
        decision = decisions[key]
        error_id, kind = decision["Error ID"], decision["Mapping Kind"]
        source = sources[channel][source_id]
        if channel == "CV":
            _validate_cv_decision(source_id, source, kind)
        if kind == "reviewed_not_divergent":
            for witness in source["witnesses"]:
                rows[channel].append({
                    "Channel": channel, "Source ID": source_id,
                    "Witness ID": witness["witness_id"], "Error ID": "—",
                    "Mapping Kind": kind, "Site Anchor": witness["anchor"],
                })
            continue
        target = register.get(error_id)
        if target is None:
            raise MappingError(f"{source_id} maps to missing register row {error_id}")
        if kind == "new_candidate":
            if not _in_range(error_id, declared):
                raise MappingError(f"new_candidate {source_id} uses {error_id} outside declared range")
            if error_id in snapshot:
                raise MappingError(f"new_candidate {source_id} collides with pre-b3d row {error_id}")
            if enforce_candidate and target.get("Status") != "candidate":
                raise MappingError(f"new_candidate {source_id} maps to {error_id}, which is not candidate")
        witnesses = source["witnesses"] if channel == "CV" else source
        for witness in witnesses:
            rows[channel].append({
                "Channel": channel, "Source ID": source_id,
                "Witness ID": witness["witness_id"], "Error ID": error_id,
                "Mapping Kind": kind, "Site Anchor": witness["anchor"],
            })
    return rows


def _render_section(marker, rows, zero):
    lines = [marker, ""]
    if not rows:
        return lines + [zero, ""]
    lines += ["| " + " | ".join(MAPPING_COLS) + " |",
              "| " + " | ".join(["---"] * len(MAPPING_COLS)) + " |"]
    for row in sorted(rows, key=lambda r: (r["Source ID"], r["Witness ID"])):
        lines.append("| " + " | ".join(row[column].replace("|", "\\|")
                                          for column in MAPPING_COLS) + " |")
    return lines + [""]


def render_mapping(display_range, rows):
    lines = ["# Detector mapping", "", f"Declared detector Error-ID range: {display_range}", ""]
    lines += _render_section(MARKERS[0], rows["DU"], DU_ZERO)
    lines += _render_section(MARKERS[1], rows["MF"], MF_ZERO)
    lines += _render_section(MARKERS[2], rows.get("CV", []), CV_ZERO)
    return "\n".join(lines).rstrip() + "\n"


def parse_mapping_text(text):
    positions = []
    for marker in MARKERS:
        if text.count(marker) != 1:
            raise MappingError(f"detector mapping must contain marker {marker} exactly once")
        positions.append(text.index(marker))
    if positions != sorted(positions):
        raise MappingError("detector mapping markers are out of order")
    declared, display = _parse_range(text, "detector mapping")
    rows = []
    for index, (marker, zero) in enumerate(zip(MARKERS, (DU_ZERO, MF_ZERO, CV_ZERO))):
        start = positions[index] + len(marker)
        end = positions[index + 1] if index + 1 < len(positions) else len(text)
        section = text[start:end]
        tables = [(headers, table_rows) for headers, table_rows, _ in du.parse_markdown_tables(section)
                  if headers == MAPPING_COLS]
        if zero in section:
            if tables:
                raise MappingError(f"{marker} contains both its explicit zero and mapping rows")
            continue
        if len(tables) != 1:
            raise MappingError(f"{marker} is missing its mapping table or explicit zero")
        for raw in tables[0][1]:
            if len(raw) != len(MAPPING_COLS):
                raise MappingError(f"{marker} contains a malformed mapping row")
            row = dict(zip(MAPPING_COLS, [_norm(cell) for cell in raw]))
            expected_channel = ("DU", "MF", "CV")[index]
            if row["Channel"] != expected_channel:
                raise MappingError(
                    f"{marker} contains row for channel {row['Channel']}, expected {expected_channel}"
                )
            if row["Mapping Kind"] not in MAPPING_KINDS:
                raise MappingError(
                    f"{marker} contains invalid Mapping Kind {row['Mapping Kind']}"
                )
            if row["Mapping Kind"] == "reviewed_not_divergent":
                if expected_channel != "CV" or row["Error ID"] != "—":
                    raise MappingError(
                        "reviewed_not_divergent mapping rows are CV-only and require Error ID —"
                    )
            elif not re.fullmatch(r"E-\d{4}", row["Error ID"]):
                raise MappingError(f"{marker} contains invalid Error ID {row['Error ID']}")
            rows.append(row)
    keys = [(row["Channel"], row["Source ID"], row["Witness ID"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise MappingError("detector mapping contains a duplicate channel/source/witness key")
    return declared, display, rows


def load_mapping(path):
    if not Path(path).is_file():
        raise MappingError(f"missing detector mapping artifact: {path}")
    return parse_mapping_text(Path(path).read_text(encoding="utf-8"))


def actionable_rows(rows):
    """Return rows that require a register row and adjudication disposition."""
    return [row for row in rows
            if row.get("Mapping Kind") != "reviewed_not_divergent"]


def _paths(package_root, audit, check):
    if check:
        frozen = audit / "_run/snapshots/code_b3b/code_error_register.md"
        register = frozen if frozen.is_file() else audit / "code_error_register.md"
    else:
        register = audit / "_staging/code_error_register.md"
    snapshot = audit / "_run/snapshots/code_b3d/code_error_register.md"
    return register, snapshot


def validate_inputs(package_root, audit, check=False):
    sources = parse_raw_sources(audit)
    sources["CV"] = parse_cv_sources(audit)
    declared, display, decisions = parse_decisions(
        audit / "_run" / "detector_mapping_decisions.md")
    register_path, snapshot_path = _paths(package_root, audit, check)
    register = parse_register(register_path)
    snapshot = parse_register(snapshot_path)
    expected = _expected_rows(
        sources, decisions, declared, register, snapshot, enforce_candidate=not check)
    if check:
        _validate_replay_key_closure(audit, register, snapshot, decisions)
    else:
        _validate_staging_converse(
            register_path, snapshot_path, decisions, register, snapshot)
    return display, expected


def _reproducibility_check(package_root, audit):
    with tempfile.TemporaryDirectory(prefix="rca-detectors-") as tmp:
        temp = Path(tmp)
        commands = [
            ([sys.executable, str(Path(__file__).with_name("emit_definition_use_bundles.py")),
              str(package_root), "--audit-dir", str(audit), "-o", str(temp / "definition_use_bundles.md")],
             audit / "_run/definition_use_bundles.md"),
            ([sys.executable, str(Path(__file__).with_name("check_manifests.py")),
              str(package_root), "--audit-dir", str(audit), "-o", str(temp / "manifest_check.md")],
             audit / "_run/manifest_check.md"),
        ]
        for command, recorded in commands:
            result = subprocess.run(command, cwd=package_root, capture_output=True, text=True)
            if result.returncode != 0:
                raise MappingError(
                    f"detector reproducibility run failed for {recorded.name}: "
                    f"{(result.stdout + result.stderr).strip()}"
                )
            fresh = temp / recorded.name
            if fresh.read_bytes() != recorded.read_bytes():
                raise MappingError(f"detector artifact is stale or edited: {recorded}")


def emit(package_root, audit, output):
    display, rows = validate_inputs(package_root, audit, check=False)
    payload = render_mapping(display, rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".detector_mapping.", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temp_name, output)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def check(package_root, audit, output):
    display, expected = validate_inputs(package_root, audit, check=True)
    declared, artifact_display, actual_rows = load_mapping(output)
    if artifact_display != display:
        raise MappingError("detector mapping declared range disagrees with decisions table")
    expected_rows = expected["DU"] + expected["MF"] + expected["CV"]
    key = lambda row: tuple(row[column] for column in MAPPING_COLS)
    if sorted(map(key, actual_rows)) != sorted(map(key, expected_rows)):
        raise MappingError("detector mapping rows do not exactly close the current detector decisions")
    actual_text = Path(output).read_text(encoding="utf-8")
    expected_text = render_mapping(display, expected)
    if actual_text[actual_text.index(MARKERS[2]):] != expected_text[expected_text.index(MARKERS[2]):]:
        raise MappingError("emitted CV section differs byte-for-byte from frozen cv_scan inputs")
    _reproducibility_check(package_root, audit)


def list_cv_sources(audit):
    sources = parse_cv_sources(audit)
    parsed = []
    for source_id, value in sources.items():
        parsed.append(cv_scan.CVSource(
            value["convention"], value["category"], source_id, value["verdict"],
            tuple(cv_scan.CVWitness(
                witness["witness_id"], witness["anchor"], "", ""
            ) for witness in value["witnesses"]),
            "", "",
        ))
    return cv_scan.render_source_listing(tuple(sorted(parsed, key=lambda item: item.source_id)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_root", type=Path)
    parser.add_argument("--audit-dir", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--list-cv-sources", action="store_true")
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    package_root = args.package_root.expanduser().resolve()
    audit = (args.audit_dir or package_root / "audit").expanduser().resolve()
    output = args.output or audit / "_run/detector_mapping.md"
    try:
        if args.check and args.list_cv_sources:
            raise MappingError("--check and --list-cv-sources are mutually exclusive")
        if args.list_cv_sources:
            sys.stdout.write(list_cv_sources(audit))
            return 0
        if args.check:
            check(package_root, audit, output)
        else:
            emit(package_root, audit, output)
    except (MappingError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{'checked' if args.check else 'wrote'} detector mapping: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
