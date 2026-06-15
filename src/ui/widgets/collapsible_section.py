"""Wiederverwendbarer Aufklapp-Bereich (Accordion) mit Pfeil-Kopfzeile.

Eingefuehrt fuer P8 (Position-Tool im Programmer) und P10 (Split-/Half-Color-
Bereich der Moving-Head-Farbwahl). Bewusst schlicht gehalten: Kopfzeile als
Toggle-Button mit ▸/▾-Pfeil, Inhalt wird ein-/ausgeblendet (kein Animations-
Overhead, funktioniert sauber in ScrollAreas und kleinen Fenstern).

Optional merkt sich die Sektion ihren Zustand in ui_prefs.json
(%APPDATA%/LightOS), wenn ein ``prefs_key`` uebergeben wird.
"""
from __future__ import annotations

import json
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

_PREFS_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS"
)
_PREFS_PATH = os.path.join(_PREFS_DIR, "ui_prefs.json")


def _load_section_prefs() -> dict:
    try:
        with open(_PREFS_PATH, encoding="utf-8") as f:
            return (json.load(f) or {}).get("collapsible_sections", {}) or {}
    except Exception:
        return {}


def _save_section_pref(key: str, collapsed: bool):
    try:
        os.makedirs(_PREFS_DIR, exist_ok=True)
        data = {}
        try:
            with open(_PREFS_PATH, encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            data = {}
        data.setdefault("collapsible_sections", {})[key] = bool(collapsed)
        with open(_PREFS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass  # Prefs sind nice-to-have, nie fatal


class CollapsibleSection(QWidget):
    """Kopfzeile (▸/▾ + Titel) + ein-/ausklappbarer Inhaltsbereich."""

    toggled = Signal(bool)   # True = aufgeklappt

    def __init__(self, title: str, content: QWidget,
                 collapsed: bool = True, prefs_key: str | None = None,
                 parent=None):
        super().__init__(parent)
        self._title = title
        self._content = content
        self._prefs_key = prefs_key
        if prefs_key:
            stored = _load_section_prefs().get(prefs_key)
            if isinstance(stored, bool):
                collapsed = stored

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        self._btn = QPushButton()
        self._btn.setCheckable(True)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setStyleSheet(
            "QPushButton { text-align:left; padding:4px 8px; font-weight:bold;"
            " background:#1b2028; color:#c9d1d9; border:1px solid #2d333b;"
            " border-radius:4px; }"
            "QPushButton:hover { background:#22272e; }"
            "QPushButton:checked { background:#22272e; }"
        )
        self._btn.toggled.connect(self._on_toggled)
        root.addWidget(self._btn)
        root.addWidget(self._content)

        self._btn.setChecked(not collapsed)
        self._apply(not collapsed)

    # ── API ──────────────────────────────────────────────────────────────────

    def set_expanded(self, expanded: bool):
        self._btn.setChecked(bool(expanded))

    def is_expanded(self) -> bool:
        return self._btn.isChecked()

    def content(self) -> QWidget:
        return self._content

    # ── intern ───────────────────────────────────────────────────────────────

    def _apply(self, expanded: bool):
        self._content.setVisible(expanded)
        arrow = "▾" if expanded else "▸"
        self._btn.setText(f"{arrow}  {self._title}")

    def _on_toggled(self, expanded: bool):
        self._apply(expanded)
        if self._prefs_key:
            _save_section_pref(self._prefs_key, collapsed=not expanded)
        self.toggled.emit(expanded)
