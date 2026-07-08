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
* **Requirements-style dependency lists**, checked with a documented,
  deliberately crude line grammar (below). A requirements manifest is
  detected three ways: a fast filename match (``requirements*.txt``/``.in`` or
  ``constraints*.txt``/``.in``, case-insensitive); content sniffing of any
  other ``.txt``/``.in``/extension-less file whose lines read as requirements;
  and an explicit ``--also PATH`` handoff. Manifests are detected by content
  and usage, not only by name, because a pip requirements file can carry any
  name (``python_requirements.txt``, ``deps.in``, …) and installers key off
  the ``-r`` flag, not the filename. Future editors: do NOT narrow detection
  back to the surface features (the name) of whatever example prompted a fix —
  that overfitting is exactly the miss this script was widened to catch.
  Content sniffing additionally requires at least one line carrying actual
  version evidence, so version-free lookalikes (bare-name lists, generated
  reports with bullet lines) do not classify. The audit's own workspace
  (identified by its content markers, not its name) is never scanned.

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

Every emitted finding records how the manifest was detected (``detected_by``:
``filename``, ``content``, or ``explicit``) so the b4 worker knows how much to
trust the classification — a content-sniffed lookalike warrants more scrutiny
than a name-matched file.

Usage:
    check_manifests.py PACKAGE_ROOT [--audit-dir audit] [-o OUTPUT.md]
                       [--also PATH ...]
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
UNPARSEABLE = "line is not parseable as a requirement"

SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules",
             ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache"}

# content sniffing: cap the bytes read from a file opened only to guess whether
# it is a requirements manifest, and the extensions worth sniffing at all
SNIFF_SIZE_CAP = 256 * 1024
SNIFF_EXTS = {".txt", ".in", ""}
SNIFF_MIN_LINES = 3

REQUIREMENTS_NAME_RE = re.compile(
    r"^(requirements|constraints)[\w.-]*\.(txt|in)$", re.IGNORECASE)
OPERATOR_RE = re.compile(r"===|==|~=|!=|<=|>=|<|>|@")
NAME_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")
# a version-like tail (>= two dot-separated numeric components) glued to a name
GLUED_VERSION_RE = re.compile(r"(?P<name>[A-Za-z][A-Za-z0-9._-]*?)(?P<ver>\d+(?:\.\d+)+)$")
# the whitespace near-miss: exactly two tokens — a distribution name, then a
# real version (``dbfread 2.0.7``). The version must carry at least one dot
# (optional leading ``v``, optional common suffixes such as ``rc1``, ``.post1``
# or ``*``); a bare integer does not qualify. Tightened this hard so enumerated
# prose — ``Table 1 summary statistics``, ``Version 2 notes`` — does not read as
# a requirement pin.
PIN_LIKE_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*"                       # distribution name
    r"\s+"                                                # whitespace separator
    r"v?\d+(?:\.\d+)+"                                    # version, >=1 dot
    r"(?:\.?(?:post|dev|rc|pre|alpha|beta|a|b|c)\d*|\.?\*)*"  # optional suffix
    r"$")                                                 # nothing after: 2 tokens
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
    return UNPARSEABLE


def _sniff_line_class(s):
    """Classify a stripped, non-comment line for content sniffing.

    Returns ``"strong"`` for a line carrying actual version evidence — an
    operator requirement (``numpy==2.2.0``), the two-token whitespace
    near-miss with a real dotted version (``dbfread 2.0.7``), or a glued
    version (``numpy2.2.0``). Returns ``"weak"`` for lines a requirements
    file may contain but that prove nothing by themselves — pip option
    lines, URL/VCS requirements, local paths, bare distribution names.
    Returns None for anything else.

    Deliberately stricter than ``check_requirements_line``: a bare-integer
    version (``name 2``) or enumerated prose (``Table 1 summary statistics``,
    ``Version 2 notes``) is None, and generated-report bullet lines
    (``- audit/_work/S1.md: ...``) are at most weak, so a file of them can
    never classify on its own.
    """
    if s.startswith("-"):
        return "weak"  # pip option line (or a prose bullet — hence weak)
    if "://" in s or VCS_RE.match(s):
        return "weak"  # URL / VCS requirement
    if s[0] in "./~":
        return "weak"  # local path
    body = s.split(";", 1)[0].strip()               # drop environment marker
    body = re.split(r"\s+#", body, maxsplit=1)[0].strip()  # drop inline comment
    body = re.sub(r"\[[^\]]*\]", "", body).strip()  # drop extras
    if not body:
        return None
    if OPERATOR_RE.search(body):
        return "strong"  # carries a version operator
    if PIN_LIKE_RE.match(body):
        return "strong"  # name <whitespace> version — the whitespace near-miss
    if GLUED_VERSION_RE.fullmatch(body):
        return "strong"  # version-like suffix glued to the name
    if NAME_RE.fullmatch(body):
        return "weak"  # plain distribution name, no version evidence
    return None


