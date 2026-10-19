"""UI-93: EINE Stelle fuer die Tastenfolgen von Rueckgaengig und Wiederholen.

Befund (Sichtprobe unter Linux/X11): nach Strg+Z stellte Strg+Y nichts wieder
her. Drei Ursachen kamen zusammen:

* ``QAction.setShortcut(QKeySequence.StandardKey.Redo)`` uebernimmt nur die
  ERSTE Bindung der Plattform. Unter Windows ist das Strg+Y, unter X11
  Strg+Umschalt+Z — dort war Strg+Y gar nicht gebunden.
* Die Virtual Console legte dieselben Folgen als ``QShortcut`` im
  Fenster-Kontext an. Zwei gleiche Folgen im selben Fenster sind fuer Qt
  mehrdeutig; dann feuert KEINE von beiden (Qt meldet nur
  „Ambiguous shortcut overload“).
* Der Laser-Zeicheneditor band Strg+Y zusaetzlich zu ``StandardKey.Redo`` —
  unter Windows steckt Strg+Y dort schon drin, also wieder mehrdeutig.

Deshalb gilt ueberall dieselbe feste Belegung, unabhaengig von der Plattform:

* Rueckgaengig: Strg+Z
* Wiederholen:  Strg+Y UND Strg+Umschalt+Z

Die Plattform entscheidet nur noch, welche der beiden Folgen ZUERST steht —
die erste zeigt Qt im Menue an, und sie steht in den Tooltips vorn.

Wer bekommt den Tastendruck? ``vorrang()`` regelt das im ``event()`` des
Fensters, noch bevor Qt ein Kuerzel ausloest (``ShortcutOverride``):

1. Ein beschreibbares Textfeld mit Fokus behaelt sein eigenes
   Rueckgaengig/Wiederholen. Qt macht das von sich aus nur fuer die Folgen der
   Plattform (unter X11 also nicht fuer Strg+Y) — die uebrigen reicht
   ``vorrang()`` an das Feld durch.
2. Ein lokaler Verlauf des Fensters (im Hauptfenster bei sichtbarer Virtual
   Console: der gemeinsame Verlauf aus Layout der Konsole und Bearbeiten →
   Rueckgaengig, siehe ``MainWindow.verlauf_schritt``).
3. Sonst laeuft der Tastendruck normal weiter und trifft das Kuerzel des
   Fensters (im Hauptfenster: Bearbeiten → Rueckgaengig/Wiederholen).

Das Wort heisst in der Oberflaeche ueberall „Wiederholen“ (nicht
„Wiederherstellen“ — das bleibt Sicherungen und dem Auto-Save vorbehalten).
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QComboBox, QLineEdit, QPlainTextEdit,
    QTextEdit,
)

#: Portable Qt-Namen; die Reihenfolge von REDO wird je Plattform umgestellt.
UNDO_PORTABEL = ("Ctrl+Z",)
REDO_PORTABEL = ("Ctrl+Y", "Ctrl+Shift+Z")

#: Fenster, die ``vorrang()`` mit einem lokalen Verlauf aufrufen, tragen dieses
#: Klassenattribut (``True``). Eingebettete Ansichten mit eigenen Kuerzeln
#: schalten ihre dann ab — sonst waeren die Folgen im Fenster doppelt belegt.
MERKMAL_ZENTRAL = "UNDO_KUERZEL_ZENTRAL"

_PORTABEL = QKeySequence.SequenceFormat.PortableText
_MODS = (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
         | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier)


def undo_folgen() -> list[QKeySequence]:
    """Tastenfolgen fuer Rueckgaengig (ueberall Strg+Z)."""
    return [QKeySequence(p) for p in UNDO_PORTABEL]


def redo_folgen() -> list[QKeySequence]:
    """Tastenfolgen fuer Wiederholen — IMMER beide, die der Plattform zuerst."""
    namen = list(REDO_PORTABEL)
    for bindung in QKeySequence.keyBindings(QKeySequence.StandardKey.Redo):
        p = bindung.toString(_PORTABEL)
        if p in namen:
            namen.remove(p)
            namen.insert(0, p)
            break
    return [QKeySequence(p) for p in namen]


def _text(folgen) -> str:
    from src.ui.hilfe import tasten_text
    return " oder ".join(tasten_text(f) for f in folgen)


def undo_text() -> str:
    """„Strg+Z“ — fuer Tooltips."""
    return _text(undo_folgen())


def redo_text() -> str:
    """„Strg+Umschalt+Z oder Strg+Y“ (Reihenfolge je Plattform) — fuer Tooltips."""
    return _text(redo_folgen())


def kuerzel_anlegen(eltern, rueckgaengig: Callable, wiederholen: Callable,
                    was_undo: str = "Rückgängig",
                    was_redo: str = "Wiederholen") -> tuple[QShortcut, QShortcut]:
    """Zwei ``QShortcut`` (Fenster-Kontext) mit der festen Belegung anlegen.

    Fuer eigenstaendige Fenster und Dialoge. ``was_*`` ist die Beschreibung in
    Hilfe → Tastenkürzel.
    """
    su = QShortcut(eltern)
    su.setKeys(undo_folgen())
    su.setWhatsThis(was_undo)
    su.activated.connect(rueckgaengig)
    sr = QShortcut(eltern)
    sr.setKeys(redo_folgen())
    sr.setWhatsThis(was_redo)
    sr.activated.connect(wiederholen)
    return su, sr


def kuerzel_art(ev) -> Optional[str]:
    """``"undo"``/``"redo"`` fuer ein Tastenereignis mit einer der Folgen, sonst None."""
    try:
        mods = ev.modifiers() & _MODS
        folge = QKeySequence(int(ev.key()) | int(mods.value)).toString(_PORTABEL)
    except Exception:
        return None
    if folge in UNDO_PORTABEL:
        return "undo"
    if folge in REDO_PORTABEL:
        return "redo"
    return None


def textfeld(widget):
    """Das beschreibbare Textfeld hinter ``widget`` (Fokus-Widget) oder None.

    Drehfelder und editierbare Auswahllisten liefern ihr inneres Eingabefeld.
    Schreibgeschuetzte Felder zaehlen nicht — sie haben nichts zurueckzunehmen.
    """
    w = widget
    try:
        if isinstance(w, QAbstractSpinBox):
            if w.isReadOnly():
                return None
            w = w.lineEdit()
        elif isinstance(w, QComboBox):
            w = w.lineEdit() if w.isEditable() else None
        if isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit)):
            return None if w.isReadOnly() else w
    except RuntimeError:        # C++-Objekt schon abgebaut
        return None
    return None


def vorrang(fenster, ev, lokal: Optional[Callable[[bool], bool]] = None) -> bool:
    """Im ``event()`` eines Fensters aufrufen; True = Ereignis ist erledigt.

    Greift nur bei ``ShortcutOverride`` mit einer der Undo-/Redo-Folgen.
    ``lokal(wiederholen)`` ist der lokale Verlauf des Fensters; er liefert True,
    wenn er zustaendig war (auch wenn es gerade nichts zurueckzunehmen gab).

    Ein Textfeld, das die Folge von sich aus kennt, nimmt den
    ``ShortcutOverride`` selbst an — dann kommt er hier gar nicht erst an. Wer
    hier mit Textfeld-Fokus landet, hat also ein Feld, das diese Folge NICHT
    kennt; dessen ``undo()``/``redo()`` wird deshalb direkt gerufen.
    """
    if ev.type() != QEvent.Type.ShortcutOverride:
        return False
    art = kuerzel_art(ev)
    if art is None:
        return False
    wiederholen = art == "redo"
    fokus = QApplication.focusWidget()
    feld = textfeld(fokus)
    if feld is not None and fokus is not None and fokus.window() is fenster:
        (feld.redo if wiederholen else feld.undo)()
        ev.accept()
        return True
    if lokal is not None and lokal(wiederholen):
        ev.accept()
        return True
    return False
