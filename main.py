"""LightOS - Einstiegspunkt."""
import sys
import os
import argparse
import faulthandler
import datetime

sys.path.insert(0, os.path.dirname(__file__))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from src.ui.main_window import MainWindow


_crash_log_handle = None


def _setup_crash_logging():
    """Schreibt native Crashes (faulthandler) + ungefangene Python-Fehler in eine
    Logdatei (%APPDATA%/LightOS/crash.log).

    Hintergrund: MIDI-bezogene Abstuerze waren teils native Crashes ohne Python-
    Traceback (leere err.txt). faulthandler dumpt den C-Stack, sodass solche
    Faelle kuenftig nachvollziehbar sind.
    """
    global _crash_log_handle
    try:
        log_dir = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS"
        )
        os.makedirs(log_dir, exist_ok=True)
        _crash_log_handle = open(
            os.path.join(log_dir, "crash.log"), "a", encoding="utf-8", buffering=1
        )
        faulthandler.enable(file=_crash_log_handle)

        def _hook(exc_type, exc_value, exc_tb):
            import traceback
            ts = datetime.datetime.now().isoformat(timespec="seconds")
            _crash_log_handle.write(f"\n=== Python Exception {ts} ===\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=_crash_log_handle)
            sys.__excepthook__(exc_type, exc_value, exc_tb)

        sys.excepthook = _hook
    except Exception:
        try:
            faulthandler.enable()
        except Exception:
            pass


def main():
    _setup_crash_logging()

    parser = argparse.ArgumentParser(description="LightOS DMX Lichtsteuerung")
    parser.add_argument("--kiosk", action="store_true",
                        help="Kiosk-Modus: Vollbild, nur Virtual Console, keine Bearbeitung")
    parser.add_argument("--touch", action="store_true",
                        help="Touch-Modus: groessere Buttons fuer Tablet-Bedienung")
    args = parser.parse_args()

    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    app = QApplication(sys.argv)
    app.setApplicationName("LightOS")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("LightOS")

    window = MainWindow(kiosk=args.kiosk, touch=args.touch)
    if args.kiosk:
        window.showFullScreen()
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