def sniff_requirements(text):
    """Guess whether *text* is a requirements manifest from its content.

    Parse non-comment, non-blank lines; treat the file as a requirements
    manifest when at least ``SNIFF_MIN_LINES`` of them read as requirements
    or recognized near-misses, those make up at least half the non-comment
    lines, AND at least one line carries actual version evidence (an
    operator, a dotted whitespace near-miss, or a glued version). The
    version-evidence requirement keeps version-free lookalikes out: a list
    of bare package names has nothing for the line grammar to find, and a
    generated report whose bullets resemble pip option lines proves nothing
    about pinning. A file full of near-misses is either a broken
    requirements file or not one at all — that ambiguity is exactly what
    the b4 worker adjudicates, so sniffing may still pull in lookalikes
    that do carry version-like lines; that is acceptable by design.
    """
    recognized = strong = total = 0
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        total += 1
        cls = _sniff_line_class(s)
        if cls is not None:
            recognized += 1
            if cls == "strong":
                strong += 1
    return (recognized >= SNIFF_MIN_LINES and recognized * 2 >= total
            and strong >= 1)


def check_requirements_file(rel, text, findings, detected_by):
    n = 0
    for lineno, line in enumerate(text.splitlines(), start=1):
        problem = check_requirements_line(line)
        if problem is not None:
            findings.append({"manifest": rel, "format": "requirements",
                             "line": str(lineno), "text": line.strip(),
                             "problem": problem, "detected_by": detected_by})
            n += 1
    return n


def check_toml_file(rel, text, findings, detected_by):
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
                     "text": "", "problem": f"invalid TOML: {err}",
                     "detected_by": detected_by})
    return 1


# --------------------------------------------------------------- package walk


def classify(name):
    """Return the manifest format for a filename, or None (skip silently)."""
    if REQUIREMENTS_NAME_RE.match(name):
        return "requirements"
    if name.lower().endswith(".toml"):
        return "toml"
    return None


