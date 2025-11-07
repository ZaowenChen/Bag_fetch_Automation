"""Logging configuration for BagFetcher."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path.home() / "Library" / "Logs" / "BagFetcher"
LOG_FILE = LOG_DIR / "app.log"


def configure() -> None:
    """Configure Python logging with rotation."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3
    )
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    # Also log to stderr for developer builds.
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)
