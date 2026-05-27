"""Command-Line Widget unten in der App (MA-/Avolites-Style)."""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QLineEdit, QLabel)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent

from src.core.cmdline.parser import execute as cmd_execute
from src.core.cmdline.lexer import KEYWORDS as _CMD_KEYWORDS
from src.core.app_state import get_state


# Verben, die als Befehl am Anfang stehen. Werden fuer Tab-Completion verwendet.
_VERBS = {
    "clear", "cl", "all",
    "go", "back", "stop",
    "blackout", "bo",
    "highlight", "hi", "lowlight", "lo",
    "page", "next", "prev",
    "record", "cue", "scene",
    "thru", "at", "full", "off", "ff",
    "intensity", "dim",
    "red", "green", "blue", "white",
    "pan", "tilt", "zoom", "focus", "strobe", "shutter",
} | set(_CMD_KEYWORDS)


class _CmdEdit(QLineEdit):
    """QLineEdit mit History (Up/Down) und Tab-Completion fuer Verben."""
    submitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: list[str] = []
        self._history_idx: int = 0

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        # History zurueck
        if key == Qt.Key.Key_Up:
            if self._history and self._history_idx > 0:
                self._history_idx -= 1
                self.setText(self._history[self._history_idx])
            event.accept()
            return
        # History vor
        if key == Qt.Key.Key_Down:
            if self._history_idx < len(self._history) - 1:
                self._history_idx += 1
                self.setText(self._history[self._history_idx])
            else:
                self.clear()
                self._history_idx = len(self._history)
            event.accept()
            return
        # Enter — abschicken
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            text = self.text().strip()
            if text:
                # Duplikat-Verhalten: hintereinander gleicher Befehl nur einmal
                if not self._history or self._history[-1] != text:
                    self._history.append(text)
                self._history_idx = len(self._history)
                self.submitted.emit(text)
                self.clear()
            event.accept()
            return
        # Tab — Verb-Completion
        if key == Qt.Key.Key_Tab:
            self._complete_current_word()
            event.accept()
            return
        super().keyPressEvent(event)

    def _complete_current_word(self):
        text = self.text()
        cursor = self.cursorPosition()
        # Trenne in vorderen Teil + aktuelles Wort
        left = text[:cursor]
        right = text[cursor:]
        # Letztes Wort im linken Teil
        i = len(left)
        while i > 0 and not left[i - 1].isspace():
            i -= 1
        word = left[i:].lower()
        if not word:
            return
        # Match suchen
        candidates = sorted(k for k in _VERBS if k.startswith(word))
        if not candidates:
            return
        chosen = candidates[0]
        new_left = left[:i] + chosen
        self.setText(new_left + right)
        self.setCursorPosition(len(new_left))


class CommandLine(QWidget):
    """Command-Line am unteren Rand der App."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setStyleSheet("background:#1a1a1a;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(6)

        prompt = QLabel(">")
        prompt.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:14px;font-family:Consolas;"
        )
        layout.addWidget(prompt)

        self._edit = _CmdEdit()
        self._edit.setPlaceholderText(
            "Befehl: '1 thru 5 @ 80'  'all @ full'  'go 1'  "
            "'record cue 2'  'page +'  'clear'   (Tab = vervollst., Pfeile = History)"
        )
        font = QFont("Consolas", 10)
        self._edit.setFont(font)
        self._edit.setStyleSheet(
            "color:#fff;background:#000;border:1px solid #444;padding:2px 6px;"
        )
        self._edit.submitted.connect(self._execute)
        layout.addWidget(self._edit, 1)

        self._status = QLabel("")
        self._status.setStyleSheet("color:#999;padding:0 8px;font-family:Consolas;")
        self._status.setMinimumWidth(320)
        layout.addWidget(self._status)

    def _execute(self, text: str):
        try:
            state = get_state()
            result = cmd_execute(text, state)
        except Exception as e:
            self._set_status(False, f"Fehler: {e}")
            return
        ok = bool(getattr(result, "ok", False))
        msg = str(getattr(result, "message", "?"))
        self._set_status(ok, msg)

    def _set_status(self, ok: bool, msg: str):
        color = "#9dff52" if ok else "#ff5555"
        self._status.setText(msg)
        self._status.setStyleSheet(
            f"color:{color};padding:0 8px;font-family:Consolas;"
        )

    def focus_input(self):
        self._edit.setFocus()
        self._edit.selectAll()
