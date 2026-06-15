"""LightOS - Einstiegspunkt."""
import sys
import os
import argparse
import faulthandler
import datetime

# pythonw.exe (Start ohne Konsolenfenster) liefert kein stdout/stderr -> print()
# wuerde dann crashen. Ausgaben in diesem Fall in eine Logdatei umleiten.
if sys.stdout is None or sys.stderr is None:
    try:
        _ld = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS")
        os.makedirs(_ld, exist_ok=True)
        _lf = open(os.path.join(_ld, "lightos.log"), "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = _lf
        if sys.stderr is None:
            sys.stderr = _lf
    except Exception:
        import io
        if sys.stdout is None:
            sys.stdout = io.StringIO()
        if sys.stderr is None:
            sys.stderr = io.StringIO()

sys.path.insert(0, os.path.dirname(__file__))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from src.ui.main_window import MainWindow


_crash_log_handle = None
_crash_log_path = None        # F-9: Pfad fuer den Crash-Report-Dialog
_crash_reporter = None        # F-9: haelt die Referenz (sonst raeumt GC ihn weg)


def _setup_crash_logging():
    """Schreibt native Crashes (faulthandler) + ungefangene Python-Fehler in eine
    Logdatei (%APPDATA%/LightOS/crash.log).

    Hintergrund: MIDI-bezogene Abstuerze waren teils native Crashes ohne Python-
    Traceback (leere err.txt). faulthandler dumpt den C-Stack, sodass solche
    Faelle kuenftig nachvollziehbar sind.
    """
    global _crash_log_handle, _crash_log_path
    try:
        log_dir = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS"
        )
        os.makedirs(log_dir, exist_ok=True)
        _crash_log_path = os.path.join(log_dir, "crash.log")
        _crash_log_handle = open(
            _crash_log_path, "a", encoding="utf-8", buffering=1
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


def _install_crash_dialog():
    """F-9: Haengt einen nutzersichtbaren Fehler-Dialog an sys.excepthook an.
    Wird NACH der QApplication aufgerufen. Der vorhandene Hook (crash.log) bleibt
    erhalten — der Dialog kommt zusaetzlich obendrauf."""
    global _crash_reporter
    try:
        from src.ui.widgets.crash_dialog import CrashReporter
        _crash_reporter = CrashReporter(_crash_log_path or "")
        prev_hook = sys.excepthook

        def _hook(exc_type, exc_value, exc_tb):
            try:
                prev_hook(exc_type, exc_value, exc_tb)   # crash.log + Default
            finally:
                try:
                    _crash_reporter.report(exc_type, exc_value, exc_tb)
                except Exception:
                    pass

        sys.excepthook = _hook
    except Exception as e:
        print(f"[main] crash dialog setup error: {e}")


_watchdog_timer = None  # Referenz halten, sonst raeumt Qt den Timer weg


def _start_freeze_watchdog():
    """Erkennt UI-Freezes und dumpt dann die Stacks ALLER Threads in crash.log.

    Hintergrund: Ein eingefrorenes UI (Event-Loop verarbeitet nichts mehr,
    Fenster "Keine Rueckmeldung") hinterlaesst KEINEN crash.log-Eintrag —
    faulthandler greift nur bei harten Crashes. Der Watchdog macht Freezes
    diagnostizierbar: Ein 1-s-QTimer im UI-Thread setzt einen Herzschlag;
    bleibt er >10 s aus, schreibt ein Daemon-Thread einen kompletten
    Thread-Dump (einmal pro Freeze-Episode).
    """
    global _watchdog_timer
    import threading
    import time
    import faulthandler
    from PySide6.QtCore import QTimer

    beat = {"t": time.monotonic()}
    _watchdog_timer = QTimer()
    _watchdog_timer.setInterval(1000)
    _watchdog_timer.timeout.connect(
        lambda: beat.__setitem__("t", time.monotonic()))
    _watchdog_timer.start()

    def _watch():
        dumped = False
        while True:
            time.sleep(2.0)
            stall = time.monotonic() - beat["t"]
            if stall > 10.0:
                if not dumped:
                    dumped = True
                    try:
                        fh = _crash_log_handle
                        if fh is not None:
                            ts = datetime.datetime.now().isoformat(timespec="seconds")
                            fh.write(f"\n=== UI-FREEZE erkannt {ts} "
                                     f"({stall:.0f}s ohne Event-Loop) — "
                                     f"Stacks aller Threads: ===\n")
                            faulthandler.dump_traceback(file=fh)
                            fh.flush()
                    except Exception:
                        pass
            else:
                dumped = False

    threading.Thread(target=_watch, name="FreezeWatchdog", daemon=True).start()


def main():
    _setup_crash_logging()

    parser = argparse.ArgumentParser(description="LightOS DMX Lichtsteuerung")
    parser.add_argument("--kiosk", action="store_true",
                        help="Kiosk-Modus: Vollbild, nur Virtual Console, keine Bearbeitung")
    parser.add_argument("--touch", action="store_true",
                        help="Touch-Modus: groessere Buttons fuer Tablet-Bedienung")
    args = parser.parse_args()

    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    # Eigene AppUserModelID -> Windows zeigt in der Taskleiste das LightOS-Icon
    # (statt des generischen Python-Icons) und gruppiert die Fenster korrekt.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LightOS.DMX.Control.1")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("LightOS")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("LightOS")

    # F-9: nutzersichtbarer Crash-Report-Dialog (nach der QApplication, da er
    # QMessageBox nutzt). Ergaenzt das stille crash.log-Logging.
    _install_crash_dialog()

    # App-/Fenster-Icon (assets/icons/lightos.png, .ico fuer den Installer-Shortcut)
    try:
        from PySide6.QtGui import QIcon
        _icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "assets", "icons", "lightos.png")
        if os.path.exists(_icon_path):
            app.setWindowIcon(QIcon(_icon_path))
    except Exception as _e:
        print(f"[main] Icon konnte nicht gesetzt werden: {_e}")

    window = MainWindow(kiosk=args.kiosk, touch=args.touch)
    _start_freeze_watchdog()
    if args.kiosk:
        window.showFullScreen()
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
