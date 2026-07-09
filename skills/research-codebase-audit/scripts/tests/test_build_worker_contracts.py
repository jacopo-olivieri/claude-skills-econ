"""Tests for deterministic audit readme and worker-contract generation."""

import regbuild as rb


builder = rb.load_script("build_worker_contracts")
REGISTERS = rb.SKILL_DIR / "references" / "registers.md"


def _build(tmp_path):
    audit_dir = tmp_path / "audit"
    artifacts = builder.build_artifacts(REGISTERS, audit_dir)
    return audit_dir, artifacts


def test_contract_extraction_is_verbatim(tmp_path):
    audit_dir, _ = _build(tmp_path)
    source = REGISTERS.read_text(encoding="utf-8")
    section = builder.extract_section(
        source, "Claims register — `audit/claims_register.md`"
    ).rstrip()

    contract = (
        audit_dir / "_run" / "contracts" / "claims_first_pass.md"
    ).read_text(encoding="utf-8")
    assert section in contract


def test_missing_mapped_heading_aborts_and_names_heading(tmp_path):
    source = REGISTERS.read_text(encoding="utf-8")
    broken = tmp_path / "registers.md"
    broken.write_text(
        source.replace("## Untrusted content", "## Renamed untrusted content", 1),
        encoding="utf-8",
    )

    res = rb.run_script(
        "build_worker_contracts.py",
        "--registers",
        broken,
        "--audit-dir",
        tmp_path / "audit",
    )

    assert res.returncode == 2
    assert "mapped heading not found: Untrusted content" in res.stderr


def test_each_generated_role_contains_mapped_sections_in_order(tmp_path):
    audit_dir, artifacts = _build(tmp_path)
    source = REGISTERS.read_text(encoding="utf-8")
    contracts = builder.load_contract_mapping(source)

    expected_contracts = {
        f"_run/contracts/{contract.role}.md" for contract in contracts
    }
    assert expected_contracts.issubset(artifacts)

    for contract in contracts:
        text = (audit_dir / "_run" / "contracts" / f"{contract.role}.md").read_text(
            encoding="utf-8"
        )
        positions = []
        for heading in contract.section_headings:
            section = builder.extract_section(source, heading).rstrip()
            positions.append(text.index(section))
        assert positions == sorted(positions), contract.role


def test_build_is_deterministic(tmp_path):
    audit_dir, artifacts = _build(tmp_path)
    first = {
        rel: path.read_bytes()
        for rel, path in artifacts.items()
    }

    artifacts = builder.build_artifacts(REGISTERS, audit_dir)
    second = {
        rel: path.read_bytes()
        for rel, path in artifacts.items()
    }

    assert second == first


def test_measure_reports_every_artifact_and_contracts_are_smaller(tmp_path):
    res = rb.run_script(
        "build_worker_contracts.py",
        "--audit-dir",
        tmp_path / "audit",
        "--measure",
    )

    assert res.returncode == 0, res.stdout + res.stderr
    lines = res.stdout.strip().splitlines()
    assert lines[0] == "artifact\tchars\tapprox_tokens"
    rows = {}
    for line in lines[1:]:
        artifact, chars, _tokens = line.split("\t")
        rows[artifact] = int(chars)

    contracts = builder.load_contract_mapping(REGISTERS.read_text(encoding="utf-8"))
    assert set(rows) == {"audit_readme.md"} | {
        f"_run/contracts/{contract.role}.md" for contract in contracts
    }
    full_readme_size = rows["audit_readme.md"]
    for artifact, chars in rows.items():
        if artifact.startswith("_run/contracts/"):
            assert chars < full_readme_size, artifact
