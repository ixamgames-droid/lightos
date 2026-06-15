"""Editor fuer Multi-Aktionen eines VC-Buttons (BTN-01).

Bearbeitet eine Liste von Zusatz-Aktionen, die der Button beim Druck — nach seiner
Primaer-Aktion — der Reihe nach ausfuehrt. Jede Aktion ist ein Dict:
``{type, function_id, snapshot_index, snap_id, effect_action_key, mode, delay}``.
"""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
                                QPushButton, QDialogButtonBox, QComboBox, QFormLayout,
                                QLineEdit, QSpinBox, QDoubleSpinBox, QLabel)


# (key, Anzeigename). Geteilt mit der Ausfuehrung in vc_button._execute_extra.
ACTION_TYPES = [
    ("function",     "Funktion (start/stop/toggle)"),
    ("effect_action","Effekt-Aktion"),
    ("snapshot",     "Snapshot anwenden"),
    ("library_snap", "Bibliothek-Snap setzen"),
    ("blackout",     "Blackout"),
    ("stop_all",     "Alle Executors stoppen"),
    ("clear",        "Programmer leeren"),
    ("clear_non_vc", "Alle Nicht-VC-Werte leeren"),
    ("tap",          "Tap-Tempo"),
]
_TYPE_LABELS = dict(ACTION_TYPES)
_MODES = [("toggle", "Umschalten"), ("on", "An / Start"), ("off", "Aus / Stop")]


def summarize(entry: dict) -> str:
    t = entry.get("type", "")
    mode = entry.get("mode", "")
    delay = entry.get("delay", 0) or 0
    suffix = f"  +{delay}s" if delay else ""
    if t == "function":
        return f"Funktion #{entry.get('function_id')} [{mode}]{suffix}"
    if t == "effect_action":
        tgt = entry.get("function_id")
        return f"Effekt: {entry.get('effect_action_key', '')} (#{tgt if tgt is not None else 'aktiv'}){suffix}"
    if t == "snapshot":
        idx = entry.get("snapshot_index")
        return f"Snapshot #{(idx + 1) if idx is not None else '?'}{suffix}"
    if t == "library_snap":
        return f"Bibliothek-Snap #{entry.get('snap_id')}{suffix}"
    if t == "blackout":
        return f"Blackout [{mode}]{suffix}"
    return f"{_TYPE_LABELS.get(t, t)}{suffix}"


