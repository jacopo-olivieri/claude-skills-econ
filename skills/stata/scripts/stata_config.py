#!/usr/bin/env python3
"""Resolve Stata resources from private config and portable discovery inputs.

The optional private config lives at ``~/.agents/config/stata.json``.  Every
resolver is lazy: a successful higher-precedence value returns before the
config or lower discovery tiers are inspected.  Discovery inputs are
injectable so the portable test suite never depends on the host installation.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path


CONFIG_PATH = Path("~/.agents/config/stata.json").expanduser()
ALLOWED_KEYS = {
    "stata_bin",
    "stata_docs_dir",
    "stata_ado_base_dir",
    "author",
    "stata_version",
}
PATH_KEYS = {"stata_bin", "stata_docs_dir", "stata_ado_base_dir"}

DEFAULT_AUTHOR = "Analyst"
DEFAULT_STATA_VERSION = "18"
DEFAULT_KNOWN_BINARIES = (
    Path("/Applications/Stata/StataSE.app/Contents/MacOS/stata-se"),
)
DEFAULT_KNOWN_DOCS = (Path("/Applications/Stata/docs"),)
DEFAULT_KNOWN_ADO = (Path("/Applications/Stata/ado/base"),)
DEFAULT_APPLICATIONS_DIR = Path("/Applications")
APP_EDITIONS = (
    ("SE", "stata-se"),
    ("MP", "stata-mp"),
    ("BE", "stata-be"),
)


class StataConfigError(Exception):
    """A named, actionable resolver failure suitable for CLI callers."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _has_control_characters(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _path_value(value: object, *, key: str, source: str) -> Path:
    if not isinstance(value, str) or not value.strip() or _has_control_characters(value):
        raise StataConfigError(
            "invalid-path",
            f"{source} value for {key} must be a non-empty path without control characters.",
        )
    return Path(value).expanduser().resolve()


def _profile_value(value: object, *, key: str, config_path: Path) -> str:
    if not isinstance(value, str) or not value.strip() or _has_control_characters(value):
        raise StataConfigError(
            "invalid-config-value",
            f"Config {config_path} key {key} must be a non-empty string without control characters.",
        )
    return value.strip()


def _default_is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _validate_binary(
    value: object,
    *,
    key: str,
    source: str,
    is_executable: Callable[[Path], bool],
) -> Path:
    path = _path_value(value, key=key, source=source)
    if not is_executable(path):
        raise StataConfigError(
            "not-executable",
            f"{source} selected a non-executable Stata binary for {key}: {path}",
        )
    return path


def _validate_directory(value: object, *, key: str, source: str) -> Path:
    path = _path_value(value, key=key, source=source)
    if not path.is_dir():
        raise StataConfigError(
            "not-directory",
            f"{source} selected a path for {key} that is not a directory: {path}",
        )
    return path


