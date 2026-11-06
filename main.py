from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.database.db import initialize_database
from app.ui.main_window import MainWindow


def main() -> int:
    initialize_database()
    app = QApplication(sys.argv)
    app.setApplicationName("AURA AI")
    app.setOrganizationName("AURA")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
