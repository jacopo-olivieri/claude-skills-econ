"""Builders for synthetic registers, plans, and audit directories.

Shared by every test module in this harness. The goal is that a later unit
(U1, U6, U8) can write a failing-first negative test in a few lines:

    a = regbuild.make_b6_claims(tmp_path, [regbuild.claims_row("C-0101", ...)])
    res = regbuild.lint(a, "b6-claims")
    assert res.returncode == 1

Column vocabularies are imported from ``lint_registers.py`` itself so the
builders can never drift from the linter's schema.
"""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent
SKILL_DIR = SCRIPTS_DIR.parent
FIXTURE_DIR = SKILL_DIR / "fixture"


def load_script(name):
    """Import a scripts/ module by path (the scripts dir is not a package)."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_lint_mod = load_script("lint_registers")
CLAIMS_COLS = _lint_mod.CLAIMS_COLS
OUTPUT_COLS = _lint_mod.OUTPUT_COLS
ERROR_COLS = _lint_mod.ERROR_COLS
LEDGER_COLS = _lint_mod.LEDGER_COLS


def run_script(name, *args, cwd=None):
    """Run a scripts/ CLI as a subprocess; returns CompletedProcess (text mode)."""
    cmd = [sys.executable, str(SCRIPTS_DIR / name)] + [str(a) for a in args]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)


# --------------------------------------------------------------- md builders


def md_table(cols, rows):
    lines = ["| " + " | ".join(cols) + " |",
             "| " + " | ".join(["---"] * len(cols)) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines) + "\n"


def register_text(title, cols, rows):
    return f"# {title}\n\n" + md_table(cols, rows)


def claims_row(cid, *, context="Sec. 1 > para 2", quote="a claimed fact",
               used="TRUE", ctype="quantitative_result",
               text="the paper asserts a value", source="`do/analysis.do`",
               outputs="", status="confirmed", severity="", issue="",
               blocked_check="", related=""):
    return [cid, context, quote, used, ctype, text, source, outputs,
            status, severity, issue, blocked_check, related]


def output_row(oid, *, obj="Table 1", context="Sec. 3 > Table 1",
               location="`paper/paper.tex:10`", pattern="`artifacts/tab1.tex`",
               script="`do/analysis.do`", inputs="`output/panel.csv`",
               spec="baseline", claims="", status="mapped"):
    return [oid, obj, context, location, pattern, script, inputs, spec,
            claims, status]


def error_row(eid, *, etype="stale_or_wrong_path",
              source="`py/make_figures.py`",
              location="`py/make_figures.py:5`", status="confirmed",
              severity="2", desc="a description of what appears wrong",
              why="a consequence for the outputs", related=""):
    return [eid, etype, source, location, status, severity, desc, why, related]


# --------------------------------------------------------------- audit dirs


class AuditDir:
    """A synthetic ``audit/`` directory under a tmp root."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.audit = self.root / "audit"
        for sub in ("_run/snapshots", "_staging", "plans"):
            (self.audit / sub).mkdir(parents=True, exist_ok=True)

    def write(self, rel, text):
        p = self.audit / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def write_manifest(self, **kv):
        manifest = {"mode": "replication", "ladder_level": 1, "warnings": []}
        manifest.update(kv)
        return self.write("_run/manifest.json", json.dumps(manifest, indent=2))

    def write_register(self, rel, cols, rows, title=None):
        title = title or Path(rel).stem.replace("_", " ").title()
        return self.write(rel, register_text(title, cols, rows))

    def write_claims_plan(self):
        """Minimal b1 claims plan: one worker allocation + coordinator ranges."""
        text = (
            "# Claims review plan\n\n"
            "| Worker ID | Worker Scope | Claim ID Range | Output ID Range | Shard File |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| W1 | full paper | C-0100–C-0999 | O-1000–O-1999 | `audit/_work/w1.md` |\n\n"
            "Merge-coordinator range: C-9000–C-9099\n"
            "Merge-coordinator range: O-9000–O-9099\n"
        )
        return self.write("plans/claims_review_plan.md", text)

    def write_recheck_summary(self, stream, splits=0, merges=0):
        name = ("claims_recheck_summary.md" if stream == "claims"
                else "code_error_recheck_summary.md")
        return self.write(
            name,
            f"# {stream} recheck summary\n\n"
            f"Splits declared: {splits}\nMerges declared: {merges}\n",
        )

    def snapshot(self, key, files):
        """Copy the named staging files into ``_run/snapshots/<key>/``."""
        snap = self.audit / "_run" / "snapshots" / key
        snap.mkdir(parents=True, exist_ok=True)
        for f in files:
            shutil.copy2(self.audit / "_staging" / f, snap / f)
        return snap


def lint(auditdir: AuditDir, stage, shard=None):
    args = ["--stage", stage, "--audit-dir", auditdir.audit]
    if shard is not None:
        args += ["--shard", shard]
    return run_script("lint_registers.py", *args)


def make_b0(tmp_path) -> AuditDir:
    """A minimal audit dir that lints green at b0 (all registers empty)."""
    a = AuditDir(tmp_path)
    a.write_manifest()
    a.write_register("claims_register.md", CLAIMS_COLS, [])
    a.write_register("output_register.md", OUTPUT_COLS, [])
    a.write_register("code_error_register.md", ERROR_COLS, [])
    a.write("audit_readme.md", "# Audit readme\n\nVocabulary and rules.\n")
    a.write("CODEMAP.md",
            "# CODEMAP\n\nS-0001 do/analysis.do\nD-0001 data/households.csv\n"
            "B-0001 build step\n\nPRECONDITIONS: 5/5\n")
    return a


def make_b6_claims(tmp_path, claims_rows, output_rows=()) -> AuditDir:
    """A minimal audit dir that reaches the b6-claims boundary cleanly.

    The staging registers equal the b6 snapshot (no splits/merges), so the
    boundary lints green as long as *claims_rows* themselves are valid.
    """
    a = AuditDir(tmp_path)
    a.write_manifest()
    a.write_claims_plan()
    a.write_register("_staging/claims_register.md", CLAIMS_COLS,
                     list(claims_rows), title="Claims register")
    a.write_register("_staging/output_register.md", OUTPUT_COLS,
                     list(output_rows), title="Output register")
    a.snapshot("claims_b6", ["claims_register.md", "output_register.md"])
    a.write_recheck_summary("claims")
    return a
