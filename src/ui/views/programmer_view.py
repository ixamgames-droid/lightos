"""Programmer-Ansicht - Live-Bearbeitung von Fixture-Attributen.

Layout:
  - Links:    Fixture-Liste + Quick-Buttons
  - Mitte:    Attribut-Gruppen-Tabs (Intensity / Color / Position / Beam / Gobo / Effect)
  - Toolbar:  Highlight, Lowlight, Clear, Copy, Paste, Undo, Redo + Fan / Color / Position
"""
from __future__ import annotations
import copy
import json
import os
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSlider, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QGroupBox, QScrollArea, QFrame,
    QTabWidget, QToolButton, QSizePolicy, QMessageBox, QDialog, QSplitter,
    QStackedWidget, QButtonGroup, QInputDialog, QRadioButton, QComboBox,
    QWhatsThis
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from src.core.app_state import (
    get_state, AppState, get_channels_for_patched, resolve_attr_channels)
from src.core.database.models import PatchedFixture, FixtureChannel

# ── UI-Praeferenzen (Layout-Modus, eingeklappte Zonen) ───────────────────────
_PREFS_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS"
)
_PREFS_PATH = os.path.join(_PREFS_DIR, "ui_prefs.json")


def _load_prefs() -> dict:
    try:
        with open(_PREFS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def programmer_to_scene_values(filtered_programmer: dict, fixtures) -> list[tuple[int, int, int]]:
    """Wandelt einen (ggf. attribut-gefilterten) Programmer-Stand
    ``{fid: {attr: val}}`` in Scene-Werte ``(fid, channel_number, value)`` um —
    via Attribut→Kanal-Aufloesung je Fixture (get_channels_for_patched).

    Nur die im Programmer enthaltenen Attribute landen in der Szene; alle anderen
    Kanaele bleiben "leer" (werden von der Szene nicht angefasst) — Grundlage fuer
    das Stapeln attribut-getrennter Ebenen (Farbe + Dimmer kombinieren)."""
    patch = {}
    for f in fixtures:
        fid = getattr(f, "fid", None)
        if fid is not None:
            patch[int(fid)] = f
    out: list[tuple[int, int, int]] = []
    for fid, attrs in (filtered_programmer or {}).items():
        try:
            fx = patch.get(int(fid))
        except (TypeError, ValueError):
            continue
        if fx is None or not isinstance(attrs, dict):
            continue
        # Mehrkopf (X-6): vorkommens-bewusste Aufloesung statt eines
        # ``{attribute: channel}``-Dicts. Letzteres KOLLIDIERT bei wiederholten
        # Attributen (zwei ``color_r`` beim Spider) — nur das letzte Vorkommen
        # ueberlebt, ``color_r#1`` verfaellt und der Kopf-0-Wert ruschte auf den
        # ZWEITEN Kanal. resolve_attr_channels mappt jeden ``attr``/``attr#N`` auf
        # sein eigenes Kanal-Vorkommen (gleiche Logik wie _flush_programmer_to_dmx).
        for ch_no, _mkey, val in resolve_attr_channels(get_channels_for_patched(fx), attrs):
            try:
                out.append((int(fid), int(ch_no), max(0, min(255, int(val)))))
            except (TypeError, ValueError):
                continue
    return out


def _save_prefs(updates: dict) -> None:
    data = _load_prefs()
    data.update(updates)
    try:
        os.makedirs(_PREFS_DIR, exist_ok=True)
        with open(_PREFS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[programmer_view] save prefs error: {e}")


# U-3 (P-08): Hilfetexte fuer den Hilfe-Modus (Qt "What's This?"). Per setWhatsThis
# an die Bedienelemente gehaengt; der Hilfe-Modus zeigt sie statt die Aktion auszuloesen.
_PROGRAMMER_HELP = {
    "Highlight": "Setzt die ausgewählten Fixtures vorübergehend auf volle "
                 "Helligkeit, um sie auf der Bühne zu lokalisieren.",
    "Lowlight": "Dimmt alle NICHT ausgewählten Fixtures ab, damit die aktuelle "
                "Auswahl hervorsticht.",
    "Clear": "Leert den Programmer (alle hier manuell gesetzten Werte). "
             "Gespeicherte Funktionen, Cues und Snapshots bleiben unberührt.",
    "Copy": "Kopiert die aktuellen Programmer-Werte in die Zwischenablage.",
    "Paste": "Fügt zuvor kopierte Programmer-Werte wieder ein.",
    "Undo": "Macht die letzte Programmer-Änderung rückgängig.",
    "Redo": "Stellt eine rückgängig gemachte Programmer-Änderung wieder her.",
    "Color Tool...": "Öffnet den Farbwähler als eigenes, frei platzierbares Fenster "
                     "für die ausgewählten Fixtures.",
    "Position Tool...": "Öffnet das Pan/Tilt-Pad für Moving Heads als eigenes Fenster "
                        "(Position live setzen, inkl. Fine-Kanäle).",
    "Fan...": "Verteilt einen Wert fächerförmig über die ausgewählten Fixtures "
              "(z. B. Pan-Fächer oder Farbverlauf über die Gruppe).",
}

# Bestehende Attribut-Konstanten (Kompatibilitaet)
COLOR_ATTRS = {"color_r", "color_g", "color_b", "color_w", "color_a", "color_uv"}
PAN_TILT_ATTRS = {"pan", "tilt", "pan_fine", "tilt_fine"}
INTENSITY_ATTRS = {"intensity", "dimmer", "master"}

# Attribut-Gruppen + Klassifikation: kanonisch aus src/core/attr_groups,
# gemeinsam mit dem Save-Kanal-Dialog (snap_file_panel) -> kein Auseinanderdriften
# mehr (siehe Bug E: Strobe wurde im Save-Dialog faelschlich "Beam" genannt).
from src.core.attr_groups import ATTR_GROUPS, classify_attr as _classify_attribute


class ProgrammerView(QWidget):
    """Hauptansicht des Programmers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: AppState = get_state()
        self._selected_fids: list[int] = []
        self._clipboard: dict[int, dict[str, int]] = {}
        self._state.subscribe(self._on_state_change)
        self._setup_ui()  # baut Body + befuellt Listen/Editor aus dem State
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe_widget(SyncEvent.REFRESH_ALL, self, lambda *_: self._sync_refresh())
            sync.subscribe_widget(SyncEvent.PATCH_CHANGED, self, lambda *_: self._sync_refresh())
            # Abschnitt 1: neue/geaenderte Funktionen + Gruppen erscheinen sofort,
            # ohne manuelles Neuladen (kein Refresh-Button als Hauptloesung).
            sync.subscribe_widget(SyncEvent.FUNCTION_CHANGED, self, lambda *_: self._refresh_effects_list())
            sync.subscribe_widget(SyncEvent.GROUP_CHANGED, self, lambda *_: self._refresh_group_list())
            # P7: Slider folgen externen Programmer-Aenderungen live (Quick-
            # Colors, Paletten, Snaps, VC/MIDI). Kurzer Coalescing-Timer, damit
            # ein Farbklick (mehrere set_programmer_value-Emits) nur EINEN
            # Refresh ausloest.
            self._slider_sync_timer = QTimer(self)
            self._slider_sync_timer.setSingleShot(True)
            self._slider_sync_timer.setInterval(30)
            self._slider_sync_timer.timeout.connect(self._refresh_sliders_from_state)
            sync.subscribe_widget(SyncEvent.PROGRAMMER_CHANGED, self,
                                  lambda *_: self._slider_sync_timer.start())
        except Exception as e:
            print(f"[programmer_view] sync subscribe error: {e}")

    # ── Public Helpers ───────────────────────────────────────────────────────

    def get_selected_fids(self) -> list[int]:
        return list(self._selected_fids)

    def _sync_refresh(self):
        try:
            self._refresh_fixture_list()
            self._refresh_group_list()
            self._rebuild_attr_editor()
            self._refresh_effects_list()
        except Exception as e:
            print(f"[programmer_view] sync_refresh error: {e}")

    def _refresh_sliders_from_state(self):
        """P7: Alle sichtbaren AttributeSlider aus dem Programmer-State neu
        laden. _load_current_value() blockt Signale (keine Echo-Loops);
        Slider, die der Nutzer gerade zieht, werden nicht angefasst."""
        try:
            sliders = self.findChildren(AttributeSlider)
        except RuntimeError:
            return  # View bereits zerstoert
        for s in sliders:
            try:
                if s._slider.isSliderDown():
                    continue
                s._load_current_value()
            except Exception:
                continue

    # ── UI Build ─────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(8, 8, 8, 8)
        self._root.setSpacing(6)
        self._layout_mode = _load_prefs().get("programmer_layout", "zones")
        self._body: QWidget | None = None
        self._build_toolbar()
        self._build_body()

    def _build_toolbar(self):
        """Gemeinsame Toolbar (beide Layouts) inkl. Layout-Umschalter."""
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
            b.setWhatsThis(_PROGRAMMER_HELP.get(label, ""))   # U-3: Hilfe-Modus
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
            b.setWhatsThis(_PROGRAMMER_HELP.get(label, ""))   # U-3
            tb.addWidget(b)

        tb.addStretch(1)

        # U-3 (P-08): Hilfe-Modus. Aktiviert Qts "What's This?" — der naechste Klick
        # auf ein Bedienelement zeigt dessen Hilfetext (setWhatsThis) als Sprechblase,
        # statt die Aktion auszuloesen. Esc beendet den Modus.
        self._btn_help = QPushButton("?")
        self._btn_help.setFixedHeight(26)
        self._btn_help.setFixedWidth(30)
        self._btn_help.setToolTip(
            "Hilfe-Modus: danach auf ein Bedienelement klicken, um seine "
            "Erklärung zu sehen (Esc beendet)."
        )
        self._btn_help.setWhatsThis(
            "Hilfe-Modus. Klicke nach dem Aktivieren ein beliebiges Bedienelement "
            "an, um zu erfahren, was es tut."
        )
        self._btn_help.clicked.connect(lambda: QWhatsThis.enterWhatsThisMode())
        tb.addWidget(self._btn_help)

        self._btn_layout = QPushButton()
        self._btn_layout.setFixedHeight(26)
        self._btn_layout.setToolTip("Programmer-Layout umschalten (Klassisch / Zonen)")
        self._btn_layout.setWhatsThis(
            "Schaltet zwischen dem klassischen Programmer-Layout und dem "
            "5-Zonen-Layout um (links wählen · Mitte programmieren · rechts "
            "Bibliothek · unten Vorschau)."
        )
        self._btn_layout.clicked.connect(self._toggle_layout)
        self._update_layout_button()
        tb.addWidget(self._btn_layout)

        self._root.addLayout(tb)

    def _update_layout_button(self):
        self._btn_layout.setText(
            "Layout: Zonen" if self._layout_mode == "zones" else "Layout: Klassisch"
        )

    def _toggle_layout(self):
        self._layout_mode = "zones" if self._layout_mode == "classic" else "classic"
        self._update_layout_button()
        _save_prefs({"programmer_layout": self._layout_mode})
        self._build_body()

    def _build_body(self):
        """(Re)baut den Body-Bereich gemaess Layout-Modus. Sicher beim Umschalten,
        da aller Zustand in self/AppState liegt und die Widgets aus dem State
        refreshen."""
        if self._body is not None:
            self._root.removeWidget(self._body)
            self._body.deleteLater()
        # Zonen-spezifische Referenzen invalidieren (werden ggf. neu erzeugt).
        self._tile_preview = None
        self._effects_list = None
        self._body = QWidget()
        self._root.addWidget(self._body, stretch=1)
        if self._layout_mode == "zones":
            self._build_zones(self._body)
        else:
            self._build_classic(self._body)
        # Inhalte aus dem State befuellen.
        self._refresh_fixture_list()
        self._refresh_group_list()
        self._rebuild_attr_editor()

    # ── Gemeinsame Widget-Erzeuger ───────────────────────────────────────────

    def _make_fixture_panel(self) -> QWidget:
        """LINKS: Fixture-Liste + Alle/Keine + Gruppen-Box (LAYOUT-02)."""
        left = QVBoxLayout()
        hdr = QLabel("Geräte")
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

        grp_box = QGroupBox("Gruppen")
        grp_layout = QVBoxLayout(grp_box)
        grp_layout.setContentsMargins(4, 6, 4, 4)
        grp_layout.setSpacing(4)
        # F-1: Such-/Filterfeld fuer die Gruppen-Liste (filtert nach Name/Ordner).
        self._group_search = QLineEdit()
        self._group_search.setPlaceholderText("Gruppe suchen…")
        self._group_search.setClearButtonEnabled(True)
        self._group_search.setStyleSheet("font-size: 11px; padding: 2px 4px;")
        self._group_search.textChanged.connect(lambda *_: self._refresh_group_list())
        grp_layout.addWidget(self._group_search)
        self._group_list = QListWidget()
        self._group_list.setMaximumHeight(130)
        self._group_list.itemClicked.connect(self._on_group_clicked)
        self._group_list.itemDoubleClicked.connect(self._on_group_add_clicked)
        grp_layout.addWidget(self._group_list)
        grp_hint = QLabel("Klick = Gruppe wählen · Doppelklick = zur Auswahl addieren")
        grp_hint.setWordWrap(True)
        grp_hint.setStyleSheet("color: #888; font-size: 10px;")
        grp_layout.addWidget(grp_hint)
        left.addWidget(grp_box)

        left_w = QWidget()
        left_w.setLayout(left)
        return left_w

    def _make_attr_area(self) -> QWidget:
        """Einheitliche Tab-Leiste (WP-5/Abschnitt 7).

        Ersetzt die fruehere Doppel-Navigation (obere Kategorie-Leiste + untere
        Attribut-Tabs) durch EINE Tab-Leiste:
          Attribut-Tabs: Intensity · Color · Position · Weitere
            (Weitere buendelt Beam + Gobo + Effect + Other — keine Doppelungen).
          Funktions-Tabs: Helper (Auto-Programm/Assistent + Effektliste) · EFX ·
            Matrix · Paletten.
        Selektions-Label + Farb-Vorschau bleiben darueber. Oben in der Toolbar
        bleiben nur Color-/Position-/Fan-Tool.
        """
        area = QWidget()
        al = QVBoxLayout(area)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(4)

        self._lbl_selection = QLabel("Kein Gerät ausgewählt")
        self._lbl_selection.setObjectName("label_header")
        al.addWidget(self._lbl_selection)

        self._color_preview = ColorPreview([], self._state)
        al.addWidget(self._color_preview)

        # Gruppen-Modus-Leiste (M5.2): Linked / Einzeln / Relativ + Fixture-Wahl.
        self._group_mode = _load_prefs().get("programmer_group_mode", "linked")
        # Farb-Kopf-Modus (Spider & Co.): "sync" = ein Regler je Farbe treibt alle
        # Koepfe gemeinsam; "separate" = ein Regler je Kopf (linke/rechte Bar usw.).
        self._color_head_mode = _load_prefs().get(
            "programmer_color_head_mode", "sync")
        self._active_fixture_idx = 0
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Gruppe:"))
        self._mode_btn_group = QButtonGroup(self)
        for label, key, tip in (
            ("Linked", "linked", "Ein Regler wirkt auf alle Geräte gleich"),
            ("Einzeln", "individual", "Nur das gewählte Fixture ändern"),
            ("Relativ", "relative", "Relative Änderung — Unterschiede bleiben erhalten"),
        ):
            rb = QRadioButton(label)
            rb.setToolTip(tip)
            rb.setChecked(self._group_mode == key)
            rb.toggled.connect(lambda chk, k=key: chk and self._set_group_mode(k))
            self._mode_btn_group.addButton(rb)
            mode_row.addWidget(rb)
        self._fixture_combo = QComboBox()
        self._fixture_combo.setToolTip("Aktives Fixture im Einzelmodus")
        self._fixture_combo.setEnabled(self._group_mode == "individual")
        self._fixture_combo.currentIndexChanged.connect(self._on_active_fixture_changed)
        mode_row.addWidget(self._fixture_combo, stretch=1)
        al.addLayout(mode_row)

        self._main_tabs = QTabWidget()
        self._main_tabs.setTabPosition(QTabWidget.TabPosition.North)

        # Attribut-Tabs: je ein Container, dessen Inhalt _rebuild_attr_editor
        # abhaengig von der Auswahl neu befuellt. "Weitere" = Beam+Gobo+Effect+Other.
        self._attr_group_tabs: dict[str, QWidget] = {}
        for label, key in (("Intensity", "Intensity"), ("Color", "Color"),
                           ("Position", "Position"), ("Gobo", "Gobo"),
                           ("Weitere", "Weitere")):
            cont = QWidget()
            cl = QVBoxLayout(cont)
            cl.setContentsMargins(0, 0, 0, 0)
            self._main_tabs.addTab(cont, label)
            self._attr_group_tabs[key] = cont
        # Gobo-Tab nur sichtbar, wenn das Geraet Gobos hat (M2.1).
        self._gobo_tab_index = self._main_tabs.indexOf(self._attr_group_tabs["Gobo"])
        self._main_tabs.setTabVisible(self._gobo_tab_index, False)

        # Mapping-Tab (Kanal-Mapping, M-Map): bildet eine Live-Position (Tilt/Pan/
        # X-Y) auf beliebige Ziel-Kanaele ab. Nur sichtbar, wenn die Auswahl
        # Pan/Tilt hat (Moving Heads / Spider) — gesetzt in _rebuild_attr_editor.
        self._mapping_page = self._make_mapping_page()
        self._main_tabs.addTab(self._mapping_page, "Mapping")
        self._mapping_tab_index = self._main_tabs.indexOf(self._mapping_page)
        self._main_tabs.setTabVisible(self._mapping_tab_index, False)

        # Funktions-Tabs (einmalig gebaut).
        self._main_tabs.addTab(self._make_effects_page(), "Helper")
        self._main_tabs.addTab(self._make_efx_page(), "EFX")
        # F-1: Matrix-Tab-Index merken, damit ein Gruppenklick direkt dorthin springt.
        self._rgb_page = self._make_rgb_page()
        self._main_tabs.addTab(self._rgb_page, "Matrix")
        self._matrix_tab_index = self._main_tabs.indexOf(self._rgb_page)
        self._main_tabs.addTab(self._make_palette_page(), "Paletten")

        al.addWidget(self._main_tabs, stretch=1)
        return area

    def _make_snap_panel(self) -> QWidget:
        """RECHTS: Snap-/Datei-Browser (LAYOUT-04)."""
        try:
            from src.ui.views.snap_file_panel import SnapFilePanel
            self._snap_file_panel = SnapFilePanel()
        except Exception as e:
            print(f"[programmer_view] snap_file_panel load error: {e}")
            self._snap_file_panel = QWidget()
        return self._snap_file_panel

    # ── Klassisches Layout ────────────────────────────────────────────────────

    def _build_classic(self, container: QWidget):
        body = QHBoxLayout(container)
        body.setContentsMargins(0, 0, 0, 0)

        left_w = self._make_fixture_panel()
        left_w.setFixedWidth(220)
        body.addWidget(left_w)

        right_top = self._make_attr_area()
        snap = self._make_snap_panel()

        right_splitter = QSplitter(Qt.Orientation.Horizontal)
        right_splitter.addWidget(right_top)
        right_splitter.addWidget(snap)
        right_splitter.setSizes([760, 320])
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 1)
        right_splitter.setChildrenCollapsible(False)
        body.addWidget(right_splitter, stretch=1)

    # ── 5-Zonen-Layout (LAYOUT-01) ─────────────────────────────────────────────

    def _build_zones(self, container: QWidget):
        outer = QHBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        h = QSplitter(Qt.Orientation.Horizontal)

        # LINKS
        left_w = self._make_fixture_panel()
        left_w.setMaximumWidth(300)
        h.addWidget(left_w)

        # CENTER: [ einheitliche Tab-Leiste (oben) | Fixture-Vorschau (unten) ]
        center = QSplitter(Qt.Orientation.Vertical)
        center.addWidget(self._make_attr_area())
        try:
            from src.ui.widgets.fixture_tile_preview import FixtureTilePreview
            self._tile_preview = FixtureTilePreview()
            self._tile_preview.set_collapsed(
                _load_prefs().get("programmer_bottom_collapsed", False)
            )
            self._tile_preview.collapsed_changed.connect(self._on_bottom_collapsed)
            center.addWidget(self._tile_preview)
        except Exception as e:
            print(f"[programmer_view] tile preview load error: {e}")
        center.setStretchFactor(0, 4)
        center.setStretchFactor(1, 1)
        center.setSizes([520, 160])

        # RECHTS-Spalte: Snap-Browser (Effekt-Mini-Vorschau entfernt, I2.7)
        right = self._make_snap_panel()

        h.addWidget(center)
        h.addWidget(right)
        h.setSizes([220, 640, 320])
        h.setStretchFactor(1, 1)
        h.setChildrenCollapsible(False)
        outer.addWidget(h)

    # _make_mitte/_on_category/_select_attr_tab wurden entfernt (WP-5/Abschnitt 7):
    # die einheitliche Tab-Leiste (_make_attr_area) ersetzt die fruehere
    # Doppel-Navigation (obere Kategorie-Leiste + untere Attribut-Tabs).

    def _make_effects_page(self) -> QWidget:
        """Effekte-Seite: Assistent + eigene Effekte anlegen + Liste mit Start/Stop."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        create_row = QHBoxLayout()
        btn = QPushButton("Effekt-Assistent...")
        btn.clicked.connect(self._open_effect_wizard)
        create_row.addWidget(btn)
        b_scene = QPushButton("+ Szene")
        b_scene.setToolTip("Neue Szene anlegen und direkt bearbeiten")
        b_scene.clicked.connect(lambda: self._new_effect("scene"))
        create_row.addWidget(b_scene)
        b_chaser = QPushButton("+ Chaser")
        b_chaser.setToolTip("Neuen Chaser anlegen und direkt bearbeiten")
        b_chaser.clicked.connect(lambda: self._new_effect("chaser"))
        create_row.addWidget(b_chaser)
        b_capture = QPushButton("Programmer → Szene")
        b_capture.setToolTip(
            "Aktuellen Programmer als Szene speichern — mit Auswahl, WELCHE "
            "Attribut-Gruppen (nur Farbe / nur Dimmer / …) gespeichert werden.\n"
            "So entstehen kombinierbare Bausteine (z. B. eine reine Farb-Szene)."
        )
        b_capture.clicked.connect(self._save_as_scene)
        create_row.addWidget(b_capture)
        create_row.addStretch(1)
        v.addLayout(create_row)
        self._effects_list = QListWidget()
        self._effects_list.itemDoubleClicked.connect(self._on_effect_toggle)
        v.addWidget(self._effects_list, stretch=1)
        row = QHBoxLayout()
        b_start = QPushButton("Start")
        b_start.clicked.connect(self._effect_start)
        b_stop = QPushButton("Stop")
        b_stop.clicked.connect(self._effect_stop)
        row.addWidget(b_start)
        row.addWidget(b_stop)
        row.addStretch(1)
        v.addLayout(row)
        self._refresh_effects_list()
        return w

    def _make_efx_page(self) -> QWidget:
        try:
            from src.ui.views.efx_view import EfxView
            # M0.1: eingebettet folgt EFX automatisch der Programmer-Auswahl
            # (analog zur RGB-Matrix nebenan).
            self._embedded_efx = EfxView(follow_selection=True)
            return self._embedded_efx
        except Exception as e:
            print(f"[programmer_view] efx embed error: {e}")
            return QLabel(f"EFX nicht verfügbar: {e}")

    def _make_mapping_page(self) -> QWidget:
        """Kanal-Mapping-Editor eingebettet (folgt der Auswahl, M-Map)."""
        try:
            from src.ui.widgets.mapped_channel_editor import MappedChannelEditor
            self._embedded_mapping = MappedChannelEditor()
            return self._embedded_mapping
        except Exception as e:
            print(f"[programmer_view] mapping embed error: {e}")
            return QLabel(f"Mapping nicht verfügbar: {e}")

    def _make_rgb_page(self) -> QWidget:
        """RGB-Matrix-Editor eingebettet (arbeitet via 'Aus Auswahl' auf der
        Programmer-Auswahl, R2)."""
        try:
            from src.ui.views.rgb_matrix_view import RgbMatrixView
            self._embedded_rgb = RgbMatrixView(follow_selection=True)
            return self._embedded_rgb
        except Exception as e:
            print(f"[programmer_view] rgb embed error: {e}")
            return QLabel(f"Matrix nicht verfügbar: {e}")

    def _make_palette_page(self) -> QWidget:
        """Paletten-Manager eingebettet (Anwenden wirkt auf die Auswahl, R2)."""
        try:
            from src.ui.views.palette_view import PaletteView
            self._embedded_palette = PaletteView()
            return self._embedded_palette
        except Exception as e:
            print(f"[programmer_view] palette embed error: {e}")
            return QLabel(f"Paletten nicht verfügbar: {e}")

    # ── Effekte-Seite: Logik ──────────────────────────────────────────────────

    def _refresh_effects_list(self):
        if not hasattr(self, "_effects_list") or self._effects_list is None:
            return
        try:
            fm = self._state.function_manager
        except Exception:
            return
        try:
            self._effects_list.clear()
            for f in fm.all():
                fid = getattr(f, "id", None)
                if fid is None:
                    continue
                name = getattr(f, "name", f"Funktion {fid}")
                running = fm.is_running(fid)
                it = QListWidgetItem(("▶ " if running else "") + name)
                it.setData(Qt.ItemDataRole.UserRole, fid)
                self._effects_list.addItem(it)
        except RuntimeError:
            pass  # Widget zwischenzeitlich geloescht (Layout-Wechsel)
        except Exception as e:
            print(f"[programmer_view] effects list error: {e}")

    def _on_effect_toggle(self, item: QListWidgetItem):
        fid = item.data(Qt.ItemDataRole.UserRole)
        if fid is None:
            return
        try:
            fm = self._state.function_manager
            if fm.is_running(fid):
                fm.stop(fid)
            else:
                fm.start(fid)
        except Exception as e:
            print(f"[programmer_view] effect toggle error: {e}")
        self._refresh_effects_list()

    def _current_effect_fid(self):
        it = self._effects_list.currentItem() if hasattr(self, "_effects_list") else None
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _effect_start(self):
        fid = self._current_effect_fid()
        if fid is not None:
            try:
                self._state.function_manager.start(fid)
            except Exception as e:
                print(f"[programmer_view] effect start error: {e}")
            self._refresh_effects_list()

    def _effect_stop(self):
        fid = self._current_effect_fid()
        if fid is not None:
            try:
                self._state.function_manager.stop(fid)
            except Exception as e:
                print(f"[programmer_view] effect stop error: {e}")
            self._refresh_effects_list()

    def _open_effect_wizard(self):
        try:
            from src.ui.widgets.effect_wizard import EffectWizard
            wiz = EffectWizard(self)
            if wiz.exec() == QDialog.DialogCode.Accepted:
                self._refresh_effects_list()
        except Exception as e:
            QMessageBox.warning(self, "Effekt-Assistent", str(e))

    def _new_effect(self, kind: str):
        """Legt eine Szene/einen Chaser an und öffnet direkt den Editor."""
        try:
            fm = self._state.function_manager
            if kind == "chaser":
                f = fm.new_chaser()
                f.name = "Neuer Chaser"
            else:
                f = fm.new_scene()
                f.name = "Neue Szene"
        except Exception as e:
            QMessageBox.warning(self, "Neuer Effekt", str(e))
            return
        try:
            from src.ui.views.function_manager_view import create_function_editor
            editor = create_function_editor(f)
            dlg = QDialog(self)
            dlg.setWindowTitle(f"Bearbeiten: {f.name}")
            dlg.resize(720, 560)
            lay = QVBoxLayout(dlg)
            lay.addWidget(editor)
            btn = QPushButton("Schließen")
            btn.clicked.connect(dlg.accept)
            lay.addWidget(btn)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "Editor", str(e))
        # Liste + Bibliothek aktualisieren
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.FUNCTION_CHANGED, {"id": getattr(f, "id", None)})
        except Exception:
            pass
        self._refresh_effects_list()

    def _save_as_scene(self):
        """Aktuellen Programmer als attribut-gefilterte Szene speichern.

        Wiederverwendet den ChannelSelectDialog (gleiche Gruppen wie beim
        Snap-Speichern): der Nutzer waehlt, WELCHE Attribut-Gruppen (nur Farbe /
        nur Dimmer / …) in die Szene wandern. Alle anderen Kanaele bleiben leer,
        sodass die Szene als Ebene mit anderen kombinierbar ist."""
        state = self._state
        prog = getattr(state, "programmer", {}) or {}
        if not prog:
            QMessageBox.information(self, "Programmer → Szene",
                                   "Programmer ist leer — nichts zu speichern.")
            return
        try:
            from src.ui.views.snap_file_panel import ChannelSelectDialog
            scope = state.active_scope_fids() if hasattr(state, "active_scope_fids") else None
            dlg = ChannelSelectDialog(prog, self, scope_fids=scope)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            filtered = dlg.filter_programmer(prog)
        except Exception as e:
            QMessageBox.warning(self, "Programmer → Szene", str(e))
            return
        if not filtered:
            QMessageBox.information(self, "Programmer → Szene",
                                   "Keine Kanäle ausgewählt.")
            return
        values = programmer_to_scene_values(filtered, state.get_patched_fixtures())
        if not values:
            QMessageBox.information(self, "Programmer → Szene",
                                   "Keine gepatchten Kanäle für die Auswahl gefunden.")
            return
        name, ok = QInputDialog.getText(self, "Programmer → Szene", "Name der Szene:")
        if not ok or not name.strip():
            return
        try:
            fm = state.function_manager
            scene = fm.new_scene(name.strip())
            for fid, ch, val in values:
                scene.set_value(fid, ch, val)
        except Exception as e:
            QMessageBox.warning(self, "Programmer → Szene", str(e))
            return
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.FUNCTION_CHANGED, {"id": getattr(scene, "id", None)})
        except Exception:
            pass
        self._refresh_effects_list()

    def _on_bottom_collapsed(self, collapsed: bool):
        _save_prefs({"programmer_bottom_collapsed": bool(collapsed)})

    def _push_selection_to_preview(self):
        tp = getattr(self, "_tile_preview", None)
        if tp is not None:
            try:
                tp.set_fixtures(self._selected_fids)
            except RuntimeError:
                pass  # Widget beim Layout-Wechsel geloescht

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
        # Einzelauswahl = keine Gruppe aktiv; VOR dem Publish setzen
        try:
            self._state.set_selected_group_id(None)
        except Exception:
            pass
        self._publish_selection()
        self._rebuild_attr_editor()

    def _publish_selection(self):
        """Gemeinsame Auswahl in den App-Zustand schreiben (R1), damit alle
        Kategorien (RGB Matrix, Effekte, Paletten …) darauf reagieren."""
        try:
            self._state.set_selected_fids(self._selected_fids)
        except Exception as e:
            print(f"[programmer_view] publish selection error: {e}")

    # ── Gruppen ──────────────────────────────────────────────────────────────

    def _session(self):
        """Öffnet eine DB-Session, sofern eine Show geladen ist."""
        eng = getattr(self._state, "_show_engine", None)
        if eng is None:
            return None
        from sqlalchemy.orm import Session
        return Session(eng)

    @staticmethod
    def _group_fids(group) -> list[int]:
        """Fids einer Gruppe in Raster-Reihenfolge (Zeile, dann Spalte).

        Die Reihenfolge ist wichtig für Fan/Chase: so laufen Effekte in der
        Reihenfolge, wie die Geräte auf dem Raster platziert wurden.
        """
        try:
            pos = json.loads(group.positions_json or "{}")
        except Exception:
            return []
        items = []
        for key, fid in pos.items():
            try:
                c, r = key.split(",")
                items.append((int(r), int(c), int(fid)))
            except Exception:
                continue
        items.sort()
        return [fid for _, _, fid in items]

    def _refresh_group_list(self):
        self._group_list.clear()
        s = self._session()
        if s is None:
            return
        q = (self._group_search.text().strip().lower()
             if hasattr(self, "_group_search") else "")
        try:
            from src.core.database.models import FixtureGroup
            from sqlalchemy import select
            with s:
                # P5/Ordner-Fix: nach Ordner + Name sortieren und Ordner als
                # (nicht waehlbare) Kopfzeilen anzeigen — vorher wurden die im
                # Patch-Bereich angelegten Ordner hier komplett ignoriert.
                groups = list(
                    s.execute(select(FixtureGroup)
                              .order_by(FixtureGroup.folder, FixtureGroup.name)
                              ).scalars()
                )
                if q:
                    # F-1: bei aktiver Suche eine gefilterte Flach-Liste zeigen
                    # (Name oder Ordner), ohne Ordner-Kopfzeilen/Einklappen — so
                    # erscheinen alle Treffer unabhaengig vom Collapse-Zustand.
                    for g in groups:
                        name = g.name or ""
                        folder = (getattr(g, "folder", "") or "").strip()
                        if q not in name.lower() and q not in folder.lower():
                            continue
                        fids = self._group_fids(g)
                        suffix = f"   📁 {folder}" if folder else ""
                        it = QListWidgetItem(f"{name}  ({len(fids)}){suffix}")
                        it.setData(Qt.ItemDataRole.UserRole, fids)
                        it.setData(Qt.ItemDataRole.UserRole + 1, g.id)
                        self._group_list.addItem(it)
                    return
                # Ordner-Kopfzeilen sind antippbar und klappen ihre Gruppen
                # ein/aus; der Zustand überlebt Neustarts (ui_prefs.json).
                collapsed = set(_load_prefs().get(
                    "programmer_collapsed_group_folders", []) or [])
                current_folder: str | None = None
                for g in groups:
                    folder = (getattr(g, "folder", "") or "").strip()
                    if folder != (current_folder or "") and folder:
                        arrow = "▸" if folder in collapsed else "▾"
                        header = QListWidgetItem(f"{arrow} 📁 {folder}")
                        header.setFlags(Qt.ItemFlag.ItemIsEnabled)
                        header.setData(Qt.ItemDataRole.UserRole + 2, folder)
                        f = header.font()
                        f.setBold(True)
                        header.setFont(f)
                        self._group_list.addItem(header)
                    current_folder = folder
                    if folder and folder in collapsed:
                        continue  # Inhalt eingeklappter Ordner verbergen
                    fids = self._group_fids(g)
                    prefix = "    " if folder else ""
                    it = QListWidgetItem(f"{prefix}{g.name}  ({len(fids)})")
                    it.setData(Qt.ItemDataRole.UserRole, fids)
                    # Gruppen-ID fuer den Gruppen-Pfad in der Matrix speichern
                    it.setData(Qt.ItemDataRole.UserRole + 1, g.id)
                    self._group_list.addItem(it)
        except Exception as e:
            print(f"[programmer_view] group list error: {e}")

    def _on_group_clicked(self, item: QListWidgetItem):
        # Ordner-Kopfzeile angetippt → Ordner auf-/zuklappen (Feature:
        # klappbare Programmer-Ordner), Zustand in ui_prefs persistieren.
        folder = item.data(Qt.ItemDataRole.UserRole + 2)
        if folder:
            collapsed = set(_load_prefs().get(
                "programmer_collapsed_group_folders", []) or [])
            if folder in collapsed:
                collapsed.discard(folder)
            else:
                collapsed.add(folder)
            _save_prefs({"programmer_collapsed_group_folders": sorted(collapsed)})
            self._refresh_group_list()
            return
        # Gruppen-ID VOR dem Publish setzen (Matrix liest sie beim SELECTION_CHANGED)
        gid = item.data(Qt.ItemDataRole.UserRole + 1)
        try:
            self._state.set_selected_group_id(gid)
        except Exception:
            pass
        self._select_fids(item.data(Qt.ItemDataRole.UserRole) or [], add=False)
        # F-1: Gruppenklick oeffnet direkt die Matrix-Ansicht der Gruppe.
        try:
            idx = getattr(self, "_matrix_tab_index", -1)
            if idx is not None and idx >= 0:
                self._main_tabs.setCurrentIndex(idx)
        except Exception:
            pass

    def _on_group_add_clicked(self, item: QListWidgetItem):
        # Additive Auswahl = gemischte Auswahl → keine einzelne Gruppe aktiv
        try:
            self._state.set_selected_group_id(None)
        except Exception:
            pass
        self._select_fids(item.data(Qt.ItemDataRole.UserRole) or [], add=True)

    def _select_fids(self, fids: list[int], add: bool = False):
        """Markiert die übergebenen Fids in der Fixture-Liste.

        Die interne Auswahl-Reihenfolge folgt der Gruppen-Reihenfolge (nicht
        der Listen-Reihenfolge), damit Fan/Chase korrekt durchlaufen.
        """
        present = {
            self._fixture_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._fixture_list.count())
        }
        # Visuelle Selektion aktualisieren (ohne _on_fixture_selected zu triggern)
        self._fixture_list.blockSignals(True)
        if not add:
            self._fixture_list.clearSelection()
        want = set(fids)
        for i in range(self._fixture_list.count()):
            it = self._fixture_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) in want:
                it.setSelected(True)
        self._fixture_list.blockSignals(False)
        # Interne Auswahl in Gruppen-Reihenfolge setzen
        existing = list(self._selected_fids) if add else []
        ordered = existing + [f for f in fids if f not in existing]
        self._selected_fids = [f for f in ordered if f in present]
        self._publish_selection()
        self._rebuild_attr_editor()

    # ── Attr Tabs Build ──────────────────────────────────────────────────────

    def _rebuild_attr_editor(self):
        # UNTEN-Vorschau (Zonen-Layout) an aktuelle Auswahl koppeln.
        self._push_selection_to_preview()
        # Neue einheitliche Tab-Struktur (WP-5): die 4 Attribut-Container befuellen.
        if not hasattr(self, "_attr_group_tabs"):
            return

        def _clear(container):
            lay = container.layout()
            while lay.count():
                w = lay.takeAt(0).widget()
                if w:
                    w.deleteLater()
            return lay

        try:
            fixtures = {f.fid: f for f in self._state.get_patched_fixtures()}
            selected = [fixtures[fid] for fid in self._selected_fids if fid in fixtures]
            if not selected:
                self._lbl_selection.setText("Kein Gerät ausgewählt")
                self._color_preview.set_fixtures([])
                self._template_channels = []
                for cont in self._attr_group_tabs.values():
                    _clear(cont).addWidget(QLabel("Kein Gerät ausgewählt"))
                if getattr(self, "_gobo_tab_index", -1) >= 0:
                    self._main_tabs.setTabVisible(self._gobo_tab_index, False)
                return

            self._lbl_selection.setText(
                f"{len(selected)} Gerät(e): " +
                ", ".join(f"[{f.fid}] {f.label}" for f in selected[:3]) +
                ("..." if len(selected) > 3 else "")
            )
            self._color_preview.set_fixtures(selected)
            self._update_fixture_combo(selected)   # M5: Einzelmodus-Auswahl

            # Kanaele des Templates nach Gruppe sortieren. "Weitere" buendelt
            # Beam+Gobo+Effect+Other (eine Stelle, keine Doppelung — Abschnitt 7).
            template = selected[0]
            channels = get_channels_for_patched(template)
            self._template_channels = list(channels)
            groups: dict[str, list[FixtureChannel]] = {
                "Intensity": [], "Color": [], "Position": [], "Gobo": [],
                "Weitere": []
            }
            seen_attrs: set[str] = set()
            for ch in channels:
                if ch.attribute in seen_attrs:
                    continue
                seen_attrs.add(ch.attribute)
                grp = _classify_attribute(ch.attribute)
                if grp in ("Intensity", "Color", "Position", "Gobo"):
                    groups[grp].append(ch)
                else:  # Beam, Effect, Other
                    groups["Weitere"].append(ch)
            # Dimmer vor Shutter/Strobe (Strobe liegt "neben" dem Dimmer).
            groups["Intensity"].sort(
                key=lambda c: 0 if c.attribute in INTENSITY_ATTRS else 1)

            for key, cont in self._attr_group_tabs.items():
                inner = self._build_group_tab(key, groups.get(key, []), selected)
                _clear(cont).addWidget(inner)

            # M2.1: Gobo-Tab nur bei vorhandenen Gobo-Kanaelen einblenden.
            if getattr(self, "_gobo_tab_index", -1) >= 0:
                self._main_tabs.setTabVisible(
                    self._gobo_tab_index, bool(groups.get("Gobo")))
        except RuntimeError:
            pass  # Widgets beim Layout-Wechsel zwischenzeitlich geloescht

    def _build_group_tab(self, group_name: str,
                         channels: list[FixtureChannel],
                         fixtures: list[PatchedFixture]) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Sub-Toolbar (bleibt FEST oben, scrollt nicht mit)
        sub_tb = QHBoxLayout()
        b_fan = QPushButton(f"Fan {group_name}...")
        b_fan.clicked.connect(lambda: self._open_fan_tool_for_group(group_name))
        sub_tb.addWidget(b_fan)

        if group_name == "Color":
            b_ct = QPushButton("Color Picker (Fenster)")
            b_ct.setCheckable(True)
            b_ct.setToolTip("Öffnet den Color Picker als eigenes, frei platzierbares "
                            "Fenster (statt unten eingebettet/abgeschnitten).")
            b_ct.toggled.connect(lambda chk: self._toggle_embedded_color(tab, chk))
            tab._cp_button = b_ct
            sub_tb.addWidget(b_ct)
            # Mehrkopf-Farbgeraet (z. B. Spider mit 2 RGBW-Baenken): Umschalter
            # Synchron <-> Getrennt fuer die Farbregler.
            if self._color_head_count() > 1:
                sub_tb.addWidget(QLabel("Köpfe:"))
                head_combo = QComboBox()
                head_combo.addItem("Synchron (beide gleich)", "sync")
                head_combo.addItem("Getrennt (pro Kopf)", "separate")
                head_combo.setCurrentIndex(
                    0 if self.color_head_mode() == "sync" else 1)
                head_combo.setToolTip(
                    "Synchron: ein Regler je Farbe steuert alle Köpfe gemeinsam.\n"
                    "Getrennt: jeder Kopf (z. B. linke/rechte Spider-Bar) hat "
                    "eigene Farbregler.")
                head_combo.currentIndexChanged.connect(
                    lambda i, c=head_combo: self._set_color_head_mode(c.itemData(i)))
                sub_tb.addWidget(head_combo)
        sub_tb.addStretch(1)
        layout.addLayout(sub_tb)

        # EIN äußerer Scroll für den GESAMTEN Tab-Inhalt (Schnellwahl + Tools +
        # Slider). Früher hingen Schnellwahl/Auto-Bar fix ÜBER dem Slider-Scroll
        # und konnten unter --touch abgeschnitten werden; jetzt scrollt alles
        # zusammen (wie der Matrix-Editor), nichts wird mehr geklippt.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        ilay = QVBoxLayout(inner)
        ilay.setContentsMargins(0, 0, 0, 0)
        ilay.setSpacing(6)
        ilay.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Capability-Schnellwahl (M2.2/M2.4): Kacheln aus den Fixture-Daten.
        self._add_quick_select(ilay, group_name, fixtures)

        # P8: Position-Tool fest als Aufklapp-Bereich im Layoutfluss — ersetzt
        # den frueheren "einbetten"-Toggle (dynamisches add/delete verschob das
        # Layout und konnte ueberlappen). Zustand merkt sich ui_prefs.
        # Spider (Doppelbar, zwei separate Tilts, kein Pan) bekommen ein eigenes
        # Tool: das XY-Pad waere irrefuehrend (Pan tut nichts, beide Bars sind nur
        # ueber den Mehrkopf-Schluessel tilt/tilt#1 getrennt steuerbar).
        if group_name == "Position":
            spider = self._selection_is_spider(fixtures)
            try:
                from src.ui.widgets.collapsible_section import CollapsibleSection
                if spider:
                    from src.ui.widgets.spider_position_tool import SpiderPositionTool
                    from src.core.app_state import tilt_head_count
                    heads = tilt_head_count(fixtures[0]) if fixtures else 2
                    spt = SpiderPositionTool(head_count=heads)
                    spt.set_live(True)
                    section = CollapsibleSection(
                        f"Spider-Position ({heads} Tilts)", spt, collapsed=False,
                        prefs_key="programmer_spider_position_tool")
                else:
                    from src.ui.widgets.position_tool import PositionTool
                    pt = PositionTool()
                    pt.set_live(True)   # M3.1: eingebettet wirkt das Pad sofort
                    section = CollapsibleSection(
                        "Position-Tool (XY-Pad)", pt, collapsed=True,
                        prefs_key="programmer_position_tool")
                ilay.addWidget(section)
            except Exception as e:
                print(f"[programmer_view] position tool embed error: {e}")

        # Slider-Liste
        if not channels:
            ilay.addWidget(QLabel(f"Keine {group_name}-Kanäle gefunden."))
        elif group_name == "Color" and self._color_head_count() > 1:
            # Mehrkopf-Farbgeraet (Spider): je nach Modus Synchron-/Pro-Kopf-Regler
            # statt der pro Attribut deduplizierten Standard-Slider.
            self._add_color_head_sliders(ilay, fixtures)
        else:
            # Spider-Position: die generischen Pan/Tilt-Slider entfallen (ein
            # einzelner "tilt"-Slider koennte die zwei Bars nicht trennen) — das
            # SpiderPositionTool oben uebernimmt beide Tilts.
            spider_pos = (group_name == "Position"
                          and self._selection_is_spider(fixtures))
            for ch in channels:
                # Reset/Rekalibrierung bekommt bewusst KEINEN Dauer-Slider —
                # nur den sicheren Button (ResetActionButton, _add_quick_select).
                if ch.attribute == "reset":
                    continue
                if spider_pos and ch.attribute in ("pan", "tilt",
                                                   "pan_fine", "tilt_fine"):
                    continue
                ilay.addWidget(AttributeSlider(ch, fixtures, self._state, owner=self))
        ilay.addStretch(1)

        scroll.setWidget(inner)
        layout.addWidget(scroll, stretch=1)

        return tab

    # ── Gruppen-Modus (M5) ────────────────────────────────────────────────────

    def group_mode(self) -> str:
        return getattr(self, "_group_mode", "linked")

    def active_fixture_index(self) -> int:
        return getattr(self, "_active_fixture_idx", 0)

    def _set_group_mode(self, key: str):
        self._group_mode = key
        if hasattr(self, "_fixture_combo"):
            self._fixture_combo.setEnabled(key == "individual")
        try:
            prefs = _load_prefs()
            prefs["programmer_group_mode"] = key
            _save_prefs(prefs)
        except Exception:
            pass
        self._rebuild_attr_editor()

    def _on_active_fixture_changed(self, idx: int):
        self._active_fixture_idx = max(0, idx)
        if self.group_mode() == "individual":
            self._rebuild_attr_editor()

    def _update_fixture_combo(self, selected):
        if not hasattr(self, "_fixture_combo"):
            return
        combo = self._fixture_combo
        combo.blockSignals(True)
        combo.clear()
        for f in selected:
            combo.addItem(f"[{f.fid}] {f.label}")
        if self._active_fixture_idx >= len(selected):
            self._active_fixture_idx = 0
        combo.setCurrentIndex(self._active_fixture_idx if selected else -1)
        combo.setEnabled(self.group_mode() == "individual")
        combo.blockSignals(False)

    def _is_touch(self) -> bool:
        try:
            from src.ui.touch_keyboard import is_touch_mode
            return bool(is_touch_mode())
        except Exception:
            return False

    def _template_channel_in(self, attrs: tuple):
        """Erstes Template-Kanalobjekt mit einem dieser Attribute (oder None)."""
        for ch in getattr(self, "_template_channels", []):
            if ch.attribute in attrs:
                return ch
        return None

    def _selection_is_spider(self, fixtures) -> bool:
        """True, wenn die uebergebene Auswahl ausschliesslich aus spider-/doppel-
        tilter-artigen Geraeten besteht (>=2 Tilt, KEIN Pan — egal ob mit/ohne
        Farbe). Nur dann schalten Position-/FX-Tab auf die Spider-Bedienung um;
        gemischte oder Moving-Head-Auswahlen bleiben unveraendert (zentrale
        is_dual_tilt_fixture — breiter als is_spider_fixture)."""
        try:
            from src.core.app_state import is_dual_tilt_fixture
            return bool(fixtures) and all(is_dual_tilt_fixture(f) for f in fixtures)
        except Exception:
            return False

    # ── Farb-Kopf-Modus (Spider & Co.: Synchron vs. Getrennt) ──────────────────

    def color_head_mode(self) -> str:
        return getattr(self, "_color_head_mode", "sync")

    def _selected_fixtures(self) -> list:
        """Die aktuell ausgewaehlten Fixture-Objekte (in Auswahl-Reihenfolge)."""
        by_fid = {f.fid: f for f in self._state.get_patched_fixtures()}
        return [by_fid[fid] for fid in getattr(self, "_selected_fids", [])
                if fid in by_fid]

    @staticmethod
    def _color_head_counts(fixture) -> dict:
        """Vorkommen je RGB(W)-Farb-Attribut in DIESEM Fixture (= Farb-Koepfe)."""
        counts: dict[str, int] = {}
        for ch in get_channels_for_patched(fixture):
            if ch.attribute in COLOR_ATTRS:
                counts[ch.attribute] = counts.get(ch.attribute, 0) + 1
        return counts

    def _color_head_count(self) -> int:
        """Maximale Farb-Kopf-Zahl ueber ALLE ausgewaehlten Fixtures (nicht nur
        das Template selected[0]). >1 => mind. ein Mehrkopf-Farbgeraet ist dabei
        (z. B. Spider mit zwei RGBW-Baenken) -> Synchron/Getrennt-Umschalter."""
        best = 1
        for f in self._selected_fixtures():
            c = self._color_head_counts(f)
            if c:
                best = max(best, max(c.values()))
        return best

    def _set_color_head_mode(self, key: str):
        if key not in ("sync", "separate") or key == self.color_head_mode():
            return
        self._color_head_mode = key
        try:
            prefs = _load_prefs()
            prefs["programmer_color_head_mode"] = key
            _save_prefs(prefs)
        except Exception:
            pass
        # Synchron: vorhandene Pro-Kopf-Abweichungen entfernen, damit alle Koepfe
        # wieder dem einfachen Schluessel folgen. Getrennt braucht KEIN Seeding —
        # die Pro-Kopf-Regler lesen den effektiven Wert (Kopf N, sonst Kopf 0),
        # es entstehen also keine toten "attr#N"-Schluessel.
        if key == "sync":
            self._normalize_color_heads_to_sync()
        self._rebuild_attr_editor()

    def _normalize_color_heads_to_sync(self):
        """Entfernt die "attr#N"-Pro-Kopf-Farbwerte der Auswahl (pro Fixture nur
        bis zu dessen echter Kopf-Zahl), sodass alle Koepfe wieder dem einfachen
        Schluessel folgen (Flush-Fallback) — so wirken auch Schnellwahl/Picker
        wieder auf beide Koepfe."""
        for f in self._selected_fixtures():
            prog = self._state.programmer.get(f.fid, {})
            for attr, cnt in self._color_head_counts(f).items():
                for h in range(1, cnt):
                    if f"{attr}#{h}" in prog:
                        self._state.clear_programmer_value(f.fid, f"{attr}#{h}")

    def _add_color_head_sliders(self, ilay, fixtures):
        """Baut die Farbregler eines Mehrkopf-Geraets je nach color_head_mode:
        - "sync": ein Regler je Farbe, treibt alle Koepfe gemeinsam.
        - "separate": ein Regler je Kopf (N-tes Vorkommen).
        Kanal-Vorlage ist das farb-reichste Geraet der Auswahl (nicht zwingend
        selected[0]); jeder Pro-Kopf-Regler bekommt NUR die Fixtures, die diesen
        Kopf wirklich besitzen (kein "attr#N" auf Einzelkopf-Geraeten)."""
        if not fixtures:
            return
        template = max(
            fixtures,
            key=lambda f: max(self._color_head_counts(f).values(), default=0))
        # Farb-Kanaele der Vorlage in Reihenfolge, mit Kopf-Index (Vorkommen).
        occ: dict[str, int] = {}
        color_chs = []   # (channel, head_index)
        for ch in get_channels_for_patched(template):
            if ch.attribute in COLOR_ATTRS:
                h = occ.get(ch.attribute, 0)
                occ[ch.attribute] = h + 1
                color_chs.append((ch, h))
        if not color_chs:
            return
        if self.color_head_mode() == "separate":
            for ch, h in color_chs:
                owners = [f for f in fixtures
                          if self._color_head_counts(f).get(ch.attribute, 0) > h]
                if owners:
                    ilay.addWidget(AttributeSlider(
                        ch, owners, self._state, owner=self, head=h))
        else:   # sync — ein Regler je Farbe (erstes Vorkommen), treibt alle Koepfe
            for ch, h in color_chs:
                if h != 0:
                    continue
                ilay.addWidget(AttributeSlider(
                    ch, fixtures, self._state, owner=self,
                    sync_heads=occ.get(ch.attribute, 1),
                    display_name=self._color_label(ch)))

    _COLOR_LABELS = {
        "color_r": "Rot", "color_g": "Grün", "color_b": "Blau",
        "color_w": "Weiß", "color_a": "Amber", "color_uv": "UV",
    }

    def _color_label(self, ch) -> str:
        """Head-agnostisches Farb-Label fuer den Synchron-Regler — aus dem Attribut
        abgeleitet (robust gegen Kanalnamen wie "Seg.1 Rot"), Fallback Kanalname."""
        return self._COLOR_LABELS.get(ch.attribute,
                                      self._strip_head_suffix(ch.name))

    @staticmethod
    def _strip_head_suffix(name: str) -> str:
        """ "Rot 1" -> "Rot" (haengende Kopf-Nummer entfernen; sonst unveraendert)."""
        parts = (name or "").rsplit(" ", 1)
        if len(parts) == 2 and parts[1].isdigit():
            return parts[0]
        return name

    def _add_quick_select(self, layout, group_name: str, fixtures):
        """Fuegt die capability-basierten Schnellwahl-Kacheln zum Tab hinzu."""
        touch = self._is_touch()
        try:
            if group_name == "Intensity":
                sh = self._template_channel_in(("shutter", "strobe"))
                if sh is not None:
                    from src.ui.widgets.preset_tile import ShutterQuickBar
                    layout.addWidget(QLabel("Shutter / Strobe:"))
                    layout.addWidget(ShutterQuickBar(sh, fixtures, self._state, touch=touch))
            elif group_name == "Color":
                attrs_present = {c.attribute for c in getattr(self, "_template_channels", [])}
                cw = self._template_channel_in(("color_wheel",))
                if (attrs_present & {"color_r", "color_g", "color_b", "color_w"}) or cw is not None:
                    from src.ui.widgets.preset_tile import ColorQuickBar
                    layout.addWidget(QLabel("Schnellwahl:"))
                    layout.addWidget(ColorQuickBar(fixtures, self._state, attrs_present,
                                                   cw, touch=touch))
            elif group_name == "Gobo":
                gw = self._template_channel_in(("gobo_wheel",))
                if gw is not None:
                    from src.ui.widgets.preset_tile import GoboQuickBar
                    layout.addWidget(QLabel("Gobo-Auswahl:"))
                    layout.addWidget(GoboQuickBar(gw, fixtures, self._state, touch=touch))
            elif group_name == "Position":
                spider = self._selection_is_spider(fixtures)
                # Pan/Tilt-Invert/Swap ist nur fuer echte Pan/Tilt-Moving-Heads
                # sinnvoll — beim Spider (kein Pan) blendet es aus.
                if not spider and self._template_channel_in(("pan", "tilt")) is not None:
                    bar = self._build_orientation_bar(fixtures)
                    if bar is not None:
                        layout.addWidget(bar)
                sp = self._template_channel_in(("speed",))
                if sp is not None:
                    layout.addWidget(QLabel("Bewegungs-Speed:" if spider
                                            else "Pan/Tilt-Speed:"))
                    layout.addWidget(AttributeSlider(sp, fixtures, self._state, owner=self))
            elif group_name == "Weitere":
                rs = self._template_channel_in(("reset",))
                if rs is not None:
                    from src.ui.widgets.preset_tile import ResetActionButton
                    layout.addWidget(QLabel("Reset / Rekalibrierung:"))
                    layout.addWidget(ResetActionButton(rs, fixtures, self._state))
        except Exception as e:
            print(f"[programmer_view] quick-select error: {e}")

    def _build_orientation_bar(self, fixtures):
        """Invert/Swap-Toggles fuer Pan/Tilt (M3.3). Schreibt die Flags pro
        Fixture via update_fixture (persistiert + im Renderer wirksam)."""
        if not fixtures:
            return None
        from PySide6.QtWidgets import QCheckBox, QGroupBox
        box = QGroupBox("Ausrichtung (pro Fixture)")
        row = QHBoxLayout(box)
        f0 = fixtures[0]
        for label, attr in (("Pan invert", "invert_pan"),
                            ("Tilt invert", "invert_tilt"),
                            ("Pan/Tilt tauschen", "swap_pan_tilt")):
            cb = QCheckBox(label)
            cb.setChecked(bool(getattr(f0, attr, False)))
            cb.toggled.connect(
                lambda chk, a=attr, fx=fixtures: self._set_orientation(a, chk, fx))
            row.addWidget(cb)
        row.addStretch(1)
        return box

    def _set_orientation(self, attr: str, value: bool, fixtures):
        for f in fixtures:
            try:
                self._state.update_fixture(f.fid, undoable=True, **{attr: bool(value)})
            except Exception as e:
                print(f"[programmer_view] orientation set error: {e}")

    def _toggle_embedded_color(self, tab: QWidget, on: bool):
        """Color Picker als schwebendes Popup-Fenster zeigen/schließen.

        Früher wurde der Picker unten in den Color-Tab eingebettet — dort war er
        oft abgeschnitten/nicht ganz sichtbar. Jetzt ein eigenes, NICHT-modales
        Fenster (Programmer bleibt bedienbar, Fenster frei verschiebbar)."""
        win = getattr(tab, "_cp_window", None)
        if on:
            if win is None:
                try:
                    from src.ui.widgets.color_picker import ColorPicker
                    win = _ToolDialog("Color Picker", self)
                    win.setModal(False)
                    win.set_content(ColorPicker())
                    win.finished.connect(lambda *_: self._on_color_window_closed(tab))
                    tab._cp_window = win
                except Exception as e:
                    print(f"[programmer_view] color picker window error: {e}")
                    return
            win.show()
            win.raise_()
            win.activateWindow()
        elif win is not None:
            win.close()

    def _on_color_window_closed(self, tab: QWidget):
        """Color-Picker-Fenster wurde geschlossen (X/„Schliessen") → Toggle lösen."""
        btn = getattr(tab, "_cp_button", None)
        if btn is not None:
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
        win = getattr(tab, "_cp_window", None)
        if win is not None:
            win.deleteLater()
            tab._cp_window = None

    

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
        btn = QPushButton("Schließen")
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
                 state: AppState, owner=None, parent=None,
                 head: int = 0, sync_heads: int = 0,
                 display_name: str | None = None):
        super().__init__(parent)
        self._channel = channel
        self._fixtures = fixtures
        self._state = state
        self._owner = owner   # ProgrammerView (Gruppen-Modus); None = Linked
        # Mehrkopf (X-6): head = welches Attribut-Vorkommen (Kopf) dieser Slider
        # steuert. sync_heads>0 => Synchron-Regler, der die Koepfe 0..N-1 GEMEINSAM
        # ueber den einfachen Schluessel treibt (und etwaige "attr#N"-Abweichungen
        # der anderen Koepfe aufraeumt, damit der Flush-Fallback spiegelt).
        # Default (0/0) = byte-genau wie bisher (Einzelkopf).
        self._head = int(head)
        self._sync_heads = int(sync_heads)
        self._display_name = display_name
        self._last_value = channel.default_value
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

        _name = self._display_name or self._channel.name
        lbl = QLabel(_name)
        lbl.setMinimumWidth(120)
        lbl.setToolTip(_name)
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
        btn_reset.setToolTip("Auf Standard zurücksetzen")
        btn_reset.clicked.connect(self._reset)
        layout.addWidget(btn_reset)

        # M2.5: groessere Touch-Targets im Touch-Modus.
        try:
            from src.ui.touch_keyboard import is_touch_mode
            if is_touch_mode():
                self.setMinimumHeight(44)
                self._slider.setMinimumHeight(30)
                btn_reset.setFixedSize(36, 36)
        except Exception:
            pass

    def _values_per_fixture(self) -> list[int]:
        h = self._base_head()
        out = []
        for f in self._fixtures:
            v = self._state.get_programmer_value(
                f.fid, self._channel.attribute, head=h)
            # Getrennt: ein noch nicht separat gesetzter Kopf>0 spiegelt Kopf 0
            # (wie der DMX-Flush) -> der Regler zeigt den echten Ausgabewert.
            if v is None and h > 0:
                v = self._state.get_programmer_value(
                    f.fid, self._channel.attribute, head=0)
            out.append(self._channel.default_value if v is None else v)
        return out

    def _load_current_value(self):
        if not self._fixtures:
            return
        vals = self._values_per_fixture()
        # M5.1: im Einzelmodus den Wert des aktiven Fixtures anzeigen.
        idx = self._active_index()
        template = vals[idx] if 0 <= idx < len(vals) else vals[0]
        self._slider.blockSignals(True)
        self._slider.setValue(template)
        self._slider.blockSignals(False)
        self._last_value = template
        divergent = len(set(vals)) > 1 and self._mode() != "individual"
        self._update_labels(template, divergent)

    def _mode(self) -> str:
        owner = self._owner
        if owner is not None and hasattr(owner, "group_mode"):
            try:
                return owner.group_mode()
            except Exception:
                return "linked"
        return "linked"

    def _active_index(self) -> int:
        owner = self._owner
        if owner is not None and hasattr(owner, "active_fixture_index"):
            try:
                return int(owner.active_fixture_index())
            except Exception:
                return 0
        return 0

    def _on_value_changed(self, value: int):
        mode = self._mode()
        if mode == "individual":
            idx = self._active_index()
            if 0 <= idx < len(self._fixtures):
                self._apply_value(self._fixtures[idx].fid, value)
            self._update_labels(value)
        elif mode == "relative":
            delta = value - self._last_value
            for f, cur in zip(self._fixtures, self._values_per_fixture()):
                self._apply_value(f.fid, max(0, min(255, cur + delta)))
            self._update_labels(value)
        else:  # linked
            for f in self._fixtures:
                self._apply_value(f.fid, value)
            self._update_labels(value)
        self._last_value = value

    def _base_head(self) -> int:
        """Kopf, dessen Wert dieser Slider anzeigt/liest (Synchron liest Kopf 0)."""
        return 0 if self._sync_heads > 0 else self._head

    def _apply_value(self, fid: int, value: int):
        """Schreibt den Wert in den/die Ziel-Kopf-Schluessel.

        Synchron (sync_heads>0): einfacher Schluessel (Kopf 0) + entfernt etwaige
        "attr#N"-Abweichungen der anderen Koepfe, sodass der DMX-Flush-Fallback und
        auch Schnellwahl/Color-Picker (die nur Kopf 0 schreiben) beide Koepfe
        gleich treiben. Getrennt: genau das N-te Vorkommen ("attr#N"; Kopf 0 =
        einfacher Schluessel)."""
        attr = self._channel.attribute
        if self._sync_heads > 0:
            self._state.set_programmer_value(fid, attr, value, head=0)
            prog = self._state.programmer.get(fid, {})
            for h in range(1, self._sync_heads):
                if f"{attr}#{h}" in prog:
                    self._state.clear_programmer_value(fid, f"{attr}#{h}")
        else:
            self._state.set_programmer_value(fid, attr, value, head=self._head)

    def _reset(self):
        self._slider.setValue(self._channel.default_value)

    def _update_labels(self, value: int, divergent: bool = False):
        self._lbl_val.setText("—" if divergent else str(value))
        self._lbl_pct.setText("" if divergent else f"{int(value / 255 * 100)}%")


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
