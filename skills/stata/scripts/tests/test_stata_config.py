"""Portable contract tests for Stata resource and profile resolution."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import stata_config as config


SCRIPT = Path(__file__).resolve().parent.parent / "stata_config.py"
EMPTY_ENV: dict[str, str] = {}


def _write_config(path: Path, values: dict[str, str], mode: int = 0o600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values), encoding="utf-8")
    path.chmod(mode)
    return path


def _executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _isolated_discovery(**overrides):
    values = {
        "env": EMPTY_ENV,
        "which": lambda _name: None,
        "known_candidates": (),
        "app_roots": (),
    }
    values.update(overrides)
    return values


def test_missing_config_and_key_fall_through_to_injected_binary(tmp_path):
    fallback = _executable(tmp_path / "fallback bin" / "stata")

    assert config.resolve_stata_bin(
        config_path=tmp_path / "missing.json",
        **_isolated_discovery(known_candidates=(fallback,)),
    ) == fallback.resolve()

    cfg = _write_config(tmp_path / "config.json", {"author": "Researcher"})
    assert config.resolve_stata_bin(
        config_path=cfg,
        **_isolated_discovery(known_candidates=(fallback,)),
    ) == fallback.resolve()


def test_environment_binary_wins_without_reading_invalid_config(tmp_path):
    binary = _executable(tmp_path / "env bin" / "stata se")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")

    assert config.resolve_stata_bin(
        env={"STATA_BIN": str(binary)},
        config_path=invalid,
        which=lambda _name: pytest.fail("PATH discovery should not run"),
        known_candidates=(),
        app_roots=(),
    ) == binary.resolve()


def test_explicit_docs_wins_without_reading_invalid_config(tmp_path):
    docs = tmp_path / "explicit docs"
    docs.mkdir()
    invalid = tmp_path / "invalid.json"
    invalid.write_text("[]", encoding="utf-8")

    assert config.resolve_docs_dir(
        explicit=str(docs),
        env={"STATA_DOCS_DIR": str(tmp_path / "ignored")},
        config_path=invalid,
        known_candidates=(),
    ) == docs.resolve()


def test_valid_config_resolves_paths_tilde_symlinks_spaces_and_profiles(
    tmp_path, monkeypatch
):
    home = tmp_path / "private home"
    monkeypatch.setenv("HOME", str(home))
    binary = _executable(home / "Stata install" / "stata se")
    docs = home / "Stata install" / "manual files"
    ado = home / "Stata install" / "ado base"
    docs.mkdir()
    ado.mkdir()
    docs_link = home / "docs link"
    docs_link.symlink_to(docs, target_is_directory=True)
    cfg = _write_config(
        home / ".agents/config/stata.json",
        {
            "stata_bin": "~/Stata install/stata se",
            "stata_docs_dir": "~/docs link",
            "stata_ado_base_dir": "~/Stata install/ado base",
            "author": "A Researcher",
            "stata_version": "19",
        },
    )

    assert config.resolve_stata_bin(
        config_path=cfg, **_isolated_discovery()
    ) == binary.resolve()
    assert config.resolve_docs_dir(
        config_path=cfg, env=EMPTY_ENV, known_candidates=()
    ) == docs.resolve()
    assert config.resolve_ado_base_dir(
        config_path=cfg,
        env=EMPTY_ENV,
        derived_candidates=(),
        known_candidates=(),
    ) == ado.resolve()
    assert config.resolve_author(config_path=cfg) == "A Researcher"
    assert config.resolve_stata_version(config_path=cfg) == "19"


def test_partial_config_with_only_desired_keys_is_valid(tmp_path):
    cfg = _write_config(tmp_path / "stata.json", {"author": "A Researcher"})

    assert config.resolve_author(config_path=cfg) == "A Researcher"
    assert config.resolve_stata_version(config_path=cfg) == "18"


@pytest.mark.parametrize(
    ("contents", "error_code"),
    [
        ("{", "malformed-config"),
        ("[]", "non-object-config"),
        ('{"surprise": "value"}', "unknown-config-key"),
        ('{"stata_docs_dir": ""}', "invalid-path"),
        ('{"stata_docs_dir": "bad\\u0001path"}', "invalid-path"),
    ],
)
def test_reached_config_reports_named_schema_errors(tmp_path, contents, error_code):
    cfg = tmp_path / "stata.json"
    cfg.write_text(contents, encoding="utf-8")
    cfg.chmod(0o600)

    with pytest.raises(config.StataConfigError) as exc:
        config.resolve_docs_dir(
            config_path=cfg, env=EMPTY_ENV, known_candidates=()
        )

    assert exc.value.code == error_code
    assert str(cfg) in str(exc.value)


def test_reached_config_rejects_unsafe_permissions(tmp_path):
    cfg = _write_config(tmp_path / "stata.json", {"author": "Analyst"}, 0o622)

    with pytest.raises(config.StataConfigError) as exc:
        config.resolve_author(config_path=cfg)

    assert exc.value.code == "unsafe-config-permissions"
    assert "group/world-writable" in str(exc.value)


def test_reached_config_rejects_wrong_owner(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path / "stata.json", {"author": "Analyst"})
    monkeypatch.setattr(config.os, "getuid", lambda: cfg.stat().st_uid + 1)

    with pytest.raises(config.StataConfigError) as exc:
        config.resolve_author(config_path=cfg)

    assert exc.value.code == "unsafe-config-owner"


def test_invalid_selected_resources_fail_without_fallback(tmp_path):
    fallback_bin = _executable(tmp_path / "fallback" / "stata")
    nonexec = tmp_path / "not executable"
    nonexec.write_text("no", encoding="utf-8")
    file_not_dir = tmp_path / "manual.pdf"
    file_not_dir.write_text("pdf", encoding="utf-8")

    with pytest.raises(config.StataConfigError) as bin_exc:
        config.resolve_stata_bin(
            env={"STATA_BIN": str(nonexec)},
            config_path=tmp_path / "missing.json",
            which=lambda _name: None,
            known_candidates=(fallback_bin,),
            app_roots=(),
        )
    assert bin_exc.value.code == "not-executable"

    with pytest.raises(config.StataConfigError) as docs_exc:
        config.resolve_docs_dir(
            explicit=str(file_not_dir),
            config_path=tmp_path / "missing.json",
            env=EMPTY_ENV,
            known_candidates=(),
        )
    assert docs_exc.value.code == "not-directory"

    with pytest.raises(config.StataConfigError) as ado_exc:
        config.resolve_ado_base_dir(
            env={"STATA_ADO_BASE_DIR": str(file_not_dir)},
            config_path=tmp_path / "missing.json",
            derived_candidates=(),
            known_candidates=(),
        )
    assert ado_exc.value.code == "not-directory"


@pytest.mark.parametrize(
    ("key", "error_code"),
    [
        ("stata_bin", "not-executable"),
        ("stata_docs_dir", "not-directory"),
        ("stata_ado_base_dir", "not-directory"),
    ],
)
def test_reached_config_validates_configured_resources(
    tmp_path, key, error_code
):
    invalid_resource = tmp_path / "invalid resource"
    invalid_resource.write_text("not a valid resource", encoding="utf-8")
    cfg = _write_config(tmp_path / "stata.json", {key: str(invalid_resource)})

    with pytest.raises(config.StataConfigError) as exc:
        config.resolve_author(config_path=cfg)

    assert exc.value.code == error_code
    assert key in str(exc.value)


def test_binary_discovery_order_is_path_then_known_then_apps(tmp_path):
    path_bin = _executable(tmp_path / "path" / "stata")
    known_bin = _executable(tmp_path / "known" / "stata-se")
    app_root = tmp_path / "Stata Applications"
    app_bin = _executable(
        app_root / "StataSE.app" / "Contents" / "MacOS" / "stata-se"
    )

    assert config.resolve_stata_bin(
        config_path=tmp_path / "missing.json",
        **_isolated_discovery(
            which=lambda _name: str(path_bin),
            known_candidates=(known_bin,),
            app_roots=(app_root,),
        ),
    ) == path_bin.resolve()

    assert config.resolve_stata_bin(
        config_path=tmp_path / "missing.json",
        **_isolated_discovery(
            known_candidates=(known_bin,), app_roots=(app_root,)
        ),
    ) == known_bin.resolve()

    assert config.resolve_stata_bin(
        config_path=tmp_path / "missing.json",
        **_isolated_discovery(app_roots=(app_root,)),
    ) == app_bin.resolve()


def test_app_scan_is_deterministic_se_then_mp_then_be(tmp_path):
    app_root = tmp_path / "Stata"
    expected = _executable(
        app_root / "StataSE.app" / "Contents" / "MacOS" / "stata-se"
    )
    _executable(app_root / "StataMP.app" / "Contents" / "MacOS" / "stata-mp")
    _executable(app_root / "StataBE.app" / "Contents" / "MacOS" / "stata-be")

    assert config.resolve_stata_bin(
        config_path=tmp_path / "missing.json",
        **_isolated_discovery(app_roots=(app_root,)),
    ) == expected.resolve()


def test_ado_derives_from_docs_layout_before_known_fallback(tmp_path):
    install = tmp_path / "Stata"
    docs = install / "docs"
    derived = install / "ado/base"
    known = tmp_path / "known ado"
    docs.mkdir(parents=True)
    derived.mkdir(parents=True)
    known.mkdir()
    cfg = _write_config(tmp_path / "stata.json", {"stata_docs_dir": str(docs)})

    assert config.resolve_ado_base_dir(
        config_path=cfg,
        env=EMPTY_ENV,
        derived_candidates=None,
        known_candidates=(known,),
        which=lambda _name: None,
        known_binary_candidates=(),
        known_docs_candidates=(),
        app_roots=(),
    ) == derived.resolve()


def test_ado_derives_from_binary_app_layout_before_known_fallback(tmp_path):
    install = tmp_path / "Stata"
    binary = _executable(
        install / "StataSE.app" / "Contents" / "MacOS" / "stata-se"
    )
    derived = install / "ado/base"
    known = tmp_path / "known ado"
    derived.mkdir(parents=True)
    known.mkdir()
    cfg = _write_config(tmp_path / "stata.json", {"stata_bin": str(binary)})

    assert config.resolve_ado_base_dir(
        config_path=cfg,
        env=EMPTY_ENV,
        derived_candidates=None,
        known_candidates=(known,),
        which=lambda _name: None,
        known_binary_candidates=(),
        known_docs_candidates=(),
        app_roots=(),
    ) == derived.resolve()


def test_neutral_profile_defaults_do_not_require_config(tmp_path):
    missing = tmp_path / "missing.json"
    assert config.resolve_author(config_path=missing) == "Analyst"
    assert config.resolve_stata_version(config_path=missing) == "18"


def test_no_fallback_never_observes_real_home_or_applications(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "isolated home"))
    observed: list[Path] = []

    def probe(path: Path) -> bool:
        observed.append(path)
        return False

    with pytest.raises(config.StataConfigError) as exc:
        config.resolve_stata_bin(
            config_path=tmp_path / "missing.json",
            env=EMPTY_ENV,
            which=lambda _name: None,
            known_candidates=(),
            app_roots=(),
            is_executable=probe,
        )

    assert exc.value.code == "resource-not-found"
    assert observed == []


def test_cli_prints_only_value_on_success_and_named_error_on_failure(tmp_path):
    binary = _executable(tmp_path / "bin with spaces" / "stata se")
    cfg = _write_config(tmp_path / "stata.json", {"stata_bin": str(binary)})
    env = os.environ.copy()
    env.pop("STATA_BIN", None)

    success = subprocess.run(
        [sys.executable, str(SCRIPT), "--config", str(cfg), "stata-bin"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert success.returncode == 0
    assert success.stdout == f"{binary.resolve()}\n"
    assert success.stderr == ""

    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    bad.chmod(0o600)
    failure = subprocess.run(
        [sys.executable, str(SCRIPT), "--config", str(bad), "author"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert failure.returncode == 2
    assert failure.stdout == ""
    assert failure.stderr.startswith("non-object-config:")


def test_example_config_has_exact_schema_and_neutral_values():
    example = SCRIPT.parent.parent / "config.example.json"
    data = json.loads(example.read_text(encoding="utf-8"))

    assert set(data) == config.ALLOWED_KEYS
    assert "/" + "Users/" not in example.read_text(encoding="utf-8")
    assert data["author"] == "Analyst"
    assert data["stata_version"] == "18"
