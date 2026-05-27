"""Sequence Editor — Editor fuer Sequence-Funktion."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QDoubleSpinBox, QComboBox,
    QGroupBox, QListWidget, QListWidgetItem, QAbstractItemView,
    QMessageBox, QInputDialog,
)
from PySide6.QtCore import Qt
from src.core.engine.sequence import Sequence, SequenceStep
from src.core.engine.function import RunOrder, Direction
from src.core.engine.function_manager import get_function_manager
from src.core.app_state import get_state


COLS = ["#", "Werte (FID → Attr=Wert)", "Fade In", "Hold", "Fade Out", "Notiz"]


class SequenceEditor(QWidget):
    """Editor fuer eine Sequence: Fixture-Selektion + Step-Tabelle."""

    def __init__(self, seq: Sequence, parent=None):
        super().__init__(parent)
        self._seq = seq
        self._building = False
        self._setup_ui()
        self._refresh()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        title = QLabel(f"Sequence: {self._seq.name}")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #58a6ff;")
        root.addWidget(title)

        # Name + Properties
        prop_row = QHBoxLayout()
        prop_row.addWidget(QLabel("Name:"))
        self._edit_name = QLineEdit(self._seq.name)
        self._edit_name.editingFinished.connect(self._on_name_changed)
        prop_row.addWidget(self._edit_name, 1)

        prop_row.addWidget(QLabel("Order:"))
        self._cb_order = QComboBox()
        for ro in RunOrder:
            self._cb_order.addItem(ro.value, ro)
        self._cb_order.setCurrentText(self._seq.run_order.value)
        self._cb_order.currentIndexChanged.connect(self._on_props_changed)
        prop_row.addWidget(self._cb_order)

        prop_row.addWidget(QLabel("Dir:"))
        self._cb_dir = QComboBox()
        for d in Direction:
            self._cb_dir.addItem(d.value, d)
        self._cb_dir.setCurrentText(self._seq.direction.value)
        self._cb_dir.currentIndexChanged.connect(self._on_props_changed)
        prop_row.addWidget(self._cb_dir)

        prop_row.addWidget(QLabel("Speed:"))
        self._sp_speed = QDoubleSpinBox()
        self._sp_speed.setRange(0.01, 100.0)
        self._sp_speed.setValue(self._seq.speed)
        self._sp_speed.setSingleStep(0.1)
        self._sp_speed.valueChanged.connect(self._on_props_changed)
        prop_row.addWidget(self._sp_speed)
        root.addLayout(prop_row)

        # Bound fixtures
        bound_box = QGroupBox("Verknuepfte Fixtures")
        bb_layout = QVBoxLayout(bound_box)
        self._lst_fixtures = QListWidget()
        self._lst_fixtures.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._lst_fixtures.setMaximumHeight(120)
        bb_layout.addWidget(self._lst_fixtures)
        bf_row = QHBoxLayout()
        btn_add_fix = QPushButton("+ Fixture")
        btn_add_fix.clicked.connect(self._add_fixture)
        btn_rm_fix = QPushButton("- Fixture")
        btn_rm_fix.clicked.connect(self._remove_fixture)
        btn_all = QPushButton("Alle gepatchten")
        btn_all.clicked.connect(self._bind_all_patched)
        bf_row.addWidget(btn_add_fix)
        bf_row.addWidget(btn_rm_fix)
        bf_row.addWidget(btn_all)
        bf_row.addStretch(1)
        bb_layout.addLayout(bf_row)
        root.addWidget(bound_box)

        # Steps table
        steps_box = QGroupBox("Steps")
        st_layout = QVBoxLayout(steps_box)
        self._tbl = QTableWidget(0, len(COLS))
        self._tbl.setHorizontalHeaderLabels(COLS)
        self._tbl.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self._tbl.itemChanged.connect(self._on_table_changed)
        st_layout.addWidget(self._tbl)

        st_btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Step (aus Programmer)")
        btn_add.setToolTip("Erstellt neuen Step mit aktuellen Programmer-Werten "
                           "der verknuepften Fixtures")
        btn_add.clicked.connect(self._add_step_from_programmer)
        btn_add_empty = QPushButton("+ Leerer Step")
        btn_add_empty.clicked.connect(self._add_empty_step)
        btn_del = QPushButton("- Step")
        btn_del.clicked.connect(self._delete_step)
        btn_up = QPushButton("Hoch")
        btn_up.clicked.connect(lambda: self._move_step(-1))
        btn_down = QPushButton("Runter")
        btn_down.clicked.connect(lambda: self._move_step(1))
        st_btn_row.addWidget(btn_add)
        st_btn_row.addWidget(btn_add_empty)
        st_btn_row.addWidget(btn_del)
        st_btn_row.addWidget(btn_up)
        st_btn_row.addWidget(btn_down)
        st_btn_row.addStretch(1)
        st_layout.addLayout(st_btn_row)

        root.addWidget(steps_box, 1)

        # Transport
        tr_row = QHBoxLayout()
        btn_play = QPushButton("Play")
        btn_play.clicked.connect(self._play)
        btn_stop = QPushButton("Stop")
        btn_stop.clicked.connect(self._stop)
        tr_row.addWidget(btn_play)
        tr_row.addWidget(btn_stop)
        tr_row.addStretch(1)
        root.addLayout(tr_row)

    # ── Refresh ──────────────────────────────────────────────────────────────

    def _refresh(self):
        self._refresh_fixtures()
        self._refresh_steps()

    def _refresh_fixtures(self):
        self._lst_fixtures.clear()
        state = get_state()
        pfs = {f.fid: f for f in state.get_patched_fixtures()}
        for fid in self._seq.bound_fixtures:
            pf = pfs.get(fid)
            label = pf.label if pf else f"<gelöscht>"
            item = QListWidgetItem(f"FID {fid}: {label}")
            item.setData(Qt.ItemDataRole.UserRole, fid)
            self._lst_fixtures.addItem(item)

    def _refresh_steps(self):
        self._building = True
        self._tbl.setRowCount(len(self._seq.steps))
        for i, st in enumerate(self._seq.steps):
            vals_txt = self._format_values(st.values)
            for col, txt in enumerate([
                str(i + 1), vals_txt,
                f"{st.fade_in:.2f}", f"{st.hold:.2f}", f"{st.fade_out:.2f}",
                st.note
            ]):
                item = QTableWidgetItem(txt)
                if col == 0:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 1:
                    item.setToolTip(
                        "Format: FID:attr=wert[, attr=wert]; FID:attr=wert ...\n"
                        "z.B. '3:dimmer=255, red=200; 5:dimmer=128'")
                self._tbl.setItem(i, col, item)
        self._building = False

    def _format_values(self, vals: dict) -> str:
        parts = []
        for fid_str, attrs in vals.items():
            inner = ", ".join(f"{a}={v}" for a, v in attrs.items())
            parts.append(f"{fid_str}:{inner}")
        return "; ".join(parts) if parts else ""

    def _parse_values(self, text: str) -> dict | None:
        """Parst 'fid:attr=val, attr=val; fid:attr=val' in dict[str, dict].
        Returns None bei Fehler."""
        text = (text or "").strip()
        if not text:
            return {}
        out: dict[str, dict[str, int]] = {}
        # Trenne nach ';'
        for part in text.split(";"):
            part = part.strip()
            if not part:
                continue
            if ":" not in part:
                return None
            fid_str, rest = part.split(":", 1)
            fid_str = fid_str.strip().lstrip("FIDfid ").strip()
            if not fid_str.isdigit():
                return None
            attrs: dict[str, int] = {}
            for kv in rest.split(","):
                kv = kv.strip()
                if not kv:
                    continue
                if "=" not in kv:
                    return None
                key, val = kv.split("=", 1)
                key = key.strip().lower()
                try:
                    v = int(float(val.strip()))
                except ValueError:
                    return None
                v = max(0, min(255, v))
                attrs[key] = v
            out[fid_str] = attrs
        return out

    # ── Properties ───────────────────────────────────────────────────────────

    def _on_name_changed(self):
        n = self._edit_name.text().strip()
        if n:
            self._seq.name = n
            try:
                from src.core.sync import get_sync, SyncEvent
                get_sync().emit(SyncEvent.FUNCTION_CHANGED, None)
            except Exception:
                pass

    def _on_props_changed(self):
        self._seq.run_order = self._cb_order.currentData()
        self._seq.direction = self._cb_dir.currentData()
        self._seq.speed = self._sp_speed.value()

    def _on_table_changed(self, item: QTableWidgetItem):
        if self._building:
            return
        row = item.row()
        col = item.column()
        if row >= len(self._seq.steps):
            return
        st = self._seq.steps[row]
        try:
            if col == 1:
                parsed = self._parse_values(item.text())
                if parsed is None:
                    QMessageBox.warning(
                        self, "Ungueltiges Format",
                        "Erwartet: 'FID:attr=wert, attr=wert; FID:attr=wert'\n"
                        "z.B. '3:dimmer=255, red=200'")
                    # Zurueck auf alten Wert
                    self._building = True
                    item.setText(self._format_values(st.values))
                    self._building = False
                else:
                    st.values = parsed
            elif col == 2:
                st.fade_in = max(0.0, float(item.text()))
            elif col == 3:
                st.hold = max(0.0, float(item.text()))
            elif col == 4:
                st.fade_out = max(0.0, float(item.text()))
            elif col == 5:
                st.note = item.text()
        except ValueError:
            pass

    # ── Fixtures ─────────────────────────────────────────────────────────────

    def _add_fixture(self):
        state = get_state()
        pfs = state.get_patched_fixtures()
        if not pfs:
            QMessageBox.information(self, "Keine Fixtures",
                                    "Erst Geraete im Patch hinzufuegen.")
            return
        options = [f"FID {f.fid}: {f.label}" for f in pfs
                   if f.fid not in self._seq.bound_fixtures]
        if not options:
            return
        sel, ok = QInputDialog.getItem(
            self, "Fixture hinzufuegen", "Auswaehlen:", options, 0, False)
        if ok and sel:
            try:
                fid = int(sel.split(":")[0].replace("FID", "").strip())
                self._seq.bound_fixtures.append(fid)
                self._refresh_fixtures()
            except Exception:
                pass

    def _remove_fixture(self):
        for it in self._lst_fixtures.selectedItems():
            fid = it.data(Qt.ItemDataRole.UserRole)
            if fid in self._seq.bound_fixtures:
                self._seq.bound_fixtures.remove(fid)
        self._refresh_fixtures()

    def _bind_all_patched(self):
        state = get_state()
        self._seq.bound_fixtures = [f.fid for f in state.get_patched_fixtures()]
        self._refresh_fixtures()

    # ── Steps ────────────────────────────────────────────────────────────────

    def _add_step_from_programmer(self):
        state = get_state()
        if not self._seq.bound_fixtures:
            QMessageBox.information(self, "Keine Fixtures",
                                    "Erst Fixtures verknuepfen.")
            return
        self._seq.add_step_from_programmer(state.programmer,
                                           fade_in=0.5, hold=1.0, fade_out=0.0)
        self._refresh_steps()

    def _add_empty_step(self):
        self._seq.steps.append(SequenceStep(values={}, fade_in=0.0, hold=1.0))
        self._refresh_steps()

    def _delete_step(self):
        rows = sorted({i.row() for i in self._tbl.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self._seq.steps):
                del self._seq.steps[r]
        self._refresh_steps()

    def _move_step(self, dir: int):
        rows = sorted({i.row() for i in self._tbl.selectedIndexes()})
        if not rows:
            return
        r = rows[0]
        nr = r + dir
        if 0 <= nr < len(self._seq.steps):
            self._seq.steps[r], self._seq.steps[nr] = (
                self._seq.steps[nr], self._seq.steps[r])
            self._refresh_steps()
            self._tbl.selectRow(nr)

    # ── Transport ────────────────────────────────────────────────────────────

    def _play(self):
        get_function_manager().start(self._seq.id)

    def _stop(self):
        get_function_manager().stop(self._seq.id)
