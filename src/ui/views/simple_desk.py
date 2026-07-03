"""Simple Desk — 512 direct DMX faders per universe + Geräte-/Kanalübersicht."""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
                                QLabel, QSpinBox, QComboBox, QPushButton,
                                QSizePolicy, QGridLayout, QSlider,
                                QTreeWidget, QTreeWidgetItem, QSplitter,
                                QFrame, QCheckBox)
from PySide6.QtCore import Qt, QTimer, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QFont, QBrush, QPen, QFontMetrics
from src.ui.weak_slots import weak_slot

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


# ── SD-01/SD-02: Kanal-Funktion (Kürzel + Farbe) ─────────────────────────────
# Attribut-Strings stammen aus dem Engine-/Fixture-Vokabular
# (app_state._DIM_INTENSITY_ATTRS/_DIM_COLOR_ATTRS, qxf_import, fixture_db).
# Farben angelehnt an AttributeSlider.ATTR_COLORS (programmer_view), erweitert
# um Shutter/Strobe/Gobo/Zoom/Focus/Dimmer.
CHANNEL_FUNCTION_COLORS: dict[str, str] = {
    # Intensität / Dimmer
    "intensity": "#ffcc00", "dimmer": "#ffcc00", "master": "#ffcc00",
    # Farbe (RGBW + A/UV)
    "color_r": "#ff4444", "red": "#ff4444",
    "color_g": "#44ff44", "green": "#44ff44",
    "color_b": "#4488ff", "blue": "#4488ff",
    "color_w": "#ffffff", "white": "#ffffff",
    "color_a": "#ffaa00", "amber": "#ffaa00",
    "color_uv": "#aa44ff", "uv": "#aa44ff",
    # CMY / Farbrad
    "cyan": "#33dddd", "magenta": "#ff55cc", "yellow": "#ffee55",
    "color_wheel": "#ff66cc",
    # Position
    "pan": "#00ccff", "tilt": "#00ccff",
    "pan_fine": "#007799", "tilt_fine": "#007799",
    # Beam
    "shutter": "#ff8800", "strobe": "#ff8800",
    "zoom": "#66ddaa", "focus": "#66ddaa", "iris": "#9fe04f", "prism": "#9fe04f",
    # Gobo
    "gobo": "#cc66ff", "gobo_wheel": "#cc66ff", "gobo_fx": "#cc66ff",
    "gobo_rotation": "#b34dff", "gobo_rot": "#b34dff",
    # Sonstiges
    "frost": "#bcd0e6", "prism_rotation": "#9fe04f",
    "reset": "#8b949e", "speed": "#8b949e", "macro": "#8b949e",
}
_CHANNEL_FUNCTION_DEFAULT = "#6e7681"   # neutral-grau für unbekannte Attribute

CHANNEL_FUNCTION_ABBREV: dict[str, str] = {
    "intensity": "Dim", "dimmer": "Dim", "master": "GM",
    "color_r": "R", "red": "R",
    "color_g": "G", "green": "G",
    "color_b": "B", "blue": "B",
    "color_w": "W", "white": "W",
    "color_a": "A", "amber": "A",
    "color_uv": "UV", "uv": "UV",
    "cyan": "C", "magenta": "M", "yellow": "Y",
    "color_wheel": "CW",
    "pan": "Pan", "tilt": "Tlt",
    "pan_fine": "Pn-", "tilt_fine": "Tl-",
    "shutter": "Sh", "strobe": "Str",
    "zoom": "Zm", "focus": "Foc", "iris": "Iri", "prism": "Pri",
    "gobo": "Gob", "gobo_wheel": "Gob", "gobo_fx": "GbX",
    "gobo_rotation": "GbR", "gobo_rot": "GbR",
    "frost": "Frs", "prism_rotation": "PrR", "reset": "Rst",
    "speed": "Spd", "macro": "Mac",
}


def channel_function_color(attr: str) -> str:
    """SD-02: Farbe (Hex) für ein Kanal-Attribut; neutral-grau wenn unbekannt."""
    return CHANNEL_FUNCTION_COLORS.get((attr or "").strip().lower(),
                                       _CHANNEL_FUNCTION_DEFAULT)


