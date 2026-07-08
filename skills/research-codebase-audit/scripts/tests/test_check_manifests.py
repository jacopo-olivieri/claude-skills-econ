"""Tests for check_manifests.py — the U2 manifest-parseability script.

The script parses the audited package's dependency/configuration manifests the
way their consuming tools would and writes an artifact of candidate findings
(``audit/_run/manifest_check.md``). It never hard-fails on package content.
"""

import os

import pytest

import regbuild as rb

cm = rb.load_script("check_manifests")


def make_pkg(tmp_path, files):
    """Write *files* (relpath -> text) under a package root; return the root."""
    root = tmp_path / "pkg"
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    return root


def run(tmp_path, files):
    """Run the CLI on a synthetic package; return (CompletedProcess, artifact text)."""
    root = make_pkg(tmp_path, files)
    audit = tmp_path / "audit"
    res = rb.run_script("check_manifests.py", root, "--audit-dir", audit)
    artifact = audit / "_run" / "manifest_check.md"
    text = artifact.read_text(encoding="utf-8") if artifact.is_file() else None
    return res, text


# --------------------------------------------------------------- happy path


def test_wellformed_requirements_parse_clean(tmp_path):
    res, art = run(tmp_path, {
        "requirements.txt": (
            "# pinned deps\n"
            "numpy==1.21.0\n"
            "pandas>=1.3,<2.0\n"
            "-e ./local_pkg\n"
            "-r extra-requirements.txt\n"
            "--index-url https://pypi.org/simple\n"
            'requests>=2.0; python_version < "3.9"\n'
            "git+https://github.com/x/y.git#egg=y\n"
            "scipy[sparse]==1.7.0\n"
            "tqdm\n"
        ),
        "extra-requirements.txt": "click==8.0\n",
    })
    assert res.returncode == 0, res.stdout + res.stderr
    assert art is not None
    assert cm.NO_FINDINGS_LINE in art


# --------------------------------------------------------------- failure paths


def test_missing_operator_whitespace_yields_one_finding(tmp_path):
    res, art = run(tmp_path, {
        "requirements.txt": "numpy==1.21.0\nstatsmodels 0.13.2\n",
    })
    assert res.returncode == 0, res.stdout + res.stderr
    assert "statsmodels 0.13.2" in art
    # exactly one candidate finding row
    assert art.count("| requirements.txt |") == 1


def test_missing_operator_glued_yields_finding(tmp_path):
    res, art = run(tmp_path, {
        "requirements.txt": "statsmodels0.13.2\n",
    })
    assert res.returncode == 0, res.stdout + res.stderr
    assert "statsmodels0.13.2" in art
    assert cm.NO_FINDINGS_LINE not in art


def test_invalid_toml_yields_finding(tmp_path):
    res, art = run(tmp_path, {
        "pyproject.toml": "[tool.poetry\nname = broken\n",
    })
    assert res.returncode == 0, res.stdout + res.stderr
    assert "pyproject.toml" in art
    assert cm.NO_FINDINGS_LINE not in art


def test_pathologically_nested_toml_is_a_finding_not_a_crash(tmp_path):
    # Untrusted package content: deep array nesting makes tomllib recurse past
    # the interpreter limit (RecursionError), which is not a TOMLDecodeError.
    # The script must still exit 0 and write the artifact, emitting a candidate
    # finding — never hard-fail on package content.
    res, art = run(tmp_path, {"pyproject.toml": "x = " + "[" * 2000})
    assert res.returncode == 0, res.stdout + res.stderr
    assert art is not None
    assert "pyproject.toml" in art
    assert cm.NO_FINDINGS_LINE not in art


def test_valid_toml_parses_clean(tmp_path):
    res, art = run(tmp_path, {
        "pyproject.toml": '[project]\nname = "pkg"\nversion = "0.1"\n',
    })
    assert res.returncode == 0, res.stdout + res.stderr
    assert cm.NO_FINDINGS_LINE in art


# --------------------------------------------------------------- edge cases


def test_unrecognized_format_skipped_silently(tmp_path):
    res, art = run(tmp_path, {
        "environment.yml": "this: is: not: valid: yaml: [\n",
        "Makefile": "all:\n\techo hi\n",
    })
    assert res.returncode == 0, res.stdout + res.stderr
    assert cm.NO_FINDINGS_LINE in art
    assert "environment.yml" not in art
    assert "Makefile" not in art


def test_guarded_toml_import_unavailable_warns_not_raises(tmp_path, monkeypatch):
    root = make_pkg(tmp_path, {
        "pyproject.toml": '[project]\nname = "pkg"\n',
    })
    monkeypatch.setattr(cm, "tomllib", None)
    results = cm.check_package(root)  # must not raise
    assert any("tomllib" in w for w in results["warnings"])
    assert results["findings"] == []


