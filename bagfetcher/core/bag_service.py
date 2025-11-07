"""High-level orchestration for bag downloads."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from .models import BagFile
from .sshclient import SSHClientWrapper

ProgressCallback = Callable[[str, int, int], None]


class BagService:
    """Provides bag listing, filtering, and download helpers."""

    def __init__(self, ssh: SSHClientWrapper, bag_dir: str, stage_dir: str):
        self.ssh = ssh
        self.bag_dir = bag_dir
        self.stage_dir = stage_dir

    def fetch_index(self) -> list[BagFile]:
        return self.ssh.list_bags(self.bag_dir)

    def filter_by_time(
        self, items: Iterable[BagFile], start_dt: datetime, end_dt: datetime
    ) -> list[BagFile]:
        filtered = [item for item in items if start_dt <= item.dt <= end_dt]
        filtered.sort(key=lambda bag: bag.dt)
        return filtered

    def stage_and_download(
        self,
        selected: Iterable[BagFile],
        local_dir: Path,
        cleanup: bool,
        progress_cb: ProgressCallback | None = None,
    ) -> None:
        selected = list(selected)
        remote_paths = [bag.remote_path for bag in selected]
        self.ssh.ensure_stage(self.stage_dir)
        self.ssh.stage_files(remote_paths, self.stage_dir)

        for bag in selected:
            dest = local_dir / bag.dt.strftime("%Y-%m-%d") / bag.name
            if progress_cb:
                progress_cb(bag.name, 0, bag.size)
            self.ssh.download_file(
                stage_dir=self.stage_dir,
                name=bag.name,
                local_path=dest,
                progress_cb=(
                    lambda transferred, bag=bag: progress_cb(bag.name, transferred, bag.size)
                    if progress_cb
                    else None
                ),
            )
            if progress_cb:
                progress_cb(bag.name, bag.size, bag.size)

        if cleanup:
            self.ssh.cleanup(self.stage_dir, [bag.name for bag in selected])
