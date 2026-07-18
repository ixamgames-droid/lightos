"""Playback-Ansicht — Cuelisten, Executor-Fader, GO/BACK."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel, QComboBox, QSplitter,
    QGroupBox, QSlider, QDoubleSpinBox, QLineEdit, QInputDialog,
    QAbstractItemView, QSizePolicy, QFrame, QMessageBox,
    QDialog, QFormLayout, QDialogButtonBox
)
from PySide6.QtCore import Qt, QTimer, Signal, QEvent
from PySide6.QtGui import QColor, QFont
from src.core.app_state import get_state, AppState
from src.core.engine.cue_stack import CueStack
from src.core.engine.cue import Cue
from src.core.engine import fade_curve
from src.ui.weak_slots import weak_slot

CUE_COLS = ["Nr.", "Label", "Fade In", "Fade Out", "Delay", "Follow", "Kurve"]


class PlaybackView(QWidget):
    # Engine meldet Page-Wechsel ggf. aus einem Worker-Thread (MIDI-RX). Das
    # Signal marshallt die UI-Aktualisierung thread-sicher in den GUI-Thread:
    # Same-Thread-Emit (User-Klick) laeuft direkt, Cross-Thread-Emit (MIDI) wird
    # per AutoConnection automatisch in den GUI-Thread gequeued. Frueher rief der
    # MIDI-Thread _on_page_changed_from_engine direkt auf -> _refresh_table baute
    # QWidgets cross-thread um -> Freeze + Access Violation (crash.log 2026-06-14).
    _page_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: AppState = get_state()
        self._current_stack: CueStack | None = None
        self._last_hl_idx = None          # zuletzt hervorgehobene Cue-Zeile (Churn-Schutz)
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
            btn.clicked.connect(weak_slot(self._switch_page, i))
            page_row.addWidget(btn)
            self._page_buttons.append(btn)
        page_row.addStretch()
        # Page-Subscriber damit UI mit Engine sync ist. Die Engine ruft die
        # Subscriber ggf. aus dem MIDI-Thread auf -> NICHT direkt UI anfassen,
        # sondern ueber das Signal in den GUI-Thread marshallen (AutoConnection).
        self._page_changed.connect(self._on_page_changed_from_engine)
        pe = self._state.playback_engine
        if pe:
            pe.subscribe_page(lambda idx: self._page_changed.emit(int(idx)))
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
        btn_quick = QPushButton("⚡ Quick-Rec")
        btn_quick.setToolTip(
            "Sofort als neue Cue auf der aktuellen Cueliste aufnehmen "
            "(Auto-Nummer/Label, kein Dialog)")
        btn_quick.clicked.connect(self._quick_record_cue)
        btn_del_cue = QPushButton("Cue löschen")
        btn_del_cue.setObjectName("btn_danger")
        btn_del_cue.clicked.connect(self._delete_cue)
        btn_goto = QPushButton("▶ Hierhin springen")
        btn_goto.setToolTip("Direkt zur markierten Cue faden (statt mehrfach GO)")
        btn_goto.clicked.connect(self._go_to_selected)
        cue_toolbar.addWidget(btn_add_cue)
        cue_toolbar.addWidget(btn_quick)
        cue_toolbar.addWidget(btn_del_cue)
        cue_toolbar.addWidget(btn_goto)
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
        for c in [0, 2, 3, 4, 5, 6]:
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self._table.itemChanged.connect(self._on_cue_edited)
        lv.addWidget(self._table)

        # UI-24b: Leerzustand-Hinweis über der (leeren) Cue-Tabelle statt leerer
        # Fläche. Als Overlay auf dem Viewport, per eventFilter mitzentriert.
        self._table_empty = QLabel(
            'Keine Cues — „+ Cue" hinzufügen oder oben eine Cueliste wählen.',
            self._table.viewport())
        self._table_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table_empty.setWordWrap(True)
        self._table_empty.setStyleSheet("color:#777; font-style:italic;")
        self._table.viewport().installEventFilter(self)
        self._table_empty.hide()

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

        # Crossfade-Fader (manueller Crossfade auf die aktive Cueliste)
        box_xfade = QGroupBox("Crossfade (manuell)")
        bx = QVBoxLayout(box_xfade)
        self._xfade = QSlider(Qt.Orientation.Horizontal)
        self._xfade.setRange(0, 100)
        self._xfade.setValue(0)
        self._xfade.setToolTip(
            "Von Hand von der aktiven zur nächsten Cue faden.\n"
            "Ganz rechts = Übergang übernommen, Fader springt zurück auf 0."
        )
        self._xfade.valueChanged.connect(self._on_xfade)
        bx.addWidget(self._xfade)
        xrow = QHBoxLayout()
        _xa = QLabel("Aktiv"); _xb = QLabel("Nächste ▶")
        _xa.setStyleSheet("color:#888; font-size:10px;")
        _xb.setStyleSheet("color:#888; font-size:10px;")
        xrow.addWidget(_xa); xrow.addStretch(); xrow.addWidget(_xb)
        bx.addLayout(xrow)
        rv.addWidget(box_xfade)

        # Loop
        box_opts = QGroupBox("Optionen")
        bo = QVBoxLayout(box_opts)
        self._btn_loop = QPushButton("Loop: AUS")
        self._btn_loop.setCheckable(True)
        self._btn_loop.toggled.connect(self._toggle_loop)
        bo.addWidget(self._btn_loop)
        # F-7: Ablauf-Modus (Einzel/Loop/Bounce/Ping-Pong)
        from PySide6.QtWidgets import QComboBox as _QCombo
        bo.addWidget(QLabel("Modus:"))
        self._combo_mode = _QCombo()
        for _m, _lbl in (("single", "Einzel (am Ende stop)"), ("loop", "Loop"),
                         ("bounce", "Bounce"), ("pingpong", "Ping-Pong")):
            self._combo_mode.addItem(_lbl, _m)
        self._combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        bo.addWidget(self._combo_mode)
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
        # Aktuelle Auswahl merken, damit ein Refresh (Cue aufgenommen, Page-Wechsel,
        # zentraler Sync) NICHT ungewollt auf die erste Cueliste zurueckspringt.
        prev = self._current_stack
        stacks = self._state.cue_stacks
        self._combo_stack.blockSignals(True)
        self._combo_stack.clear()
        for stack in stacks:
            self._combo_stack.addItem(stack.name)
        sel = stacks.index(prev) if prev in stacks else (0 if stacks else -1)
        self._combo_stack.setCurrentIndex(sel)
        self._combo_stack.blockSignals(False)
        if 0 <= sel < len(stacks):
            self._current_stack = stacks[sel]
            self._refresh_table()
            self._sync_mode_combo()
        else:
            self._current_stack = None
            self._refresh_table()

    def _on_stack_selected(self, idx: int):
        if 0 <= idx < len(self._state.cue_stacks):
            self._current_stack = self._state.cue_stacks[idx]
            self._refresh_table()
            self._sync_mode_combo()
            self._reset_xfade()

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
            removed = self._current_stack
            self._state.remove_cue_stack(removed)
            # remove_cue_stack emittiert synchron stacks_changed -> der Combo-Refresh
            # hat _current_stack ggf. schon auf die naechste gueltige Cueliste gesetzt.
            # Nur auf None setzen, wenn wirklich noch die geloeschte referenziert wird —
            # sonst zeigte die Combo eine Auswahl, waehrend die Cue-Tabelle leer blieb.
            if self._current_stack is removed:
                self._current_stack = None

    def eventFilter(self, obj, event):
        # UI-24b: den Leerzustand-Hinweis auf die Viewport-Größe zentrieren.
        if (getattr(self, "_table_empty", None) is not None
                and obj is self._table.viewport()
                and event.type() == QEvent.Type.Resize):
            self._table_empty.setGeometry(self._table.viewport().rect())
        return super().eventFilter(obj, event)

    def _refresh_table(self):
        empty = (not self._current_stack) or (not self._current_stack.cues)
        if getattr(self, "_table_empty", None) is not None:
            if empty:
                self._table_empty.setGeometry(self._table.viewport().rect())
            self._table_empty.setVisible(empty)
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
            # F-5: Fade-Verlauf als Combo (eigene Zelle, kein itemChanged)
            self._table.setCellWidget(row, 6, self._make_curve_combo(cue))
        self._table.blockSignals(False)
        # Zeilen wurden neu aufgebaut -> Highlight im naechsten Tick neu zeichnen.
        self._last_hl_idx = None

    def _make_curve_combo(self, cue) -> QComboBox:
        """F-5: Combo zur Wahl des Fade-Verlaufs einer Cue.
        Aenderung schreibt direkt in cue.fade_curve (wird mit der Show gespeichert)."""
        combo = QComboBox()
        for name in fade_curve.CURVE_NAMES:
            combo.addItem(fade_curve.CURVE_LABELS[name], name)
        cur = getattr(cue, "fade_curve", "scurve")
        try:
            combo.setCurrentIndex(fade_curve.CURVE_NAMES.index(cur))
        except ValueError:
            combo.setCurrentIndex(0)
        # currentData() erst NACH setCurrentIndex verbinden -> kein Spurious-Fire.
        combo.currentIndexChanged.connect(
            lambda _i, c=cue, cb=combo: setattr(c, "fade_curve", cb.currentData())
        )
        return combo

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
        self._reset_xfade()

    def _on_xfade(self, value: int):
        """Manueller Crossfade-Fader -> scrubbt die aktive Cueliste von Hand."""
        if not self._current_stack:
            return
        committed = self._current_stack.manual_crossfade(value / 100.0)
        if committed:
            self._reset_xfade()

    def _reset_xfade(self):
        if hasattr(self, "_xfade"):
            self._xfade.blockSignals(True)
            self._xfade.setValue(0)
            self._xfade.blockSignals(False)

    def _toggle_loop(self, checked: bool):
        if self._current_stack:
            self._current_stack.loop = checked
        self._btn_loop.setText(f"Loop: {'AN' if checked else 'AUS'}")
        self._sync_mode_combo()

    def _on_mode_changed(self, _idx: int):
        """F-7: Ablauf-Modus des aktuellen Stacks setzen (Einzel/Loop/Bounce/Ping-Pong)."""
        if self._current_stack is None:
            return
        mode = self._combo_mode.currentData() or "single"
        self._current_stack.mode = mode
        self._btn_loop.blockSignals(True)
        self._btn_loop.setChecked(mode != "single")
        self._btn_loop.setText(f"Loop: {'AN' if mode != 'single' else 'AUS'}")
        self._btn_loop.blockSignals(False)

    def _sync_mode_combo(self):
        """Combo + Loop-Button an den Modus des aktuellen Stacks angleichen."""
        if self._current_stack is None or not hasattr(self, "_combo_mode"):
            return
        mode = getattr(self._current_stack, "mode", "single")
        self._combo_mode.blockSignals(True)
        for i in range(self._combo_mode.count()):
            if self._combo_mode.itemData(i) == mode:
                self._combo_mode.setCurrentIndex(i)
                break
        self._combo_mode.blockSignals(False)

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

    def _quick_record_cue(self):
        """F-14: dialogfreies Ein-Klick-Record auf die AKTUELLE Cueliste
        (Auto-Nummer = letzte+1, Auto-Label 'Cue N'), ohne QInputDialog."""
        if not self._current_stack:
            QMessageBox.information(self, "Info", "Erst eine Cueliste anlegen.")
            return
        existing = [c.number for c in self._current_stack.cues]
        n = (max(existing) + 1.0) if existing else 1.0
        self._state.record_cue(self._current_stack, n, f"Cue {n:g}")
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

    def _go_to_selected(self):
        """Direkt zur markierten Cue faden (go_to nutzt den normalen Fade-In)."""
        if not self._current_stack:
            return
        rows = sorted({idx.row() for idx in self._table.selectedIndexes()})
        if not rows or rows[0] >= len(self._current_stack.cues):
            return
        self._current_stack.go_to(self._current_stack.cues[rows[0]].number)

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
            if col == 0:
                new_num = round(float(val.replace(",", ".")), 3)
                if not any(abs(c.number - new_num) < 0.001 and c is not cue
                           for c in self._current_stack.cues):
                    # ENG-13: NICHT cue.number direkt setzen + cues.sort() — das umging
                    # _reindex_after_mutation und liess _current_idx einer laufenden
                    # Cueliste auf die falsche Cue zeigen (Replay/Skip) + lief ohne Lock
                    # gegen den Engine-Tick-Thread. renumber_cue macht beides konsistent.
                    self._current_stack.renumber_cue(cue, new_num)
                self._refresh_table()
                return
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

        # Aktive Zeile hervorheben — nur neu zeichnen, wenn sich der Index aendert
        # (kein 50-Hz-Churn) und mit blockierten Signalen, sonst loest setBackground
        # bei jeder Zelle staendig itemChanged -> _on_cue_edited aus.
        if idx != self._last_hl_idx:
            self._last_hl_idx = idx
            self._table.blockSignals(True)
            for row in range(self._table.rowCount()):
                brush = QColor("#1a3a1a") if row == idx else QColor()
                for col in range(self._table.columnCount()):
                    item = self._table.item(row, col)
                    if item:
                        item.setBackground(brush)
            self._table.blockSignals(False)

        if cue:
            self._lbl_current.setText(f"▶ Cue {cue.number} — {cue.label}")
            # Naechste Cue modusabhaengig (loop/bounce/pingpong) statt naivem
            # idx+1 — der zeigte am Listenende/bei bounce die falsche Vorschau.
            try:
                next_idx, _d = self._current_stack.peek_next()
            except Exception:
                next_idx = idx + 1
            if (next_idx is not None
                    and 0 <= next_idx < len(self._current_stack.cues)):
                nc = self._current_stack.cues[next_idx]
                self._lbl_next.setText(f"Nächste: {nc.number} — {nc.label}")
            else:
                self._lbl_next.setText("Nächste: Ende")

    def _on_state(self, event: str, _data):
        if event in ("stacks_changed", "cue_recorded"):
            self._refresh_stack_combo()
            self._refresh_executors()

    # ── Tab sichtbar/versteckt: Tick-Timer pausieren (CPU sparen) ──────────────

    def showEvent(self, event):
        super().showEvent(event)
        if not self._tick.isActive():
            self._tick.start(50)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._tick.stop()


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

        # Kopfzeile: Label + Konfig-Zahnrad
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(2)
        self._lbl = QLabel(f"Ex {self._slot}")
        self._lbl.setStyleSheet("font-size: 11px; color: #aaa;")
        head.addWidget(self._lbl, 1)
        self._btn_cfg = QPushButton("⚙")
        self._btn_cfg.setFixedSize(18, 18)
        self._btn_cfg.setToolTip("Executor konfigurieren (Label, Fader-Funktion, Tasten)")
        self._btn_cfg.setStyleSheet("font-size: 10px; padding: 0; border: none;")
        self._btn_cfg.clicked.connect(self._open_config)
        head.addWidget(self._btn_cfg)
        layout.addLayout(head)

        # Stack-Zuweisung
        self._combo = QComboBox()
        self._combo.addItem("— Leer —", None)
        for s in self._state.cue_stacks:
            self._combo.addItem(s.name, s)
        self._combo.currentIndexChanged.connect(self._assign_stack)
        self._combo.setStyleSheet("font-size: 10px;")
        layout.addWidget(self._combo)

        # Fader (Intensität ODER manueller Crossfade — je nach fader_function)
        self._fader = QSlider(Qt.Orientation.Vertical)
        self._fader.setRange(0, 100)
        self._fader.setValue(100)
        self._fader.setFixedHeight(50)
        self._fader.valueChanged.connect(self._fader_changed)
        layout.addWidget(self._fader, alignment=Qt.AlignmentFlag.AlignHCenter)

        # 3 frei konfigurierbare Tasten (einheitlich pressed/released, damit
        # FLASH auch dann momentan ist, wenn es auf Taste 1/2 liegt).
        btn_layout = QHBoxLayout()
        self._fn_buttons: list[QPushButton] = []
        for i in range(3):
            b = QPushButton()
            b.setFixedHeight(22)
            b.pressed.connect(weak_slot(self._press, i))
            b.released.connect(weak_slot(self._release, i))
            btn_layout.addWidget(b)
            self._fn_buttons.append(b)
        layout.addLayout(btn_layout)
        self._relabel_buttons()

        # Rahmen
        self.setStyleSheet("border: 1px solid #333; border-radius: 4px;")

    # ── Executor-Zugriff / Konfiguration ──────────────────────────────────────

    BTN_LABELS = {"go": "GO", "back": "◀", "stop": "■", "flash": "FL"}
    BTN_TIPS = {"go": "GO – nächste Cue", "back": "BACK – eine Cue zurück",
                "stop": "STOP", "flash": "FLASH (gedrückt halten)"}

    def _executor(self):
        pe = self._state.playback_engine
        return pe.get_executor(self._slot) if pe else None

    def _display_name(self, ex) -> str:
        """Eigenes Label hat Vorrang, sonst Stack-Name, sonst 'Ex N'."""
        if ex and ex.label and ex.label != f"Exec {ex.slot}":
            return ex.label[:12]
        if ex and ex.stack:
            return ex.stack.name[:12]
        return f"Ex {self._slot}"

    def _relabel_buttons(self):
        ex = self._executor()
        fns = (ex.btn1, ex.btn2, ex.btn3) if ex else ("go", "back", "flash")
        for b, fn in zip(self._fn_buttons, fns):
            b.setText(self.BTN_LABELS.get(fn, fn[:2].upper()))
            b.setToolTip(self.BTN_TIPS.get(fn, fn))
            style = "font-size: 10px;"
            if fn == "go":
                style += " background: #006600; color: #00ff00;"
            b.setStyleSheet(style)

    def _press(self, i: int):
        ex = self._executor()
        if ex:
            ex.press_btn(i)

    def _release(self, i: int):
        ex = self._executor()
        if ex:
            ex.release_btn(i)

    def _open_config(self):
        ex = self._executor()
        if not ex:
            return
        dlg = ExecutorConfigDialog(ex, self)
        if dlg.exec():
            dlg.apply()
            self._relabel_buttons()
            self._lbl.setText(self._display_name(ex))
            self._sync_fader_for_function(ex)

    def _sync_fader_for_function(self, ex):
        """Fader-Startwert je nach Funktion: Crossfade ruht auf 0, Volume auf
        dem gespeicherten Pegel."""
        self._fader.blockSignals(True)
        if ex.fader_function == "crossfade":
            self._fader.setValue(0)
        else:
            self._fader.setValue(int(round(ex.fader_value * 100)))
        self._fader.blockSignals(False)

    def _assign_stack(self, idx: int):
        ex = self._executor()
        if not ex:
            return
        ex.stack = self._combo.currentData()
        self._lbl.setText(self._display_name(ex))

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
        self._lbl.setText(self._display_name(ex))
        self._relabel_buttons()
        self._sync_fader_for_function(ex)

    def _fader_changed(self, value: int):
        """Volume-Fader skaliert die Intensität; Crossfade-Fader scrubbt die Cue."""
        ex = self._executor()
        if not ex:
            return
        if ex.fader_function == "crossfade":
            if ex.stack and ex.stack.manual_crossfade(value / 100.0):
                self._fader.blockSignals(True)
                self._fader.setValue(0)        # Übergang übernommen -> Fader zurück
                self._fader.blockSignals(False)
        else:
            ex.fader_value = value / 100.0


class ExecutorConfigDialog(QDialog):
    """Konfiguriert einen Executor: Label, Fader-Funktion und die 3 Tasten."""

    FADER_FUNCS = [("volume", "Intensität (Dimmer)"),
                   ("crossfade", "Manueller Crossfade")]
    BTN_FUNCS = [("go", "GO – nächste Cue"), ("back", "BACK – zurück"),
                 ("stop", "STOP"), ("flash", "FLASH (halten)")]

    def __init__(self, ex, parent=None):
        super().__init__(parent)
        self._ex = ex
        self.setWindowTitle(f"Executor {ex.slot}")
        form = QFormLayout(self)

        self._ed_label = QLineEdit(ex.label)
        form.addRow("Label:", self._ed_label)

        self._cb_fader = QComboBox()
        for v, lbl in self.FADER_FUNCS:
            self._cb_fader.addItem(lbl, v)
        _select_by_data(self._cb_fader, ex.fader_function)
        form.addRow("Fader:", self._cb_fader)

        self._cb_btn: list[QComboBox] = []
        for i, cur in enumerate((ex.btn1, ex.btn2, ex.btn3)):
            cb = QComboBox()
            for v, lbl in self.BTN_FUNCS:
                cb.addItem(lbl, v)
            _select_by_data(cb, cur)
            form.addRow(f"Taste {i + 1}:", cb)
            self._cb_btn.append(cb)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def apply(self):
        ex = self._ex
        ex.label = self._ed_label.text().strip() or f"Exec {ex.slot}"
        ex.fader_function = self._cb_fader.currentData() or "volume"
        ex.btn1 = self._cb_btn[0].currentData() or "go"
        ex.btn2 = self._cb_btn[1].currentData() or "back"
        ex.btn3 = self._cb_btn[2].currentData() or "flash"


def _select_by_data(combo: QComboBox, data):
    for i in range(combo.count()):
        if combo.itemData(i) == data:
            combo.setCurrentIndex(i)
            return
