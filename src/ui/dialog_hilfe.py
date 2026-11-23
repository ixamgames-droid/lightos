"""STAB-41: modale Dialoge nach ``exec()`` freigeben.

Ein Dialog, der mit einem Elternfenster gebaut wird (``SomeDialog(self)``),
haengt als Kind an diesem Fenster. Nach ``exec()`` ist er nur noch versteckt —
haelt eine Signalverbindung (``lambda`` mit ``self``) oder ein anderer Verweis
das Python-Objekt fest, bleibt er samt allen Unter-Widgets bis zum Ende der
Sitzung am Hauptfenster liegen. Im Klick-Test vom 16.11.2026 stuerzte die App
beim 5./6. so geoeffneten und geschlossenen Dialog nativ ab (SIGSEGV), mit
``deleteLater()`` nach jedem Dialog nicht mehr.

Gemeinsames Muster fuer alle Stellen in ``main_window.py`` und ``views/``:

* ``ausfuehren(dlg)`` — ``exec()``, Ergebnis zurueckgeben, danach freigeben.
  Fuer Dialoge, von denen nach dem Schliessen nichts mehr gelesen wird.
* ``with offen(dlg):`` — wenn nach ``exec()`` noch Werte aus dem Dialog
  gelesen werden: im Block ``exec()`` aufrufen und lesen, freigegeben wird
  beim Verlassen des Blocks (auch bei ``return``/Ausnahme).

Freigegeben wird mit ``deleteLater()``: geloescht wird erst, wenn die
Ereignisschleife wieder dran ist — nie mitten im Aufrufer, und ein Signal,
das der Dialog beim Schliessen noch ausloest, erreicht ein lebendes Objekt.
``QMessageBox``-/``QInputDialog``-/``QFileDialog``-Statics brauchen das nicht
(Qt raeumt dort selbst auf).

Ein Waechtertest (``tests/test_stab41_dialoge_freigeben.py``) meldet neue
``exec()``-Stellen ohne diese Hilfe.
"""
from __future__ import annotations

from contextlib import contextmanager


def freigeben(dialog) -> None:
    """``deleteLater()`` — still, wenn das Objekt schon weg ist."""
    loeschen = getattr(dialog, "deleteLater", None)
    if loeschen is None:            # None oder ein Ersatzobjekt (Tests)
        return
    try:
        import shiboken6
        if not shiboken6.isValid(dialog):
            return
    except (ImportError, TypeError):
        pass                        # kein Qt-Objekt — trotzdem versuchen
    try:
        loeschen()
    except RuntimeError:
        pass


def ausfuehren(dialog) -> int:
    """``dialog.exec()`` ausfuehren, danach freigeben. Gibt das Ergebnis von
    ``exec()`` zurueck (``QDialog.DialogCode`` als ``int``)."""
    try:
        return dialog.exec()
    finally:
        freigeben(dialog)


@contextmanager
def offen(dialog):
    """``with offen(dlg): …`` — im Block ``exec()`` und Werte lesen; beim
    Verlassen (auch per ``return`` oder Ausnahme) wird der Dialog freigegeben."""
    try:
        yield dialog
    finally:
        freigeben(dialog)


# ── UI-145: Meldungen mittig ueber dem Hauptfenster ─────────────────────────

def mittig_ueber(dialog, eltern) -> bool:
    """Ein Fenster mittig ueber ``eltern.window()`` setzen (auf dessen
    Bildschirm begrenzt). Rueckgabe: ob verschoben wurde."""
    try:
        if eltern is None:
            return False
        haupt = eltern.window()
        if haupt is None or not haupt.isVisible() or haupt.isMinimized():
            return False
        rahmen = haupt.frameGeometry()
        groesse = dialog.frameGeometry().size()
        if groesse.width() <= 0 or groesse.height() <= 0:
            groesse = dialog.sizeHint()
        x = rahmen.center().x() - groesse.width() // 2
        y = rahmen.center().y() - groesse.height() // 2
        schirm = haupt.screen()
        if schirm is not None:
            frei = schirm.availableGeometry()
            x = max(frei.left(), min(x, frei.right() - groesse.width() + 1))
            y = max(frei.top(), min(y, frei.bottom() - groesse.height() + 1))
        dialog.move(x, y)
        return True
    except RuntimeError:
        return False


class _MeldungenMittig:
    """Ereignisfilter fuer die Anwendung: jede ``QMessageBox`` (Fehler,
    Warnung, Rueckfrage), die zum Hauptfenster gehoert, erscheint beim
    Zeigen mittig darueber. Im Klicktest (23.11.2026) lagen „Fehler“ und
    „Show unvollständig geladen“ am rechten Bildschirmrand ausserhalb des
    App-Fensters — Fenstermanager platzieren Dialoge nicht immer selbst."""

    def __init__(self, fenster):
        from PySide6.QtCore import QEvent, QObject, QTimer
        from PySide6.QtWidgets import QMessageBox
        from src.ui.abbau import abbau_still_filter

        hauptfenster = fenster
        zeigen = QEvent.Type.Show

        class _Filter(QObject):
            @abbau_still_filter
            def eventFilter(self, obj, ev):  # noqa: N802 (Qt-Name)
                # Laeuft fuer JEDES Ereignis der Anwendung: erst der billige
                # Typvergleich, Importe stehen oben.
                if ev.type() != zeigen or not isinstance(obj, QMessageBox):
                    return False
                try:
                    eltern = obj.parentWidget()
                    if eltern is not None and eltern.window() is hauptfenster:
                        mittig_ueber(obj, eltern)
                        # Die Box passt ihre Groesse im eigenen showEvent
                        # noch an — einmal nachziehen.
                        QTimer.singleShot(0, obj, lambda o=obj, e=eltern:
                                          mittig_ueber(o, e))
                except RuntimeError:
                    pass
                return False

        self.filter = _Filter(fenster)


def meldungen_mittig_halten(fenster):
    """UI-145: Ereignisfilter an der Anwendung installieren (Lebenszeit =
    ``fenster``). Gibt den Filter zurueck (fuer Tests)."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return None
    f = _MeldungenMittig(fenster).filter
    app.installEventFilter(f)
    return f
