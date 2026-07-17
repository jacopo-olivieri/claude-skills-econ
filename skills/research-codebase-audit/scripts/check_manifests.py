#!/usr/bin/env python3
"""Manifest-parseability detector run at the certified b3d boundary.
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
It carries a "Manifests checked" table, one source-level candidate row per
manifest, a full witness table, and any warnings. The b3d mapping stage closes
every standard source into the canonical register before b3b.
When there are no findings the artifact states so on a fixed line.

Every emitted finding records how the manifest was detected (``detected_by``:
``filename``, ``content``, or ``explicit``) so the recheck worker knows how much to
trust the classification — a content-sniffed lookalike warrants more scrutiny
than a name-matched file.

Usage:
    check_manifests.py PACKAGE_ROOT [--audit-dir audit] [-o OUTPUT.md]
                       [--also PATH ...]
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from bootstrap_conda_oracle import ORACLE_PATH, ORACLE_SHA256
from source_projection import audited_regular_files

try:  # guarded import — degrade to a warning, never an exception (see U2/KTD-2)
    import tomllib
except ImportError:  # pragma: no cover - depends on the interpreter version
    tomllib = None

NO_FINDINGS_LINE = "No candidate findings: every recognized manifest parsed clean."
UNPARSEABLE = "line is not parseable as a requirement"
MF_ZERO_LINE = "No standard MF rows: no manifest candidates were emitted."

RULE_SLUGS = frozenset({
    "invalid-requirement", "invalid-toml", "invalid-utf8",
    "conda-oracle-rejected", "conda-malformed-line",
})

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
CONDA_NAMES = {"environment.yml", "environment.yaml"}


class OracleError(RuntimeError):
    """The conda oracle is absent, tampered, or could not run safely."""


def _short_id(prefix, identity):
    payload = "\0".join(str(part).strip() for part in identity)
    return f"{prefix}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12]}"


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_oracle(path=ORACLE_PATH, expected=ORACLE_SHA256, digest_fn=_sha256):
    path = Path(path)
    if not path.is_file():
        raise OracleError(
            f"conda oracle missing at {path}; expected sha256 {expected}"
        )
    actual = digest_fn(path)
    if actual != expected:
        raise OracleError(
            f"conda oracle digest mismatch at {path}: expected {expected}, actual {actual}"
        )
    return path


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
    the later recheck worker adjudicates, so sniffing may still pull in lookalikes
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
                             "problem": problem, "detected_by": detected_by,
                             "rule_slug": "invalid-requirement"})
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
                     "detected_by": detected_by,
                     "rule_slug": "invalid-toml"})
    return 1


CONDA_SOLVE_FAILURE = "Could not solve for environment specs"


def check_conda_file(rel, path, findings, oracle_path):
    """Ask pinned micromamba for an offline dry-run parse verdict.

    Offline the oracle cannot solve legal-but-uncached specs, so a solver
    failure is not a finding; only a parse or spec rejection is. `--no-rc`
    and `--no-env` keep the verdict independent of the operator's conda
    configuration, which must not influence detection or the b9 re-run.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        findings.append({
            "manifest": rel, "format": "conda", "line": "", "text": "",
            "problem": "file is not valid UTF-8; micromamba would reject it",
            "detected_by": "filename", "rule_slug": "invalid-utf8",
        })
        return 1
    suspicious = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and ":" not in stripped \
                and not stripped.startswith("-"):
            suspicious.append((lineno, line.strip()))
    scrubbed = {key: value for key, value in os.environ.items()
                if not key.startswith(("CONDA_", "MAMBA_"))}
    scrubbed["MAMBA_NO_BANNER"] = "1"
    with tempfile.TemporaryDirectory(prefix="rca-conda-") as prefix:
        result = subprocess.run(
            [str(oracle_path), "env", "create", "--dry-run", "--offline", "--yes",
             "--no-rc", "--no-env",
             "--prefix", str(Path(prefix) / "env"), "--file", str(path)],
            capture_output=True, text=True, env=scrubbed,
        )
    if result.returncode == 0:
        return 0
    if CONDA_SOLVE_FAILURE in (result.stderr or ""):
        return 0
    detail = " ".join((result.stderr or result.stdout).split()).replace(
        prefix, "<temporary-prefix>")[-500:]
    if suspicious:
        for lineno, raw in suspicious:
            findings.append({
                "manifest": rel, "format": "conda", "line": str(lineno),
                "text": raw, "problem": f"micromamba rejected environment: {detail}",
                "detected_by": "filename", "rule_slug": "conda-malformed-line",
            })
    else:
        findings.append({
            "manifest": rel, "format": "conda", "line": "", "text": "",
            "problem": f"micromamba rejected environment: {detail}",
            "detected_by": "filename", "rule_slug": "conda-oracle-rejected",
        })
    return max(1, len(suspicious))


