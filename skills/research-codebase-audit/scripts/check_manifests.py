#!/usr/bin/env python3
"""Manifest-parseability check (U2): parse the audited package's dependency and
configuration manifests the way their consuming tools would, and emit a
candidate finding for any manifest a real tool would reject.

Why this exists: a worker reading a malformed manifest tends to charitably
normalize it (rewriting ``package 1.2.3`` into a clean name), which is exactly
what an installer refuses to do. A parser does not normalize.

Recognized formats — anything else is skipped silently, never reported:

* **TOML** (``*.toml``): parsed with the standard-library ``tomllib`` under a
  guarded import. If ``tomllib`` is unavailable (Python < 3.11) the script
  degrades to a warning and skips TOML files — never an exception.
* **Requirements-style dependency lists** (filenames matching
  ``requirements*.txt``/``.in`` or ``constraints*.txt``/``.in``,
  case-insensitive), checked with a documented, deliberately crude line
  grammar (below).

The requirements line grammar (crude by design — a tripwire, not a resolver).
Each line, after stripping whitespace:

1. Blank lines and ``#`` comment lines are tolerated; a trailing ``\\``
   continuation marker is stripped.
2. Lines starting with ``-`` are pip options and are tolerated wholesale
   (``-e``, ``-r``, ``-c``, ``--index-url``, ``--find-links``, ``--hash``, …).
3. Lines containing ``://`` or starting with ``git+``/``hg+``/``svn+``/``bzr+``
   are URL or version-control requirements: tolerated.
4. Lines starting with ``.``, ``/`` or ``~`` are local paths: tolerated.
5. An environment marker (``; python_version < "3.9"``) and an inline comment
   (whitespace + ``#``) are stripped; an extras bracket (``[sparse]``) is
   removed.
6. What remains is tolerated if it contains a version operator
   (``==  ===  ~=  !=  <=  >=  <  >  @``) or is a plain distribution name
   (letters/digits/dot/dash/underscore).
7. Otherwise it is a **candidate finding**: a name followed by whitespace and
   more text (``package 1.2.3``), a version-like suffix glued to a name with
   no operator (``package1.2.3``), or an outright unparseable line.

Every parse failure becomes a candidate finding for a worker to disposition;
the script NEVER hard-fails on package content — the exit status is 0 whenever
the check ran (2 only on usage errors such as a missing package root). The
findings are read from the artifact, not the exit code.

Artifact: a Markdown report written to ``AUDIT_DIR/_run/manifest_check.md``
(override with ``-o``), following the ``audit/_run/conventions.md`` precedent.
It carries a "Manifests checked" table, a "Candidate findings" table
(``| Manifest | Format | Line | Offending Text | Problem |``) whose rows the
b4 recheck-plan step folds into the candidate inventory, and any warnings.
When there are no findings the artifact states so on a fixed line.

Usage:
    check_manifests.py PACKAGE_ROOT [--audit-dir audit] [-o OUTPUT.md]
"""

import argparse
import os
import re
import sys
from pathlib import Path

try:  # guarded import — degrade to a warning, never an exception (see U2/KTD-2)
    import tomllib
except ImportError:  # pragma: no cover - depends on the interpreter version
    tomllib = None

NO_FINDINGS_LINE = "No candidate findings: every recognized manifest parsed clean."

SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules",
             ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache"}

REQUIREMENTS_NAME_RE = re.compile(
    r"^(requirements|constraints)[\w.-]*\.(txt|in)$", re.IGNORECASE)
OPERATOR_RE = re.compile(r"===|==|~=|!=|<=|>=|<|>|@")
NAME_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")
# a version-like tail (>= two dot-separated numeric components) glued to a name
GLUED_VERSION_RE = re.compile(r"(?P<name>[A-Za-z][A-Za-z0-9._-]*?)(?P<ver>\d+(?:\.\d+)+)$")
VCS_RE = re.compile(r"^(git|hg|svn|bzr)\+")
TOML_LINE_RE = re.compile(r"at line (\d+)")


