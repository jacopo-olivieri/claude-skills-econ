"""Pytest configuration for the paper-summary-obsidian script tests.

Run from the repo root (or this skill folder) with:

    uv run --no-project --with pytest --with pyyaml -- pytest skills/paper-summary-obsidian/scripts/tests/

(or plain ``python3 -m pytest scripts/tests/`` if pytest is already installed;
PyYAML-dependent assertions self-skip when yaml is unavailable).

The script under test (``save_paper_summary.py``) lives one directory up, so we
add that ``scripts/`` directory to ``sys.path`` for a direct ``import``.
"""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

TESTS_DIR = Path(__file__).resolve().parent
DATA_DIR = TESTS_DIR / "data"
TEMPLATE_FIXTURE = DATA_DIR / "template_fixture.md"
