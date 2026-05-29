"""MIDI Teach Dialog — visuelles Zuweisen von APC-mini-Tasten/Fadern zu VC-Widgets.

Der Dialog zeigt ein 2D-Abbild des APC mini. Eine Bindung kann auf zwei Wegen
gesetzt werden:
  1) Echte Taste/Fader am APC mini betaetigen (live erkannt + hervorgehoben)
  2) Element im Bild mit der Maus anklicken

Rueckgabe ueber `result_binding` (nur gueltig wenn exec() == Accepted):
  (msg_type, channel, data1)  oder  None (= Bindung entfernen)
"""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QDialogButtonBox, QWidget, QPushButton)
from PySide6.QtCore import Qt, QRect, QTimer, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QPen


# ── APC mini Layout (Note-/CC-Nummern) ────────────────────────────────────────
_CELL = 38
_GAP = 4
_STEP = _CELL + _GAP
_X0 = 16
_Y0 = 16

GRID_COLS = 8
GRID_ROWS = 8
TRACK_NOTES = list(range(64, 72))   # horizontale Buttons unter dem Grid
SCENE_NOTES = list(range(82, 90))   # vertikale Buttons rechts
FADER_CCS = list(range(48, 57))     # 8 Track-Fader + Master (CC 48..56)


class _ApcView(QWidget):
    """Gezeichnetes APC-mini-Abbild mit Klick-Auswahl + Live-Highlight."""

    element_selected = Signal(str, int)   # kind ("note"|"cc"), data1

    def __init__(self, accept_kinds=("note", "cc"), parent=None):
        super().__init__(parent)
        self._accept = set(accept_kinds)
        self._elements: list[dict] = []
        self._selected: tuple[str, int] | None = None
        self._cc_values: dict[int, int] = {}
        self._content_bottom = 0
        self._compute_elements()
        w = max(_X0 * 2 + GRID_COLS * _STEP + 10 + _CELL,
                _X0 * 2 + len(FADER_CCS) * _STEP)
        self.setFixedSize(w, self._content_bottom + _Y0)

    def _compute_elements(self):
        els = []
        # 8x8 Grid (row 0 = unten, wie auf der Hardware)
        for row in range(GRID_ROWS):
            for col in range(GRID_COLS):
                x = _X0 + col * _STEP
                y = _Y0 + (GRID_ROWS - 1 - row) * _STEP
                note = row * GRID_COLS + col
                els.append({"rect": QRect(x, y, _CELL, _CELL),
                            "kind": "note", "data1": note, "group": "grid"})
        grid_bottom = _Y0 + GRID_ROWS * _STEP
        # Scene-Buttons rechts (82 oben .. 89 unten)
        sx = _X0 + GRID_COLS * _STEP + 10
        for i, note in enumerate(SCENE_NOTES):
            y = _Y0 + i * _STEP
            els.append({"rect": QRect(sx, y, _CELL, _CELL),
                        "kind": "note", "data1": note, "group": "scene"})
        # Track-Buttons unter dem Grid
        ty = grid_bottom + 8
        for i, note in enumerate(TRACK_NOTES):
            x = _X0 + i * _STEP
            els.append({"rect": QRect(x, ty, _CELL, 26),
                        "kind": "note", "data1": note, "group": "track"})
        # Fader (CC) darunter
        fy = ty + 26 + 12
        for i, cc in enumerate(FADER_CCS):
            x = _X0 + i * _STEP
            els.append({"rect": QRect(x, fy, _CELL, 54),
                        "kind": "cc", "data1": cc, "group": "fader"})
        self._content_bottom = fy + 54
        self._elements = els

    # ── Highlight / Live-Werte ────────────────────────────────────────────────

    def set_selected(self, kind, data1):
        if kind is not None and data1 is not None and data1 >= 0:
            self._selected = (kind, data1)
        else:
            self._selected = None
        self.update()

    def set_cc_value(self, cc: int, value: int):
        self._cc_values[cc] = value
        self.update()

    # ── Maus ──────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        for el in self._elements:
            if el["rect"].contains(pos):
                if el["kind"] not in self._accept:
                    return
                self.set_selected(el["kind"], el["data1"])
                self.element_selected.emit(el["kind"], el["data1"])
                return

    # ── Paint ──────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0d1117"))
        p.setFont(QFont("Segoe UI", 7))
        for el in self._elements:
            r = el["rect"]
            accepted = el["kind"] in self._accept
            sel = self._selected == (el["kind"], el["data1"])
            group = el["group"]
            if not accepted:
                base = QColor("#161b22")
            elif group == "grid":
                base = QColor("#22304a")
            elif group == "scene":
                base = QColor("#3a2a4a")
            elif group == "track":
                base = QColor("#2a3a2a")
            else:  # fader
                base = QColor("#1a2a3a")
            p.fillRect(r, base)
            # Fader-Fuellstand (Live)
            if el["kind"] == "cc" and accepted:
                val = self._cc_values.get(el["data1"], 0)
                fill_h = int(r.height() * max(0, min(127, val)) / 127.0)
                if fill_h > 0:
                    p.fillRect(r.x(), r.bottom() - fill_h, r.width(), fill_h,
                               QColor("#0088ff"))
            # Rahmen
            if sel:
                p.setPen(QPen(QColor("#ffcc00"), 3))
            else:
                p.setPen(QPen(QColor("#33415c"), 1))
            p.drawRect(r.adjusted(0, 0, -1, -1))
            # Label
            if sel:
                p.setPen(QColor("#ffcc00"))
            elif accepted:
                p.setPen(QColor("#c9d1d9"))
            else:
                p.setPen(QColor("#444c56"))
            lbl = f"CC{el['data1']}" if el["kind"] == "cc" else str(el["data1"])
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, lbl)
        p.end()