# --------------------------------------------------------------- package walk


def classify(name):
    """Return the manifest format for a filename, or None (skip silently)."""
    if REQUIREMENTS_NAME_RE.match(name):
        return "requirements"
    if name.lower().endswith(".toml"):
        return "toml"
    if name.lower() in CONDA_NAMES:
        return "conda"
    return None


def _read_projection_manifest(root):
    path = Path(root) / "audit" / "_run" / "manifest.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def _consumer_roles(root, files, manifests):
    commands = []
    installer = re.compile(r"\b(?:pip\s+install|conda\s+env\s+create|mamba\s+env\s+create|micromamba\s+env\s+create)\b", re.I)
    for path in files:
        if path in manifests or path.suffix.lower() not in {".md", ".rst", ".txt", ".sh", ".py", ".do", ""}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        commands.extend(line for line in text.splitlines() if installer.search(line))
    roles = {}
    for path in manifests:
        rel = path.relative_to(root).as_posix()
        mentioned = any(rel in command or path.name in command for command in commands)
        roles[rel] = "consumed" if mentioned else ("not_consumed" if commands else "undetermined")
    return roles


def _assign_identities(results):
    seen_sources, seen_witnesses = {}, {}
    for finding in sorted(results["findings"], key=lambda f: (
            f["manifest"], f.get("rule_slug", ""), int(f.get("line") or 0),
            f.get("text", ""))):
        source_input = (finding["manifest"],)
        source_id = _short_id("MF", source_input)
        prior = seen_sources.setdefault(source_id, source_input)
        if prior != source_input:
            raise RuntimeError(f"Source ID collision {source_id}: {prior!r} vs {source_input!r}")
        witness_input = (finding["manifest"], finding.get("line", ""),
                         finding.get("rule_slug", ""), finding.get("text", "").strip())
        witness_id = _short_id("MFW", witness_input)
        prior_witness = seen_witnesses.setdefault(witness_id, witness_input)
        if prior_witness != witness_input:
            raise RuntimeError(
                f"Witness ID collision {witness_id}: {prior_witness!r} vs {witness_input!r}"
            )
        finding["source_id"] = source_id
        finding["witness_id"] = witness_id
        finding["consumer_role"] = results["consumer_roles"].get(
            finding["manifest"], "undetermined")


