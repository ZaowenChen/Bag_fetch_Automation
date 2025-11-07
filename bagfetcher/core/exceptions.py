"""Core exceptions shared across BagFetcher."""
from __future__ import annotations


class DownloadCancelled(RuntimeError):
    """Raised when a user cancels an in-progress download."""


__all__ = ["DownloadCancelled"]