class MidiTeachDialog(QDialog):
    """Dialog zum Teachen einer MIDI-Bindung fuer ein VC-Widget."""

    def __init__(self, parent=None, current=None,
                 accept_kinds=("note", "cc"), title="MIDI Teach"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._accept = set(accept_kinds)
        self._channel = 0           # 0 = alle Kanaele
        self._binding = None        # (msg_type, channel, data1) | None
        self.result_binding = None  # gesetzt bei OK (kann None = entfernen sein)

        lay = QVBoxLayout(self)
        hint_kinds = []
        if "note" in self._accept:
            hint_kinds.append("eine Taste druecken")
        if "cc" in self._accept:
            hint_kinds.append("einen Fader bewegen")
        info = QLabel("Am APC mini " + " oder ".join(hint_kinds) +
                      " — oder ein Element im Bild anklicken.")
        info.setStyleSheet("color:#aaa;")
        info.setWordWrap(True)
        lay.addWidget(info)

        self._view = _ApcView(accept_kinds=accept_kinds)
        self._view.element_selected.connect(self._on_view_select)
        wrap = QHBoxLayout()
        wrap.addStretch(1)
        wrap.addWidget(self._view)
        wrap.addStretch(1)
        lay.addLayout(wrap)

        self._status = QLabel("Keine Bindung gewaehlt.")
        self._status.setStyleSheet("font-weight:bold; padding:4px;")
        lay.addWidget(self._status)

        row = QHBoxLayout()
        btn_clear = QPushButton("Bindung entfernen")
        btn_clear.clicked.connect(self._on_clear)
        row.addWidget(btn_clear)
        row.addStretch(1)
        lay.addLayout(row)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        # Vorbelegung mit aktueller Bindung
        if current and len(current) == 3 and current[2] is not None and current[2] >= 0:
            mtype, ch, d1 = current
            self._channel = ch or 0
            self._binding = (mtype, ch, d1)
            self._view.set_selected("cc" if mtype == "cc" else "note", d1)
            self._update_status()

        # MIDI-Subscribe — Callback laeuft im MidiDispatch-Thread, daher per
        # QTimer.singleShot in den UI-Thread marshallen (sonst nativer Crash).
        from src.core.midi.midi_manager import get_midi_manager
        self._mm = get_midi_manager()
        self._mm.subscribe(self._on_midi_raw)

    # ── MIDI ───────────────────────────────────────────────────────────────────

    def _on_midi_raw(self, msg):
        QTimer.singleShot(0, lambda m=msg: self._on_midi(m))

    def _on_midi(self, msg):
        try:
            if msg.msg_type == "cc" and "cc" in self._accept:
                self._view.set_cc_value(msg.data1, msg.data2)
                self._set_binding("cc", msg.channel, msg.data1)
            elif msg.msg_type == "note_on" and msg.data2 > 0 and "note" in self._accept:
                self._set_binding("note_on", msg.channel, msg.data1)
            # note_off / nicht akzeptierte Typen ignorieren
        except Exception:
            pass

    def _on_view_select(self, kind: str, data1: int):
        mtype = "cc" if kind == "cc" else "note_on"
        self._set_binding(mtype, self._channel or 1, data1)

    def _set_binding(self, msg_type: str, channel: int, data1: int):
        self._channel = channel
        self._binding = (msg_type, channel, data1)
        self._view.set_selected("cc" if msg_type == "cc" else "note", data1)
        self._update_status()

    def _on_clear(self):
        self._binding = None
        self._view.set_selected(None, None)
        self._status.setText("Bindung wird ENTFERNT (mit OK bestaetigen).")

    def _update_status(self):
        if not self._binding:
            self._status.setText("Keine Bindung gewaehlt.")
            return
        mtype, ch, d1 = self._binding
        ch_txt = "alle" if not ch else str(ch)
        kind = "CC / Fader" if mtype == "cc" else "Note / Taste"
        self._status.setText(f"Gewaehlt: {kind} {d1}  ·  Kanal {ch_txt}")

    # ── Schliessen → unsubscribe ───────────────────────────────────────────────

    def done(self, result: int):
        try:
            self._mm.unsubscribe(self._on_midi_raw)
        except Exception:
            pass
        if result == QDialog.DialogCode.Accepted:
            self.result_binding = self._binding   # kann None sein (= entfernen)
        super().done(result)
