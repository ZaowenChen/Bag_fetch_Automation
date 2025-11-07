"""Dataclasses used throughout BagFetcher."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass(slots=True)
class Profile:
    """Connection profile saved to disk."""

    name: str
    host: str
    port: int
    user: str
    bag_dir: str = "/root/GAUSSIAN_RUNTIME_DIR/bag"
    stage_dir: str = "/root/public/tmp"
    save_password: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class BagFile:
    """Represents a bag file on the remote host."""

    name: str
    remote_path: str
    dt: datetime
    size: int


@dataclass(slots=True)
class DownloadJob:
    """Tracks a download request."""

    bag: BagFile
    local_path: Path
    cleanup_remote: bool = False


__all__ = ["Profile", "BagFile", "DownloadJob"]
