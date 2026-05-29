"""3D/2D Visualizer - separates Fenster mit Three.js Stage-Ansicht.

Features:
- 2D Top-Down Edit-Modus zum Positionieren von Fixtures
- 3D Perspektivansicht
- Custom Stage Builder (Plattformen, Truss, Waende, LED-Walls, Speaker, ...)
- Bidirektionale Bruecke Python <-> JavaScript via QWebChannel
- Stage-Persistenz in %APPDATA%/LightOS/stages/
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QComboBox, QToolBar, QListWidget, QListWidgetItem,
    QSplitter, QGroupBox, QFormLayout, QSlider, QCheckBox,
    QDoubleSpinBox, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QColorDialog, QInputDialog, QMessageBox, QLineEdit, QSizePolicy,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile, QWebEnginePage
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QUrl, Qt, QTimer, Signal, Slot, QObject
from PySide6.QtGui import QAction, QColor

from src.core.app_state import AppState, get_state, get_channels_for_patched
from src.core.database.models import PatchedFixture
from src.core.stage.stage_definition import (
    StageDefinition, StageElement,
    list_stages, load_stage, save_stage, delete_stage,
    get_default_simple, get_default_theatre, get_default_rock,
    DEFAULT_PRESETS,
)

HTML_PATH = os.path.join(os.path.dirname(__file__), "stage_scene.html")

# Fixture-Positionen leben in AppState.visualizer_positions ({fid: (x, y, z)})
# und werden mit der Show (.lshow) persistiert. Zugriff ueber self._state.


# ============================================================================
# Bridge
# ============================================================================

class VisualizerBridge(QObject):
    """Kommunikationsbruecke Python <-> JavaScript (Three.js).

    Signals -> JS
        fixtureAdded(json), fixtureRemoved(fid), dmxUpdated(json),
        allFixtures(json), settingsChanged(json), stageChanged(name),
        viewModeChanged(name), editModeChanged(name), stageLoaded(json),
        addStageObject(type), removeStageObject(id), selectStageObject(id),
        applyFixtureTransform(json), alignSelected(mode),
        distributeSelected(axis), requestSaveStage(), cameraReset()

    Slots <- JS
        requestFixtures(), placeFixture(json), fixturePositionChanged(...),
        fixtureSelectionChanged(json), fixtureDeleted(fid),
        stageListChanged(json), stageSelectionChanged(id), saveStage(json)
    """

    # ── Signals -> JavaScript ───────────────────────────────────────────────
    fixtureAdded            = Signal(str)
    fixtureRemoved          = Signal(int)
    dmxUpdated              = Signal(str)
    allFixtures             = Signal(str)
    settingsChanged         = Signal(str)
    stageChanged            = Signal(str)
    viewModeChanged         = Signal(str)
    editModeChanged         = Signal(str)
    stageLoaded             = Signal(str)
    addStageObject          = Signal(str)
    removeStageObject       = Signal(str)
    selectStageObject       = Signal(str)
    applyFixtureTransform   = Signal(str)
    alignSelected           = Signal(str)
    distributeSelected      = Signal(str)
    requestSaveStage        = Signal()
    cameraReset             = Signal()
    brightnessSignal        = Signal(float)   # 0.0 - 1.0
    brightnessAutoSignal    = Signal()        # Reset auto-mode
    updateStageObject       = Signal(str)     # JSON: gezieltes Update eines Stage-Elements
    resizeModeSignal        = Signal(bool)    # Toggle Resize-Handles im JS

    # ── Python-seitige Signals (an die Hauptfenster-Klasse) ─────────────────
    pyFixtureMoved          = Signal(int, float, float, float)
    pyFixtureSelection      = Signal(list)
    pyFixtureDeleted        = Signal(int)
    pyStageListChanged      = Signal(list)
    pyStageSelection        = Signal(str)
    pyStageSaved            = Signal(dict)
    pyBrightnessChanged     = Signal(float)   # JS meldet Auto-Brightness an Slider

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._state.subscribe(self._on_state)

    # ── Slots aufgerufen durch JavaScript ───────────────────────────────────

    @Slot()
    def requestFixtures(self):
        try:
            fixtures = self._build_fixture_list()
            self.allFixtures.emit(json.dumps(fixtures))
        except Exception as e:
            print(f"[Visualizer] requestFixtures error: {e}")

    @Slot(str)
    def placeFixture(self, pos_json: str):
        """JS sendet Rechtsklick-Position - platziert den naechsten
        noch unplatzierten Fixture an dieser Stelle."""
        try:
            pos = json.loads(pos_json)
            for f in self._state.get_patched_fixtures():
                if f.fid not in self._state.visualizer_positions:
                    self._state.visualizer_positions[f.fid] = (
                        float(pos["x"]),
                        float(pos.get("y", 6.5)),
                        float(pos["z"]),
                    )
                    data = self._fixture_to_dict(f)
                    self.fixtureAdded.emit(json.dumps(data))
                    return
        except Exception as e:
            print(f"[Visualizer] placeFixture error: {e}")

    @Slot(str, float, float, float)
    def fixturePositionChanged(self, fid_str: str, x: float, y: float, z: float):
        """JS meldet neue Fixture-Position (nach Drag)."""
        try:
            fid = int(fid_str)
            self._state.visualizer_positions[fid] = (float(x), float(y), float(z))
            self.pyFixtureMoved.emit(fid, float(x), float(y), float(z))
        except Exception as e:
            print(f"[Visualizer] fixturePositionChanged error: {e}")

    @Slot(str)
    def fixtureSelectionChanged(self, fids_json: str):
        try:
            fids = json.loads(fids_json) or []
            self.pyFixtureSelection.emit([int(x) for x in fids])
        except Exception as e:
            print(f"[Visualizer] fixtureSelectionChanged error: {e}")

    @Slot(str)
    def fixtureDeleted(self, fid_str: str):
        try:
            fid = int(fid_str)
            self._state.visualizer_positions.pop(fid, None)
            self.pyFixtureDeleted.emit(fid)
        except Exception as e:
            print(f"[Visualizer] fixtureDeleted error: {e}")

    @Slot(str)
    def stageListChanged(self, json_str: str):
        try:
            data = json.loads(json_str) or []
            self.pyStageListChanged.emit(data)
        except Exception as e:
            print(f"[Visualizer] stageListChanged error: {e}")

    @Slot(str)
    def stageSelectionChanged(self, sid: str):
        try:
            self.pyStageSelection.emit(sid or "")
        except Exception as e:
            print(f"[Visualizer] stageSelectionChanged error: {e}")

    @Slot(str)
    def saveStage(self, json_str: str):
        try:
            data = json.loads(json_str) or {}
            self.pyStageSaved.emit(data)
        except Exception as e:
            print(f"[Visualizer] saveStage error: {e}")

    @Slot(float)
    def brightnessChanged(self, value: float):
        """JS meldet wenn Auto-Brightness die Helligkeit aendert."""
        try:
            self.pyBrightnessChanged.emit(float(value))
        except Exception as e:
            print(f"[Visualizer] brightnessChanged error: {e}")

    # ── Python -> JS helpers ────────────────────────────────────────────────

    def place_fixture_at(self, fid: int, x: float, y: float, z: float):
        self._state.visualizer_positions[fid] = (x, y, z)
        fixtures = {f.fid: f for f in self._state.get_patched_fixtures()}
        if fid in fixtures:
            self.fixtureAdded.emit(json.dumps(self._fixture_to_dict(fixtures[fid])))

    def remove_fixture_from_scene(self, fid: int):
        self._state.visualizer_positions.pop(fid, None)
        self.fixtureRemoved.emit(fid)

    def push_dmx_update(self, fid: int, attrs: dict[str, int]):
        try:
            r = attrs.get("color_r", 0)
            g = attrs.get("color_g", 0)
            b = attrs.get("color_b", 0)
            w = attrs.get("color_w", 0)
            intensity = attrs.get("intensity", 255)
            pan = attrs.get("pan", 128)
            tilt = attrs.get("tilt", 128)
            payload = {
                "fid": fid,
                "r": min(255, r + w),
                "g": min(255, g + w),
                "b": min(255, b + w),
                "intensity": intensity,
                "pan": pan,
                "tilt": tilt,
            }
            self.dmxUpdated.emit(json.dumps(payload))
        except Exception as e:
            print(f"[Visualizer] push_dmx_update error: {e}")

    def push_settings(self, s: dict):
        try:
            self.settingsChanged.emit(json.dumps(s))
        except Exception as e:
            print(f"[Visualizer] push_settings error: {e}")

    def push_stage_preset(self, name: str):
        try:
            self.stageChanged.emit(name)
        except Exception as e:
            print(f"[Visualizer] push_stage_preset error: {e}")

    def push_view_mode(self, mode: str):
        try:
            self.viewModeChanged.emit(mode)
        except Exception as e:
            print(f"[Visualizer] push_view_mode error: {e}")

    def push_edit_mode(self, mode: str):
        try:
            self.editModeChanged.emit(mode)
        except Exception as e:
            print(f"[Visualizer] push_edit_mode error: {e}")

    def push_stage_definition(self, definition: StageDefinition):
        try:
            self.stageLoaded.emit(json.dumps(definition.to_js_dict()))
        except Exception as e:
            print(f"[Visualizer] push_stage_definition error: {e}")

    def push_add_stage_object(self, type_: str):
        try:
            self.addStageObject.emit(type_)
        except Exception as e:
            print(f"[Visualizer] push_add_stage_object error: {e}")

    def push_remove_stage_object(self, sid: str):
        try:
            self.removeStageObject.emit(sid)
        except Exception as e:
            print(f"[Visualizer] push_remove_stage_object error: {e}")

    def push_select_stage_object(self, sid: str):
        try:
            self.selectStageObject.emit(sid)
        except Exception as e:
            print(f"[Visualizer] push_select_stage_object error: {e}")

    def push_apply_fixture_transform(self, fid: int, x: float, y: float, z: float, rot_y: float = 0.0):
        try:
            payload = {"fid": fid, "x": x, "y": y, "z": z, "rotY": rot_y}
            self.applyFixtureTransform.emit(json.dumps(payload))
        except Exception as e:
            print(f"[Visualizer] push_apply_fixture_transform error: {e}")

    # ── interne helpers ─────────────────────────────────────────────────────

    def _fixture_to_dict(self, f: PatchedFixture) -> dict:
        pos = self._state.visualizer_positions.get(f.fid, (0.0, 6.5, 0.0))
        return {
            "fid": f.fid,
            "label": f.label,
            "type": f.fixture_type,
            "x": pos[0], "y": pos[1], "z": pos[2],
            "r": 0, "g": 0, "b": 0, "intensity": 0,
            "pan": 128, "tilt": 128,
        }

    def _build_fixture_list(self) -> list[dict]:
        return [
            self._fixture_to_dict(f)
            for f in self._state.get_patched_fixtures()
            if f.fid in self._state.visualizer_positions
        ]

    def _on_state(self, event: str, data):
        if event == "patch_changed":
            current_fids = {f.fid for f in self._state.get_patched_fixtures()}
            stale = [fid for fid in list(self._state.visualizer_positions) if fid not in current_fids]
            for fid in stale:
                self.remove_fixture_from_scene(fid)


# ============================================================================
# Hauptfenster
# ============================================================================

class VisualizerWindow(QMainWindow):

    STAGE_TYPES = [
        ("platform",  "Plattform"),
        ("truss_h",   "Truss (horizontal)"),
        ("truss_v",   "Truss/Stuetze (vertikal)"),
        ("wall",      "Wand / Backdrop"),
        ("led_wall",  "LED-Wand"),
        ("speaker",   "Lautsprecher"),
        ("audience",  "Publikumsflaeche"),
        ("dj_booth",  "DJ-Booth"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = get_state()
        self.setWindowTitle("LightOS - 3D/2D Visualizer")
        self.resize(1400, 850)

        self._current_stage: StageDefinition = get_default_simple()
        self._stage_elements_cache: list[dict] = []   # spiegel der JS-stageObjects
        self._selected_stage_id: str = ""
        self._suppress_property_signals = False

        self._setup_ui()
        self._setup_channel()
        self._setup_update_timer()

    # ── UI ──────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        # -------- Toolbar (touch-optimiert) --------
        tb = QToolBar("Visualizer")
        tb.setMovable(False)
        tb.setStyleSheet(
            "QToolBar { spacing: 6px; padding: 4px; }"
            "QToolButton { min-height: 38px; min-width: 38px;"
            "              padding: 6px 12px; font-size: 12px; }"
            "QComboBox   { min-height: 36px; padding: 4px 8px;"
            "              font-size: 12px; min-width: 130px; }"
            "QComboBox QAbstractItemView::item { min-height: 32px; padding: 4px; }"
            "QToolBar QLabel { padding: 0 4px; font-weight: bold; }"
        )
        self.addToolBar(tb)

        tb.addWidget(QLabel("Ansicht:"))
        self._combo_view = QComboBox()
        self._combo_view.addItem("3D Perspective", "3D")
        self._combo_view.addItem("2D Top-Down",    "2D")
        self._combo_view.currentIndexChanged.connect(self._on_view_mode_changed)
        tb.addWidget(self._combo_view)

        tb.addWidget(QLabel("Modus:"))
        self._combo_edit = QComboBox()
        self._combo_edit.addItem("Ansehen",            "view")
        self._combo_edit.addItem("Fixtures bearbeiten", "edit")
        self._combo_edit.addItem("Buehne bearbeiten",   "stage")
        self._combo_edit.currentIndexChanged.connect(self._on_edit_mode_changed)
        tb.addWidget(self._combo_edit)

        tb.addSeparator()

        tb.addWidget(QLabel("Buehne:"))
        self._combo_stage = QComboBox()
        self._reload_stage_combo()
        self._combo_stage.currentIndexChanged.connect(self._on_stage_combo_changed)
        tb.addWidget(self._combo_stage)

        act_save = QAction("💾 Speichern", self)
        act_save.triggered.connect(self._on_save_stage)
        tb.addAction(act_save)

        act_new = QAction("✚ Neu", self)
        act_new.triggered.connect(self._on_new_stage)
        tb.addAction(act_new)

        act_del = QAction("🗑 Loeschen", self)
        act_del.triggered.connect(self._on_delete_stage)
        tb.addAction(act_del)

        tb.addSeparator()

        act_reset_cam = QAction("⌖ Kamera", self)
        act_reset_cam.triggered.connect(self._reset_camera)
        tb.addAction(act_reset_cam)

        act_clear_fx = QAction("✖ Alle Fixtures", self)
        act_clear_fx.triggered.connect(self._clear_positions)
        tb.addAction(act_clear_fx)

        # -------- Splitter --------
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._view = QWebEngineView()
        # ── CACHE FIX: HTTP-Cache komplett deaktivieren ──────────────────────
        try:
            profile = self._view.page().profile()
            profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
            )
            profile.setHttpCacheMaximumSize(1)
        except Exception as e:
            print(f"[Visualizer] cache-disable error: {e}")
        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        splitter.addWidget(self._view)

        right_panel = self._build_right_panel()
        right_panel.setMinimumWidth(330)
        right_panel.setMaximumWidth(420)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        self.setCentralWidget(splitter)

        # Info bar
        self._lbl_info = QLabel("Bereit")
        self._lbl_info.setStyleSheet("color: #888; font-size: 11px;")
        self.statusBar().addWidget(self._lbl_info)

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_fixture_tab(), "Fixtures")
        self._tabs.addTab(self._build_stage_tab(),   "Buehne")
        self._tabs.addTab(self._build_settings_tab(), "Einstellungen")
        layout.addWidget(self._tabs)
        return panel

    # ----- Fixtures-Tab -----
    def _build_fixture_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        layout.addWidget(QLabel("Gepatchte Fixtures:"))
        self._patch_list = QListWidget()
        self._patch_list.itemSelectionChanged.connect(self._on_patch_list_selected)
        layout.addWidget(self._patch_list, 1)

        row = QHBoxLayout()
        btn_place = QPushButton("Im Raum platzieren")
        btn_place.setMinimumHeight(40)
        btn_place.clicked.connect(self._place_selected)
        row.addWidget(btn_place)
        btn_remove = QPushButton("Entfernen")
        btn_remove.setMinimumHeight(40)
        btn_remove.clicked.connect(self._remove_selected)
        row.addWidget(btn_remove)
        layout.addLayout(row)

        box = QGroupBox("Position (X / Y / Z)")
        form = QFormLayout(box)
        self._spin_x = QDoubleSpinBox(); self._spin_x.setRange(-50, 50); self._spin_x.setSingleStep(0.5)
        self._spin_y = QDoubleSpinBox(); self._spin_y.setRange(0, 25);   self._spin_y.setSingleStep(0.25); self._spin_y.setValue(6.5)
        self._spin_z = QDoubleSpinBox(); self._spin_z.setRange(-30, 30); self._spin_z.setSingleStep(0.5)
        for sp in (self._spin_x, self._spin_y, self._spin_z):
            sp.setMinimumHeight(38)
            sp.valueChanged.connect(self._on_fixture_pos_spin_changed)
        form.addRow("X (links/rechts):", self._spin_x)
        form.addRow("Y (Hoehe):",        self._spin_y)
        form.addRow("Z (vorne/hinten):", self._spin_z)
        layout.addWidget(box)

        return w

    # ----- Stage-Tab -----
    def _build_stage_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        layout.addWidget(QLabel("Buehnen-Elemente:"))
        self._stage_tree = QTreeWidget()
        self._stage_tree.setHeaderLabels(["Typ", "Name"])
        self._stage_tree.itemSelectionChanged.connect(self._on_stage_tree_selected)
        # Touch-freundliche groessere Zeilen + ruhigeres Painting
        self._stage_tree.setStyleSheet(
            "QTreeWidget::item { padding: 8px 4px; }"
            "QTreeWidget::item:selected { background: #ffd700; color: #000; }"
        )
        self._stage_tree.setUniformRowHeights(True)   # weniger Reflow beim Add/Remove
        self._stage_tree.setAlternatingRowColors(True)
        layout.addWidget(self._stage_tree, 1)

        # Add-buttons grid
        add_box = QGroupBox("Element hinzufuegen")
        add_grid = QVBoxLayout(add_box)
        add_grid.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(4)
        col_count = 0
        for type_, label in self.STAGE_TYPES:
            btn = QPushButton("+ " + label)
            btn.setMinimumHeight(40)
            btn.clicked.connect(lambda _checked=False, t=type_: self._add_stage_element(t))
            row.addWidget(btn)
            col_count += 1
            if col_count == 2:
                add_grid.addLayout(row)
                row = QHBoxLayout()
                row.setSpacing(4)
                col_count = 0
        if col_count > 0:
            add_grid.addLayout(row)
        layout.addWidget(add_box)

        # Properties
        prop_box = QGroupBox("Eigenschaften (Selektion)")
        prop_form = QFormLayout(prop_box)
        self._stage_name_edit = QLineEdit()
        self._stage_name_edit.editingFinished.connect(self._on_stage_property_changed)
        prop_form.addRow("Name:", self._stage_name_edit)

        self._stage_spin_x = QDoubleSpinBox(); self._stage_spin_x.setRange(-50, 50); self._stage_spin_x.setSingleStep(0.5)
        self._stage_spin_y = QDoubleSpinBox(); self._stage_spin_y.setRange(0, 30);   self._stage_spin_y.setSingleStep(0.25)
        self._stage_spin_z = QDoubleSpinBox(); self._stage_spin_z.setRange(-30, 30); self._stage_spin_z.setSingleStep(0.5)
        self._stage_spin_w = QDoubleSpinBox(); self._stage_spin_w.setRange(0.05, 60); self._stage_spin_w.setSingleStep(0.5); self._stage_spin_w.setValue(4)
        self._stage_spin_h = QDoubleSpinBox(); self._stage_spin_h.setRange(0.05, 30); self._stage_spin_h.setSingleStep(0.25); self._stage_spin_h.setValue(0.4)
        self._stage_spin_d = QDoubleSpinBox(); self._stage_spin_d.setRange(0.05, 60); self._stage_spin_d.setSingleStep(0.5); self._stage_spin_d.setValue(4)
        self._stage_spin_rot = QDoubleSpinBox(); self._stage_spin_rot.setRange(-360, 360); self._stage_spin_rot.setSingleStep(15); self._stage_spin_rot.setSuffix(" deg")

        for sp in (self._stage_spin_x, self._stage_spin_y, self._stage_spin_z,
                   self._stage_spin_w, self._stage_spin_h, self._stage_spin_d,
                   self._stage_spin_rot):
            sp.setMinimumHeight(38)
            sp.valueChanged.connect(self._on_stage_property_changed)

        prop_form.addRow("X:", self._stage_spin_x)
        prop_form.addRow("Y:", self._stage_spin_y)
        prop_form.addRow("Z:", self._stage_spin_z)
        prop_form.addRow("Breite (W):", self._stage_spin_w)
        prop_form.addRow("Hoehe  (H):", self._stage_spin_h)
        prop_form.addRow("Tiefe  (D):", self._stage_spin_d)
        prop_form.addRow("Rotation:",   self._stage_spin_rot)

        color_row = QHBoxLayout()
        self._stage_color_btn = QPushButton("Farbe waehlen")
        self._stage_color_btn.clicked.connect(self._on_pick_stage_color)
        color_row.addWidget(self._stage_color_btn)
        self._stage_color_preview = QLabel("    ")
        self._stage_color_preview.setMinimumWidth(40)
        self._stage_color_preview.setStyleSheet("background:#2a2a3a; border:1px solid #555;")
        color_row.addWidget(self._stage_color_preview)
        prop_form.addRow("Farbe:", color_row)

        # Resize-Mode Toggle (default AUS - sonst stoeren die Handles bei kleinen Elementen)
        self._btn_resize_mode = QPushButton("Groesse anpassen")
        self._btn_resize_mode.setCheckable(True)
        self._btn_resize_mode.setChecked(False)
        self._btn_resize_mode.setMinimumHeight(32)
        self._btn_resize_mode.setToolTip(
            "AUS: Element kann nur verschoben werden (kein Stoeren durch Eck-Handles).\n"
            "AN: 4 gelbe Eck-Handles erscheinen - mit Maus ziehen zum Groesse aendern."
        )
        self._btn_resize_mode.setStyleSheet(
            "QPushButton {"
            " background-color: #2a3a4a; color: #ddd;"
            " border: 1px solid #4a5a6a; border-radius: 4px;"
            " padding: 4px 12px; font-weight: bold;"
            "}"
            "QPushButton:hover { background-color: #3a4a5a; }"
            "QPushButton:checked {"
            " background-color: #ffd700; color: #000;"
            " border: 2px solid #b89000;"
            "}"
        )
        self._btn_resize_mode.toggled.connect(self._on_resize_mode_toggled)
        prop_form.addRow(self._btn_resize_mode)

        del_row = QHBoxLayout()
        btn_del = QPushButton("Element LOESCHEN")
        btn_del.setObjectName("btn_danger")
        btn_del.setMinimumHeight(36)
        btn_del.setStyleSheet(
            "QPushButton {"
            " background-color: #c0392b;"
            " color: white;"
            " font-weight: bold;"
            " font-size: 13px;"
            " border: 2px solid #8b1e0e;"
            " border-radius: 4px;"
            " padding: 6px 12px;"
            "}"
            "QPushButton:hover { background-color: #e04030; }"
            "QPushButton:pressed { background-color: #8b1e0e; }"
        )
        btn_del.clicked.connect(self._delete_selected_stage_element)
        del_row.addWidget(btn_del)
        prop_form.addRow(del_row)

        layout.addWidget(prop_box)
        return w

    # ----- Settings-Tab -----
    def _build_settings_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # ── Helligkeit (NEU) ────────────────────────────────────────────────
        brightness_group = QGroupBox("Szenen-Helligkeit")
        bg_layout = QVBoxLayout(brightness_group)

        b_row = QHBoxLayout()
        b_row.addWidget(QLabel("Helligkeit:"))
        self._sld_brightness = QSlider(Qt.Orientation.Horizontal)
        self._sld_brightness.setRange(0, 100)
        self._sld_brightness.setValue(20)
        self._sld_brightness.setToolTip(
            "Hintergrund/Ambient-Licht der Visualizer-Szene.\n"
            "Niedrig = dunkel (Beams sichtbar)\n"
            "Hoch = hell (Buehne gut sichtbar zum Bearbeiten)"
        )
        self._sld_brightness.valueChanged.connect(self._on_brightness_changed)
        b_row.addWidget(self._sld_brightness, 1)
        self._lbl_brightness = QLabel("20%")
        self._lbl_brightness.setFixedWidth(38)
        b_row.addWidget(self._lbl_brightness)
        bg_layout.addLayout(b_row)

        ab_row = QHBoxLayout()
        self._chk_auto_brightness = QCheckBox("Auto-Helligkeit im Edit-Modus")
        self._chk_auto_brightness.setChecked(True)
        self._chk_auto_brightness.setToolTip(
            "Wenn aktiv: Helligkeit springt automatisch auf 65% wenn du in den\n"
            "Fixtures-/Buehne-Edit-Modus wechselst, und zurueck auf 20% im Ansichts-Modus."
        )
        self._chk_auto_brightness.toggled.connect(self._on_auto_brightness_toggled)
        ab_row.addWidget(self._chk_auto_brightness)
        btn_auto = QPushButton("Auto-Werte anwenden")
        btn_auto.setFixedHeight(22)
        btn_auto.clicked.connect(self._on_auto_brightness_apply)
        ab_row.addWidget(btn_auto)
        bg_layout.addLayout(ab_row)

        # Quick-Presets
        preset_row = QHBoxLayout()
        for label, val in [("Konzert (10%)", 10), ("Standard (20%)", 20),
                           ("Probe (50%)", 50), ("Bearbeiten (75%)", 75),
                           ("Vollhell (100%)", 100)]:
            btn = QPushButton(label)
            btn.setFixedHeight(22)
            btn.clicked.connect(lambda _, v=val: self._sld_brightness.setValue(v))
            preset_row.addWidget(btn)
        bg_layout.addLayout(preset_row)

        layout.addWidget(brightness_group)

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Beam Opacity:"))
        self._sld_opacity = QSlider(Qt.Orientation.Horizontal)
        self._sld_opacity.setRange(0, 100)
        self._sld_opacity.setValue(70)
        self._sld_opacity.valueChanged.connect(self._on_settings_changed)
        opacity_row.addWidget(self._sld_opacity, 1)
        self._lbl_opacity = QLabel("70%")
        self._lbl_opacity.setFixedWidth(38)
        opacity_row.addWidget(self._lbl_opacity)
        layout.addLayout(opacity_row)

        self._chk_cones = QCheckBox("Lichtkegel anzeigen");      self._chk_cones.setChecked(True)
        self._chk_floor = QCheckBox("Bodenpunkte anzeigen");     self._chk_floor.setChecked(True)
        self._chk_fog   = QCheckBox("Nebel/Haze anzeigen");      self._chk_fog.setChecked(True)
        self._chk_snap  = QCheckBox("Snap to Grid (1m)");        self._chk_snap.setChecked(True)
        for c in (self._chk_cones, self._chk_floor, self._chk_fog, self._chk_snap):
            c.toggled.connect(self._on_settings_changed)
            layout.addWidget(c)

        grid_row = QHBoxLayout()
        grid_row.addWidget(QLabel("Grid-Schritt (m):"))
        self._spin_grid = QDoubleSpinBox()
        self._spin_grid.setRange(0.1, 5.0); self._spin_grid.setSingleStep(0.1)
        self._spin_grid.setValue(1.0)
        self._spin_grid.valueChanged.connect(self._on_settings_changed)
        grid_row.addWidget(self._spin_grid)
        layout.addLayout(grid_row)

        layout.addStretch()
        return w

    # ── WebChannel ──────────────────────────────────────────────────────────

    def _setup_channel(self):
        self._bridge = VisualizerBridge(self._state, self)
        self._channel = QWebChannel(self)
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)
        # ── CACHE FIX: Cache-Buster an URL anhaengen, damit QWebEngineView die
        # HTML bei jedem Visualizer-Open frisch laedt ────────────────────────
        try:
            url = QUrl.fromLocalFile(HTML_PATH)
            url.setQuery(f"v={int(time.time() * 1000)}")
            self._view.load(url)
        except Exception as e:
            print(f"[Visualizer] HTML load error: {e}")
            self._view.load(QUrl.fromLocalFile(HTML_PATH))
        self._view.loadFinished.connect(self._on_load_finished)

        # Python <- JS bridge signals
        self._bridge.pyFixtureMoved.connect(self._on_fixture_moved_from_js)
        self._bridge.pyFixtureSelection.connect(self._on_fixture_selection_from_js)
        self._bridge.pyFixtureDeleted.connect(self._on_fixture_deleted_from_js)
        self._bridge.pyStageListChanged.connect(self._on_stage_list_from_js)
        self._bridge.pyStageSelection.connect(self._on_stage_selection_from_js)
        self._bridge.pyStageSaved.connect(self._on_stage_saved_from_js)
        self._bridge.pyBrightnessChanged.connect(self._on_brightness_from_js)

    def _on_load_finished(self, ok: bool):
        if not ok:
            return
        QTimer.singleShot(400, self._push_initial_state)

    def _apply_active_stage_from_state(self):
        """Setzt die in AppState gespeicherte Buehne (Preset-Key oder User-Name)
        als aktuelle Stage und synchronisiert die Combo-Auswahl."""
        name = getattr(self._state, "active_stage_name", "simple") or "simple"
        stage = None
        combo_kind = combo_name = None
        if name in DEFAULT_PRESETS:
            try:
                stage = DEFAULT_PRESETS[name]()
                combo_kind, combo_name = "default", name
            except Exception as e:
                print(f"[Visualizer] default stage '{name}' error: {e}")
        else:
            loaded = load_stage(name)
            if loaded:
                stage = loaded
                combo_kind, combo_name = "user", name
        if stage is None:
            stage = get_default_simple()
            combo_kind, combo_name = "default", "simple"
        self._current_stage = stage
        self._selected_stage_id = ""
        self._select_stage_in_combo(combo_kind, combo_name)
        self._apply_stage(self._current_stage)

    def _push_initial_state(self):
        try:
            self._bridge.push_settings(self._collect_settings())
            self._bridge.push_view_mode(self._combo_view.currentData() or "3D")
            self._bridge.push_edit_mode(self._combo_edit.currentData() or "view")
            self._apply_active_stage_from_state()
            self._bridge.requestFixtures()
            self._refresh_patch_list()
        except Exception as e:
            print(f"[Visualizer] _push_initial_state error: {e}")

    def _setup_update_timer(self):
        self._dmx_timer = QTimer(self)
        self._dmx_timer.timeout.connect(self._push_dmx_updates)
        self._dmx_timer.start(33)
        self._state.subscribe(self._on_state)

    def _push_dmx_updates(self):
        try:
            for fixture in self._state.get_patched_fixtures():
                if fixture.fid not in self._state.visualizer_positions:
                    continue
                if fixture.universe not in self._state.universes:
                    continue
                universe = self._state.universes[fixture.universe]
                channels = get_channels_for_patched(fixture)
                attrs: dict[str, int] = {}
                for ch in channels:
                    dmx_addr = fixture.address + ch.channel_number - 1
                    if 1 <= dmx_addr <= 512:
                        attrs[ch.attribute] = universe.get_channel(dmx_addr)
                self._bridge.push_dmx_update(fixture.fid, attrs)
        except Exception as e:
            print(f"[Visualizer] _push_dmx_updates error: {e}")

    # ── Fixture-Tab actions ─────────────────────────────────────────────────

    def _refresh_patch_list(self):
        self._patch_list.blockSignals(True)
        self._patch_list.clear()
        for f in self._state.get_patched_fixtures():
            mark = "[X] " if f.fid in self._state.visualizer_positions else "[ ] "
            item = QListWidgetItem(f"{mark}[{f.fid:03d}] {f.label} ({f.fixture_type})")
            item.setData(Qt.ItemDataRole.UserRole, f.fid)
            self._patch_list.addItem(item)
        count = len(self._state.visualizer_positions)
        self._lbl_info.setText(f"{count} Fixture(s) in Szene  |  {len(self._current_stage.elements)} Buehnen-Elemente")
        self._patch_list.blockSignals(False)

    def _on_patch_list_selected(self):
        item = self._patch_list.currentItem()
        if not item:
            return
        fid = item.data(Qt.ItemDataRole.UserRole)
        if fid in self._state.visualizer_positions:
            x, y, z = self._state.visualizer_positions[fid]
            self._suppress_property_signals = True
            try:
                self._spin_x.setValue(x)
                self._spin_y.setValue(y)
                self._spin_z.setValue(z)
            finally:
                self._suppress_property_signals = False

    def _place_selected(self):
        item = self._patch_list.currentItem()
        if not item:
            return
        fid = item.data(Qt.ItemDataRole.UserRole)
        x, y, z = self._spin_x.value(), self._spin_y.value(), self._spin_z.value()
        self._bridge.place_fixture_at(fid, x, y, z)
        self._refresh_patch_list()

    def _remove_selected(self):
        item = self._patch_list.currentItem()
        if not item:
            return
        fid = item.data(Qt.ItemDataRole.UserRole)
        self._bridge.remove_fixture_from_scene(fid)
        self._refresh_patch_list()

    def _on_fixture_pos_spin_changed(self, *_):
        if self._suppress_property_signals:
            return
        item = self._patch_list.currentItem()
        if not item:
            return
        fid = item.data(Qt.ItemDataRole.UserRole)
        if fid not in self._state.visualizer_positions:
            return
        x, y, z = self._spin_x.value(), self._spin_y.value(), self._spin_z.value()
        self._state.visualizer_positions[fid] = (x, y, z)
        self._bridge.push_apply_fixture_transform(fid, x, y, z, 0.0)

    def _clear_positions(self):
        for fid in list(self._state.visualizer_positions):
            self._bridge.remove_fixture_from_scene(fid)
        self._state.visualizer_positions.clear()
        self._refresh_patch_list()

    # ── Fixture-Bridge-Slots (JS -> Python) ─────────────────────────────────

    def _on_fixture_moved_from_js(self, fid: int, x: float, y: float, z: float):
        # Update spinner if this is the selected fixture
        item = self._patch_list.currentItem()
        if item and item.data(Qt.ItemDataRole.UserRole) == fid:
            self._suppress_property_signals = True
            try:
                self._spin_x.setValue(x)
                self._spin_y.setValue(y)
                self._spin_z.setValue(z)
            finally:
                self._suppress_property_signals = False

    def _on_fixture_selection_from_js(self, fids: list):
        if not fids:
            return
        # Highlight first one in list
        target = int(fids[0])
        for i in range(self._patch_list.count()):
            it = self._patch_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == target:
                self._patch_list.setCurrentItem(it)
                break

    def _on_fixture_deleted_from_js(self, fid: int):
        self._state.visualizer_positions.pop(fid, None)
        self._refresh_patch_list()

    # ── Stage-Tab actions ───────────────────────────────────────────────────

    def _reload_stage_combo(self):
        self._combo_stage.blockSignals(True)
        self._combo_stage.clear()
        # Defaults
        for key, label in [("simple", "Simple"), ("theatre", "Theatre"), ("rock", "Rock Concert")]:
            self._combo_stage.addItem(label, ("default", key))
        # User-saved
        saved = list_stages()
        if saved:
            self._combo_stage.insertSeparator(self._combo_stage.count())
            for name in saved:
                self._combo_stage.addItem(name, ("user", name))
        self._combo_stage.blockSignals(False)

    def _on_stage_combo_changed(self, idx: int):
        if idx < 0:
            return
        data = self._combo_stage.itemData(idx)
        if not data or not isinstance(data, tuple) or len(data) != 2:
            return
        kind, name = data
        if kind == "default":
            preset_fn = DEFAULT_PRESETS.get(name)
            if preset_fn:
                self._current_stage = preset_fn()
            else:
                print(f"[stage] unknown default preset: {name}")
                return
        elif kind == "user":
            loaded = load_stage(name)
            if loaded:
                self._current_stage = loaded
            else:
                print(f"[stage] load failed for user-stage: {name}")
                QMessageBox.warning(
                    self, "Laden fehlgeschlagen",
                    f"Buehne '{name}' konnte nicht geladen werden."
                )
                return
        else:
            return
        self._selected_stage_id = ""
        self._state.active_stage_name = name
        self._apply_stage(self._current_stage)
        self._refresh_patch_list()

    def _apply_stage(self, definition: StageDefinition):
        """Sende komplette Buehnen-Definition an JS."""
        try:
            self._bridge.push_stage_definition(definition)
        except Exception as e:
            print(f"[Visualizer] _apply_stage push error: {e}")
        self._refresh_stage_tree()

    def _refresh_stage_tree(self):
        # Aktuelle Selektion merken um sie nach Rebuild wiederherzustellen (T4.3)
        selected_id = self._selected_stage_id or ""
        # FLICKER-FIX: Painting komplett aussetzen waehrend Clear+Rebuild,
        # sonst sieht der User die leere Liste fuer einen Frame.
        self._stage_tree.setUpdatesEnabled(False)
        self._stage_tree.blockSignals(True)
        try:
            self._stage_tree.clear()
            type_labels = {
                "platform":  "Plattform",  "truss_h":  "Truss horiz.",
                "truss_v":   "Truss vert.", "wall":    "Wand",
                "led_wall":  "LED-Wand",   "speaker":  "Speaker",
                "audience":  "Publikum",   "dj_booth": "DJ-Booth",
            }
            for el in self._current_stage.elements:
                label_name = el.name or el.id
                type_label = type_labels.get(el.type, el.type)
                it = QTreeWidgetItem([type_label, label_name])
                it.setData(0, Qt.ItemDataRole.UserRole, el.id)
                self._stage_tree.addTopLevelItem(it)
            # Selektion wiederherstellen
            if selected_id:
                for i in range(self._stage_tree.topLevelItemCount()):
                    it = self._stage_tree.topLevelItem(i)
                    if it.data(0, Qt.ItemDataRole.UserRole) == selected_id:
                        self._stage_tree.setCurrentItem(it)
                        break
        finally:
            self._stage_tree.blockSignals(False)
            self._stage_tree.setUpdatesEnabled(True)

    def _add_stage_element(self, type_: str):
        # Pick reasonable defaults per type
        defaults = {
            "platform":  dict(x=0, y=0.2, z=0, w=6, h=0.4, d=4, color="#332520"),
            "truss_h":   dict(x=0, y=8, z=0, w=4, h=0.3, d=0.3, color="#999999"),
            "truss_v":   dict(x=0, y=2, z=0, w=0.3, h=4, d=0.3, color="#999999"),
            "wall":      dict(x=0, y=3, z=-5, w=10, h=6, d=0.2, color="#222230"),
            "led_wall":  dict(x=0, y=4, z=-5, w=8, h=4.5, d=0.15, color="#080820"),
            "speaker":   dict(x=-5, y=2.3, z=4, w=1.4, h=4.5, d=1.4, color="#111111"),
            "audience":  dict(x=0, y=0.05, z=8, w=12, h=0.1, d=8, color="#0c0c10"),
            "dj_booth":  dict(x=0, y=0.6, z=0, w=2.4, h=1.2, d=1.0, color="#1a1a25"),
        }
        kwargs = defaults.get(type_, {})
        type_label = dict(self.STAGE_TYPES).get(type_, type_)
        kwargs.setdefault("name", type_label)
        el = self._current_stage.add(type_, **kwargs)
        # Sicherstellen, dass wir in "Stage"-EditMode sind (sonst kann User
        # das neue Element nicht direkt anfassen)
        try:
            cur_mode = self._combo_edit.currentData() or "view"
            if cur_mode != "stage":
                # In stage-Modus wechseln (loest editModeChanged aus)
                for i in range(self._combo_edit.count()):
                    if self._combo_edit.itemData(i) == "stage":
                        self._combo_edit.setCurrentIndex(i)
                        break
        except Exception as e:
            print(f"[Visualizer] _add_stage_element mode-switch error: {e}")
        # Komplettes Stage-Update senden -> JS legt das neue Element an
        self._apply_stage(self._current_stage)
        # Auto-Selektion (sowohl im Tree als auch im JS) -> Drag/Resize sofort moeglich
        self._selected_stage_id = el.id
        for i in range(self._stage_tree.topLevelItemCount()):
            it = self._stage_tree.topLevelItem(i)
            if it.data(0, Qt.ItemDataRole.UserRole) == el.id:
                self._stage_tree.setCurrentItem(it)
                break
        try:
            self._bridge.push_select_stage_object(el.id)
        except Exception as e:
            print(f"[Visualizer] auto-select stage object error: {e}")

    def _selected_stage_element(self) -> Optional[StageElement]:
        it = self._stage_tree.currentItem()
        if not it:
            return None
        eid = it.data(0, Qt.ItemDataRole.UserRole)
        return self._current_stage.get(eid)

    def _on_stage_tree_selected(self):
        el = self._selected_stage_element()
        if not el:
            return
        self._suppress_property_signals = True
        try:
            self._stage_name_edit.setText(el.name)
            self._stage_spin_x.setValue(el.x)
            self._stage_spin_y.setValue(el.y)
            self._stage_spin_z.setValue(el.z)
            self._stage_spin_w.setValue(el.w)
            self._stage_spin_h.setValue(el.h)
            self._stage_spin_d.setValue(el.d)
            import math
            self._stage_spin_rot.setValue(math.degrees(el.rotation))
            self._stage_color_preview.setStyleSheet(
                f"background:{el.color}; border:1px solid #555;"
            )
            # Resize-Mode bei Element-Wechsel zuruecksetzen (Default = Verschieben)
            if hasattr(self, "_btn_resize_mode"):
                self._btn_resize_mode.blockSignals(True)
                self._btn_resize_mode.setChecked(False)
                self._btn_resize_mode.setText("Groesse anpassen")
                self._btn_resize_mode.blockSignals(False)
                try:
                    self._bridge.resizeModeSignal.emit(False)
                except Exception:
                    pass
            self._bridge.push_select_stage_object(el.id)
        finally:
            self._suppress_property_signals = False

    def _on_stage_property_changed(self, *_):
        if self._suppress_property_signals:
            return
        el = self._selected_stage_element()
        if not el:
            return
        import math
        el.name     = self._stage_name_edit.text()
        el.x        = self._stage_spin_x.value()
        el.y        = self._stage_spin_y.value()
        el.z        = self._stage_spin_z.value()
        el.w        = self._stage_spin_w.value()
        el.h        = self._stage_spin_h.value()
        el.d        = self._stage_spin_d.value()
        el.rotation = math.radians(self._stage_spin_rot.value())

        # Gezieltes Update an JS senden (kein kompletter Rebuild -> kein Selection-Swap)
        try:
            payload = json.dumps({
                "id": el.id,
                "position": {"x": el.x, "y": el.y, "z": el.z},
                "size":     {"x": el.w, "y": el.h, "z": el.d},
                "rotation": el.rotation,
                "color":    el.color,
                "name":     el.name,
            })
            self._bridge.updateStageObject.emit(payload)
        except Exception as e:
            print(f"[Visualizer] update stage object error: {e}")

        # Tree-Label aktualisieren (Name kann sich geaendert haben) ohne Rebuild
        item = self._stage_tree.currentItem()
        if item:
            item.setText(1, el.name or el.id)

    def _on_resize_mode_toggled(self, checked: bool):
        """Toggle Resize-Handles im JS. AUS = nur Verschieben moeglich (default)."""
        try:
            self._bridge.resizeModeSignal.emit(bool(checked))
            if checked:
                self._btn_resize_mode.setText("Groesse anpassen: AN")
            else:
                self._btn_resize_mode.setText("Groesse anpassen")
        except Exception as e:
            print(f"[Visualizer] resize toggle error: {e}")

    def _on_pick_stage_color(self):
        el = self._selected_stage_element()
        if not el:
            return
        col = QColorDialog.getColor(QColor(el.color), self, "Element-Farbe")
        if col.isValid():
            el.color = col.name()
            self._stage_color_preview.setStyleSheet(
                f"background:{el.color}; border:1px solid #555;"
            )
            # Gezielter Farb-Update (kein Rebuild)
            try:
                self._bridge.updateStageObject.emit(json.dumps({
                    "id": el.id, "color": el.color,
                }))
            except Exception as e:
                print(f"[Visualizer] update stage color error: {e}")

    def _delete_selected_stage_element(self):
        el = self._selected_stage_element()
        if not el:
            return
        self._current_stage.remove(el.id)
        self._apply_stage(self._current_stage)

    def _on_save_stage(self):
        name, ok = QInputDialog.getText(
            self, "Buehne speichern", "Name:",
            QLineEdit.EchoMode.Normal, self._current_stage.name
        )
        if not ok or not name.strip():
            return
        self._current_stage.name = name.strip()
        path = save_stage(self._current_stage)
        if path:
            QMessageBox.information(self, "Gespeichert", f"Buehne '{name}' gespeichert.")
            # Combo neu aufbauen UND die soeben gespeicherte Buehne auswaehlen
            self._reload_stage_combo()
            self._select_stage_in_combo("user", name.strip())
            self._state.active_stage_name = name.strip()
        else:
            QMessageBox.warning(self, "Fehler", "Konnte Buehne nicht speichern.")

    def _select_stage_in_combo(self, kind: str, name: str):
        """Selektiert eine bestimmte Buehne im Combo (ohne Signal-Loop)."""
        try:
            self._combo_stage.blockSignals(True)
            for i in range(self._combo_stage.count()):
                data = self._combo_stage.itemData(i)
                if data and isinstance(data, tuple) and data == (kind, name):
                    self._combo_stage.setCurrentIndex(i)
                    break
        finally:
            self._combo_stage.blockSignals(False)

    def _on_new_stage(self):
        name, ok = QInputDialog.getText(
            self, "Neue Buehne", "Name:",
            QLineEdit.EchoMode.Normal, "Neue Buehne"
        )
        if not ok or not name.strip():
            return
        # NEW STAGE FIX: komplett leeres Stage-Objekt anlegen, JS-Scene leeren
        self._current_stage = StageDefinition(name=name.strip())
        self._selected_stage_id = ""
        # JS explizit eine LEERE Stage senden (clearStageObjects wird in JS gerufen)
        try:
            self._bridge.stageLoaded.emit(json.dumps({
                "name": name.strip(),
                "objects": [],
                "fixtures": [],
            }))
        except Exception as e:
            print(f"[Visualizer] _on_new_stage stageLoaded error: {e}")
        # Tree-Panel und Patch-Liste neu aufbauen
        self._refresh_stage_tree()
        self._refresh_patch_list()
        # Combo-Auswahl auf -1 (keine), damit User die neue Buehne nach Save findet
        self._combo_stage.blockSignals(True)
        self._combo_stage.setCurrentIndex(-1)
        self._combo_stage.blockSignals(False)

    def _on_delete_stage(self):
        data = self._combo_stage.currentData()
        if not data or data[0] != "user":
            QMessageBox.information(
                self, "Hinweis", "Nur gespeicherte Buehnen koennen geloescht werden."
            )
            return
        name = data[1]
        if QMessageBox.question(
            self, "Loeschen", f"Buehne '{name}' loeschen?"
        ) != QMessageBox.StandardButton.Yes:
            return
        delete_stage(name)
        self._reload_stage_combo()

    # ── Stage-Bridge-Slots (JS -> Python) ───────────────────────────────────

    def _on_stage_list_from_js(self, items: list):
        """Wird ausgeloest wenn JS Stage-Objekte aendert (z.B. Drag im 3D-View).
        Aktualisiert nur die Datenmodelle - KEIN Tree-Rebuild (verhindert Selection-Swap),
        ausser ein Element wurde hinzugefuegt ODER entfernt."""
        tree_needs_rebuild = False
        js_ids = set()
        for it in items:
            sid = it.get("id")
            if not sid:
                continue
            js_ids.add(sid)
            el = self._current_stage.get(sid)
            if el is None:
                # Neues Element aus JS - in Python-Modell anlegen
                from src.core.stage.stage_definition import StageElement
                pos = it.get("position") or {}
                size = it.get("size") or {}
                el = StageElement(
                    id=sid,
                    type=it.get("type", "platform"),
                    x=float(pos.get("x", 0)), y=float(pos.get("y", 0)), z=float(pos.get("z", 0)),
                    w=float(size.get("x", 1)), h=float(size.get("y", 1)), d=float(size.get("z", 1)),
                    rotation=float(it.get("rotation", 0)),
                    color=it.get("color", "#888888"),
                    name=it.get("name", ""),
                )
                self._current_stage.elements.append(el)
                tree_needs_rebuild = True
                continue
            pos = it.get("position") or {}
            size = it.get("size") or {}
            el.x = float(pos.get("x", el.x))
            el.y = float(pos.get("y", el.y))
            el.z = float(pos.get("z", el.z))
            el.w = float(size.get("x", el.w))
            el.h = float(size.get("y", el.h))
            el.d = float(size.get("z", el.d))
            el.rotation = float(it.get("rotation", el.rotation))
            el.color = it.get("color", el.color)

        # Elemente die nur in Python existieren (in JS via Hotkey/FAB geloescht) entfernen
        py_ids_to_remove = [e.id for e in self._current_stage.elements if e.id not in js_ids]
        if py_ids_to_remove:
            for pid in py_ids_to_remove:
                self._current_stage.remove(pid)
                if self._selected_stage_id == pid:
                    self._selected_stage_id = ""
            tree_needs_rebuild = True

        if tree_needs_rebuild:
            self._refresh_stage_tree()

        # Properties-Panel updaten OHNE Tree-Rebuild
        cur = self._selected_stage_element()
        if cur:
            self._suppress_property_signals = True
            try:
                import math
                self._stage_spin_x.setValue(cur.x)
                self._stage_spin_y.setValue(cur.y)
                self._stage_spin_z.setValue(cur.z)
                self._stage_spin_w.setValue(cur.w)
                self._stage_spin_h.setValue(cur.h)
                self._stage_spin_d.setValue(cur.d)
                self._stage_spin_rot.setValue(math.degrees(cur.rotation))
            finally:
                self._suppress_property_signals = False

    def _on_stage_selection_from_js(self, sid: str):
        self._selected_stage_id = sid or ""
        if not sid:
            return
        for i in range(self._stage_tree.topLevelItemCount()):
            it = self._stage_tree.topLevelItem(i)
            if it.data(0, Qt.ItemDataRole.UserRole) == sid:
                self._stage_tree.setCurrentItem(it)
                break

    def _on_stage_saved_from_js(self, data: dict):
        # Optional: JS-getriggertes Save (z.B. via Tastenkuerzel). Falls Name vorhanden:
        name = data.get("name") or "CustomStage"
        sd = StageDefinition.from_dict(data)
        sd.name = name
        save_stage(sd)
        self._reload_stage_combo()

    # ── View / Edit Mode ────────────────────────────────────────────────────

    def _on_view_mode_changed(self, idx: int):
        mode = self._combo_view.itemData(idx) or "3D"
        self._bridge.push_view_mode(mode)

    def _on_edit_mode_changed(self, idx: int):
        mode = self._combo_edit.itemData(idx) or "view"
        self._bridge.push_edit_mode(mode)
        # Switch right-panel tab to match
        if mode == "stage":
            self._tabs.setCurrentIndex(1)
        elif mode == "edit":
            self._tabs.setCurrentIndex(0)

    def _reset_camera(self):
        self._bridge.cameraReset.emit()

    # ── Settings ────────────────────────────────────────────────────────────

    def _collect_settings(self) -> dict:
        return {
            "beamOpacity":     self._sld_opacity.value() / 100.0,
            "showCones":       self._chk_cones.isChecked(),
            "showFloorSpots":  self._chk_floor.isChecked(),
            "showFog":         self._chk_fog.isChecked(),
            "snapToGrid":      self._chk_snap.isChecked(),
            "gridStep":        float(self._spin_grid.value()),
            "brightness":      self._sld_brightness.value() / 100.0,
            "autoBrightness":  self._chk_auto_brightness.isChecked(),
        }

    def _on_settings_changed(self, *_):
        try:
            self._lbl_opacity.setText(f"{self._sld_opacity.value()}%")
            self._bridge.push_settings(self._collect_settings())
        except Exception as e:
            print(f"[Visualizer] _on_settings_changed error: {e}")

    def _on_brightness_changed(self, value: int):
        """User bewegt den Helligkeits-Slider - sendet Manual-Override an JS."""
        try:
            self._lbl_brightness.setText(f"{value}%")
            # Direkter Manual-Setter im JS (verhindert Auto-Override beim Mode-Wechsel)
            self._bridge.brightnessSignal.emit(value / 100.0)
        except Exception as e:
            print(f"[Visualizer] _on_brightness_changed error: {e}")

    def _on_auto_brightness_toggled(self, checked: bool):
        try:
            self._bridge.push_settings(self._collect_settings())
            if checked:
                # Auto-Mode wieder aktivieren
                self._bridge.brightnessAutoSignal.emit()
        except Exception as e:
            print(f"[Visualizer] _on_auto_brightness_toggled error: {e}")

    def _on_auto_brightness_apply(self):
        """User klickt 'Auto-Werte anwenden' - reset Manual-Override und triggere Mode-Brightness."""
        try:
            self._bridge.brightnessAutoSignal.emit()
        except Exception as e:
            print(f"[Visualizer] _on_auto_brightness_apply error: {e}")

    def _on_brightness_from_js(self, value: float):
        """JS-Auto-Brightness updated den Slider stumm (ohne Signal-Loop)."""
        try:
            v = int(round(max(0.0, min(1.0, value)) * 100))
            self._sld_brightness.blockSignals(True)
            self._sld_brightness.setValue(v)
            self._lbl_brightness.setText(f"{v}%")
            self._sld_brightness.blockSignals(False)
        except Exception as e:
            print(f"[Visualizer] _on_brightness_from_js error: {e}")

    def _on_state(self, event: str, _data):
        if event == "patch_changed":
            self._refresh_patch_list()
        elif event == "show_loaded":
            # Neue Show geladen -> Stage + Fixture-Positionen aus AppState uebernehmen
            try:
                self._apply_active_stage_from_state()
                self._bridge.requestFixtures()
                self._refresh_patch_list()
            except Exception as e:
                print(f"[Visualizer] show_loaded handling error: {e}")
