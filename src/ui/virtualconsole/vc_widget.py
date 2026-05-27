"""VCWidget — Basisklasse aller Virtual-Console-Widgets."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QMenu, QSizePolicy
from PySide6.QtCore import Qt, QPoint, QRect, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QCursor, QAction


class VCWidget(QFrame):
    """Basisklasse — abstrakt, nicht direkt instanziieren."""

    HANDLE_SIZE = 14
    MIN_SIZE = (40, 30)

    moved = Signal(int, int)       # x, y
    resized = Signal(int, int)     # w, h
    delete_requested = Signal()

    def __init__(self, caption: str = "", parent=None):
        super().__init__(parent)
        self.caption = caption
        self._edit_mode = False
        self._dragging = False
        self._resizing = False
        self._drag_start = QPoint()
        self._orig_rect = QRect()
        self._bg_color = QColor("#2a2a2a")
        self._fg_color = QColor("#ffffff")
        # MIDI-Bindung: {"msg_type": "note_on"/"cc", "channel": 1, "data1": 0, "port_filter": "APC"}
        self.midi_binding: dict | None = None
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    # ── Edit Mode ─────────────────────────────────────────────────────────────

    def set_edit_mode(self, enabled: bool):
        self._edit_mode = enabled
        self.setCursor(Qt.CursorShape.SizeAllCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.update()
        for child in self.findChildren(VCWidget):
            child.set_edit_mode(enabled)

    # ── Farben ────────────────────────────────────────────────────────────────

    def set_background_color(self, color: QColor):
        self._bg_color = color
        self.update()

    def set_foreground_color(self, color: QColor):
        self._fg_color = color
        self.update()

    # ── Maus-Events (Drag + Resize) ───────────────────────────────────────────

    def mousePressEvent(self, event):
        if not self._edit_mode:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())
            return
        pos = event.position().toPoint()
        if self._is_resize_handle(pos):
            self._resizing = True
        else:
            self._dragging = True
        self._drag_start = event.globalPosition().toPoint()
        self._orig_rect = self.geometry()
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._edit_mode:
            return
        pos = event.position().toPoint()
        delta = event.globalPosition().toPoint() - self._drag_start
        if self._dragging and self.parent():
            nx = max(0, self._orig_rect.x() + delta.x())
            ny = max(0, self._orig_rect.y() + delta.y())
            p = self.parent()
            grid = getattr(p, 'GRID', None) or getattr(p, '_GRID', 0)
            if getattr(p, '_snap_to_grid', False) and grid:
                nx = round(nx / grid) * grid
                ny = round(ny / grid) * grid
            self.move(nx, ny)
            self.moved.emit(nx, ny)
        elif self._resizing:
            nw = max(self.MIN_SIZE[0], self._orig_rect.width() + delta.x())
            nh = max(self.MIN_SIZE[1], self._orig_rect.height() + delta.y())
            self.resize(nw, nh)
            self.resized.emit(nw, nh)
        else:
            if self._is_resize_handle(pos):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            else:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
        event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self._resizing = False
        event.accept()

    def _is_resize_handle(self, pos: QPoint) -> bool:
        r = self.rect()
        hs = self.HANDLE_SIZE
        return (r.right() - hs <= pos.x() <= r.right() and
                r.bottom() - hs <= pos.y() <= r.bottom())

    def _show_context_menu(self, global_pos: QPoint):
        menu = QMenu(self)
        menu.addAction("Einstellungen...").triggered.connect(self._open_properties)
        menu.addAction("Löschen").triggered.connect(self.delete_requested.emit)
        menu.addAction("Vordergrund-Farbe").triggered.connect(self._pick_fg)
        menu.addAction("Hintergrund-Farbe").triggered.connect(self._pick_bg)
        menu.exec(global_pos)

    def _open_properties(self):
        pass  # override in subclasses

    def _pick_fg(self):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(self._fg_color, self, "Vordergrundfarbe")
        if c.isValid():
            self.set_foreground_color(c)

    def _pick_bg(self):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(self._bg_color, self, "Hintergrundfarbe")
        if c.isValid():
            self.set_background_color(c)

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg_color)
        if self._edit_mode:
            hs = self.HANDLE_SIZE
            r = self.rect()
            p.setPen(QPen(QColor("#0088ff"), 1, Qt.PenStyle.DashLine))
            p.drawRect(r.adjusted(0, 0, -1, -1))
            # Resize-Handle (diagonal gestreift)
            p.fillRect(r.right() - hs, r.bottom() - hs, hs, hs, QColor("#0088ff"))
            p.setPen(QPen(QColor("#ffffff"), 1))
            for i in range(3, hs, 4):
                p.drawLine(r.right() - hs + i, r.bottom() - 2,
                           r.right() - 2,      r.bottom() - hs + i)
        p.end()

    # ── Serialisierung ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        g = self.geometry()
        return {
            "type": self.__class__.__name__,
            "caption": self.caption,
            "x": g.x(), "y": g.y(),
            "w": g.width(), "h": g.height(),
            "bg": self._bg_color.name(),
            "fg": self._fg_color.name(),
            "midi_binding": self.midi_binding,
        }

    def apply_dict(self, d: dict):
        self.caption = d.get("caption", self.caption)
        self.setGeometry(d.get("x", 0), d.get("y", 0),
                         d.get("w", 120), d.get("h", 60))
        if "bg" in d:
            self._bg_color = QColor(d["bg"])
        if "fg" in d:
            self._fg_color = QColor(d["fg"])
        self.midi_binding = d.get("midi_binding")
