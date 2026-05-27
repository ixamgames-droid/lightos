"""Snapshots View - Quick-Save Buttons fuer Programmer States mit Ordner-Panel.

- Linke Seite: 12x4 Snapshot-Grid (Klick = Capture/Apply)
- Rechte Seite: Ordner-Struktur (Snaps per Drag einordnen, VC-Button erstellen)
- Save-Dialog: optionale Nullwerte fuer nicht-aktive Kanaele
"""
from __future__ import annotations
import os
import json
import copy
from typing import Optional

from PySide6.QtCore import Qt, QMimeData, QPoint
from PySide6.QtGui import QColor, QAction, QCursor, QDrag
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGridLayout, QLabel,
    QMenu, QInputDialog, QMessageBox, QFileDialog,
    QDialog, QScrollArea, QCheckBox, QDialogButtonBox, QLineEdit, QFrame,
    QSplitter, QTreeWidget, QTreeWidgetItem, QAbstractItemView, QApplication,
)

try:
    from src.core.app_state import get_state
except Exception:
    get_state = None  # type: ignore


SNAPSHOTS_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS"
)
SNAPSHOTS_FILE = os.path.join(SNAPSHOTS_DIR, "snapshots.json")
SNAPSHOT_COLS = 12
SNAPSHOT_ROWS = 4
SNAPSHOT_TOTAL = SNAPSHOT_COLS * SNAPSHOT_ROWS
SNAP_MIME = "application/x-lightos-snap-index"

# Singleton-Referenz damit VCButton auf die Snapshots zugreifen kann
_SNAPSHOTS_VIEW_REF: list["SnapshotsView"] = []


def get_snapshots_view() -> Optional["SnapshotsView"]:
    return _SNAPSHOTS_VIEW_REF[0] if _SNAPSHOTS_VIEW_REF else None


# ── Datenmodell ───────────────────────────────────────────────────────────────

class Snapshot:
    """Ein gespeicherter Programmer-State."""

    def __init__(self, name: str = "", values: dict | None = None):
        self.name = name
        self.values: dict[int, dict[str, int]] = values or {}

    def is_empty(self) -> bool:
        return not self.values

    def to_dict(self) -> dict:
        ser_vals = {}
        for fid, attrs in self.values.items():
            ser_vals[str(fid)] = dict(attrs)
        return {"name": self.name, "values": ser_vals}

    @classmethod
    def from_dict(cls, d: dict) -> "Snapshot":
        raw = d.get("values", {})
        vals: dict[int, dict[str, int]] = {}
        for k, v in raw.items():
            try:
                vals[int(k)] = {ak: int(av) for ak, av in v.items()}
            except Exception:
                pass
        return cls(name=d.get("name", ""), values=vals)


# Attributgruppen
_ATTR_GROUPS = [
    ("Intensity / Master",          {"intensity", "dimmer", "master"}),
    ("Farbe: Rot (R)",              {"color_r"}),
    ("Farbe: Gruen (G)",            {"color_g"}),
    ("Farbe: Blau (B)",             {"color_b"}),
    ("Farbe: Weiss / Amber / UV",   {"color_w", "color_a", "color_uv"}),
    ("Position  (Pan / Tilt)",      {"pan", "tilt", "pan_fine", "tilt_fine"}),
    ("Beam  (Shutter / Zoom / ...)",{"shutter", "strobe", "zoom", "focus", "frost", "iris", "prism"}),
    ("Gobo",                        {"gobo", "gobo_rotation", "gobo_wheel", "gobo1", "gobo2"}),
    ("Effekte",                     {"macro", "effect", "effect_speed", "prism_rot", "animation"}),
]

_ALL_KNOWN_ATTRS: set[str] = set()
for _, _s in _ATTR_GROUPS:
    _ALL_KNOWN_ATTRS.update(_s)


# ── Save-Dialog (mit Nullwerte-Option) ────────────────────────────────────────