def check_package(root, also=None):
    """Walk *root*; parse every recognized manifest.

    Returns {"checked": [(relpath, format, n_problems, detected_by)],
             "findings": [finding dict], "warnings": [str]}, where
    ``detected_by`` is ``"filename"`` (name match), ``"content"`` (sniffed) or
    ``"explicit"`` (handed in via ``also``).

    *also* is an optional list of paths to treat as requirements manifests
    regardless of name or content (an explicit ``--also`` handoff, e.g. a file
    the package docs feed to ``pip install -r``).

    The audited package is UNTRUSTED. The reader stays strictly inside the
    package boundary: a candidate manifest that is a symlink, or whose real
    path resolves outside the package root, is recorded as a warning and never
    read — otherwise a hostile package could ship ``requirements.txt`` as a
    symlink to ``~/.ssh/id_rsa`` and have its content echoed into the artifact.
    The same guard is applied to sniffed and explicit paths.
    """
    root = Path(root)
    root_rp = root.resolve()
    checked, findings, warnings = [], [], []
    toml_warned = False
    seen = set()  # resolved real paths already processed (dedup across paths)

    def _boundary_ok(path, rel):
        # Never read a symlink or a file whose real path escapes the package
        # root (see docstring). Record the gap so the coverage hole is visible.
        if path.is_symlink():
            warnings.append(
                f"skipped {rel}: it is a symlink and was not read "
                f"(untrusted package — potential path-escape)")
            return False
        try:
            real = path.resolve()
        except OSError as exc:
            warnings.append(f"could not resolve {rel}: {exc}")
            return False
        if not real.is_relative_to(root_rp):
            warnings.append(
                f"skipped {rel}: its real path resolves outside the "
                f"package root and was not read (untrusted package)")
            return False
        return True

    def _record_requirements(rel, path, detected_by):
        try:
            # utf-8-sig: strip a leading BOM so it does not glue onto the first
            # line's package name in the finding text.
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            findings.append({"manifest": rel, "format": "requirements",
                             "line": "", "text": "",
                             "problem": "file is not valid UTF-8; its "
                                        "consuming tool would reject it",
                             "detected_by": detected_by})
            checked.append((rel, "requirements", 1, detected_by))
            return
        except OSError as exc:
            warnings.append(f"could not read {rel}: {exc}")
            return
        n = check_requirements_file(rel, text, findings, detected_by)
        checked.append((rel, "requirements", n, detected_by))

    def _on_walk_error(exc):
        # os.walk swallows errors (e.g. an unreadable directory) by default,
        # silently skipping the subtree — which would let a manifest vanish
        # from the artifact. Surface it as a warning instead.
        name = getattr(exc, "filename", None) or exc
        warnings.append(f"could not read directory {name}: {exc}")

    def _is_audit_workspace(parent, d):
        # The skill's own working directory lives inside the package root
        # and fills up with generated .txt reports that content sniffing
        # would otherwise pull in. Identify it by its content markers
        # (audit_readme.md, _run/manifest.json) rather than by its name —
        # a package may legitimately ship a folder called "audit".
        cand = Path(parent) / d
        try:
            return ((cand / "audit_readme.md").is_file()
                    or (cand / "_run" / "manifest.json").is_file())
        except OSError:
            return False  # unreadable: let the walk surface it as a warning

    for dirpath, dirnames, filenames in os.walk(root, onerror=_on_walk_error):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS
                             and not _is_audit_workspace(dirpath, d))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            fmt = classify(name)
            if fmt is not None:
                if not _boundary_ok(path, rel):
                    continue
                seen.add(path.resolve())
                if fmt == "requirements":
                    _record_requirements(rel, path, "filename")
                    continue
                if tomllib is None:  # fmt == "toml"
                    if not toml_warned:
                        warnings.append(
                            "tomllib unavailable (Python < 3.11): TOML "
                            "manifests were NOT checked — rerun on Python "
                            "3.11+ or verify them manually")
                        toml_warned = True
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    findings.append({"manifest": rel, "format": "toml",
                                     "line": "", "text": "",
                                     "problem": "file is not valid UTF-8; its "
                                                "consuming tool would reject it",
                                     "detected_by": "filename"})
                    checked.append((rel, "toml", 1, "filename"))
                    continue
                except OSError as exc:
                    warnings.append(f"could not read {rel}: {exc}")
                    continue
                n = check_toml_file(rel, text, findings, "filename")
                checked.append((rel, "toml", n, "filename"))
                continue
            # Not name-matched: sniff the content of plausible text files. A
            # requirements manifest can carry any name, so filename is only a
            # fast path — see the module docstring.
            if os.path.splitext(name)[1].lower() not in SNIFF_EXTS:
                continue
            if not _boundary_ok(path, rel):
                continue
            try:
                raw = path.read_bytes()
            except OSError as exc:
                warnings.append(f"could not read {rel}: {exc}")
                continue
            if len(raw) > SNIFF_SIZE_CAP:
                continue  # too large to be a hand-written manifest; skip
            try:
                text = raw.decode("utf-8-sig")  # strip a leading BOM if present
            except UnicodeDecodeError:
                continue  # not text — cannot be a requirements manifest
            if "\x00" in text:
                continue  # binary content
            if not sniff_requirements(text):
                continue
            seen.add(path.resolve())
            n = check_requirements_file(rel, text, findings, "content")
            checked.append((rel, "requirements", n, "content"))

    # Explicit handoffs: files fed to an installer under a name the walk would
    # never key on. Same boundary guard; skip anything already processed.
    for raw in (also or []):
        path = Path(raw)
        try:
            rel = path.resolve().relative_to(root_rp).as_posix()
        except (OSError, ValueError):
            rel = path.as_posix()
        if not _boundary_ok(path, rel):
            continue
        real = path.resolve()
        if real in seen:
            continue
        if not path.is_file():
            warnings.append(f"skipped --also {rel}: not a regular file")
            continue
        seen.add(real)
        _record_requirements(rel, path, "explicit")

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
        lines += ["| Manifest | Format | Detected by | Problem lines |",
                  "| --- | --- | --- | --- |"]
        for rel, fmt, n, det in results["checked"]:
            lines.append(f"| `{_cell(rel)}` | {fmt} | {det} | {n} |")
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
    ap.add_argument("--also", type=Path, action="append", default=None,
                    metavar="PATH",
                    help="treat PATH as a requirements manifest regardless of "
                         "its name or content (repeatable); use for any file "
                         "the docs feed to `pip install -r`. Must resolve "
                         "inside the package root.")
    args = ap.parse_args()

    if not args.package_root.is_dir():
        print(f"error: package root is not a directory: {args.package_root}",
              file=sys.stderr)
        return 2

    results = check_package(args.package_root, also=args.also)
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
