"""Application bootstrap for BagFetcher."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .core import logging_cfg
from .ui.main_window import MainWindow


def main() -> int:
    """Entry point used by both `python -m bagfetcher` and PyInstaller."""
    logging_cfg.configure()

    app = QApplication(sys.argv)
    app.setApplicationName("BagFetcher")
    app.setOrganizationName("BagFetcher")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