class SnapshotSaveDialog(QDialog):
    """Dialog: Name + Attributgruppen + optionale Nullwerte fuer nicht-aktive Kanaele."""

    def __init__(self, parent, index: int, programmer_vals: dict):
        super().__init__(parent)
        self.setWindowTitle("Snapshot speichern")
        self.setModal(True)
        self.setMinimumWidth(460)
        self._programmer_vals = programmer_vals
        self._checkboxes: list[tuple[QCheckBox, set]] = []
        self._zero_checkboxes: list[tuple[QCheckBox, set]] = []
        self._setup_ui(index)

    def _setup_ui(self, index: int):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit(f"Snap {index + 1}")
        self._name_edit.selectAll()
        layout.addWidget(self._name_edit)

        layout.addWidget(self._separator())

        lbl = QLabel("Welche Attribute sollen gespeichert werden?")
        lbl.setStyleSheet("font-weight: bold; color: #ccc;")
        layout.addWidget(lbl)

        # Welche Attribute sind im Programmer?
        used_attrs: set[str] = set()
        for fid_attrs in self._programmer_vals.values():
            used_attrs.update(fid_attrs.keys())

        known_attrs: set[str] = set()
        for _, attr_set in _ATTR_GROUPS:
            known_attrs.update(attr_set)
        other_attrs = used_attrs - known_attrs

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(120)
        scroll.setMaximumHeight(200)
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setSpacing(3)
        vbox.setContentsMargins(4, 4, 4, 4)

        for group_label, attr_set in _ATTR_GROUPS:
            present = attr_set & used_attrs
            if not present:
                continue
            detail = ", ".join(sorted(present))
            cb = QCheckBox(f"{group_label}    ({detail})")
            cb.setChecked(True)
            vbox.addWidget(cb)
            self._checkboxes.append((cb, attr_set))

        if other_attrs:
            detail = ", ".join(sorted(other_attrs))
            cb = QCheckBox(f"Sonstige    ({detail})")
            cb.setChecked(True)
            vbox.addWidget(cb)
            self._checkboxes.append((cb, other_attrs))

        if not self._checkboxes:
            vbox.addWidget(QLabel("(Keine Attribute im Programmer)"))

        vbox.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll)

        btn_row = QHBoxLayout()
        b_all = QPushButton("Alle auswaehlen")
        b_none = QPushButton("Keine")
        b_all.clicked.connect(lambda: [cb.setChecked(True) for cb, _ in self._checkboxes])
        b_none.clicked.connect(lambda: [cb.setChecked(False) for cb, _ in self._checkboxes])
        btn_row.addWidget(b_all)
        btn_row.addWidget(b_none)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # ── Nullwerte-Sektion ──────────────────────────────────────────────────
        layout.addWidget(self._separator())

        lbl_zero = QLabel("Kanaele explizit auf 0 setzen (auch wenn nicht im Programmer):")
        lbl_zero.setStyleSheet("font-weight: bold; color: #aaa; font-size: 11px;")
        lbl_zero.setToolTip(
            "Diese Kanaele sind gerade NICHT im Programmer (also auf Standard-Wert).\n"
            "Du kannst sie trotzdem als 0 speichern – nuetzlich fuer z.B. 'Nur Rot': "
            "dann werden G=0, B=0, W=0 beim Apply explizit gesetzt."
        )
        layout.addWidget(lbl_zero)

        scroll2 = QScrollArea()
        scroll2.setWidgetResizable(True)
        scroll2.setMinimumHeight(70)
        scroll2.setMaximumHeight(130)
        container2 = QWidget()
        vbox2 = QVBoxLayout(container2)
        vbox2.setSpacing(3)
        vbox2.setContentsMargins(4, 4, 4, 4)

        # Gruppen die NICHT im Programmer sind (also gerade 0 / nicht gesetzt)
        groups_in_programmer: set[str] = set()
        for _, attr_set in self._checkboxes:
            groups_in_programmer.update(attr_set)

        any_zero = False
        for group_label, attr_set in _ATTR_GROUPS:
            if not (attr_set & groups_in_programmer):
                detail = ", ".join(sorted(attr_set))
                cb = QCheckBox(f"{group_label}    ({detail})")
                cb.setChecked(False)
                cb.setStyleSheet("color: #888;")
                vbox2.addWidget(cb)
                self._zero_checkboxes.append((cb, attr_set))
                any_zero = True

        if not any_zero:
            vbox2.addWidget(QLabel("(Alle bekannten Gruppen sind bereits im Programmer)"))

        vbox2.addStretch(1)
        scroll2.setWidget(container2)
        layout.addWidget(scroll2)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def _separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #444;")
        return line

    def snapshot_name(self) -> str:
        return self._name_edit.text().strip()

    def filtered_values(self) -> dict:
        """Programmer-Werte gefiltert + optionale Nullwerte fuer nicht-aktive Gruppen."""
        selected: set[str] = set()
        for cb, attr_set in self._checkboxes:
            if cb.isChecked():
                selected.update(attr_set)

        zero_selected: set[str] = set()
        for cb, attr_set in self._zero_checkboxes:
            if cb.isChecked():
                zero_selected.update(attr_set)

        result: dict[int, dict[str, int]] = {}

        # Vorhandene Programmer-Werte filtern
        for fid, attrs in self._programmer_vals.items():
            filtered = {k: v for k, v in attrs.items() if k in selected}
            if filtered:
                result[fid] = filtered

        # Explizite Nullwerte fuer alle Fixtures die im Programmer sind
        if zero_selected:
            for fid in self._programmer_vals.keys():
                if fid not in result:
                    result[fid] = {}
                for attr in zero_selected:
                    if attr not in result[fid]:
                        result[fid][attr] = 0

        return result


