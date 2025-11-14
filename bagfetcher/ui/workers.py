"""Background worker objects for network operations."""
from __future__ import annotations

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
    robot_info_ready = Signal(object)  # RobotInfo

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
            robot_info = self._fetch_robot_info(ssh)
        except Exception as exc:  # pragma: no cover - network side effects
            self.error.emit(str(exc))
            return
        self.robot_info_ready.emit(robot_info)
        self.finished.emit(ssh, service, bags)

    # ------------------------------------------------------------------
    def _fetch_robot_info(self, ssh: SSHClientWrapper) -> RobotInfo:
        """Fetch robot metadata using SSH fallbacks."""
        try:
            return fetch_robot_info(ssh)
        except Exception:
            return RobotInfo()


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


class UserConfigWorker(QObject):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, ssh: SSHClientWrapper, robot_info: RobotInfo, host: str) -> None:
        super().__init__()
        self.ssh = ssh
        self.robot_info = robot_info
        self.host = host

    @Slot()
    def run(self) -> None:
        try:
            local_dir = resolve_local_config_dir(self.robot_info, self.host)
            Path(local_dir).mkdir(parents=True, exist_ok=True)
            local_path = str(Path(local_dir) / "user_config.yaml")
            download_user_config(self.ssh.sftp, local_path, ssh_wrapper=self.ssh)
        except Exception as exc:  # pragma: no cover - network side effects
            self.error.emit(str(exc))
            return
        self.finished.emit(local_path)
