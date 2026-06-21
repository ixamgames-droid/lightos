"""Snap-Editor — Bearbeiten eines Bibliotheks-Snaps (programmierte Kanalwerte).

Snaps haben keinen Programmer-Editor wie Szenen/Matrix (sie speichern fertige
Werte). Dieser Overlay zeigt eine LISTE der tatsaechlich programmierten
Geraete/Attribute — mit aufgeloestem Kanalnamen + DMX-Adresse — und laesst die
Werte direkt aendern oder Eintraege entfernen. Aufgerufen via Rechtsklick/
Langdruck → „Bearbeiten..." in der Bibliothek (snap_file_panel._edit_snap).

Mutationen laufen ueber die SnapLibrary-API (set_snap_value/remove_snap_attr);
weil der Snap das Live-Objekt der Singleton-Bibliothek ist, wird die Aenderung
mit der Show gespeichert (kein extra Save-Hook noetig).
"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QSpinBox, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt

from src.core.app_state import get_state, get_channels_for_patched
from src.core.engine.snap_library import get_snap_library
from src.core.attr_groups import classify_attr as _classify_attr  # kanonisch, kein Zyklus


_COLS = ["Gerät", "Kanal", "Gruppe", "DMX", "Wert", ""]


class SnapEditor(QWidget):
    """Tabellarischer Editor fuer die programmierten Werte EINES Snaps."""

    def __init__(self, snap, parent=None):
        super().__init__(parent)
        self._snap = snap
        self._building = False
        self._setup_ui()
        self._load()

    def _lib(self):
        try:
            return get_snap_library()
        except Exception:
            return None

    def _setup_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)

        hdr = QHBoxLayout()
        self._title = QLabel()
        self._title.setStyleSheet("font-weight: bold;")
        hdr.addWidget(self._title)
        hdr.addStretch(1)
        b_prev = QPushButton("Vorschau senden")
        b_prev.setFixedHeight(24)
        b_prev.setToolTip("Den Snap in den Programmer laden (auf der Bühne sichtbar machen).")
        b_prev.clicked.connect(self._preview)
        hdr.addWidget(b_prev)
        v.addLayout(hdr)

        self._tbl = QTableWidget(0, len(_COLS))
        self._tbl.setHorizontalHeaderLabels(_COLS)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        hh = self._tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._tbl.setMinimumHeight(220)
        v.addWidget(self._tbl, 1)

        self._info = QLabel()
        self._info.setStyleSheet("color: #8b949e; font-size: 11px;")
        self._info.setWordWrap(True)
        v.addWidget(self._info)

    # ── Kanal-Aufloesung ──────────────────────────────────────────────────────

    def _fixtures(self) -> dict:
        try:
            return {f.fid: f for f in get_state().get_patched_fixtures()}
        except Exception:
            return {}

    def _resolve(self, fx, attr: str):
        """(Gerätelabel, Kanalname, DMX-Adresse|None) fuer ein fid+attr."""
        if fx is None:
            return ("<nicht gepatcht>", attr, None)
        label = getattr(fx, "label", None) or f"FID {getattr(fx, 'fid', '?')}"
        chan_name, dmx = attr, None
        try:
            base = attr.split("#")[0].lower()   # Mehrkopf attr#N -> Basis-Attribut
            for ch in get_channels_for_patched(fx):
                if (ch.attribute or "").lower() == base:
                    chan_name = ch.name or attr
                    dmx = int(fx.address) + int(ch.channel_number) - 1
                    break
        except Exception:
            pass
        return (label, chan_name, dmx)

    def _load(self):
        self._building = True
        self._title.setText(f"Snap: {self._snap.name}")
        fixtures = self._fixtures()
        rows = []
        for fid in sorted(self._snap.values.keys()):
            for attr in sorted(self._snap.values[fid].keys()):
                rows.append((int(fid), attr, self._snap.values[fid][attr]))
        self._tbl.setRowCount(len(rows))
        for r, (fid, attr, val) in enumerate(rows):
            label, chan_name, dmx = self._resolve(fixtures.get(fid), attr)
            self._tbl.setItem(r, 0, QTableWidgetItem(f"{label}  (FID {fid})"))
            self._tbl.setItem(r, 1, QTableWidgetItem(chan_name))
            self._tbl.setItem(r, 2, QTableWidgetItem(_classify_attr(attr)))
            dmx_item = QTableWidgetItem("—" if dmx is None else str(dmx))
            dmx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._tbl.setItem(r, 3, dmx_item)
            sp = QSpinBox()
            sp.setRange(0, 255)
            sp.setValue(int(val))
            sp.valueChanged.connect(
                lambda value, f=fid, a=attr: self._on_value(f, a, value))
            self._tbl.setCellWidget(r, 4, sp)
            btn = QPushButton("✕")
            btn.setFixedWidth(28)
            btn.setToolTip("Diesen Kanal aus dem Snap entfernen")
            btn.clicked.connect(lambda _=False, f=fid, a=attr: self._remove(f, a))
            self._tbl.setCellWidget(r, 5, btn)
        ndev = len(self._snap.values)
        self._info.setText(
            f"{len(rows)} programmierte Kanäle auf {ndev} Gerät(en). "
            f"DMX-Strich = Gerät nicht (mehr) gepatcht.")
        self._building = False

    # ── Mutationen (ueber die Library-API) ────────────────────────────────────

    def _on_value(self, fid: int, attr: str, val: int):
        if self._building:
            return
        lib = self._lib()
        if lib is not None:
            lib.set_snap_value(self._snap.id, int(fid), attr, int(val))
        else:
            self._snap.values.setdefault(int(fid), {})[attr] = max(0, min(255, int(val)))

    def _remove(self, fid: int, attr: str):
        lib = self._lib()
        if lib is not None:
            lib.remove_snap_attr(self._snap.id, int(fid), attr)
        else:
            self._snap.values.get(int(fid), {}).pop(attr, None)
            if int(fid) in self._snap.values and not self._snap.values[int(fid)]:
                self._snap.values.pop(int(fid), None)
        self._load()

    def _preview(self):
        try:
            st = get_state()
            for fid, attrs in self._snap.values.items():
                for attr, val in attrs.items():
                    st.set_programmer_value(int(fid), attr, int(val))
        except Exception:
            pass
