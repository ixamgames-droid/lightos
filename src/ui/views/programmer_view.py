"""Programmer-Ansicht - Live-Bearbeitung von Fixture-Attributen.

Layout:
  - Links:    Fixture-Liste + Quick-Buttons
  - Mitte:    Attribut-Gruppen-Tabs (Intensity / Color / Position / Beam / Gobo / Effect)
  - Toolbar:  Highlight, Lowlight, Clear, Copy, Paste, Undo, Redo + Fan / Color / Position
"""
from __future__ import annotations
import copy
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSlider, QPushButton,
    QListWidget, QListWidgetItem, QGroupBox, QScrollArea, QFrame,
    QTabWidget, QToolButton, QSizePolicy, QMessageBox, QDialog, QSplitter
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from src.core.app_state import get_state, AppState, get_channels_for_patched
from src.core.database.models import PatchedFixture, FixtureChannel

# Bestehende Attribut-Konstanten (Kompatibilitaet)
COLOR_ATTRS = {"color_r", "color_g", "color_b", "color_w", "color_a", "color_uv"}
PAN_TILT_ATTRS = {"pan", "tilt", "pan_fine", "tilt_fine"}
INTENSITY_ATTRS = {"intensity", "dimmer", "master"}

# Attribut-Gruppen (Name -> Set of attribute names oder Substring-Match)
ATTR_GROUPS = {
    "Intensity": {"intensity", "dimmer", "master"},
    "Color":     {"color_r", "color_g", "color_b", "color_w", "color_a", "color_uv",
                  "cyan", "magenta", "yellow", "color_wheel", "colour_wheel", "color"},
    "Position":  {"pan", "tilt", "pan_fine", "tilt_fine"},
    "Beam":      {"shutter", "strobe", "zoom", "focus", "frost", "iris", "prism"},
    "Gobo":      {"gobo", "gobo_rotation", "gobo_wheel", "gobo1", "gobo2",
                  "gobo_rot"},
    "Effect":    {"macro", "effect", "effect_speed", "prism_rot", "animation"},
}


def _classify_attribute(attr: str) -> str:
    """Ordnet ein Attribut einer Gruppe zu. Default: 'Other'."""
    a = (attr or "").lower()
    for grp, names in ATTR_GROUPS.items():
        if a in names:
            return grp
        for n in names:
            if n in a:
                return grp
    return "Other"