# ── Snapshot-Button (mit Drag-Support) ────────────────────────────────────────

class SnapshotButton(QPushButton):
    """Ein Snapshot-Slot Button – unterstuetzt Drag in Ordner."""

    def __init__(self, index: int, parent: "SnapshotsView"):
        super().__init__(parent)
        self._index = index
        self._view = parent
        self._drag_start_pos: QPoint | None = None
        self._drag_active = False
        self.setMinimumSize(80, 56)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.clicked.connect(self._on_click)
        self.setMouseTracking(True)
        self.refresh()

    def index(self) -> int:
        return self._index

    def refresh(self):
        snap = self._view.get_snapshot(self._index)
        if snap.is_empty():
            self.setText(f"{self._index + 1}\n(leer)")
            self.setStyleSheet(
                "QPushButton { background: #1a1a1a; color: #555; "
                "border: 1px dashed #333; }"
                "QPushButton:hover { background: #222; color: #888; }"
            )
        else:
            name = snap.name or f"Snap {self._index + 1}"
            count = len(snap.values)
            self.setText(f"{name}\n({count} FX)")
            self.setStyleSheet(
                "QPushButton { background: #2a3344; color: #FFD700; "
                "border: 1px solid #4f6391; font-weight: bold; }"
                "QPushButton:hover { background: #364463; }"
            )

    def mousePressEvent(self, event):
        snap = self._view.get_snapshot(self._index)
        if event.button() == Qt.MouseButton.LeftButton and not snap.is_empty():
            self._drag_start_pos = event.position().toPoint()
            self._drag_active = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._drag_start_pos is not None
                and event.buttons() & Qt.MouseButton.LeftButton
                and not self._drag_active):
            delta = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            if delta >= QApplication.startDragDistance():
                snap = self._view.get_snapshot(self._index)
                if not snap.is_empty():
                    self._drag_active = True
                    self._drag_start_pos = None
                    drag = QDrag(self)
                    mime = QMimeData()
                    mime.setData(SNAP_MIME, str(self._index).encode())
                    drag.setMimeData(mime)
                    drag.exec(Qt.DropAction.CopyAction)
                    self._drag_active = False
                    return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def _on_click(self):
        if self._drag_active:
            return
        snap = self._view.get_snapshot(self._index)
        if snap.is_empty():
            self._view.capture(self._index)
        else:
            self._view.apply(self._index)

    def _on_context_menu(self, _pos):
        menu = QMenu(self)
        snap = self._view.get_snapshot(self._index)
        if snap.is_empty():
            a_cap = menu.addAction("Capture aktueller Programmer")
            a_cap.triggered.connect(lambda: self._view.capture(self._index))
        else:
            a_apply = menu.addAction("Apply")
            a_apply.triggered.connect(lambda: self._view.apply(self._index))
            a_rename = menu.addAction("Umbenennen...")
            a_rename.triggered.connect(lambda: self._view.rename(self._index))
            a_export = menu.addAction("Exportieren...")
            a_export.triggered.connect(lambda: self._view.export(self._index))
            menu.addSeparator()
            a_del = menu.addAction("Loeschen")
            a_del.triggered.connect(lambda: self._view.delete(self._index))
        menu.exec(QCursor.pos())


# ── Ordner-Panel (rechte Seite) ───────────────────────────────────────────────

