"""Channel Groups View - QLC+ style channel groups with shared sliders."""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QInputDialog, QMessageBox,
    QSlider, QLineEdit, QSpinBox,
)
from PySide6.QtCore import Qt
from src.core.app_state import get_state
from src.ui.weak_slots import weak_slot, weak_slot_fwd


_PERSIST_PATH = os.path.join("data", "channel_groups.json")


@dataclass
class ChannelGroup:
    name: str = "Neue Gruppe"
    universe: int = 1
    channels: list[int] = field(default_factory=list)
    value: int = 0  # 0-255

    def to_dict(self):
        return {
            "name": self.name,
            "universe": self.universe,
            "channels": self.channels,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            name=d.get("name", "Gruppe"),
            universe=int(d.get("universe", 1)),
            channels=list(d.get("channels", [])),
            value=int(d.get("value", 0)),
        )


def _parse_channels(text: str) -> list[int]:
    """Parse '1,2,5-10' -> [1,2,5,6,7,8,9,10]."""
    out = []
    for part in text.split(','):
        part = part.strip()
        if not part:
            continue
        try:
            if '-' in part:
                a, b = part.split('-', 1)
                a = int(a.strip()); b = int(b.strip())
                if a > b: a, b = b, a
                for v in range(a, b + 1):
                    if 1 <= v <= 512:
                        out.append(v)
            else:
                v = int(part)
                if 1 <= v <= 512:
                    out.append(v)
        except ValueError:
            continue
    # Dedup keep order
    seen = set(); res = []
    for v in out:
        if v not in seen:
            seen.add(v); res.append(v)
    return res


def _format_channels(channels: list[int]) -> str:
    return ",".join(str(c) for c in channels)


class ChannelGroupsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = get_state()
        self._groups: list[ChannelGroup] = []
        self._setup_ui()
        self._load()
        self._refresh_table()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Toolbar
        tb = QHBoxLayout()
        b_new = QPushButton("+ Neue Gruppe")
        b_new.clicked.connect(self._add_group)
        tb.addWidget(b_new)
        b_del = QPushButton("Löschen")
        b_del.setObjectName("btn_danger")
        b_del.clicked.connect(self._delete_selected)
        tb.addWidget(b_del)
        b_save = QPushButton("Speichern")
        b_save.clicked.connect(self._save)
        tb.addWidget(b_save)
        tb.addStretch(1)
        tb.addWidget(QLabel("Wert-Slider regelt alle Kanäle der Gruppe gleichzeitig."))
        root.addLayout(tb)

        # Table
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Name", "Universe", "Kanäle", "Wert (0-255)", ""]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self._table, 1)

    def _refresh_table(self):
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._groups))
        for row, g in enumerate(self._groups):
            # Name
            name_edit = QLineEdit(g.name)
            name_edit.setProperty("row", row)
            name_edit.editingFinished.connect(self._on_name_edit_finished)
            self._table.setCellWidget(row, 0, name_edit)

            # Universe
            # 1-32 wie der Universen-Manager (nicht 1-16), sonst sind Gruppen in
            # Universe 17-32 nicht konfigurierbar.
            spin_u = QSpinBox(); spin_u.setRange(1, 32); spin_u.setValue(g.universe)
            spin_u.valueChanged.connect(weak_slot_fwd(self._on_universe_changed, row))
            self._table.setCellWidget(row, 1, spin_u)

            # Channels
            ch_edit = QLineEdit(_format_channels(g.channels))
            ch_edit.setProperty("row", row)
            ch_edit.editingFinished.connect(self._on_channels_edit_finished)
            self._table.setCellWidget(row, 2, ch_edit)

            # Slider + value
            sl_widget = QWidget()
            sl_l = QHBoxLayout(sl_widget)
            sl_l.setContentsMargins(0, 0, 0, 0)
            sld = QSlider(Qt.Orientation.Horizontal)
            sld.setRange(0, 255)
            sld.setValue(g.value)
            sld.valueChanged.connect(weak_slot_fwd(self._on_value_changed, row))
            lbl = QLabel(str(g.value))
            lbl.setFixedWidth(36)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sl_l.addWidget(sld, 1)
            sl_l.addWidget(lbl)
            self._table.setCellWidget(row, 3, sl_widget)
            # Store label in property for refresh
            sld.setProperty("value_label", id(lbl))
            sld.setProperty("row", row)

            # Apply button (re-push)
            b_apply = QPushButton("Send")
            # Touch-Schrift (14px) sprengte die feste 60px-Breite -> Text knapp.
            b_apply.setStyleSheet("QPushButton { font-size:12px; padding:2px 8px; }")
            b_apply.setMinimumWidth(60)
            b_apply.clicked.connect(weak_slot(self._apply_value, row))
            self._table.setCellWidget(row, 4, b_apply)
        self._table.blockSignals(False)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_name_edit_finished(self):
        # sender()-Adapter statt Lambda (STAB-09): Zeile haengt als Property am Edit.
        w = self.sender()
        if w is not None:
            self._on_name_changed(w.property("row"), w.text())

    def _on_channels_edit_finished(self):
        w = self.sender()
        if w is not None:
            self._on_channels_changed(w.property("row"), w.text())

    def _on_name_changed(self, row, text: str):
        if 0 <= row < len(self._groups):
            self._groups[row].name = text

    def _on_universe_changed(self, row, value: int):
        if 0 <= row < len(self._groups):
            self._groups[row].universe = value

    def _on_channels_changed(self, row, text: str):
        if 0 <= row < len(self._groups):
            self._groups[row].channels = _parse_channels(text)

    def _on_value_changed(self, row, value: int):
        if 0 <= row < len(self._groups):
            self._groups[row].value = value
            self._apply_value(row)
            # Update value label
            try:
                widget = self._table.cellWidget(row, 3)
                if widget:
                    lbl = widget.findChild(QLabel)
                    if lbl:
                        lbl.setText(str(value))
            except Exception:
                pass

    def _apply_value(self, row: int):
        if not (0 <= row < len(self._groups)):
            return
        g = self._groups[row]
        # Ueber die Simple-Desk-Override-Schicht schreiben (oberste Schicht in
        # _render_frame) statt roh per universe.set_channel: den Roh-Wert
        # ueberschrieb der 44-Hz-Renderer sofort wieder -> der Gruppen-Slider war
        # wirkungslos, sobald irgendetwas anderes renderte.
        for ch in g.channels:
            if 1 <= ch <= 512:
                self._state.set_simple_desk_channel(g.universe, ch, g.value)

    def _add_group(self):
        name, ok = QInputDialog.getText(self, "Neue Gruppe", "Name:")
        if not ok or not name.strip():
            name = f"Gruppe {len(self._groups) + 1}"
        else:
            name = name.strip()
        self._groups.append(ChannelGroup(name=name, universe=1, channels=[], value=0))
        self._refresh_table()

    def _delete_selected(self):
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for row in rows:
            if 0 <= row < len(self._groups):
                self._groups.pop(row)
        self._refresh_table()

    # ── Show-Integration (SDK-02: Kanal-Gruppen pro Show) ─────────────────────

    def to_dict(self) -> list[dict]:
        """Serialisiert alle Gruppen für die Show-Datei (.lshow)."""
        return [g.to_dict() for g in self._groups]

    def load_data(self, payload) -> None:
        """Ersetzt die Gruppen aus Show-Daten, wendet sie an und spiegelt sie in
        die lokale Arbeitsdatei (Live-Puffer). Wird beim Show-Laden aufgerufen."""
        groups: list[ChannelGroup] = []
        if isinstance(payload, list):
            for d in payload:
                if isinstance(d, dict):
                    try:
                        groups.append(ChannelGroup.from_dict(d))
                    except Exception:
                        pass
        self._groups = groups
        self._refresh_table()
        self._apply_all()
        self._write_disk()

    def _apply_all(self):
        for r in range(len(self._groups)):
            self._apply_value(r)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _write_disk(self) -> bool:
        try:
            os.makedirs(os.path.dirname(_PERSIST_PATH), exist_ok=True)
            with open(_PERSIST_PATH, "w", encoding="utf-8") as f:
                json.dump([g.to_dict() for g in self._groups], f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[ChannelGroupsView] save error: {e}")
            return False

    def _save(self):
        if self._write_disk():
            QMessageBox.information(self, "Gespeichert", _PERSIST_PATH)
        else:
            QMessageBox.warning(self, "Fehler", "Speichern fehlgeschlagen")

    def _load(self):
        if not os.path.exists(_PERSIST_PATH):
            return
        try:
            with open(_PERSIST_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._groups = [ChannelGroup.from_dict(d) for d in data]
        except Exception as e:
            print(f"[ChannelGroupsView] load error: {e}")
            self._groups = []
