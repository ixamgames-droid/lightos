"""VCEncoder — generischer Dreh-Encoder fuer Effekt-Parameter (Live-Programming).

Im Gegensatz zum VCSlider (absoluter Fader) steuert der Encoder einen
Effekt-Parameter *relativ* (Drehen ohne Sprung): Drag nach oben/unten, Mausrad
oder ein relativer MIDI-Encoder erhoehen/senken den Wert um Schritte. Er nutzt
denselben gemeinsamen Dispatcher wie alle Live-Bedienelemente
(``effect_live.adjust_param`` relativ bzw. ``set_param_normalized`` absolut) und
zeigt stets den AKTUELLEN Wert des Zielparameters an (fest gebundener Effekt
ueber ``function_id`` oder der aktive Effekt, wenn leer).

Geeignet fuer numerische Parameter (int/float) wie speed, level, count, rate,
density, spread, runner_count …
"""
from __future__ import annotations
import math
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QComboBox,
                                QDialogButtonBox, QDoubleSpinBox, QSpinBox, QLabel)
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from .vc_widget import VCWidget


class EncoderMidiMode(str):
    RELATIVE = "Relativ"     # Hardware-Encoder: CC sendet Schritte (1..63 = +, 65..127 = −)
    ABSOLUTE = "Absolut"     # Poti/Fader: CC 0..127 → Wertebereich des Parameters


