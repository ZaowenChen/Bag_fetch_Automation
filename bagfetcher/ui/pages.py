"""Page widgets for the BagFetcher application."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QSplitter,
)

from bagfetcher.core.robot_info import RobotInfo
from bagfetcher.ui.bag_browser import BagBrowser
from bagfetcher.ui.connect_panel import ConnectPanel
from bagfetcher.ui.download_panel import DownloadPanel


class PageWidget(QWidget):
    """Base class for page widgets with navigation signals."""

    back_requested = Signal()


class ConnectionPage(PageWidget):
    """Page for establishing a new connection."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        self.connect_panel = ConnectPanel()
        layout.addWidget(self.connect_panel)


class DashboardPage(PageWidget):
    """Dashboard shown after connecting to a robot."""

    bag_download_requested = Signal()
    param_restore_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignCenter)

        self.robot_info_panel = self._build_robot_info_panel()
        layout.addWidget(self.robot_info_panel)

        # App function buttons
        functions_layout = QGridLayout()
        self.bag_download_btn = QPushButton("Download Bagfile")
        self.bag_download_btn.clicked.connect(self.bag_download_requested)
        functions_layout.addWidget(self.bag_download_btn, 0, 0)

        self.param_restore_btn = QPushButton("Parameter Restore")
        self.param_restore_btn.clicked.connect(self.param_restore_requested)
        functions_layout.addWidget(self.param_restore_btn, 0, 1)

        layout.addLayout(functions_layout)
        layout.addStretch()

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
            grid.addWidget(value, row, 1)

        grid.setColumnStretch(1, 1)
        return box

    def update_info(self, robot_info: RobotInfo | None) -> None:
        info = robot_info or RobotInfo()
        self.robot_info_sn_label.setText(info.product_id or info.sn or "Unknown")
        self.robot_info_model_label.setText(info.model_type or "Unknown")
        self.robot_info_model_number_label.setText(info.model_number or "Unknown")
        self.robot_info_sw_label.setText(info.upper_pc_version or "Unknown")


class BagDownloadPage(PageWidget):
    """Page for browsing and downloading bag files."""

    def __init__(self, bag_browser: BagBrowser, download_panel: DownloadPanel, parent: QWidget | None = None):
        super().__init__(parent)
        self.bag_browser = bag_browser
        self.download_panel = download_panel
        
        layout = QVBoxLayout(self)
        
        back_btn = QPushButton("Back to Dashboard")
        back_btn.clicked.connect(self.back_requested)
        nav_layout = QHBoxLayout()
        nav_layout.addWidget(back_btn)
        nav_layout.addStretch()
        layout.addLayout(nav_layout)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.bag_browser)
        splitter.addWidget(self.download_panel)
        splitter.setSizes([700, 300])
        
        layout.addWidget(splitter)


class ParameterRestorePage(PageWidget):
    """Page for downloading and updating user_config.yaml."""

    download_config_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        back_btn = QPushButton("Back to Dashboard")
        back_btn.clicked.connect(self.back_requested)
        nav_layout = QHBoxLayout()
        nav_layout.addWidget(back_btn)
        nav_layout.addStretch()
        layout.addLayout(nav_layout)

        self.panel = self._build_panel()
        layout.addWidget(self.panel)
        layout.addStretch()

    def _build_panel(self) -> QGroupBox:
        box = QGroupBox("User Config Restore")
        grid = QGridLayout(box)

        grid.addWidget(QLabel("User config:"), 0, 0)
        self.user_config_path_label = QLabel("Not downloaded")
        self.user_config_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        grid.addWidget(self.user_config_path_label, 0, 1)

        self.user_config_open_btn = QPushButton("Open")
        grid.addWidget(self.user_config_open_btn, 0, 2)

        self.user_config_reveal_btn = QPushButton("Reveal in Finder")
        grid.addWidget(self.user_config_reveal_btn, 0, 3)

        self.download_config_btn = QPushButton("Download user_config (1)")
        self.download_config_btn.clicked.connect(self.download_config_requested)
        grid.addWidget(self.download_config_btn, 1, 0, 1, 4)

        grid.setColumnStretch(1, 1)
        return box

    def set_path(self, path: str | None) -> None:
        self.user_config_path_label.setText(path or "Not downloaded")

    def set_buttons_enabled(self, enabled: bool) -> None:
        self.download_config_btn.setEnabled(enabled)

    def set_file_actions_enabled(self, enabled: bool) -> None:
        self.user_config_open_btn.setEnabled(enabled)
        self.user_config_reveal_btn.setEnabled(enabled)
