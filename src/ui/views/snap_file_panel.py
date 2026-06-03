"""Snap File Panel - Bibliotheks-Panel fuer show-gebundene Programmer-Snaps.

Speicher: src.core.engine.snap_library (mit der Show serialisiert, nicht mehr als
globale Einzeldateien). Siehe docs/PROGRAMMER_REBUILD.md (Phase 2).

Features:
  - Baumansicht der Snaps nach (verschachtelbaren) Ordnern, Snaps gelb markiert
  - Aktuellen Programmer als benannten Snap speichern (mit Kanal-Filter)
  - Snap auf Programmer anwenden (Doppelklick oder Button)
  - Ordner anlegen, umbenennen, Snaps und Ordner loeschen
  - Snaps per Drag & Drop oder "In Ordner verschieben" zwischen Ordnern bewegen
  - Rechtsklick-Kontextmenue
"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTreeWidget,
    QAbstractItemView, QTreeWidgetItem, QLabel, QInputDialog, QMessageBox,
    QDialog, QCheckBox, QMenu, QFormLayout, QLineEdit,
    QDoubleSpinBox, QComboBox, QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QColor

try:
    from src.core.app_state import get_state
except Exception:
    get_state = None  # type: ignore

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

_ROLE_REF = Qt.ItemDataRole.UserRole       # Snap-ID (int) | Ordnerpfad (str)
_ROLE_KIND = Qt.ItemDataRole.UserRole + 1  # "snap" | "folder"
# Rückwärtskompatibler Alias (frühere Versionen nutzten _ROLE_PATH).
_ROLE_PATH = _ROLE_REF

# Farbcode der Bibliothek (Phase 3): Snaps gelb, Funktionen je Typ eingefärbt,
# damit auf einen Blick klar ist „was ist was". Siehe docs/PROGRAMMER_REBUILD.md.
_SNAP_COLOR = QColor("#FFD700")
_FUNC_COLOR_DEFAULT = QColor("#5ec8ff")
_FUNC_COLORS = {
    "Scene":     "#5ec8ff",   # hellblau
    "Chaser":    "#ff9a55",   # orange
    "Sequence":  "#ff77bb",   # pink
    "Collection":"#b388ff",   # violett
    "RGBMatrix": "#ffd166",   # gold-orange
    "Audio":     "#9aa0a6",   # grau
    "Show":      "#cfcfcf",   # hellgrau
}
_FUNC_COLOR_EFFECT = QColor("#5effa6")  # EFX / Layered / Carousel: grün
_FUNC_COLOR_SCRIPT = QColor("#88ddcc")  # Script: teal


def _func_color(f) -> QColor:
    """Farbe eines Funktions-Items je nach Typ."""
    if getattr(f, "is_script", False):
        return _FUNC_COLOR_SCRIPT
    if getattr(f, "is_layered_effect", False) or getattr(f, "is_carousel", False):
        return _FUNC_COLOR_EFFECT
    ft = getattr(f, "function_type", None)
    name = getattr(ft, "value", str(ft))
    if name == "EFX":
        return _FUNC_COLOR_EFFECT
    return QColor(_FUNC_COLORS.get(name, _FUNC_COLOR_DEFAULT.name()))


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
        src_kind = dragged_item.data(0, _ROLE_KIND)
        if src_kind not in ("snap", "function"):
            event.ignore()
            return
        ref = dragged_item.data(0, _ROLE_REF)

        # Ziel-Ordner aus dem Drop-Ziel bestimmen
        dest = self._panel._folder_of_item(target_item)

        if src_kind == "snap":
            lib = self._panel._lib()
            if lib is not None:
                lib.move_snap(ref, dest)
        else:  # function
            f = self._panel._get_func(int(ref))
            if f is not None:
                f.folder = dest
            self._panel._emit_function_changed()
        self._panel._refresh_tree()
        event.accept()


class SnapFilePanel(QWidget):
    """Bibliotheks-Panel für show-gebundene Programmer-Snaps."""

    # MIDI-Learn läuft im MIDI-Thread → thread-sicher in den UI-Thread marshallen.
    _midi_learned_sig = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._learn_fid: int | None = None
        self._learn_name: str = ""
        self._learn_box = None
        self._midi_learned_sig.connect(self._apply_learned_midi)
        self._setup_ui()
        self._refresh_tree()
        # Bei Show-Wechsel / Funktionsänderung den Baum neu aufbauen.
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe(SyncEvent.REFRESH_ALL, lambda *_: self._safe_refresh())
            sync.subscribe(SyncEvent.FUNCTION_CHANGED, lambda *_: self._safe_refresh())
        except Exception as e:
            print(f"[snap_file_panel] sync subscribe error: {e}")
        # Laufende Funktionen alle 500 ms fett markieren (ohne Neuaufbau).
        try:
            from PySide6.QtCore import QTimer
            self._run_timer = QTimer(self)
            self._run_timer.setInterval(500)
            self._run_timer.timeout.connect(self._update_running)
            self._run_timer.start()
        except Exception as e:
            print(f"[snap_file_panel] run timer error: {e}")

    def _lib(self):
        try:
            from src.core.engine.snap_library import get_snap_library
            return get_snap_library()
        except Exception as e:
            print(f"[snap_file_panel] library unavailable: {e}")
            return None

    def _fm(self):
        try:
            from src.core.engine.function_manager import get_function_manager
            return get_function_manager()
        except Exception as e:
            print(f"[snap_file_panel] function manager unavailable: {e}")
            return None

    def _safe_refresh(self):
        try:
            self._refresh_tree()
        except RuntimeError:
            pass  # Widget zwischenzeitlich gelöscht (Layout-Wechsel)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        hdr = QLabel("Bibliothek")
        hdr.setStyleSheet("font-weight: bold; font-size: 12px; color: #ccc;")
        hdr.setToolTip("Snaps (gelb) und Effekte/Funktionen (farbig) in einer "
                       "gemeinsamen Ordnerstruktur")
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

    def _all_folders(self) -> set[str]:
        """Ordnerpfade aus Snap-Bibliothek ∪ Funktions-Ordnern (inkl. Eltern)."""
        lib = self._lib()
        folders: set[str] = set(lib.folders()) if lib is not None else set()
        fm = self._fm()
        if fm is not None:
            for f in fm.all():
                path = getattr(f, "folder", "") or ""
                if not path:
                    continue
                parts = path.split("/")
                for i in range(1, len(parts) + 1):
                    folders.add("/".join(parts[:i]))
        return folders

    def _refresh_tree(self):
        self._tree.clear()
        lib = self._lib()
        if lib is None:
            return
        self._folder_items: dict[str, QTreeWidgetItem] = {}
        self._func_items: list[tuple[QTreeWidgetItem, int]] = []
        for fpath in sorted(self._all_folders(), key=str.lower):
            self._ensure_folder_item(fpath)
        # Snaps (gelb)
        for snap in lib.snaps_sorted():
            parent = self._ensure_folder_item(snap.folder)
            item = QTreeWidgetItem(parent, [snap.name])
            item.setData(0, _ROLE_REF, snap.id)
            item.setData(0, _ROLE_KIND, "snap")
            item.setForeground(0, _SNAP_COLOR)
        # Funktionen/Effekte (je Typ farbig)
        fm = self._fm()
        if fm is not None:
            for f in sorted(fm.all(), key=lambda x: (getattr(x, "folder", "") or "").lower()
                            + "\x00" + getattr(x, "name", "").lower()):
                fid = getattr(f, "id", None)
                if fid is None:
                    continue
                parent = self._ensure_folder_item(getattr(f, "folder", "") or "")
                item = QTreeWidgetItem(parent, [f.name])
                item.setData(0, _ROLE_REF, int(fid))
                item.setData(0, _ROLE_KIND, "function")
                item.setForeground(0, _func_color(f))
                self._func_items.append((item, int(fid)))
        self._update_running()

    def _update_running(self):
        """Laufende Funktionen fett markieren (ohne den Baum neu aufzubauen)."""
        fm = self._fm()
        if fm is None:
            return
        from PySide6.QtGui import QFont
        bold = QFont(); bold.setBold(True)
        normal = QFont()
        for item, fid in getattr(self, "_func_items", []):
            try:
                item.setFont(0, bold if fm.is_running(fid) else normal)
            except RuntimeError:
                pass

    def _ensure_folder_item(self, path: str) -> QTreeWidgetItem:
        """Liefert (und erzeugt bei Bedarf rekursiv) das Baum-Item für einen
        verschachtelten Ordnerpfad. "" = Wurzel (unsichtbares Root-Item)."""
        if not path:
            return self._tree.invisibleRootItem()
        existing = self._folder_items.get(path)
        if existing is not None:
            return existing
        parent_path, _, name = path.rpartition("/")
        parent_item = self._ensure_folder_item(parent_path)
        item = QTreeWidgetItem(parent_item, [name])
        item.setData(0, _ROLE_REF, path)
        item.setData(0, _ROLE_KIND, "folder")
        item.setExpanded(True)
        self._folder_items[path] = item
        return item

    # â”€â”€ Hilfs-Methoden â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _selected(self) -> tuple[object, str | None]:
        items = self._tree.selectedItems()
        if not items:
            return None, None
        item = items[0]
        return (item.data(0, _ROLE_REF), item.data(0, _ROLE_KIND))

    def _selected_snap_ids(self) -> list[int]:
        ids: list[int] = []
        for item in self._tree.selectedItems():
            if item.data(0, _ROLE_KIND) == "snap":
                ids.append(int(item.data(0, _ROLE_REF)))
        return ids

    def _target_folder(self) -> str:
        """Ordnerpfad für neue Snaps/Unterordner aus der aktuellen Auswahl."""
        ref, kind = self._selected()
        if kind == "folder" and ref:
            return str(ref)
        if kind == "snap" and ref is not None:
            lib = self._lib()
            snap = lib.get(ref) if lib is not None else None
            return snap.folder if snap is not None else ""
        if kind == "function" and ref is not None:
            f = self._get_func(int(ref))
            return getattr(f, "folder", "") or "" if f is not None else ""
        return ""

    def _get_func(self, fid: int):
        fm = self._fm()
        if fm is None:
            return None
        try:
            return fm.get(fid)
        except Exception:
            return None

    def _folder_of_item(self, item) -> str:
        """Ziel-Ordnerpfad eines (Drop-)Items: Ordner→Pfad, Snap/Funktion→deren Ordner."""
        if item is None:
            return ""
        kind = item.data(0, _ROLE_KIND)
        ref = item.data(0, _ROLE_REF)
        if kind == "folder":
            return str(ref)
        if kind == "snap":
            lib = self._lib()
            snap = lib.get(ref) if lib is not None else None
            return snap.folder if snap is not None else ""
        if kind == "function":
            f = self._get_func(int(ref))
            return getattr(f, "folder", "") or "" if f is not None else ""
        return ""

    # â”€â”€ Aktionen â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _save_snap(self):
        if get_state is None:
            return
        lib = self._lib()
        if lib is None:
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

            lib.add_snap(name.strip(), self._target_folder(), filtered)
            self._refresh_tree()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _new_folder(self):
        lib = self._lib()
        if lib is None:
            return
        name, ok = QInputDialog.getText(self, "Neuer Ordner", "Ordner-Name:")
        if not ok or not name.strip():
            return
        parent = self._target_folder()
        leaf = name.strip().strip("/")
        path = f"{parent}/{leaf}" if parent else leaf
        lib.add_folder(path)
        self._refresh_tree()

    def _apply_selected(self):
        ref, kind = self._selected()
        if kind == "snap" and ref is not None:
            self._apply_snap(int(ref))

    def _apply_snap(self, sid: int):
        if get_state is None:
            return
        lib = self._lib()
        snap = lib.get(sid) if lib is not None else None
        if snap is None:
            return
        try:
            state = get_state()
            for fid, attrs in snap.values.items():
                for attr, val in attrs.items():
                    state.set_programmer_value(int(fid), attr, int(val))
        except Exception as e:
            QMessageBox.warning(self, "Fehler beim Anwenden", str(e))

    def _create_chase_from_selection(self):
        snap_ids = self._selected_snap_ids()
        if len(snap_ids) < 2:
            QMessageBox.information(
                self,
                "Chase erstellen",
                "Bitte mindestens zwei Snaps markieren.",
            )
            return

        dlg = ChaseCreateDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        opts = dlg.values()

        lib = self._lib()
        snap_payloads: list[tuple[str, dict]] = []
        for sid in snap_ids:
            snap = lib.get(sid) if lib is not None else None
            if snap is None or not snap.values:
                continue
            values = {str(fid): attrs for fid, attrs in snap.values.items()}
            snap_payloads.append((snap.name, values))
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
                "Im Button-Dialog Aktion 'FunctionToggle' waehlen und die Funktion\n"
                "im Dropdown 'Funktion/Chase (Name)' direkt nach Namen auswaehlen.\n"
                "Beim SpeedDial dieselbe Funktion im Namens-Dropdown waehlen\n"
                "(Target wird automatisch auf 'Function' gesetzt)."
            ),
        )

    def _delete_selected(self):
        ref, kind = self._selected()
        if ref is None or not kind:
            return
        lib = self._lib()
        if lib is None:
            return
        if kind == "folder":
            # Snaps im Ordner werden gelöscht; Funktionen werden zur Sicherheit
            # in den Elternordner verschoben (nie still gelöscht — sie können in
            # Playback/VC referenziert sein).
            path = str(ref)
            n_funcs = self._move_functions_up(path, dry_run=True)
            extra = (f"\n{n_funcs} Funktion(en) darin werden in den übergeordneten "
                     f"Ordner verschoben (nicht gelöscht)." if n_funcs else "")
            reply = QMessageBox.question(self, "Ordner löschen",
                f"Ordner '{path.rsplit('/', 1)[-1]}' und alle enthaltenen Snaps "
                f"wirklich löschen?{extra}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self._move_functions_up(path, dry_run=False)
                lib.remove_folder(path)
                self._refresh_tree()
        elif kind == "function":
            f = self._get_func(int(ref))
            display = getattr(f, "name", str(ref)) if f is not None else str(ref)
            reply = QMessageBox.question(self, "Funktion löschen",
                f"Funktion '{display}' wirklich löschen?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                fm = self._fm()
                if fm is not None:
                    fm.remove(int(ref))
                self._emit_function_changed()
                self._refresh_tree()
        else:
            snap = lib.get(int(ref))
            display = snap.name if snap is not None else str(ref)
            reply = QMessageBox.question(self, "Snap löschen",
                f"Snap '{display}' wirklich löschen?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                lib.remove_snap(int(ref))
                self._refresh_tree()

    def _on_double_click(self, item: QTreeWidgetItem, _col: int):
        kind = item.data(0, _ROLE_KIND)
        ref = item.data(0, _ROLE_REF)
        if kind == "snap":
            self._apply_snap(int(ref))
        elif kind == "function":
            self._toggle_function(int(ref))

    def _add_move_menu(self, menu: QMenu):
        """Untermenü „In Ordner verschieben" für das aktuell gewählte Item."""
        move_menu = menu.addMenu("In Ordner verschieben")
        act_root = move_menu.addAction("(Stammordner)")
        act_root.triggered.connect(lambda: self._move_to(""))
        folders = self._collect_folders()
        if folders:
            move_menu.addSeparator()
        for display, fpath in folders:
            act = move_menu.addAction(display)
            act.triggered.connect(lambda checked, p=fpath: self._move_to(p))

    def _context_menu(self, _pos):
        ref, kind = self._selected()
        menu = QMenu(self)
        if kind == "snap":
            menu.addAction("Anwenden").triggered.connect(self._apply_selected)
            menu.addAction("Chase aus Auswahl erstellen").triggered.connect(
                self._create_chase_from_selection
            )
            menu.addSeparator()
            menu.addAction("Umbenennen...").triggered.connect(self._rename_selected)
            self._add_move_menu(menu)
            menu.addSeparator()
            menu.addAction("Löschen").triggered.connect(self._delete_selected)
        elif kind == "function":
            fm = self._fm()
            running = fm.is_running(int(ref)) if fm is not None else False
            if running:
                menu.addAction("Stop").triggered.connect(
                    lambda: self._stop_function(int(ref)))
            else:
                menu.addAction("Start").triggered.connect(
                    lambda: self._start_function(int(ref)))
            menu.addAction("Bearbeiten...").triggered.connect(
                lambda: self._edit_function(int(ref)))
            menu.addAction("🎹 MIDI lernen (Pad/Fader drücken)").triggered.connect(
                lambda: self._learn_midi_for_function(int(ref)))
            menu.addSeparator()
            menu.addAction("Umbenennen...").triggered.connect(self._rename_selected)
            self._add_move_menu(menu)
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

    # â”€â”€ Ordner-/Snap-Aktionen â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _collect_folders(self) -> list[tuple[str, str]]:
        """Alle Ordner als (Anzeigename, Ordnerpfad)-Paare (Snaps ∪ Funktionen)."""
        return [
            (path.replace("/", " / "), path)
            for path in sorted(self._all_folders(), key=str.lower)
        ]

    def _rename_selected(self):
        ref, kind = self._selected()
        if ref is None or kind not in ("snap", "function", "folder"):
            return
        lib = self._lib()
        if lib is None:
            return
        if kind == "snap":
            snap = lib.get(int(ref))
            old_name = snap.name if snap is not None else ""
        elif kind == "function":
            f = self._get_func(int(ref))
            old_name = getattr(f, "name", "") if f is not None else ""
        else:
            old_name = str(ref).rsplit("/", 1)[-1]
        new_name, ok = QInputDialog.getText(
            self, "Umbenennen", "Neuer Name:", text=old_name
        )
        if not ok or not new_name.strip():
            return
        if kind == "snap":
            lib.rename_snap(int(ref), new_name.strip())
        elif kind == "function":
            f = self._get_func(int(ref))
            if f is not None:
                f.name = new_name.strip()
            self._emit_function_changed()
        else:
            # Ordner: Snap-Seite umbenennen, dann Funktions-Ordner mitziehen.
            new_path = lib.rename_folder(str(ref), new_name.strip())
            if new_path:
                self._rewrite_function_folders(str(ref), new_path)
            self._emit_function_changed()
        self._refresh_tree()

    def _move_to(self, dest_folder: str):
        ref, kind = self._selected()
        if ref is None:
            return
        if kind == "snap":
            lib = self._lib()
            if lib is not None:
                lib.move_snap(int(ref), dest_folder or "")
        elif kind == "function":
            f = self._get_func(int(ref))
            if f is not None:
                f.folder = dest_folder or ""
            self._emit_function_changed()
        else:
            return
        self._refresh_tree()

    # â”€â”€ Funktions-Aktionen â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _toggle_function(self, fid: int):
        fm = self._fm()
        if fm is None:
            return
        try:
            if fm.is_running(fid):
                fm.stop(fid)
            else:
                fm.start(fid)
        except Exception as e:
            print(f"[snap_file_panel] toggle function error: {e}")
        self._update_running()

    def _start_function(self, fid: int):
        fm = self._fm()
        if fm is not None:
            try:
                fm.start(fid)
            except Exception as e:
                print(f"[snap_file_panel] start function error: {e}")
        self._update_running()

    def _stop_function(self, fid: int):
        fm = self._fm()
        if fm is not None:
            try:
                fm.stop(fid)
            except Exception as e:
                print(f"[snap_file_panel] stop function error: {e}")
        self._update_running()

    def _learn_midi_for_function(self, fid: int):
        """Legt die Funktion live auf ein MIDI-Pad/-Fader (aus dem Funktions-Browser
        portiert, damit das Feature nach Auflösung des Funktionen-Tabs erhalten bleibt)."""
        f = self._get_func(fid)
        if f is None:
            return
        try:
            from src.core.app_state import get_state
            mapper = get_state().midi_mapper
        except Exception:
            mapper = None
        if mapper is None:
            QMessageBox.warning(self, "MIDI lernen",
                                "Kein MIDI-Mapper verfügbar (MIDI nicht initialisiert).")
            return
        self._learn_fid = int(fid)
        self._learn_name = f.name
        box = QMessageBox(self)
        box.setWindowTitle("MIDI lernen")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(f'Drücke jetzt das Pad / den Fader für\n„{f.name}" …')
        box.setStandardButtons(QMessageBox.StandardButton.Cancel)
        box.buttonClicked.connect(lambda *_: self._cancel_learn())
        self._learn_box = box
        mapper.start_learn(self._on_midi_learned)
        box.show()

    def _cancel_learn(self):
        try:
            from src.core.app_state import get_state
            mapper = get_state().midi_mapper
            if mapper is not None:
                mapper.stop_learn()
        except Exception:
            pass
        self._learn_fid = None
        self._learn_box = None

    def _on_midi_learned(self, msg):
        # Läuft im MIDI-Thread → thread-sicher in den UI-Thread marshallen.
        self._midi_learned_sig.emit(msg)

    def _apply_learned_midi(self, msg):
        box = self._learn_box
        self._learn_box = None
        if box is not None:
            try:
                box.close()
            except Exception:
                pass
        fid = self._learn_fid
        self._learn_fid = None
        if fid is None:
            return
        try:
            from src.core.app_state import get_state
            from src.core.midi.midi_mapper import MidiMapping, MidiOutFeedback
            mapper = get_state().midi_mapper
            if mapper is None:
                return
            is_cc = (msg.msg_type == "cc")
            # Vorhandene Bindung auf demselben Bedienelement entfernen.
            existing = mapper.get_mappings()
            for i in range(len(existing) - 1, -1, -1):
                m = existing[i]
                same_type = (m.msg_type == "cc") == is_cc
                if (same_type and int(m.channel) == int(msg.channel)
                        and int(m.data1) == int(msg.data1)):
                    mapper.remove_mapping(i)
            mapping = MidiMapping(
                name=f"Funktion: {self._learn_name}",
                msg_type="cc" if is_cc else "note_on",
                channel=int(msg.channel),
                data1=int(msg.data1),
                target_id=f"function:{int(fid)}",
                button_mode="toggle",
                port_filter=getattr(msg, "port_name", "") or "",
                midi_out=MidiOutFeedback(message_type="cc" if is_cc else "note"),
            )
            mapper.add_mapping(mapping)
            mapper.save("data/midi_mappings.json")
            kind = "CC" if is_cc else "Note"
            QMessageBox.information(
                self, "MIDI gelernt",
                f'„{self._learn_name}" liegt jetzt auf {kind} {int(msg.data1)} '
                f'(Kanal {int(msg.channel)}).')
        except Exception as e:
            QMessageBox.warning(self, "MIDI lernen", f"Fehler: {e}")

    def _edit_function(self, fid: int):
        f = self._get_func(fid)
        if f is None:
            return
        try:
            from src.ui.views.function_manager_view import create_function_editor
            editor = create_function_editor(f)
        except Exception as e:
            QMessageBox.warning(self, "Bearbeiten", f"Editor nicht verfügbar: {e}")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Bearbeiten: {getattr(f, 'name', '')}")
        dlg.resize(720, 560)
        v = QVBoxLayout(dlg)
        v.addWidget(editor)
        btn = QPushButton("Schließen")
        btn.clicked.connect(dlg.accept)
        v.addWidget(btn)
        dlg.exec()
        self._emit_function_changed()
        self._refresh_tree()

    # â”€â”€ Ordner ↔ Funktionen ────────────────────────────────────────────────────

    def _rewrite_function_folders(self, old_path: str, new_path: str):
        """Zieht Funktions-Ordner beim Ordner-Umbenennen mit (inkl. Unterordner)."""
        fm = self._fm()
        if fm is None:
            return
        prefix = old_path + "/"
        for f in fm.all():
            fp = getattr(f, "folder", "") or ""
            if fp == old_path:
                f.folder = new_path
            elif fp.startswith(prefix):
                f.folder = new_path + "/" + fp[len(prefix):]

    def _move_functions_up(self, folder: str, dry_run: bool) -> int:
        """Verschiebt Funktionen aus folder (+ Unterordnern) in dessen Elternordner.
        Mit dry_run=True wird nur gezählt. Gibt die Anzahl betroffener Funktionen."""
        fm = self._fm()
        if fm is None:
            return 0
        parent = folder.rsplit("/", 1)[0] if "/" in folder else ""
        prefix = folder + "/"
        count = 0
        for f in fm.all():
            fp = getattr(f, "folder", "") or ""
            if fp == folder or fp.startswith(prefix):
                count += 1
                if not dry_run:
                    f.folder = parent
        return count

    def _emit_function_changed(self):
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.FUNCTION_CHANGED, None)
        except Exception:
            pass




