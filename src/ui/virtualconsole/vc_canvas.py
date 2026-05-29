"""VCCanvas — Free-form layout surface for all VC widgets."""
from __future__ import annotations
import json
from PySide6.QtWidgets import (QWidget, QScrollArea, QMenu, QFileDialog,
                                QMessageBox, QInputDialog, QSizePolicy)
from PySide6.QtCore import Qt, QPoint, QSize, Signal
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

    GRID = 8

    # Signale nach außen (für VirtualConsoleView)
    midi_learn_done = Signal()          # MIDI-Learn für Button abgeschlossen
    snapshot_assign_done = Signal()     # Snapshot-Assign abgeschlossen

    def __init__(self, parent=None):
        super().__init__(parent)
        self._edit_mode = False
        self._snap_to_grid = False
        self.setMinimumSize(QSize(1200, 800))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self._bg = QColor("#0d1117")

        # MIDI-Learn-Modus
        self._midi_learn_btn = None       # VCButton das auf MIDI wartet

        # Snapshot-Assign-Modus
        self._assign_snapshot_index: int | None = None  # welcher Snap zugewiesen wird
        self._awaiting_button_click_for: str | None = None

        self._setup_midi()

    # ── MIDI ─────────────────────────────────────────────────────────────────

    def _setup_midi(self):
        try:
            from src.core.midi.midi_manager import get_midi_manager
            get_midi_manager().subscribe(self._on_midi_raw)
        except Exception as e:
            print(f"[VCCanvas] MIDI-Subscribe-Fehler: {e}")

    def _on_midi_raw(self, msg):
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda m=msg: self._handle_midi(m))

    def _handle_midi(self, msg):
        # MIDI-Learn: nächste Message wird dem bewaffneten Button zugewiesen
        if self._midi_learn_btn is not None:
            btn = self._midi_learn_btn
            self._midi_learn_btn = None
            btn.accept_midi(msg.channel, msg.data1, msg.msg_type)
            self.midi_learn_done.emit()
            return

        # Dispatch an alle VCWidgets (VCButton, VCSlider, …)
        for widget in self.findChildren(VCWidget):
            widget.handle_midi(msg)

    # ── MIDI-Learn-Modus ─────────────────────────────────────────────────────

    def start_midi_learn(self):
        """
        Aktiviert MIDI-Learn: der nächste Klick auf einen VCButton bewaffnet ihn,
        die darauf folgende MIDI-Message wird ihm zugewiesen.
        """
        self._midi_learn_btn = None
        # Signalisiere allen Buttons dass sie für MIDI-Learn klickbar sind
        self._awaiting_button_click_for = "midi_learn"
        self.setCursor(Qt.CursorShape.CrossCursor)

    def cancel_midi_learn(self):
        if self._midi_learn_btn is not None:
            try:
                self._midi_learn_btn._midi_armed = False
                self._midi_learn_btn.update()
            except Exception:
                pass
        self._midi_learn_btn = None
        self._awaiting_button_click_for = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    # ── Snapshot-Assign-Modus ─────────────────────────────────────────────────

    def start_snapshot_assign(self, snapshot_index: int):
        """
        Aktiviert Assign-Modus: nächster Klick auf einen VCButton weist ihm
        den angegebenen Snapshot zu.
        """
        self._assign_snapshot_index = snapshot_index
        self._awaiting_button_click_for = "snapshot"
        self.setCursor(Qt.CursorShape.CrossCursor)

    def cancel_snapshot_assign(self):
        self._assign_snapshot_index = None
        self._awaiting_button_click_for = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    # ── Mausereignisse für Learn/Assign ──────────────────────────────────────

    def mousePressEvent(self, event):
        mode = getattr(self, "_awaiting_button_click_for", None)
        if mode and event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if child is not None:
                # VCButton-Elternteil suchen
                from .vc_button import VCButton
                btn = child if isinstance(child, VCButton) else None
                p = child.parent()
                while p is not None and not isinstance(p, VCCanvas):
                    if isinstance(p, VCButton):
                        btn = p
                        break
                    p = p.parent()

                if btn is not None:
                    if mode == "midi_learn":
                        self._midi_learn_btn = btn
                        btn.arm_midi_learn()
                        self._awaiting_button_click_for = None
                        self.setCursor(Qt.CursorShape.ArrowCursor)
                        return
                    elif mode == "snapshot":
                        from .vc_button import ButtonAction
                        btn.action = ButtonAction.SNAPSHOT
                        btn.snapshot_index = self._assign_snapshot_index
                        btn.update()
                        self._assign_snapshot_index = None
                        self._awaiting_button_click_for = None
                        self.setCursor(Qt.CursorShape.ArrowCursor)
                        self.snapshot_assign_done.emit()
                        return

            # Klick ins Leere bricht Modus ab
            self.cancel_midi_learn()
            self.cancel_snapshot_assign()
            return

        super().mousePressEvent(event)

    # ── Edit mode ────────────────────────────────────────────────────────────

    def set_edit_mode(self, enabled: bool):
        self._edit_mode = enabled
        for child in self.findChildren(VCWidget):
            child.set_edit_mode(enabled)
        self.update()

    def set_snap_to_grid(self, enabled: bool):
        self._snap_to_grid = enabled
        grid = self.GRID if enabled else 0
        for child in self.findChildren(VCWidget):
            child.set_snap_grid(grid)

    # ── Context menu ─────────────────────────────────────────────────────────

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
        w.set_snap_grid(self.GRID if self._snap_to_grid else 0)
        if d:
            w.apply_dict(d)
        else:
            snapped = QPoint(
                round(pos.x() / self.GRID) * self.GRID,
                round(pos.y() / self.GRID) * self.GRID,
            )
            w.move(snapped)
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

        # Hinweis wenn MIDI-Learn oder Snapshot-Assign aktiv
        mode = getattr(self, "_awaiting_button_click_for", None)
        if mode == "midi_learn":
            p.setPen(QColor("#ff8800"))
            p.drawText(self.rect().adjusted(8, 4, -8, 0),
                       Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                       "MIDI-Learn: Klicke einen Button an...")
        elif mode == "snapshot":
            p.setPen(QColor("#ffd700"))
            p.drawText(self.rect().adjusted(8, 4, -8, 0),
                       Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                       f"Snapshot zuweisen: Klicke einen Button an...")
        p.end()
