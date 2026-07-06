"""Pytest configuration for the research-codebase-audit script tests.

Run from the skill folder with:

    uv run --no-project --with pytest --with openpyxl -- pytest scripts/tests/

(or plain ``python -m pytest scripts/tests/`` if pytest and openpyxl are
installed). Shared builders live in ``regbuild.py``.
"""

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
