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
    assert set(wb.sheetnames) == {
        "Overview", "Paper Claims", "Code Errors",
        "Late observations (unverified)", "Late observation coverage",
    }

    ws = wb["Paper Claims"]
    data = list(ws.values)
    headers = [str(h) for h in data[0]]
    assert "Potential Issue" in headers
    rows = {r[headers.index("Claim ID")]: r for r in data[1:]}
    assert "C-0000" not in rows  # example row dropped
    assert rows["C-0101"][headers.index("Potential Issue")] == "FALSE"
    assert rows["C-0102"][headers.index("Potential Issue")] == "TRUE"


# ---------------------------------------------------------------- U6 hardening


def _export(a, tmp_path, mode="replication"):
    out = tmp_path / "code_review.xlsx"
    res = rb.run_script("export_xlsx.py", "--audit-dir", a.audit,
                        "--mode", mode, "-o", out)
    return res, out


def _claims_cell(out, claim_id, column):
    """Read one cell of the Paper Claims sheet back with openpyxl."""
    wb = openpyxl.load_workbook(out)
    ws = wb["Paper Claims"]
    data = list(ws.values)
    headers = [str(h) for h in data[0]]
    row = next(r for r in data[1:] if r[headers.index("Claim ID")] == claim_id)
    cell_value = row[headers.index(column)]
    # locate the same physical cell so we can inspect its data_type
    col_i = headers.index(column) + 1
    for r_i, r in enumerate(data[1:], start=2):
        if r[headers.index("Claim ID")] == claim_id:
            return cell_value, ws.cell(row=r_i, column=col_i)
    return cell_value, None


def test_formula_cell_exported_inert(tmp_path):
    """A cell text beginning with '=' exports as inert text, not a live formula."""
    a = rb.AuditDir(tmp_path)
    a.write_manifest()
    a.write_register("claims_register.md", rb.CLAIMS_COLS, [
        rb.claims_row("C-0201", text="=HYPERLINK(\"http://evil\",\"click\")"),
    ])
    a.write_register("code_error_register.md", rb.ERROR_COLS, [
        rb.error_row("E-0201"),
    ])
    res, out = _export(a, tmp_path)
    assert res.returncode == 0, res.stdout + res.stderr

    value, cell = _claims_cell(out, "C-0201", "Claim Text")
    assert cell.data_type == "s", "cell must be a string, not a formula"
    assert value.startswith("'="), value  # apostrophe-guarded, still readable
    assert value.lstrip("'").startswith("=HYPERLINK"), value


def test_plus_and_at_cells_exported_inert(tmp_path):
    """Cells beginning with '+' or '@' are likewise neutralised."""
    a = rb.AuditDir(tmp_path)
    a.write_manifest()
    a.write_register("claims_register.md", rb.CLAIMS_COLS, [
        rb.claims_row("C-0301", text="+1+1"),
        rb.claims_row("C-0302", text="@SUM(A1:A9)"),
    ])
    a.write_register("code_error_register.md", rb.ERROR_COLS, [
        rb.error_row("E-0301"),
    ])
    res, out = _export(a, tmp_path)
    assert res.returncode == 0, res.stdout + res.stderr

    v1, c1 = _claims_cell(out, "C-0301", "Claim Text")
    assert c1.data_type == "s" and v1 == "'+1+1", v1
    v2, c2 = _claims_cell(out, "C-0302", "Claim Text")
    assert c2.data_type == "s" and v2 == "'@SUM(A1:A9)", v2


def test_negative_number_text_survives_readably(tmp_path):
    """A leading-'-' text cell (a negative number) stays readable text, not a formula."""
    a = rb.AuditDir(tmp_path)
    a.write_manifest()
    a.write_register("claims_register.md", rb.CLAIMS_COLS, [
        rb.claims_row("C-0401", text="-30% vs the stated 30%"),
    ])
    a.write_register("code_error_register.md", rb.ERROR_COLS, [
        rb.error_row("E-0401"),
    ])
    res, out = _export(a, tmp_path)
    assert res.returncode == 0, res.stdout + res.stderr

    value, cell = _claims_cell(out, "C-0401", "Claim Text")
    assert cell.data_type == "s", "cell must be a string, not a formula/number"
    assert value.lstrip("'") == "-30% vs the stated 30%", value  # content intact


def test_invalid_manifest_json_exits_cleanly(tmp_path):
    """Malformed manifest JSON exits non-zero with a clear message, no traceback."""
    a = rb.AuditDir(tmp_path)
    a.write("_run/manifest.json", "{ this is : not valid json ,,, ")
    a.write_register("claims_register.md", rb.CLAIMS_COLS, [
        rb.claims_row("C-0501"),
    ])
    a.write_register("code_error_register.md", rb.ERROR_COLS, [
        rb.error_row("E-0501"),
    ])
    res, _ = _export(a, tmp_path)
    assert res.returncode != 0
    assert "invalid manifest json" in res.stderr.lower()
    assert "Traceback" not in res.stderr


def test_non_list_warnings_does_not_crash(tmp_path):
    """A non-list 'warnings' value is coerced, not crashed on."""
    a = rb.AuditDir(tmp_path)
    a.write_manifest(warnings="a single degraded-confidence warning as a bare string")
    a.write_register("claims_register.md", rb.CLAIMS_COLS, [
        rb.claims_row("C-0601"),
    ])
    a.write_register("code_error_register.md", rb.ERROR_COLS, [
        rb.error_row("E-0601"),
    ])
    res, out = _export(a, tmp_path)
    assert res.returncode == 0, res.stdout + res.stderr
    # the bare string surfaces as a single warning on the Overview sheet
    wb = openpyxl.load_workbook(out)
    overview_text = "\n".join(
        str(c.value) for row in wb["Overview"].iter_rows() for c in row if c.value
    )
    assert "a single degraded-confidence warning as a bare string" in overview_text