def check_package(root, also=None, oracle_path=ORACLE_PATH,
                  oracle_sha256=ORACLE_SHA256, digest_fn=_sha256):
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
    root = Path(root).expanduser().resolve()
    root_rp = root
    checked, findings, warnings = [], [], []
    toml_warned = False
    seen = set()  # resolved real paths already processed (dedup across paths)
    manifest = _read_projection_manifest(root)
    def _walk_error(exc):
        warnings.append(f"could not read directory {getattr(exc, 'filename', None) or exc}: {exc}")

    def _link_warning(_path, relative):
        if classify(relative.name) is not None:
            warnings.append(
                f"skipped {relative.as_posix()}: it is a symlink and was not read "
                f"(untrusted package — potential path-escape)"
            )

    projected = audited_regular_files(
        root, manifest, SKIP_DIRS, onerror=_walk_error, onlink=_link_warning)
    conda_paths = [p for p in projected if p.name.lower() in CONDA_NAMES]
    oracle = (require_oracle(oracle_path, oracle_sha256, digest_fn)
              if conda_paths else None)

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
                             "detected_by": detected_by,
                             "rule_slug": "invalid-utf8"})
            checked.append((rel, "requirements", 1, detected_by))
            return
        except OSError as exc:
            warnings.append(f"could not read {rel}: {exc}")
            return
        n = check_requirements_file(rel, text, findings, detected_by)
        checked.append((rel, "requirements", n, detected_by))

    for path in projected:
        name = path.name
        rel = path.relative_to(root).as_posix()
        fmt = classify(name)
        if fmt is not None:
            if not _boundary_ok(path, rel):
                continue
            seen.add(path.resolve())
            if fmt == "requirements":
                _record_requirements(rel, path, "filename")
                continue
            if fmt == "conda":
                n = check_conda_file(rel, path, findings, oracle)
                checked.append((rel, "conda", n, "filename"))
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
                                 "detected_by": "filename",
                                 "rule_slug": "invalid-utf8"})
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

    manifest_paths = {root / rel for rel, *_ in checked}
    results = {
        "checked": checked, "findings": findings, "warnings": warnings,
        "consumer_roles": _consumer_roles(root, projected, manifest_paths),
    }
    _assign_identities(results)
    return results


# --------------------------------------------------------------- artifact


def _cell(s):
    return s.replace("|", "\\|").replace("\n", " ")


def render_artifact(results):
    lines = [
        "# Manifest parseability check",
        "",
        "Generated by `scripts/check_manifests.py` at b3d. Each MF source is",
        "mapped exactly once in `audit/_run/detector_mapping.md` before b3b.",
        "One source represents one manifest; its witness rows preserve every",
        "flagged line and closed-vocabulary rule slug.",
        "",
        "## Manifests checked",
        "",
    ]
    if results["checked"]:
        lines += ["| Manifest | Format | Detected by | Consumer Role | Problem lines |",
                  "| --- | --- | --- | --- | --- |"]
        for rel, fmt, n, det in results["checked"]:
            role = results.get("consumer_roles", {}).get(rel, "undetermined")
            lines.append(f"| `{_cell(rel)}` | {fmt} | {det} | {role} | {n} |")
    else:
        lines.append("No recognized manifests found in the package.")
    lines += ["", "## Candidate findings", ""]
    if results["findings"]:
        grouped = {}
        for finding in results["findings"]:
            grouped.setdefault(finding["source_id"], []).append(finding)
        lines += ["| Source ID | Manifest | Format | Consumer Role | Witness Count |",
                  "| --- | --- | --- | --- | --- |"]
        for source_id, findings in sorted(grouped.items()):
            first = findings[0]
            lines.append(
                f"| `{source_id}` | {_cell(first['manifest'])} | {first['format']} | "
                f"{first['consumer_role']} | {len(findings)} |"
            )
        lines += ["", "## Witnesses", "",
                  "| Source ID | Witness ID | Site Anchor | Rule Slug | Offending Text | Problem |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for f in sorted(results["findings"], key=lambda item: item["witness_id"]):
            text = f"`{_cell(f['text'])}`" if f["text"] else ""
            anchor = f"{f['manifest']}:{f['line']}" if f["line"] else f["manifest"]
            lines.append(
                f"| `{f['source_id']}` | `{f['witness_id']}` | `{_cell(anchor)}` | "
                f"{f['rule_slug']} | {text} | {_cell(f['problem'])} |"
            )
    else:
        lines.append(NO_FINDINGS_LINE)
        lines.append(MF_ZERO_LINE)
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
    ap.add_argument("--oracle-path", type=Path, default=ORACLE_PATH,
                    help=argparse.SUPPRESS)
    args = ap.parse_args()

    if not args.package_root.is_dir():
        print(f"error: package root is not a directory: {args.package_root}",
              file=sys.stderr)
        return 2

    out = args.output or (args.audit_dir / "_run" / "manifest_check.md")
    try:
        results = check_package(args.package_root, also=args.also,
                                oracle_path=args.oracle_path)
    except (OracleError, RuntimeError) as exc:
        out.unlink(missing_ok=True)
        print(f"error: {exc}", file=sys.stderr)
        return 1
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
