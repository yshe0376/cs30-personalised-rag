"""One logging setup for the whole project.

Stage timings and counts recorded here become the raw material for the Week 2
ablation table, so keep the emitted fields stable.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"


def log_path() -> Path:
    """Return the documented application log path."""

    directory = Path(os.environ.get("CS30_LOG_DIR", "logs"))
    return directory / "cs30.log"


def configure_logging(level: str = "INFO") -> None:
    """Install stderr and rotating-file handlers. Safe to call more than once."""

    resolved = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger("cs30")
    formatter = logging.Formatter(_FORMAT)
    if not any(getattr(handler, "_cs30_console", False) for handler in root.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(formatter)
        handler._cs30_console = True  # type: ignore[attr-defined]
        root.addHandler(handler)

    target = log_path()
    if not any(getattr(handler, "_cs30_file", False) for handler in root.handlers):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                target,
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler._cs30_file = True  # type: ignore[attr-defined]
            root.addHandler(file_handler)
        except OSError as exc:
            root.warning("file logging unavailable path=%s error=%s", target, exc)

    root.propagate = False
    root.setLevel(resolved)


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the shared ``cs30`` namespace."""

    return logging.getLogger(f"cs30.{name}")
