"""Application entrypoint."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from config import DEFAULT_APP_CONFIG
from runtime import GenericApplicationProfile
from ui.views.main_window_view import MainWindow


def main() -> int:
    """Run the PyQt6 application."""
    app = QApplication(sys.argv)
    profile = GenericApplicationProfile(name=DEFAULT_APP_CONFIG.name)
    window = MainWindow(application_profile=profile)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