def test_empty_and_comment_only_manifests_parse_clean(tmp_path):
    res, art = run(tmp_path, {
        "requirements.txt": "",
        "constraints.txt": "# nothing here\n\n# still nothing\n",
        "empty.toml": "",
    })
    assert res.returncode == 0, res.stdout + res.stderr
    assert cm.NO_FINDINGS_LINE in art


def test_plain_names_without_versions_are_tolerated(tmp_path):
    res, art = run(tmp_path, {
        "requirements.txt": "numpy\nbackports.csv\nurllib3\npytest-xdist\n",
    })
    assert res.returncode == 0, res.stdout + res.stderr
    assert cm.NO_FINDINGS_LINE in art


# --------------------------------------------------------------- CLI contract


def test_missing_package_root_is_usage_error(tmp_path):
    res = rb.run_script("check_manifests.py", tmp_path / "nope",
                        "--audit-dir", tmp_path / "audit")
    assert res.returncode == 2


def test_explicit_output_path_overrides_audit_dir(tmp_path):
    root = make_pkg(tmp_path, {"requirements.txt": "numpy==1.0\n"})
    out = tmp_path / "elsewhere" / "mc.md"
    res = rb.run_script("check_manifests.py", root, "-o", out)
    assert res.returncode == 0, res.stdout + res.stderr
    assert out.is_file()


# --------------------------------------------------------------- coverage: walk


def test_manifest_under_skip_dir_is_not_checked(tmp_path):
    # A recognized manifest buried under a SKIP_DIRS directory (.git, node_modules)
    # must be pruned from the walk: it never appears in "Manifests checked".
    res, art = run(tmp_path, {
        ".git/requirements.txt": "package 1.2.3\n",
        "node_modules/foo/requirements.txt": "another 4.5.6\n",
        "requirements.txt": "numpy==1.0\n",
    })
    assert res.returncode == 0, res.stdout + res.stderr
    assert "`requirements.txt`" in art  # the top-level one is checked
    assert ".git/requirements.txt" not in art
    assert "node_modules" not in art
    # the buried offending lines never surface
    assert "package 1.2.3" not in art
    assert "another 4.5.6" not in art


def test_non_utf8_manifest_yields_encoding_finding_not_crash(tmp_path):
    # Raw non-UTF-8 bytes in a recognized manifest: the consuming tool would
    # reject it, so the script emits a candidate finding — and never crashes.
    root = tmp_path / "pkg"
    root.mkdir(parents=True, exist_ok=True)
    (root / "requirements.txt").write_bytes(b"numpy==1.0\n\xff\xfe not utf-8\n")
    audit = tmp_path / "audit"
    res = rb.run_script("check_manifests.py", root, "--audit-dir", audit)
    art = (audit / "_run" / "manifest_check.md").read_text(encoding="utf-8")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "not valid UTF-8" in art
    assert cm.NO_FINDINGS_LINE not in art


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="chmod-000 read guard does not apply to root")
def test_unreadable_manifest_yields_warning_not_exception(tmp_path):
    # An OSError on read (unreadable file) must degrade to a warning, mirroring
    # test_guarded_toml_import_unavailable — never an exception, never a finding.
    root = make_pkg(tmp_path, {"requirements.txt": "numpy==1.0\n"})
    target = root / "requirements.txt"
    os.chmod(target, 0o000)
    try:
        results = cm.check_package(root)  # must not raise
    finally:
        os.chmod(target, 0o644)
    assert any("could not read requirements.txt" in w
               for w in results["warnings"])
    assert results["findings"] == []


# --------------------------------------------------------------- security: boundary


def test_symlink_manifest_is_not_read_and_is_warned(tmp_path):
    # Finding 2: a hostile package ships requirements.txt as a symlink to a file
    # outside the package (a stand-in for ~/.ssh/id_rsa). Its content must NOT
    # appear in the artifact, and the skip must be surfaced as a warning.
    secret = tmp_path / "secret_outside.txt"
    secret.write_text("SUPERSECRET_PRIVATE_KEY_MATERIAL\n", encoding="utf-8")
    root = tmp_path / "pkg"
    root.mkdir(parents=True, exist_ok=True)
    (root / "requirements.txt").symlink_to(secret)
    audit = tmp_path / "audit"
    res = rb.run_script("check_manifests.py", root, "--audit-dir", audit)
    art = (audit / "_run" / "manifest_check.md").read_text(encoding="utf-8")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "SUPERSECRET_PRIVATE_KEY_MATERIAL" not in art
    assert "## Warnings" in art
    assert "requirements.txt" in art  # named in the warning
    assert "symlink" in art


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="chmod-000 directory guard does not apply to root")
def test_unreadable_directory_is_warned_not_silently_skipped(tmp_path):
    # Finding 6: os.walk silently skips a directory it cannot enter, so a
    # manifest that lives only under it would vanish from the artifact. The
    # onerror handler must record a Warnings entry instead.
    root = make_pkg(tmp_path, {"locked/requirements.txt": "package 1.2.3\n"})
    locked = root / "locked"
    os.chmod(locked, 0o000)
    try:
        res, art = None, None
        audit = tmp_path / "audit"
        res = rb.run_script("check_manifests.py", root, "--audit-dir", audit)
        art = (audit / "_run" / "manifest_check.md").read_text(encoding="utf-8")
    finally:
        os.chmod(locked, 0o755)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "## Warnings" in art
    assert "could not read directory" in art


