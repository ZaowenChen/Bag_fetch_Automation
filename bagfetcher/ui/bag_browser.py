"""Bag browser panel."""
from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QTime, Qt, Signal
from PySide6.QtWidgets import (
    QCalendarWidget,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from bagfetcher.core.models import BagFile


class BagBrowser(QWidget):
    selection_changed = Signal(list)
    filter_changed = Signal(datetime, datetime)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._bags: list[BagFile] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox("Step 2 – Time & Bag selection")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        top_row = QHBoxLayout()
        self.calendar = QCalendarWidget()
        self.calendar.selectionChanged.connect(self.emit_filter)
        self.calendar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        top_row.addWidget(self.calendar, 1)

        controls = QVBoxLayout()
        controls.setSpacing(6)

        start_row = QHBoxLayout()
        start_row.addWidget(QLabel("Start:"))
        self.start_time = QTimeEdit()
        self.start_time.setDisplayFormat("HH:mm")
        self.start_time.setTimeRange(QTime(0, 0), QTime(23, 59))
        self.start_time.timeChanged.connect(self.emit_filter)
        start_row.addWidget(self.start_time)
        controls.addLayout(start_row)

        end_row = QHBoxLayout()
        end_row.addWidget(QLabel("End:"))
        self.end_time = QTimeEdit()
        self.end_time.setDisplayFormat("HH:mm")
        self.end_time.setTimeRange(QTime(0, 0), QTime(23, 59))
        self.end_time.timeChanged.connect(self.emit_filter)
        end_row.addWidget(self.end_time)
        controls.addLayout(end_row)

        quick_row = QHBoxLayout()
        for label, delta in [
            ("Last 30m", timedelta(minutes=30)),
            ("Last 2h", timedelta(hours=2)),
            ("Today", None),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, d=delta: self.apply_quick_filter(d))
            quick_row.addWidget(btn)
        controls.addLayout(quick_row)

        self.match_label = QLabel("Showing 0 matching files")
        controls.addWidget(self.match_label)
        controls.addStretch()
        top_row.addLayout(controls, 1)

        layout.addLayout(top_row)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "Timestamp", "Size (MB)"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.itemSelectionChanged.connect(self._emit_selection)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        self.table.setMinimumHeight(320)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.table, 1)

        root.addWidget(group)

    def apply_quick_filter(self, delta: timedelta | None) -> None:
        if delta is None:
            today = datetime.now()
            self.calendar.setSelectedDate(QDate(today.year, today.month, today.day))
            self.start_time.setTime(QTime(0, 0))
            self.end_time.setTime(QTime(23, 59))
        else:
            end = datetime.now()
            start = end - delta
            self.calendar.setSelectedDate(QDate(start.year, start.month, start.day))
            self.start_time.setTime(QTime(start.hour, start.minute))
            self.end_time.setTime(QTime(end.hour, end.minute))
        self.emit_filter()

    def emit_filter(self) -> None:
        date = self.calendar.selectedDate()
        start_dt = datetime(
            date.year(), date.month(), date.day(), self.start_time.time().hour(), self.start_time.time().minute()
        )
        end_dt = datetime(
            date.year(), date.month(), date.day(), self.end_time.time().hour(), self.end_time.time().minute()
        )
        self.filter_changed.emit(start_dt, end_dt)
        self.populate_table(self._bags)

    def set_bags(self, bags: list[BagFile]) -> None:
        self._bags = sorted(bags, key=lambda bag: bag.dt, reverse=True)
        if self._bags:
            latest = self._bags[0]
            self.calendar.setSelectedDate(QDate(latest.dt.year, latest.dt.month, latest.dt.day))
            self.start_time.setTime(QTime(0, 0))
            self.end_time.setTime(QTime(23, 59))
        self.populate_table(self._bags)

    def populate_table(self, bags: list[BagFile]) -> None:
        self.table.setRowCount(0)
        date = self.calendar.selectedDate()
        start_time = self.start_time.time()
        end_time = self.end_time.time()
        start_dt = datetime(date.year(), date.month(), date.day(), start_time.hour(), start_time.minute())
        end_dt = datetime(date.year(), date.month(), date.day(), end_time.hour(), end_time.minute())
        filtered = [bag for bag in bags if start_dt <= bag.dt <= end_dt]
        for bag in filtered:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(bag.name))
            self.table.setItem(row, 1, QTableWidgetItem(bag.dt.strftime("%Y-%m-%d %H:%M:%S")))
            self.table.setItem(row, 2, QTableWidgetItem(f"{bag.size / (1024*1024):.1f}"))
            self.table.item(row, 0).setData(Qt.UserRole, bag)
        self.match_label.setText(f"Showing {len(filtered)} matching file(s)")

    def _emit_selection(self) -> None:
        self.selection_changed.emit(self.selected_bags())

    def selected_bags(self) -> list[BagFile]:
        model = self.table.selectionModel()
        if not model:
            return []
        bags: list[BagFile] = []
        for index in model.selectedRows():
            item = self.table.item(index.row(), 0)
            bag = item.data(Qt.UserRole) if item else None
            if bag:
                bags.append(bag)
        return bags
