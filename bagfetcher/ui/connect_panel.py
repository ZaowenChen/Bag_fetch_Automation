"""Connection panel UI controls."""
from __future__ import annotations

from dataclasses import asdict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
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
        self.set_connection_status("Not connected", state="idle")

    # region UI setup --------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        step_group = QGroupBox("Step 1 – Connection")
        step_layout = QVBoxLayout(step_group)
        step_layout.setSpacing(12)

        instruction = QLabel("Paste ngrok SSH block here (from WeChat)")
        instruction.setWordWrap(True)
        step_layout.addWidget(instruction)

        self.paste = QPlainTextEdit()
        self.paste.setPlaceholderText("ssh gaussian@ngrok-xxxx.gs-robot.com -p 12345\npassword123")
        self.paste.setMinimumHeight(140)
        step_layout.addWidget(self.paste)

        parse_row = QHBoxLayout()
        parse_row.addStretch()
        self.parse_btn = QPushButton("Parse")
        self.parse_btn.clicked.connect(self.parse_block)
        parse_row.addWidget(self.parse_btn)
        step_layout.addLayout(parse_row)

        form_box = QGroupBox("Connection Details")
        form_layout = QFormLayout(form_box)
        form_layout.setLabelAlignment(Qt.AlignRight)

        self.user_edit = QLineEdit("gaussian")
        self.host_edit = QLineEdit()
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(22)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_toggle = QToolButton()
        self.password_toggle.setText("Show")
        self.password_toggle.setCheckable(True)
        self.password_toggle.toggled.connect(self._toggle_password_visibility)

        password_row = QHBoxLayout()
        password_row.setContentsMargins(0, 0, 0, 0)
        password_row.addWidget(self.password_edit)
        password_row.addWidget(self.password_toggle)
        password_widget = QWidget()
        password_widget.setLayout(password_row)

        self.bag_dir_edit = QLineEdit("/root/GAUSSIAN_RUNTIME_DIR/bag")
        self.stage_dir_edit = QLineEdit("/root/public/tmp")

        form_layout.addRow("User", self.user_edit)
        form_layout.addRow("Host", self.host_edit)
        form_layout.addRow("Port", self.port_spin)
        form_layout.addRow("Password", password_widget)

        step_layout.addWidget(form_box)

        # Advanced section -------------------------------------------------
        toggle_row = QHBoxLayout()
        toggle_row.addStretch()
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("Advanced ▾")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        toggle_row.addWidget(self.advanced_toggle)
        step_layout.addLayout(toggle_row)

        self.advanced_frame = QFrame()
        self.advanced_frame.setFrameShape(QFrame.StyledPanel)
        self.advanced_frame.setVisible(False)
        adv_layout = QFormLayout(self.advanced_frame)
        adv_layout.setLabelAlignment(Qt.AlignRight)
        adv_layout.addRow("Bag Dir", self.bag_dir_edit)
        adv_layout.addRow("Stage Dir", self.stage_dir_edit)
        step_layout.addWidget(self.advanced_frame)

        # Connect button + status ---------------------------------------
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._emit_connect)
        self.connect_btn.setMinimumHeight(36)
        step_layout.addWidget(self.connect_btn)

        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        step_layout.addWidget(self.status_label)

        step_layout.addStretch()
        root.addWidget(step_group)

    # endregion -------------------------------------------------------

    def parse_block(self) -> None:
        try:
            result = parse_paste(self.paste.toPlainText())
        except ParseError as exc:
            self._show_error(str(exc))
            return
        self.user_edit.setText(result.user)
        self.host_edit.setText(result.host)
        self.port_spin.setValue(result.port)
        self.password_edit.setText(result.password)
        self.parsed.emit(asdict(result))

    def set_connection_status(self, text: str, state: str = "idle") -> None:
        color = "#95a5a6"
        symbol = "○"
        if state == "connected":
            color = "#2ecc71"
            symbol = "●"
        elif state == "error":
            color = "#e74c3c"
            symbol = "●"
        elif state == "progress":
            color = "#f1c40f"
            symbol = "●"
        self.status_label.setText(f'<span style="color:{color};font-size:14px;">{symbol}</span> {text}')

    def _toggle_password_visibility(self, checked: bool) -> None:
        self.password_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        self.password_toggle.setText("Hide" if checked else "Show")

    def _toggle_advanced(self, checked: bool) -> None:
        self.advanced_frame.setVisible(checked)
        self.advanced_toggle.setText("Advanced ▴" if checked else "Advanced ▾")

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "BagFetcher", message)

    def _emit_connect(self) -> None:
        payload = {
            "user": self.user_edit.text().strip() or "gaussian",
            "host": self.host_edit.text().strip(),
            "port": int(self.port_spin.value()),
            "password": self.password_edit.text(),
            "bag_dir": self.bag_dir_edit.text().strip(),
            "stage_dir": self.stage_dir_edit.text().strip(),
        }
        if not payload["host"]:
            self._show_error("Host is required before connecting.")
            return
        self.connect_requested.emit(payload)

    def parse_paste_result(self, result: PasteResult) -> None:
        self.user_edit.setText(result.user)
        self.host_edit.setText(result.host)
        self.port_spin.setValue(result.port)
        self.password_edit.setText(result.password)

    def load_profile(self, profile: Profile) -> None:
        self.user_edit.setText(profile.user)
        self.host_edit.setText(profile.host)
        self.port_spin.setValue(profile.port)
        self.bag_dir_edit.setText(profile.bag_dir)
        self.stage_dir_edit.setText(profile.stage_dir)

    def to_profile(self, name: str) -> Profile:
        return Profile(
            name=name,
            user=self.user_edit.text().strip() or "gaussian",
            host=self.host_edit.text().strip(),
            port=int(self.port_spin.value()),
            bag_dir=self.bag_dir_edit.text().strip(),
            stage_dir=self.stage_dir_edit.text().strip(),
        )
