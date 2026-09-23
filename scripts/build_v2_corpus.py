"""Repository wrapper for the installed v2 M1 CLI."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cs30.v2.cli import run  # noqa: E402, I001


if __name__ == "__main__":
    raise SystemExit(run())
