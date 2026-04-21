"""Shared widgets for BagFetcher UI."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QLabel


class ClickableLabel(QLabel):
    """Clickable QLabel that emits a signal when pressed."""

    clicked = Signal()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setCursor(Qt.PointingHandCursor)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # pragma: no cover - GUI input
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


__all__ = ["ClickableLabel"]
