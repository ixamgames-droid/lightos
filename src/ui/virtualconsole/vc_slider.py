"""VCSlider — Virtual Console Fader Widget."""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QComboBox,
                                QDialogButtonBox, QSizePolicy, QSpinBox, QLabel)
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QFont, QLinearGradient
from .vc_widget import VCWidget


class SliderMode(str):
    LEVEL    = "Level"
    PLAYBACK = "Playback"
    SUBMASTER = "Submaster"


class VCSlider(VCWidget):
    """Vertikaler Fader — Level / Playback / Submaster."""

    def __init__(self, caption: str = "Fader", parent=None):
        super().__init__(caption, parent)
        self.mode = SliderMode.LEVEL
        self.function_id: int | None = None
        self.dmx_channel: int = 1
        self.dmx_universe: int = 0
        self._value: int = 0          # 0–255
        self._drag_y: int | None = None
        self._drag_start_val: int = 0
        self._bg_color = QColor("#1a1a2e")
        self._fg_color = QColor("#ffffff")
        # MIDI CC binding
        self.midi_cc: int = -1        # -1 = kein MIDI
        self.midi_ch: int = 0         # 0 = alle Kanäle
        self.resize(60, 200)

    # ── Value ─────────────────────────────────────────────────────────────────

    @property
    def value(self) -> int:
        return self._value

    @value.setter
    def value(self, v: int):
        self._value = max(0, min(255, v))
        self._apply()
        self.update()

    def _apply(self):
        from src.core.app_state import get_state
        state = get_state()
        if self.mode == SliderMode.LEVEL:
            if self.dmx_universe < len(state.universes):
                state.universes[self.dmx_universe].set_channel(self.dmx_channel, self._value)
        elif self.mode == SliderMode.PLAYBACK and self.function_id is not None:
            slot = self.function_id
            executors = state.playback_engine.executors
            if slot < len(executors):
                executors[slot].fader_value = self._value / 255.0
        elif self.mode == SliderMode.SUBMASTER:
            state.output_manager.set_submaster(self.function_id or 0, self._value / 255.0)

    # ── MIDI ─────────────────────────────────────────────────────────────────

    def handle_midi(self, msg) -> bool:
        if self.midi_cc < 0 or msg.msg_type != "cc":
            return False
        if self.midi_ch != 0 and self.midi_ch != msg.channel:
            return False
        if msg.data1 != self.midi_cc:
            return False
        self.value = int(msg.data2 / 127.0 * 255)
        return True

    # ── Track geometry ────────────────────────────────────────────────────────

    def _track_rect(self) -> QRect:
        m = 20
        return QRect(self.width() // 2 - 6, m, 12, self.height() - m * 2)

    def _handle_y(self) -> int:
        tr = self._track_rect()
        ratio = 1.0 - self._value / 255.0
        return int(tr.y() + ratio * tr.height())

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_y = event.position().toPoint().y()
            self._drag_start_val = self._value
        event.accept()

    def mouseMoveEvent(self, event):
        if self._edit_mode:
            super().mouseMoveEvent(event)
            return
        if self._drag_y is not None:
            dy = self._drag_y - event.position().toPoint().y()
            tr = self._track_rect()
            delta = int(dy / tr.height() * 255)
            self.value = self._drag_start_val + delta
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
        steps = event.angleDelta().y() // 120
        self.value = self._value + steps * 5

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg_color)

        tr = self._track_rect()
        # Track background
        p.fillRect(tr, QColor("#333355"))

        # Fill from bottom to handle
        hy = self._handle_y()
        fill = QRect(tr.x(), hy, tr.width(), tr.bottom() - hy)
        grad = QLinearGradient(0, fill.bottom(), 0, fill.top())
        grad.setColorAt(0.0, QColor("#003366"))
        grad.setColorAt(1.0, QColor("#0088ff"))
        p.fillRect(fill, grad)

        # Handle knob
        p.fillRect(tr.x() - 8, hy - 4, tr.width() + 16, 8, QColor("#aaccff"))

        # Label at bottom
        p.setPen(self._fg_color)
        p.setFont(QFont("Segoe UI", 8))
        label_rect = QRect(0, self.height() - 18, self.width(), 18)
        p.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, self.caption)

        # Value
        p.setFont(QFont("Segoe UI", 7))
        val_rect = QRect(0, 2, self.width(), 14)
        pct = int(self._value / 255 * 100)
        p.drawText(val_rect, Qt.AlignmentFlag.AlignCenter, f"{pct}%")

        # MIDI-Bindung-Indikator oben rechts (cyan dot)
        if self.midi_cc >= 0:
            p.fillRect(self.width() - 8, 0, 8, 8, QColor("#00aaff"))
        p.end()

    # ── Properties ───────────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Fader Einstellungen")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        mode_cb = QComboBox()
        for m in (SliderMode.LEVEL, SliderMode.PLAYBACK, SliderMode.SUBMASTER):
            mode_cb.addItem(m)
        mode_cb.setCurrentText(self.mode)
        form.addRow("Modus:", mode_cb)
        ch = QLineEdit(str(self.dmx_channel))
        form.addRow("DMX-Kanal (Level-Modus):", ch)
        slot = QLineEdit(str(self.function_id) if self.function_id is not None else "")
        form.addRow("Executor-Slot (Playback):", slot)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        form.addRow(QLabel("── MIDI CC Bindung ──"))

        midi_cc_spin = QSpinBox()
        midi_cc_spin.setRange(-1, 127)
        midi_cc_spin.setValue(self.midi_cc)
        midi_cc_spin.setSpecialValueText("keine")
        form.addRow("CC-Nummer (-1=keine):", midi_cc_spin)

        midi_ch_spin = QSpinBox()
        midi_ch_spin.setRange(0, 16)
        midi_ch_spin.setValue(self.midi_ch)
        midi_ch_spin.setSpecialValueText("Alle")
        form.addRow("MIDI-Kanal (0=alle):", midi_ch_spin)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self.mode = mode_cb.currentText()
            try:
                self.dmx_channel = int(ch.text())
            except ValueError:
                pass
            try:
                self.function_id = int(slot.text())
            except ValueError:
                self.function_id = None
            self.midi_cc = midi_cc_spin.value()
            self.midi_ch = midi_ch_spin.value()
            self.update()

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["mode"] = self.mode
        d["function_id"] = self.function_id
        d["dmx_channel"] = self.dmx_channel
        d["dmx_universe"] = self.dmx_universe
        d["value"] = self._value
        d["midi_cc"] = self.midi_cc
        d["midi_ch"] = self.midi_ch
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self.mode = d.get("mode", SliderMode.LEVEL)
        self.function_id = d.get("function_id")
        self.dmx_channel = d.get("dmx_channel", 1)
        self.dmx_universe = d.get("dmx_universe", 0)
        self._value = d.get("value", 0)
        self.midi_cc = d.get("midi_cc", -1)
        self.midi_ch = d.get("midi_ch", 0)
