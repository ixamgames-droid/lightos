"""VCFrame — Container widget with optional multi-page support."""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QCheckBox,
                                QSpinBox, QDialogButtonBox, QTabBar, QSizePolicy)
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from .vc_widget import VCWidget


class VCFrame(VCWidget):
    """Container that holds child VCWidgets. Supports multiple pages."""

    def __init__(self, caption: str = "Frame", parent=None):
        super().__init__(caption, parent)
        self._page_count: int = 1
        self._current_page: int = 0
        self._show_header: bool = True
        self._solo: bool = False        # Solo-Frame: nur 1 Child gleichzeitig aktiv (T0.4)
        self._bg_color = QColor("#161b22")
        self._fg_color = QColor("#8b949e")
        self._tab_height = 22
        self.resize(300, 200)
        self.setAcceptDrops(True)

    # ── Solo-Frame Logik (T0.4) ──────────────────────────────────────────────

    def is_solo(self) -> bool:
        return self._solo

    def set_solo(self, on: bool):
        self._solo = bool(on)
        self.update()

    def on_child_activated(self, child: VCWidget):
        """Wird vom VC-Button aufgerufen wenn er gepresst/aktiviert wird.
        Im Solo-Modus: alle anderen Children mit toggle-state werden released."""
        if not self._solo:
            return
        for c in self.findChildren(VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            if c is child:
                continue
            # VCButton-spezifisch: setze _state auf False und triggere
            if hasattr(c, "_state") and getattr(c, "_state", False):
                try:
                    c._state = False
                    if hasattr(c, "_trigger"):
                        c._trigger(False)
                    c.update()
                except Exception:
                    pass

    # ── Page management ───────────────────────────────────────────────────────

    def _content_rect(self) -> QRect:
        top = self._tab_height if self._show_header and self._page_count > 1 else 0
        return self.rect().adjusted(2, top + 2, -2, -2)

    def _tab_for_page(self, page: int) -> QRect:
        w = max(40, self.width() // self._page_count)
        return QRect(page * w, 0, w, self._tab_height)

    def switch_page(self, page: int):
        self._current_page = max(0, min(self._page_count - 1, page))
        for child in self.findChildren(VCWidget):
            p = child.property("vc_page") or 0
            child.setVisible(p == self._current_page)
        self.update()

    def add_child_to_page(self, widget: VCWidget, page: int = 0):
        widget.setParent(self)
        widget.setProperty("vc_page", page)
        widget.setVisible(page == self._current_page)
        if self._edit_mode:
            widget.set_edit_mode(True)
        widget.show()

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        pos = event.position().toPoint()
        if self._show_header and self._page_count > 1 and pos.y() < self._tab_height:
            w = max(40, self.width() // self._page_count)
            page = pos.x() // w
            self.switch_page(page)
            return
        super().mousePressEvent(event)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg_color)
        # Frame border - rot wenn Solo-Modus
        if self._solo:
            p.setPen(QPen(QColor("#e63946"), 2))
        else:
            p.setPen(QPen(QColor("#30363d"), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        if self._show_header:
            # Header bar
            header = QRect(0, 0, self.width(), self._tab_height)
            p.fillRect(header, QColor("#21262d"))
            if self._page_count <= 1:
                p.setPen(self._fg_color)
                p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                p.drawText(header, Qt.AlignmentFlag.AlignCenter, self.caption)
            else:
                # Page tabs
                w = max(40, self.width() // self._page_count)
                for i in range(self._page_count):
                    tab = self._tab_for_page(i)
                    if i == self._current_page:
                        p.fillRect(tab, QColor("#0d4f8b"))
                    p.setPen(QColor("#e6edf3") if i == self._current_page else self._fg_color)
                    p.setFont(QFont("Segoe UI", 8))
                    p.drawText(tab, Qt.AlignmentFlag.AlignCenter, f"P{i+1}")
        p.end()

    # ── Properties ───────────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Frame Einstellungen")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        pages = QSpinBox()
        pages.setRange(1, 10)
        pages.setValue(self._page_count)
        form.addRow("Seitenanzahl:", pages)
        header = QCheckBox()
        header.setChecked(self._show_header)
        form.addRow("Header anzeigen:", header)
        solo = QCheckBox("Solo-Frame (nur 1 Button gleichzeitig aktiv)")
        solo.setChecked(self._solo)
        form.addRow("Modus:", solo)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self._page_count = pages.value()
            self._show_header = header.isChecked()
            self._solo = solo.isChecked()
            self.update()

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["page_count"] = self._page_count
        d["show_header"] = self._show_header
        d["solo"] = self._solo
        children = []
        for child in self.findChildren(VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            cd = child.to_dict()
            cd["vc_page"] = child.property("vc_page") or 0
            children.append(cd)
        d["children"] = children
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self._page_count = d.get("page_count", 1)
        self._show_header = d.get("show_header", True)
        self._solo = d.get("solo", False)