def channel_function_abbrev(attr: str, name: str = "") -> str:
    """SD-01: kurzes Kürzel für einen Kanal (z. B. 'R', 'Dim').
    Bekanntes Attribut -> Map; sonst die ersten Zeichen des Kanalnamens."""
    a = (attr or "").strip().lower()
    if a in CHANNEL_FUNCTION_ABBREV:
        return CHANNEL_FUNCTION_ABBREV[a]
    n = (name or "").strip()
    return n[:3] if n else ""


class ChannelFader(QWidget):
    """Single vertical fader for one DMX channel."""
    def __init__(self, channel: int, parent=None):
        super().__init__(parent)
        self.channel = channel
        self._value = 0
        self._tint_color: QColor | None = None
        self._attr_text = ""
        self.setFixedSize(36, 124)
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

        # SD-01: kleines Funktions-Kürzel (z. B. 'R'/'Dim'); voller Name im Tooltip.
        self._attr_lbl = QLabel("")
        self._attr_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._attr_lbl.setStyleSheet("color:#adbac7; font-size:7px;")
        layout.addWidget(self._attr_lbl)

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

    def set_tint(self, color: QColor | None):
        """SDK-01: faerbt den Fader nach Fixture (visuelle Gruppierung). None = neutral.
        Scoped auf ChannelFader, damit Slider/Labels ihre eigenen Styles behalten."""
        self._tint_color = color
        if color is None:
            self.setStyleSheet("")
            self._ch_lbl.setStyleSheet("color:#484f58; font-size:7px;")
            return
        r, g, b = color.red(), color.green(), color.blue()
        self.setStyleSheet(
            f"ChannelFader {{ background: rgba({r},{g},{b},38); border-radius:4px; }}")
        self._ch_lbl.setStyleSheet(
            f"color:#fff; font-size:7px; background: rgba({r},{g},{b},190); border-radius:2px;")

    def flash(self):
        """Kurzes Aufblinken (Klick in Übersicht/Header-Band → Fader hervorheben)."""
        self.setStyleSheet(
            "ChannelFader { background:#ffd33d; border:2px solid #ffd33d; border-radius:4px; }")
        QTimer.singleShot(450, lambda: self.set_tint(self._tint_color))

    def set_function_label(self, text: str):
        """SD-01: setzt das Funktions-Kürzel unter dem Slider (leer = aus)."""
        self._attr_text = text or ""
        self._attr_lbl.setText(self._attr_text)


# ── Fixture-Header-Band (zeigt Zusammengehörigkeit über den Fadern) ───────────

# Geometrie MUSS exakt zur Fader-Reihe passen (ChannelFader 36px breit,
# QHBoxLayout-Spacing 2px, linker Rand 4px) — sonst sitzen die Balken schief.
_FADER_W       = 36
_FADER_SPACING = 2
_FADER_MARGIN  = 4
_FADER_STRIDE  = _FADER_W + _FADER_SPACING   # 38px pro Kanal-Spalte


