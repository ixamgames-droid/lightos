"""Simple Desk — 512 direct DMX faders per universe + Geräte-/Kanalübersicht."""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
                                QLabel, QSpinBox, QComboBox, QPushButton,
                                QSizePolicy, QGridLayout, QSlider,
                                QTreeWidget, QTreeWidgetItem, QSplitter,
                                QFrame)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QFont, QBrush

# ── Farb-Konstanten (Dark-Theme) ──────────────────────────────────────────────
_C_BG        = "#0d1117"
_C_BG2       = "#161b22"
_C_TEXT      = "#e6edf3"
_C_TEXT_DIM  = "#8b949e"
_C_BORDER    = "#30363d"
_C_ACCENT    = "#58a6ff"
_C_ACCENT2   = "#1f6feb"
_C_RED       = "#f85149"
_C_GREEN     = "#3fb950"
_C_WARN_BG   = "#2d1117"   # Roter Hintergrund (dezent)
_C_WARN2_BG  = "#1d2217"   # Oranger Hintergrund für fehlerhafte Adresse


class ChannelFader(QWidget):
    """Single vertical fader for one DMX channel."""
    def __init__(self, channel: int, parent=None):
        super().__init__(parent)
        self.channel = channel
        self._value = 0
        self.setFixedSize(36, 110)
        self.setToolTip(f"CH {channel}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(1)

        self._val_lbl = QLabel("0")
        self._val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._val_lbl.setStyleSheet("color:#8b949e; font-size:8px;")
        layout.addWidget(self._val_lbl)

        self._slider = QSlider(Qt.Orientation.Vertical)
        self._slider.setRange(0, 255)
        self._slider.setValue(0)
        self._slider.setStyleSheet("""
            QSlider::groove:vertical { background:#21262d; width:8px; border-radius:4px; }
            QSlider::handle:vertical { background:#58a6ff; height:12px; width:12px;
                                       margin:-2px -2px; border-radius:6px; }
            QSlider::sub-page:vertical { background:#1f6feb; border-radius:4px; }
        """)
        self._slider.valueChanged.connect(self._on_change)
        layout.addWidget(self._slider)

        self._ch_lbl = QLabel(str(channel))
        self._ch_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ch_lbl.setStyleSheet("color:#484f58; font-size:7px;")
        layout.addWidget(self._ch_lbl)

    def _on_change(self, val: int):
        self._value = val
        self._val_lbl.setText(str(val))
        self.value_changed(val)

    def value_changed(self, val: int):
        pass  # to be monkey-patched by parent

    def set_value_silent(self, val: int):
        self._slider.blockSignals(True)
        self._slider.setValue(val)
        self._value = val
        self._val_lbl.setText(str(val))
        self._slider.blockSignals(False)


# ── Geräteübersicht ───────────────────────────────────────────────────────────

_OVERVIEW_COLUMNS = ["Gerät", "FID", "Universe", "Start", "Kanäle", "Anz.", "Modus", "Typ"]

_OVERVIEW_STYLE = f"""
QTreeWidget {{
    background: {_C_BG2};
    color: {_C_TEXT};
    border: 1px solid {_C_BORDER};
    border-radius: 4px;
    font-size: 11px;
    outline: none;
}}
QTreeWidget::item {{
    padding: 2px 4px;
    border: none;
}}
QTreeWidget::item:selected {{
    background: {_C_ACCENT2};
    color: {_C_TEXT};
}}
QTreeWidget::item:hover {{
    background: #21262d;
}}
QHeaderView::section {{
    background: #21262d;
    color: {_C_TEXT_DIM};
    border: none;
    border-bottom: 1px solid {_C_BORDER};
    padding: 3px 6px;
    font-size: 10px;
}}
QTreeWidget::branch:has-children:!has-siblings:closed,
QTreeWidget::branch:closed:has-children:has-siblings {{
    border-image: none; image: none;
}}
QTreeWidget::branch:open:has-children:!has-siblings,
QTreeWidget::branch:open:has-children:has-siblings {{
    border-image: none; image: none;
}}
"""


class FixtureOverviewPanel(QWidget):
    """Einklappbares Panel mit QTreeWidget-Geräteübersicht."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter_universe: int = 0   # 0 = alle
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ── Toolbar ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        lbl = QLabel("Geräteübersicht")
        lbl.setStyleSheet(f"color:{_C_TEXT}; font-size:11px; font-weight:600;")
        toolbar.addWidget(lbl)

        toolbar.addSpacing(12)
        toolbar.addWidget(QLabel("Universe:"))

        self._uni_filter = QComboBox()
        self._uni_filter.setFixedWidth(110)
        self._uni_filter.setStyleSheet(f"""
            QComboBox {{
                background: #21262d; color: {_C_TEXT}; border: 1px solid {_C_BORDER};
                border-radius: 3px; padding: 1px 6px; font-size: 10px;
            }}
            QComboBox QAbstractItemView {{
                background: #21262d; color: {_C_TEXT}; selection-background-color: {_C_ACCENT2};
            }}
        """)
        self._uni_filter.currentIndexChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self._uni_filter)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # ── Trennlinie ──
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {_C_BORDER};")
        layout.addWidget(line)

        # ── Tree ──
        self._tree = QTreeWidget()
        self._tree.setColumnCount(len(_OVERVIEW_COLUMNS))
        self._tree.setHeaderLabels(_OVERVIEW_COLUMNS)
        self._tree.setStyleSheet(_OVERVIEW_STYLE)
        self._tree.setAlternatingRowColors(False)
        self._tree.setRootIsDecorated(True)
        self._tree.setSortingEnabled(False)
        self._tree.setUniformRowHeights(False)
        self._tree.setAnimated(True)

        # Spaltenbreiten
        header = self._tree.header()
        header.setDefaultSectionSize(80)
        col_widths = [140, 42, 72, 60, 90, 40, 90, 130]
        for i, w in enumerate(col_widths):
            self._tree.setColumnWidth(i, w)

        layout.addWidget(self._tree)

    # ── Filter ────────────────────────────────────────────────────────────────

    def _on_filter_changed(self, idx: int):
        data = self._uni_filter.currentData()
        self._filter_universe = data if data is not None else 0
        self.rebuild()

    def _update_uni_filter_items(self, universes: list[int]):
        """Universe-Filter-ComboBox mit vorhandenen Universen befüllen."""
        prev = self._uni_filter.currentData()
        self._uni_filter.blockSignals(True)
        self._uni_filter.clear()
        self._uni_filter.addItem("Alle", 0)
        for u in sorted(universes):
            self._uni_filter.addItem(f"Universe {u}", u)
        # Selektion wiederherstellen
        for i in range(self._uni_filter.count()):
            if self._uni_filter.itemData(i) == prev:
                self._uni_filter.setCurrentIndex(i)
                break
        self._uni_filter.blockSignals(False)
        self._filter_universe = self._uni_filter.currentData() or 0

    # ── Rebuild ───────────────────────────────────────────────────────────────

    def rebuild(self):
        """Übersicht komplett neu aufbauen aus zentralem State."""
        self._tree.clear()
        try:
            from src.core.app_state import get_state, get_channels_for_patched
            state = get_state()
            fixtures = state.get_patched_fixtures()
        except Exception as e:
            print(f"[simple_desk] Übersicht laden fehlgeschlagen: {e}")
            return

        # Universe-Filter aktualisieren
        universes = list({fx.universe for fx in fixtures})
        self._update_uni_filter_items(universes)

        # Sortieren: (universe, address)
        try:
            fixtures_sorted = sorted(fixtures, key=lambda fx: (fx.universe, fx.address))
        except Exception as e:
            print(f"[simple_desk] Sortierung fehlgeschlagen: {e}")
            fixtures_sorted = list(fixtures)

        for fx in fixtures_sorted:
            # Universe-Filter anwenden
            if self._filter_universe != 0 and fx.universe != self._filter_universe:
                continue
            self._add_fixture_item(fx, state)

    def _add_fixture_item(self, fx, state):
        """Fixture-Zeile + Kanal-Detailzeilen zum Tree hinzufügen."""
        try:
            # ── Validierung ──
            addr_ok = (1 <= fx.address <= 512 and
                       1 <= fx.address + fx.channel_count - 1 <= 512 and
                       fx.universe >= 1)
            end_addr = fx.address + fx.channel_count - 1

            # Konflikt-Prüfung
            try:
                conflicts = state.check_address_conflict(
                    fx.universe, fx.address, fx.channel_count, exclude_fid=fx.fid
                )
            except Exception as ce:
                print(f"[simple_desk] Konfliktprüfung FID {fx.fid}: {ce}")
                conflicts = []

            has_conflict = len(conflicts) > 0
            has_error = not addr_ok

            # ── Typ-Bezeichnung ──
            typ = ""
            try:
                if fx.manufacturer_name and fx.fixture_name:
                    typ = f"{fx.manufacturer_name} {fx.fixture_name}"
                elif fx.fixture_type:
                    typ = fx.fixture_type
                else:
                    typ = fx.fixture_type or ""
            except Exception:
                typ = getattr(fx, "fixture_type", "") or ""

            # ── Top-Level-Item ──
            channel_range = f"CH {fx.address:03d}–{end_addr:03d}"
            top = QTreeWidgetItem([
                fx.label or f"Fixture {fx.fid}",
                str(fx.fid),
                str(fx.universe),
                f"{fx.address:03d}",
                channel_range,
                str(fx.channel_count),
                fx.mode_name or "–",
                typ,
            ])

            # ── Farb-Markierung ──
            if has_error:
                self._color_item(top, _C_RED, _C_WARN_BG)
                tooltip = "Ungültige Adresse: "
                if fx.universe < 1:
                    tooltip += f"Universe {fx.universe} < 1. "
                if fx.address < 1:
                    tooltip += f"Startadresse {fx.address} < 1. "
                if fx.address + fx.channel_count - 1 > 512:
                    tooltip += f"Endadresse {end_addr} > 512. "
                top.setToolTip(0, tooltip.strip())
            elif has_conflict:
                self._color_item(top, _C_RED, _C_WARN_BG)
                top.setToolTip(0, f"Kanal-Konflikt mit FID(s): {conflicts}")
            else:
                # Normales Fixture
                for col in range(len(_OVERVIEW_COLUMNS)):
                    top.setForeground(col, QBrush(QColor(_C_TEXT)))

            self._tree.addTopLevelItem(top)

            # ── Kanal-Detailzeilen ──
            try:
                from src.core.app_state import get_channels_for_patched
                channels = get_channels_for_patched(fx)
                for ch in channels:
                    abs_addr = fx.address + ch.channel_number - 1
                    ch_label = ch.name if (ch.name and ch.name.strip()) else ch.attribute
                    child = QTreeWidgetItem([
                        f"  CH {abs_addr:03d}: {ch_label}",
                        "", "", "", "", "", "", "",
                    ])
                    child.setForeground(0, QBrush(QColor(_C_TEXT_DIM)))
                    if has_error or has_conflict:
                        child.setForeground(0, QBrush(QColor(_C_RED).lighter(130)))
                    top.addChild(child)
            except Exception as ch_e:
                print(f"[simple_desk] Kanäle FID {fx.fid}: {ch_e}")

        except Exception as e:
            print(f"[simple_desk] Fixture-Item Fehler (FID {getattr(fx, 'fid', '?')}): {e}")

    @staticmethod
    def _color_item(item: QTreeWidgetItem, fg: str, bg: str):
        """Alle Spalten eines Items einfärben."""
        fg_brush = QBrush(QColor(fg))
        bg_brush = QBrush(QColor(bg))
        for col in range(len(_OVERVIEW_COLUMNS)):
            item.setForeground(col, fg_brush)
            item.setBackground(col, bg_brush)


# ── Haupt-View ────────────────────────────────────────────────────────────────

class SimpleDeskView(QWidget):
    """Direct 1:1 DMX channel faders (512 per universe) + Geräteübersicht."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._universe = 1   # 1-based DMX universe number
        self._faders: list[ChannelFader] = []
        self._user_active_until: dict[int, float] = {}  # {channel: timestamp}
        self._setup_ui()

        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self._sync_from_output)
        self._sync_timer.start(200)

        # Zentraler StateSync
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe(SyncEvent.REFRESH_ALL, lambda *_: self._on_refresh_all())
            sync.subscribe(SyncEvent.PATCH_CHANGED, lambda *_: self._on_patch_changed())
            sync.subscribe(SyncEvent.DMX_CHANGED, lambda *_: self._sync_from_output())
        except Exception as e:
            print(f"[simple_desk] sync subscribe error: {e}")

        # Initiale Übersicht aufbauen (verzögert, damit State bereit ist)
        QTimer.singleShot(100, self._rebuild_overview)

    # ── UI-Aufbau ─────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(4)

        # ── Header (Universe-Auswahl + Buttons + Toggle) ──
        header = QHBoxLayout()

        header.addWidget(QLabel("Universe:"))
        self._uni_combo = QComboBox()
        self._uni_combo.addItems(["Universe 1", "Universe 2", "Universe 3", "Universe 4"])
        self._uni_combo.currentIndexChanged.connect(self._universe_changed)
        self._uni_combo.setFixedWidth(120)
        header.addWidget(self._uni_combo)
        header.addSpacing(20)

        btn_all_zero = QPushButton("Alles auf 0")
        btn_all_zero.setFixedHeight(24)
        btn_all_zero.clicked.connect(self._zero_all)
        btn_all_zero.setStyleSheet("""
            QPushButton { background:#21262d; color:#f85149; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:hover { background:#30363d; }
        """)
        header.addWidget(btn_all_zero)

        btn_full = QPushButton("Alles auf 255")
        btn_full.setFixedHeight(24)
        btn_full.clicked.connect(lambda: self._set_all(255))
        btn_full.setStyleSheet(btn_all_zero.styleSheet().replace("#f85149", "#3fb950"))
        header.addWidget(btn_full)

        header.addStretch()

        # Toggle-Button für Übersicht
        self._toggle_btn = QPushButton("▼ Geräteübersicht")
        self._toggle_btn.setFixedHeight(24)
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setChecked(True)
        self._toggle_btn.clicked.connect(self._toggle_overview)
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: #21262d; color: {_C_ACCENT};
                border: 1px solid {_C_BORDER}; border-radius: 3px;
                font-size: 10px; padding: 0 10px;
            }}
            QPushButton:hover {{ background: #30363d; }}
            QPushButton:checked {{ background: {_C_ACCENT2}; color: {_C_TEXT}; }}
        """)
        header.addWidget(self._toggle_btn)

        root_layout.addLayout(header)

        # ── Splitter: Übersicht (oben) + Fader-Bereich (unten) ──
        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.setHandleWidth(5)
        self._splitter.setStyleSheet(f"""
            QSplitter::handle {{ background: {_C_BORDER}; }}
            QSplitter::handle:hover {{ background: {_C_ACCENT2}; }}
        """)

        # Geräteübersicht-Panel
        self._overview = FixtureOverviewPanel()
        self._overview.setMinimumHeight(60)
        self._splitter.addWidget(self._overview)

        # Fader-Bereich
        fader_container = QWidget()
        fader_container.setStyleSheet(f"background:{_C_BG};")
        fader_v = QVBoxLayout(fader_container)
        fader_v.setContentsMargins(0, 0, 0, 0)
        fader_v.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border:none; background:{_C_BG}; }}")

        fader_widget = QWidget()
        fader_widget.setStyleSheet(f"background:{_C_BG};")
        grid = QHBoxLayout(fader_widget)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setSpacing(2)
        grid.setAlignment(Qt.AlignmentFlag.AlignLeft)

        for ch in range(1, 513):
            f = ChannelFader(ch)
            f.value_changed = lambda val, c=ch: self._on_fader_change(c, val)
            grid.addWidget(f)
            self._faders.append(f)

        scroll.setWidget(fader_widget)
        fader_v.addWidget(scroll)
        self._splitter.addWidget(fader_container)

        # Anfangs-Größenverhältnis: ~35% Übersicht / ~65% Fader
        self._splitter.setSizes([200, 370])

        root_layout.addWidget(self._splitter)

    # ── Toggle Übersicht ──────────────────────────────────────────────────────

    def _toggle_overview(self, checked: bool):
        """Übersichts-Panel ein-/ausklappen."""
        self._overview.setVisible(checked)
        if checked:
            self._toggle_btn.setText("▼ Geräteübersicht")
            sizes = self._splitter.sizes()
            total = sum(sizes)
            self._splitter.setSizes([max(150, total // 3), total - max(150, total // 3)])
        else:
            self._toggle_btn.setText("▶ Geräteübersicht")
            sizes = self._splitter.sizes()
            total = sum(sizes)
            self._splitter.setSizes([0, total])

    # ── Übersicht neu aufbauen ────────────────────────────────────────────────

    def _rebuild_overview(self):
        """Geräteübersicht komplett neu aufbauen (bei PATCH_CHANGED / REFRESH_ALL)."""
        try:
            self._overview.rebuild()
        except Exception as e:
            print(f"[simple_desk] _rebuild_overview Fehler: {e}")

    # ── Sync-Callbacks ────────────────────────────────────────────────────────

    def _on_patch_changed(self):
        """PATCH_CHANGED: Fader-Sync + Übersicht neu aufbauen."""
        self._sync_from_output()
        self._rebuild_overview()

    def _on_refresh_all(self):
        """REFRESH_ALL: Fader-Sync + Übersicht neu aufbauen."""
        self._sync_from_output()
        self._rebuild_overview()

    # ── Fader-Logik (unverändert) ─────────────────────────────────────────────

    def _on_fader_change(self, channel: int, value: int):
        import time
        # User aktiv -> 800ms lang nicht vom Sync ueberschreiben
        self._user_active_until[channel] = time.monotonic() + 0.8
        try:
            from src.core.app_state import get_state
            state = get_state()
            # Sicherstellen dass das Universe existiert
            if self._universe not in state.universes:
                state.universes[self._universe] = state.output_manager.add_universe(self._universe)
            state.universes[self._universe].set_channel(channel, value)
        except Exception as e:
            print(f"[SimpleDesk] fader change error: {e}")

    def _universe_changed(self, idx: int):
        # Combobox-Index (0-based) -> Universe-Nummer (1-based)
        self._universe = idx + 1
        self._user_active_until.clear()
        self._sync_from_output()

    def _zero_all(self):
        self._set_all(0)

    def _set_all(self, val: int):
        import time
        try:
            from src.core.app_state import get_state
            state = get_state()
            if self._universe not in state.universes:
                state.universes[self._universe] = state.output_manager.add_universe(self._universe)
            u = state.universes[self._universe]
            now = time.monotonic() + 0.8
            for ch in range(1, 513):
                u.set_channel(ch, val)
                self._user_active_until[ch] = now
        except Exception as e:
            print(f"[SimpleDesk] set_all error: {e}")
        for f in self._faders:
            f.set_value_silent(val)

    def _sync_from_output(self):
        import time
        try:
            from src.core.app_state import get_state
            state = get_state()
            u = state.universes.get(self._universe)
            if u is None:
                return
            data = u.get_all()
            now = time.monotonic()
            for i, f in enumerate(self._faders):
                if i >= len(data):
                    continue
                ch = i + 1
                # User-Bewegung kuerzlich -> nicht ueberschreiben
                if self._user_active_until.get(ch, 0) > now:
                    continue
                f.set_value_silent(data[i])
        except Exception as e:
            print(f"[SimpleDesk] sync error: {e}")
