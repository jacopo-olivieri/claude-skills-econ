"""The audited-source projection shared by certification and detectors."""

import os
from pathlib import Path


DEFAULT_DETECTOR_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv",
    "venv", ".tox", ".mypy_cache", ".pytest_cache",
}


def path_is_excluded(relative, exclusions):
    return any(relative == excluded or excluded in relative.parents
               for excluded in exclusions)


def existing_exclusions(package_root, manifest):
    """Return existing, safe relative exclusions from the intake manifest."""
    package_root = Path(package_root)
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
            if (package_root / relative).exists():
                exclusions.add(relative)
    return exclusions


def iter_in_scope_entries(package_root, manifest, onerror=None):
    """Yield ``(path, relative, kind)`` for fingerprinted files and links."""
    package_root = Path(package_root).expanduser().resolve()
    exclusions = existing_exclusions(package_root, manifest)

    def walk(directory):
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            if onerror is not None:
                onerror(exc)
                return
            raise
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(package_root)
            if path_is_excluded(relative, exclusions):
                continue
            if entry.is_symlink():
                yield path, relative, "symlink"
            elif entry.is_dir(follow_symlinks=False):
                yield from walk(path)
            elif entry.is_file(follow_symlinks=False):
                yield path, relative, "file"

    yield from walk(package_root)


def audited_regular_files(package_root, manifest, skip_dirs=None, onerror=None,
                          onlink=None):
    """Return detector-readable regular files within the U2 projection."""
    skip_dirs = DEFAULT_DETECTOR_SKIP_DIRS if skip_dirs is None else set(skip_dirs)
    files = []
    for path, relative, kind in iter_in_scope_entries(
            package_root, manifest, onerror=onerror):
        if kind == "symlink":
            if onlink is not None:
                onlink(path, relative)
            continue
        if any(part in skip_dirs for part in relative.parts[:-1]):
            continue
        files.append(path)
    return files
