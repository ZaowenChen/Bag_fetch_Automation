"""Main window composition for BagFetcher."""
from __future__ import annotations

import logging

from pathlib import Path

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from bagfetcher.core.models import BagFile
from bagfetcher.ui.bag_browser import BagBrowser
from bagfetcher.ui.connect_panel import ConnectPanel
from bagfetcher.ui.download_panel import DownloadPanel
from bagfetcher.ui.workers import ConnectWorker, DownloadWorker

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BagFetcher")
        self.resize(1200, 800)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        splitter = QSplitter()
        layout.addWidget(splitter)

        self.connect_panel = ConnectPanel()
        splitter.addWidget(self.connect_panel)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.bag_browser = BagBrowser()
        self.download_panel = DownloadPanel()
        right_layout.addWidget(self.bag_browser, 4)
        right_layout.addWidget(self.download_panel, 1)
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

    # region slots -----------------------------------------------------
    def handle_connect(self, payload: dict) -> None:
        if self._connect_thread:
            QMessageBox.information(self, "BagFetcher", "Already connecting. Please wait.")
            return
        self.status_bar.showMessage("Connecting…")
        self.connect_panel.setEnabled(False)
        worker = ConnectWorker(payload)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_connected)
        worker.error.connect(self._on_connect_error)
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
        self.download_panel.set_suggestion(worker.payload["host"])
        self.bag_browser.set_bags(bags)
        self.status_bar.showMessage(f"Connected to {worker.payload['host']} – {len(bags)} files listed", 5000)

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

    def closeEvent(self, event):  # type: ignore[override]
        try:
            if self._ssh:
                self._ssh.close()
        finally:
            super().closeEvent(event)

    # endregion -------------------------------------------------------
