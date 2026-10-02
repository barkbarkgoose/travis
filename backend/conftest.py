"""Pytest configuration for the backend test suite.

Makes the local `keychain` package importable when tests are collected from the
`backend/` directory. Test-specific settings live in `config.settings.test`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
