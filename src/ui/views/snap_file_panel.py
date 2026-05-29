"""Snap File Panel - Bibliothek und Dateimanager fuer Programmer-Snaps.

Features:
  - Baumansicht der gespeicherten Snaps nach Ordnern
  - Aktuellen Programmer als benannten Snap speichern (mit Kanal-Filter)
  - Snap aus Bibliothek auf Programmer anwenden (Doppelklick oder Button)
  - Ordner anlegen, umbenennen, Snaps und Ordner loeschen
  - Snaps per Drag & Drop oder "In Ordner verschieben" zwischen Ordnern bewegen
  - Rechtsklick-Kontextmenue
"""
from __future__ import annotations
import os
import json
import shutil
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTreeWidget,
    QAbstractItemView, QTreeWidgetItem, QLabel, QInputDialog, QMessageBox,
    QDialog, QCheckBox, QMenu, QFormLayout, QLineEdit,
    QDoubleSpinBox, QComboBox, QDialogButtonBox,
)
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QCursor

try:
    from src.core.app_state import get_state
except Exception:
    get_state = None  # type: ignore

SNAPS_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS", "snaps"
)

_ATTR_GROUPS = {
    "Intensity": {"intensity", "dimmer", "master"},
    "Color":     {"color_r", "color_g", "color_b", "color_w", "color_a", "color_uv",
                  "cyan", "magenta", "yellow", "color_wheel", "colour_wheel", "color"},
    "Position":  {"pan", "tilt", "pan_fine", "tilt_fine"},
    "Beam":      {"shutter", "strobe", "zoom", "focus", "frost", "iris", "prism"},
    "Gobo":      {"gobo", "gobo_rotation", "gobo_wheel", "gobo1", "gobo2", "gobo_rot"},
    "Effect":    {"macro", "effect", "effect_speed", "prism_rot", "animation"},
}
_ATTR_GROUP_ORDER = ["Intensity", "Color", "Position", "Beam", "Gobo", "Effect", "Other"]


def _classify_attr(attr: str) -> str:
    a = (attr or "").lower()
    for grp, names in _ATTR_GROUPS.items():
        if a in names:
            return grp
        for n in names:
            if n in a:
                return grp
    return "Other"


def _safe_filename(name: str) -> str:
    return "".join(c for c in name if c not in r'\/:*?"<>|').strip() or "snap"


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Kanal-Auswahl-Dialog
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ChannelSelectDialog(QDialog):
    """Zeigt Checkboxen pro Attribut-Gruppe. Nutzer waehlt, was gespeichert wird."""

    def __init__(self, programmer: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kanäle auswählen")
        self.setMinimumWidth(300)
        self._checks: dict[str, QCheckBox] = {}
        self._setup_ui(programmer)

    def _setup_ui(self, programmer: dict):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        lbl = QLabel("Welche Kanäle sollen gespeichert werden?")
        lbl.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl)

        # Zaehle Werte pro Gruppe
        counts: dict[str, int] = {}
        for attrs in programmer.values():
            for attr in attrs:
                grp = _classify_attr(attr)
                counts[grp] = counts.get(grp, 0) + 1

        for grp in _ATTR_GROUP_ORDER:
            count = counts.get(grp, 0)
            if count == 0:
                continue
            cb = QCheckBox(f"{grp}  ({count} Wert{'e' if count != 1 else ''})")
            cb.setChecked(True)
            layout.addWidget(cb)
            self._checks[grp] = cb

        if not self._checks:
            layout.addWidget(QLabel("Keine Werte im Programmer."))

        layout.addSpacing(4)
        btn_row = QHBoxLayout()
        btn_ok = QPushButton("OK")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def get_selected_groups(self) -> set[str]:
        return {grp for grp, cb in self._checks.items() if cb.isChecked()}

    def filter_programmer(self, programmer: dict) -> dict:
        """Gibt gefilterte Kopie des Programmers zurueck (nur gewaehlte Gruppen)."""
        selected = self.get_selected_groups()
        result: dict = {}
        for fid, attrs in programmer.items():
            filtered = {
                attr: val for attr, val in attrs.items()
                if _classify_attr(attr) in selected
            }
            if filtered:
                result[fid] = filtered
        return result


