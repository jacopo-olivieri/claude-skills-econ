"""Plant-drift check: the planted fixture files must not change silently.

An accidental "fix" to a planted bug would show up as a mysterious 13/14 in
the next fixture re-score; this test catches it at test time instead. If a
fixture change is INTENTIONAL, regenerate the manifest:

    python - <<'EOF'
    import hashlib, json
    from pathlib import Path
    skill = Path("skills/research-codebase-audit")
    planted = skill / "fixture" / "planted"
    hashes = {
        str(p.relative_to(planted)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(planted.rglob("*")) if p.is_file()
    }
    out = skill / "scripts" / "tests" / "data" / "planted_sha256.json"
    out.write_text(json.dumps(hashes, indent=2) + "\n")
    EOF
"""

import hashlib
import json

import regbuild as rb

MANIFEST = rb.TESTS_DIR / "data" / "planted_sha256.json"
PLANTED = rb.FIXTURE_DIR / "planted"


def test_planted_files_unchanged():
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual = {
        str(p.relative_to(PLANTED)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(PLANTED.rglob("*")) if p.is_file()
    }
    assert actual == expected, (
        "fixture/planted/ differs from the committed hash manifest — a "
        "planted bug may have been 'fixed'. If the change is intentional, "
        "regenerate scripts/tests/data/planted_sha256.json (see module "
        "docstring)."
    )
