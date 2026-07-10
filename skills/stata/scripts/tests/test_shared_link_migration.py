import os
from pathlib import Path
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
HELPER = REPO_ROOT / "scripts" / "link-shared-skill.sh"
ROUTINE_LINKER = REPO_ROOT / "scripts" / "link-skills.sh"


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def make_repo(tmp_path: Path, *, skill_name: str = "stata") -> tuple[Path, Path]:
    repo = tmp_path / "repo with spaces"
    skill = repo / "skills" / skill_name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: stata\n---\n", encoding="utf-8")
    paper = repo / "skills" / "paper-summary"
    paper.mkdir(parents=True, exist_ok=True)
    (paper / "SKILL.md").write_text("paper\n", encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "Migration Tests")
    git(repo, "add", "skills")
    git(repo, "commit", "-qm", "add skill")
    return repo, skill


def run_helper(
    home: Path,
    source: Path,
    *args: str,
    check: bool = False,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["LINK_SHARED_TIMESTAMP"] = "20260710T120000"
    env.update(env_overrides or {})
    result = subprocess.run(
        [str(HELPER), "--home", str(home), *args, str(source)],
        capture_output=True,
        text=True,
        env=env,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def installed_paths(home: Path, name: str = "stata") -> tuple[Path, Path]:
    return home / ".agents" / "skills" / name, home / ".claude" / "skills" / name


def seed_real_install(home: Path, name: str = "stata") -> tuple[Path, Path]:
    agents, claude = installed_paths(home, name)
    agents.mkdir(parents=True)
    (agents / "legacy.txt").write_text("deployed copy\n", encoding="utf-8")
    claude.parent.mkdir(parents=True)
    claude.symlink_to(agents)
    return agents, claude


def seed_paper_sentinel(home: Path, repo: Path) -> tuple[Path, Path]:
    paper_source = repo / "skills" / "paper-summary"
    assert (paper_source / "SKILL.md").is_file()
    agents = home / ".agents" / "skills" / "paper-summary"
    claude = home / ".claude" / "skills" / "paper-summary"
    agents.parent.mkdir(parents=True, exist_ok=True)
    claude.parent.mkdir(parents=True, exist_ok=True)
    agents.symlink_to(paper_source)
    claude.symlink_to(agents)
    return agents, claude


def test_preview_names_archive_and_changes_nothing(tmp_path: Path) -> None:
    _, source = make_repo(tmp_path)
    home = tmp_path / "home"
    agents, claude = seed_real_install(home)
    outside = tmp_path / "outside-sentinel"
    outside.write_text("unchanged\n", encoding="utf-8")

    result = run_helper(home, source, "--preview", check=True)

    assert "preview:" in result.stdout
    assert "rollback source:" in result.stdout
    assert agents.is_dir() and not agents.is_symlink()
    assert claude.readlink() == agents
    assert not (home / ".agents" / "backups").exists()
    assert outside.read_text(encoding="utf-8") == "unchanged\n"


def test_real_install_is_archived_and_shared_chain_created(tmp_path: Path) -> None:
    repo, source = make_repo(tmp_path)
    home = tmp_path / "home"
    agents, claude = seed_real_install(home)
    paper_agents, paper_claude = seed_paper_sentinel(home, repo)
    paper_state = (paper_agents.readlink(), paper_claude.readlink())

    result = run_helper(home, source, check=True)

    archive = home / ".agents" / "backups" / "stata-pre-repo-20260710T120000"
    assert archive.is_dir()
    assert (archive / "legacy.txt").read_text(encoding="utf-8") == "deployed copy\n"
    assert agents.is_symlink() and agents.readlink() == source.resolve()
    assert claude.is_symlink() and claude.readlink() == agents.absolute()
    assert f"rollback source: {archive}" in result.stdout
    assert (paper_agents.readlink(), paper_claude.readlink()) == paper_state


def test_correct_topology_is_idempotent(tmp_path: Path) -> None:
    _, source = make_repo(tmp_path)
    home = tmp_path / "home"
    agents, claude = installed_paths(home)
    agents.parent.mkdir(parents=True)
    claude.parent.mkdir(parents=True)
    agents.symlink_to(source.resolve())
    claude.symlink_to(agents.absolute())

    first = run_helper(home, source, check=True)
    second = run_helper(home, source, check=True)

    assert "already linked" in first.stdout
    assert "already linked" in second.stdout
    assert not (home / ".agents" / "backups").exists()


def test_direct_claude_repo_link_is_repaired(tmp_path: Path) -> None:
    _, source = make_repo(tmp_path)
    home = tmp_path / "home"
    agents, claude = installed_paths(home)
    agents.parent.mkdir(parents=True)
    claude.parent.mkdir(parents=True)
    agents.symlink_to(source.resolve())
    claude.symlink_to(source.resolve())

    result = run_helper(home, source, check=True)

    assert "repaired Claude link" in result.stdout
    assert claude.readlink() == agents.absolute()


def test_archive_collision_uses_a_new_safe_name(tmp_path: Path) -> None:
    _, source = make_repo(tmp_path)
    home = tmp_path / "home"
    seed_real_install(home)
    backups = home / ".agents" / "backups"
    collision = backups / "stata-pre-repo-20260710T120000"
    collision.mkdir(parents=True)
    (collision / "keep.txt").write_text("keep\n", encoding="utf-8")

    result = run_helper(home, source, check=True)

    archive = backups / "stata-pre-repo-20260710T120000-1"
    assert archive.is_dir()
    assert (collision / "keep.txt").read_text(encoding="utf-8") == "keep\n"
    assert f"rollback source: {archive}" in result.stdout


@pytest.mark.parametrize("shadow", ["codex", "command", "command_file"])
def test_discovery_shadows_abort_without_mutation(tmp_path: Path, shadow: str) -> None:
    _, source = make_repo(tmp_path)
    home = tmp_path / "home"
    agents, claude = seed_real_install(home)
    if shadow == "codex":
        target = home / ".codex" / "skills" / "stata"
        target.mkdir(parents=True)
    elif shadow == "command":
        target = home / ".claude" / "commands" / "stata"
        target.mkdir(parents=True)
    else:
        target = home / ".claude" / "commands" / "stata.md"
        target.parent.mkdir(parents=True)
        target.write_text("shadow\n", encoding="utf-8")

    result = run_helper(home, source)

    assert result.returncode != 0
    assert "shadow" in result.stderr.lower()
    assert agents.is_dir() and not agents.is_symlink()
    assert claude.readlink() == agents
    assert not (home / ".agents" / "backups").exists()


@pytest.mark.parametrize("kind", ["relative", "unexpected"])
def test_agents_symlink_must_be_absolute_and_expected(tmp_path: Path, kind: str) -> None:
    _, source = make_repo(tmp_path)
    home = tmp_path / "home"
    agents, _ = installed_paths(home)
    agents.parent.mkdir(parents=True)
    if kind == "relative":
        agents.symlink_to("../../../somewhere/stata")
    else:
        other = tmp_path / "other" / "stata"
        other.mkdir(parents=True)
        agents.symlink_to(other)

    result = run_helper(home, source)

    assert result.returncode != 0
    assert kind in result.stderr.lower()
    assert agents.is_symlink()
    assert not (home / ".agents" / "backups").exists()


def test_missing_source_aborts_before_home_mutation(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = tmp_path / "missing" / "stata"

    result = run_helper(home, source)

    assert result.returncode != 0
    assert "source" in result.stderr.lower()
    assert not home.exists()


def test_untracked_source_aborts_before_home_mutation(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path, skill_name="tracked")
    source = repo / "skills" / "stata"
    source.mkdir()
    (source / "SKILL.md").write_text("untracked\n", encoding="utf-8")
    home = tmp_path / "home"

    result = run_helper(home, source)

    assert result.returncode != 0
    assert "tracked at head" in result.stderr.lower()
    assert not home.exists()


def test_dirty_checkout_aborts_without_archiving(tmp_path: Path) -> None:
    _, source = make_repo(tmp_path)
    home = tmp_path / "home"
    agents, _ = seed_real_install(home)
    (source / "SKILL.md").write_text("dirty\n", encoding="utf-8")

    result = run_helper(home, source)

    assert result.returncode != 0
    assert "dirty" in result.stderr.lower()
    assert agents.is_dir() and not agents.is_symlink()
    assert not (home / ".agents" / "backups").exists()


def test_rollback_restores_archive_only_from_expected_links(tmp_path: Path) -> None:
    _, source = make_repo(tmp_path)
    home = tmp_path / "home"
    agents, claude = seed_real_install(home)
    migrated = run_helper(home, source, check=True)
    archive = Path(
        next(line.split(": ", 1)[1] for line in migrated.stdout.splitlines() if line.startswith("rollback source:"))
    )

    rolled_back = run_helper(home, source, "--rollback", str(archive), check=True)

    assert "rollback complete" in rolled_back.stdout
    assert agents.is_dir() and not agents.is_symlink()
    assert (agents / "legacy.txt").exists()
    assert claude.readlink() == agents.absolute()
    assert not archive.exists()


def test_rollback_refuses_changed_links_without_mutation(tmp_path: Path) -> None:
    _, source = make_repo(tmp_path)
    home = tmp_path / "home"
    agents, claude = seed_real_install(home)
    migrated = run_helper(home, source, check=True)
    archive = next((home / ".agents" / "backups").iterdir())
    claude.unlink()
    claude.symlink_to(tmp_path / "unexpected")

    result = run_helper(home, source, "--rollback", str(archive))

    assert result.returncode != 0
    assert "rollback" in result.stderr.lower()
    assert agents.is_symlink() and agents.readlink() == source.resolve()
    assert archive.is_dir()
    assert claude.readlink() == tmp_path / "unexpected"


def test_rollback_move_failure_restores_repo_link_and_keeps_archive(
    tmp_path: Path,
) -> None:
    _, source = make_repo(tmp_path)
    home = tmp_path / "home"
    agents, claude = seed_real_install(home)
    run_helper(home, source, check=True)
    archive = next((home / ".agents" / "backups").iterdir())
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_mv = fake_bin / "mv"
    fake_mv.write_text("#!/bin/sh\nexit 77\n", encoding="utf-8")
    fake_mv.chmod(0o755)

    result = run_helper(
        home,
        source,
        "--rollback",
        str(archive),
        env_overrides={"PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )

    assert result.returncode == 77
    assert agents.is_symlink() and agents.readlink() == source.resolve()
    assert claude.is_symlink() and claude.readlink() == agents.absolute()
    assert archive.is_dir()


def test_routine_linker_skips_shared_stata_chain(tmp_path: Path) -> None:
    home = tmp_path / "home"
    agents, claude = installed_paths(home)
    agents.parent.mkdir(parents=True)
    claude.parent.mkdir(parents=True)
    agents.symlink_to((REPO_ROOT / "skills" / "stata").resolve())
    claude.symlink_to(agents.absolute())
    paper_agents, paper_claude = seed_paper_sentinel(home, REPO_ROOT)
    paper_state = (paper_agents.readlink(), paper_claude.readlink())
    env = os.environ.copy()
    env["HOME"] = str(home)

    result = subprocess.run(
        [str(ROUTINE_LINKER)], capture_output=True, text=True, env=env
    )

    assert result.returncode == 0, result.stderr
    assert "skipped stata (wired via ~/.agents/skills)" in result.stdout
    assert agents.readlink() == (REPO_ROOT / "skills" / "stata").resolve()
    assert claude.readlink() == agents.absolute()
    assert (paper_agents.readlink(), paper_claude.readlink()) == paper_state