class ChaseCreateDialog(QDialog):
    """Dialog for turning multiple snaps into one sequence chase."""

    def __init__(self, default_name: str = "Snap Chase", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chase aus Snaps erstellen")
        self.setMinimumWidth(340)
        self._setup_ui(default_name)

    def _setup_ui(self, default_name: str):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name = QLineEdit(default_name)
        form.addRow("Name:", self._name)

        self._fade_in = QDoubleSpinBox()
        self._fade_in.setRange(0.0, 30.0)
        self._fade_in.setDecimals(2)
        self._fade_in.setValue(0.15)
        form.addRow("Fade In (s):", self._fade_in)

        self._hold = QDoubleSpinBox()
        self._hold.setRange(0.01, 120.0)
        self._hold.setDecimals(2)
        self._hold.setValue(0.80)
        form.addRow("Hold (s):", self._hold)

        self._fade_out = QDoubleSpinBox()
        self._fade_out.setRange(0.0, 30.0)
        self._fade_out.setDecimals(2)
        self._fade_out.setValue(0.10)
        form.addRow("Fade Out (s):", self._fade_out)

        self._speed = QDoubleSpinBox()
        self._speed.setRange(0.05, 20.0)
        self._speed.setDecimals(2)
        self._speed.setValue(1.0)
        form.addRow("Speed Multiplier:", self._speed)

        self._order = QComboBox()
        self._order.addItems(["Loop", "SingleShot", "PingPong"])
        form.addRow("Run Order:", self._order)

        self._direction = QComboBox()
        self._direction.addItems(["Forward", "Backward"])
        form.addRow("Direction:", self._direction)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        name = self._name.text().strip() or "Snap Chase"
        return {
            "name": name,
            "fade_in": float(self._fade_in.value()),
            "hold": float(self._hold.value()),
            "fade_out": float(self._fade_out.value()),
            "speed": float(self._speed.value()),
            "order": self._order.currentText(),
            "direction": self._direction.currentText(),
        }


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Snap File Panel
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_ROLE_PATH = Qt.ItemDataRole.UserRole
_ROLE_KIND = Qt.ItemDataRole.UserRole + 1   # "snap" | "folder"


class _SnapTree(QTreeWidget):
    """QTreeWidget mit Drag & Drop zum Verschieben von Snaps zwischen Ordnern."""

    def __init__(self, panel: "SnapFilePanel", parent=None):
        super().__init__(parent)
        self._panel = panel
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

    def dropEvent(self, event):
        target_item = self.itemAt(event.position().toPoint())
        dragged = self.selectedItems()
        if not dragged:
            event.ignore()
            return

        dragged_item = dragged[0]
        src_path = dragged_item.data(0, _ROLE_PATH)
        src_kind = dragged_item.data(0, _ROLE_KIND)

        if src_kind != "snap":
            event.ignore()
            return

        if target_item is None:
            dest_dir = SNAPS_DIR
        else:
            tgt_kind = target_item.data(0, _ROLE_KIND)
            tgt_path = target_item.data(0, _ROLE_PATH)
            if tgt_kind == "folder":
                dest_dir = tgt_path
            else:
                dest_dir = str(Path(tgt_path).parent)

        src = Path(src_path)
        dst = Path(dest_dir) / src.name

        if src.parent == Path(dest_dir):
            event.ignore()
            return

        if dst.exists():
            QMessageBox.warning(self._panel, "Fehler",
                f"Snap '{src.stem}' existiert bereits in diesem Ordner.")
            event.ignore()
            return

        try:
            shutil.move(str(src), str(dst))
            self._panel._refresh_tree()
        except Exception as e:
            QMessageBox.warning(self._panel, "Fehler", str(e))

        event.accept()


class SnapFilePanel(QWidget):
    """Dateimanager-Panel fuer die Snap-Bibliothek."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._refresh_tree()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        hdr = QLabel("Snap-Bibliothek")
        hdr.setStyleSheet("font-weight: bold; font-size: 12px; color: #ccc;")
        layout.addWidget(hdr)

        # Toolbar
        tb = QHBoxLayout()
        tb.setSpacing(4)

        b_save = QPushButton("Speichern")
        b_save.setFixedHeight(24)
        b_save.setToolTip("Aktuellen Programmer hier speichern")
        b_save.clicked.connect(self._save_snap)

        b_folder = QPushButton("Ordner +")
        b_folder.setFixedHeight(24)
        b_folder.clicked.connect(self._new_folder)

        b_apply = QPushButton("Anwenden")
        b_apply.setFixedHeight(24)
        b_apply.clicked.connect(self._apply_selected)

        b_chase = QPushButton("Chase +")
        b_chase.setFixedHeight(24)
        b_chase.setToolTip("Aus mehreren selektierten Snaps eine Sequence/Chase erzeugen")
        b_chase.clicked.connect(self._create_chase_from_selection)

        b_del = QPushButton("Löschen")
        b_del.setFixedHeight(24)
        b_del.setStyleSheet("color: #ff6666;")
        b_del.clicked.connect(self._delete_selected)

        b_ref = QPushButton("↻")
        b_ref.setFixedSize(24, 24)
        b_ref.setToolTip("Aktualisieren")
        b_ref.clicked.connect(self._refresh_tree)

        for btn in [b_save, b_folder, b_apply, b_chase, b_del, b_ref]:
            tb.addWidget(btn)
        layout.addLayout(tb)

        # Tree mit Drag & Drop
        self._tree = _SnapTree(self)
        self._tree.setHeaderLabel("Name")
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._context_menu)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._tree, stretch=1)

    # â”€â”€ Baum aufbauen â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _refresh_tree(self):
        self._tree.clear()
        os.makedirs(SNAPS_DIR, exist_ok=True)
        self._populate(self._tree.invisibleRootItem(), Path(SNAPS_DIR))

    def _populate(self, parent: QTreeWidgetItem, directory: Path):
        try:
            entries = sorted(directory.iterdir(),
                             key=lambda p: (p.is_file(), p.name.lower()))
        except Exception:
            return
        for entry in entries:
            if entry.is_dir():
                item = QTreeWidgetItem(parent, [entry.name])
                item.setData(0, _ROLE_PATH, str(entry))
                item.setData(0, _ROLE_KIND, "folder")
                item.setExpanded(True)
                self._populate(item, entry)
            elif entry.suffix == ".json":
                item = QTreeWidgetItem(parent, [entry.stem])
                item.setData(0, _ROLE_PATH, str(entry))
                item.setData(0, _ROLE_KIND, "snap")

    # â”€â”€ Hilfs-Methoden â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _selected(self) -> tuple[str | None, str | None]:
        items = self._tree.selectedItems()
        if not items:
            return None, None
        item = items[0]
        return (item.data(0, _ROLE_PATH), item.data(0, _ROLE_KIND))

    def _selected_snap_paths(self) -> list[str]:
        paths: list[str] = []
        for item in self._tree.selectedItems():
            path = item.data(0, _ROLE_PATH)
            kind = item.data(0, _ROLE_KIND)
            if kind == "snap" and path:
                paths.append(str(path))
        return paths

    def _target_dir(self) -> str:
        path, kind = self._selected()
        if kind == "folder" and path:
            return path
        if kind == "snap" and path:
            return str(Path(path).parent)
        return SNAPS_DIR

    # â”€â”€ Aktionen â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _save_snap(self):
        if get_state is None:
            return
        try:
            state = get_state()
            prog = state.programmer
            if not prog:
                QMessageBox.information(self, "Snap speichern",
                    "Programmer ist leer - nichts zu speichern.")
                return

            dlg = ChannelSelectDialog(prog, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            filtered = dlg.filter_programmer(prog)
            if not filtered:
                QMessageBox.information(self, "Snap speichern",
                    "Keine Kanäle ausgewählt.")
                return

            name, ok = QInputDialog.getText(self, "Snap speichern", "Name:")
            if not ok or not name.strip():
                return

            save_dir = self._target_dir()
            os.makedirs(save_dir, exist_ok=True)

            filepath = os.path.join(save_dir, f"{_safe_filename(name.strip())}.json")
            snap_data = {
                "name": name.strip(),
                "values": {str(fid): attrs for fid, attrs in filtered.items()},
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(snap_data, f, indent=2, ensure_ascii=False)

            self._refresh_tree()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _new_folder(self):
        target = self._target_dir()
        name, ok = QInputDialog.getText(self, "Neuer Ordner", "Ordner-Name:")
        if not ok or not name.strip():
            return
        try:
            os.makedirs(os.path.join(target, _safe_filename(name.strip())), exist_ok=True)
            self._refresh_tree()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _apply_selected(self):
        path, kind = self._selected()
        if kind == "snap" and path:
            self._apply_snap(path)

    def _apply_snap(self, filepath: str):
        if get_state is None:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            state = get_state()
            for fid_str, attrs in data.get("values", {}).items():
                fid = int(fid_str)
                for attr, val in attrs.items():
                    state.set_programmer_value(fid, attr, int(val))
        except Exception as e:
            QMessageBox.warning(self, "Fehler beim Anwenden", str(e))

    def _read_snap_values(self, filepath: str) -> tuple[str, dict] | None:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        raw_vals = data.get("values", {})
        if not isinstance(raw_vals, dict):
            return None

        clean_vals: dict[str, dict[str, int]] = {}
        for fid_key, attrs in raw_vals.items():
            try:
                fid = int(fid_key)
            except Exception:
                continue
            if not isinstance(attrs, dict):
                continue
            clean_attrs: dict[str, int] = {}
            for attr, val in attrs.items():
                try:
                    clean_attrs[str(attr)] = max(0, min(255, int(val)))
                except Exception:
                    continue
            if clean_attrs:
                clean_vals[str(fid)] = clean_attrs
        if not clean_vals:
            return None

        snap_name = str(data.get("name") or Path(filepath).stem)
        return snap_name, clean_vals

    def _create_chase_from_selection(self):
        snap_paths = self._selected_snap_paths()
        if len(snap_paths) < 2:
            QMessageBox.information(
                self,
                "Chase erstellen",
                "Bitte mindestens zwei Snap-Dateien markieren.",
            )
            return

        dlg = ChaseCreateDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        opts = dlg.values()

        snap_payloads: list[tuple[str, dict]] = []
        for path in snap_paths:
            snap_data = self._read_snap_values(path)
            if snap_data is not None:
                snap_payloads.append(snap_data)
        if len(snap_payloads) < 2:
            QMessageBox.warning(
                self,
                "Chase erstellen",
                "Zu wenige gueltige Snaps gefunden (mindestens 2 mit Werten noetig).",
            )
            return

        try:
            from src.core.engine.function import RunOrder, Direction
            from src.core.engine.function_manager import get_function_manager
            from src.core.engine.sequence import SequenceStep
        except Exception as e:
            QMessageBox.warning(self, "Chase erstellen", f"Engine-Import fehlgeschlagen: {e}")
            return

        fm = get_function_manager()
        seq = fm.new_sequence(opts["name"])
        seq.speed = float(opts["speed"])
        try:
            seq.run_order = RunOrder(str(opts["order"]))
        except Exception:
            seq.run_order = RunOrder.Loop
        try:
            seq.direction = Direction(str(opts["direction"]))
        except Exception:
            seq.direction = Direction.Forward

        bound: set[int] = set()
        for snap_name, snap_values in snap_payloads:
            for fid_str in snap_values.keys():
                try:
                    bound.add(int(fid_str))
                except Exception:
                    continue
            seq.steps.append(
                SequenceStep(
                    values=snap_values,
                    fade_in=float(opts["fade_in"]),
                    hold=float(opts["hold"]),
                    fade_out=float(opts["fade_out"]),
                    note=snap_name,
                )
            )
        seq.bound_fixtures = sorted(bound)

        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.emit(SyncEvent.FUNCTION_CHANGED, {"id": seq.id})
            sync.emit(SyncEvent.REFRESH_ALL, None)
        except Exception:
            pass

        QMessageBox.information(
            self,
            "Chase erstellt",
            (
                f"Sequence '{seq.name}' erstellt.\n"
                f"Function-ID: {seq.id}\n"
                f"Steps: {len(seq.steps)}\n\n"
                "Virtual Console Tipp:\n"
                "Button Aktion auf 'FunctionToggle' und Function-ID setzen.\n"
                "SpeedDial Target auf 'Function' und gleiche Function-ID setzen."
            ),
        )

    def _delete_selected(self):
        path, kind = self._selected()
        if not path or not kind:
            return
        display = Path(path).stem if kind == "snap" else Path(path).name
        if kind == "folder":
            reply = QMessageBox.question(self, "Ordner löschen",
                f"Ordner '{display}' und alle Inhalte wirklich löschen?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    shutil.rmtree(path)
                    self._refresh_tree()
                except Exception as e:
                    QMessageBox.warning(self, "Fehler", str(e))
        else:
            reply = QMessageBox.question(self, "Snap löschen",
                f"Snap '{display}' wirklich löschen?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    os.remove(path)
                    self._refresh_tree()
                except Exception as e:
                    QMessageBox.warning(self, "Fehler", str(e))

    def _on_double_click(self, item: QTreeWidgetItem, _col: int):
        path = item.data(0, _ROLE_PATH)
        kind = item.data(0, _ROLE_KIND)
        if kind == "snap" and path:
            self._apply_snap(path)

    def _context_menu(self, _pos):
        path, kind = self._selected()
        menu = QMenu(self)
        if kind == "snap":
            menu.addAction("Anwenden").triggered.connect(self._apply_selected)
            menu.addAction("Chase aus Auswahl erstellen").triggered.connect(
                self._create_chase_from_selection
            )
            menu.addSeparator()
            menu.addAction("Umbenennen...").triggered.connect(self._rename_selected)
            move_menu = menu.addMenu("In Ordner verschieben")
            act_root = move_menu.addAction("(Stammordner)")
            act_root.triggered.connect(lambda: self._move_to(SNAPS_DIR))
            folders = self._collect_folders()
            if folders:
                move_menu.addSeparator()
            for display, fpath in folders:
                act = move_menu.addAction(display)
                act.triggered.connect(lambda checked, p=fpath: self._move_to(p))
            menu.addSeparator()
            menu.addAction("Löschen").triggered.connect(self._delete_selected)
        elif kind == "folder":
            menu.addAction("Unterordner erstellen").triggered.connect(self._new_folder)
            menu.addAction("Umbenennen...").triggered.connect(self._rename_selected)
            menu.addSeparator()
            menu.addAction("Ordner löschen").triggered.connect(self._delete_selected)
        else:
            menu.addAction("Snap speichern").triggered.connect(self._save_snap)
            menu.addAction("Ordner erstellen").triggered.connect(self._new_folder)
        if not menu.isEmpty():
            menu.exec(QCursor.pos())

    # â”€â”€ Neue Aktionen â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _collect_folders(self) -> list[tuple[str, str]]:
        """Sammelt alle Ordner im Baum als (Anzeigename, Pfad)-Paare."""
        result: list[tuple[str, str]] = []

        def walk(item: QTreeWidgetItem, parts: list[str]):
            for i in range(item.childCount()):
                child = item.child(i)
                if child.data(0, _ROLE_KIND) == "folder":
                    name = child.text(0)
                    fpath = child.data(0, _ROLE_PATH)
                    new_parts = parts + [name]
                    display = " / ".join(new_parts)
                    result.append((display, fpath))
                    walk(child, new_parts)

        walk(self._tree.invisibleRootItem(), [])
        return result

    def _rename_selected(self):
        path, kind = self._selected()
        if not path or kind not in ("snap", "folder"):
            return
        old_name = Path(path).stem if kind == "snap" else Path(path).name
        new_name, ok = QInputDialog.getText(
            self, "Umbenennen", "Neuer Name:", text=old_name
        )
        if not ok or not new_name.strip():
            return
        safe = _safe_filename(new_name.strip())
        parent_dir = str(Path(path).parent)
        new_path = os.path.join(parent_dir, f"{safe}.json" if kind == "snap" else safe)
        if os.path.exists(new_path):
            QMessageBox.warning(self, "Fehler",
                "Ein Element mit diesem Namen existiert bereits.")
            return
        try:
            os.rename(path, new_path)
            if kind == "snap":
                try:
                    with open(new_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    data["name"] = new_name.strip()
                    with open(new_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass
            self._refresh_tree()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _move_to(self, dest_dir: str):
        path, kind = self._selected()
        if kind != "snap" or not path:
            return
        src = Path(path)
        dst = Path(dest_dir) / src.name
        if src.parent == Path(dest_dir):
            return
        if dst.exists():
            QMessageBox.warning(self, "Fehler",
                f"In diesem Ordner existiert bereits ein Snap mit dem Namen '{src.stem}'.")
            return
        try:
            shutil.move(str(src), str(dst))
            self._refresh_tree()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))




