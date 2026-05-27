"""Snapshots View - Quick-Save Buttons fuer Programmer States.

Wie QLC+ Snapshots: 48 Slots in einem 12x4 Grid.
  - Klick auf leeren Slot  -> capture aktuellen Programmer
  - Klick auf gefuellten   -> apply (rueckwaerts in Programmer)
  - Rechtsklick            -> Loeschen / Umbenennen / Exportieren
"""
from __future__ import annotations
import os
import json
import copy
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QBrush, QPen, QAction, QCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGridLayout, QLabel,
    QMenu, QInputDialog, QMessageBox, QFileDialog
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


class Snapshot:
    """Ein gespeicherter Programmer-State."""

    def __init__(self, name: str = "", values: dict | None = None):
        self.name = name
        self.values: dict[int, dict[str, int]] = values or {}

    def is_empty(self) -> bool:
        return not self.values

    def to_dict(self) -> dict:
        # JSON keys muessen Strings sein
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


class SnapshotButton(QPushButton):
    """Ein Snapshot-Slot Button."""

    def __init__(self, index: int, parent: "SnapshotsView"):
        super().__init__(parent)
        self._index = index
        self._view = parent
        self.setMinimumSize(80, 56)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.clicked.connect(self._on_click)
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

    def _on_click(self):
        snap = self._view.get_snapshot(self._index)
        if snap.is_empty():
            # Capture aktuellen Programmer
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


class SnapshotsView(QWidget):
    """Komplette Snapshots-Ansicht."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._snapshots: list[Snapshot] = [Snapshot() for _ in range(SNAPSHOT_TOTAL)]
        self._buttons: list[SnapshotButton] = []
        self._setup_ui()
        self._load_from_disk()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        title = QLabel("Snapshots - Schnellzugriff auf gespeicherte Programmer-States")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #ccc;")
        root.addWidget(title)

        info = QLabel(
            "Klick auf leeren Slot: aktuellen Programmer speichern. "
            "Klick auf gefuellten Slot: anwenden. Rechtsklick: Menue."
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
        root.addLayout(tb)

        # Grid
        grid = QGridLayout()
        grid.setSpacing(4)
        for i in range(SNAPSHOT_TOTAL):
            row = i // SNAPSHOT_COLS
            col = i % SNAPSHOT_COLS
            btn = SnapshotButton(i, self)
            grid.addWidget(btn, row, col)
            self._buttons.append(btn)
        root.addLayout(grid)
        root.addStretch(1)

    # ── Snapshot API ─────────────────────────────────────────────────────────

    def get_snapshot(self, index: int) -> Snapshot:
        return self._snapshots[index]

    def capture(self, index: int):
        if get_state is None:
            return
        try:
            state = get_state()
            # Deepcopy damit spaetere Aenderungen die snapshot nicht beeinflussen
            vals = copy.deepcopy(state.programmer)
            if not vals:
                QMessageBox.information(
                    self, "Snapshot",
                    "Programmer ist leer - es gibt nichts zu speichern."
                )
                return
            name, ok = QInputDialog.getText(
                self, "Snapshot speichern",
                f"Name fuer Snapshot {index + 1}:",
                text=f"Snap {index + 1}"
            )
            if not ok:
                return
            self._snapshots[index] = Snapshot(name=name or f"Snap {index + 1}",
                                              values=vals)
            self._buttons[index].refresh()
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
            self, "Snapshot umbenennen", "Neuer Name:",
            text=snap.name
        )
        if ok:
            snap.name = name
            self._buttons[index].refresh()
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
        # Suche ersten leeren Slot
        slot = -1
        for i, s in enumerate(self._snapshots):
            if s.is_empty():
                slot = i
                break
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
        reply = QMessageBox.question(
            self, "Alle Snapshots loeschen",
            "Alle 48 Snapshots wirklich loeschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._snapshots = [Snapshot() for _ in range(SNAPSHOT_TOTAL)]
            for b in self._buttons:
                b.refresh()
            self._save_to_disk()

    # ── Persistenz ───────────────────────────────────────────────────────────

    def _save_to_disk(self):
        try:
            os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
            payload = [s.to_dict() for s in self._snapshots]
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
            if not isinstance(payload, list):
                return
            new_list = []
            for i in range(SNAPSHOT_TOTAL):
                if i < len(payload):
                    new_list.append(Snapshot.from_dict(payload[i] or {}))
                else:
                    new_list.append(Snapshot())
            self._snapshots = new_list
            for b in self._buttons:
                b.refresh()
        except Exception as e:
            print(f"[snapshots] load error: {e}")
