"""Tests for lint_registers.py.

Includes the failing-first contract test for the U1 advisory adjudication
heuristic (KTD-1). No committed fixture run artifacts exist (``fixture/``
holds only the planted package and scorecards), so lintable boundaries are
built synthetically via ``regbuild``.
"""

import pytest

import regbuild as rb


def warning_lines(res, token):
    return [ln for ln in res.stdout.splitlines()
            if ln.startswith("WARNING") and token in ln]


# ------------------------------------------------------------ harness sanity


def test_b0_green_on_empty_registers(tmp_path):
    a = rb.make_b0(tmp_path)
    res = rb.lint(a, "b0")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "LINT PASS [b0]" in res.stdout


def test_b0_red_on_nonempty_register(tmp_path):
    a = rb.make_b0(tmp_path)
    a.write_register("claims_register.md", rb.CLAIMS_COLS,
                     [rb.claims_row("C-0101")])
    res = rb.lint(a, "b0")
    assert res.returncode == 1
    assert "must be empty at b0" in res.stdout


def test_b6_claims_green_on_clean_rows(tmp_path):
    """The b6-claims builder produces a boundary the current linter passes."""
    rows = [
        rb.claims_row("C-0101", status="confirmed"),
        rb.claims_row("C-0102", status="blocked",
                      blocked_check="The raw data is restricted-access."),
    ]
    a = rb.make_b6_claims(tmp_path, rows)
    res = rb.lint(a, "b6-claims")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "LINT PASS [b6-claims]" in res.stdout


def test_b6_claims_red_on_blocked_without_blocked_check(tmp_path):
    """Negative sanity: the harness surfaces a real lint failure."""
    rows = [rb.claims_row("C-0101", status="blocked", blocked_check="")]
    a = rb.make_b6_claims(tmp_path, rows)
    res = rb.lint(a, "b6-claims")
    assert res.returncode == 1
    assert "Blocked Check" in res.stdout


# ------------------------------------------- U1 advisory heuristic (pinned)


@pytest.mark.xfail(strict=True, reason="U1 heuristic not yet implemented")
def test_adjudication_advisory_warning_contract(tmp_path):
    """CONTRACT pinned for U1 (remove the xfail marker when implementing).

    The recommendation-1 advisory heuristic (plan KTD-1 / U1):

    * Runs wherever a *final* claims register is linted — the recheck-merge
      and finalize boundaries, i.e. ``--stage b6-claims`` and ``--stage b8``
      (this test exercises b6-claims).
    * For every claims row whose Status is ``confirmed`` or ``blocked``, the
      linter scans that row's own Issue Description and Blocked Check text
      for contradiction language (a small token set documented inline in
      lint_registers.py, e.g. "whereas", "but the code", "instead",
      "does not match", "should be", "contradicts").
    * A negated mention must NOT fire: "nothing visible confirms or
      contradicts the claim" is a clean blocked row, not a flagged one.
    * The warning is ADVISORY — it never changes the exit code. It surfaces
      as one WARNING line per flagged row, in the linter's existing warning
      format, containing the literal token ``adjudication`` and the flagged
      Claim ID. Suggested shape:

        WARNING [b6-claims]: adjudication: C-0101 (blocked) — Blocked Check
        contains contradiction language ('whereas'); review against the
        escalation rule (registers.md)

      This test asserts only the stable parts: line starts with "WARNING",
      contains "adjudication" and the row ID.
    """
    rows = [
        # (a) blocked row whose Blocked Check records a paper-vs-code
        #     contradiction -> WARNING expected
        rb.claims_row(
            "C-0101", status="blocked",
            blocked_check=(
                "The paper states the estimates use a one-in-ten subsample "
                "whereas the shipped README shows households.csv is a "
                "1-in-20 subsample."
            ),
        ),
        # (b) cleanly-closed confirmed row, no discrepancy language -> silent
        rb.claims_row(
            "C-0102", status="confirmed",
            text="the sample contains 4,832 households",
        ),
        # (c) confirmed row whose Issue Description records a discrepancy
        #     -> WARNING expected
        rb.claims_row(
            "C-0103", status="confirmed", severity="2",
            issue=("The code does not match the stated definition of the "
                   "sample window."),
        ),
        # (d) blocked row whose Blocked Check states only a missing input,
        #     with a negated contradiction mention -> silent
        rb.claims_row(
            "C-0104", status="blocked",
            blocked_check=("The raw survey data is restricted-access; "
                           "nothing visible confirms or contradicts the "
                           "claim."),
        ),
    ]
    a = rb.make_b6_claims(tmp_path, rows)
    res = rb.lint(a, "b6-claims")

    # advisory: the stage still passes
    assert res.returncode == 0, res.stdout + res.stderr

    warns = warning_lines(res, "adjudication")
    assert any("C-0101" in ln for ln in warns), \
        f"no adjudication warning for C-0101 in:\n{res.stdout}"
    assert any("C-0103" in ln for ln in warns), \
        f"no adjudication warning for C-0103 in:\n{res.stdout}"
    assert not any("C-0102" in ln for ln in warns), \
        f"spurious adjudication warning for clean confirmed row C-0102:\n{res.stdout}"
    assert not any("C-0104" in ln for ln in warns), \
        f"spurious adjudication warning for clean blocked row C-0104:\n{res.stdout}"
