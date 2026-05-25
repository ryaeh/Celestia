"""Shared pytest configuration and utilities."""

import sys
from pathlib import Path

# Ensure the repo root is importable regardless of where pytest is invoked from.
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