class FixtureHeaderBand(QWidget):
    """Schmaler Balken über den Fadern: zeichnet pro Fixture einen farbigen
    Balken über GENAU seine Kanal-Spalten (= direkt sichtbare Zusammengehörigkeit).
    Liegt im selben Scroll-Inhalt wie die Fader und scrollt mit ihnen mit."""

    channel_clicked = Signal(int)   # Start-Kanal des angeklickten Fixtures

    def __init__(self, parent=None):
        super().__init__(parent)
        # (start, count, QColor, label)
        self._spans: list[tuple[int, int, QColor, str]] = []
        self.setFixedHeight(26)
        self._row_width = _FADER_MARGIN * 2 + 512 * _FADER_W + 511 * _FADER_SPACING
        self.setFixedWidth(self._row_width)
        self.setMouseTracking(True)

    def set_spans(self, spans):
        self._spans = list(spans)
        self.update()

    @staticmethod
    def _x_for(channel: int) -> int:
        """Linke Kante der Fader-Spalte für DMX-Kanal (1-basiert)."""
        return _FADER_MARGIN + (channel - 1) * _FADER_STRIDE

    def _fixture_at(self, x: int):
        for span in self._spans:
            start, count = span[0], span[1]
            x0 = self._x_for(start)
            x1 = self._x_for(start + count - 1) + _FADER_W
            if x0 <= x <= x1:
                return span
        return None

    def mousePressEvent(self, ev):
        hit = self._fixture_at(int(ev.position().x()))
        if hit:
            self.channel_clicked.emit(hit[0])
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        hit = self._fixture_at(int(ev.position().x()))
        if hit:
            start, count, _c, label = hit
            end = start + count - 1
            self.setToolTip(f"{label} · CH {start:03d}–{end:03d} ({count} Kanäle)")
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setToolTip("")
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(ev)

    def paintEvent(self, _ev):
        if not self._spans:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = QFont()
        font.setPointSizeF(8.0)
        font.setBold(True)
        p.setFont(font)
        fm = QFontMetrics(font)
        h = self.height()
        for start, count, color, label in self._spans:
            x0 = self._x_for(start)
            x1 = self._x_for(start + count - 1) + _FADER_W
            w = x1 - x0
            rect = QRectF(x0 + 0.5, 3.5, w - 1, h - 7)
            fill = QColor(color)
            fill.setAlpha(210)
            p.setBrush(QBrush(fill))
            p.setPen(QPen(QColor(color).darker(150), 1))
            p.drawRoundedRect(rect, 4, 4)
            # Label weiß, auf die Fixture-Breite gekürzt
            p.setPen(QPen(QColor("#ffffff")))
            txt = fm.elidedText(label, Qt.TextElideMode.ElideRight, int(max(0, w - 8)))
            p.drawText(rect.adjusted(4, 0, -2, 0),
                       int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), txt)
        p.end()


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

    # (universe, address, channel_count) eines angeklickten Geräts → die Haupt-
    # View springt zu seinen Fadern und lässt sie kurz aufblinken.
    fixture_activated = Signal(int, int, int)
    # Gewähltes Universe des Filters (0 = Alle) → Faderbereich kann mitziehen.
    universe_filter_changed = Signal(int)

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

        # ── Legende (nur sichtbar, wenn es Probleme gibt) + Status ──
        self._legend = QLabel("⬤ Konflikt / ungültige Adresse")
        self._legend.setStyleSheet(f"color:{_C_RED}; font-size:10px;")
        self._legend.setVisible(False)
        toolbar.addWidget(self._legend)
        toolbar.addSpacing(12)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color:{_C_TEXT_DIM}; font-size:10px;")
        toolbar.addWidget(self._status_lbl)

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

        self._tree.itemClicked.connect(self._on_item_clicked)

        layout.addWidget(self._tree)

    # ── Filter ────────────────────────────────────────────────────────────────

    def _on_filter_changed(self, idx: int):
        data = self._uni_filter.currentData()
        self._filter_universe = data if data is not None else 0
        self.rebuild()
        self.universe_filter_changed.emit(self._filter_universe)

    def set_universe_filter(self, universe: int):
        """Filter von außen (Fader-Universe) setzen — ohne universe_filter_changed
        erneut auszulösen (verhindert Signal-Pingpong)."""
        for i in range(self._uni_filter.count()):
            if self._uni_filter.itemData(i) == universe:
                self._uni_filter.blockSignals(True)
                self._uni_filter.setCurrentIndex(i)
                self._uni_filter.blockSignals(False)
                self._filter_universe = universe
                self.rebuild()
                return

    def follow_universe(self, universe: int):
        """Beim Universe-Wechsel im Faderbereich nachziehen — aber eine bewusste
        'Alle'-Auswahl respektieren."""
        cur = self._uni_filter.currentData() or 0
        if cur == 0:
            return
        self.set_universe_filter(universe)

    def _on_item_clicked(self, item: QTreeWidgetItem, _col: int):
        """Klick auf ein Gerät (oder seine Kanalzeile) → Haupt-View springt zu
        dessen Fadern."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None and item.parent() is not None:
            data = item.parent().data(0, Qt.ItemDataRole.UserRole)
        if data:
            universe, address, count = data
            self.fixture_activated.emit(int(universe), int(address), int(count))

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

        shown = 0
        problems = 0
        for fx in fixtures_sorted:
            # Universe-Filter anwenden
            if self._filter_universe != 0 and fx.universe != self._filter_universe:
                continue
            ok, has_problem = self._add_fixture_item(fx, state)
            if ok:
                shown += 1
                if has_problem:
                    problems += 1
        self._update_status(shown, problems)

    def _update_status(self, shown: int, problems: int):
        """Status-Zeile (Geräteanzahl + Probleme) + Legende ein/aus."""
        if not hasattr(self, "_status_lbl"):
            return
        txt = f"{shown} Gerät" + ("" if shown == 1 else "e")
        if problems:
            txt += f"  ·  {problems} Problem" + ("" if problems == 1 else "e")
        self._status_lbl.setText(txt)
        self._legend.setVisible(problems > 0)

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
            # Daten für Klick→Fader-Sprung (Universe, Startadresse, Kanalanzahl)
            top.setData(0, Qt.ItemDataRole.UserRole,
                        (int(fx.universe), int(fx.address), int(fx.channel_count)))

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

            return True, (has_error or has_conflict)

        except Exception as e:
            print(f"[simple_desk] Fixture-Item Fehler (FID {getattr(fx, 'fid', '?')}): {e}")
            return False, False

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
        self._color_by_function = False   # SD-02: False=nach Fixture, True=nach Funktion
        self._faders: list[ChannelFader] = []
        self._user_active_until: dict[int, float] = {}  # {channel: timestamp}
        self._setup_ui()

        # Override-Zustand initialisieren (Default: Anzeige -> Fader/Buttons gesperrt).
        try:
            from src.core.app_state import get_state
            _initial_override = bool(getattr(get_state(), "simple_desk_override", False))
        except Exception:
            _initial_override = False
        self._override_cb.setChecked(_initial_override)
        self._apply_override_ui(_initial_override)

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

        # Manueller Override (ISO-03): Default AUS = Simple Desk ist reine Anzeige
        # (Fader spiegeln die Live-Ausgabe). AN = die Fader uebernehmen mit
        # absoluter Oberhand (oberste Render-Schicht).
        self._override_cb = QCheckBox("Manueller Override")
        self._override_cb.setToolTip(
            "Aus: Simple Desk zeigt nur die Ausgabe an (Monitor).\n"
            "An: die Fader steuern direkt mit absoluter Priorität (über Effekte/Programmer).")
        self._override_cb.setStyleSheet(
            f"QCheckBox {{ color:{_C_TEXT_DIM}; font-size:11px; }}"
            f"QCheckBox:checked {{ color:{_C_RED}; font-weight:bold; }}")
        self._override_cb.toggled.connect(self._on_override_toggled)
        header.addWidget(self._override_cb)
        header.addSpacing(12)

        # SD-02: Fader nach Kanal-Funktion (R/G/B/W/Dimmer/…) statt nach Fixture faerben.
        self._func_color_cb = QCheckBox("Farbe nach Funktion")
        self._func_color_cb.setToolTip(
            "Aus: Fader nach Gerät gruppiert (Fixture-Farbe).\n"
            "An: jeder Fader bekommt die Farbe seiner Funktion (R/G/B/W/Dimmer/Pan…).")
        self._func_color_cb.setStyleSheet(
            f"QCheckBox {{ color:{_C_TEXT_DIM}; font-size:11px; }}"
            f"QCheckBox:checked {{ color:{_C_ACCENT}; font-weight:bold; }}")
        self._func_color_cb.toggled.connect(self._on_func_color_toggled)
        header.addWidget(self._func_color_cb)
        header.addSpacing(12)

        self._btn_all_zero = QPushButton("Alles auf 0")
        self._btn_all_zero.setFixedHeight(24)
        self._btn_all_zero.clicked.connect(self._zero_all)
        self._btn_all_zero.setStyleSheet("""
            QPushButton { background:#21262d; color:#f85149; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:hover { background:#30363d; }
            QPushButton:disabled { color:#5a5a5a; border-color:#21262d; }
        """)
        header.addWidget(self._btn_all_zero)

        self._btn_full = QPushButton("Alles auf 255")
        self._btn_full.setFixedHeight(24)
        self._btn_full.clicked.connect(weak_slot(self._set_all, 255))
        self._btn_full.setStyleSheet(self._btn_all_zero.styleSheet().replace("#f85149", "#3fb950"))
        header.addWidget(self._btn_full)

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
        self._overview.fixture_activated.connect(self._on_overview_fixture)
        self._overview.universe_filter_changed.connect(self._on_overview_universe)
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
        self._scroll = scroll

        fader_widget = QWidget()
        fader_widget.setStyleSheet(f"background:{_C_BG};")
        outer = QVBoxLayout(fader_widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Fixture-Header-Band (scrollt mit den Fadern, zeigt Zusammengehörigkeit)
        self._header_band = FixtureHeaderBand()
        self._header_band.channel_clicked.connect(self._on_band_clicked)
        outer.addWidget(self._header_band, 0, Qt.AlignmentFlag.AlignLeft)

        fader_row = QWidget()
        grid = QHBoxLayout(fader_row)
        grid.setContentsMargins(_FADER_MARGIN, 4, _FADER_MARGIN, 4)
        grid.setSpacing(_FADER_SPACING)
        grid.setAlignment(Qt.AlignmentFlag.AlignLeft)
        for ch in range(1, 513):
            f = ChannelFader(ch)
            f.value_changed = lambda val, c=ch: self._on_fader_change(c, val)
            grid.addWidget(f)
            self._faders.append(f)
        outer.addWidget(fader_row, 0, Qt.AlignmentFlag.AlignLeft)
        outer.addStretch(1)

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
        self._apply_fixture_tints()

    # SDK-01: Fader nach Fixture einfaerben (visuelle Gruppierung im aktuellen Universe)
    _TINTS = ["#1f6feb", "#3fb950", "#d29922", "#a371f7", "#f85149", "#39c5cf",
              "#db61a2", "#bc8cff"]

    def _apply_fixture_tints(self):
        for f in self._faders:
            f.set_tint(None)
            f.set_function_label("")
            f.setToolTip(f"CH {f.channel}")
        spans: list[tuple[int, int, QColor, str]] = []
        try:
            from src.core.app_state import get_state, get_channels_for_patched
            state = get_state()
            fixtures = [fx for fx in state.get_patched_fixtures()
                        if fx.universe == self._universe]
            fixtures.sort(key=lambda fx: fx.address)
            by_function = getattr(self, "_color_by_function", False)
            for idx, fx in enumerate(fixtures):
                color = QColor(self._TINTS[idx % len(self._TINTS)])
                try:
                    chans = get_channels_for_patched(fx)
                    cmap = {c.channel_number:
                            (c.name if (c.name and c.name.strip()) else c.attribute)
                            for c in chans}
                    amap = {c.channel_number: (getattr(c, "attribute", "") or "")
                            for c in chans}
                except Exception:
                    cmap = {}
                    amap = {}
                count = int(getattr(fx, "channel_count", 1) or 1)
                label = getattr(fx, "label", "") or f"FID {getattr(fx, 'fid', '?')}"
                for off in range(count):
                    ch = fx.address + off
                    if 1 <= ch <= 512:
                        fader = self._faders[ch - 1]
                        attr = amap.get(off + 1, "")
                        cname = cmap.get(off + 1, "")
                        # SD-02: nach Funktion einfaerben, sonst nach Fixture gruppieren.
                        fader.set_tint(QColor(channel_function_color(attr))
                                       if by_function else color)
                        # SD-01: pro-Kanal-Kürzel (voller Name bleibt im Tooltip).
                        fader.set_function_label(channel_function_abbrev(attr, cname))
                        fader.setToolTip(
                            f"CH {ch} · {label}" + (f" · {cname}" if cname else ""))
                # Header-Band-Eintrag (sichtbaren Bereich auf 1..512 begrenzen)
                if 1 <= fx.address <= 512:
                    vis = min(count, 512 - fx.address + 1)
                    spans.append((fx.address, vis, color, label))
        except Exception as e:
            print(f"[simple_desk] tint error: {e}")
        self._band_spans = spans
        if hasattr(self, "_header_band"):
            self._header_band.set_spans(spans)

    def _reveal_fixture(self, address: int, count: int):
        """Fader eines Fixtures sichtbar scrollen und kurz aufblinken lassen."""
        if not (1 <= address <= 512):
            return
        try:
            self._scroll.ensureWidgetVisible(self._faders[address - 1], 100, 0)
        except Exception as e:
            print(f"[simple_desk] reveal scroll error: {e}")
        for off in range(max(1, count)):
            ch = address + off
            if 1 <= ch <= 512:
                self._faders[ch - 1].flash()

    def _on_overview_fixture(self, universe: int, address: int, count: int):
        """Klick in der Geräteübersicht → ggf. Universe wechseln, dann Fader zeigen."""
        if 1 <= universe <= 4 and universe != self._universe:
            self._uni_combo.setCurrentIndex(universe - 1)  # löst _universe_changed aus
            QTimer.singleShot(60, lambda a=address, c=count: self._reveal_fixture(a, c))
        else:
            self._reveal_fixture(address, count)

    def _on_overview_universe(self, universe: int):
        """Overview-Filter auf ein konkretes Universe gestellt → Fader ziehen mit."""
        if universe and 1 <= universe <= 4 and universe != self._universe:
            self._uni_combo.setCurrentIndex(universe - 1)

    def _on_band_clicked(self, start_channel: int):
        """Klick auf das Header-Band → Fader des Fixtures hervorheben."""
        for s, c, _color, _label in getattr(self, "_band_spans", []):
            if s == start_channel:
                self._reveal_fixture(s, c)
                return

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

    def _on_override_toggled(self, checked: bool):
        """Manueller Override an/aus. Aus = reine Anzeige (Fader gesperrt, Werte
        verworfen); An = Fader steuern mit absoluter Prioritaet."""
        try:
            from src.core.app_state import get_state
            get_state().set_simple_desk_override(bool(checked))
        except Exception as e:
            print(f"[SimpleDesk] override toggle error: {e}")
        self._apply_override_ui(bool(checked))
        if not checked:
            # Zurueck zur Anzeige: Fader sofort auf die Live-Ausgabe syncen.
            self._sync_from_output()

    def _on_func_color_toggled(self, checked: bool):
        """SD-02: zwischen Fixture-Gruppierung und Funktions-Farbe umschalten."""
        self._color_by_function = bool(checked)
        self._apply_fixture_tints()

    def _apply_override_ui(self, enabled: bool):
        """Sperrt/entsperrt die Fader und die 'Alles auf …'-Buttons je nach
        Override-Zustand (im Anzeige-Modus sind sie nur Monitor)."""
        for f in self._faders:
            f.setEnabled(enabled)
        if hasattr(self, "_btn_all_zero"):
            self._btn_all_zero.setEnabled(enabled)
        if hasattr(self, "_btn_full"):
            self._btn_full.setEnabled(enabled)

    def _on_fader_change(self, channel: int, value: int):
        import time
        # Nur wirksam im manuellen Override-Modus (sonst reine Anzeige).
        if not self._override_cb.isChecked():
            return
        # User aktiv -> 800ms lang nicht vom Sync ueberschreiben
        self._user_active_until[channel] = time.monotonic() + 0.8
        try:
            from src.core.app_state import get_state
            state = get_state()
            # Sicherstellen dass das Universe existiert (Renderer baut Scratch nur
            # aus state.universes; sonst wuerde der Override nicht gerendert).
            if self._universe not in state.universes:
                state.universes[self._universe] = state.output_manager.add_universe(self._universe)
            # ISO-03: in die Simple-Desk-Override-Ebene schreiben statt roh ins
            # Live-Universe — der zentrale Renderer wendet sie deterministisch an.
            state.set_simple_desk_channel(self._universe, channel, value)
        except Exception as e:
            print(f"[SimpleDesk] fader change error: {e}")

    def _universe_changed(self, idx: int):
        # Combobox-Index (0-based) -> Universe-Nummer (1-based)
        self._universe = idx + 1
        self._user_active_until.clear()
        self._sync_from_output()
        self._apply_fixture_tints()      # SDK-01: Faerbung fuers neue Universe
        # Übersicht kohärent nachziehen (außer der Nutzer hat bewusst "Alle" gewählt)
        try:
            self._overview.follow_universe(self._universe)
        except Exception as e:
            print(f"[simple_desk] follow_universe error: {e}")

    def _zero_all(self):
        self._set_all(0)

    def _set_all(self, val: int):
        import time
        if not self._override_cb.isChecked():
            return  # nur im manuellen Override-Modus wirksam
        try:
            from src.core.app_state import get_state
            state = get_state()
            if self._universe not in state.universes:
                state.universes[self._universe] = state.output_manager.add_universe(self._universe)
            # ISO-03: alle 512 Kanaele als Simple-Desk-Override setzen (statt roh).
            state.set_simple_desk_all(self._universe, val)
            now = time.monotonic() + 0.8
            for ch in range(1, 513):
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

    # ── Sichtbarkeit: Sync-Timer nur laufen lassen, wenn der Tab sichtbar ist ──
    # (512 Fader 5×/s zu aktualisieren ist sinnlos, wenn niemand hinsieht.)

    def showEvent(self, ev):
        super().showEvent(ev)
        if hasattr(self, "_sync_timer") and not self._sync_timer.isActive():
            self._sync_timer.start(200)
        # Beim Zurückkehren auf den Tab: frischer Stand.
        self._sync_from_output()
        self._rebuild_overview()

    def hideEvent(self, ev):
        super().hideEvent(ev)
        if hasattr(self, "_sync_timer"):
            self._sync_timer.stop()
