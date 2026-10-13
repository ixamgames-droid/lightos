"""STAB-34: die Qt-Plattform — vorgeben (Werkzeuge) und ehrlich abfragen (App).

``QT_QPA_PLATFORM`` wird von Qt genau EINMAL gelesen: wenn die Anwendung
entsteht. Danach ist die Variable nur noch eine Zeichenkette im Prozess — sie
sagt nichts mehr darueber, worauf Qt laeuft.

Daran hing ein Datenverlust: drei Bibliotheksmodule setzten beim Import
``os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")`` (richtig fuer
Werkzeuge, die ihre Anwendung erst danach bauen). Als die Lade-Pruefung der App
eines davon nachlud (TOOL-25), stand die Variable in der LAUFENDEN, sichtbaren
App auf „offscreen“ — und das Hauptfenster las daraus „niemand sitzt davor“ und
fragte nicht mehr „Show speichern?“.

Zwei Regeln, eine Stelle:

* :func:`offscreen_fuer_werkzeuge` — die Vorgabe NUR setzen, solange noch keine
  Qt-Anwendung laeuft. Einer laufenden Anwendung wird nichts untergeschoben.
* :func:`ohne_bildschirm` — wer wissen will, ob ein modaler Dialog jemanden
  erreicht, fragt die Plattform, die Qt wirklich benutzt.

Blattmodul: importiert Qt nicht selbst (ist PySide6 noch nicht geladen, kann
auch keine Anwendung laufen).
"""
from __future__ import annotations

import os
import sys

VARIABLE = "QT_QPA_PLATFORM"
OFFSCREEN = "offscreen"


def _anwendung_laeuft() -> bool:
    """Gibt es in diesem Prozess schon eine Qt-Anwendung?"""
    qtcore = sys.modules.get("PySide6.QtCore")
    if qtcore is None:
        return False
    try:
        return qtcore.QCoreApplication.instance() is not None
    except Exception:                                    # noqa: BLE001
        return False


def _laufende_plattform() -> str:
    """Name der Plattform, auf der die laufende Qt-Anwendung zeichnet
    („windows“, „xcb“, „wayland“, „cocoa“, „offscreen“ …); leer, wenn es keine
    Anwendung mit Oberflaeche gibt."""
    qtgui = sys.modules.get("PySide6.QtGui")
    if qtgui is None or not _anwendung_laeuft():
        return ""
    try:
        return str(qtgui.QGuiApplication.platformName() or "").lower()
    except Exception:                                    # noqa: BLE001
        return ""


def offscreen_fuer_werkzeuge() -> bool:
    """„Kein Fenster noetig“ als VORGABE fuer Werkzeuge und Skripte.

    Wirkt nur, solange noch keine Qt-Anwendung laeuft, und ueberschreibt keine
    ausdrueckliche Wahl (``setdefault``). Liefert ``True``, wenn die Vorgabe
    jetzt gilt oder die Variable schon gesetzt war; ``False``, wenn eine
    laufende Anwendung in Ruhe gelassen wurde."""
    if _anwendung_laeuft():
        return False
    os.environ.setdefault(VARIABLE, OFFSCREEN)
    return True


def ohne_bildschirm() -> bool:
    """Laeuft Qt ohne Bildschirm (Testlauf, Werkzeug, CI)?

    Mit laufender Anwendung entscheidet deren Plattform — auch dann, wenn sie
    ueber die Kommandozeile (``-platform offscreen``) gewaehlt wurde oder die
    Variable inzwischen etwas anderes behauptet. Ohne Anwendung bleibt nur die
    Variable (deckt auch Varianten wie ``offscreen:size=…``)."""
    plattform = _laufende_plattform()
    if plattform:
        return plattform.startswith(OFFSCREEN)
    return os.environ.get(VARIABLE, "").lower().startswith(OFFSCREEN)
