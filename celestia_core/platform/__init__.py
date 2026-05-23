"""OS-specific path rules (Windows now, Linux stub)."""

from __future__ import annotations

import sys


def get_platform():
    if sys.platform.startswith("linux"):
        from celestia_core.platform import linux as plat

        return plat
    from celestia_core.platform import windows as plat

    return plat
