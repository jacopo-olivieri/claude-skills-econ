# Maintaining an installation

Machine-specific maintenance notes. Nothing here is needed to *use* the
skills — see the [README](../README.md) for install and contribution basics.

## Sharing one skill copy between Claude and Codex

Skills used by both Claude and Codex can share one repo-owned copy via
`~/.agents/skills`. The guarded migration helper archives an existing installed
directory, makes the `~/.agents` link, and keeps Claude pointed through that
single rollback seam:

```bash
# The checkout must be clean and the skill must be tracked at HEAD.
bash scripts/link-shared-skill.sh --preview skills/<name>
bash scripts/link-shared-skill.sh skills/<name>

# Use the exact archive path printed as "rollback source" if rollback is needed.
bash scripts/link-shared-skill.sh --rollback ~/.agents/backups/<archive> skills/<name>
```

The helper refuses unexpected agent, Claude, Codex, or legacy-command state
before making changes. It never deletes the archive. Once linked, both harnesses
execute the active checkout directly: branch switches and uncommitted edits are
immediately live. Cut over only from a clean, reviewed commit, retain the archive
until fresh Claude and Codex sessions pass, and use `scripts/link-skills.sh` only
for routine linking—it deliberately skips skills already owned by the shared
chain.

## Stata skill tests

The Stata skill keeps its default tests host-independent. Its real-machine
checks are explicit and non-destructive: they run do-files only under pytest's
temporary directory, make no package or permanent preference changes, and are
skipped unless enabled.

```bash
# Portable default (the live module skips before resolving local resources)
uv run --no-project --with pytest -- pytest skills/stata/scripts/tests/

# Opt-in smoke test for the configured or discovered Stata binary and manuals
STATA_LIVE_TESTS=1 uv run --no-project --with pytest --with pdfplumber -- \
  pytest skills/stata/scripts/tests/test_live_stata.py
```
