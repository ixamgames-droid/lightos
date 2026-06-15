"""Tasten-Lern-Dialog für VC-Widgets (Pendant zum MidiTeachDialog).

Der Dialog fängt den nächsten Tastendruck (inkl. Modifier wie Strg/Shift/Alt)
und zeigt ihn als portablen Sequenz-String ("Ctrl+F5"). Eine Konfliktprüfung
gegen die übrigen Widgets der Canvas warnt bei Doppelbelegung — Übernehmen
bleibt trotzdem möglich (bewusste Doppelbelegung erlaubt, z. B. Gruppen-Flash).

Sicherheits-Kennzeichnung: ist das Ziel eine kritische Aktion (Blackout /
Stop All), zeigt der Dialog einen deutlichen roten Hinweis.

Hinweis: Der globale Hotkey-Filter pausiert automatisch, solange dieser
modale Dialog offen ist (keine versehentlichen Trigger beim Lernen).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout)

from src.core.input.keyboard_hotkeys import sequence_from_event

_BTN_STYLE = """
    QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                  border-radius:4px; font-size:11px; padding:6px 14px; }
    QPushButton:hover { background:#30363d; }
    QPushButton:disabled { color:#555d68; }
"""

# ButtonAction-Namen, die als kritisch gelten (deutliche Kennzeichnung).
_CRITICAL_ACTIONS = ("BLACKOUT", "STOP_ALL", "STOPALL")


class KeyTeachDialog(QDialog):
    """Eine Taste(nkombination) aufnehmen und dem Widget zuweisen."""

    def __init__(self, widget=None, current: str = "",
                 conflict_check=None, title: str = "Taste zuweisen",
                 parent=None):
        super().__init__(parent or widget)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setStyleSheet("QDialog { background:#161b22; } "
                           "QLabel { color:#e6edf3; font-size:12px; }")
        self._conflict_check = conflict_check
        self.result_sequence: str = current or ""

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        info = QLabel("Drücke jetzt die gewünschte Taste oder Kombination\n"
                      "(z. B. F5, Strg+B, Shift+Leertaste).\n"
                      "Esc bricht ab.")
        info.setStyleSheet("color:#8b949e; font-size:11px;")
        root.addWidget(info)

        self._seq_label = QLabel(self.result_sequence or "—")
        self._seq_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._seq_label.setStyleSheet(
            "background:#0d1117; color:#79c0ff; border:1px solid #30363d;"
            "border-radius:6px; font-size:18px; font-weight:bold; padding:14px;")
        root.addWidget(self._seq_label)

        self._conflict_label = QLabel("")
        self._conflict_label.setStyleSheet("color:#d29922; font-size:11px;")
        self._conflict_label.setWordWrap(True)
        root.addWidget(self._conflict_label)

        # Kritische Aktionen deutlich kennzeichnen (Blackout/Stop All)
        action_name = str(getattr(getattr(widget, "action", None), "name", "") or
                          getattr(widget, "action", "") or "").upper()
        if any(c in action_name for c in _CRITICAL_ACTIONS):
            warn = QLabel("⚠ KRITISCHE AKTION (Blackout/Stop) — Taste mit "
                          "Bedacht wählen, sie wirkt sofort und ohne Rückfrage!")
            warn.setStyleSheet("color:#f85149; font-size:11px; font-weight:bold;")
            warn.setWordWrap(True)
            root.addWidget(warn)

        btns = QHBoxLayout()
        self._btn_ok = QPushButton("Übernehmen")
        self._btn_ok.setEnabled(bool(self.result_sequence))
        self._btn_remove = QPushButton("Bindung entfernen")
        self._btn_remove.setEnabled(bool(current))
        btn_cancel = QPushButton("Abbrechen")
        for b in (self._btn_ok, self._btn_remove, btn_cancel):
            b.setMinimumHeight(38)
            b.setStyleSheet(_BTN_STYLE)
            btns.addWidget(b)
        self._btn_ok.clicked.connect(self.accept)
        self._btn_remove.clicked.connect(self._on_remove)
        btn_cancel.clicked.connect(self.reject)
        root.addLayout(btns)

        self.resize(420, 260)
        self._update_conflicts()

    # ── Tasten-Aufnahme ───────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        seq = sequence_from_event(event)
        if not seq:
            return  # reiner Modifier — auf die eigentliche Taste warten
        self.result_sequence = seq
        self._seq_label.setText(seq)
        self._btn_ok.setEnabled(True)
        self._update_conflicts()

    def _update_conflicts(self):
        if not self.result_sequence or self._conflict_check is None:
            self._conflict_label.setText("")
            return
        try:
            owners = list(self._conflict_check(self.result_sequence) or [])
        except Exception:
            owners = []
        if owners:
            self._conflict_label.setText(
                "⚠ Bereits belegt durch: " + ", ".join(owners)
                + " — Übernehmen löst dann BEIDE aus.")
        else:
            self._conflict_label.setText("")

    def _on_remove(self):
        self.result_sequence = ""
        self.accept()
