"""LightOS — Einstiegspunkt."""
import sys
import os

# Sicherstellen dass src/ im Python-Pfad ist
sys.path.insert(0, os.path.dirname(__file__))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from src.ui.main_window import MainWindow


def main():
    # High-DPI Support (wichtig für Snapdragon-Displays)
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    app = QApplication(sys.argv)
    app.setApplicationName("LightOS")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("LightOS")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