def _load_config(
    config_path: Path | str | None,
    *,
    is_executable: Callable[[Path], bool] = _default_is_executable,
) -> dict[str, str]:
    path = Path(config_path if config_path is not None else CONFIG_PATH).expanduser()
    try:
        metadata = path.stat()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise StataConfigError(
            "unreadable-config", f"Could not inspect config {path}: {exc}"
        ) from exc

    if not stat.S_ISREG(metadata.st_mode):
        raise StataConfigError("invalid-config-file", f"Config {path} must be a file.")
    if metadata.st_uid != os.getuid():
        raise StataConfigError(
            "unsafe-config-owner",
            f"Config {path} must be owned by the current user (uid {os.getuid()}).",
        )
    if metadata.st_mode & 0o022:
        raise StataConfigError(
            "unsafe-config-permissions",
            f"Config {path} is group/world-writable; run chmod 600 {path}.",
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StataConfigError(
            "malformed-config", f"Config {path} is not valid JSON: {exc}"
        ) from exc
    except OSError as exc:
        raise StataConfigError(
            "unreadable-config", f"Could not read config {path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise StataConfigError(
            "non-object-config", f"Config {path} must contain one JSON object."
        )

    unknown = sorted(set(data) - ALLOWED_KEYS)
    if unknown:
        raise StataConfigError(
            "unknown-config-key",
            f"Config {path} contains unknown key(s): {', '.join(unknown)}. "
            f"Allowed keys: {', '.join(sorted(ALLOWED_KEYS))}.",
        )

    validated: dict[str, str] = {}
    for key, value in data.items():
        if key == "stata_bin":
            validated[key] = str(
                _validate_binary(
                    value,
                    key=key,
                    source=f"Config {path}",
                    is_executable=is_executable,
                )
            )
        elif key in {"stata_docs_dir", "stata_ado_base_dir"}:
            validated[key] = str(
                _validate_directory(value, key=key, source=f"Config {path}")
            )
        else:
            validated[key] = _profile_value(value, key=key, config_path=path)
    return validated


def _environment(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def _candidate_roots(app_roots: Iterable[Path | str] | None) -> tuple[Path, ...]:
    if app_roots is not None:
        return tuple(sorted((Path(root) for root in app_roots), key=str))
    return tuple(sorted(DEFAULT_APPLICATIONS_DIR.glob("Stata*"), key=str))


def _app_binary_candidates(app_roots: Iterable[Path | str] | None) -> Iterable[Path]:
    roots = _candidate_roots(app_roots)
    for edition, executable in APP_EDITIONS:
        bundle_name = f"Stata{edition}.app"
        for root in roots:
            bundle = root if root.name == bundle_name else root / bundle_name
            yield bundle / "Contents" / "MacOS" / executable


def resolve_stata_bin(
    *,
    env: Mapping[str, str] | None = None,
    config_path: Path | str | None = None,
    which: Callable[[str], str | None] = shutil.which,
    known_candidates: Iterable[Path | str] | None = None,
    app_roots: Iterable[Path | str] | None = None,
    is_executable: Callable[[Path], bool] = _default_is_executable,
) -> Path:
    """Resolve the Stata binary using env, config, PATH, known, then app scan."""
    environment = _environment(env)
    if "STATA_BIN" in environment:
        return _validate_binary(
            environment["STATA_BIN"],
            key="STATA_BIN",
            source="Environment",
            is_executable=is_executable,
        )

    data = _load_config(config_path, is_executable=is_executable)
    if "stata_bin" in data:
        return Path(data["stata_bin"])

    path_candidate = which("stata")
    if path_candidate:
        return _validate_binary(
            path_candidate,
            key="PATH",
            source="PATH",
            is_executable=is_executable,
        )

    known = DEFAULT_KNOWN_BINARIES if known_candidates is None else known_candidates
    for candidate in known:
        path = Path(candidate).expanduser().resolve()
        if is_executable(path):
            return path

    for candidate in _app_binary_candidates(app_roots):
        path = candidate.expanduser().resolve()
        if is_executable(path):
            return path

    raise StataConfigError(
        "resource-not-found",
        "Could not resolve an executable Stata binary. Set STATA_BIN or "
        f"stata_bin in {Path(config_path or CONFIG_PATH).expanduser()}.",
    )


def resolve_docs_dir(
    explicit: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    config_path: Path | str | None = None,
    known_candidates: Iterable[Path | str] | None = None,
) -> Path:
    """Resolve the manual directory using explicit, env, config, then known."""
    if explicit is not None:
        return _validate_directory(explicit, key="--docs-dir", source="CLI")

    environment = _environment(env)
    if "STATA_DOCS_DIR" in environment:
        return _validate_directory(
            environment["STATA_DOCS_DIR"],
            key="STATA_DOCS_DIR",
            source="Environment",
        )

    data = _load_config(config_path)
    if "stata_docs_dir" in data:
        return Path(data["stata_docs_dir"])

    known = DEFAULT_KNOWN_DOCS if known_candidates is None else known_candidates
    for candidate in known:
        path = Path(candidate).expanduser().resolve()
        if path.is_dir():
            return path

    raise StataConfigError(
        "resource-not-found",
        "Could not resolve the Stata manuals directory. Set STATA_DOCS_DIR or "
        f"stata_docs_dir in {Path(config_path or CONFIG_PATH).expanduser()}.",
    )


def _install_root_from_binary(binary: Path) -> Path | None:
    for parent in binary.parents:
        if parent.suffix == ".app":
            return parent.parent
    return None


def _default_derived_ado_candidates(
    *,
    environment: Mapping[str, str],
    config_data: Mapping[str, str],
    which: Callable[[str], str | None],
    known_binary_candidates: Iterable[Path | str] | None,
    known_docs_candidates: Iterable[Path | str] | None,
    app_roots: Iterable[Path | str] | None,
) -> Iterable[Path]:
    docs_values: list[str | Path] = []
    if "STATA_DOCS_DIR" in environment:
        docs_values.append(environment["STATA_DOCS_DIR"])
    if "stata_docs_dir" in config_data:
        docs_values.append(config_data["stata_docs_dir"])
    docs_values.extend(
        DEFAULT_KNOWN_DOCS if known_docs_candidates is None else known_docs_candidates
    )
    for docs_value in docs_values:
        docs = Path(docs_value).expanduser().resolve()
        yield docs.parent / "ado" / "base"

    binary_values: list[str | Path] = []
    if "STATA_BIN" in environment:
        binary_values.append(environment["STATA_BIN"])
    if "stata_bin" in config_data:
        binary_values.append(config_data["stata_bin"])
    path_binary = which("stata")
    if path_binary:
        binary_values.append(path_binary)
    binary_values.extend(
        DEFAULT_KNOWN_BINARIES
        if known_binary_candidates is None
        else known_binary_candidates
    )
    binary_values.extend(_app_binary_candidates(app_roots))
    for binary_value in binary_values:
        install_root = _install_root_from_binary(
            Path(binary_value).expanduser().resolve()
        )
        if install_root is not None:
            yield install_root / "ado" / "base"


def resolve_ado_base_dir(
    *,
    env: Mapping[str, str] | None = None,
    config_path: Path | str | None = None,
    derived_candidates: Iterable[Path | str] | None = None,
    known_candidates: Iterable[Path | str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    known_binary_candidates: Iterable[Path | str] | None = None,
    known_docs_candidates: Iterable[Path | str] | None = None,
    app_roots: Iterable[Path | str] | None = None,
) -> Path:
    """Resolve ado/base using env, config, derived layout, then known."""
    environment = _environment(env)
    if "STATA_ADO_BASE_DIR" in environment:
        return _validate_directory(
            environment["STATA_ADO_BASE_DIR"],
            key="STATA_ADO_BASE_DIR",
            source="Environment",
        )

    data = _load_config(config_path)
    if "stata_ado_base_dir" in data:
        return Path(data["stata_ado_base_dir"])

    derived = derived_candidates
    if derived is None:
        derived = _default_derived_ado_candidates(
            environment=environment,
            config_data=data,
            which=which,
            known_binary_candidates=known_binary_candidates,
            known_docs_candidates=known_docs_candidates,
            app_roots=app_roots,
        )
    for candidate in derived:
        path = Path(candidate).expanduser().resolve()
        if path.is_dir():
            return path

    known = DEFAULT_KNOWN_ADO if known_candidates is None else known_candidates
    for candidate in known:
        path = Path(candidate).expanduser().resolve()
        if path.is_dir():
            return path

    raise StataConfigError(
        "resource-not-found",
        "Could not resolve Stata ado/base. Set STATA_ADO_BASE_DIR or "
        f"stata_ado_base_dir in {Path(config_path or CONFIG_PATH).expanduser()}.",
    )


def resolve_author(*, config_path: Path | str | None = None) -> str:
    """Return the configured do-file author or a neutral public default."""
    data = _load_config(config_path)
    return data.get("author", DEFAULT_AUTHOR)


def resolve_stata_version(*, config_path: Path | str | None = None) -> str:
    """Return the configured Stata version or the preserved neutral default."""
    data = _load_config(config_path)
    return data.get("stata_version", DEFAULT_STATA_VERSION)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve local Stata resources")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=f"Private config path (default: {CONFIG_PATH})",
    )
    parser.add_argument(
        "resource",
        choices=("stata-bin", "docs-dir", "ado-base-dir", "author", "stata-version"),
    )
    parser.add_argument(
        "--explicit",
        help="Explicit path for docs-dir (the search helper's --docs-dir value)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.resource == "stata-bin":
            value: str | Path = resolve_stata_bin(config_path=args.config)
        elif args.resource == "docs-dir":
            value = resolve_docs_dir(args.explicit, config_path=args.config)
        elif args.resource == "ado-base-dir":
            value = resolve_ado_base_dir(config_path=args.config)
        elif args.resource == "author":
            value = resolve_author(config_path=args.config)
        else:
            value = resolve_stata_version(config_path=args.config)
    except StataConfigError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 2

    print(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
