"""Smoke tests for export_xlsx.py (home for U6's hardening tests)."""

import pytest

import regbuild as rb

openpyxl = pytest.importorskip("openpyxl")


def make_canon_audit(tmp_path):
    a = rb.AuditDir(tmp_path)
    a.write_manifest(warnings=["one degraded-confidence warning"])
    a.write_register("claims_register.md", rb.CLAIMS_COLS, [
        rb.claims_row("C-0000"),  # schema example row — must be dropped
        rb.claims_row("C-0101", status="confirmed"),
        rb.claims_row("C-0102", status="inconsistent", severity="3",
                      issue="the paper and the artifact disagree"),
    ])
    a.write_register("code_error_register.md", rb.ERROR_COLS, [
        rb.error_row("E-0101", severity="2"),
    ])
    return a


def test_export_replication_workbook(tmp_path):
    a = make_canon_audit(tmp_path)
    out = tmp_path / "code_review.xlsx"
    res = rb.run_script("export_xlsx.py", "--audit-dir", a.audit,
                        "--mode", "replication", "-o", out)
    assert res.returncode == 0, res.stdout + res.stderr

    wb = openpyxl.load_workbook(out, read_only=True)
    assert set(wb.sheetnames) == {"Overview", "Paper Claims", "Code Errors"}

    ws = wb["Paper Claims"]
    data = list(ws.values)
    headers = [str(h) for h in data[0]]
    assert "Potential Issue" in headers
    rows = {r[headers.index("Claim ID")]: r for r in data[1:]}
    assert "C-0000" not in rows  # example row dropped
    assert rows["C-0101"][headers.index("Potential Issue")] == "FALSE"
    assert rows["C-0102"][headers.index("Potential Issue")] == "TRUE"
