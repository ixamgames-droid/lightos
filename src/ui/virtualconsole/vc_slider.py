"""VCSlider — Virtual Console Fader Widget."""
from __future__ import annotations
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QComboBox, QDialogButtonBox, QSizePolicy
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
            # Direkt zur angeklickten Position springen
            tr = self._track_rect()
            y = event.position().toPoint().y()
            ratio = (y - tr.y()) / max(1, tr.height())
            self.value = int((1.0 - max(0.0, min(1.0, ratio))) * 255)
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

    # ── MIDI ─────────────────────────────────────────────────────────────────

    def handle_midi(self, msg):
        """Wird vom VCCanvas aufgerufen wenn eine MIDI-Nachricht eingeht."""
        b = self.midi_binding
        if b is None:
            return
        if b.get("msg_type") != msg.msg_type:
            return
        ch = b.get("channel", 0)
        if ch != 0 and ch != msg.channel:
            return
        if b.get("data1") != msg.data1:
            return
        pf = b.get("port_filter", "")
        if pf and pf not in msg.port_name:
            return
        # CC-Wert 0-127 → Slider-Wert 0-255
        self.value = int(msg.data2 / 127.0 * 255)

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
        p.end()

    # ── Properties ───────────────────────────────────────────────────────────

    def _open_properties(self):
        from PySide6.QtWidgets import QHBoxLayout
        from PySide6.QtCore import QTimer
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

        # MIDI-Bindung
        _binding = [self.midi_binding.copy() if self.midi_binding else None]

        def _binding_text():
            b = _binding[0]
            if b is None:
                return "Keine"
            return f"{b.get('msg_type','')} / CH{b.get('channel',0)} / CC/Note {b.get('data1',0)}"

        midi_display = QLabel(_binding_text())
        midi_display.setStyleSheet("color:#58a6ff; font-size:10px;")
        btn_learn = QPushButton("MIDI Lernen")
        btn_learn.setFixedHeight(22)
        btn_clear_midi = QPushButton("Loeschen")
        btn_clear_midi.setFixedHeight(22)

        def on_learn():
            try:
                from src.core.midi.midi_manager import get_midi_manager
                btn_learn.setText("Warte auf MIDI...")
                btn_learn.setEnabled(False)
                midi = get_midi_manager()
                def on_msg(msg):
                    _binding[0] = {
                        "msg_type": msg.msg_type,
                        "channel": msg.channel,
                        "data1": msg.data1,
                        "port_filter": msg.port_name,
                    }
                    def _update_ui():
                        midi_display.setText(_binding_text())
                        btn_learn.setText("MIDI Lernen")
                        btn_learn.setEnabled(True)
                    QTimer.singleShot(0, _update_ui)
                midi.start_learn(on_msg)
            except Exception as e:
                btn_learn.setText("MIDI Lernen")
                btn_learn.setEnabled(True)
                print(f"[VCSlider] MIDI Learn Fehler: {e}")

        def on_clear_midi():
            _binding[0] = None
            midi_display.setText("Keine")

        btn_learn.clicked.connect(on_learn)
        btn_clear_midi.clicked.connect(on_clear_midi)

        from PySide6.QtWidgets import QWidget as _QWidget
        midi_row = _QWidget()
        midi_row_layout = QHBoxLayout(midi_row)
        midi_row_layout.setContentsMargins(0, 0, 0, 0)
        midi_row_layout.setSpacing(4)
        midi_row_layout.addWidget(midi_display, stretch=1)
        midi_row_layout.addWidget(btn_learn)
        midi_row_layout.addWidget(btn_clear_midi)
        form.addRow("MIDI-Bindung:", midi_row)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
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
            self.midi_binding = _binding[0]
            self.update()

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["mode"] = self.mode
        d["function_id"] = self.function_id
        d["dmx_channel"] = self.dmx_channel
        d["dmx_universe"] = self.dmx_universe
        d["value"] = self._value
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self.mode = d.get("mode", SliderMode.LEVEL)
        self.function_id = d.get("function_id")
        self.dmx_channel = d.get("dmx_channel", 1)
        self.dmx_universe = d.get("dmx_universe", 0)
        self._value = d.get("value", 0)