# --------------------------------------------------------------- content sniffing


def test_content_sniffed_requirements_under_odd_name(tmp_path):
    # The real-world miss: a pip requirements file named python_requirements.txt
    # whose lines read "name version" (invalid pip syntax). It is not matched by
    # filename, but content sniffing pulls it in and the whitespace near-miss
    # fires, tagged detected_by "content".
    root = make_pkg(tmp_path, {
        "python_requirements.txt": (
            "# python dependencies\n"
            "# install with: pip install -r python_requirements.txt\n"
            "dbfread 2.0.7\n"
            "numpy 2.2.0\n"
            "pandas 2.1.0\n"
        ),
    })
    results = cm.check_package(root)
    problems = [f for f in results["findings"]
                if f["manifest"] == "python_requirements.txt"]
    assert len(problems) == 3
    assert all(f["detected_by"] == "content" for f in problems)
    assert all("without an operator" in f["problem"] for f in problems)


def test_bare_name_list_yields_no_findings(tmp_path):
    # A Stata-dependencies lookalike: a header line plus bare names. Bare
    # names carry no version evidence, so the strong-line gate keeps the
    # file from classifying at all — and even if it were checked, bare names
    # are valid pip grammar, so no finding could fire.
    root = make_pkg(tmp_path, {
        "dependencies.txt":
            "Stata packages:\n\navar\nestout\nreghdfe\nftools\n",
    })
    results = cm.check_package(root)
    assert results["findings"] == []
    assert not any(rel == "dependencies.txt" for rel, *_ in results["checked"])


def test_generated_report_bullets_not_classified(tmp_path):
    # A lint-report lookalike: a header sentence plus bullet lines that
    # resemble pip option lines ("- path: message"). Bullets are at most
    # weak evidence and the file has no version-carrying line, so the
    # strong-line gate must keep it out.
    root = make_pkg(tmp_path, {
        "report.txt": (
            "LINT FAIL [b2-claims] — 4 finding(s):\n"
            "  - audit/_work/S1.md: claims row 1 has 12 cells, expected 13\n"
            "  - audit/_work/S1.md: claims row 2 has 12 cells, expected 13\n"
            "  - audit/_work/S1.md: claims row 3 has 12 cells, expected 13\n"
            "  - audit/_work/S1.md: claims row 4 has 12 cells, expected 13\n"
        ),
    })
    results = cm.check_package(root)
    assert results["findings"] == []
    assert not any(rel == "report.txt" for rel, *_ in results["checked"])


def test_audit_workspace_is_not_scanned(tmp_path):
    # The skill's own working directory (identified by its content markers,
    # not its name) fills with generated files during a run; the checker
    # must not descend into it. The same manifest at package root is still
    # found.
    pins = "dbfread 2.0.7\ngeopy 2.4.1\nnumpy 2.2.0\n"
    root = make_pkg(tmp_path, {
        "python_requirements.txt": pins,
        "audit/audit_readme.md": "# audit\n",
        "audit/_run/lint_reports/S1.txt": pins,
    })
    results = cm.check_package(root)
    rels = [rel for rel, *_ in results["checked"]]
    assert "python_requirements.txt" in rels
    assert not any(rel.startswith("audit/") for rel in rels)


def test_prose_txt_is_not_classified_as_manifest(tmp_path):
    # Guards the classification boundary, not the sniffer path: this plain prose
    # has no version-like tokens, so it fails classification on the old code too.
    res, art = run(tmp_path, {
        "README.txt": (
            "This package replicates the main results of the paper.\n"
            "Run the do-files in order to reproduce every table.\n"
            "Questions can be directed to the corresponding author.\n"
            "The data were obtained under a restricted-use agreement.\n"
        ),
    })
    assert res.returncode == 0, res.stdout + res.stderr
    assert cm.NO_FINDINGS_LINE in art
    assert "README.txt" not in art


