"""High-level orchestration for bag downloads."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from .exceptions import DownloadCancelled
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
        cancel_cb: Callable[[], bool] | None = None,
    ) -> None:
        selected = list(selected)
        if not selected:
            return
        staged_names = [bag.name for bag in selected]
        self._ensure_not_cancelled(cancel_cb)
        remote_paths = [bag.remote_path for bag in selected]
        self.ssh.ensure_stage(self.stage_dir)
        self._ensure_not_cancelled(cancel_cb)
        self.ssh.stage_files(remote_paths, self.stage_dir, cancel_cb=cancel_cb)

        try:
            for bag in selected:
                self._ensure_not_cancelled(cancel_cb)
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
                    cancel_cb=cancel_cb,
                )
                if progress_cb:
                    progress_cb(bag.name, bag.size, bag.size)
        finally:
            if cleanup:
                self.ssh.cleanup(self.stage_dir, staged_names)

    @staticmethod
    def _ensure_not_cancelled(cancel_cb: Callable[[], bool] | None) -> None:
        if cancel_cb and cancel_cb():
            raise DownloadCancelled()
