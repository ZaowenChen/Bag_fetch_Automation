"""Background worker objects for network operations."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QObject, Signal, Slot

from bagfetcher.core.bag_service import BagService
from bagfetcher.core.exceptions import DownloadCancelled
from bagfetcher.core.models import BagFile
from bagfetcher.core.robot_info import (
    RobotInfo,
    download_user_config,
    fetch_robot_info,
    resolve_local_config_dir,
)
from bagfetcher.core.sshclient import SSHClientWrapper


class ConnectWorker(QObject):
    finished = Signal(object, object, list)  # ssh, service, bags
    error = Signal(str)
    robot_info_ready = Signal(object, object)  # RobotInfo, user_config_path (or None)
    user_config_failed = Signal(str)

    def __init__(self, payload: dict):
        super().__init__()
        self.payload = payload

    @Slot()
    def run(self) -> None:
        try:
            ssh = SSHClientWrapper(
                host=self.payload["host"],
                port=self.payload["port"],
                user=self.payload["user"],
                password=self.payload["password"],
            )
            ssh.connect()
            service = BagService(ssh, self.payload["bag_dir"], self.payload["stage_dir"])
            bags = service.fetch_index()
            self._fetch_robot_info(ssh)
        except Exception as exc:  # pragma: no cover - network side effects
            self.error.emit(str(exc))
            return
        self.finished.emit(ssh, service, bags)

    # ------------------------------------------------------------------
    def _fetch_robot_info(self, ssh: SSHClientWrapper) -> None:
        """Fetch robot metadata and download user_config.yaml."""
        robot_info: RobotInfo
        try:
            robot_info = fetch_robot_info(ssh.sftp)
        except Exception:
            robot_info = RobotInfo()

        local_path: str | None = None
        try:
            local_dir = resolve_local_config_dir(robot_info, self.payload["host"])
            os.makedirs(local_dir, exist_ok=True)
            local_path = os.path.join(local_dir, "user_config.yaml")
            download_user_config(ssh.sftp, local_path, ssh_wrapper=ssh)
        except Exception as exc:
            local_path = None
            self.user_config_failed.emit(f"Failed to download user_config.yaml: {exc}")

        self.robot_info_ready.emit(robot_info, local_path)


class DownloadWorker(QObject):
    progress = Signal(str, int, int)
    status = Signal(str, str)
    finished = Signal()
    cancelled = Signal()
    error = Signal(str)

    def __init__(
        self,
        service: BagService,
        items: Iterable[BagFile],
        local_dir: Path,
        cleanup: bool,
    ) -> None:
        super().__init__()
        self.service = service
        self.items = list(items)
        self.local_dir = local_dir
        self.cleanup = cleanup
        self._cancelled = False

    @Slot()
    def run(self) -> None:
        try:
            self.service.stage_and_download(
                self.items,
                self.local_dir,
                self.cleanup,
                progress_cb=self._emit_progress,
                cancel_cb=self.is_cancelled,
            )
        except DownloadCancelled:
            self.cancelled.emit()
            return
        except Exception as exc:  # pragma: no cover - network side effects
            self.error.emit(str(exc))
            return
        self.finished.emit()

    def request_cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def _emit_progress(self, name: str, transferred: int, total: int) -> None:
        self.progress.emit(name, transferred, total)
        if transferred == total:
            self.status.emit(name, "Completed")
        elif transferred == 0:
            self.status.emit(name, "Starting")
        else:
            self.status.emit(name, "Downloading")