class FolderPanel(QWidget):
    """Ordner-Struktur fuer Snapshots: Snaps per Drag einordnen, VC-Button erstellen."""

    def __init__(self, snapshots_view: "SnapshotsView", parent=None):
        super().__init__(parent)
        self._view = snapshots_view
        self.setAcceptDrops(True)
        self.setMinimumWidth(180)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        header = QHBoxLayout()
        lbl = QLabel("Ordner")
        lbl.setStyleSheet("font-weight: bold; color: #ccc; font-size: 12px;")
        header.addWidget(lbl)
        header.addStretch()
        btn_new = QPushButton("+")
        btn_new.setFixedSize(24, 24)
        btn_new.setToolTip("Neuer Ordner erstellen")
        btn_new.setStyleSheet(
            "QPushButton { background: #1a3a1a; color: #9DFF52; "
            "border: 1px solid #2a6a2a; border-radius: 3px; font-weight: bold; font-size: 14px; }"
            "QPushButton:hover { background: #2a5a2a; }"
        )
        btn_new.clicked.connect(self._new_folder)
        header.addWidget(btn_new)
        layout.addLayout(header)

        # Schnell-Capture: Snap direkt aus Ordner-Panel aufnehmen
        btn_capture = QPushButton("Snap aufnehmen")
        btn_capture.setToolTip(
            "Aktuellen Programmer in den naechsten freien Slot speichern\n"
            "und optional direkt in einen Ordner einordnen"
        )
        btn_capture.setStyleSheet(
            "QPushButton { background: #2a3a1a; color: #FFD700; "
            "border: 1px solid #4a6a1a; border-radius: 3px; "
            "font-weight: bold; font-size: 11px; padding: 3px 6px; }"
            "QPushButton:hover { background: #3a5a2a; }"
        )
        btn_capture.clicked.connect(self._quick_capture)
        layout.addWidget(btn_capture)

        info = QLabel("Snap per Drag auf Ordner einordnen")
        info.setStyleSheet("color: #444; font-size: 10px; font-style: italic;")
        layout.addWidget(info)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.setStyleSheet("""
            QTreeWidget {
                background: #0d1117;
                color: #ccc;
                border: 1px solid #30363d;
                border-radius: 3px;
            }
            QTreeWidget::item { padding: 3px 2px; }
            QTreeWidget::item:hover { background: #1f2937; }
            QTreeWidget::item:selected { background: #0d4f8b; color: #fff; }
            QTreeWidget::branch:closed:has-children {
                border-image: none; image: none;
            }
        """)
        layout.addWidget(self._tree, 1)

    def refresh(self):
        """Baum aus _view._folders neu aufbauen."""
        self._tree.clear()
        for fi, folder in enumerate(self._view.get_folders()):
            folder_item = QTreeWidgetItem(self._tree)
            folder_item.setText(0, f"[+] {folder['name']}")
            folder_item.setForeground(0, QColor("#9DFF52"))
            folder_item.setData(0, Qt.ItemDataRole.UserRole, ("folder", fi))
            folder_item.setExpanded(True)

            for snap_idx in folder.get("snap_indices", []):
                snap = self._view.get_snapshot(snap_idx)
                name = snap.name if not snap.is_empty() else f"(leer {snap_idx + 1})"
                snap_item = QTreeWidgetItem(folder_item)
                snap_item.setText(0, f"  {snap_idx + 1}: {name}")
                snap_item.setData(0, Qt.ItemDataRole.UserRole, ("snap", fi, snap_idx))
                if snap.is_empty():
                    snap_item.setForeground(0, QColor("#555"))
                else:
                    snap_item.setForeground(0, QColor("#FFD700"))

    # ── Drag & Drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(SNAP_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(SNAP_MIME):
            # Ziel-Item hervorheben
            item = self._tree.itemAt(event.position().toPoint())
            if item is not None:
                self._tree.setCurrentItem(item)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(SNAP_MIME):
            event.ignore()
            return

        snap_idx = int(bytes(event.mimeData().data(SNAP_MIME)).decode())
        drop_pos = event.position().toPoint()
        item = self._tree.itemAt(drop_pos)

        folder_idx = None
        if item is not None:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data:
                if data[0] == "folder":
                    folder_idx = data[1]
                elif data[0] == "snap":
                    folder_idx = data[1]

        if folder_idx is None:
            # Kein Ordner getroffen: falls keiner existiert, neuen erstellen
            if not self._view.get_folders():
                name, ok = QInputDialog.getText(
                    self, "Neuer Ordner",
                    "Es gibt noch keine Ordner. Name fuer neuen Ordner:",
                    text="Neuer Ordner"
                )
                if ok and name.strip():
                    folder_idx = self._view.add_folder(name.strip())
                else:
                    event.ignore()
                    return
            else:
                event.ignore()
                return

        self._view.add_snap_to_folder(folder_idx, snap_idx)
        self.refresh()
        self._view._save_to_disk()
        event.acceptProposedAction()

    # ── Kontextmenue ─────────────────────────────────────────────────────────

    def _on_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        menu = QMenu(self)

        if item is None:
            menu.addAction("Neuer Ordner").triggered.connect(self._new_folder)
        else:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if not data:
                return
            if data[0] == "folder":
                fi = data[1]
                menu.addAction("Umbenennen...").triggered.connect(lambda: self._rename_folder(fi))
                menu.addAction("Ordner loeschen").triggered.connect(lambda: self._delete_folder(fi))
                menu.addSeparator()
                menu.addAction("Neuer Ordner").triggered.connect(self._new_folder)
            elif data[0] == "snap":
                fi, snap_idx = data[1], data[2]
                snap = self._view.get_snapshot(snap_idx)
                if not snap.is_empty():
                    menu.addAction("Apply (Programmer laden)").triggered.connect(
                        lambda: self._view.apply(snap_idx))
                    menu.addAction("Als VC Button erstellen...").triggered.connect(
                        lambda: self._create_vc_button(snap_idx))
                    menu.addSeparator()
                menu.addAction("Aus Ordner entfernen").triggered.connect(
                    lambda: self._remove_from_folder(fi, snap_idx))

        if menu.actions():
            menu.exec(self._tree.mapToGlobal(pos))

    # ── Ordner-Aktionen ───────────────────────────────────────────────────────

    def _new_folder(self):
        name, ok = QInputDialog.getText(self, "Neuer Ordner", "Name:", text="Neuer Ordner")
        if ok and name.strip():
            self._view.add_folder(name.strip())
            self._view._save_to_disk()

    def _rename_folder(self, fi: int):
        folders = self._view.get_folders()
        if fi >= len(folders):
            return
        name, ok = QInputDialog.getText(
            self, "Ordner umbenennen", "Neuer Name:", text=folders[fi]["name"]
        )
        if ok and name.strip():
            self._view.rename_folder(fi, name.strip())
            self._view._save_to_disk()

    def _delete_folder(self, fi: int):
        folders = self._view.get_folders()
        if fi >= len(folders):
            return
        reply = QMessageBox.question(
            self, "Ordner loeschen",
            f"Ordner '{folders[fi]['name']}' loeschen?\n(Die Snaps selbst bleiben erhalten.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._view.delete_folder(fi)
            self._view._save_to_disk()

    def _remove_from_folder(self, fi: int, snap_idx: int):
        self._view.remove_snap_from_folder(fi, snap_idx)
        self._view._save_to_disk()

    # ── VC Button erstellen ───────────────────────────────────────────────────

    def _create_vc_button(self, snap_idx: int):
        snap = self._view.get_snapshot(snap_idx)
        default_name = snap.name or f"Snap {snap_idx + 1}"
        caption, ok = QInputDialog.getText(
            self, "VC Button erstellen",
            "Beschriftung des Buttons:",
            text=default_name
        )
        if not ok or not caption.strip():
            return

        canvas = self._get_vc_canvas()
        if canvas is None:
            QMessageBox.warning(
                self, "Virtual Console nicht gefunden",
                "Die Virtual Console konnte nicht gefunden werden.\n"
                "Bitte zuerst zur Virtual Console wechseln und sicherstellen, "
                "dass das Fenster geoeffnet ist."
            )
            return

        try:
            from PySide6.QtCore import QPoint as _QP
            from src.ui.virtualconsole.vc_button import ButtonAction

            # Freie Position suchen (20px Raster, max 10 Versuche)
            pos = _QP(20, 20)
            for _ in range(10):
                occupied = any(
                    child.x() == pos.x() and child.y() == pos.y()
                    for child in canvas.children()
                    if hasattr(child, 'x') and callable(child.x)
                )
                if not occupied:
                    break
                pos = _QP(pos.x() + 130, pos.y())

            btn = canvas._add_widget("VCButton", pos)
            if btn is not None:
                btn.caption = caption.strip()
                btn.action = ButtonAction.SNAPSHOT
                btn.snapshot_index = snap_idx
                btn.update()
                QMessageBox.information(
                    self, "VC Button erstellt",
                    f"Button '{caption}' wurde zur Virtual Console hinzugefuegt.\n"
                    "Du kannst ihn dort verschieben und anpassen (Bearbeiten-Modus)."
                )
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))
            print(f"[folder_panel] create_vc_button error: {e}")

    def _quick_capture(self):
        """Programmer in naechsten freien Slot speichern + optional in Ordner legen."""
        # Naechsten leeren Slot finden
        free_idx = next(
            (i for i, s in enumerate(self._view._snapshots) if s.is_empty()), -1
        )
        if free_idx < 0:
            # Alle Slots belegt: automatisch neuen hinzufuegen
            self._view._add_slot_row()
            free_idx = next(
                (i for i, s in enumerate(self._view._snapshots) if s.is_empty()), -1
            )

        # Capture ausfuehren (oeffnet den Standard-Dialog)
        self._view.capture(free_idx)

        # Falls Snap jetzt belegt: Ordner anbieten
        snap = self._view.get_snapshot(free_idx)
        if snap.is_empty():
            return  # User hat Abbrechen gedrueckt

        folders = self._view.get_folders()
        if not folders:
            return

        # Fragen ob der neue Snap in einen Ordner soll
        items = [f["name"] for f in folders]
        items.insert(0, "(Kein Ordner)")
        item, ok = QInputDialog.getItem(
            self, "In Ordner einordnen?",
            f"Snap '{snap.name}' in Ordner einordnen:",
            items, 0, False
        )
        if ok and item != "(Kein Ordner)":
            fi = items.index(item) - 1  # -1 wegen "(Kein Ordner)" am Anfang
            self._view.add_snap_to_folder(fi, free_idx)
            self._view._save_to_disk()

    def _get_vc_canvas(self):
        """Sucht VCCanvas in allen Top-Level-Fenstern."""
        for w in QApplication.topLevelWidgets():
            if hasattr(w, "_vc_view") and hasattr(w._vc_view, "_canvas"):
                return w._vc_view._canvas
        return None


