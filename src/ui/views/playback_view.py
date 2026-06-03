"""Playback-Ansicht — Cuelisten, Executor-Fader, GO/BACK."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel, QComboBox, QSplitter,
    QGroupBox, QSlider, QDoubleSpinBox, QLineEdit, QInputDialog,
    QAbstractItemView, QSizePolicy, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from src.core.app_state import get_state, AppState
from src.core.engine.cue_stack import CueStack
from src.core.engine.cue import Cue

CUE_COLS = ["Nr.", "Label", "Fade In", "Fade Out", "Delay", "Follow"]


class PlaybackView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: AppState = get_state()
        self._current_stack: CueStack | None = None
        self._state.subscribe(self._on_state)
        self._setup_ui()
        self._refresh_stack_combo()
        # Tick-Timer für Cue-Positionsanzeige
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._update_cue_highlight)
        self._tick.start(50)

        # Zentraler StateSync
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe(SyncEvent.REFRESH_ALL, lambda *_: self._sync_refresh())
            sync.subscribe(SyncEvent.CUE_STACK_CHANGED, lambda *_: self._sync_refresh())
            sync.subscribe(SyncEvent.PATCH_CHANGED, lambda *_: self._sync_refresh())
        except Exception as e:
            print(f"[playback_view] sync subscribe error: {e}")

    def _sync_refresh(self):
        try:
            self._refresh_stack_combo()
            self._refresh_table()
            self._refresh_executors()
        except Exception as e:
            print(f"[playback_view] sync_refresh error: {e}")

    def _refresh_executors(self):
        for w in getattr(self, "_executors_widgets", []):
            try:
                w.refresh_from_state()
            except Exception as e:
                print(f"[playback_view] executor refresh error: {e}")

    # ── Multi-Page (T0.1) ───────────────────────────────────────────────────

    def _switch_page(self, page_idx: int):
        """User klickt Page-Button."""
        pe = self._state.playback_engine
        if pe:
            pe.set_page(page_idx)
        # Visuell aktualisieren
        for i, btn in enumerate(self._page_buttons):
            btn.setChecked(i == page_idx)
        self._refresh_stack_combo()
        self._refresh_executors()

    def _on_page_changed_from_engine(self, page_idx: int):
        """Engine meldet Page-Wechsel (z.B. via MIDI/Hotkey)."""
        for i, btn in enumerate(self._page_buttons):
            btn.setChecked(i == page_idx)
        self._refresh_stack_combo()
        self._refresh_executors()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Page-Selector (T0.1 Multi-Page-Playback) ─────────────────────────
        page_row = QHBoxLayout()
        page_row.setSpacing(2)
        page_row.addWidget(QLabel("Page:"))
        self._page_buttons: list[QPushButton] = []
        for i in range(10):
            btn = QPushButton(str(i + 1))
            btn.setFixedSize(34, 26)
            btn.setCheckable(True)
            btn.setStyleSheet(
                "QPushButton { background:#2a3a4a; color:#ddd; border:1px solid #4a5a6a; }"
                "QPushButton:hover { background:#3a4a5a; }"
                "QPushButton:checked { background:#ffd700; color:#000; font-weight:bold; }"
            )
            btn.clicked.connect(lambda checked=False, idx=i: self._switch_page(idx))
            page_row.addWidget(btn)
            self._page_buttons.append(btn)
        page_row.addStretch()
        # Page-Subscriber damit UI mit Engine sync ist
        pe = self._state.playback_engine
        if pe:
            pe.subscribe_page(lambda idx: self._on_page_changed_from_engine(idx))
            self._page_buttons[pe.current_page].setChecked(True)
        else:
            self._page_buttons[0].setChecked(True)
        layout.addLayout(page_row)

        # ── Obere Leiste: Stack-Auswahl + Transport ────────────────────────────
        top = QHBoxLayout()

        top.addWidget(QLabel("Cueliste:"))
        self._combo_stack = QComboBox()
        self._combo_stack.setMinimumWidth(200)
        self._combo_stack.currentIndexChanged.connect(self._on_stack_selected)
        top.addWidget(self._combo_stack)

        btn_new = QPushButton("+ Neu")
        btn_new.clicked.connect(self._new_stack)
        btn_del = QPushButton("Löschen")
        btn_del.setObjectName("btn_danger")
        btn_del.clicked.connect(self._delete_stack)
        top.addWidget(btn_new)
        top.addWidget(btn_del)
        top.addStretch()

        # Transport-Buttons
        self._btn_go = QPushButton("GO")
        self._btn_go.setObjectName("btn_go")
        self._btn_go.setFixedSize(80, 48)
        self._btn_go.clicked.connect(self._go)

        btn_back = QPushButton("◀ BACK")
        btn_back.setFixedSize(80, 48)
        btn_back.clicked.connect(self._back)

        btn_stop = QPushButton("■ STOP")
        btn_stop.setFixedSize(80, 48)
        btn_stop.setObjectName("btn_danger")
        btn_stop.clicked.connect(self._stop)

        top.addWidget(btn_back)
        top.addWidget(self._btn_go)
        top.addWidget(btn_stop)
        layout.addLayout(top)

        # ── Hauptbereich: Cueliste + Optionen ────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Cue-Tabelle
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)

        cue_toolbar = QHBoxLayout()
        btn_add_cue = QPushButton("+ Cue aufnehmen")
        btn_add_cue.clicked.connect(self._record_cue)
        btn_del_cue = QPushButton("Cue löschen")
        btn_del_cue.setObjectName("btn_danger")
        btn_del_cue.clicked.connect(self._delete_cue)
        cue_toolbar.addWidget(btn_add_cue)
        cue_toolbar.addWidget(btn_del_cue)
        cue_toolbar.addStretch()
        lv.addLayout(cue_toolbar)

        self._table = QTableWidget(0, len(CUE_COLS))
        self._table.setHorizontalHeaderLabels(CUE_COLS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in [0, 2, 3, 4, 5]:
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self._table.itemChanged.connect(self._on_cue_edited)
        lv.addWidget(self._table)

        splitter.addWidget(left)

        # Rechts: Cue-Details + Status
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(4, 0, 0, 0)

        # Aktuelle Cue
        box_current = QGroupBox("Aktive Cue")
        bc = QVBoxLayout(box_current)
        self._lbl_current = QLabel("—")
        self._lbl_current.setObjectName("label_header")
        self._lbl_next = QLabel("Nächste: —")
        self._lbl_next.setStyleSheet("color: #888;")
        bc.addWidget(self._lbl_current)
        bc.addWidget(self._lbl_next)
        rv.addWidget(box_current)

        # Crossfade-Fader
        box_xfade = QGroupBox("Crossfade (manuell)")
        bx = QVBoxLayout(box_xfade)
        self._xfade = QSlider(Qt.Orientation.Horizontal)
        self._xfade.setRange(0, 100)
        self._xfade.setValue(100)
        bx.addWidget(self._xfade)
        rv.addWidget(box_xfade)

        # Loop
        box_opts = QGroupBox("Optionen")
        bo = QVBoxLayout(box_opts)
        self._btn_loop = QPushButton("Loop: AUS")
        self._btn_loop.setCheckable(True)
        self._btn_loop.toggled.connect(self._toggle_loop)
        bo.addWidget(self._btn_loop)
        rv.addWidget(box_opts)

        rv.addStretch()
        splitter.addWidget(right)
        splitter.setSizes([700, 250])
        layout.addWidget(splitter)

        # ── Executor-Leiste ───────────────────────────────────────────────────
        layout.addWidget(QLabel("Executor-Leiste:"))
        exec_scroll = QHBoxLayout()
        self._executors_widgets: list[ExecutorWidget] = []
        for i in range(1, 11):
            ex_widget = ExecutorWidget(i, self._state)
            exec_scroll.addWidget(ex_widget)
            self._executors_widgets.append(ex_widget)
        exec_widget = QWidget()
        exec_widget.setLayout(exec_scroll)
        exec_widget.setFixedHeight(140)
        layout.addWidget(exec_widget)

    # ── Cuelisten-Verwaltung ──────────────────────────────────────────────────

    def _refresh_stack_combo(self):
        self._combo_stack.blockSignals(True)
        self._combo_stack.clear()
        for stack in self._state.cue_stacks:
            self._combo_stack.addItem(stack.name)
        self._combo_stack.blockSignals(False)
        if self._state.cue_stacks:
            self._current_stack = self._state.cue_stacks[0]
            self._refresh_table()

    def _on_stack_selected(self, idx: int):
        if 0 <= idx < len(self._state.cue_stacks):
            self._current_stack = self._state.cue_stacks[idx]
            self._refresh_table()

    def _new_stack(self):
        name, ok = QInputDialog.getText(self, "Neue Cueliste", "Name:")
        if ok and name:
            self._state.new_cue_stack(name)

    def _delete_stack(self):
        if not self._current_stack:
            return
        reply = QMessageBox.question(
            self, "Löschen?",
            f'Cueliste "{self._current_stack.name}" löschen?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._state.remove_cue_stack(self._current_stack)
            self._current_stack = None

    def _refresh_table(self):
        if not self._current_stack:
            self._table.setRowCount(0)
            return
        cues = self._current_stack.cues
        self._table.blockSignals(True)
        self._table.setRowCount(len(cues))
        for row, cue in enumerate(cues):
            items = [
                str(cue.number),
                cue.label,
                f"{cue.fade_in:.1f}s",
                f"{cue.fade_out:.1f}s",
                f"{cue.delay_in:.1f}s",
                f"{cue.follow:.1f}s" if cue.follow is not None else "—",
            ]
            for col, val in enumerate(items):
                item = QTableWidgetItem(val)
                if col != 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, col, item)
        self._table.blockSignals(False)

    # ── Transport ─────────────────────────────────────────────────────────────

    def _go(self):
        if self._current_stack:
            self._current_stack.go()

    def _back(self):
        if self._current_stack:
            self._current_stack.back()

    def _stop(self):
        if self._current_stack:
            self._current_stack.stop()
            self._lbl_current.setText("—")
            self._lbl_next.setText("Nächste: —")

    def _toggle_loop(self, checked: bool):
        if self._current_stack:
            self._current_stack.loop = checked
        self._btn_loop.setText(f"Loop: {'AN' if checked else 'AUS'}")

    # ── Cue Record / Delete ───────────────────────────────────────────────────

    def _record_cue(self):
        if not self._current_stack:
            QMessageBox.information(self, "Info", "Erst eine Cueliste anlegen.")
            return
        existing = [c.number for c in self._current_stack.cues]
        next_num = (max(existing) + 1.0) if existing else 1.0
        num, ok = QInputDialog.getDouble(
            self, "Cue aufnehmen", "Cue-Nummer:", next_num, 0.1, 9999.0, 1
        )
        if not ok:
            return
        label, ok2 = QInputDialog.getText(self, "Cue aufnehmen", "Label:")
        if not ok2:
            label = f"Cue {num}"
        self._state.record_cue(self._current_stack, num, label)
        self._refresh_table()

    def _delete_cue(self):
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        if not self._current_stack or not rows:
            return
        for row in sorted(rows, reverse=True):
            if row < len(self._current_stack.cues):
                cue = self._current_stack.cues[row]
                self._current_stack.remove_cue(cue.number)
        self._refresh_table()

    def _on_cue_edited(self, item: QTableWidgetItem):
        if not self._current_stack:
            return
        row = item.row()
        col = item.column()
        if row >= len(self._current_stack.cues):
            return
        cue = self._current_stack.cues[row]
        try:
            val = item.text().replace("s", "").strip()
            if col == 1:
                cue.label = item.text()
            elif col == 2:
                cue.fade_in = float(val)
            elif col == 3:
                cue.fade_out = float(val)
            elif col == 4:
                cue.delay_in = float(val)
            elif col == 5:
                cue.follow = None if val == "—" else float(val)
        except ValueError:
            pass

    def _update_cue_highlight(self):
        if not self._current_stack:
            return
        idx = self._current_stack.current_index
        cue = self._current_stack.current_cue

        # Tabellenzeile hervorheben
        for row in range(self._table.rowCount()):
            color = QColor("#1a3a1a" if row == idx else "#1e1e1e")
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item:
                    item.setBackground(color)

        if cue:
            self._lbl_current.setText(f"▶ Cue {cue.number} — {cue.label}")
            # Nächste Cue
            next_idx = idx + 1
            if next_idx < len(self._current_stack.cues):
                nc = self._current_stack.cues[next_idx]
                self._lbl_next.setText(f"Nächste: {nc.number} — {nc.label}")
            else:
                self._lbl_next.setText("Nächste: Ende")

    def _on_state(self, event: str, _data):
        if event in ("stacks_changed", "cue_recorded"):
            self._refresh_stack_combo()
            self._refresh_executors()


class ExecutorWidget(QWidget):
    """Ein Executor-Slot: Fader + Label + 3 Buttons."""

    def __init__(self, slot: int, state: AppState, parent=None):
        super().__init__(parent)
        self._slot = slot
        self._state = state
        self.setFixedWidth(110)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Label
        self._lbl = QLabel(f"Ex {self._slot}")
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl.setStyleSheet("font-size: 11px; color: #aaa;")
        layout.addWidget(self._lbl)

        # Stack-Zuweisung
        self._combo = QComboBox()
        self._combo.addItem("— Leer —", None)
        for s in self._state.cue_stacks:
            self._combo.addItem(s.name, s)
        self._combo.currentIndexChanged.connect(self._assign_stack)
        self._combo.setStyleSheet("font-size: 10px;")
        layout.addWidget(self._combo)

        # Fader
        self._fader = QSlider(Qt.Orientation.Vertical)
        self._fader.setRange(0, 100)
        self._fader.setValue(100)
        self._fader.setFixedHeight(50)
        self._fader.valueChanged.connect(self._fader_changed)
        layout.addWidget(self._fader, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Buttons
        btn_layout = QHBoxLayout()
        self._btn_go = QPushButton("GO")
        self._btn_go.setFixedHeight(22)
        self._btn_go.setStyleSheet("font-size: 10px; background: #006600; color: #00ff00;")
        self._btn_go.clicked.connect(self._go)

        self._btn_back = QPushButton("◀")
        self._btn_back.setFixedHeight(22)
        self._btn_back.setStyleSheet("font-size: 10px;")
        self._btn_back.clicked.connect(self._back)

        self._btn_flash = QPushButton("FL")
        self._btn_flash.setFixedHeight(22)
        self._btn_flash.setStyleSheet("font-size: 10px;")
        self._btn_flash.pressed.connect(self._flash_on)
        self._btn_flash.released.connect(self._flash_off)

        btn_layout.addWidget(self._btn_go)
        btn_layout.addWidget(self._btn_back)
        btn_layout.addWidget(self._btn_flash)
        layout.addLayout(btn_layout)

        # Rahmen
        self.setStyleSheet("border: 1px solid #333; border-radius: 4px;")

    def _assign_stack(self, idx: int):
        if not self._state.playback_engine:
            return
        ex = self._state.playback_engine.get_executor(self._slot)
        stack = self._combo.currentData()
        ex.stack = stack
        self._lbl.setText(stack.name[:12] if stack else f"Ex {self._slot}")

    def refresh_from_state(self):
        """Combo/Fader/Label aus dem Executor der aktuellen Page neu aufbauen
        (nach Show-Load, Page-Wechsel oder Cuelisten-Aenderung)."""
        pe = self._state.playback_engine
        if not pe:
            return
        ex = pe.get_executor(self._slot)
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItem("— Leer —", None)
        sel = 0
        for i, s in enumerate(self._state.cue_stacks):
            self._combo.addItem(s.name, s)
            if s is ex.stack:
                sel = i + 1
        self._combo.setCurrentIndex(sel)
        self._combo.blockSignals(False)
        self._lbl.setText(ex.stack.name[:12] if ex.stack else f"Ex {self._slot}")
        self._fader.blockSignals(True)
        self._fader.setValue(int(round(ex.fader_value * 100)))
        self._fader.blockSignals(False)

    def _fader_changed(self, value: int):
        if not self._state.playback_engine:
            return
        ex = self._state.playback_engine.get_executor(self._slot)
        ex.fader_value = value / 100.0

    def _go(self):
        if self._state.playback_engine:
            self._state.playback_engine.get_executor(self._slot).press_btn(0)

    def _back(self):
        if self._state.playback_engine:
            self._state.playback_engine.get_executor(self._slot).press_btn(1)

    def _flash_on(self):
        if self._state.playback_engine:
            self._state.playback_engine.get_executor(self._slot).press_btn(2)

    def _flash_off(self):
        if self._state.playback_engine:
            self._state.playback_engine.get_executor(self._slot).release_btn(2)