class VCEncoder(VCWidget):
    """Dreh-Encoder, der einen Effekt-Parameter relativ live verstellt."""

    def __init__(self, caption: str = "Encoder", parent=None):
        super().__init__(caption, parent)
        self.param_key: str = "speed"
        self.function_id: int | None = None     # None = aktiver Effekt
        # Schrittweite je Detent/Rad-Schritt als Anteil des Wertebereichs (0..1).
        self.step: float = 0.05
        self.midi_mode: str = EncoderMidiMode.RELATIVE
        # MIDI-CC-Bindung (-1 = keine) — wie beim Fader
        self.midi_cc: int = -1
        self.midi_ch: int = 0

        self._drag_y: int | None = None
        self._bg_color = QColor("#0d1117")
        self._fg_color = QColor("#58a6ff")
        self.resize(96, 110)

    # ── Dispatcher-Anbindung (gemeinsam mit VC/MIDI) ──────────────────────────

    def _spec(self):
        try:
            from src.core.engine import effect_live
            for s in effect_live.list_params(self.function_id):
                if s.key == self.param_key:
                    return s
        except Exception:
            pass
        return None

    def _current_value(self):
        try:
            from src.core.engine import effect_live
            return effect_live.get_param(self.param_key, self.function_id)
        except Exception:
            return None

    def _current_norm(self) -> float | None:
        """Aktueller Wert als 0..1 fuer die Bogenanzeige (oder None = kein Ziel)."""
        spec = self._spec()
        val = self._current_value()
        if spec is None or val is None:
            return None
        try:
            if spec.kind == "bool":
                return 1.0 if val else 0.0
            if spec.kind == "select":
                opts = tuple(spec.options or ())
                return (opts.index(val) / max(1, len(opts) - 1)) if val in opts else 0.0
            lo, hi = float(spec.min), float(spec.max)
            if hi <= lo:
                return 0.0
            return max(0.0, min(1.0, (float(val) - lo) / (hi - lo)))
        except Exception:
            return None

    def nudge(self, ticks: float):
        """Relativ um `ticks` Schritte (× step) verstellen — der Kern des Encoders."""
        try:
            from src.core.engine import effect_live
            effect_live.adjust_param(self.param_key, ticks * self.step, self.function_id)
        except Exception:
            pass
        self.update()

    def set_normalized(self, norm: float):
        """Absolut setzen (nur fuer den absoluten MIDI-Modus)."""
        try:
            from src.core.engine import effect_live
            effect_live.set_param_normalized(self.param_key, norm, self.function_id)
        except Exception:
            pass
        self.update()

    # ── MIDI ─────────────────────────────────────────────────────────────────

    def handle_midi(self, msg) -> bool:
        if self.midi_cc < 0 or msg.msg_type != "cc":
            return False
        if self.midi_ch != 0 and self.midi_ch != msg.channel:
            return False
        if msg.data1 != self.midi_cc:
            return False
        if self.midi_mode == EncoderMidiMode.ABSOLUTE:
            self.set_normalized(msg.data2 / 127.0)
        else:
            # Relativ (Zweierkomplement um 64): 1..63 = +, 65..127 = − , 0/64 = 0.
            v = int(msg.data2)
            steps = v if v < 64 else v - 128
            if steps:
                self.nudge(steps)
        return True

    def supports_midi_teach(self) -> bool:
        return True

    def _midi_teach_kinds(self):
        return ("cc",)

    def current_midi_binding(self):
        if self.midi_cc is None or self.midi_cc < 0:
            return None
        return ("cc", self.midi_ch, self.midi_cc)

    def apply_midi_binding(self, msg_type, channel, data1):
        if data1 is None or data1 < 0:
            self.midi_cc = -1
            return
        if msg_type == "cc":
            self.midi_cc = data1
            self.midi_ch = channel or 0

    # ── Maus ────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        if self._run_input_blocked():
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_y = event.position().toPoint().y()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._edit_mode:
            super().mouseMoveEvent(event)
            return
        if self._drag_y is not None:
            y = event.position().toPoint().y()
            dy = self._drag_y - y                     # nach oben = +
            if abs(dy) >= 3:
                # 3 px ~ ein Schritt; feinfuehlig ueber den Drag.
                self.nudge(dy / 60.0 / max(self.step, 1e-6))
                self._drag_y = y
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._edit_mode:
            super().mouseReleaseEvent(event)
            return
        self._drag_y = None
        event.accept()

    def wheelEvent(self, event):
        if self._edit_mode:
            return
        self.nudge(event.angleDelta().y() / 120.0)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def _center(self) -> QPoint:
        return QPoint(self.width() // 2, self.height() // 2 - 4)

    def _radius(self) -> int:
        return min(self.width(), self.height() - 28) // 2 - 6

    def _fmt_value(self) -> str:
        val = self._current_value()
        if val is None:
            return "—"
        if isinstance(val, bool):
            return "An" if val else "Aus"
        if isinstance(val, float):
            return f"{val:.2f}".rstrip("0").rstrip(".")
        return str(val)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg_color)

        c = self._center()
        r = self._radius()
        # Hintergrund-Bogen (270°, von 225° im Uhrzeigersinn)
        p.setPen(QPen(QColor("#21262d"), 4))
        p.drawArc(c.x() - r, c.y() - r, r * 2, r * 2, int(225 * 16), int(-270 * 16))

        norm = self._current_norm()
        if norm is not None:
            span = int(norm * 270)
            p.setPen(QPen(self._fg_color, 4))
            p.drawArc(c.x() - r, c.y() - r, r * 2, r * 2, int(225 * 16), int(-span * 16))
            # Zeiger
            ang = math.radians(-225 + norm * 270)
            nx = c.x() + int(math.cos(ang) * (r - 4))
            ny = c.y() - int(math.sin(ang) * (r - 4))
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.drawLine(c, QPoint(nx, ny))

        # Wert in der Mitte
        p.setPen(self._fg_color if norm is not None else QColor("#484f58"))
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(QRect(c.x() - 34, c.y() - 9, 68, 18),
                   Qt.AlignmentFlag.AlignCenter, self._fmt_value())

        # Caption oben, Parameter-Key unten
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor("#8b949e"))
        p.drawText(QRect(0, 2, self.width(), 14), Qt.AlignmentFlag.AlignCenter, self.caption)
        p.setFont(QFont("Segoe UI", 7))
        p.drawText(QRect(0, self.height() - 16, self.width(), 14),
                   Qt.AlignmentFlag.AlignCenter, self.param_key)

        # MIDI-Indikator
        if self.midi_cc >= 0:
            p.fillRect(self.width() - 8, 0, 8, 8, QColor("#00aaff"))
        p.end()

    # ── Properties ─────────────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Encoder Einstellungen")
        form = QFormLayout(dlg)

        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)

        key_edit = QLineEdit(self.param_key)
        key_edit.setToolTip("Effekt-Parameter-Key (numerisch), z. B. speed, level, count, rate, density")
        form.addRow("Parameter-Key:", key_edit)

        fid_edit = QLineEdit("" if self.function_id is None else str(self.function_id))
        fid_edit.setToolTip("Funktions-ID des Ziel-Effekts. Leer = aktiver Effekt.")
        form.addRow("Effekt-ID (leer=aktiv):", fid_edit)

        step_sb = QDoubleSpinBox()
        step_sb.setRange(0.005, 1.0)
        step_sb.setSingleStep(0.01)
        step_sb.setDecimals(3)
        step_sb.setValue(self.step)
        step_sb.setToolTip("Schrittweite je Detent/Rad-Schritt als Anteil des Wertebereichs")
        form.addRow("Schrittweite (Anteil):", step_sb)

        mode_cb = QComboBox()
        mode_cb.addItems([EncoderMidiMode.RELATIVE, EncoderMidiMode.ABSOLUTE])
        mode_cb.setCurrentText(self.midi_mode)
        form.addRow("MIDI-Modus:", mode_cb)

        form.addRow(QLabel("── MIDI CC Bindung (oder Rechtsklick → Teach) ──"))
        cc_sb = QSpinBox()
        cc_sb.setRange(-1, 127)
        cc_sb.setValue(self.midi_cc)
        cc_sb.setSpecialValueText("keine")
        form.addRow("CC-Nummer (-1=keine):", cc_sb)
        ch_sb = QSpinBox()
        ch_sb.setRange(0, 16)
        ch_sb.setValue(self.midi_ch)
        ch_sb.setSpecialValueText("Alle")
        form.addRow("MIDI-Kanal (0=alle):", ch_sb)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self.param_key = key_edit.text().strip() or self.param_key
            t = fid_edit.text().strip()
            self.function_id = int(t) if t.lstrip("-").isdigit() else None
            self.step = float(step_sb.value())
            self.midi_mode = mode_cb.currentText()
            self.midi_cc = cc_sb.value()
            self.midi_ch = ch_sb.value()
            self.update()

    # ── Serialisierung ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["param_key"] = self.param_key
        d["function_id"] = self.function_id
        d["step"] = self.step
        d["midi_mode"] = self.midi_mode
        d["midi_cc"] = self.midi_cc
        d["midi_ch"] = self.midi_ch
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self.param_key = d.get("param_key", "speed")
        self.function_id = d.get("function_id")
        self.step = float(d.get("step", 0.05))
        self.midi_mode = d.get("midi_mode", EncoderMidiMode.RELATIVE)
        self.midi_cc = int(d.get("midi_cc", -1))
        self.midi_ch = int(d.get("midi_ch", 0))
