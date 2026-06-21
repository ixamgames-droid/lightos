"""App-weite Tastatur-Hotkeys für die Virtual Console (Feature: Keyboard-Patch).

Ein einziger QApplication-Event-Filter fängt KeyPress/KeyRelease ab, baut
daraus einen portablen Sequenz-String (QKeySequence, z. B. "F5", "Ctrl+B",
"Shift+Space") und verteilt ihn an Subscriber (die VC-Canvases). Die Canvases
leiten an ihre Widgets weiter — gleiche Architektur wie der MIDI-Pfad
(MidiManager → VCCanvas → widget.handle_midi).

Schutzregeln (wichtig für den Live-Betrieb):
- KEIN Auslösen, wenn der Fokus in einem Texteingabefeld liegt
  (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, editierbare
  QComboBox, QKeySequenceEdit) — normale Eingaben bleiben ungestört.
- KEIN Auslösen, solange ein modaler Dialog offen ist (z. B. der
  Tasten-Lern-Dialog selbst oder eine Sicherheitsabfrage).
- Auto-Repeat wird verschluckt (gedrückt halten feuert nicht mehrfach).
- Für Flash-Tasten wird das Release zuverlässig zugestellt: beim Press wird
  die gesendete Sequenz pro Basis-Taste gemerkt und beim Release derselben
  Taste wiederverwendet (auch wenn der Modifier zuerst losgelassen wurde).

Technische Grenzen (dokumentiert, siehe docs/KEYBOARD_MAPPING.md):
- App-intern: Hotkeys feuern nur, solange LightOS den Fokus hat (kein
  OS-globaler Hook — bewusst, um keine anderen Programme zu kapern).
- Windows liefert über Qt KEINE Geräte-Unterscheidung: eine zweite
  USB-/Makro-Tastatur sendet dieselben Key-Events wie die Haupttastatur.
  Getrennte Profile pro Tastatur bräuchten Raw-Input (WM_INPUT) über einen
  nativen Hook — als möglicher Ausbau dokumentiert, nicht implementiert.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

# Reine Modifier-Tasten erzeugen selbst keine Sequenz.
_MODIFIER_KEYS = {
    Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt,
    Qt.Key.Key_Meta, Qt.Key.Key_AltGr, Qt.Key.Key_CapsLock,
    Qt.Key.Key_NumLock, Qt.Key.Key_ScrollLock,
}


def _is_text_input(widget) -> bool:
    """True, wenn das fokussierte Widget normale Texteingabe erwartet."""
    if widget is None:
        return False
    from PySide6.QtWidgets import (QAbstractSpinBox, QComboBox, QLineEdit,
                                   QPlainTextEdit, QTextEdit)
    try:
        from PySide6.QtWidgets import QKeySequenceEdit
        if isinstance(widget, QKeySequenceEdit):
            return True
    except Exception:
        pass
    if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
        return True
    if isinstance(widget, QComboBox) and widget.isEditable():
        return True
    return False


def sequence_from_event(event) -> str | None:
    """Baut den Sequenz-String aus einem QKeyEvent ("Ctrl+F5", "B", …)."""
    key = event.key()
    if key in _MODIFIER_KEYS or key in (Qt.Key.Key_unknown, 0):
        return None
    combo = int(event.modifiers().value) | int(key)
    seq = QKeySequence(combo).toString(QKeySequence.SequenceFormat.PortableText)
    return seq or None


class KeyboardHotkeyFilter(QObject):
    """Singleton-Event-Filter; Subscriber: cb(seq: str, pressed: bool) -> bool.

    Gibt ein Subscriber True zurück, gilt der Hotkey als konsumiert und das
    Key-Event wird nicht weitergereicht (verhindert z. B. Scrollen per Space).
    """

    def __init__(self):
        super().__init__()
        self._subs: list = []
        self._installed = False
        # pro Basis-Taste die beim Press gesendete Sequenz (für das Release)
        self._active: dict[int, str] = {}

    # ── Subscriber-Verwaltung ────────────────────────────────────────────────

    def ensure_installed(self):
        if self._installed:
            return
        app = QApplication.instance()
        if app is None:
            return
        app.installEventFilter(self)
        self._installed = True

    def subscribe(self, cb):
        if cb not in self._subs:
            self._subs.append(cb)
        self.ensure_installed()

    def unsubscribe(self, cb):
        try:
            self._subs.remove(cb)
        except ValueError:
            pass

    # ── Event-Filter ─────────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        et = event.type()
        if et not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return False
        if not self._subs:
            return False
        if event.isAutoRepeat():
            # Auto-Repeat schlucken, wenn die Taste bei uns aktiv ist —
            # sonst normal durchreichen (Texteingabe etc.).
            return int(event.key()) in self._active
        app = QApplication.instance()
        if app is None:
            return False
        # Modaler Dialog offen → Hotkeys pausieren (Sicherheits-/Lern-Dialoge).
        if app.activeModalWidget() is not None:
            return False
        if _is_text_input(app.focusWidget()):
            return False

        key = int(event.key())
        if et == QEvent.Type.KeyPress:
            seq = sequence_from_event(event)
            if not seq:
                return False
            consumed = self._dispatch(seq, True)
            if consumed:
                self._active[key] = seq
            return consumed
        # KeyRelease: gemerkte Sequenz der Basis-Taste verwenden (Modifier
        # kann zu diesem Zeitpunkt schon losgelassen sein).
        seq = self._active.pop(key, None)
        if seq is None:
            return False
        self._dispatch(seq, False)
        return True

    def _dispatch(self, seq: str, pressed: bool) -> bool:
        consumed = False
        for cb in list(self._subs):
            try:
                if cb(seq, pressed):
                    consumed = True
            except Exception as e:
                print(f"[keyboard_hotkeys] subscriber error: {e}")
        return consumed


_filter: KeyboardHotkeyFilter | None = None


def get_keyboard_hotkeys() -> KeyboardHotkeyFilter:
    global _filter
    if _filter is None:
        _filter = KeyboardHotkeyFilter()
    return _filter
