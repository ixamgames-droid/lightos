"""VCButton — Virtual Console Button Widget."""
from __future__ import annotations
from enum import Enum
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QComboBox, QKeySequenceEdit, QDialogButtonBox, QSizePolicy
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor, QFont, QKeySequence
from .vc_widget import VCWidget


class ButtonAction(str, Enum):
    TOGGLE   = "Toggle"
    FLASH    = "Flash"
    BLACKOUT = "Blackout"
    STOP_ALL = "StopAll"


class VCButton(VCWidget):
    """Pushbutton — Flash / Toggle / Blackout / StopAll."""

    def __init__(self, caption: str = "Button", parent=None):
        super().__init__(caption, parent)
        self.action = ButtonAction.TOGGLE
        self.function_id: int | None = None   # linked CueStack slot
        self._pressed = False
        self._bg_color = QColor("#1a3a5c")
        self._fg_color = QColor("#ffffff")
        self.resize(120, 60)

    # ── Action ───────────────────────────────────────────────────────────────

    def _trigger(self, press: bool):
        # Solo-Frame: parent informieren wenn dieser Button aktiviert wird (T0.4)
        if press:
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
            ex.press_btn("go")

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
        bg = self._bg_color.lighter(140) if self._pressed else self._bg_color
        p.fillRect(self.rect(), bg)
        p.setPen(self._fg_color)
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.caption)
        if self.action == ButtonAction.FLASH:
            p.fillRect(0, self.height() - 4, self.width(), 4, QColor("#ff8800"))
        elif self.action == ButtonAction.BLACKOUT:
            p.fillRect(0, self.height() - 4, self.width(), 4, QColor("#ff2222"))
        p.end()

    # ── Properties dialog ────────────────────────────────────────────────────

    def _open_properties(self):
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
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self.action = ButtonAction(act.currentText())
            try:
                self.function_id = int(slot.text())
            except ValueError:
                self.function_id = None
            self.update()

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["action"] = self.action.value
        d["function_id"] = self.function_id
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self.action = ButtonAction(d.get("action", "Toggle"))
        self.function_id = d.get("function_id")
