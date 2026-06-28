"""Sequence Editor — Editor fuer Sequence-Funktion."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QDoubleSpinBox, QComboBox,
    QGroupBox, QListWidget, QListWidgetItem, QAbstractItemView,
    QMessageBox, QInputDialog, QScrollArea,
)
from PySide6.QtCore import Qt
from src.core.engine.sequence import Sequence, SequenceStep
from src.core.engine.function import RunOrder, Direction
from src.core.engine.function_manager import get_function_manager
from src.core.app_state import get_state
from src.ui.widgets.curve_editor import CurveThumbnail, CurveEditorDialog
from PySide6.QtWidgets import QDialog


COLS = ["#", "Schritt", "Fade In", "In-Kurve",
        "Hold", "Fade Out", "Out-Kurve", "Werte"]


class SequenceEditor(QWidget):
    """Editor fuer eine Sequence: Fixture-Selektion + Step-Tabelle."""

    def __init__(self, seq: Sequence, parent=None):
        super().__init__(parent)
        self._seq = seq
        self._building = False
        self._setup_ui()
        self._refresh()

    def _setup_ui(self):
        # ── Top-Level: nur Header (Pop-out) + EIN Scrollbereich + Platzhalter ──
        # Loest das alte Platzproblem: der ganze Editor liegt jetzt in EINEM
        # scrollbaren Koerper (kein Stauchen/Abschneiden mehr) und laesst sich per
        # Knopf komplett in ein grosses, frei vergroesserbares Fenster auskoppeln.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addStretch(1)
        self._btn_editor_popout = QPushButton("⤢ Großes Fenster")
        self._btn_editor_popout.setFixedHeight(24)
        self._btn_editor_popout.setToolTip(
            "Den ganzen Editor in einem großen, scrollbaren Fenster bearbeiten")
        self._btn_editor_popout.setStyleSheet(
            "QPushButton{background:#21262d;color:#e6edf3;border:1px solid #30363d;"
            "border-radius:3px;font-size:10px;padding:1px 8px;} "
            "QPushButton:hover{background:#30363d;}")
        self._btn_editor_popout.clicked.connect(self._toggle_editor_popout)
        header.addWidget(self._btn_editor_popout)
        outer.addLayout(header)

        # ── Editor-Koerper (alles ausser dem Header; wandert komplett ins Pop-out) ─
        self._editor_body = QWidget()
        root = QVBoxLayout(self._editor_body)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)

        title = QLabel(f"Sequence: {self._seq.name}")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #58a6ff;")
        root.addWidget(title)

        # ── Gruppe: Grundeinstellungen (Name / Order / Dir / Speed) ───────────
        grp_general = QGroupBox("Grundeinstellungen")
        prop_row = QHBoxLayout(grp_general)
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
        root.addWidget(grp_general)

        # ── Gruppe: Tempo (beatgenau via Bus vs. Free-Run/Crossfade) ──────────
        # Spiegelt das Tempo-Panel der Matrix-/EFX-/Chaser-Editoren. Werte werden
        # VOR connect gesetzt (wie Order/Dir/Speed oben), damit das Setup kein
        # _on_props_changed feuert.
        grp_tempo = QGroupBox("Tempo")
        tempo_row = QHBoxLayout(grp_tempo)
        tempo_row.addWidget(QLabel("Tempo-Bus:"))
        self._tempo_bus_combo = QComboBox()
        self._tempo_bus_combo.addItem("Global (taktgleich, Standard)", "Global")
        self._tempo_bus_combo.addItem("Frei (nicht taktgebunden)", "")
        for _bus_id in ("A", "B", "C", "D"):
            self._tempo_bus_combo.addItem(f"Bus {_bus_id}", _bus_id)
        _bi = self._tempo_bus_combo.findData(getattr(self._seq, "tempo_bus_id", "Global"))
        self._tempo_bus_combo.setCurrentIndex(_bi if _bi >= 0 else 0)
        self._tempo_bus_combo.setToolTip(
            "Beatgenau an einen Tempo-Bus koppeln (folgt der globalen BPM) oder "
            "'Frei' für zeitbasiertes Überblenden zwischen den Schritten.")
        self._tempo_bus_combo.currentIndexChanged.connect(self._on_props_changed)
        tempo_row.addWidget(self._tempo_bus_combo, 1)

        tempo_row.addWidget(QLabel("×:"))
        self._tempo_mult_spin = QDoubleSpinBox()
        self._tempo_mult_spin.setRange(0.0625, 16.0)
        self._tempo_mult_spin.setSingleStep(0.25)
        self._tempo_mult_spin.setDecimals(4)
        self._tempo_mult_spin.setValue(float(getattr(self._seq, "tempo_multiplier", 1.0)))
        self._tempo_mult_spin.setToolTip(
            "Geschwindigkeit relativ zum Tempo-Bus, z. B. 0,5 = halb, 2 = doppelt.")
        self._tempo_mult_spin.valueChanged.connect(self._on_props_changed)
        tempo_row.addWidget(self._tempo_mult_spin)

        tempo_row.addWidget(QLabel("Versatz:"))
        self._tempo_phase_spin = QDoubleSpinBox()
        self._tempo_phase_spin.setRange(0.0, 1.0)
        self._tempo_phase_spin.setSingleStep(0.05)
        self._tempo_phase_spin.setDecimals(2)
        self._tempo_phase_spin.setValue(float(getattr(self._seq, "phase_offset", 0.0)))
        self._tempo_phase_spin.setToolTip(
            "Phasenversatz in Beats. 0 = gemeinsamer Start auf der Eins.")
        self._tempo_phase_spin.valueChanged.connect(self._on_props_changed)
        tempo_row.addWidget(self._tempo_phase_spin)
        root.addWidget(grp_tempo)

        # Bound fixtures
        bound_box = QGroupBox("Verknüpfte Fixtures")
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
        self._tbl.setMinimumHeight(200)
        self._tbl.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self._tbl.itemChanged.connect(self._on_table_changed)
        st_layout.addWidget(self._tbl)

        st_btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Step (aus Programmer)")
        btn_add.setToolTip("Erstellt neuen Step mit aktuellen Programmer-Werten "
                           "der verknüpften Fixtures")
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

        # ── Aeusserer Scrollbereich + Pop-out-Verwaltung ──────────────────────
        self._editor_window = None
        self._editor_window_scroll = None
        self._editor_scroll = QScrollArea()
        self._editor_scroll.setWidgetResizable(True)
        self._editor_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._editor_scroll.setWidget(self._editor_body)
        self._editor_scroll.setStyleSheet("QScrollArea{border:none;}")
        outer.addWidget(self._editor_scroll, 1)

        self._editor_placeholder = QLabel(
            "⤢ Der Editor ist in einem eigenen großen Fenster geöffnet.\n\n"
            "Zum Andocken das Fenster schließen oder erneut auf »Großes Fenster« tippen.")
        self._editor_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._editor_placeholder.setWordWrap(True)
        self._editor_placeholder.setStyleSheet("color:#8b949e; font-size:11px; padding:24px;")
        self._editor_placeholder.setVisible(False)
        outer.addWidget(self._editor_placeholder, 1)

    def _toggle_editor_popout(self):
        """Koppelt den GANZEN Sequenz-Editor in ein grosses, scrollbares Fenster
        aus / dockt ihn zurueck (loest das Platzproblem bei vielen Step-Zeilen)."""
        if self._editor_window is not None:
            self._editor_window.close()
            return
        body = self._editor_scroll.takeWidget()
        if body is None:
            return
        win = QDialog(self)
        win.setWindowTitle("Sequenz-Editor")
        win.setModal(False)
        wl = QVBoxLayout(win)
        wl.setContentsMargins(6, 6, 6, 6)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.Shape.NoFrame)
        sc.setWidget(body)
        sc.setStyleSheet("QScrollArea{border:none;}")
        wl.addWidget(sc)
        win.resize(760, 980)
        win.finished.connect(lambda *_: self._redock_editor())
        self._editor_window = win
        self._editor_window_scroll = sc
        self._btn_editor_popout.setText("⤡ Andocken")
        self._editor_scroll.setVisible(False)
        self._editor_placeholder.setVisible(True)
        win.show()

    def _redock_editor(self):
        """Holt den Editor-Koerper aus dem Fenster zurueck in die Inline-Ansicht."""
        if self._editor_window is None:
            return
        try:
            body = self._editor_window_scroll.takeWidget()
            if body is not None:
                self._editor_scroll.setWidget(body)
            self._editor_scroll.setVisible(True)
            self._editor_placeholder.setVisible(False)
            self._btn_editor_popout.setText("⤢ Großes Fenster")
        except RuntimeError:
            pass
        self._editor_window = None

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
            # Spalte 1 zeigt den Step-NAMEN (Davids Wunsch: NICHT die Roh-Werte
            # '0 0 0 … 255' je Step). Die Werte stehen im Tooltip + im Werte-Button.
            name = st.note or f"Schritt {i + 1}"
            text_cols = {
                0: str(i + 1), 1: name,
                2: f"{st.fade_in:.2f}", 4: f"{st.hold:.2f}",
                5: f"{st.fade_out:.2f}",
            }
            for col, txt in text_cols.items():
                item = QTableWidgetItem(txt)
                if col == 0:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 1:
                    item.setToolTip(vals_txt or "(keine Werte)")
                self._tbl.setItem(i, col, item)
            # Kurven-Spalten: 3 In-Kurve, 6 Out-Kurve
            self._tbl.setCellWidget(i, 3, self._make_curve_cell(i, "fade_in_curve"))
            self._tbl.setCellWidget(i, 6, self._make_curve_cell(i, "fade_out_curve"))
            # Werte-Spalte (7): Button oeffnet den Werte-Editor (statt Inline-Dump).
            vbtn = QPushButton("Werte…")
            vbtn.setToolTip("Die programmierten Kanalwerte dieses Steps bearbeiten")
            vbtn.clicked.connect(lambda _=False, r=i: self._edit_values(r))
            self._tbl.setCellWidget(i, 7, vbtn)
        self._building = False

    def _make_curve_cell(self, row: int, attr: str) -> CurveThumbnail:
        curve = getattr(self._seq.steps[row], attr)
        thumb = CurveThumbnail(curve)
        label = "Fade-In" if attr == "fade_in_curve" else "Fade-Out"
        thumb.setToolTip(f"{label}-Kurve: {curve.name}\nKlicken zum Bearbeiten")
        thumb.clicked.connect(lambda r=row, a=attr: self._edit_curve(r, a))
        return thumb

    def _edit_curve(self, row: int, attr: str):
        if not (0 <= row < len(self._seq.steps)):
            return
        step = self._seq.steps[row]
        cur = getattr(step, attr)
        label = "Fade-In" if attr == "fade_in_curve" else "Fade-Out"
        dlg = CurveEditorDialog(cur, title=f"{label}-Kurve – Step {row + 1}",
                                parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_curve:
            setattr(step, attr, dlg.result_curve)
            self._refresh_steps()
            self._tbl.selectRow(row)

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
        self._seq.tempo_bus_id = str(self._tempo_bus_combo.currentData() or "")
        self._seq.tempo_multiplier = self._tempo_mult_spin.value()
        self._seq.phase_offset = self._tempo_phase_spin.value()

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
                st.note = item.text()       # Spalte 1 ist jetzt der Step-NAME
            elif col == 2:
                st.fade_in = max(0.0, float(item.text()))
            elif col == 4:
                st.hold = max(0.0, float(item.text()))
            elif col == 5:
                st.fade_out = max(0.0, float(item.text()))
        except ValueError:
            pass

    def _edit_values(self, row: int):
        """Werte-Editor fuer EINEN Step (statt Inline-Dump in der Step-Liste)."""
        if not (0 <= row < len(self._seq.steps)):
            return
        st = self._seq.steps[row]
        text, ok = QInputDialog.getMultiLineText(
            self, f"Werte – {st.note or f'Schritt {row + 1}'}",
            "Format: FID:attr=wert[, attr=wert]; FID:attr=wert …\n"
            "z.B. '3:dimmer=255, red=200; 5:dimmer=128'",
            self._format_values(st.values))
        if not ok:
            return
        parsed = self._parse_values(text)
        if parsed is None:
            QMessageBox.warning(self, "Ungültiges Format",
                                "Erwartet: 'FID:attr=wert, attr=wert; FID:attr=wert'")
            return
        st.values = parsed
        self._refresh_steps()

    # ── Fixtures ─────────────────────────────────────────────────────────────

    def _add_fixture(self):
        state = get_state()
        pfs = state.get_patched_fixtures()
        if not pfs:
            QMessageBox.information(self, "Keine Fixtures",
                                    "Erst Geräte im Patch hinzufügen.")
            return
        options = [f"FID {f.fid}: {f.label}" for f in pfs
                   if f.fid not in self._seq.bound_fixtures]
        if not options:
            return
        sel, ok = QInputDialog.getItem(
            self, "Fixture hinzufügen", "Auswählen:", options, 0, False)
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
                                    "Erst Fixtures verknüpfen.")
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
