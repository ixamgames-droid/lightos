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
import weakref
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QBrush, QPen, QAction, QCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGridLayout, QLabel,
    QMenu, QInputDialog, QMessageBox, QFileDialog, QDialog, QSplitter,
    QListWidget, QListWidgetItem, QDialogButtonBox
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

    def __init__(self, name: str = "", values: dict | None = None,
                 ignored: set | None = None):
        self.name = name
        self.values: dict[int, dict[str, int]] = values or {}
        # SNP-01: (fid, attr)-Paare, die beim ANWENDEN uebersprungen werden
        # (gespeicherter Wert bleibt erhalten, wird aber nicht in den Programmer
        # geschrieben). Unterschied: gespeichert vs. nicht-gespeichert (gar nicht
        # in values) vs. bewusst ignoriert (in values, aber hier gelistet).
        self.ignored: set[tuple[int, str]] = set(ignored or set())

    def is_empty(self) -> bool:
        return not self.values

    def is_ignored(self, fid, attr) -> bool:
        return (int(fid), attr) in self.ignored

    def ignored_count(self) -> int:
        return len(self.ignored)

    def to_dict(self) -> dict:
        # JSON keys muessen Strings sein
        ser_vals = {}
        for fid, attrs in self.values.items():
            ser_vals[str(fid)] = dict(attrs)
        return {"name": self.name, "values": ser_vals,
                "ignored": [[fid, attr] for (fid, attr) in sorted(self.ignored)]}

    @classmethod
    def from_dict(cls, d: dict) -> "Snapshot":
        raw = d.get("values", {})
        vals: dict[int, dict[str, int]] = {}
        for k, v in raw.items():
            try:
                fid = int(k)
            except (TypeError, ValueError):
                continue
            if not isinstance(v, dict):
                continue
            # STAB-18: int(av) PRO Wert kapseln — ein einzelner kaputter Wert
            # (None/Liste/nicht-numerisch aus hand-editiertem/importiertem JSON) darf
            # nur DIESEN Kanal ueberspringen, nicht das GANZE Fixture verwerfen
            # (Verlust-Amplifikation). Analog show_file.py-Programmer-Loader /
            # snap_library._clean_values.
            attrs: dict[str, int] = {}
            for ak, av in v.items():
                try:
                    attrs[str(ak)] = int(av)
                except (TypeError, ValueError):
                    continue
            vals[fid] = attrs
        ign: set[tuple[int, str]] = set()
        for item in d.get("ignored", []):
            try:
                ign.add((int(item[0]), str(item[1])))
            except Exception:
                pass
        return cls(name=d.get("name", ""), values=vals, ignored=ign)