class ProgrammerView(QWidget):
    """Hauptansicht des Programmers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: AppState = get_state()
        self._selected_fids: list[int] = []
        self._clipboard: dict[int, dict[str, int]] = {}
        self._state.subscribe(self._on_state_change)
        self._setup_ui()
        self._refresh_fixture_list()
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe(SyncEvent.REFRESH_ALL, lambda *_: self._sync_refresh())
            sync.subscribe(SyncEvent.PATCH_CHANGED, lambda *_: self._sync_refresh())
        except Exception as e:
            print(f"[programmer_view] sync subscribe error: {e}")

    # ── Public Helpers ───────────────────────────────────────────────────────

    def get_selected_fids(self) -> list[int]:
        return list(self._selected_fids)

    def _sync_refresh(self):
        try:
            self._refresh_fixture_list()
            self._rebuild_attr_editor()
        except Exception as e:
            print(f"[programmer_view] sync_refresh error: {e}")

    # ── UI Build ─────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Toolbar ──────────────────────────────────────────────────────────
        tb = QHBoxLayout()
        for label, slot, color in [
            ("Highlight", self._highlight, "#FFD700"),
            ("Lowlight",  self._lowlight,  "#888888"),
            ("Clear",     self._clear_programmer, "#ff5555"),
            ("Copy",      self._copy_to_clipboard, "#88aaff"),
            ("Paste",     self._paste_from_clipboard, "#88ffaa"),
            ("Undo",      self._undo, "#cccccc"),
            ("Redo",      self._redo, "#cccccc"),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(26)
            b.setStyleSheet(
                f"QPushButton {{ color: {color}; font-weight: bold; padding: 0 10px; }}"
            )
            b.clicked.connect(slot)
            tb.addWidget(b)
        tb.addSpacing(20)

        # Tool-Buttons (Color, Position, Fan)
        for label, slot in [
            ("Color Tool...",    self._open_color_tool),
            ("Position Tool...", self._open_position_tool),
            ("Fan...",           self._open_fan_tool),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(26)
            b.clicked.connect(slot)
            tb.addWidget(b)

        tb.addStretch(1)
        root.addLayout(tb)

        # ── Main Body ────────────────────────────────────────────────────────
        body = QHBoxLayout()

        # Links: Fixture-Liste
        left = QVBoxLayout()
        hdr = QLabel("Geraete")
        hdr.setObjectName("label_header")
        left.addWidget(hdr)
        self._fixture_list = QListWidget()
        self._fixture_list.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )
        self._fixture_list.itemSelectionChanged.connect(self._on_fixture_selected)
        left.addWidget(self._fixture_list)

        btn_row = QHBoxLayout()
        b_all = QPushButton("Alle")
        b_all.clicked.connect(self._select_all)
        b_none = QPushButton("Keine")
        b_none.clicked.connect(self._fixture_list.clearSelection)
        btn_row.addWidget(b_all)
        btn_row.addWidget(b_none)
        left.addLayout(btn_row)

        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(220)
        body.addWidget(left_w)

        # Rechts: Tab-Editor + Snap-Bibliothek (Splitter)
        right_top = QWidget()
        right_top_layout = QVBoxLayout(right_top)
        right_top_layout.setContentsMargins(0, 0, 0, 0)
        right_top_layout.setSpacing(4)

        self._lbl_selection = QLabel("Kein Geraet ausgewaehlt")
        self._lbl_selection.setObjectName("label_header")
        right_top_layout.addWidget(self._lbl_selection)

        self._color_preview = ColorPreview([], self._state)
        right_top_layout.addWidget(self._color_preview)

        self._attr_tabs = QTabWidget()
        self._attr_tabs.setTabPosition(QTabWidget.TabPosition.North)
        right_top_layout.addWidget(self._attr_tabs, stretch=1)

        try:
            from src.ui.views.snap_file_panel import SnapFilePanel
            self._snap_file_panel = SnapFilePanel()
        except Exception as e:
            print(f"[programmer_view] snap_file_panel load error: {e}")
            self._snap_file_panel = QWidget()

        right_splitter = QSplitter(Qt.Orientation.Horizontal)
        right_splitter.addWidget(right_top)
        right_splitter.addWidget(self._snap_file_panel)
        right_splitter.setSizes([760, 320])
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 1)
        right_splitter.setChildrenCollapsible(False)

        body.addWidget(right_splitter, stretch=1)

        root.addLayout(body, stretch=1)

    # ── Fixture List ─────────────────────────────────────────────────────────

    def _refresh_fixture_list(self):
        self._fixture_list.clear()
        for f in self._state.get_patched_fixtures():
            it = QListWidgetItem(f"[{f.fid:03d}] {f.label}")
            it.setData(Qt.ItemDataRole.UserRole, f.fid)
            self._fixture_list.addItem(it)

    def _select_all(self):
        self._fixture_list.selectAll()

    def _on_fixture_selected(self):
        self._selected_fids = []
        for it in self._fixture_list.selectedItems():
            self._selected_fids.append(it.data(Qt.ItemDataRole.UserRole))
        self._rebuild_attr_editor()

    # ── Attr Tabs Build ──────────────────────────────────────────────────────

    def _rebuild_attr_editor(self):
        # Tabs leeren
        while self._attr_tabs.count():
            w = self._attr_tabs.widget(0)
            self._attr_tabs.removeTab(0)
            if w:
                w.deleteLater()

        if not self._selected_fids:
            self._lbl_selection.setText("Kein Geraet ausgewaehlt")
            self._color_preview.set_fixtures([])
            return

        fixtures = {f.fid: f for f in self._state.get_patched_fixtures()}
        selected = [fixtures[fid] for fid in self._selected_fids if fid in fixtures]
        self._lbl_selection.setText(
            f"{len(selected)} Geraet(e): " +
            ", ".join(f"[{f.fid}] {f.label}" for f in selected[:3]) +
            ("..." if len(selected) > 3 else "")
        )
        self._color_preview.set_fixtures(selected)

        # Sammele alle Kanaele aller selektierten Fixtures (gruppieren nach Gruppe)
        template = selected[0]
        channels = get_channels_for_patched(template)

        # Map: Group -> List[FixtureChannel]
        groups: dict[str, list[FixtureChannel]] = {
            "Intensity": [], "Color": [], "Position": [],
            "Beam": [], "Gobo": [], "Effect": [], "Other": []
        }
        seen_attrs: set[str] = set()
        for ch in channels:
            if ch.attribute in seen_attrs:
                continue
            seen_attrs.add(ch.attribute)
            grp = _classify_attribute(ch.attribute)
            groups[grp].append(ch)

        # Tabs in fester Reihenfolge bauen
        order = ["Intensity", "Color", "Position", "Beam", "Gobo", "Effect", "Other"]
        for grp_name in order:
            chans = groups.get(grp_name, [])
            if not chans and grp_name not in ("Color", "Position"):
                continue
            tab = self._build_group_tab(grp_name, chans, selected)
            self._attr_tabs.addTab(tab, grp_name)

    def _build_group_tab(self, group_name: str,
                         channels: list[FixtureChannel],
                         fixtures: list[PatchedFixture]) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Sub-Toolbar
        sub_tb = QHBoxLayout()
        b_fan = QPushButton(f"Fan {group_name}...")
        b_fan.clicked.connect(lambda: self._open_fan_tool_for_group(group_name))
        sub_tb.addWidget(b_fan)

        if group_name == "Color":
            b_ct = QPushButton("Color Picker einbetten")
            b_ct.setCheckable(True)
            b_ct.toggled.connect(lambda chk: self._toggle_embedded_color(tab, chk))
            sub_tb.addWidget(b_ct)
        elif group_name == "Position":
            b_pt = QPushButton("Position Tool einbetten")
            b_pt.setCheckable(True)
            b_pt.toggled.connect(lambda chk: self._toggle_embedded_position(tab, chk))
            sub_tb.addWidget(b_pt)
        sub_tb.addStretch(1)
        layout.addLayout(sub_tb)

        # Slider-Liste
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        ilay = QVBoxLayout(inner)
        ilay.setAlignment(Qt.AlignmentFlag.AlignTop)
        if not channels:
            ilay.addWidget(QLabel(f"Keine {group_name}-Kanaele gefunden."))
        else:
            for ch in channels:
                ilay.addWidget(AttributeSlider(ch, fixtures, self._state))
        scroll.setWidget(inner)
        layout.addWidget(scroll, stretch=1)

        return tab

    def _toggle_embedded_color(self, tab: QWidget, on: bool):
        # Embed color picker in tab below the slider list
        layout = tab.layout()
        if on and not hasattr(tab, "_embedded_cp"):
            try:
                from src.ui.widgets.color_picker import ColorPicker
                cp = ColorPicker()
                layout.addWidget(cp)
                tab._embedded_cp = cp
            except Exception as e:
                print(f"[programmer_view] color picker embed error: {e}")
        elif not on and hasattr(tab, "_embedded_cp"):
            tab._embedded_cp.setParent(None)
            tab._embedded_cp.deleteLater()
            del tab._embedded_cp

    def _toggle_embedded_position(self, tab: QWidget, on: bool):
        layout = tab.layout()
        if on and not hasattr(tab, "_embedded_pt"):
            try:
                from src.ui.widgets.position_tool import PositionTool
                pt = PositionTool()
                layout.addWidget(pt)
                tab._embedded_pt = pt
            except Exception as e:
                print(f"[programmer_view] position tool embed error: {e}")
        elif not on and hasattr(tab, "_embedded_pt"):
            tab._embedded_pt.setParent(None)
            tab._embedded_pt.deleteLater()
            del tab._embedded_pt

    # ── Toolbar Actions ──────────────────────────────────────────────────────

    def _highlight(self):
        """Setzt selektierte Fixtures auf: Intensity 255, Pan/Tilt center, weiss."""
        if not self._selected_fids:
            return
        for fid in self._selected_fids:
            self._state.set_programmer_value(fid, "intensity", 255)
            self._state.set_programmer_value(fid, "pan", 127)
            self._state.set_programmer_value(fid, "tilt", 127)
            self._state.set_programmer_value(fid, "color_r", 255)
            self._state.set_programmer_value(fid, "color_g", 255)
            self._state.set_programmer_value(fid, "color_b", 255)

    def _lowlight(self):
        """Dimmt nicht-selektierte Fixtures auf ca 30 % (intensity 76)."""
        all_fids = [f.fid for f in self._state.get_patched_fixtures()]
        sel = set(self._selected_fids)
        for fid in all_fids:
            if fid in sel:
                continue
            self._state.set_programmer_value(fid, "intensity", 76)

    def _clear_programmer(self):
        if not self._selected_fids:
            # Komplett leeren
            self._state.clear_programmer()
        else:
            for fid in self._selected_fids:
                self._state.clear_programmer(fid)
        self._rebuild_attr_editor()

    def _copy_to_clipboard(self):
        self._clipboard = copy.deepcopy({
            fid: self._state.programmer.get(fid, {})
            for fid in self._selected_fids
        })

    def _paste_from_clipboard(self):
        if not self._clipboard or not self._selected_fids:
            return
        clip_list = list(self._clipboard.values())
        if not clip_list:
            return
        # Round-robin: clip Value n -> selected fixture n (mod len)
        for i, fid in enumerate(self._selected_fids):
            src = clip_list[i % len(clip_list)]
            for attr, val in src.items():
                self._state.set_programmer_value(fid, attr, val)

    def _undo(self):
        try:
            from src.core.undo import get_undo_stack
            get_undo_stack().undo()
        except Exception as e:
            print(f"[programmer_view] undo error: {e}")

    def _redo(self):
        try:
            from src.core.undo import get_undo_stack
            get_undo_stack().redo()
        except Exception as e:
            print(f"[programmer_view] redo error: {e}")

    # ── Tools (Dialoge) ──────────────────────────────────────────────────────

    def _open_color_tool(self):
        try:
            from src.ui.widgets.color_picker import ColorPicker
            dlg = _ToolDialog("Color Tool", self)
            cp = ColorPicker()
            dlg.set_content(cp)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "Color Tool", str(e))

    def _open_position_tool(self):
        try:
            from src.ui.widgets.position_tool import PositionTool
            dlg = _ToolDialog("Position Tool", self)
            pt = PositionTool()
            dlg.set_content(pt)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "Position Tool", str(e))

    def _open_fan_tool(self):
        try:
            from src.ui.widgets.fan_tool import FanTool
            dlg = _ToolDialog("Fan Tool", self)
            ft = FanTool()
            ft.set_selection(self._selected_fids)
            dlg.set_content(ft)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "Fan Tool", str(e))

    def _open_fan_tool_for_group(self, group_name: str):
        try:
            from src.ui.widgets.fan_tool import FanTool, FAN_ATTRIBUTES
            dlg = _ToolDialog(f"Fan Tool - {group_name}", self)
            ft = FanTool()
            ft.set_selection(self._selected_fids)
            # Default attribute fuer die Gruppe
            default_attr = {
                "Intensity": "intensity",
                "Color":     "color_r",
                "Position":  "pan",
                "Beam":      "zoom",
                "Gobo":      "gobo",
                "Effect":    "macro",
            }.get(group_name, "intensity")
            for i in range(ft._combo_attr.count()):
                if ft._combo_attr.itemData(i) == default_attr:
                    ft._combo_attr.setCurrentIndex(i)
                    break
            dlg.set_content(ft)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "Fan Tool", str(e))

    # ── Legacy State Events ──────────────────────────────────────────────────

    def _on_state_change(self, event: str, _data):
        if event == "patch_changed":
            self._refresh_fixture_list()
            self._rebuild_attr_editor()
        elif event == "programmer_changed":
            if hasattr(self, "_color_preview"):
                self._color_preview.update_colors()


class _ToolDialog(QDialog):
    """Schmaler modaler Wrapper fuer Tool-Widgets."""
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(640, 520)
        self._layout = QVBoxLayout(self)

    def set_content(self, widget: QWidget):
        self._layout.addWidget(widget)
        btn = QPushButton("Schliessen")
        btn.clicked.connect(self.accept)
        self._layout.addWidget(btn)


# ─────────────────────────────────────────────────────────────────────────────
# Slider + Color Preview (Reused)
# ─────────────────────────────────────────────────────────────────────────────

class AttributeSlider(QWidget):
    """Ein Slider + Label + Wert-Anzeige fuer ein Fixture-Attribut."""

    ATTR_COLORS = {
        "intensity": "#ffcc00",
        "color_r": "#ff4444",
        "color_g": "#44ff44",
        "color_b": "#4488ff",
        "color_w": "#ffffff",
        "color_a": "#ffaa00",
        "color_uv": "#aa44ff",
        "pan": "#00ccff",
        "tilt": "#00ccff",
        "pan_fine": "#007799",
        "tilt_fine": "#007799",
    }

    def __init__(self, channel: FixtureChannel, fixtures: list[PatchedFixture],
                 state: AppState, parent=None):
        super().__init__(parent)
        self._channel = channel
        self._fixtures = fixtures
        self._state = state
        self._setup_ui()
        self._load_current_value()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)

        indicator = QFrame()
        indicator.setFixedSize(6, 24)
        color = self.ATTR_COLORS.get(self._channel.attribute, "#555")
        indicator.setStyleSheet(f"background: {color}; border-radius: 3px;")
        layout.addWidget(indicator)

        lbl = QLabel(self._channel.name)
        lbl.setFixedWidth(120)
        layout.addWidget(lbl)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 255)
        self._slider.setValue(self._channel.default_value)
        self._slider.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self._slider, stretch=1)

        self._lbl_val = QLabel("0")
        self._lbl_val.setObjectName("label_value")
        self._lbl_val.setFixedWidth(38)
        self._lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._lbl_val)

        self._lbl_pct = QLabel("0%")
        self._lbl_pct.setFixedWidth(38)
        self._lbl_pct.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._lbl_pct)

        btn_reset = QPushButton("↺")
        btn_reset.setFixedSize(24, 24)
        btn_reset.setToolTip("Auf Standard zuruecksetzen")
        btn_reset.clicked.connect(self._reset)
        layout.addWidget(btn_reset)

    def _load_current_value(self):
        if not self._fixtures:
            return
        val = self._state.get_programmer_value(
            self._fixtures[0].fid, self._channel.attribute
        )
        if val is None:
            val = self._channel.default_value
        self._slider.blockSignals(True)
        self._slider.setValue(val)
        self._slider.blockSignals(False)
        self._update_labels(val)

    def _on_value_changed(self, value: int):
        self._update_labels(value)
        for f in self._fixtures:
            self._state.set_programmer_value(f.fid, self._channel.attribute, value)

    def _reset(self):
        self._slider.setValue(self._channel.default_value)

    def _update_labels(self, value: int):
        self._lbl_val.setText(str(value))
        self._lbl_pct.setText(f"{int(value / 255 * 100)}%")


class ColorPreview(QWidget):
    """Zeigt aktuelle Farbe pro Fixture."""

    def __init__(self, fixtures: list[PatchedFixture], state: AppState, parent=None):
        super().__init__(parent)
        self._fixtures = fixtures
        self._state = state
        self.setFixedHeight(36)
        self.update_colors()

    def set_fixtures(self, fixtures: list[PatchedFixture]):
        self._fixtures = fixtures
        self.update_colors()

    def update_colors(self):
        self._colors = []
        for f in self._fixtures:
            r = self._state.get_programmer_value(f.fid, "color_r") or 0
            g = self._state.get_programmer_value(f.fid, "color_g") or 0
            b = self._state.get_programmer_value(f.fid, "color_b") or 0
            self._colors.append(QColor(r, g, b))
        self.update()

    def paintEvent(self, _event):
        if not self._colors:
            return
        p = QPainter(self)
        w = self.width()
        h = self.height()
        sw = w // len(self._colors) if self._colors else w
        for i, color in enumerate(self._colors):
            p.fillRect(i * sw, 0, sw, h, color)
        p.setPen(QColor("#333"))
        p.drawRect(0, 0, w - 1, h - 1)
        p.end()
