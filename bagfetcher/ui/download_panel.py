"""Download panel for BagFetcher."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bagfetcher.core.models import BagFile


class DownloadPanel(QWidget):
    destination_changed = Signal(Path)
    download_requested = Signal(dict)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._progress_widgets: dict[str, QProgressBar] = {}
        self._status_items: dict[str, QTableWidgetItem] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        group = QGroupBox("Destination")
        grid = QGridLayout(group)

        self.dest_label = QLabel("–")
        self.dest_edit = QLineEdit()
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        self.cleanup_chk = QCheckBox("Cleanup staged files after download")
        self.cleanup_chk.setChecked(True)

        grid.addWidget(QLabel("Suggested"), 0, 0)
        grid.addWidget(self.dest_label, 0, 1, 1, 2)
        grid.addWidget(QLabel("Directory"), 1, 0)
        grid.addWidget(self.dest_edit, 1, 1)
        grid.addWidget(browse, 1, 2)
        grid.addWidget(self.cleanup_chk, 2, 0, 1, 3)

        root.addWidget(group)

        btns = QHBoxLayout()
        self.download_btn = QPushButton("Stage & Download")
        self.download_btn.clicked.connect(self._emit_download)
        btns.addWidget(self.download_btn)
        btns.addStretch()
        root.addLayout(btns)

        progress_box = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_box)
        self.progress_table = QTableWidget(0, 3)
        self.progress_table.setHorizontalHeaderLabels(["File", "Progress", "Status"])
        self.progress_table.horizontalHeader().setStretchLastSection(True)
        self.progress_table.verticalHeader().setVisible(False)
        self.progress_table.setEditTriggers(QTableWidget.NoEditTriggers)
        progress_layout.addWidget(self.progress_table)
        root.addWidget(progress_box)

        root.addStretch()

    # ------------------------------------------------------------------
    def set_suggestion(self, host: str) -> None:
        host = host or "remote-host"
        today = datetime.now().strftime("%Y-%m-%d")
        path = Path.home() / "RobotBags" / host / today
        self.dest_label.setText(str(path))
        if not self.dest_edit.text():
            self.dest_edit.setText(str(path))

    def _browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Choose download folder",
            self.dest_edit.text() or self.dest_label.text() or str(Path.home()),
        )
        if directory:
            self.dest_edit.setText(directory)
            self.destination_changed.emit(Path(directory))

    def _emit_download(self) -> None:
        directory = Path(self.dest_edit.text() or self.dest_label.text())
        if not directory:
            QMessageBox.warning(self, "BagFetcher", "Please choose a destination directory first.")
            return
        directory.mkdir(parents=True, exist_ok=True)
        self.download_requested.emit(
            {
                "directory": directory,
                "cleanup": self.cleanup_chk.isChecked(),
            }
        )

    # Progress helpers -------------------------------------------------
    def prepare_progress(self, bags: list[BagFile]) -> None:
        self.progress_table.setRowCount(0)
        self._progress_widgets.clear()
        self._status_items.clear()
        for bag in bags:
            row = self.progress_table.rowCount()
            self.progress_table.insertRow(row)
            self.progress_table.setItem(row, 0, QTableWidgetItem(bag.name))
            bar = QProgressBar()
            bar.setRange(0, bag.size or 1)
            bar.setValue(0)
            self.progress_table.setCellWidget(row, 1, bar)
            status = QTableWidgetItem("Pending")
            self.progress_table.setItem(row, 2, status)
            self._progress_widgets[bag.name] = bar
            self._status_items[bag.name] = status

    def set_busy(self, busy: bool) -> None:
        self.download_btn.setEnabled(not busy)

    def update_progress(self, name: str, transferred: int, total: int) -> None:
        bar = self._progress_widgets.get(name)
        if not bar:
            return
        bar.setMaximum(total or 1)
        bar.setValue(min(transferred, total or 1))

    def update_status(self, name: str, text: str) -> None:
        item = self._status_items.get(name)
        if item:
            item.setText(text)

    def mark_all_complete(self) -> None:
        for item in self._status_items.values():
            if item.text() != "Completed":
                item.setText("Completed")
