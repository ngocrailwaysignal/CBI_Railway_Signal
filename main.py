"""Application entrypoint."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from generic_application import GenericApplicationProfile
from ui.main_window import MainWindow


def main() -> int:
    """Run the PyQt6 application."""
    app = QApplication(sys.argv)
    profile = GenericApplicationProfile(name="CBI Simulation")
    window = MainWindow(application_profile=profile)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

