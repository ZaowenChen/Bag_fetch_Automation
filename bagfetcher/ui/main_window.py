"""Main window composition for BagFetcher."""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from bagfetcher.core.models import BagFile
from bagfetcher.core.robot_info import RobotInfo
from bagfetcher.ui.bag_browser import BagBrowser
from bagfetcher.ui.connect_panel import ConnectPanel
from bagfetcher.ui.download_panel import DownloadPanel
from bagfetcher.ui.workers import ConnectWorker, DownloadWorker, UserConfigWorker

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BagFetcher")
        self.resize(1200, 800)
        self._user_config_path: str | None = None
        self._robot_info: RobotInfo | None = None
        self._current_host: str | None = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        splitter = QSplitter()
        layout.addWidget(splitter)

        self.connect_panel = ConnectPanel()
        splitter.addWidget(self.connect_panel)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.robot_info_panel = self._build_robot_info_panel()
        self.bag_browser = BagBrowser()
        self.download_panel = DownloadPanel()
        right_layout.addWidget(self.robot_info_panel)
        right_layout.addWidget(self.bag_browser, 3)
        right_layout.addWidget(self.download_panel, 2)
        splitter.addWidget(right)

        splitter.setSizes([400, 800])

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.connect_panel.connect_requested.connect(self.handle_connect)
        self.download_panel.download_requested.connect(self.handle_download)
        self.download_panel.cancel_requested.connect(self.handle_cancel_download)
        self.bag_browser.selection_changed.connect(self._selection_changed)

        self._ssh = None
        self._service = None
        self._connect_thread: QThread | None = None
        self._connect_worker: ConnectWorker | None = None
        self._download_thread: QThread | None = None
        self._download_worker: DownloadWorker | None = None
        self._user_config_thread: QThread | None = None
        self._user_config_worker: UserConfigWorker | None = None

        self._config_shortcut = QShortcut(QKeySequence("1"), self)
        self._config_shortcut.activated.connect(self._handle_user_config_download)

    def _build_robot_info_panel(self) -> QGroupBox:
        box = QGroupBox("Robot Info")
        grid = QGridLayout(box)
        labels = [
            ("SN / Product ID:", "robot_info_sn_label"),
            ("Model type:", "robot_info_model_label"),
            ("Model number:", "robot_info_model_number_label"),
            ("Software (上位机版本):", "robot_info_sw_label"),
        ]

        for row, (text, attr) in enumerate(labels):
            grid.addWidget(QLabel(text), row, 0)
            value = QLabel("–")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            setattr(self, attr, value)
            grid.addWidget(value, row, 1, 1, 3)

        grid.addWidget(QLabel("User config:"), len(labels), 0)
        self.user_config_path_label = QLabel("Not downloaded")
        self.user_config_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        grid.addWidget(self.user_config_path_label, len(labels), 1)
        self.user_config_open_btn = QPushButton("Open")
        self.user_config_open_btn.clicked.connect(self._open_user_config_default)
        grid.addWidget(self.user_config_open_btn, len(labels), 2)
        self.user_config_reveal_btn = QPushButton("Reveal in Finder")
        self.user_config_reveal_btn.clicked.connect(self._reveal_user_config)
        grid.addWidget(self.user_config_reveal_btn, len(labels), 3)

        self.download_config_btn = QPushButton("Download user_config (1)")
        self.download_config_btn.clicked.connect(self._handle_user_config_download)
        grid.addWidget(self.download_config_btn, len(labels) + 1, 0, 1, 4)

        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 0)
        self._reset_robot_info_panel()
        return box

    def _reset_robot_info_panel(self) -> None:
        self.robot_info_sn_label.setText("–")
        self.robot_info_model_label.setText("–")
        self.robot_info_model_number_label.setText("–")
        self.robot_info_sw_label.setText("–")
        self.user_config_path_label.setText("Not downloaded")
        self.download_config_btn.setEnabled(False)
        self.user_config_open_btn.setEnabled(False)
        self.user_config_reveal_btn.setEnabled(False)
        self._robot_info = None
        self._user_config_path = None

    # region slots -----------------------------------------------------
    def handle_connect(self, payload: dict) -> None:
        if self._connect_thread:
            QMessageBox.information(self, "BagFetcher", "Already connecting. Please wait.")
            return
        self._reset_robot_info_panel()
        self._current_host = payload.get("host")
        self.status_bar.showMessage("Connecting…")
        self.connect_panel.set_connection_status("Connecting…", state="progress")
        self.connect_panel.setEnabled(False)
        worker = ConnectWorker(payload)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_connected)
        worker.error.connect(self._on_connect_error)
        worker.robot_info_ready.connect(self._on_robot_info_loaded)
        thread.start()
        self._connect_thread = thread
        self._connect_worker = worker

    def handle_download(self, payload: dict) -> None:
        if not self._service:
            QMessageBox.warning(self, "BagFetcher", "Connect to a host before downloading.")
            return
        if self._download_thread:
            QMessageBox.information(self, "BagFetcher", "A download is already in progress.")
            return

        selected = self.bag_browser.selected_bags()
        if not selected:
            QMessageBox.warning(self, "BagFetcher", "Select at least one bag to download.")
            return

        local_dir: Path = payload["directory"]
        cleanup: bool = payload.get("cleanup", True)

        self.download_panel.prepare_progress(selected)
        self.download_panel.set_busy(True)
        self.status_bar.showMessage(f"Downloading {len(selected)} file(s)…")

        worker = DownloadWorker(self._service, selected, local_dir, cleanup)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.download_panel.update_progress)
        worker.status.connect(self.download_panel.update_status)
        worker.finished.connect(self._on_download_finished)
        worker.cancelled.connect(self._on_download_cancelled)
        worker.error.connect(self._on_download_error)
        thread.start()
        self._download_thread = thread
        self._download_worker = worker

    def _selection_changed(self, bags: list[BagFile]) -> None:
        self.status_bar.showMessage(f"{len(bags)} files selected")

    def handle_cancel_download(self) -> None:
        if not self._download_worker:
            return
        self.status_bar.showMessage("Cancelling download…")
        self._download_worker.request_cancel()

    # Worker callbacks -------------------------------------------------
    def _on_connected(self, ssh, service, bags: list[BagFile]) -> None:
        thread = self._connect_thread
        worker = self._connect_worker
        if thread:
            thread.quit()
            thread.wait()
        if worker:
            worker.deleteLater()
        self._connect_thread = None
        self._connect_worker = None
        self.connect_panel.setEnabled(True)
        self._ssh = ssh
        self._service = service
        host = worker.payload["host"]
        self._current_host = host
        self.download_panel.set_suggestion(host)
        self.bag_browser.set_bags(bags)
        self.status_bar.showMessage(f"Connected to {worker.payload['host']} – {len(bags)} files listed", 5000)
        self.connect_panel.set_connection_status(f"Connected to {host}:{worker.payload['port']}", state="connected")
        self._update_user_config_button_state()

    def _on_connect_error(self, message: str) -> None:
        thread = self._connect_thread
        worker = self._connect_worker
        if thread:
            thread.quit()
            thread.wait()
        if worker:
            worker.deleteLater()
        self._connect_thread = None
        self._connect_worker = None
        self.connect_panel.setEnabled(True)
        self.connect_panel.set_connection_status("Connection failed", state="error")
        QMessageBox.critical(self, "BagFetcher", f"Failed to connect: {message}")
        log.exception("Connect failed: %s", message)

    def _on_download_finished(self) -> None:
        thread = self._download_thread
        worker = self._download_worker
        if thread:
            thread.quit()
            thread.wait()
        if worker:
            worker.deleteLater()
        self._download_thread = None
        self._download_worker = None
        self.download_panel.set_busy(False)
        self.download_panel.mark_all_complete()
        self.status_bar.showMessage("Download complete", 5000)

    def _on_download_cancelled(self) -> None:
        thread = self._download_thread
        worker = self._download_worker
        if thread:
            thread.quit()
            thread.wait()
        if worker:
            worker.deleteLater()
        self._download_thread = None
        self._download_worker = None
        self.download_panel.set_busy(False)
        self.download_panel.mark_all_cancelled()
        self.status_bar.showMessage("Download cancelled", 5000)

    def _on_download_error(self, message: str) -> None:
        thread = self._download_thread
        worker = self._download_worker
        if thread:
            thread.quit()
            thread.wait()
        if worker:
            worker.deleteLater()
        self._download_thread = None
        self._download_worker = None
        self.download_panel.set_busy(False)
        QMessageBox.critical(self, "BagFetcher", f"Download failed: {message}")
        log.exception("Download failed: %s", message)

    # Robot info slots -------------------------------------------------
    @Slot(object)
    def _on_robot_info_loaded(self, robot_info: RobotInfo | None) -> None:
        info = robot_info or RobotInfo()
        self._robot_info = info
        self.robot_info_sn_label.setText(info.product_id or info.sn or "Unknown")
        self.robot_info_model_label.setText(info.model_type or "Unknown")
        self.robot_info_model_number_label.setText(info.model_number or "Unknown")
        self.robot_info_sw_label.setText(info.upper_pc_version or "Unknown")
        self._update_user_config_button_state()

    def _open_in_finder(self, path: str) -> None:
        if not path:
            return
        if not os.path.exists(path):
            QMessageBox.warning(self, "BagFetcher", "User config file is missing locally.")
            return
        try:
            subprocess.Popen(["open", "-R", path])
        except Exception as exc:  # pragma: no cover - macOS specific
            QMessageBox.warning(self, "BagFetcher", f"Unable to reveal file in Finder: {exc}")

    def _open_user_config_default(self) -> None:
        if not self._user_config_path:
            QMessageBox.information(self, "BagFetcher", "User config file not downloaded yet.")
            return
        if not os.path.exists(self._user_config_path):
            QMessageBox.warning(self, "BagFetcher", "User config file is missing locally.")
            return
        try:
            subprocess.Popen(["open", self._user_config_path])
        except Exception as exc:
            QMessageBox.warning(self, "BagFetcher", f"Unable to open file: {exc}")

    def _reveal_user_config(self) -> None:
        if not self._user_config_path:
            QMessageBox.information(self, "BagFetcher", "User config file not downloaded yet.")
            return
        self._open_in_finder(self._user_config_path)

    def _handle_user_config_download(self) -> None:
        if self._user_config_thread:
            QMessageBox.information(self, "BagFetcher", "User config download already in progress.")
            return
        if not self._ssh or not self._robot_info:
            QMessageBox.warning(self, "BagFetcher", "Connect first before downloading user_config.yaml.")
            return
        host = self._current_host or "robot"
        worker = UserConfigWorker(self._ssh, self._robot_info, host)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_user_config_downloaded)
        worker.error.connect(self._on_user_config_download_error)
        thread.start()
        self._user_config_thread = thread
        self._user_config_worker = worker
        self.user_config_path_label.setText("Downloading…")
        self.download_config_btn.setEnabled(False)

    @Slot(str)
    def _on_user_config_downloaded(self, path: str) -> None:
        self._cleanup_user_config_worker()
        self._user_config_path = path
        self.user_config_path_label.setText(path)
        self.status_bar.showMessage("user_config.yaml downloaded", 5000)
        self._update_user_config_button_state()

    @Slot(str)
    def _on_user_config_download_error(self, message: str) -> None:
        self._cleanup_user_config_worker()
        self._user_config_path = None
        self.user_config_path_label.setText("Download failed")
        QMessageBox.warning(self, "BagFetcher", f"Failed to download user_config.yaml: {message}")
        self._update_user_config_button_state()

    def _cleanup_user_config_worker(self) -> None:
        thread = self._user_config_thread
        worker = self._user_config_worker
        if thread:
            thread.quit()
            thread.wait()
        if worker:
            worker.deleteLater()
        self._user_config_thread = None
        self._user_config_worker = None

    def _update_user_config_button_state(self) -> None:
        enabled = bool(self._ssh and self._robot_info and not self._user_config_thread)
        self.download_config_btn.setEnabled(enabled)
        has_path = bool(self._user_config_path and os.path.exists(self._user_config_path))
        self.user_config_open_btn.setEnabled(has_path)
        self.user_config_reveal_btn.setEnabled(has_path)

    def closeEvent(self, event):  # type: ignore[override]
        try:
            self._cleanup_user_config_worker()
            if self._ssh:
                self._ssh.close()
        finally:
            super().closeEvent(event)

    # endregion -------------------------------------------------------
