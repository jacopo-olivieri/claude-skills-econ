#!/usr/bin/env python3
"""Certify research-codebase-audit stage state from on-disk evidence.

This script is the sole writer of the manifest's ``stages`` and
``run_identity`` blocks.  Run it from the audited package root, or pass that
root explicitly with ``--package-root``.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from mechanism_schema import MECHANISM_SCHEMA_VERSION


SCRIPT_DIR = Path(__file__).resolve().parent
OBLIGATIONS_PATH = SCRIPT_DIR / "stage_obligations.json"

FULL_STAGES = (
    "b0",
    "claims_b1", "claims_b2", "claims_b3", "claims_b3c", "claims_b3b",
    "claims_b4", "claims_b5", "claims_b6",
    "code_b1", "code_b2", "code_b3", "code_b3b", "code_b4", "code_b5",
    "code_b6",
    "b7", "b8", "b9",
)
CODE_ONLY_STAGES = (
    "b0",
    "code_b1", "code_b2", "code_b3", "code_b3b", "code_b4", "code_b5",
    "code_b6",
    "b8", "b9",
)

LEGAL_START_STATES = {"pending", "blocked"}
VALID_STAGE_STATES = {"pending", "running", "done", "blocked"}

VALIDATORS = {
    "lint:b0": "b0",
    "lint:b1-claims": "b1-claims",
    "lint:b2-claims": "b2-claims",
    "lint:b4-claims": "b4-claims",
    "lint:b5-claims": "b5-claims",
    "lint:b1-code": "b1-code",
    "lint:b2-code": "b2-code",
    "lint:b4-code": "b4-code",
    "lint:b5-code": "b5-code",
    "lint:b8": "b8",
    "lint:b9": "b9",
}
SHARD_VALIDATORS = {
    "lint:b2-claims", "lint:b5-claims", "lint:b2-code", "lint:b5-code",
}


class CertificationError(RuntimeError):
    """A command cannot safely perform its requested state transition."""


def canonical_package_root(path):
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise CertificationError(f"package root is not a directory: {root}")
    return root


def audit_paths(package_root):
    audit = package_root / "audit"
    run_dir = audit / "_run"
    return audit, run_dir, run_dir / "manifest.json", run_dir / "RUNNING"


def read_manifest(package_root):
    _, _, manifest_path, _ = audit_paths(package_root)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CertificationError(f"manifest does not exist: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise CertificationError(f"manifest is not valid JSON: {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise CertificationError(f"manifest must contain a JSON object: {manifest_path}")
    return manifest


def write_manifest_atomic(package_root, manifest):
    """Serialize the complete manifest and atomically replace the old file."""
    _, run_dir, manifest_path, _ = audit_paths(package_root)
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=".manifest.", suffix=".tmp", dir=run_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, manifest_path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _path_is_excluded(relative, exclusions):
    return any(relative == excluded or excluded in relative.parents
               for excluded in exclusions)


def _existing_exclusions(package_root, manifest):
    exclusions = {Path("audit")}
    for field in ("scope_exclusions", "off_limits"):
        values = manifest.get(field, [])
        if not isinstance(values, list):
            continue
        for raw in values:
            if not isinstance(raw, str) or not raw.strip():
                continue
            relative = Path(raw)
            if relative.is_absolute() or ".." in relative.parts:
                continue
            candidate = package_root / relative
            if candidate.exists():
                exclusions.add(relative)
    return exclusions


def _sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_tree_fingerprint(package_root, manifest):
    """Hash regular files and link target strings in the audited tree."""
    package_root = canonical_package_root(package_root)
    exclusions = _existing_exclusions(package_root, manifest)
    entries = []

    def walk(directory):
        for entry in sorted(os.scandir(directory), key=lambda item: item.name):
            path = Path(entry.path)
            relative = path.relative_to(package_root)
            if _path_is_excluded(relative, exclusions):
                continue
            if entry.is_symlink():
                target_hash = hashlib.sha256(os.readlink(path).encode("utf-8")).hexdigest()
                entries.append((relative.as_posix(), target_hash))
            elif entry.is_dir(follow_symlinks=False):
                walk(path)
            elif entry.is_file(follow_symlinks=False):
                entries.append((relative.as_posix(), _sha256_file(path)))

    walk(package_root)
    serialized = "\n".join(f"{relative},{digest}" for relative, digest in sorted(entries))
    return {
        "aggregate_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "file_count": len(entries),
    }


def git_commit(package_root):
    result = subprocess.run(
        ["git", "-C", str(package_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def make_run_identity(package_root, manifest):
    return {
        "git_commit": git_commit(package_root),
        "canonical_package_root": str(package_root),
        "tree_fingerprint": compute_tree_fingerprint(package_root, manifest),
        "mechanism_schema_version": MECHANISM_SCHEMA_VERSION,
    }


def _identity_failures(package_root, manifest, check_fingerprint):
    identity = manifest.get("run_identity")
    if not isinstance(identity, dict):
        return ["run identity is missing"]
    failures = []
    recorded_root = identity.get("canonical_package_root")
    if recorded_root != str(package_root):
        failures.append(
            "canonical package root mismatch: "
            f"recorded {recorded_root!r}, current {str(package_root)!r}"
        )
    recorded_version = identity.get("mechanism_schema_version")
    if recorded_version != MECHANISM_SCHEMA_VERSION:
        failures.append(
            "mechanism schema changed under the run "
            f"(recorded {recorded_version!r}, current {MECHANISM_SCHEMA_VERSION!r}); "
            "restart is required"
        )
    if check_fingerprint:
        recorded_fingerprint = identity.get("tree_fingerprint")
        current_fingerprint = compute_tree_fingerprint(package_root, manifest)
        if recorded_fingerprint != current_fingerprint:
            failures.append(
                "audited tree changed across the pause "
                f"(recorded {recorded_fingerprint!r}, current {current_fingerprint!r}); "
                "restarting the audit is the only path forward"
            )
    return failures


def require_canonical_identity(package_root, manifest):
    identity = manifest.get("run_identity")
    recorded = identity.get("canonical_package_root") if isinstance(identity, dict) else None
    if recorded != str(package_root):
        raise CertificationError(
            "canonical package root mismatch: "
            f"recorded {recorded!r}, current {str(package_root)!r}"
        )


def _marker_text():
    started = datetime.now(timezone.utc).isoformat()
    return f"started_at={started}\npid={os.getpid()}\n"


def replace_running_marker(package_root, clear_stale=False):
    _, run_dir, _, marker = audit_paths(package_root)
    run_dir.mkdir(parents=True, exist_ok=True)
    if marker.exists() and not clear_stale:
        details = marker.read_text(encoding="utf-8", errors="replace").strip()
        raise CertificationError(
            "another audit run appears to be live because audit/_run/RUNNING exists"
            + (f" ({details})" if details else "")
            + "; if the previous run is certainly dead, retry with --clear-stale-marker"
        )
    if marker.exists():
        marker.unlink()
    marker.write_text(_marker_text(), encoding="utf-8")


def remove_running_marker(package_root):
    _, _, _, marker = audit_paths(package_root)
    try:
        marker.unlink()
    except FileNotFoundError as exc:
        raise CertificationError("audit/_run/RUNNING does not exist") from exc


def stages_for_mode(mode):
    if mode == "replication":
        return FULL_STAGES
    if mode == "code_errors_only":
        return CODE_ONLY_STAGES
    raise CertificationError(
        f"manifest mode must be 'replication' or 'code_errors_only', got {mode!r}"
    )


def init_run(package_root, clear_stale_marker=False):
    manifest = read_manifest(package_root)
    stages = stages_for_mode(manifest.get("mode"))
    replace_running_marker(package_root, clear_stale_marker)
    manifest["run_identity"] = make_run_identity(package_root, manifest)
    manifest["stages"] = {
        stage: {"status": "pending", "retries": 0, "shards": {}}
        for stage in stages
    }
    write_manifest_atomic(package_root, manifest)


def stage_entry(manifest, stage):
    stages = manifest.get("stages")
    if not isinstance(stages, dict) or stage not in stages:
        raise CertificationError(f"stage {stage!r} is not present in this run's manifest")
    entry = stages[stage]
    if not isinstance(entry, dict):
        raise CertificationError(f"manifest entry for stage {stage!r} is not an object")
    status = entry.get("status")
    if status not in VALID_STAGE_STATES:
        raise CertificationError(f"stage {stage!r} has invalid current state {status!r}")
    return entry


def start_stage(package_root, stage):
    manifest = read_manifest(package_root)
    require_canonical_identity(package_root, manifest)
    entry = stage_entry(manifest, stage)
    status = entry["status"]
    if status not in LEGAL_START_STATES:
        raise CertificationError(
            f"stage {stage!r} is {status!r}; start permits only pending -> running "
            "or blocked -> running"
        )
    if status == "blocked":
        entry["retries"] = int(entry.get("retries", 0)) + 1
    entry["status"] = "running"
    entry.pop("reason", None)
    entry.pop("note", None)
    write_manifest_atomic(package_root, manifest)


def load_obligations(path=OBLIGATIONS_PATH):
    try:
        table = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CertificationError(f"cannot load obligations table {path}: {exc}") from exc
    if not isinstance(table, dict):
        raise CertificationError("obligations table must be a JSON object")
    return table


def _artifact_failure(audit, pattern):
    matches = [path for path in audit.glob(pattern)
               if path.is_file() and path.stat().st_size > 0]
    if matches:
        return None
    return f"artifact:{pattern} matched no existing non-empty file under {audit}"


def _resolve_shard_path(package_root, audit, raw):
    shard = Path(raw)
    if shard.is_absolute():
        return shard
    if shard.parts and shard.parts[0] == "audit":
        return package_root / shard
    return audit / shard


def _validator_commands(identifier, package_root, audit, stage_entry_value):
    lint_stage = VALIDATORS.get(identifier)
    if lint_stage is None:
        raise CertificationError(f"unknown validator identifier {identifier!r}")
    base = [
        sys.executable,
        str(SCRIPT_DIR / "lint_registers.py"),
        "--stage", lint_stage,
        "--audit-dir", str(audit),
    ]
    if identifier not in SHARD_VALIDATORS:
        return [base]
    shards = stage_entry_value.get("shards")
    if not isinstance(shards, dict) or not shards:
        raise CertificationError(f"validator {identifier!r} requires recorded shard paths")
    nonterminal = []
    done_shards = []
    for raw, value in sorted(shards.items()):
        status = value.get("status") if isinstance(value, dict) else None
        if status not in {"done", "blocked"}:
            nonterminal.append(f"{raw} ({status!r})")
        elif status == "done":
            done_shards.append(raw)
    if nonterminal:
        raise CertificationError(
            f"validator {identifier!r} requires every shard to be done or blocked; "
            "nonterminal shard(s): " + ", ".join(nonterminal)
        )
    if not done_shards:
        raise CertificationError(
            f"validator {identifier!r} requires at least one done shard"
        )
    commands = []
    for raw in done_shards:
        command = list(base)
        command.extend(["--shard", str(_resolve_shard_path(package_root, audit, raw))])
        commands.append(command)
    return commands


def _run_validator(identifier, package_root, audit, stage_entry_value):
    failures = []
    try:
        commands = _validator_commands(
            identifier, package_root, audit, stage_entry_value
        )
    except CertificationError as exc:
        return [str(exc)]
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, cwd=package_root)
        if result.returncode != 0:
            detail = (result.stdout + result.stderr).strip()
            failures.append(
                f"validate:{identifier} exited {result.returncode}"
                + (f": {detail}" if detail else "")
            )
    return failures


def resolve_stage_obligations(package_root, manifest, stage, table=None):
    table = load_obligations() if table is None else table
    if stage not in table:
        return [f"obligations table has no entry for stage {stage!r}"]
    obligations = table[stage]
    if not isinstance(obligations, list) or not obligations:
        return [f"obligations table entry for stage {stage!r} is empty"]
    audit, _, _, _ = audit_paths(package_root)
    entry = stage_entry(manifest, stage)
    failures = []
    for obligation in obligations:
        if not isinstance(obligation, dict):
            failures.append(f"stage {stage!r} has a malformed obligation {obligation!r}")
            continue
        obligation_type = obligation.get("type")
        if obligation_type == "artifact":
            pattern = obligation.get("pattern")
            if not isinstance(pattern, str) or not pattern:
                failures.append(f"stage {stage!r} has an artifact obligation without a pattern")
                continue
            failure = _artifact_failure(audit, pattern)
            if failure:
                failures.append(failure)
        elif obligation_type == "validate":
            identifier = obligation.get("validator")
            if not isinstance(identifier, str) or not identifier:
                failures.append(f"stage {stage!r} has a validate obligation without an identifier")
                continue
            failures.extend(
                _run_validator(identifier, package_root, audit, entry)
            )
        else:
            failures.append(
                f"stage {stage!r} has unknown obligation type {obligation_type!r}"
            )
    return failures


def finish_stage(package_root, stage, outcome, reason=None):
    manifest = read_manifest(package_root)
    require_canonical_identity(package_root, manifest)
    entry = stage_entry(manifest, stage)
    if entry["status"] != "running":
        raise CertificationError(
            f"stage {stage!r} is {entry['status']!r}; finish permits only "
            "running -> done or running -> blocked"
        )
    if outcome == "blocked":
        if reason is None or not reason.strip():
            raise CertificationError("a blocked outcome requires a non-empty --reason")
        entry["status"] = "blocked"
        entry["reason"] = " ".join(reason.split())
        write_manifest_atomic(package_root, manifest)
        return
    failures = resolve_stage_obligations(package_root, manifest, stage)
    if failures:
        raise CertificationError(
            f"stage {stage!r} failed obligation(s): " + " | ".join(failures)
        )
    entry["status"] = "done"
    entry.pop("reason", None)
    entry.pop("note", None)
    write_manifest_atomic(package_root, manifest)


def set_shard(package_root, stage, shard, status, reason=None):
    manifest = read_manifest(package_root)
    require_canonical_identity(package_root, manifest)
    entry = stage_entry(manifest, stage)
    if entry["status"] != "running":
        raise CertificationError(
            f"stage {stage!r} is {entry['status']!r}; shards may change only while it is running"
        )
    shards = entry.setdefault("shards", {})
    if not isinstance(shards, dict):
        raise CertificationError(f"stage {stage!r} has a non-object shards entry")
    shard_path = _resolve_shard_path(package_root, package_root / "audit", shard)
    if status == "done" and (not shard_path.is_file() or shard_path.stat().st_size == 0):
        raise CertificationError(
            f"shard {shard!r} cannot be done: file is missing or empty ({shard_path})"
        )
    if status == "blocked" and (reason is None or not reason.strip()):
        raise CertificationError("a blocked shard requires a non-empty --reason")
    previous = shards.get(shard, {})
    retries = int(previous.get("retries", 0))
    if previous.get("status") == "blocked" and status == "done":
        retries += 1
    value = {"status": status, "retries": retries}
    if status == "blocked":
        value["reason"] = " ".join(reason.split())
    shards[shard] = value
    write_manifest_atomic(package_root, manifest)


def verify_done_stages(package_root, manifest):
    failures = []
    stages = manifest.get("stages")
    if not isinstance(stages, dict):
        return ["manifest stages block is missing or not an object"]
    for stage, entry in stages.items():
        if isinstance(entry, dict) and entry.get("status") == "done":
            for failure in resolve_stage_obligations(package_root, manifest, stage):
                failures.append(f"stage {stage!r}: {failure}")
    return failures


def _done_stage_summary(manifest, evidence_failures):
    stages = manifest.get("stages", {})
    done = [stage for stage, entry in stages.items()
            if isinstance(entry, dict) and entry.get("status") == "done"]
    failed = {
        stage for stage in done
        if any(failure.startswith(f"stage {stage!r}:")
               for failure in evidence_failures)
    }
    passed = [stage for stage in done if stage not in failed]
    return "recorded passes still hold: " + (", ".join(passed) if passed else "none")


def verify_run(package_root):
    manifest = read_manifest(package_root)
    failures = _identity_failures(package_root, manifest, check_fingerprint=True)
    evidence_failures = verify_done_stages(package_root, manifest)
    summary = _done_stage_summary(manifest, evidence_failures)
    failures.extend(evidence_failures)
    if failures:
        raise CertificationError(
            "verification failed: " + " | ".join(failures) + " | " + summary
        )
    return summary


def resume_check(package_root, clear_stale_marker=False):
    manifest = read_manifest(package_root)
    replace_running_marker(package_root, clear_stale_marker)
    failures = _identity_failures(package_root, manifest, check_fingerprint=True)
    evidence_failures = verify_done_stages(package_root, manifest)
    summary = _done_stage_summary(manifest, evidence_failures)
    failures.extend(evidence_failures)
    if failures:
        raise CertificationError(
            "resume check failed: " + " | ".join(failures) + " | " + summary
        )
    return summary


def demote_stage(package_root, stage, reason=None):
    manifest = read_manifest(package_root)
    require_canonical_identity(package_root, manifest)
    entry = stage_entry(manifest, stage)
    if entry["status"] != "done":
        raise CertificationError(
            f"stage {stage!r} is {entry['status']!r}; demote permits only done -> pending"
        )
    entry["status"] = "pending"
    if reason is None or not reason.strip():
        entry["note"] = "demoted after failed verification"
    else:
        entry["note"] = " ".join(reason.split())
    write_manifest_atomic(package_root, manifest)


def close_run(package_root):
    manifest = read_manifest(package_root)
    require_canonical_identity(package_root, manifest)
    remove_running_marker(package_root)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def command(name):
        subparser = subparsers.add_parser(name)
        subparser.add_argument(
            "--package-root", type=Path, default=Path.cwd(),
            help="audited package root (default: current working directory)",
        )
        return subparser

    init = command("init")
    init.add_argument("--clear-stale-marker", action="store_true")

    start = command("start")
    start.add_argument("--stage", required=True)

    finish = command("finish")
    finish.add_argument("--stage", required=True)
    finish.add_argument("--outcome", required=True, choices=("done", "blocked"))
    finish.add_argument("--reason")

    shard = command("set-shard")
    shard.add_argument("--stage", required=True)
    shard.add_argument("--shard", required=True)
    shard.add_argument("--status", required=True, choices=("done", "blocked"))
    shard.add_argument("--reason")

    command("verify-run")

    demote = command("demote")
    demote.add_argument("--stage", required=True)
    demote.add_argument("--reason")

    resume = command("resume-check")
    resume.add_argument("--clear-stale-marker", action="store_true")

    command("close-run")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    detail = None
    try:
        package_root = canonical_package_root(args.package_root)
        if args.command == "init":
            init_run(package_root, args.clear_stale_marker)
        elif args.command == "start":
            start_stage(package_root, args.stage)
        elif args.command == "finish":
            finish_stage(package_root, args.stage, args.outcome, args.reason)
        elif args.command == "set-shard":
            set_shard(package_root, args.stage, args.shard, args.status, args.reason)
        elif args.command == "verify-run":
            detail = verify_run(package_root)
        elif args.command == "demote":
            demote_stage(package_root, args.stage, args.reason)
        elif args.command == "resume-check":
            detail = resume_check(package_root, args.clear_stale_marker)
        elif args.command == "close-run":
            close_run(package_root)
    except CertificationError as exc:
        print(f"CERTIFICATION REFUSED: {exc}", file=sys.stderr)
        return 1
    print(f"CERTIFICATION OK: {args.command}" + (f"; {detail}" if detail else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
