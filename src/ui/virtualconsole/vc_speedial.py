"""VCSpeedDial — Rotary speed control with tap-tempo."""
from __future__ import annotations
import time
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QDoubleSpinBox, QLineEdit, QDialogButtonBox,
    QSizePolicy, QComboBox,
)
from PySide6.QtCore import Qt, QRect, QPoint, QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QConicalGradient
import math
from .vc_widget import VCWidget


class SpeedTarget(str):
    EXECUTOR = "Executor"
    FUNCTION = "Function"


class VCSpeedDial(VCWidget):
    """Rotary dial controlling a function's speed + tap-tempo button."""

    def __init__(self, caption: str = "Speed", parent=None):
        super().__init__(caption, parent)
        self.function_id: int | None = None
        self.target_mode: str = SpeedTarget.EXECUTOR
        self._bpm: float = 120.0         # 20–600 BPM
        self._min_bpm: float = 20.0
        self._max_bpm: float = 600.0
        self._drag_y: int | None = None
        self._drag_start_bpm: float = 120.0
        self._tap_times: list[float] = []
        self._bg_color = QColor("#0d1117")
        self._fg_color = QColor("#58a6ff")
        self.resize(120, 140)

    # ── BPM ──────────────────────────────────────────────────────────────────

    @property
    def bpm(self) -> float:
        return self._bpm

    @bpm.setter
    def bpm(self, v: float):
        self._bpm = max(self._min_bpm, min(self._max_bpm, v))
        self._apply()
        self.update()

    def _apply(self):
        if self.function_id is None:
            return
        try:
            from src.core.app_state import get_state
            state = get_state()
            if self.target_mode == SpeedTarget.FUNCTION:
                fn = state.function_manager.get(int(self.function_id))
                if fn is None or not hasattr(fn, "speed"):
                    return
                fn.speed = max(0.05, min(20.0, self._bpm / 120.0))
                return

            executors = state.playback_engine.executors
            if self.function_id < len(executors):
                ex = executors[self.function_id]
                if ex.stack:
                    for cue in ex.stack.cues:
                        cue.fade_in = max(0.01, 60.0 / self._bpm)
        except Exception:
            pass

    def _tap(self):
        now = time.monotonic()
        self._tap_times.append(now)
        # Keep last 8 taps
        self._tap_times = self._tap_times[-8:]
        if len(self._tap_times) >= 2:
            intervals = [self._tap_times[i+1] - self._tap_times[i]
                         for i in range(len(self._tap_times) - 1)]
            avg = sum(intervals) / len(intervals)
            self.bpm = 60.0 / avg

    # ── Dial geometry ─────────────────────────────────────────────────────────

    def _dial_center(self) -> QPoint:
        return QPoint(self.width() // 2, self.height() // 2 - 10)

    def _dial_radius(self) -> int:
        return min(self.width(), self.height() - 40) // 2 - 6

    def _bpm_to_angle(self) -> float:
        t = (self._bpm - self._min_bpm) / (self._max_bpm - self._min_bpm)
        return -225 + t * 270   # degrees: -225° (min) → 45° (max)

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def _tap_rect(self) -> QRect:
        return QRect(4, self.height() - 28, self.width() - 8, 24)

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        pos = event.position().toPoint()
        if self._tap_rect().contains(pos):
            self._tap()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_y = pos.y()
            self._drag_start_bpm = self._bpm
        event.accept()

    def mouseMoveEvent(self, event):
        if self._edit_mode:
            super().mouseMoveEvent(event)
            return
        if self._drag_y is not None:
            dy = self._drag_y - event.position().toPoint().y()
            self.bpm = self._drag_start_bpm + dy * 2.0
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._edit_mode:
            super().mouseReleaseEvent(event)
            return
        self._drag_y = None
        event.accept()

    def wheelEvent(self, event):
        steps = event.angleDelta().y() // 120
        self.bpm = self._bpm + steps * 5.0

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg_color)

        cx = self._dial_center()
        r = self._dial_radius()

        # Track arc (background)
        p.setPen(QPen(QColor("#21262d"), 4))
        p.drawArc(cx.x() - r, cx.y() - r, r*2, r*2, int(225 * 16), int(-270 * 16))

        # Value arc
        t = (self._bpm - self._min_bpm) / (self._max_bpm - self._min_bpm)
        span_deg = int(t * 270)
        p.setPen(QPen(self._fg_color, 4))
        p.drawArc(cx.x() - r, cx.y() - r, r*2, r*2, int(225 * 16), int(-span_deg * 16))

        # Needle
        angle_rad = math.radians(self._bpm_to_angle())
        nx = cx.x() + int(math.cos(angle_rad) * (r - 4))
        ny = cx.y() - int(math.sin(angle_rad) * (r - 4))
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawLine(cx, QPoint(nx, ny))

        # Center dot
        p.setBrush(QColor("#30363d"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx, 6, 6)

        # BPM text
        p.setPen(self._fg_color)
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(QRect(cx.x() - 30, cx.y() - 10, 60, 20),
                   Qt.AlignmentFlag.AlignCenter, f"{self._bpm:.1f}")
        p.setFont(QFont("Segoe UI", 7))
        p.drawText(QRect(cx.x() - 20, cx.y() + 8, 40, 14),
                   Qt.AlignmentFlag.AlignCenter, "BPM")

        # Caption
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor("#8b949e"))
        p.drawText(QRect(0, 4, self.width(), 16),
                   Qt.AlignmentFlag.AlignCenter, self.caption)

        # Tap button
        tr = self._tap_rect()
        p.fillRect(tr, QColor("#21262d"))
        p.setPen(QColor("#e6edf3"))
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.drawText(tr, Qt.AlignmentFlag.AlignCenter, "TAP")
        p.end()

    # ── Properties ───────────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Speed Dial Einstellungen")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        bpm_sb = QDoubleSpinBox()
        bpm_sb.setRange(20, 600)
        bpm_sb.setValue(self._bpm)
        form.addRow("BPM:", bpm_sb)
        mode_cb = QComboBox()
        mode_cb.addItems([SpeedTarget.EXECUTOR, SpeedTarget.FUNCTION])
        mode_cb.setCurrentText(self.target_mode)
        form.addRow("Target:", mode_cb)
        slot = QLineEdit(str(self.function_id) if self.function_id is not None else "")
        form.addRow("Executor-Slot / Function-ID:", slot)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self.bpm = bpm_sb.value()
            self.target_mode = mode_cb.currentText()
            try:
                self.function_id = int(slot.text())
            except ValueError:
                self.function_id = None
            self.update()

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["bpm"] = self._bpm
        d["function_id"] = self.function_id
        d["target_mode"] = self.target_mode
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self._bpm = d.get("bpm", 120.0)
        self.function_id = d.get("function_id")
        self.target_mode = d.get("target_mode", SpeedTarget.EXECUTOR)
