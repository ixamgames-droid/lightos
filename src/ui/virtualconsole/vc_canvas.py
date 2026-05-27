"""VCCanvas — Free-form layout surface for all VC widgets."""
from __future__ import annotations
import json
from PySide6.QtWidgets import (QWidget, QScrollArea, QMenu, QFileDialog,
                                QMessageBox, QInputDialog, QSizePolicy)
from PySide6.QtCore import Qt, QPoint, QSize
from PySide6.QtGui import QPainter, QColor, QAction

from .vc_widget import VCWidget


WIDGET_REGISTRY: dict[str, type] = {}

def _register():
    from .vc_button   import VCButton
    from .vc_slider   import VCSlider
    from .vc_xypad    import VCXYPad
    from .vc_label    import VCLabel
    from .vc_cuelist  import VCCueList
    from .vc_speedial import VCSpeedDial
    from .vc_frame    import VCFrame
    WIDGET_REGISTRY.update({
        "VCButton":   VCButton,
        "VCSlider":   VCSlider,
        "VCXYPad":    VCXYPad,
        "VCLabel":    VCLabel,
        "VCCueList":  VCCueList,
        "VCSpeedDial":VCSpeedDial,
        "VCFrame":    VCFrame,
    })

_register()


class VCCanvas(QWidget):
    """The free-form canvas. Widgets are placed as direct children."""

    GRID = 8       # snap grid in pixels

    def __init__(self, parent=None):
        super().__init__(parent)
        self._edit_mode = False
        self._snap_to_grid = True
        self.setMinimumSize(QSize(1200, 800))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self._bg = QColor("#0d1117")
        try:
            from src.core.midi.midi_manager import get_midi_manager
            get_midi_manager().subscribe(self._on_midi)
        except Exception:
            pass

    def _on_midi(self, msg):
        """Leitet MIDI-Nachrichten an alle VC-Widgets mit passender Bindung weiter."""
        for child in self.findChildren(VCWidget):
            if hasattr(child, "handle_midi"):
                try:
                    child.handle_midi(msg)
                except Exception:
                    pass

    # ── Edit mode ────────────────────────────────────────────────────────────

    def set_edit_mode(self, enabled: bool):
        self._edit_mode = enabled
        for child in self.findChildren(VCWidget):
            child.set_edit_mode(enabled)
        self.update()

    def set_snap_to_grid(self, enabled: bool):
        self._snap_to_grid = enabled
        for child in self.findChildren(VCWidget):
            if hasattr(child, '_snap_to_grid'):
                child._snap_to_grid = enabled

    # ── Context menu (right-click on canvas) ──────────────────────────────────

    def _context_menu(self, local_pos: QPoint):
        if not self._edit_mode:
            return
        menu = QMenu(self)
        menu.setTitle("Widget hinzufügen")

        add_menu = menu.addMenu("Hinzufügen")
        for wtype in WIDGET_REGISTRY:
            act = add_menu.addAction(wtype.replace("VC", ""))
            act.setData((wtype, local_pos))

        menu.addSeparator()
        act_clear = menu.addAction("Alle löschen")
        act_save  = menu.addAction("Speichern als…")
        act_load  = menu.addAction("Laden…")

        chosen = menu.exec(self.mapToGlobal(local_pos))
        if chosen is None:
            return
        if chosen == act_clear:
            self._clear()
        elif chosen == act_save:
            self._save()
        elif chosen == act_load:
            self._load()
        elif chosen.data():
            wtype, pos = chosen.data()
            self._add_widget(wtype, pos)

    def _add_widget(self, wtype: str, pos: QPoint, d: dict | None = None):
        cls = WIDGET_REGISTRY.get(wtype)
        if cls is None:
            return
        w = cls(parent=self)
        w.set_edit_mode(self._edit_mode)
        if d:
            w.apply_dict(d)
        else:
            if self._snap_to_grid:
                pos = QPoint(
                    round(pos.x() / self.GRID) * self.GRID,
                    round(pos.y() / self.GRID) * self.GRID,
                )
            w.move(pos)
        w.delete_requested.connect(lambda widget=w: self._remove_widget(widget))
        w.show()
        return w

    def _remove_widget(self, widget: VCWidget):
        widget.hide()
        widget.setParent(None)
        widget.deleteLater()

    def _clear(self):
        for child in self.findChildren(VCWidget,
                                       options=Qt.FindChildOption.FindDirectChildrenOnly):
            child.setParent(None)
            child.deleteLater()

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        widgets = []
        for child in self.findChildren(VCWidget,
                                       options=Qt.FindChildOption.FindDirectChildrenOnly):
            widgets.append(child.to_dict())
        return {"widgets": widgets}

    def from_dict(self, d: dict):
        self._clear()
        for wd in d.get("widgets", []):
            wtype = wd.get("type", "")
            self._add_widget(wtype, QPoint(wd.get("x", 0), wd.get("y", 0)), wd)

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, "VC Layout speichern",
                                               "", "JSON (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)

    def _load(self):
        path, _ = QFileDialog.getOpenFileName(self, "VC Layout laden",
                                               "", "JSON (*.json)")
        if path:
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                self.from_dict(d)
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg)
        if self._edit_mode:
            p.setPen(QColor("#1f2937"))
            g = self.GRID * 4
            for x in range(0, self.width(), g):
                p.drawLine(x, 0, x, self.height())
            for y in range(0, self.height(), g):
                p.drawLine(0, y, self.width(), y)
        p.end()
