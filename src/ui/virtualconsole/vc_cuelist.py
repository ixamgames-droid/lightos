"""VCCueList — Linked CueStack controller widget."""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QSpinBox,
                                QDialogButtonBox, QVBoxLayout, QHBoxLayout,
                                QPushButton, QListWidget, QListWidgetItem, QLabel,
                                QSizePolicy)
from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QPainter, QColor, QFont
from .vc_widget import VCWidget


class VCCueList(VCWidget):
    """Shows a CueStack's cue list with GO/BACK/STOP transport."""

    def __init__(self, caption: str = "Cueliste", parent=None):
        super().__init__(caption, parent)
        self.stack_slot: int = 0
        self._bg_color = QColor("#0d1117")
        self._fg_color = QColor("#e6edf3")
        self.resize(280, 320)
        self._setup_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(200)

    def _setup_ui(self):
        from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QPushButton, QListWidget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._title_label = QLabel(self.caption)
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setStyleSheet("color: #58a6ff; font-weight: bold; font-size: 10px;")
        layout.addWidget(self._title_label)

        self._cue_list = QListWidget()
        self._cue_list.setStyleSheet("""
            QListWidget { background: #161b22; color: #e6edf3; font-size: 9px; border: none; }
            QListWidget::item:selected { background: #1f6feb; }
            QListWidget::item:hover { background: #21262d; }
        """)
        layout.addWidget(self._cue_list)

        btn_row = QHBoxLayout()
        self._btn_back = QPushButton("◄◄")
        self._btn_go   = QPushButton("GO ►")
        self._btn_stop = QPushButton("■")
        for btn in (self._btn_back, self._btn_go, self._btn_stop):
            btn.setFixedHeight(28)
            btn.setStyleSheet("""
                QPushButton { background: #21262d; color: #e6edf3; border: 1px solid #30363d;
                              font-size: 9px; font-weight: bold; border-radius: 3px; }
                QPushButton:hover { background: #30363d; }
                QPushButton:pressed { background: #1f6feb; }
            """)
            btn_row.addWidget(btn)
        self._btn_go.setStyleSheet(self._btn_go.styleSheet() +
                                    "QPushButton { background: #0d4f8b; color: #58d68d; }")
        layout.addLayout(btn_row)

        self._btn_back.clicked.connect(self._do_back)
        self._btn_go.clicked.connect(self._do_go)
        self._btn_stop.clicked.connect(self._do_stop)

    # ── Transport ─────────────────────────────────────────────────────────────

    def _executor(self):
        try:
            from src.core.app_state import get_state
            state = get_state()
            executors = state.playback_engine.executors
            if self.stack_slot < len(executors):
                return executors[self.stack_slot]
        except Exception:
            pass
        return None

    def _do_go(self):
        ex = self._executor()
        if ex:
            ex.press_btn("go")

    def _do_back(self):
        ex = self._executor()
        if ex:
            ex.press_btn("back")

    def _do_stop(self):
        ex = self._executor()
        if ex:
            ex.press_btn("stop")

    def _refresh(self):
        ex = self._executor()
        if ex is None or ex.stack is None:
            return
        stack = ex.stack
        current = self._cue_list.count()
        if current != len(stack.cues):
            self._cue_list.clear()
            for cue in stack.cues:
                label = f"{cue.number:>6.1f}  {cue.label or '---'}"
                item = QListWidgetItem(label)
                self._cue_list.addItem(item)
        # Highlight current cue
        idx = stack.current_index
        if 0 <= idx < self._cue_list.count():
            self._cue_list.setCurrentRow(idx)

    # ── Edit mode pass-through ─────────────────────────────────────────────

    def set_edit_mode(self, enabled: bool):
        super().set_edit_mode(enabled)
        for btn in (self._btn_back, self._btn_go, self._btn_stop):
            btn.setEnabled(not enabled)
        self._cue_list.setEnabled(not enabled)

    # ── Properties ───────────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Cueliste-Einstellungen")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        slot = QSpinBox()
        slot.setRange(0, 19)
        slot.setValue(self.stack_slot)
        form.addRow("Executor-Slot:", slot)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self.stack_slot = slot.value()
            self._title_label.setText(self.caption)
            self.update()

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["stack_slot"] = self.stack_slot
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self.stack_slot = d.get("stack_slot", 0)
        if hasattr(self, "_title_label"):
            self._title_label.setText(self.caption)