# --------------------------------------------------------------- line grammar


def check_requirements_line(line):
    """Apply the documented crude grammar to one line.

    Returns a problem description (str) if the line is one a real installer
    would reject, else None (tolerated).
    """
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if s.endswith("\\"):
        s = s[:-1].strip()
        if not s:
            return None
    if s.startswith("-"):
        return None  # pip option line (-e, -r, -c, --index-url, --hash, ...)
    if "://" in s or VCS_RE.match(s):
        return None  # URL / VCS requirement
    if s[0] in "./~":
        return None  # local path
    s = s.split(";", 1)[0].strip()          # drop environment marker
    s = re.split(r"\s+#", s, maxsplit=1)[0].strip()  # drop inline comment
    s = re.sub(r"\[[^\]]*\]", "", s).strip()         # drop extras
    if not s:
        return None
    if OPERATOR_RE.search(s):
        return None  # carries a version operator; assume the tool parses it
    if re.search(r"\s", s):
        return "version specifier without an operator (name and version separated by whitespace)"
    m = GLUED_VERSION_RE.fullmatch(s)
    if m:
        return (f"version-like suffix '{m.group('ver')}' glued to the name "
                f"without an operator")
    if NAME_RE.fullmatch(s):
        return None  # plain distribution name, no version pin
    return "line is not parseable as a requirement"


def check_requirements_file(rel, text, findings):
    n = 0
    for lineno, line in enumerate(text.splitlines(), start=1):
        problem = check_requirements_line(line)
        if problem is not None:
            findings.append({"manifest": rel, "format": "requirements",
                             "line": str(lineno), "text": line.strip(),
                             "problem": problem})
            n += 1
    return n


def check_toml_file(rel, text, findings):
    err = None
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        err = str(exc)
    except ValueError as exc:  # tomllib raises ValueError subclasses only
        err = str(exc)
    except RecursionError:
        # pathologically nested input blows the interpreter's recursion limit
        # before tomllib can raise TOMLDecodeError; the consuming tool would
        # crash on it the same way — a parse failure, not a script failure.
        err = "parser recursion limit exceeded (pathologically nested TOML)"
    except Exception as exc:  # never hard-fail on package content
        err = f"unexpected parser failure: {exc.__class__.__name__}: {exc}"
    if err is None:
        return 0
    m = TOML_LINE_RE.search(err)
    findings.append({"manifest": rel, "format": "toml",
                     "line": m.group(1) if m else "",
                     "text": "", "problem": f"invalid TOML: {err}"})
    return 1


# --------------------------------------------------------------- package walk


def classify(name):
    """Return the manifest format for a filename, or None (skip silently)."""
    if REQUIREMENTS_NAME_RE.match(name):
        return "requirements"
    if name.lower().endswith(".toml"):
        return "toml"
    return None


