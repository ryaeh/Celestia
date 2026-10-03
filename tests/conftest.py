"""Shared pytest configuration and utilities."""

import sys
from pathlib import Path

# Ensure the repo root is importable regardless of where pytest is invoked from.
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Importing shell_server calls faillog.setup(), which attaches a handler writing
# ERRORs to the real data/logs/errors.log. Tests trigger errors on purpose, so
# mark it done up front to keep test runs out of the user's log.
import celestia_core.faillog as _faillog  # noqa: E402

_faillog._setup_done = True
