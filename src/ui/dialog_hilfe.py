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
