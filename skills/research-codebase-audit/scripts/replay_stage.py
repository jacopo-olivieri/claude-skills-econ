#!/usr/bin/env python3
"""Replay one audit stage from an explicit, hash-pinned dependency cut.

Scenario files are JSON objects (``format_version`` 1).  An illustrative
scenario from an invented archaeology project is::

    {
      "format_version": 1,
      "stage": "code_b3d",
      "route": "deterministic_stage",
      "dependency_cut": [
        {"kind": "archive", "path": "src/pottery.do", "sha256": "..."},
        {"kind": "authored", "source": "scenario-material/a1/manifest.json",
         "path": "audit/_run/manifest.json", "sha256": "...",
         "classification": "conductor"}
      ],
      "promised_outputs": ["audit/_run/detector_mapping.md"],
      "downstream_exclusions": ["audit/_run/detector_mapping.md"],
      "deterministic_prefix": [{"argv": ["{python}",
        "{skill_root}/scripts/emit_definition_use_bundles.py", "{sandbox}"]}],
      "stage_commands": [{"argv": ["{python}",
        "{skill_root}/scripts/build_detector_mapping.py", "{sandbox}"]}],
      "answer_sheet": "answers/a1.json",
      "runs": 1
    }

Paths in ``archive`` entries are relative to the configured archive root.
Paths in ``authored`` entries name a conductor-only source under the replay
data root and its destination in the sandbox.  Commands are argv arrays, not
shell strings.  The placeholders ``{python}``, ``{skill_root}``, ``{sandbox}``,
``{data_root}``, and ``{scenario_id}`` are supported.  Worker and merge routes
also declare ``prompt_template``, ``prompt_slots``, ``model``, ``effort``,
``role_key``, and two or three ``runs``.

Configuration uses ``--data-root`` / ``RCA_REPLAY_DATA_ROOT`` and
``--archive-root`` / ``RCA_REPLAY_ARCHIVE_ROOT``.  No default contains a
machine-specific path.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import certify_stage
import dispatch_tracking
import build_detector_mapping as detector_mapping
import definition_use as definition_use
from mechanism_schema import MECHANISM_SCHEMA_VERSION


FORMAT_VERSION = 1
ROUTES = {"deterministic_stage", "worker", "merge"}
STAGE_KEYS = frozenset(certify_stage.FULL_STAGES) | frozenset(certify_stage.CODE_ONLY_STAGES)
AUTHORED_SOURCE_ROOT = "scenario-material"
ARCHIVE_FILE_MODES = {0o400, 0o444, 0o500, 0o555}
ARCHIVE_DIR_MODES = {0o500, 0o555}
IDENTITY_FIELDS = (
    "model_requested", "model_reported", "cli_version", "code_commit",
    "code_dirty", "requested_effort", "observed_effort",
    "mechanism_schema_version",
)


class ReplayError(RuntimeError):
    """The replay cannot proceed without compromising its evidence."""


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _safe_relative(raw, label):
    if not isinstance(raw, str) or not raw.strip():
        raise ReplayError(f"{label} must be a non-empty relative path")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ReplayError(f"{label} escapes its root: {raw!r}")
    if str(path) != raw or raw.startswith("/"):
        raise ReplayError(f"{label} is not normalized POSIX-relative: {raw!r}")
    return path


def _walk_tree(root):
    """Return path metadata while surfacing every directory-walk error."""
    root = Path(root)
    found = {}

    def walk(directory):
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise ReplayError(f"archive directory walk failed at {directory}: {exc}") from exc
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise ReplayError(f"archive stat failed for {path}: {exc}") from exc
            mode = stat.S_IMODE(info.st_mode)
            if entry.is_symlink():
                raise ReplayError(f"archive contains unsupported symlink: {relative}")
            if entry.is_dir(follow_symlinks=False):
                found[relative] = {"type": "dir", "mode": mode}
                walk(path)
            elif entry.is_file(follow_symlinks=False):
                try:
                    digest = sha256_file(path)
                except OSError as exc:
                    raise ReplayError(f"archive read failed for {path}: {exc}") from exc
                found[relative] = {
                    "type": "file", "mode": mode, "size": info.st_size,
                    "sha256": digest,
                }
            else:
                raise ReplayError(f"archive contains unsupported entry: {relative}")
    walk(root)
    return found


def verify_archive(archive_root, manifest_path):
    root = Path(archive_root).expanduser()
    if not root.exists():
        raise ReplayError(f"archive root does not exist: {root}")
    if not root.is_dir():
        raise ReplayError(f"archive root is not a directory: {root}")
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayError(f"cannot read archive manifest {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ReplayError("archive manifest must be an object")
    if manifest.get("manifest_version") != 1:
        raise ReplayError("archive manifest_version must be 1")
    if manifest.get("hash_algorithm") != "sha256":
        raise ReplayError("archive manifest hash_algorithm must be sha256")
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ReplayError("archive manifest entries must be a list")
    if manifest.get("entry_count") != len(entries):
        raise ReplayError("archive manifest entry_count disagrees with entries")
    expected = {}
    total_bytes = 0
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ReplayError(f"archive manifest entry {index} is not an object")
        relative = _safe_relative(entry.get("path"), f"manifest entry {index} path").as_posix()
        if relative in expected:
            raise ReplayError(f"archive manifest contains duplicate path: {relative}")
        kind = entry.get("type")
        try:
            mode = int(str(entry.get("mode")), 8)
        except (TypeError, ValueError) as exc:
            raise ReplayError(f"archive manifest has invalid mode for {relative}") from exc
        if kind == "file":
            if mode not in ARCHIVE_FILE_MODES:
                raise ReplayError(
                    f"archive file {relative} has unsupported recorded mode {mode:04o}; "
                    "expected 0400, 0444, 0500, or 0555"
                )
            size, digest = entry.get("size"), entry.get("sha256")
            if not isinstance(size, int) or size < 0:
                raise ReplayError(f"archive file {relative} has invalid size")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ReplayError(f"archive file {relative} has invalid sha256")
            total_bytes += size
            expected[relative] = {
                "type": kind, "mode": mode, "size": size, "sha256": digest,
            }
        elif kind == "dir":
            if mode not in ARCHIVE_DIR_MODES:
                raise ReplayError(
                    f"archive directory {relative} has unsupported recorded mode {mode:04o}; "
                    "expected 0500 or 0555"
                )
            expected[relative] = {"type": kind, "mode": mode}
        else:
            raise ReplayError(f"archive manifest has invalid type for {relative}: {kind!r}")
    if manifest.get("total_file_bytes") != total_bytes:
        raise ReplayError("archive manifest total_file_bytes disagrees with file entries")
    actual = _walk_tree(root)
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise ReplayError(f"archive tree paths differ; missing={missing[:5]}, extra={extra[:5]}")
    for relative, wanted in expected.items():
        if actual[relative] != wanted:
            raise ReplayError(
                f"archive entry differs for {relative}: expected {wanted}, actual {actual[relative]}"
            )
    return {"entry_count": len(expected), "total_file_bytes": total_bytes}


def load_scenario(path):
    path = Path(path).expanduser().resolve()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayError(f"cannot read scenario {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("format_version") != FORMAT_VERSION:
        raise ReplayError("scenario must be a format_version 1 JSON object")
    if value.get("route") not in ROUTES:
        raise ReplayError(f"scenario route must be one of {sorted(ROUTES)}")
    if value.get("stage") not in STAGE_KEYS:
        raise ReplayError(
            f"scenario stage must be a stage key certify_stage.py knows, "
            f"got {value.get('stage')!r}"
        )
    cut = value.get("dependency_cut")
    if not isinstance(cut, list) or not cut:
        raise ReplayError("scenario dependency_cut must be a non-empty list")
    outputs = value.get("promised_outputs")
    exclusions = value.get("downstream_exclusions")
    if not isinstance(outputs, list) or not outputs or not all(isinstance(x, str) and x for x in outputs):
        raise ReplayError("scenario promised_outputs must be a non-empty string list")
    if not isinstance(exclusions, list) or not exclusions or not all(isinstance(x, str) and x for x in exclusions):
        raise ReplayError("scenario downstream_exclusions must be a non-empty string list")
    runs = value.get("runs", 1)
    if value["route"] == "deterministic_stage" and runs != 1:
        raise ReplayError("deterministic_stage scenarios run exactly once")
    if value["route"] in {"worker", "merge"} and runs not in {2, 3}:
        raise ReplayError("worker and merge scenarios require two or three runs")
    return path, value


def _matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _cut_sources(scenario, data_root, archive_root):
    destinations = {}
    answer_path = (Path(data_root) / scenario["answer_sheet"]).resolve()
    for index, entry in enumerate(scenario["dependency_cut"]):
        if not isinstance(entry, dict):
            raise ReplayError(f"dependency_cut entry {index} is not an object")
        destination = _safe_relative(entry.get("path"), f"cut entry {index} path").as_posix()
        if destination in destinations:
            raise ReplayError(f"dependency_cut contains duplicate destination: {destination}")
        if _matches(destination, scenario["downstream_exclusions"]):
            raise ReplayError(
                f"dependency cut refuses downstream artifact {destination}"
            )
        digest = entry.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ReplayError(f"cut entry {destination} has invalid sha256")
        kind = entry.get("kind")
        if kind == "archive":
            relative = _safe_relative(entry.get("path"), f"archive cut entry {index}")
            source = Path(archive_root).joinpath(*relative.parts)
            try:
                resolved = source.resolve(strict=True)
            except OSError as exc:
                raise ReplayError(f"archive cut entry cannot be resolved: {relative}") from exc
            archive_resolved = Path(archive_root).resolve(strict=True)
            if not resolved.is_relative_to(archive_resolved) or not resolved.is_file():
                raise ReplayError(f"archive cut entry escapes archive root: {relative}")
        elif kind == "authored":
            if entry.get("classification") != "conductor":
                raise ReplayError(
                    f"authored cut entry {destination} must be classified conductor"
                )
            relative = _safe_relative(entry.get("source"), f"authored cut entry {index} source")
            if relative.parts[0] != AUTHORED_SOURCE_ROOT:
                raise ReplayError(
                    f"authored cut entry must live under {AUTHORED_SOURCE_ROOT}/ "
                    f"(the sole admissible authored-source root): {relative}"
                )
            source = Path(data_root).joinpath(*relative.parts)
            try:
                resolved = source.resolve(strict=True)
            except OSError as exc:
                raise ReplayError(f"authored cut entry cannot be resolved: {relative}") from exc
            data_resolved = Path(data_root).resolve(strict=True)
            if not resolved.is_relative_to(
                    (data_resolved / AUTHORED_SOURCE_ROOT)) or not resolved.is_file():
                raise ReplayError(f"authored cut entry escapes {AUTHORED_SOURCE_ROOT}/: {relative}")
            if resolved == answer_path:
                raise ReplayError(f"authored cut entry is answer material: {relative}")
        else:
            raise ReplayError(f"cut entry {destination} has invalid kind {kind!r}")
        if sha256_file(resolved) != digest:
            raise ReplayError(f"dependency cut digest mismatch for {destination}")
        destinations[destination] = resolved
    return destinations


def _sandbox_files(sandbox):
    sandbox = Path(sandbox)
    found = set()
    for directory, dirs, files in os.walk(sandbox, followlinks=False):
        for name in dirs:
            path = Path(directory) / name
            if path.is_symlink():
                raise ReplayError(f"sandbox contains symlink: {path.relative_to(sandbox)}")
        for name in files:
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                raise ReplayError(f"sandbox contains unsupported entry: {path.relative_to(sandbox)}")
            found.add(path.relative_to(sandbox).as_posix())
    return found


def verify_declared_cut(sandbox, destinations):
    actual = _sandbox_files(sandbox)
    expected = set(destinations)
    if actual != expected:
        raise ReplayError(
            "sandbox does not exactly match declared dependency cut; "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    for relative, source in destinations.items():
        copied = Path(sandbox) / relative
        if sha256_file(copied) != sha256_file(source):
            raise ReplayError(f"sandbox cut copy digest differs for {relative}")


def verify_no_downstream(sandbox, patterns):
    matches = sorted(path for path in _sandbox_files(sandbox) if _matches(path, patterns))
    if matches:
        raise ReplayError(f"sandbox contains downstream artifact(s): {matches}")


def prepare_sandbox(scenario, data_root, archive_root, sandbox):
    destinations = _cut_sources(scenario, data_root, archive_root)
    sandbox = Path(sandbox)
    if sandbox.exists() and any(sandbox.iterdir()):
        raise ReplayError(f"sandbox must be absent or empty: {sandbox}")
    sandbox.mkdir(parents=True, exist_ok=True)
    for relative, source in destinations.items():
        target = sandbox / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target, follow_symlinks=False)
        target.chmod(stat.S_IMODE(target.stat().st_mode) | stat.S_IWUSR)
    verify_declared_cut(sandbox, destinations)
    verify_no_downstream(sandbox, scenario["downstream_exclusions"])
    return destinations


def _format_command(command, values):
    if not isinstance(command, dict) or not isinstance(command.get("argv"), list):
        raise ReplayError("each replay command must be an object with an argv list")
    if not command["argv"] or not all(isinstance(value, str) for value in command["argv"]):
        raise ReplayError("replay command argv must contain strings")
    try:
        argv = [value.format_map(values) for value in command["argv"]]
        cwd = command.get("cwd", "{sandbox}").format_map(values)
    except KeyError as exc:
        raise ReplayError(f"unknown command placeholder: {exc}") from exc
    return argv, cwd


def _run_commands(commands, values, label):
    records = []
    for index, command in enumerate(commands or [], start=1):
        argv, cwd = _format_command(command, values)
        result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
        records.append({"argv": argv, "cwd": cwd, "returncode": result.returncode})
        if result.returncode:
            detail = (result.stdout + result.stderr).strip()
            raise ReplayError(f"{label} command {index} failed ({result.returncode}): {detail}")
    return records


def verify_deterministic_expectations(scenario, sandbox):
    """Mechanically compare detector emissions and mapping identities/anchors."""
    declaration = scenario.get("deterministic_expectations")
    if declaration is None:
        return "not-declared"
    if not isinstance(declaration, dict):
        raise ReplayError("deterministic_expectations must be an object")
    expected = declaration.get("detector_rows")
    if not isinstance(expected, list) or not expected:
        raise ReplayError("deterministic_expectations requires detector_rows")
    required = {"channel", "source_id", "witness_id", "site_anchor"}
    normalized = []
    for index, row in enumerate(expected):
        if not isinstance(row, dict) or set(row) != required:
            raise ReplayError(
                f"deterministic expectation {index} must contain exactly {sorted(required)}"
            )
        normalized.append((row["channel"], row["source_id"], row["witness_id"],
                           row["site_anchor"]))
    if len(normalized) != len(set(normalized)):
        raise ReplayError("deterministic expectations contain a duplicate detector row")
    mapping_relative = _safe_relative(
        declaration.get("mapping_path"), "deterministic mapping_path")
    bundle_relative = _safe_relative(
        declaration.get("bundle_path"), "deterministic bundle_path")
    try:
        _declared, _display, mapping_rows = detector_mapping.load_mapping(
            Path(sandbox).joinpath(*mapping_relative.parts))
        artifact = definition_use.parse_artifact(
            Path(sandbox).joinpath(*bundle_relative.parts).read_text(encoding="utf-8"))
    except (OSError, detector_mapping.MappingError,
            definition_use.DefinitionUseFormatError) as exc:
        raise ReplayError(f"deterministic expectation artifact is invalid: {exc}") from exc
    actual_mapping = sorted((
        row["Channel"], row["Source ID"], row["Witness ID"], row["Site Anchor"]
    ) for row in mapping_rows if row["Channel"] == "DU")
    expected_rows = sorted(normalized)
    if actual_mapping != expected_rows:
        raise ReplayError(
            f"deterministic detector mapping differs: expected={expected_rows}, "
            f"actual={actual_mapping}"
        )
    emitted = sorted((
        "DU", row["Bundle ID"], row["Witness ID"], row["Consumer Site"]
    ) for row in artifact.standard_rows)
    if emitted != expected_rows:
        raise ReplayError(
            f"deterministic detector emission differs: expected={expected_rows}, actual={emitted}"
        )
    return {"status": "score", "detector_rows": len(expected_rows)}


_SLOT_RE = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")


def render_worker_prompt(scenario, skill_root):
    relative = _safe_relative(scenario.get("prompt_template"), "prompt_template")
    template_path = Path(skill_root).joinpath(*relative.parts).resolve()
    skill_resolved = Path(skill_root).resolve()
    if not template_path.is_relative_to(skill_resolved) or not template_path.is_file():
        raise ReplayError("prompt_template must resolve to a production skill file")
    text = template_path.read_text(encoding="utf-8")
    match = re.search(r"```md\n(.*?)\n```", text, re.DOTALL)
    if not match:
        raise ReplayError(f"prompt template has no md skeleton fence: {template_path}")
    skeleton = match.group(1)
    required = set(_SLOT_RE.findall(skeleton))
    slots = scenario.get("prompt_slots")
    if not isinstance(slots, dict) or set(slots) != required:
        raise ReplayError(
            f"prompt_slots must exactly fill the production skeleton; "
            f"missing={sorted(required - set(slots or {}))}, extra={sorted(set(slots or {}) - required)}"
        )
    rendered = skeleton
    for name in sorted(required, key=len, reverse=True):
        value = slots[name]
        if not isinstance(value, str):
            raise ReplayError(f"prompt slot {name} must be a string")
        rendered = rendered.replace("{" + name + "}", value)
    if _SLOT_RE.search(rendered):
        raise ReplayError("rendered worker prompt retains an unfilled slot")
    marker = f"RCA-DISPATCH role={scenario['role_key']} stage={scenario['stage']}"
    return marker + "\n\n" + rendered + "\n"


def _persist_prompt(run_dir, prompt):
    """Persist the rendered worker prompt beside the record; return its sha256."""
    path = Path(run_dir) / "worker-prompt.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(prompt)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _git_identity(repo_root):
    commit = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )
    if commit.returncode:
        raise ReplayError("cannot record repository commit")
    dirty = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain"],
        capture_output=True, text=True,
    )
    if dirty.returncode:
        raise ReplayError("cannot record repository dirty-tree state")
    return commit.stdout.strip(), bool(dirty.stdout)


def _claude_version():
    result = subprocess.run(["claude", "--version"], capture_output=True, text=True)
    if result.returncode:
        raise ReplayError(f"cannot record Claude CLI version: {result.stderr.strip()}")
    return result.stdout.strip()


def _reported_model(payload):
    if not isinstance(payload, dict):
        return "absent"
    for key in ("model", "model_id"):
        if isinstance(payload.get(key), str) and payload[key]:
            return payload[key]
    usage = payload.get("modelUsage") or payload.get("model_usage")
    if isinstance(usage, dict) and len(usage) == 1:
        return next(iter(usage))
    return "absent"


def _observed_effort(sandbox):
    audit = Path(sandbox) / "audit"
    ledger_path = audit / "_run" / "dispatch_ledger.md"
    events_dir = audit / "_run" / "dispatch_events"
    rows = dispatch_tracking.read_ledger_rows(ledger_path)
    events = []
    if events_dir.is_dir():
        for path in sorted(events_dir.glob("*.json")):
            try:
                events.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError) as exc:
                events.append({"malformed": str(exc), "path": path.name})
    if not rows and not events:
        return {"status": "absent", "dispatch_ledger": [], "hook_events": []}
    return {"status": "observed", "dispatch_ledger": rows, "hook_events": events}


def _promised_matches(sandbox, patterns):
    files = _sandbox_files(sandbox)
    return sorted(path for path in files if _matches(path, patterns))


def execute_sandbox(scenario_path, scenario, data_root, archive_root, sandbox,
                    run_dir, run_index, skill_root):
    destinations = _cut_sources(scenario, data_root, archive_root)
    verify_declared_cut(sandbox, destinations)
    values = {
        "python": sys.executable, "skill_root": str(Path(skill_root).resolve()),
        "sandbox": str(Path(sandbox).resolve()), "data_root": str(Path(data_root).resolve()),
        "scenario_id": Path(scenario_path).stem,
    }
    prefix_records = _run_commands(
        scenario.get("deterministic_prefix", []), values, "deterministic prefix")
    deterministic_check = verify_deterministic_expectations(scenario, sandbox)
    verify_no_downstream(sandbox, scenario["downstream_exclusions"])
    cli_version = "not-applicable"
    model_requested = model_reported = requested_effort = "not-applicable"
    prompt_sha256 = "not-applicable"
    route_records = []
    if scenario["route"] == "deterministic_stage":
        route_records = _run_commands(scenario.get("stage_commands", []), values, "stage")
        if not route_records:
            raise ReplayError("deterministic_stage requires at least one stage command")
        certifier = scenario.get("certifier_command")
        if not certifier:
            raise ReplayError("deterministic_stage requires a production certifier_command")
        route_records += _run_commands([certifier], values, "certifier")
        observed_effort = "not-applicable"
    else:
        model_requested = scenario.get("model")
        requested_effort = scenario.get("effort")
        role = scenario.get("role_key")
        if not isinstance(model_requested, str) or not model_requested:
            raise ReplayError("worker route requires a model pin")
        if requested_effort not in dispatch_tracking.EFFORT_TIERS:
            raise ReplayError("worker route requires a valid effort pin")
        if role not in dispatch_tracking.ROLE_KEYS:
            raise ReplayError("worker route requires a production role_key")
        prompt = render_worker_prompt(scenario, skill_root)
        prompt_sha256 = _persist_prompt(run_dir, prompt)
        cli_version = _claude_version()
        tracking = [
            sys.executable, str(Path(skill_root) / "scripts/dispatch_tracking.py"), "record",
            "--audit-dir", str(Path(sandbox) / "audit"), "--role", role,
            "--carrier", f"rca-carrier-{requested_effort}", "--stage", scenario["stage"],
            "--owner", scenario.get("owner", "replay-output"), "--sequence", "1",
        ]
        tracked = subprocess.run(tracking, cwd=sandbox, capture_output=True, text=True)
        if tracked.returncode:
            raise ReplayError(f"production dispatch record failed: {(tracked.stdout + tracked.stderr).strip()}")
        command = [
            "claude", "--print", "--output-format", "json", "--no-session-persistence",
            "--permission-mode", "acceptEdits", "--model", model_requested,
            "--effort", requested_effort, "--agent", f"rca-carrier-{requested_effort}",
        ]
        result = subprocess.run(
            command, input=prompt, cwd=sandbox, capture_output=True, text=True,
        )
        response_path = Path(run_dir) / "worker-response.json"
        if result.stdout.strip():
            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError:
                payload = {"unparsed_stdout": result.stdout}
        else:
            payload = {}
        atomic_json(response_path, payload)
        model_reported = _reported_model(payload)
        route_records = [{"argv": command, "cwd": str(sandbox), "returncode": result.returncode}]
        if result.returncode:
            raise ReplayError(f"worker launch failed ({result.returncode}): {result.stderr.strip()}")
        observed_effort = _observed_effort(sandbox)
    promised = _promised_matches(sandbox, scenario["promised_outputs"])
    repo_root = Path(skill_root).parents[1]
    commit, dirty = _git_identity(repo_root)
    identity = {
        "model_requested": model_requested, "model_reported": model_reported,
        "cli_version": cli_version, "code_commit": commit, "code_dirty": dirty,
        "requested_effort": requested_effort, "observed_effort": observed_effort,
        "mechanism_schema_version": MECHANISM_SCHEMA_VERSION,
    }
    record = {
        "format_version": FORMAT_VERSION, "scenario_id": Path(scenario_path).stem,
        "stage": scenario["stage"], "route": scenario["route"],
        "run_index": run_index, "timestamp": datetime.now(timezone.utc).isoformat(),
        "identity": identity, "prompt_sha256": prompt_sha256,
        "deterministic_prefix": prefix_records,
        "deterministic_check": deterministic_check,
        "route_commands": route_records, "promised_outputs_found": promised,
    }
    atomic_json(Path(run_dir) / "replay-record.json", record)
    return record


def _configured_root(flag, env_name, label):
    raw = flag or os.environ.get(env_name)
    if not raw:
        raise ReplayError(f"{label} is required via CLI or {env_name}")
    path = Path(raw).expanduser().resolve()
    if not path.is_dir():
        raise ReplayError(f"{label} is not a directory: {path}")
    return path


def _manifest_path(scenario, data_root):
    relative = _safe_relative(scenario.get("archive_manifest"), "archive_manifest")
    path = Path(data_root).joinpath(*relative.parts).resolve()
    if not path.is_relative_to(Path(data_root).resolve()) or not path.is_file():
        raise ReplayError("archive_manifest must resolve under the replay data root")
    return path


def verify_answer_sheet_pin(scenario, data_root):
    relative = _safe_relative(scenario.get("answer_sheet"), "answer_sheet")
    path = Path(data_root).joinpath(*relative.parts).resolve()
    if not path.is_relative_to(Path(data_root).resolve()) or not path.is_file():
        raise ReplayError("answer_sheet must resolve under the replay data root")
    expected = scenario.get("answer_sheet_sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ReplayError("scenario answer_sheet_sha256 is missing or invalid")
    actual = sha256_file(path)
    if actual != expected:
        raise ReplayError(
            f"answer sheet digest mismatch: expected {expected}, actual {actual}"
        )
    return path


def _registry_label(data_root, scenario_id):
    path = Path(data_root) / "registry.json"
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayError(f"cannot read scenario registry {path}: {exc}") from exc
    label = registry.get(scenario_id) if isinstance(registry, dict) else None
    if not isinstance(label, str) or not re.fullmatch(r"S-7\d{2}", label):
        raise ReplayError(f"scenario registry has no valid label for {scenario_id}")
    return label


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--archive-root", type=Path)
    parser.add_argument("--skill-root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "prepare", "execute"):
        command = sub.add_parser(name)
        command.add_argument("scenario", type=Path)
        if name in {"prepare", "execute"}:
            command.add_argument("--sandbox", type=Path, required=True)
        if name == "execute":
            command.add_argument("--run-dir", type=Path, required=True)
            command.add_argument("--run-index", type=int, default=1)
    verify = sub.add_parser("verify-archive")
    verify.add_argument("scenario", type=Path)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        data_root = _configured_root(args.data_root, "RCA_REPLAY_DATA_ROOT", "replay data root")
        archive_root = _configured_root(args.archive_root, "RCA_REPLAY_ARCHIVE_ROOT", "archive root")
        scenario_path, scenario = load_scenario(args.scenario)
        manifest_path = _manifest_path(scenario, data_root)
        verify_answer_sheet_pin(scenario, data_root)
        verified = verify_archive(archive_root, manifest_path)
        if args.command == "verify-archive":
            print(f"REPLAY OK: archive verified ({verified['entry_count']} entries)")
            return 0
        if args.command == "prepare":
            prepare_sandbox(scenario, data_root, archive_root, args.sandbox)
            print(f"REPLAY OK: sandbox prepared at {args.sandbox}")
            return 0
        if args.command == "execute":
            args.run_dir.mkdir(parents=True, exist_ok=True)
            execute_sandbox(
                scenario_path, scenario, data_root, archive_root, args.sandbox,
                args.run_dir, args.run_index, args.skill_root,
            )
            verify_archive(archive_root, manifest_path)
            print(f"REPLAY OK: run {args.run_index} completed at {args.run_dir}")
            return 0
        label = _registry_label(data_root, scenario_path.stem)
        scenario_results = data_root / "results" / label
        completed = []
        for run_index in range(1, scenario.get("runs", 1) + 1):
            run_dir = scenario_results / f"run-{run_index:03d}"
            sandbox = run_dir / "sandbox"
            if run_dir.exists():
                raise ReplayError(f"run directory already exists: {run_dir}")
            run_dir.mkdir(parents=True)
            prepare_sandbox(scenario, data_root, archive_root, sandbox)
            completed.append(execute_sandbox(
                scenario_path, scenario, data_root, archive_root, sandbox,
                run_dir, run_index, args.skill_root,
            ))
            verify_archive(archive_root, manifest_path)
        print(f"REPLAY OK: completed {len(completed)} run(s) in {scenario_results}")
        return 0
    except ReplayError as exc:
        print(f"REPLAY REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