# ── Haupt-View ────────────────────────────────────────────────────────────────

class SnapshotsView(QWidget):
    """Snapshots-Ansicht mit Ordner-Panel (Splitter-Layout)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._snapshots: list[Snapshot] = [Snapshot() for _ in range(SNAPSHOT_TOTAL)]
        self._buttons: list[SnapshotButton] = []
        self._folders: list[dict] = []  # [{"name": str, "snap_indices": [int, ...]}, ...]
        self._grid_layout = None   # wird in _setup_ui gesetzt
        self._grid_widget = None

        # Singleton-Referenz fuer VCButton-Zugriff
        _SNAPSHOTS_VIEW_REF.clear()
        _SNAPSHOTS_VIEW_REF.append(self)

        self._setup_ui()
        self._load_from_disk()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        title = QLabel("Snapshots  –  Schnellzugriff auf gespeicherte Programmer-States")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #ccc;")
        root.addWidget(title)

        info = QLabel(
            "Leerer Slot klicken: Programmer speichern. "
            "Gefuellter Slot klicken: anwenden. "
            "Snap in Ordner ziehen (rechte Seite)."
        )
        info.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(info)

        # Toolbar
        tb = QHBoxLayout()
        b_clear = QPushButton("Alle leeren")
        b_clear.setObjectName("btn_danger")
        b_clear.clicked.connect(self._clear_all)
        tb.addWidget(b_clear)
        b_save = QPushButton("Speichern")
        b_save.clicked.connect(self._save_to_disk)
        tb.addWidget(b_save)
        b_load = QPushButton("Laden")
        b_load.clicked.connect(self._load_from_disk)
        tb.addWidget(b_load)
        b_import = QPushButton("Importieren...")
        b_import.clicked.connect(self._import_dialog)
        tb.addWidget(b_import)
        tb.addStretch(1)

        # Mehr Slots Button
        b_more = QPushButton("+ 12 Slots")
        b_more.setToolTip("12 weitere Snapshot-Slots hinzufuegen (eine neue Zeile)")
        b_more.setStyleSheet(
            "QPushButton { background: #1a2a3a; color: #58a6ff; "
            "border: 1px solid #2a4a6a; border-radius: 3px; padding: 0 8px; }"
            "QPushButton:hover { background: #2a3a5a; }"
        )
        b_more.clicked.connect(self._add_slot_row)
        tb.addWidget(b_more)
        root.addLayout(tb)

        # Slot-Zähler Label
        self._lbl_slots = QLabel(f"{SNAPSHOT_TOTAL} Slots")
        self._lbl_slots.setStyleSheet("color: #555; font-size: 10px;")
        root.addWidget(self._lbl_slots)

        # Splitter: Grid (links) + Ordner-Panel (rechts)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Linke Seite: Snap-Grid (scrollbar)
        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(4)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        for i in range(SNAPSHOT_TOTAL):
            row = i // SNAPSHOT_COLS
            col = i % SNAPSHOT_COLS
            btn = SnapshotButton(i, self)
            self._grid_layout.addWidget(btn, row, col)
            self._buttons.append(btn)

        left_scroll = QScrollArea()
        left_scroll.setWidget(self._grid_widget)
        left_scroll.setWidgetResizable(True)
        left_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        splitter.addWidget(left_scroll)

        # Rechte Seite: Ordner-Panel
        self._folder_panel = FolderPanel(self)
        splitter.addWidget(self._folder_panel)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([820, 240])

        root.addWidget(splitter, 1)

    # ── Slot-Erweiterung ──────────────────────────────────────────────────────

    def _add_slot_row(self):
        """12 neue leere Snapshot-Slots hinzufuegen (eine neue Grid-Zeile)."""
        start = len(self._snapshots)
        new_row = start // SNAPSHOT_COLS
        for i in range(SNAPSHOT_COLS):
            idx = start + i
            self._snapshots.append(Snapshot())
            btn = SnapshotButton(idx, self)
            self._grid_layout.addWidget(btn, new_row, i)
            self._buttons.append(btn)
        total = len(self._snapshots)
        self._lbl_slots.setText(f"{total} Slots")
        self._save_to_disk()

    # ── Ordner-API ────────────────────────────────────────────────────────────

    def get_folders(self) -> list[dict]:
        return self._folders

    def add_folder(self, name: str) -> int:
        self._folders.append({"name": name, "snap_indices": []})
        self._folder_panel.refresh()
        return len(self._folders) - 1

    def rename_folder(self, folder_idx: int, name: str):
        if 0 <= folder_idx < len(self._folders):
            self._folders[folder_idx]["name"] = name
            self._folder_panel.refresh()

    def delete_folder(self, folder_idx: int):
        if 0 <= folder_idx < len(self._folders):
            del self._folders[folder_idx]
            self._folder_panel.refresh()

    def add_snap_to_folder(self, folder_idx: int, snap_idx: int):
        if 0 <= folder_idx < len(self._folders):
            indices = self._folders[folder_idx]["snap_indices"]
            if snap_idx not in indices:
                indices.append(snap_idx)
                self._folder_panel.refresh()

    def remove_snap_from_folder(self, folder_idx: int, snap_idx: int):
        if 0 <= folder_idx < len(self._folders):
            indices = self._folders[folder_idx]["snap_indices"]
            if snap_idx in indices:
                indices.remove(snap_idx)
                self._folder_panel.refresh()

    # ── Snapshot-API ──────────────────────────────────────────────────────────

    def get_snapshot(self, index: int) -> Snapshot:
        return self._snapshots[index]

    def capture(self, index: int):
        if get_state is None:
            return
        try:
            state = get_state()
            vals = copy.deepcopy(state.programmer)
            if not vals:
                QMessageBox.information(
                    self, "Snapshot",
                    "Programmer ist leer - es gibt nichts zu speichern."
                )
                return
            dlg = SnapshotSaveDialog(self, index, vals)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            name = dlg.snapshot_name() or f"Snap {index + 1}"
            filtered = dlg.filtered_values()
            if not filtered:
                QMessageBox.information(
                    self, "Snapshot",
                    "Keine Attribute ausgewaehlt - Snapshot wurde nicht gespeichert."
                )
                return
            self._snapshots[index] = Snapshot(name=name, values=filtered)
            self._buttons[index].refresh()
            self._folder_panel.refresh()
            self._save_to_disk()
        except Exception as e:
            print(f"[snapshots] capture error: {e}")

    def apply(self, index: int):
        if get_state is None:
            return
        try:
            snap = self._snapshots[index]
            if snap.is_empty():
                return
            state = get_state()
            for fid, attrs in snap.values.items():
                for attr, val in attrs.items():
                    state.set_programmer_value(int(fid), attr, int(val))
        except Exception as e:
            print(f"[snapshots] apply error: {e}")

    def rename(self, index: int):
        snap = self._snapshots[index]
        name, ok = QInputDialog.getText(
            self, "Snapshot umbenennen", "Neuer Name:", text=snap.name
        )
        if ok:
            snap.name = name
            self._buttons[index].refresh()
            self._folder_panel.refresh()
            self._save_to_disk()

    def delete(self, index: int):
        reply = QMessageBox.question(
            self, "Snapshot loeschen",
            f"Snapshot {index + 1} '{self._snapshots[index].name}' wirklich loeschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._snapshots[index] = Snapshot()
            self._buttons[index].refresh()
            # Aus allen Ordnern entfernen
            for folder in self._folders:
                if index in folder["snap_indices"]:
                    folder["snap_indices"].remove(index)
            self._folder_panel.refresh()
            self._save_to_disk()

    def export(self, index: int):
        snap = self._snapshots[index]
        path, _ = QFileDialog.getSaveFileName(
            self, "Snapshot exportieren",
            f"{snap.name or 'snapshot'}.json",
            "JSON (*.json)"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(snap.to_dict(), f, indent=2, ensure_ascii=False)
            except Exception as e:
                QMessageBox.warning(self, "Export-Fehler", str(e))

    def _import_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Snapshot importieren", "", "JSON (*.json)"
        )
        if not path:
            return
        slot = next((i for i, s in enumerate(self._snapshots) if s.is_empty()), -1)
        if slot < 0:
            QMessageBox.warning(self, "Import", "Keine leeren Slots verfuegbar.")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._snapshots[slot] = Snapshot.from_dict(data)
            self._buttons[slot].refresh()
            self._save_to_disk()
        except Exception as e:
            QMessageBox.warning(self, "Import-Fehler", str(e))

    def _clear_all(self):
        total = len(self._snapshots)
        reply = QMessageBox.question(
            self, "Alle Snapshots loeschen",
            f"Alle {total} Snapshots wirklich loeschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._snapshots = [Snapshot() for _ in range(total)]
            for b in self._buttons:
                b.refresh()
            self._folder_panel.refresh()
            self._save_to_disk()

    # ── Persistenz ────────────────────────────────────────────────────────────

    def _save_to_disk(self):
        try:
            os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
            payload = {
                "snaps": [s.to_dict() for s in self._snapshots],
                "folders": self._folders,
            }
            with open(SNAPSHOTS_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[snapshots] save error: {e}")

    def _load_from_disk(self):
        if not os.path.exists(SNAPSHOTS_FILE):
            return
        try:
            with open(SNAPSHOTS_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)

            # Rueckwaertskompatibilitaet: altes Format war eine Liste
            if isinstance(payload, list):
                snaps_data = payload
                folders_data: list = []
            elif isinstance(payload, dict):
                snaps_data = payload.get("snaps", [])
                folders_data = payload.get("folders", [])
            else:
                return

            # Gespeicherte Slot-Anzahl kann groesser als SNAPSHOT_TOTAL sein
            saved_count = len(snaps_data)
            target_count = max(SNAPSHOT_TOTAL, saved_count)

            # Fehlende Grid-Buttons erstellen falls gespeicherte Anzahl groesser ist
            current_count = len(self._snapshots)
            if target_count > current_count and self._grid_layout is not None:
                for idx in range(current_count, target_count):
                    row = idx // SNAPSHOT_COLS
                    col = idx % SNAPSHOT_COLS
                    self._snapshots.append(Snapshot())
                    btn = SnapshotButton(idx, self)
                    self._grid_layout.addWidget(btn, row, col)
                    self._buttons.append(btn)

            new_list = []
            for i in range(target_count):
                if i < len(snaps_data):
                    new_list.append(Snapshot.from_dict(snaps_data[i] or {}))
                else:
                    new_list.append(Snapshot())
            self._snapshots = new_list
            self._folders = folders_data if isinstance(folders_data, list) else []

            # Slot-Zaehler aktualisieren
            if hasattr(self, "_lbl_slots"):
                self._lbl_slots.setText(f"{len(self._snapshots)} Slots")

            for b in self._buttons:
                b.refresh()
            self._folder_panel.refresh()
        except Exception as e:
            print(f"[snapshots] load error: {e}")
