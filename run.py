#!/usr/bin/env python
"""Main entrypoint for the trader.

Delegates to `trader.cli`. Kept as a shim so users can just `python run.py`
without knowing about the package.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make src importable when running from the repo without editable install.
_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from trader.cli import app  # noqa: E402


if __name__ == "__main__":
    app()
