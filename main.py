"""LightOS - Einstiegspunkt."""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(__file__))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from src.ui.main_window import MainWindow
from src.ui import touch_keyboard


def main():
    parser = argparse.ArgumentParser(description="LightOS DMX Lichtsteuerung")
    parser.add_argument("--kiosk", action="store_true",
                        help="Kiosk-Modus: Vollbild, nur Virtual Console, keine Bearbeitung")
    parser.add_argument("--touch", action="store_true",
                        help="Touch-Modus: groessere Buttons fuer Tablet-Bedienung")
    parser.add_argument("--no-touch", action="store_true",
                        help="Touch-Modus auch bei erkanntem Touchscreen deaktivieren")
    args = parser.parse_args()

    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    app = QApplication(sys.argv)
    app.setApplicationName("LightOS")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("LightOS")

    # Touch-Erkennung: explizit erzwingen, explizit deaktivieren, oder auto
    if args.no_touch:
        touch_active = False
    elif args.touch:
        touch_active = True
    else:
        touch_active = None  # auto-erkennen

    touch_enabled = touch_keyboard.install(app, touch=touch_active)

    window = MainWindow(kiosk=args.kiosk, touch=touch_enabled or args.touch)
    if args.kiosk:
        window.showFullScreen()
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
