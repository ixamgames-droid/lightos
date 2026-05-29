"""VCWidget — Basisklasse aller Virtual-Console-Widgets."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QMenu, QSizePolicy
from PySide6.QtCore import Qt, QPoint, QRect, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QCursor, QAction


class VCWidget(QFrame):
    """Basisklasse — abstrakt, nicht direkt instanziieren."""

    HANDLE_SIZE = 8
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
        self._selected = False
        self._snap_grid = 0      # 0 = kein Snap, sonst Grid-Größe in Pixel
        self._drag_start = QPoint()
        self._orig_rect = QRect()
        self._bg_color = QColor("#2a2a2a")
        self._fg_color = QColor("#ffffff")
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    # ── Edit Mode ─────────────────────────────────────────────────────────────

    def set_edit_mode(self, enabled: bool):
        self._edit_mode = enabled
        if not enabled:
            self._selected = False
        self.setCursor(Qt.CursorShape.SizeAllCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.update()
        for child in self.findChildren(VCWidget):
            child.set_edit_mode(enabled)

    def set_snap_grid(self, grid: int):
        """Setzt die Snap-Grid-Größe (0 = kein Snap)."""
        self._snap_grid = grid
        for child in self.findChildren(VCWidget):
            child.set_snap_grid(grid)

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
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._deselect_siblings()
            self._selected = True
            self.update()
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
        delta = event.globalPosition().toPoint() - self._drag_start
        if self._dragging and self.parent():
            nx = max(0, self._orig_rect.x() + delta.x())
            ny = max(0, self._orig_rect.y() + delta.y())
            if self._snap_grid > 0:
                nx = round(nx / self._snap_grid) * self._snap_grid
                ny = round(ny / self._snap_grid) * self._snap_grid
            self.move(nx, ny)
            self.moved.emit(nx, ny)
        elif self._resizing:
            nw = max(self.MIN_SIZE[0], self._orig_rect.width() + delta.x())
            nh = max(self.MIN_SIZE[1], self._orig_rect.height() + delta.y())
            if self._snap_grid > 0:
                nw = round(nw / self._snap_grid) * self._snap_grid
                nh = round(nh / self._snap_grid) * self._snap_grid
            self.resize(nw, nh)
            self.resized.emit(nw, nh)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if self._edit_mode and event.button() == Qt.MouseButton.LeftButton:
            self._open_properties()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self._resizing = False
        event.accept()

    def _deselect_siblings(self):
        """Deselektiert alle anderen VCWidgets im selben Parent."""
        if self.parent() is not None:
            for sibling in self.parent().findChildren(VCWidget):
                if sibling is not self and sibling._selected:
                    sibling._selected = False
                    sibling.update()

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

    def handle_midi(self, msg) -> bool:
        """Verarbeitet eine MIDI-Message. Gibt True zurück wenn konsumiert."""
        return False

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
            p.fillRect(r.right() - hs, r.bottom() - hs, hs, hs, QColor("#0088ff"))
            if self._selected:
                p.setPen(QPen(QColor("#58d68d"), 2, Qt.PenStyle.SolidLine))
            else:
                p.setPen(QPen(QColor("#0088ff"), 1, Qt.PenStyle.DashLine))
            p.drawRect(r.adjusted(0, 0, -1, -1))
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
        }

    def apply_dict(self, d: dict):
        self.caption = d.get("caption", self.caption)
        self.setGeometry(d.get("x", 0), d.get("y", 0),
                         d.get("w", 120), d.get("h", 60))
        if "bg" in d:
            self._bg_color = QColor(d["bg"])
        if "fg" in d:
            self._fg_color = QColor(d["fg"])
