"""Connection panel UI controls."""
from __future__ import annotations

from dataclasses import asdict

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from bagfetcher.core.models import Profile
from bagfetcher.core.parser import ParseError, PasteResult, parse_paste


class ConnectPanel(QWidget):
    parsed = Signal(dict)
    connect_requested = Signal(dict)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._build_ui()

    # region UI setup --------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        self.paste = QTextEdit()
        self.paste.setPlaceholderText("Paste ssh block here...\nssh user@host -p 1234\npassword")
        root.addWidget(self.paste)

        parse_btn = QPushButton("Parse")
        parse_btn.clicked.connect(self.parse_block)
        root.addWidget(parse_btn)

        form_box = QGroupBox("Connection Details")
        form_layout = QFormLayout(form_box)

        self.user_edit = QLineEdit("gaussian")
        self.host_edit = QLineEdit()
        self.port_edit = QLineEdit("22")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.bag_dir_edit = QLineEdit("/root/GAUSSIAN_RUNTIME_DIR/bag")
        self.stage_dir_edit = QLineEdit("/root/public/tmp")

        form_layout.addRow("User", self.user_edit)
        form_layout.addRow("Host", self.host_edit)
        form_layout.addRow("Port", self.port_edit)
        form_layout.addRow("Password", self.password_edit)
        form_layout.addRow("Bag Dir", self.bag_dir_edit)
        form_layout.addRow("Stage Dir", self.stage_dir_edit)

        root.addWidget(form_box)

        btn_row = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._emit_connect)
        btn_row.addWidget(self.connect_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

    # endregion -------------------------------------------------------

    def parse_block(self) -> None:
        try:
            result = parse_paste(self.paste.toPlainText())
        except ParseError as exc:
            self._show_error(str(exc))
            return
        self.user_edit.setText(result.user)
        self.host_edit.setText(result.host)
        self.port_edit.setText(str(result.port))
        self.password_edit.setText(result.password)
        self.parsed.emit(asdict(result))

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "BagFetcher", message)

    def _emit_connect(self) -> None:
        payload = {
            "user": self.user_edit.text().strip() or "gaussian",
            "host": self.host_edit.text().strip(),
            "port": int(self.port_edit.text() or "22"),
            "password": self.password_edit.text(),
            "bag_dir": self.bag_dir_edit.text().strip(),
            "stage_dir": self.stage_dir_edit.text().strip(),
        }
        if not payload["host"]:
            self._show_error("Host is required before connecting.")
            return
        self.connect_requested.emit(payload)

    def load_profile(self, profile: Profile) -> None:
        self.user_edit.setText(profile.user)
        self.host_edit.setText(profile.host)
        self.port_edit.setText(str(profile.port))
        self.bag_dir_edit.setText(profile.bag_dir)
        self.stage_dir_edit.setText(profile.stage_dir)

    def to_profile(self, name: str) -> Profile:
        return Profile(
            name=name,
            user=self.user_edit.text().strip() or "gaussian",
            host=self.host_edit.text().strip(),
            port=int(self.port_edit.text() or "22"),
            bag_dir=self.bag_dir_edit.text().strip(),
            stage_dir=self.stage_dir_edit.text().strip(),
        )
