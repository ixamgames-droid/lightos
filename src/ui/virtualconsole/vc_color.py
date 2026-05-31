"""VCColor — Virtual-Console-Widget, das eine feste Farbe haelt.

Klick (oder gebundene MIDI-Taste/Fader) wendet die Farbe auf die Ziel-Fixtures
an. Die Kachel zeigt die Farbe direkt an. MIDI-Bindung funktioniert identisch
zum VCButton, daher greifen MIDI-Teach (Rechtsklick) und der Canvas-Dispatch
ohne Zusatzcode. Das APC-mk2-LED-Feedback faerbt das gebundene Pad in genau
dieser Farbe (siehe apc_mk2_feedback.py).
"""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QComboBox,
                                QDialogButtonBox, QSpinBox, QLabel, QPushButton)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from .vc_widget import VCWidget


class ColorTarget(str):
    PROGRAMMER = "Programmer/Selektion"
    ALL = "Alle Fixtures"


class VCColor(VCWidget):
    """Farb-Kachel — wendet eine RGB(+W/A/UV)-Farbe auf Fixtures an."""

    def __init__(self, caption: str = "Farbe", parent=None):
        super().__init__(caption, parent)
        self.color_r = 255
        self.color_g = 255
        self.color_b = 255
        self.color_w = 0       # nur gesendet wenn > 0
        self.color_a = 0
        self.color_uv = 0
        # Intensitaet mitsetzen, damit die Farbe IMMER sichtbar ist (sonst haengt
        # sie von der Intensitaet eines laufenden Effekts ab -> "Farbe geht nicht").
        self.with_intensity = True
        self.intensity = 255
        self.target = ColorTarget.PROGRAMMER

        # MIDI-Bindung (-1 = keine) — identisch zu VCButton
        self.midi_ch: int = 0
        self.midi_data1: int = -1
        self.midi_type: str = "note_on"

        self._pressed = False
        self.resize(80, 80)

    # ── Farbe als QColor ───────────────────────────────────────────────────────

    def color(self) -> QColor:
        return QColor(self.color_r, self.color_g, self.color_b)

    def set_color(self, c: QColor):
        self.color_r, self.color_g, self.color_b = c.red(), c.green(), c.blue()
        self.update()

    # ── Anwenden ───────────────────────────────────────────────────────────────

    def _target_fids(self, state) -> list[int]:
        if self.target == ColorTarget.PROGRAMMER:
            fids = list(state.programmer.keys())
            if fids:
                return fids
        # Fallback / "Alle": alle gepatchten Fixtures
        out = []
        for f in state.get_patched_fixtures():
            fid = getattr(f, "fid", None)
            if fid is None and isinstance(f, dict):
                fid = f.get("fid") or f.get("id")
            if fid is not None:
                out.append(fid)
        return out

    def _apply(self):
        try:
            from src.core.app_state import get_state
            state = get_state()
            for fid in self._target_fids(state):
                if self.with_intensity:
                    state.set_programmer_value(fid, "intensity", self.intensity)
                state.set_programmer_value(fid, "color_r", self.color_r)
                state.set_programmer_value(fid, "color_g", self.color_g)
                state.set_programmer_value(fid, "color_b", self.color_b)
                # color_w IMMER setzen -> klärt Restweiss eines vorigen Looks/Effekts
                state.set_programmer_value(fid, "color_w", self.color_w)
                if self.color_a:
                    state.set_programmer_value(fid, "color_a", self.color_a)
                if self.color_uv:
                    state.set_programmer_value(fid, "color_uv", self.color_uv)
        except Exception as e:
            print(f"[VCColor] apply error: {e}")

    # ── MIDI (analog VCButton) ─────────────────────────────────────────────────

    def supports_midi_teach(self) -> bool:
        return True

    def current_midi_binding(self):
        if self.midi_data1 is None or self.midi_data1 < 0:
            return None
        return (self.midi_type, self.midi_ch, self.midi_data1)

    def apply_midi_binding(self, msg_type, channel, data1):
        if data1 is None or data1 < 0:
            self.midi_data1 = -1
            return
        self.midi_type = "cc" if msg_type == "cc" else "note_on"
        self.midi_ch = channel or 0
        self.midi_data1 = data1

    def matches_midi(self, msg) -> bool:
        if self.midi_data1 < 0:
            return False
        if self.midi_type == "note_on":
            if msg.msg_type not in ("note_on", "note_off"):
                return False
        elif self.midi_type != msg.msg_type:
            return False
        if self.midi_ch != 0 and self.midi_ch != msg.channel:
            return False
        return self.midi_data1 == msg.data1

    def handle_midi(self, msg) -> bool:
        if not self.matches_midi(msg):
            return False
        if msg.msg_type == "note_on" and msg.data2 > 0:
            self._pressed = True
            self._apply()
            self.update()
        elif msg.msg_type in ("note_off",) or (msg.msg_type == "note_on" and msg.data2 == 0):
            self._pressed = False
            self.update()
        elif msg.msg_type == "cc":
            press = msg.data2 > 63
            if press != self._pressed:
                self._pressed = press
                if press:
                    self._apply()
                self.update()
        return True

    # ── Maus ───────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        if self._run_input_blocked():
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._apply()
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._edit_mode:
            super().mouseReleaseEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self.update()
        event.accept()

    # ── Paint ──────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        col = self.color()
        if self._pressed:
            col = col.lighter(130)
        p.fillRect(self.rect(), col)

        # Kontrast-Textfarbe
        lum = self.color_r + self.color_g + self.color_b
        text_col = QColor("#000") if lum > 380 else QColor("#fff")
        p.setPen(text_col)
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                   self.caption)

        if self._pressed:
            p.setPen(QPen(QColor("#ffffff"), 3))
            p.drawRect(self.rect().adjusted(1, 1, -2, -2))

        # MIDI-Bindung-Indikator oben rechts
        if self.midi_data1 >= 0:
            p.fillRect(self.width() - 8, 0, 8, 8, QColor("#00aaff"))

        # Edit-Mode: Resize-Handle + Auswahlrahmen wieder einzeichnen
        if self._edit_mode:
            hs = self.HANDLE_SIZE
            r = self.rect()
            p.fillRect(r.right() - hs, r.bottom() - hs, hs, hs, QColor("#0088ff"))
            if self._selected:
                p.setPen(QPen(QColor("#58d68d"), 2))
            else:
                p.setPen(QPen(QColor("#0088ff"), 1, Qt.PenStyle.DashLine))
            p.drawRect(r.adjusted(0, 0, -1, -1))
        p.end()

    # ── Properties ─────────────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Farb-Kachel Einstellungen")
        form = QFormLayout(dlg)

        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)

        # Farbauswahl
        btn_color = QPushButton()
        btn_color.setFixedHeight(28)

        def _refresh_swatch():
            c = self.color()
            tc = "#000" if (self.color_r + self.color_g + self.color_b) > 380 else "#fff"
            btn_color.setStyleSheet(
                f"background: rgb({c.red()},{c.green()},{c.blue()}); color:{tc};"
                "border:1px solid #555; border-radius:3px;")
            btn_color.setText(f"RGB {c.red()},{c.green()},{c.blue()}")

        def _pick():
            from PySide6.QtWidgets import QColorDialog
            c = QColorDialog.getColor(self.color(), dlg, "Farbe waehlen")
            if c.isValid():
                self.color_r, self.color_g, self.color_b = c.red(), c.green(), c.blue()
                _refresh_swatch()
        btn_color.clicked.connect(_pick)
        _refresh_swatch()
        form.addRow("Farbe:", btn_color)

        w_spin = QSpinBox(); w_spin.setRange(0, 255); w_spin.setValue(self.color_w)
        form.addRow("White (0=aus):", w_spin)
        a_spin = QSpinBox(); a_spin.setRange(0, 255); a_spin.setValue(self.color_a)
        form.addRow("Amber (0=aus):", a_spin)
        uv_spin = QSpinBox(); uv_spin.setRange(0, 255); uv_spin.setValue(self.color_uv)
        form.addRow("UV (0=aus):", uv_spin)

        target_cb = QComboBox()
        target_cb.addItems([ColorTarget.PROGRAMMER, ColorTarget.ALL])
        target_cb.setCurrentText(self.target)
        form.addRow("Ziel:", target_cb)

        form.addRow(QLabel("── MIDI-Bindung (oder Rechtsklick → Teach) ──"))
        midi_type_combo = QComboBox()
        midi_type_combo.addItems(["note_on", "cc"])
        midi_type_combo.setCurrentText(self.midi_type)
        form.addRow("MIDI-Typ:", midi_type_combo)
        midi_ch_spin = QSpinBox(); midi_ch_spin.setRange(0, 16)
        midi_ch_spin.setValue(self.midi_ch); midi_ch_spin.setSpecialValueText("Alle")
        form.addRow("MIDI-Kanal (0=alle):", midi_ch_spin)
        midi_note_spin = QSpinBox(); midi_note_spin.setRange(-1, 127)
        midi_note_spin.setValue(self.midi_data1); midi_note_spin.setSpecialValueText("keine")
        form.addRow("Note / CC (-1=keine):", midi_note_spin)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self.color_w = w_spin.value()
            self.color_a = a_spin.value()
            self.color_uv = uv_spin.value()
            self.target = target_cb.currentText()
            self.midi_type = midi_type_combo.currentText()
            self.midi_ch = midi_ch_spin.value()
            self.midi_data1 = midi_note_spin.value()
            self.update()

    # ── Serialisierung ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["color_r"] = self.color_r
        d["color_g"] = self.color_g
        d["color_b"] = self.color_b
        d["color_w"] = self.color_w
        d["color_a"] = self.color_a
        d["color_uv"] = self.color_uv
        d["with_intensity"] = self.with_intensity
        d["intensity"] = self.intensity
        d["target"] = self.target
        d["midi_ch"] = self.midi_ch
        d["midi_data1"] = self.midi_data1
        d["midi_type"] = self.midi_type
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self.color_r = d.get("color_r", 255)
        self.color_g = d.get("color_g", 255)
        self.color_b = d.get("color_b", 255)
        self.color_w = d.get("color_w", 0)
        self.color_a = d.get("color_a", 0)
        self.color_uv = d.get("color_uv", 0)
        self.with_intensity = bool(d.get("with_intensity", True))
        self.intensity = d.get("intensity", 255)
        self.target = d.get("target", ColorTarget.PROGRAMMER)
        self.midi_ch = d.get("midi_ch", 0)
        self.midi_data1 = d.get("midi_data1", -1)
        self.midi_type = d.get("midi_type", "note_on")
