"""Main window composition for BagFetcher."""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Slot
from PySide6.QtGui import QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from bagfetcher.core.models import BagFile
from bagfetcher.core.robot_info import RobotInfo
from bagfetcher.ui.bag_browser import BagBrowser
from bagfetcher.ui.download_panel import DownloadPanel
from bagfetcher.ui.pages import (
    BagDownloadPage,
    ConnectionPage,
    DashboardPage,
    ParameterRestorePage,
)
from bagfetcher.ui.workers import ConnectWorker, DownloadWorker, UserConfigWorker

log = logging.getLogger(__name__)

STYLESHEET = """
QWidget {
    background-color: #2e2e2e;
    color: #e0e0e0;
    font-size: 14px;
}
QMainWindow {
    background-color: #2e2e2e;
}
QGroupBox {
    font-weight: bold;
    border: 1px solid #555;
    border-radius: 8px;
    margin-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top center;
    padding: 0 10px;
}
QLabel#header_title {
    font-size: 24px;
    font-weight: bold;
    color: #ffffff;
}
QPushButton {
    background-color: #555;
    color: #fff;
    border: 1px solid #666;
    padding: 8px 16px;
    border-radius: 4px;
}
QPushButton:hover {
    background-color: #666;
}
QPushButton:pressed {
    background-color: #777;
}
QLineEdit, QPlainTextEdit, QSpinBox {
    background-color: #3c3c3c;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 5px;
}
QStatusBar {
    color: #ccc;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BagFetcher")
        icon_path = self._find_icon()
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

        self.resize(1024, 768)
        self.setStyleSheet(STYLESHEET)

        self._user_config_path: str | None = None
        self._robot_info: RobotInfo | None = None
        self._current_host: str | None = None

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Header
        header = self._build_header(icon_path)
        main_layout.addLayout(header)

        # Core widgets that are passed to pages
        self.bag_browser = BagBrowser()
        self.download_panel = DownloadPanel()

        # Pages
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        self._init_pages()
        self._init_workers()

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self._setup_connections()

        self._config_shortcut = QShortcut(QKeySequence("1"), self)
        self._config_shortcut.activated.connect(self._handle_user_config_download)

    def _find_icon(self) -> str | None:
        base_path = Path(__file__).resolve().parent.parent
        icon_path = base_path / "packaging" / "cobotiq_logo.icns"
        if icon_path.exists():
            return str(icon_path)
        return None

    def _build_header(self, icon_path: str | None) -> QHBoxLayout:
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(10, 10, 10, 20)
        if icon_path:
            pixmap = QPixmap(icon_path)
            icon_label = QLabel()
            icon_label.setPixmap(pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            header_layout.addWidget(icon_label)

        title = QLabel("BagFetcher")
        title.setObjectName("header_title")
        header_layout.addWidget(title)
        header_layout.addStretch()
        return header_layout

    def _init_pages(self) -> None:
        self.connection_page = ConnectionPage()
        self.dashboard_page = DashboardPage()
        self.bag_download_page = BagDownloadPage(self.bag_browser, self.download_panel)
        self.param_restore_page = ParameterRestorePage()

        self.stacked_widget.addWidget(self.connection_page)
        self.stacked_widget.addWidget(self.dashboard_page)
        self.stacked_widget.addWidget(self.bag_download_page)
        self.stacked_widget.addWidget(self.param_restore_page)

    def _init_workers(self) -> None:
        self._ssh = None
        self._service = None
        self._connect_thread: QThread | None = None
        self._connect_worker: ConnectWorker | None = None
        self._download_thread: QThread | None = None
        self._download_worker: DownloadWorker | None = None
        self._user_config_thread: QThread | None = None
        self._user_config_worker: UserConfigWorker | None = None

    def _setup_connections(self) -> None:
        # Connection
        self.connection_page.connect_panel.connect_requested.connect(self.handle_connect)

        # Dashboard navigation
        self.dashboard_page.bag_download_requested.connect(lambda: self.stacked_widget.setCurrentWidget(self.bag_download_page))
        self.dashboard_page.param_restore_requested.connect(lambda: self.stacked_widget.setCurrentWidget(self.param_restore_page))

        # Back navigation
        self.bag_download_page.back_requested.connect(self.show_dashboard)
        self.param_restore_page.back_requested.connect(self.show_dashboard)

        # Bag download
        self.download_panel.download_requested.connect(self.handle_download)
        self.download_panel.cancel_requested.connect(self.handle_cancel_download)
        self.bag_browser.selection_changed.connect(self._selection_changed)

        # Param restore
        self.param_restore_page.download_config_requested.connect(self._handle_user_config_download)
        self.param_restore_page.user_config_open_btn.clicked.connect(self._open_user_config_default)
        self.param_restore_page.user_config_reveal_btn.clicked.connect(self._reveal_user_config)

    def show_dashboard(self) -> None:
        self.stacked_widget.setCurrentWidget(self.dashboard_page)

    # region slots -----------------------------------------------------
    def handle_connect(self, payload: dict) -> None:
        if self._connect_thread:
            QMessageBox.information(self, "BagFetcher", "Already connecting. Please wait.")
            return
        self._current_host = payload.get("host")
        self.status_bar.showMessage("Connecting…")
        self.connection_page.connect_panel.set_connection_status("Connecting…", state="progress")
        self.connection_page.connect_panel.setEnabled(False)
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
        self.connection_page.connect_panel.setEnabled(True)
        self._ssh = ssh
        self._service = service
        host = worker.payload["host"]
        self._current_host = host
        
        self.download_panel.set_suggestion(host)
        self.bag_browser.set_bags(bags)
        
        self.status_bar.showMessage(f"Connected to {host} – {len(bags)} files listed", 5000)
        self.connection_page.connect_panel.set_connection_status(f"Connected to {host}:{worker.payload['port']}", state="connected")
        
        self.stacked_widget.setCurrentWidget(self.dashboard_page)
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
        self.connection_page.connect_panel.setEnabled(True)
        self.connection_page.connect_panel.set_connection_status("Connection failed", state="error")
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
        self._robot_info = robot_info
        self.dashboard_page.update_info(robot_info)
        self._update_user_config_button_state()

    def _open_in_finder(self, path: str) -> None:
        if not path:
            return
        if not os.path.exists(path):
            QMessageBox.warning(self, "BagFetcher", "User config file is missing locally.")
            return
        try:
            subprocess.Popen(["open", "-R", path])
        except Exception as exc:
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
        self.param_restore_page.set_path("Downloading…")
        self.param_restore_page.set_buttons_enabled(False)

    @Slot(str)
    def _on_user_config_downloaded(self, path: str) -> None:
        self._cleanup_user_config_worker()
        self._user_config_path = path
        self.param_restore_page.set_path(path)
        self.status_bar.showMessage("user_config.yaml downloaded", 5000)
        self._update_user_config_button_state()

    @Slot(str)
    def _on_user_config_download_error(self, message: str) -> None:
        self._cleanup_user_config_worker()
        self._user_config_path = None
        self.param_restore_page.set_path("Download failed")
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
        self.param_restore_page.set_buttons_enabled(enabled)
        has_path = bool(self._user_config_path and os.path.exists(self._user_config_path))
        self.param_restore_page.set_file_actions_enabled(has_path)

    def closeEvent(self, event):
        try:
            self._cleanup_user_config_worker()
            if self._ssh:
                self._ssh.close()
        finally:
            super().closeEvent(event)
    # endregion -------------------------------------------------------