class _EntryDialog(QDialog):
    """Bearbeitet eine einzelne Aktion."""

    def __init__(self, entry: dict | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aktion")
        self.setModal(True)
        entry = entry or {}
        form = QFormLayout(self)

        self._type = QComboBox()
        for key, label in ACTION_TYPES:
            self._type.addItem(label, key)
        self._set_combo_data(self._type, entry.get("type", "function"))
        form.addRow("Typ:", self._type)

        self._func = QComboBox()
        self._func.addItem("(aktiver Effekt / keine)", None)
        try:
            from src.core.app_state import get_state
            for f in sorted(get_state().function_manager.all(),
                            key=lambda x: (x.name or "").lower()):
                ftype = getattr(f.function_type, "value", str(f.function_type))
                self._func.addItem(f"{f.name}  [{ftype} #{f.id}]", int(f.id))
        except Exception:
            pass
        if entry.get("function_id") is not None:
            self._set_combo_data(self._func, entry.get("function_id"))
        form.addRow("Funktion/Effekt:", self._func)

        self._mode = QComboBox()
        for key, label in _MODES:
            self._mode.addItem(label, key)
        self._set_combo_data(self._mode, entry.get("mode", "toggle"))
        form.addRow("Modus (Funktion/Blackout):", self._mode)

        self._eff_key = QLineEdit(entry.get("effect_action_key", "next_color"))
        self._eff_key.setToolTip("z. B. next_color, prev_color, reverse_direction, "
                                 "toggle_bounce, toggle_freeze, tap")
        form.addRow("Effekt-Aktion:", self._eff_key)

        self._snap_idx = QSpinBox()
        self._snap_idx.setRange(-1, 47)
        self._snap_idx.setSpecialValueText("—")
        si = entry.get("snapshot_index")
        self._snap_idx.setValue(si if si is not None else -1)
        form.addRow("Snapshot-Index:", self._snap_idx)

        self._snap_id = QSpinBox()
        self._snap_id.setRange(-1, 99999)
        self._snap_id.setSpecialValueText("—")
        sid = entry.get("snap_id")
        self._snap_id.setValue(sid if sid is not None else -1)
        form.addRow("Bibliothek-Snap-ID:", self._snap_id)

        self._delay = QDoubleSpinBox()
        self._delay.setRange(0.0, 60.0)
        self._delay.setSingleStep(0.1)
        self._delay.setSuffix(" s")
        self._delay.setValue(float(entry.get("delay", 0) or 0))
        form.addRow("Verzögerung:", self._delay)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    @staticmethod
    def _set_combo_data(combo: QComboBox, data):
        for i in range(combo.count()):
            if combo.itemData(i) == data:
                combo.setCurrentIndex(i)
                return

    def result_entry(self) -> dict:
        si = self._snap_idx.value()
        sid = self._snap_id.value()
        return {
            "type": self._type.currentData(),
            "function_id": self._func.currentData(),
            "mode": self._mode.currentData(),
            "effect_action_key": self._eff_key.text().strip() or "next_color",
            "snapshot_index": si if si >= 0 else None,
            "snap_id": sid if sid >= 0 else None,
            "delay": round(self._delay.value(), 2),
        }


class MultiActionDialog(QDialog):
    def __init__(self, actions: list[dict] | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mehrfach-Aktionen")
        self.setModal(True)
        self.resize(420, 360)
        self._actions: list[dict] = [dict(a) for a in (actions or [])]

        root = QVBoxLayout(self)
        hint = QLabel("Aktionen werden beim Druck — nach der Primär-Aktion — der "
                      "Reihe nach ausgeführt.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8b949e; font-size:10px;")
        root.addWidget(hint)

        body = QHBoxLayout()
        self._list = QListWidget()
        body.addWidget(self._list, stretch=1)

        col = QVBoxLayout()
        for txt, cb in (("Hinzufügen", self._add), ("Bearbeiten", self._edit),
                        ("Entfernen", self._remove), ("▲", lambda: self._move(-1)),
                        ("▼", lambda: self._move(1))):
            b = QPushButton(txt)
            b.clicked.connect(cb)
            col.addWidget(b)
        col.addStretch(1)
        body.addLayout(col)
        root.addLayout(body)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)
        self._rebuild()

    def _rebuild(self):
        row = self._list.currentRow()
        self._list.clear()
        for a in self._actions:
            self._list.addItem(summarize(a))
        if 0 <= row < self._list.count():
            self._list.setCurrentRow(row)

    def _add(self):
        dlg = _EntryDialog(None, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._actions.append(dlg.result_entry())
            self._rebuild()
            self._list.setCurrentRow(len(self._actions) - 1)

    def _edit(self):
        i = self._list.currentRow()
        if not (0 <= i < len(self._actions)):
            return
        dlg = _EntryDialog(self._actions[i], self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._actions[i] = dlg.result_entry()
            self._rebuild()

    def _remove(self):
        i = self._list.currentRow()
        if 0 <= i < len(self._actions):
            self._actions.pop(i)
            self._rebuild()

    def _move(self, delta: int):
        i = self._list.currentRow()
        j = i + delta
        if 0 <= i < len(self._actions) and 0 <= j < len(self._actions):
            self._actions[i], self._actions[j] = self._actions[j], self._actions[i]
            self._list.setCurrentRow(j)
            self._rebuild()

    def get_actions(self) -> list[dict]:
        return [dict(a) for a in self._actions]
