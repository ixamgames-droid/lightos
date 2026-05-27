"""VCLabel — Static text label widget."""
from __future__ import annotations
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QSpinBox, QDialogButtonBox
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor, QFont
from .vc_widget import VCWidget


class VCLabel(VCWidget):
    """Non-interactive text label."""

    def __init__(self, caption: str = "Label", parent=None):
        super().__init__(caption, parent)
        self._font_size = 10
        self._bg_color = QColor("#111111")
        self._fg_color = QColor("#cccccc")
        self.resize(120, 40)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg_color)
        p.setPen(self._fg_color)
        p.setFont(QFont("Segoe UI", self._font_size))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.caption)
        p.end()

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Label Einstellungen")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Text:", cap)
        fs = QSpinBox()
        fs.setRange(6, 48)
        fs.setValue(self._font_size)
        form.addRow("Schriftgröße:", fs)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text()
            self._font_size = fs.value()
            self.update()

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["font_size"] = self._font_size
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self._font_size = d.get("font_size", 10)
