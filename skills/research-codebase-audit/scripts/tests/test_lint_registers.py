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


# ------------------------------- U2 conventions artifact (advisory, b4-code)


def test_conventions_artifact_absent_is_silent(tmp_path):
    """No b3c artifact (a package with no multi-site convention) -> no
    conventions warning, and the check never contributes an error."""
    a = rb.make_conventions_b4_code(tmp_path, include_artifact=False)
    res = rb.lint(a, "b4-code")
    assert not warning_lines(res, "conventions.md"), res.stdout


def test_conventions_artifact_wellformed_is_silent(tmp_path):
    """A well-formed artifact with in-vocabulary categories warns about
    nothing."""
    rows = [
        rb.conventions_row("fiscal-year boundary"),
        rb.conventions_row(
            "household ID key", category="id_or_merge_key",
            definition="merge on hhid (C-0210)",
            sites="`do/merge.do`; C-0210; C-0233"),
    ]
    a = rb.make_conventions_b4_code(tmp_path, rows)
    res = rb.lint(a, "b4-code")
    assert not warning_lines(res, "conventions.md"), res.stdout


def test_conventions_artifact_bad_category_warns(tmp_path):
    """An out-of-vocabulary Category draws an advisory warning, never a fail."""
    rows = [rb.conventions_row("mystery thing", category="not_a_real_category")]
    a = rb.make_conventions_b4_code(tmp_path, rows)
    res = rb.lint(a, "b4-code")
    warns = warning_lines(res, "conventions.md")
    assert any("out-of-vocabulary Category" in ln for ln in warns), res.stdout
    assert any("mystery thing" in ln for ln in warns), res.stdout


def test_conventions_artifact_wrong_header_warns(tmp_path):
    """A file present but not the expected table warns (advisory) so the grep
    step knows it may be skipped; still never a hard fail from this check."""
    a = rb.make_conventions_b4_code(tmp_path, include_artifact=False)
    a.write("_run/conventions.md",
            "# Conventions\n\n| Foo | Bar |\n| --- | --- |\n| x | y |\n")
    res = rb.lint(a, "b4-code")
    assert any("expected header" in ln for ln in warning_lines(res, "conventions.md")), \
        res.stdout


# --------------------- U4 identifier-anchoring advisory (b5-claims ledger)
#
# KTD-3: the advisory reads the recheck ledger's `Evidence Checked` column,
# never the claims register's own row (a confirmed register row has no
# evidence column — comparing identifiers against it would fire on nearly
# every clean row). The claim's *text* comes from the canonical claims
# register at ``audit/claims_register.md``, keyed by the ledger row's ID.
# Advisory only: one WARNING per flagged row, exit status never changed.
# Fixture domain: an education-panel package (fresh, non-Floods surface).


def _anchoring_b5(tmp_path, *, claim_text, evidence,
                  verdict="not_substantiated",
                  change="set Status=confirmed",
                  note="", with_register=True):
    """A b5-claims boundary: one rechecked claim row closing `confirmed`."""
    row = rb.ledger_row(
        "C-0101", status="confirmed", severity="", evidence=evidence,
        verdict=verdict, change=change, impact="none", note=note)
    a, shard = rb.make_b5(tmp_path, "claims", ledger_rows=[row])
    if with_register:
        a.write_register(
            "claims_register.md", rb.CLAIMS_COLS,
            [rb.claims_row("C-0101", text=claim_text)],
            title="Claims register")
    return a, shard


def test_anchoring_named_identifier_in_evidence_is_silent(tmp_path):
    """A confirmed close whose evidence names the claimed identifier draws
    no anchoring warning."""
    a, shard = _anchoring_b5(
        tmp_path,
        claim_text=("the score index `test_score_std` is standardized to "
                    "mean zero within each cohort"),
        evidence=("`code/build_scores.R:41-44` standardizes test_score_std "
                  "within cohort; recomputed mean is 0 at shown precision"),
    )
    res = rb.lint(a, "b5-claims", shard=shard)
    assert res.returncode == 0, res.stdout + res.stderr
    assert not warning_lines(res, "anchoring"), res.stdout


def test_anchoring_named_identifier_absent_warns(tmp_path):
    """A confirmed close whose evidence never mentions the claimed identifier
    draws exactly one anchoring warning naming the row — and the warning is
    advisory (exit status unchanged)."""
    a, shard = _anchoring_b5(
        tmp_path,
        claim_text=("the panel drops teachers with `teacher_tenure_yrs` "
                    "below two years"),
        evidence=("verified the drop filter exists at `code/build_panel.R:88` "
                  "and covers the tenure block"),
    )
    res = rb.lint(a, "b5-claims", shard=shard)
    # advisory: never changes the stage exit status
    assert res.returncode == 0, res.stdout + res.stderr
    warns = warning_lines(res, "anchoring")
    assert len(warns) == 1, res.stdout
    assert "C-0101" in warns[0], res.stdout
    assert "teacher_tenure_yrs" in warns[0], res.stdout


def test_anchoring_line_number_only_evidence_warns(tmp_path):
    """PINNED DECISION — the main false-positive path.

    Evidence that cites only a file:line range without repeating the named
    identifier WARNS. Rationale: the evidence-discipline rule already
    requires exact anchors, and the anchoring norm requires each named
    identifier located *at its claimed role* — an anchor that names the
    identifier is the compliant form, so a line-number-only citation is
    exactly the case a human should re-read. Consistent with the U1 advisory
    philosophy: the lexical proxy over-matches by design; advisory noise is
    acceptable, a silent miss is not (the warning never fails the stage).
    """
    a, shard = _anchoring_b5(
        tmp_path,
        claim_text=("the panel drops teachers with `teacher_tenure_yrs` "
                    "below two years"),
        evidence=("`code/build_panel.R:88-93` applies the described drop "
                  "filter; output row count matches the paper"),
    )
    res = rb.lint(a, "b5-claims", shard=shard)
    assert res.returncode == 0, res.stdout + res.stderr
    warns = warning_lines(res, "anchoring")
    assert len(warns) == 1 and "C-0101" in warns[0], res.stdout


def test_anchoring_scoped_to_confirmed_closes_only(tmp_path):
    """A row NOT closing `confirmed` (here `confirmation_needed`) is out of
    scope even when its evidence omits the named identifier — this also pins
    that the 'confirmed' detector does not fire on 'confirmation_needed'."""
    a, shard = _anchoring_b5(
        tmp_path,
        claim_text=("the panel drops teachers with `teacher_tenure_yrs` "
                    "below two years"),
        evidence="static read of `code/build_panel.R:88` could not decide",
        verdict="confirmation_needed",
        change="set Status=confirmation_needed",
        note="cannot decide statically; needs the shipped panel",
    )
    res = rb.lint(a, "b5-claims", shard=shard)
    assert res.returncode == 0, res.stdout + res.stderr
    assert not warning_lines(res, "anchoring"), res.stdout


def test_anchoring_silent_without_claims_register(tmp_path):
    """No canonical claims register in the audit dir (as in these synthetic
    boundaries): the advisory skips silently — it never fails the stage and
    never crashes the linter."""
    a, shard = _anchoring_b5(
        tmp_path,
        claim_text="unused",
        evidence="verified the drop filter exists at `code/build_panel.R:88`",
        with_register=False,
    )
    res = rb.lint(a, "b5-claims", shard=shard)
    assert res.returncode == 0, res.stdout + res.stderr
    assert not warning_lines(res, "anchoring"), res.stdout
