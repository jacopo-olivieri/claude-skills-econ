"""Tests for check_manifests.py — the U2 manifest-parseability script.

The script parses the audited package's dependency/configuration manifests the
way their consuming tools would and writes an artifact of candidate findings
(``audit/_run/manifest_check.md``). It never hard-fails on package content.
"""

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
