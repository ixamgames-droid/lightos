"""VCButton — Virtual Console Button Widget."""
from __future__ import annotations
from enum import Enum
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QComboBox,
                                QKeySequenceEdit, QDialogButtonBox, QSizePolicy,
                                QPushButton, QColorDialog, QSpinBox, QLabel,
                                QHBoxLayout, QWidget)
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor, QFont, QKeySequence
from .vc_widget import VCWidget


class ButtonAction(str, Enum):
    TOGGLE   = "Toggle"
    FLASH    = "Flash"
    BLACKOUT = "Blackout"
    STOP_ALL = "StopAll"
    SNAPSHOT = "Snapshot"


class VCButton(VCWidget):
    """Pushbutton — Flash / Toggle / Blackout / StopAll / Snapshot."""

    def __init__(self, caption: str = "Button", parent=None):
        super().__init__(caption, parent)
        self.action = ButtonAction.TOGGLE
        self.function_id: int | None = None   # linked CueStack slot
        self.snapshot_index: int | None = None  # linked Snapshot slot (fuer SNAPSHOT action)
        self._pressed = False
        self._state: bool = False             # persistent TOGGLE active state
        self._bg_color = QColor("#1a3a5c")
        self._fg_color = QColor("#ffffff")
        self.resize(120, 60)

    # ── Action ───────────────────────────────────────────────────────────────

    def _deactivate(self):
        """Vom Solo-Frame aufgerufen, um diesen Button zwangsweise zu deaktivieren."""
        if not self._state:
            return
        self._state = False
        try:
            from src.core.app_state import get_state
            state = get_state()
            if self.function_id is not None:
                slot = self.function_id
                executors = state.playback_engine.executors
                if slot < len(executors):
                    executors[slot].press_btn("go")
        except Exception:
            pass
        self.update()

    def _trigger(self, press: bool):
        # SNAPSHOT: Programmer-State aus gespeichertem Snap laden
        if self.action == ButtonAction.SNAPSHOT:
            if press:
                try:
                    from src.ui.views.snapshots_view import get_snapshots_view
                    sv = get_snapshots_view()
                    if sv is not None and self.snapshot_index is not None:
                        sv.apply(self.snapshot_index)
                        self._state = True
                        self.update()
                except Exception as e:
                    print(f"[vc_button] snapshot apply error: {e}")
            else:
                self._state = False
                self.update()
            return

        # Solo-Frame: bei TOGGLE-Aktivierung andere Buttons im Frame deaktivieren
        if press and self.action == ButtonAction.TOGGLE and not self._state:
            try:
                from .vc_frame import VCFrame
                p = self.parent()
                while p is not None:
                    if isinstance(p, VCFrame) and p.is_solo():
                        p.on_child_activated(self)
                        break
                    p = p.parent()
            except Exception:
                pass

        from src.core.app_state import get_state
        state = get_state()
        if self.action == ButtonAction.BLACKOUT:
            if press:
                state.output_manager.set_blackout(True)
            else:
                state.output_manager.set_blackout(False)
            return
        if self.action == ButtonAction.STOP_ALL:
            if press:
                state.playback_engine.stop_all()
            return
        if self.function_id is None:
            return
        slot = self.function_id
        executors = state.playback_engine.executors
        if slot >= len(executors):
            return
        ex = executors[slot]
        if self.action == ButtonAction.FLASH:
            ex.press_btn("flash") if press else ex.release_btn("flash")
        elif self.action == ButtonAction.TOGGLE and press:
            self._state = not self._state
            ex.press_btn("go")

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

        press = msg.msg_type == "note_on" and msg.data2 > 0
        release = msg.msg_type == "note_off" or (msg.msg_type == "note_on" and msg.data2 == 0)
        if press:
            self._pressed = True
            self._trigger(True)
            self._update_apc_led()
            self.update()
        elif release:
            self._pressed = False
            self._trigger(False)
            self._update_apc_led()
            self.update()

    def _update_apc_led(self):
        """Sendet LED-Feedback an APC Mini fuer diese Button-Bindung."""
        b = self.midi_binding
        if b is None or b.get("msg_type") != "note_on":
            return
        note = b.get("data1", -1)
        if not (0 <= note <= 127):
            return
        try:
            from src.core.midi.apc_mini_feedback import get_apc_feedback, LED_GREEN, LED_OFF
            fb = get_apc_feedback()
            if fb:
                if self.action in (ButtonAction.TOGGLE,) and self._state:
                    fb.set_led(note, LED_GREEN)
                elif self._pressed:
                    fb.set_led(note, LED_GREEN)
                else:
                    fb.set_led(note, LED_OFF)
        except Exception:
            pass

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._trigger(True)
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._edit_mode:
            super().mouseReleaseEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self._trigger(False)
            self.update()
        event.accept()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        if self._pressed:
            bg = self._bg_color.lighter(140)
        elif self._state and self.action in (ButtonAction.TOGGLE, ButtonAction.SNAPSHOT):
            bg = self._bg_color.lighter(170)
        else:
            bg = self._bg_color
        p.fillRect(self.rect(), bg)
        # Aktivierungsindikator oben
        if self._state and self.action in (ButtonAction.TOGGLE, ButtonAction.SNAPSHOT):
            p.fillRect(0, 0, self.width(), 3, QColor("#39d353"))
        p.setPen(self._fg_color)
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.caption)
        if self.action == ButtonAction.FLASH:
            p.fillRect(0, self.height() - 4, self.width(), 4, QColor("#ff8800"))
        elif self.action == ButtonAction.BLACKOUT:
            p.fillRect(0, self.height() - 4, self.width(), 4, QColor("#ff2222"))
        elif self.action == ButtonAction.SNAPSHOT:
            p.fillRect(0, self.height() - 4, self.width(), 4, QColor("#FFD700"))
        p.end()

    # ── Properties dialog ────────────────────────────────────────────────────

    def _open_properties(self):
        from PySide6.QtCore import QTimer
        dlg = QDialog(self)
        dlg.setWindowTitle("Button Einstellungen")
        form = QFormLayout(dlg)

        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)

        act = QComboBox()
        for a in ButtonAction:
            act.addItem(a.value)
        act.setCurrentText(self.action.value)
        form.addRow("Aktion:", act)

        slot = QLineEdit(str(self.function_id) if self.function_id is not None else "")
        form.addRow("Executor-Slot:", slot)

        # Snapshot-Picker (sichtbar nur wenn Aktion = Snapshot)
        snap_row_lbl = QLabel("Snapshot-Slot:")
        snap_cb = QComboBox()
        snap_cb.setMinimumWidth(200)
        self._fill_snapshot_combo(snap_cb)
        snap_row_lbl.setVisible(self.action == ButtonAction.SNAPSHOT)
        snap_cb.setVisible(self.action == ButtonAction.SNAPSHOT)
        form.addRow(snap_row_lbl, snap_cb)

        def on_action_changed(text):
            is_snap = text == ButtonAction.SNAPSHOT.value
            snap_row_lbl.setVisible(is_snap)
            snap_cb.setVisible(is_snap)
            slot.setEnabled(not is_snap)

        act.currentTextChanged.connect(on_action_changed)
        on_action_changed(act.currentText())

        # Farbauswahl
        chosen_bg = [QColor(self._bg_color)]
        chosen_fg = [QColor(self._fg_color)]

        btn_bg = QPushButton()
        btn_bg.setFixedHeight(24)
        btn_bg.setStyleSheet(f"background-color: {chosen_bg[0].name()}; border: 1px solid #555;")

        btn_fg = QPushButton()
        btn_fg.setFixedHeight(24)
        btn_fg.setStyleSheet(f"background-color: {chosen_fg[0].name()}; border: 1px solid #555;")

        def pick_bg():
            c = QColorDialog.getColor(chosen_bg[0], dlg, "Hintergrundfarbe")
            if c.isValid():
                chosen_bg[0] = c
                btn_bg.setStyleSheet(f"background-color: {c.name()}; border: 1px solid #555;")

        def pick_fg():
            c = QColorDialog.getColor(chosen_fg[0], dlg, "Textfarbe")
            if c.isValid():
                chosen_fg[0] = c
                btn_fg.setStyleSheet(f"background-color: {c.name()}; border: 1px solid #555;")

        btn_bg.clicked.connect(pick_bg)
        btn_fg.clicked.connect(pick_fg)
        form.addRow("Hintergrundfarbe:", btn_bg)
        form.addRow("Textfarbe:", btn_fg)

        # MIDI-Bindung
        _binding = [self.midi_binding.copy() if self.midi_binding else None]

        def _binding_text():
            b = _binding[0]
            if b is None:
                return "Keine"
            return f"{b.get('msg_type','')} / CH{b.get('channel',0)} / Note/CC {b.get('data1',0)}"

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
                print(f"[VCButton] MIDI Learn Fehler: {e}")

        def on_clear_midi():
            _binding[0] = None
            midi_display.setText("Keine")

        btn_learn.clicked.connect(on_learn)
        btn_clear_midi.clicked.connect(on_clear_midi)

        midi_row = QWidget()
        midi_row_layout = QHBoxLayout(midi_row)
        midi_row_layout.setContentsMargins(0, 0, 0, 0)
        midi_row_layout.setSpacing(4)
        midi_row_layout.addWidget(midi_display, stretch=1)
        midi_row_layout.addWidget(btn_learn)
        midi_row_layout.addWidget(btn_clear_midi)
        form.addRow("MIDI-Bindung:", midi_row)

        ok_cancel = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok_cancel.accepted.connect(dlg.accept)
        ok_cancel.rejected.connect(dlg.reject)
        form.addRow(ok_cancel)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self.action = ButtonAction(act.currentText())
            if self.action == ButtonAction.SNAPSHOT:
                idx = snap_cb.currentData()
                self.snapshot_index = idx if isinstance(idx, int) else None
                self.function_id = None
            else:
                self.snapshot_index = None
                try:
                    self.function_id = int(slot.text())
                except ValueError:
                    self.function_id = None
            self._bg_color = chosen_bg[0]
            self._fg_color = chosen_fg[0]
            self.midi_binding = _binding[0]
            # APC Mini Exclude-Liste aktualisieren
            self._sync_apc_exclude()
            self.update()

    def _sync_apc_exclude(self):
        """Registriert/deregistriert diese Note bei APCMiniFeedback."""
        try:
            from src.core.midi.apc_mini_feedback import get_apc_feedback
            fb = get_apc_feedback()
            if fb is None:
                return
            b = self.midi_binding
            if b and b.get("msg_type") == "note_on":
                fb.exclude_note(b.get("data1", -1))
            # Alte Bindung freigeben ist nicht trivial ohne vorherigen Zustand
            # — wird beim naechsten Feedback-Update automatisch korrekt gesetzt
        except Exception:
            pass

    def _fill_snapshot_combo(self, combo: QComboBox):
        """Snapshot-ComboBox mit allen Slots befuellen."""
        try:
            from src.ui.views.snapshots_view import get_snapshots_view
            sv = get_snapshots_view()
            if sv is not None:
                for i in range(48):
                    snap = sv.get_snapshot(i)
                    if snap.is_empty():
                        label = f"Slot {i + 1}: (leer)"
                    else:
                        label = f"Slot {i + 1}: {snap.name or f'Snap {i + 1}'}"
                    combo.addItem(label, i)
                # Aktuellen Wert setzen
                if self.snapshot_index is not None:
                    combo.setCurrentIndex(self.snapshot_index)
                return
        except Exception as e:
            print(f"[vc_button] fill_snapshot_combo error: {e}")

        # Fallback: 48 leere Eintraege
        for i in range(48):
            combo.addItem(f"Slot {i + 1}", i)
        if self.snapshot_index is not None:
            combo.setCurrentIndex(self.snapshot_index)

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["action"] = self.action.value
        d["function_id"] = self.function_id
        d["snapshot_index"] = self.snapshot_index
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self.action = ButtonAction(d.get("action", "Toggle"))
        self.function_id = d.get("function_id")
        self.snapshot_index = d.get("snapshot_index")