def check_package(root):
    """Walk *root*; parse every recognized manifest.

    Returns {"checked": [(relpath, format, n_problems)],
             "findings": [finding dict], "warnings": [str]}.

    The audited package is UNTRUSTED. The reader stays strictly inside the
    package boundary: a candidate manifest that is a symlink, or whose real
    path resolves outside the package root, is recorded as a warning and never
    read — otherwise a hostile package could ship ``requirements.txt`` as a
    symlink to ``~/.ssh/id_rsa`` and have its content echoed into the artifact.
    """
    root = Path(root)
    root_rp = root.resolve()
    checked, findings, warnings = [], [], []
    toml_warned = False

    def _on_walk_error(exc):
        # os.walk swallows errors (e.g. an unreadable directory) by default,
        # silently skipping the subtree — which would let a manifest vanish
        # from the artifact. Surface it as a warning instead.
        name = getattr(exc, "filename", None) or exc
        warnings.append(f"could not read directory {name}: {exc}")

    for dirpath, dirnames, filenames in os.walk(root, onerror=_on_walk_error):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            fmt = classify(name)
            if fmt is None:
                continue
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            # Boundary guard: never read a symlink or a file whose real path
            # escapes the package root (see docstring). Record the gap so the
            # coverage hole is visible, but emit no content as a finding.
            if path.is_symlink():
                warnings.append(
                    f"skipped {rel}: it is a symlink and was not read "
                    f"(untrusted package — potential path-escape)")
                continue
            try:
                real = path.resolve()
            except OSError as exc:
                warnings.append(f"could not resolve {rel}: {exc}")
                continue
            if not real.is_relative_to(root_rp):
                warnings.append(
                    f"skipped {rel}: its real path resolves outside the "
                    f"package root and was not read (untrusted package)")
                continue
            if fmt == "toml" and tomllib is None:
                if not toml_warned:
                    warnings.append(
                        "tomllib unavailable (Python < 3.11): TOML manifests "
                        "were NOT checked — rerun on Python 3.11+ or verify "
                        "them manually")
                    toml_warned = True
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                findings.append({"manifest": rel, "format": fmt, "line": "",
                                 "text": "",
                                 "problem": "file is not valid UTF-8; its "
                                            "consuming tool would reject it"})
                checked.append((rel, fmt, 1))
                continue
            except OSError as exc:
                warnings.append(f"could not read {rel}: {exc}")
                continue
            if fmt == "requirements":
                n = check_requirements_file(rel, text, findings)
            else:
                n = check_toml_file(rel, text, findings)
            checked.append((rel, fmt, n))
    return {"checked": checked, "findings": findings, "warnings": warnings}


# --------------------------------------------------------------- artifact


def _cell(s):
    return s.replace("|", "\\|").replace("\n", " ")


def render_artifact(results):
    lines = [
        "# Manifest parseability check",
        "",
        "Generated by `scripts/check_manifests.py` (b4). Each candidate-findings",
        "row is a parse failure a real tool would hit: mint it as a `candidate`",
        "code-error row and fold it into the b4 recheck inventory for a worker",
        "to disposition. This artifact never hard-fails a stage.",
        "",
        "## Manifests checked",
        "",
    ]
    if results["checked"]:
        lines += ["| Manifest | Format | Problem lines |",
                  "| --- | --- | --- |"]
        for rel, fmt, n in results["checked"]:
            lines.append(f"| `{_cell(rel)}` | {fmt} | {n} |")
    else:
        lines.append("No recognized manifests found in the package.")
    lines += ["", "## Candidate findings", ""]
    if results["findings"]:
        lines += ["| Manifest | Format | Line | Offending Text | Problem |",
                  "| --- | --- | --- | --- | --- |"]
        for f in results["findings"]:
            text = f"`{_cell(f['text'])}`" if f["text"] else ""
            lines.append(f"| {_cell(f['manifest'])} | {f['format']} | "
                         f"{f['line']} | {text} | {_cell(f['problem'])} |")
    else:
        lines.append(NO_FINDINGS_LINE)
    if results["warnings"]:
        lines += ["", "## Warnings", ""]
        lines += [f"- {w}" for w in results["warnings"]]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package_root", type=Path,
                    help="root of the audited package")
    ap.add_argument("--audit-dir", type=Path, default=Path("audit"),
                    help="audit directory (artifact goes to AUDIT_DIR/_run/"
                         "manifest_check.md)")
    ap.add_argument("-o", "--output", type=Path, default=None,
                    help="explicit artifact path (overrides --audit-dir)")
    args = ap.parse_args()

    if not args.package_root.is_dir():
        print(f"error: package root is not a directory: {args.package_root}",
              file=sys.stderr)
        return 2

    results = check_package(args.package_root)
    out = args.output or (args.audit_dir / "_run" / "manifest_check.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_artifact(results), encoding="utf-8")

    for w in results["warnings"]:
        print(f"WARNING: {w}")
    n = len(results["findings"])
    print(f"checked {len(results['checked'])} manifest(s); "
          f"{n} candidate finding(s) -> {out}")
    return 0  # findings are signalled via the artifact, never the exit status


if __name__ == "__main__":
    sys.exit(main())