class SnapshotIgnoreDialog(QDialog):
    """SNP-01: einzelne (fid, attr)-Kanäle eines Snapshots vom Anwenden ausschließen."""

    def __init__(self, snap: "Snapshot", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Kanäle ignorieren — {snap.name or 'Snapshot'}")
        self.setModal(True)
        self.resize(360, 440)

        names = {}
        try:
            if get_state is not None:
                for f in get_state().get_patched_fixtures():
                    names[int(f.fid)] = getattr(f, "name", None) or f"Fixture {f.fid}"
        except Exception:
            pass

        root = QVBoxLayout(self)
        hint = QLabel("Angehakte Kanäle werden beim Anwenden NICHT geschrieben "
                      "(gespeicherter Wert bleibt erhalten).")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#888; font-size:10px;")
        root.addWidget(hint)

        self._list = QListWidget()
        root.addWidget(self._list, stretch=1)
        for fid in sorted(snap.values):
            fname = names.get(int(fid), f"Fixture {fid}")
            for attr in sorted(snap.values[fid]):
                it = QListWidgetItem(f"FID {fid} · {fname} — {attr}")
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Checked if snap.is_ignored(fid, attr)
                                 else Qt.CheckState.Unchecked)
                it.setData(Qt.ItemDataRole.UserRole, (int(fid), attr))
                self._list.addItem(it)

        tb = QHBoxLayout()
        for txt, fn in (("Alle", lambda: self._set_all(True)),
                        ("Keine", lambda: self._set_all(False)),
                        ("Invertieren", self._invert)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            tb.addWidget(b)
        tb.addStretch(1)
        root.addLayout(tb)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _set_all(self, ignored: bool):
        st = Qt.CheckState.Checked if ignored else Qt.CheckState.Unchecked
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(st)

    def _invert(self):
        for i in range(self._list.count()):
            it = self._list.item(i)
            it.setCheckState(Qt.CheckState.Unchecked
                             if it.checkState() == Qt.CheckState.Checked
                             else Qt.CheckState.Checked)

    def get_ignored(self) -> set:
        out = set()
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                out.add(it.data(Qt.ItemDataRole.UserRole))
        return out


class SnapshotButton(QPushButton):
    """Ein Snapshot-Slot Button."""

    def __init__(self, index: int, parent: "SnapshotsView"):
        super().__init__(parent)
        self._index = index
        # SCHWACHE Referenz auf die View: eine starke Ref macht
        # view -> _buttons -> Button -> view zu einem Referenz-Zyklus, den erst
        # die ZYKLISCHE GC abraeumt. Dealloziert die den Owner-Wrapper (die View
        # besitzt ihr C++-Objekt), laeuft die Qt-Eltern-Kaskade mitten in der GC
        # in beliebiger Dealloc-Reihenfolge -> native Access Violation
        # (PySide6 6.11/Python 3.14; deterministischer Teardown-Crash von
        # tests/test_snapshot_ignore.py). Ohne Zyklus stirbt der Baum per
        # Refcount geordnet und die GC fasst ihn nie an.
        self._view_ref = weakref.ref(parent)
        self.setMinimumSize(80, 56)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.clicked.connect(self._on_click)
        self.refresh()

    @property
    def _view(self) -> "SnapshotsView":
        return self._view_ref()

    def index(self) -> int:
        return self._index

    def refresh(self):
        if self._view is None:      # View bereits zerstoert (Teardown-Fenster)
            return
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
            ign = snap.ignored_count()
            suffix = f", ⊘{ign}" if ign else ""
            self.setText(f"{name}\n({count} FX{suffix})")
            self.setStyleSheet(
                "QPushButton { background: #2a3344; color: #FFD700; "
                "border: 1px solid #4f6391; font-weight: bold; }"
                "QPushButton:hover { background: #364463; }"
            )

    def _on_click(self):
        if self._view is None:
            return
        snap = self._view.get_snapshot(self._index)
        if snap.is_empty():
            # Capture aktuellen Programmer
            self._view.capture(self._index)
        else:
            self._view.apply(self._index)

    def _on_context_menu(self, _pos):
        if self._view is None:
            return
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
            a_ignore = menu.addAction("Kanäle ignorieren...")
            a_ignore.triggered.connect(lambda: self._view.edit_ignored(self._index))
            menu.addSeparator()
            a_del = menu.addAction("Löschen")
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
            "Klick auf gefüllten Slot: anwenden. Rechtsklick: Menü."
        )
        info.setWordWrap(True)
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

        # Linke Seite: Snapshot-Grid
        left_content = QWidget()
        left_layout = QVBoxLayout(left_content)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        grid = QGridLayout()
        grid.setSpacing(4)
        for i in range(SNAPSHOT_TOTAL):
            row = i // SNAPSHOT_COLS
            col = i % SNAPSHOT_COLS
            btn = SnapshotButton(i, self)
            grid.addWidget(btn, row, col)
            self._buttons.append(btn)
        left_layout.addLayout(grid)
        left_layout.addStretch(1)

        # Rechte Seite: Snap-Dateimanager
        try:
            from src.ui.views.snap_file_panel import SnapFilePanel
            self._snap_file_panel = SnapFilePanel()
        except Exception as e:
            print(f"[snapshots] snap_file_panel load error: {e}")
            self._snap_file_panel = QWidget()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_content)
        splitter.addWidget(self._snap_file_panel)
        splitter.setSizes([900, 320])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, stretch=1)

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
                f"Name für Snapshot {index + 1}:",
                text=f"Snap {index + 1}"
            )
            if not ok:
                return

            # Kanal-Auswahl: welche Attribut-Gruppen sollen gespeichert werden?
            try:
                from src.ui.views.snap_file_panel import ChannelSelectDialog
                # Scope wie an den anderen Call-Sites (snap_file_panel/programmer_view/
                # main_window) uebergeben: nur die aktuell ausgewaehlten Geraete kommen
                # in den Snapshot. Sonst landen liegengebliebene Programmer-Werte zuvor
                # gewaehlter Gruppen mit im Snapshot ("Color speichert Dimmer mit").
                scope = state.active_scope_fids() if hasattr(state, "active_scope_fids") else None
                chan_dlg = ChannelSelectDialog(vals, self, scope_fids=scope)
                if chan_dlg.exec() != QDialog.DialogCode.Accepted:
                    return
                vals = chan_dlg.filter_programmer(vals)
                if not vals:
                    QMessageBox.information(self, "Snapshot",
                        "Keine Kanäle ausgewählt - Snapshot nicht gespeichert.")
                    return
            except Exception as e:
                print(f"[snapshots] channel select error: {e}")

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
                    if snap.is_ignored(fid, attr):
                        continue          # SNP-01: bewusst ignorierter Kanal
                    state.set_programmer_value(int(fid), attr, int(val))
        except Exception as e:
            print(f"[snapshots] apply error: {e}")

    def edit_ignored(self, index: int):
        """SNP-01: Dialog zum nachträglichen Ignorieren einzelner Kanäle."""
        snap = self._snapshots[index]
        if snap.is_empty():
            return
        dlg = SnapshotIgnoreDialog(snap, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            snap.ignored = dlg.get_ignored()
            self._buttons[index].refresh()
            self._save_to_disk()

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
            self, "Snapshot löschen",
            f"Snapshot {index + 1} '{self._snapshots[index].name}' wirklich löschen?",
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
            QMessageBox.warning(self, "Import", "Keine leeren Slots verfügbar.")
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
            self, "Alle Snapshots löschen",
            "Alle 48 Snapshots wirklich löschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._snapshots = [Snapshot() for _ in range(SNAPSHOT_TOTAL)]
            for b in self._buttons:
                b.refresh()
            self._save_to_disk()

    # ── Show-Integration (pro Show statt global) ──────────────────────────────

    def to_dict(self) -> list[dict]:
        """Serialisiert alle Slots für die Show-Datei (.lshow)."""
        return [s.to_dict() for s in self._snapshots]

    def load_data(self, payload) -> None:
        """Ersetzt die Slots aus Show-Daten und aktualisiert die Anzeige.

        Wird beim Laden einer Show aufgerufen → Snapshots sind pro Show.
        Leere/ungültige Payload setzt alle Slots zurück. Das Ergebnis wird
        zusätzlich in die lokale Arbeitsdatei geschrieben (Live-Puffer).
        """
        new_list = [Snapshot() for _ in range(SNAPSHOT_TOTAL)]
        if isinstance(payload, list):
            for i in range(SNAPSHOT_TOTAL):
                if i < len(payload) and isinstance(payload[i], dict):
                    try:
                        new_list[i] = Snapshot.from_dict(payload[i])
                    except Exception:
                        pass
        self._snapshots = new_list
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
