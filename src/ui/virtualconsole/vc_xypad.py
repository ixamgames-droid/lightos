"""VCXYPad — Pan/Tilt 2D control pad."""
from __future__ import annotations
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox
from PySide6.QtCore import Qt, QRect, QPoint, QPointF
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from .vc_widget import VCWidget


class VCXYPad(VCWidget):
    """2D Pad for Pan/Tilt control of selected fixtures."""

    def __init__(self, caption: str = "XY Pad", parent=None):
        super().__init__(caption, parent)
        self._pan: float = 0.5      # 0.0–1.0
        self._tilt: float = 0.5
        self._dragging_pad = False
        self.pan_attr  = "pan"
        self.tilt_attr = "tilt"
        self._fixture_ids: list[int] = []
        self._bg_color = QColor("#0d1117")
        self._fg_color = QColor("#58a6ff")
        self.resize(200, 200)

    # ── Pad area ─────────────────────────────────────────────────────────────

    def _pad_rect(self) -> QRect:
        m = 24
        return self.rect().adjusted(m, m, -m, -m)

    def _cursor_pos(self) -> QPoint:
        pr = self._pad_rect()
        x = int(pr.x() + self._pan * pr.width())
        y = int(pr.y() + self._tilt * pr.height())
        return QPoint(x, y)

    def _pos_to_value(self, pos: QPoint):
        pr = self._pad_rect()
        pan = max(0.0, min(1.0, (pos.x() - pr.x()) / pr.width()))
        tilt = max(0.0, min(1.0, (pos.y() - pr.y()) / pr.height()))
        self._pan = pan
        self._tilt = tilt
        self._apply()
        self.update()

    def _apply(self):
        from src.core.app_state import get_state
        state = get_state()
        pan_val  = int(self._pan * 255)
        tilt_val = int(self._tilt * 255)
        for fid in self._fixture_ids:
            state.set_programmer_value(fid, self.pan_attr,  pan_val)
            state.set_programmer_value(fid, self.tilt_attr, tilt_val)
        if not self._fixture_ids:
            # Apply to all patched fixtures with pan/tilt — defensive,
            # _patch_cache kann list oder dict sein
            try:
                patched = state.get_patched_fixtures()
            except Exception:
                patched = getattr(state, "_patch_cache", None) or []
            if isinstance(patched, dict):
                fids = list(patched.keys())
            else:
                fids = [getattr(f, "fid", None) for f in patched]
                fids = [fid for fid in fids if fid is not None]
            for fid in fids:
                state.set_programmer_value(fid, self.pan_attr,  pan_val)
                state.set_programmer_value(fid, self.tilt_attr, tilt_val)

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging_pad = True
            self._pos_to_value(event.position().toPoint())
        event.accept()

    def mouseMoveEvent(self, event):
        if self._edit_mode:
            super().mouseMoveEvent(event)
            return
        if self._dragging_pad:
            self._pos_to_value(event.position().toPoint())
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._edit_mode:
            super().mouseReleaseEvent(event)
            return
        self._dragging_pad = False
        event.accept()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg_color)

        pr = self._pad_rect()
        p.fillRect(pr, QColor("#111827"))

        # Grid
        pen = QPen(QColor("#1f2937"), 1, Qt.PenStyle.SolidLine)
        p.setPen(pen)
        step_x = pr.width() // 4
        step_y = pr.height() // 4
        for i in range(1, 4):
            p.drawLine(pr.x() + i * step_x, pr.y(), pr.x() + i * step_x, pr.bottom())
            p.drawLine(pr.x(), pr.y() + i * step_y, pr.right(), pr.y() + i * step_y)

        # Crosshair lines
        cp = self._cursor_pos()
        p.setPen(QPen(QColor("#0088ff"), 1, Qt.PenStyle.DashLine))
        p.drawLine(pr.x(), cp.y(), pr.right(), cp.y())
        p.drawLine(cp.x(), pr.y(), cp.x(), pr.bottom())

        # Cursor dot
        p.setPen(QPen(self._fg_color, 2))
        p.setBrush(self._fg_color)
        p.drawEllipse(cp, 6, 6)

        # Labels
        p.setPen(self._fg_color)
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(QRect(0, 0, self.width(), 20), Qt.AlignmentFlag.AlignCenter, self.caption)
        pan_pct  = int(self._pan * 100)
        tilt_pct = int(self._tilt * 100)
        p.setFont(QFont("Segoe UI", 7))
        p.drawText(QRect(0, self.height() - 20, self.width() // 2, 20),
                   Qt.AlignmentFlag.AlignCenter, f"P:{pan_pct}%")
        p.drawText(QRect(self.width() // 2, self.height() - 20, self.width() // 2, 20),
                   Qt.AlignmentFlag.AlignCenter, f"T:{tilt_pct}%")
        p.end()

    # ── Properties ───────────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("XY Pad Einstellungen")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        pan_a = QLineEdit(self.pan_attr)
        form.addRow("Pan-Attribut:", pan_a)
        tilt_a = QLineEdit(self.tilt_attr)
        form.addRow("Tilt-Attribut:", tilt_a)
        fids = QLineEdit(", ".join(str(f) for f in self._fixture_ids))
        form.addRow("Fixture-IDs (kommagetrennt):", fids)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self.pan_attr = pan_a.text() or "pan"
            self.tilt_attr = tilt_a.text() or "tilt"
            try:
                self._fixture_ids = [int(x.strip()) for x in fids.text().split(",") if x.strip()]
            except ValueError:
                pass
            self.update()

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["pan"] = self._pan
        d["tilt"] = self._tilt
        d["pan_attr"] = self.pan_attr
        d["tilt_attr"] = self.tilt_attr
        d["fixture_ids"] = self._fixture_ids
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self._pan = d.get("pan", 0.5)
        self._tilt = d.get("tilt", 0.5)
        self.pan_attr = d.get("pan_attr", "pan")
        self.tilt_attr = d.get("tilt_attr", "tilt")
        self._fixture_ids = d.get("fixture_ids", [])