def test_below_threshold_pins_not_classified(tmp_path):
    # Guards the classification boundary, not the sniffer path: two pins are
    # below SNIFF_MIN_LINES, so this fails classification on the old code too.
    # Only two pin-like lines amid prose: below SNIFF_MIN_LINES, so not a
    # manifest and nothing is checked.
    root = make_pkg(tmp_path, {
        "notes.txt": (
            "The analysis proceeds in three broad stages as follows.\n"
            "We first clean the raw survey extracts before merging.\n"
            "numpy 1.21\n"
            "The second stage estimates the headline specification.\n"
            "pandas 1.3\n"
            "Robustness checks appear in the online appendix section.\n"
        ),
    })
    results = cm.check_package(root)
    assert not any(rel == "notes.txt" for rel, *_ in results["checked"])
    assert results["findings"] == []


# --------------------------------------------------------------- --also handoff


def test_also_forces_check_with_explicit_detection(tmp_path):
    root = make_pkg(tmp_path, {
        "install/deps.cfg": "numpy==1.0\nstatsmodels 0.13.2\n",
    })
    target = root / "install" / "deps.cfg"
    audit = tmp_path / "audit"
    res = rb.run_script("check_manifests.py", root, "--audit-dir", audit,
                        "--also", target)
    art = (audit / "_run" / "manifest_check.md").read_text(encoding="utf-8")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "statsmodels 0.13.2" in art
    assert "explicit" in art
    # and the finding dict carries detected_by "explicit"
    results = cm.check_package(root, also=[target])
    hits = [f for f in results["findings"] if "statsmodels" in f["text"]]
    assert hits and all(f["detected_by"] == "explicit" for f in hits)


def test_also_outside_root_is_skipped_with_warning(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("statsmodels 0.13.2\n", encoding="utf-8")
    root = make_pkg(tmp_path, {"requirements.txt": "numpy==1.0\n"})
    results = cm.check_package(root, also=[outside])
    assert results["findings"] == []
    assert any("outside" in w and "package root" in w
               for w in results["warnings"])


def test_also_symlink_is_skipped_with_warning(tmp_path):
    secret = tmp_path / "secret_outside.txt"
    secret.write_text("statsmodels 0.13.2\n", encoding="utf-8")
    root = make_pkg(tmp_path, {"requirements.txt": "numpy==1.0\n"})
    link = root / "handed_in.txt"
    link.symlink_to(secret)
    results = cm.check_package(root, also=[link])
    assert results["findings"] == []
    assert any("symlink" in w for w in results["warnings"])


# --------------------------------------------------------------- detected_by field


def test_name_matched_requirements_detected_by_filename(tmp_path):
    root = make_pkg(tmp_path, {"requirements.txt": "statsmodels 0.13.2\n"})
    results = cm.check_package(root)
    assert results["findings"]
    assert all(f["detected_by"] == "filename" for f in results["findings"])
    assert all(det == "filename" for *_, det in results["checked"])


# ---------------------------------------------- near-miss classifier tightness


def test_enumerated_prose_outputs_list_not_classified(tmp_path):
    # Exercises the tightened near-miss path (fails on the old code, which read
    # "Table 1"/"Figure 2" as name-plus-version pins and sniffed this README as
    # a manifest). A plain-prose outputs list must not be classified.
    res, art = run(tmp_path, {
        "README.txt": (
            "Table 1 summary statistics\n"
            "Table 2 main regressions\n"
            "Figure 1 event study\n"
            "Figure 2 robustness\n"
        ),
    })
    assert res.returncode == 0, res.stdout + res.stderr
    assert cm.NO_FINDINGS_LINE in art
    assert "README.txt" not in art


def test_bare_integer_version_not_pin_like(tmp_path):
    # Exercises the tightened near-miss path: two-token lines whose version is a
    # bare integer ("name 2") are NOT real pins, so the file is not classified.
    root = make_pkg(tmp_path, {
        "notes.txt": (
            "alpha 2\n"
            "beta 3\n"
            "gamma 1\n"
            "delta 4\n"
        ),
    })
    results = cm.check_package(root)
    assert not any(rel == "notes.txt" for rel, *_ in results["checked"])
    assert results["findings"] == []


def test_bom_prefixed_manifest_name_has_no_bom(tmp_path):
    # A UTF-8 BOM on requirements.txt must not glue onto the first line's name
    # in the finding text.
    root = tmp_path / "pkg"
    root.mkdir(parents=True, exist_ok=True)
    (root / "requirements.txt").write_bytes(
        b"\xef\xbb\xbfdbfread 2.0.7\n")
    results = cm.check_package(root)
    hits = [f for f in results["findings"] if "dbfread" in f["text"]]
    assert hits, results["findings"]
    assert all("﻿" not in f["text"] for f in hits)
    assert any(f["text"] == "dbfread 2.0.7" for f in hits)
