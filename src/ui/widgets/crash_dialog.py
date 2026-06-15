"""F-9: Crash-Report-Dialog.

Bei einem ungefangenen Fehler zeigt LightOS jetzt einen Dialog mit Kurzmeldung,
Traceback und einem Auszug aus crash.log — statt nur still in die Logdatei zu
schreiben. Worker-Thread-Fehler werden via Signal in den GUI-Thread marshallt
(QMessageBox darf nur im GUI-Thread laufen); ein bereits offener Dialog blockt
weitere, damit ein Fehler-Sturm nicht den Bildschirm zuspammt.

Die Formatierung (`format_crash`/`read_log_tail`) ist reine Logik und ohne Qt-
Dialog testbar.
"""
from __future__ import annotations
import os
import traceback

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QMessageBox, QApplication


def read_log_tail(path: str, max_lines: int = 30) -> str:
    """Letzte ``max_lines`` Zeilen einer Logdatei (leer bei Fehler/kein Pfad)."""
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-max_lines:]).strip()
    except Exception:
        return ""


def format_crash(exc_type, exc_value, exc_tb, log_path: str = "") -> tuple[str, str]:
    """(Kurztitel, Detailtext) fuer einen ungefangenen Fehler.

    Titel = ``Fehlertyp: Meldung``; Details = vollstaendiger Traceback + (falls
    vorhanden und nicht ohnehin enthalten) ein Auszug aus crash.log + Log-Pfad.
    """
    name = getattr(exc_type, "__name__", str(exc_type))
    title = f"{name}: {exc_value}"
    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb)).strip()
    details = tb
    tail = read_log_tail(log_path)
    if tail and tail not in tb:
        details += "\n\n--- crash.log (Auszug) ---\n" + tail
    if log_path:
        details += f"\n\nVollständiges Log: {log_path}"
    return title, details


class CrashReporter(QObject):
    """Zeigt ungefangene Fehler als Dialog (thread-sicher per QueuedConnection)."""

    _report = Signal(str, str)   # (titel, details)

    def __init__(self, log_path: str = "", parent=None):
        super().__init__(parent)
        self._log_path = log_path
        self._open = False
        # Queued -> der Slot laeuft IMMER im GUI-(Owner-)Thread, auch wenn report()
        # aus einem Worker-Thread (MIDI/OSC/Audio) heraus aufgerufen wird.
        self._report.connect(self._show, Qt.ConnectionType.QueuedConnection)

    def report(self, exc_type, exc_value, exc_tb) -> None:
        """Aus dem (beliebigen) Thread aufrufbar — formatiert und marshallt."""
        try:
            title, details = format_crash(exc_type, exc_value, exc_tb, self._log_path)
            self._report.emit(title, details)
        except Exception:
            pass

    def _show(self, title: str, details: str) -> None:
        if self._open or QApplication.instance() is None:
            return
        self._open = True
        try:
            box = QMessageBox()
            box.setIcon(QMessageBox.Icon.Critical)
            box.setWindowTitle("LightOS — Unerwarteter Fehler")
            box.setText(
                "Ein unerwarteter Fehler ist aufgetreten.\n"
                "LightOS versucht weiterzulaufen — sichere zur Sicherheit deine Show."
            )
            box.setInformativeText(title)
            box.setDetailedText(details)
            open_btn = box.addButton("Log-Ordner öffnen",
                                     QMessageBox.ButtonRole.ActionRole)
            copy_btn = box.addButton("Details kopieren",
                                     QMessageBox.ButtonRole.ActionRole)
            box.addButton("Schließen", QMessageBox.ButtonRole.AcceptRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is open_btn:
                self._open_log_folder()
            elif clicked is copy_btn:
                cb = QApplication.clipboard()
                if cb is not None:
                    cb.setText(details)
        except Exception:
            pass
        finally:
            self._open = False

    def _open_log_folder(self) -> None:
        try:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            folder = os.path.dirname(self._log_path) or "."
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        except Exception:
            pass
