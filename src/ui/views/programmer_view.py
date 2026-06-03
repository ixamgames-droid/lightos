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
    QListWidget, QListWidgetItem, QGroupBox, QScrollArea, QFrame,
    QTabWidget, QToolButton, QSizePolicy, QMessageBox, QDialog, QSplitter,
    QStackedWidget, QButtonGroup, QInputDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from src.core.app_state import get_state, AppState, get_channels_for_patched
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
        chmap = {c.attribute: c.channel_number for c in get_channels_for_patched(fx)}
        for attr, val in attrs.items():
            ch = chmap.get(attr)
            if ch is None:
                continue
            try:
                out.append((int(fid), int(ch), max(0, min(255, int(val)))))
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
        self._setup_ui()  # baut Body + befuellt Listen/Editor aus dem State
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
            self._refresh_group_list()
            self._rebuild_attr_editor()
            self._refresh_effects_list()
        except Exception as e:
            print(f"[programmer_view] sync_refresh error: {e}")

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

        self._btn_layout = QPushButton()
        self._btn_layout.setFixedHeight(26)
        self._btn_layout.setToolTip("Programmer-Layout umschalten (Klassisch / Zonen)")
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

        grp_box = QGroupBox("Gruppen")
        grp_layout = QVBoxLayout(grp_box)
        grp_layout.setContentsMargins(4, 6, 4, 4)
        grp_layout.setSpacing(4)
        self._group_list = QListWidget()
        self._group_list.setMaximumHeight(130)
        self._group_list.itemClicked.connect(self._on_group_clicked)
        self._group_list.itemDoubleClicked.connect(self._on_group_add_clicked)
        grp_layout.addWidget(self._group_list)
        grp_hint = QLabel("Klick = Gruppe waehlen · Doppelklick = zur Auswahl addieren")
        grp_hint.setWordWrap(True)
        grp_hint.setStyleSheet("color: #888; font-size: 10px;")
        grp_layout.addWidget(grp_hint)
        left.addWidget(grp_box)

        left_w = QWidget()
        left_w.setLayout(left)
        return left_w

    def _make_attr_area(self) -> QWidget:
        """Selektions-Label + Farb-Vorschau + Attribut-Tabs (alle Gruppen)."""
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
        return right_top

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

        # CENTER: [ MITTE-top | UNTEN ]
        center = QSplitter(Qt.Orientation.Vertical)
        center.addWidget(self._make_mitte())
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

    def _make_mitte(self) -> QWidget:
        """MITTE: Kategorie-Leiste + gestapelte Eingabe-Panels (P-05 / LAYOUT-03).

        Farben/Dimmer/Bewegung/Weitere zeigen die Attribut-Tabs (und springen auf
        den passenden Tab); Effekte und EFX sind eigene Seiten.
        """
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        bar = QHBoxLayout()
        bar.setSpacing(2)
        self._cat_group = QButtonGroup(self)
        self._cat_group.setExclusive(True)

        self._mitte_stack = QStackedWidget()
        self._mitte_stack.addWidget(self._make_attr_area())     # Index 0
        self._mitte_stack.addWidget(self._make_effects_page())  # Index 1
        self._mitte_stack.addWidget(self._make_efx_page())      # Index 2
        self._mitte_stack.addWidget(self._make_rgb_page())      # Index 3
        self._mitte_stack.addWidget(self._make_palette_page())  # Index 4

        cats = [
            ("Farben", "Color"), ("Dimmer", "Intensity"),
            ("Bewegung", "Position"), ("Weitere", None),
            ("Effekte", "__effects__"), ("EFX", "__efx__"),
            ("Matrix", "__rgb__"), ("Paletten", "__palette__"),
        ]
        for label, target in cats:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setFixedHeight(26)
            b.clicked.connect(lambda _=False, t=target: self._on_category(t))
            self._cat_group.addButton(b)
            bar.addWidget(b)
        bar.addStretch(1)
        v.addLayout(bar)
        v.addWidget(self._mitte_stack, stretch=1)

        # Default: Farben
        buttons = self._cat_group.buttons()
        if buttons:
            buttons[0].setChecked(True)
        return w

    def _on_category(self, target):
        page_index = {
            "__effects__": 1, "__efx__": 2, "__rgb__": 3, "__palette__": 4,
        }
        if target in page_index:
            self._mitte_stack.setCurrentIndex(page_index[target])
        else:
            self._mitte_stack.setCurrentIndex(0)
            if target:
                self._select_attr_tab(target)

    def _select_attr_tab(self, name: str):
        if not hasattr(self, "_attr_tabs"):
            return
        for i in range(self._attr_tabs.count()):
            if self._attr_tabs.tabText(i) == name:
                self._attr_tabs.setCurrentIndex(i)
                return

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
            self._embedded_efx = EfxView()
            return self._embedded_efx
        except Exception as e:
            print(f"[programmer_view] efx embed error: {e}")
            return QLabel(f"EFX nicht verfuegbar: {e}")

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
            return QLabel(f"Paletten nicht verfuegbar: {e}")

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
            btn = QPushButton("Schliessen")
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
            dlg = ChannelSelectDialog(prog, self)
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
        try:
            from src.core.database.models import FixtureGroup
            from sqlalchemy import select
            with s:
                groups = list(
                    s.execute(select(FixtureGroup).order_by(FixtureGroup.name)).scalars()
                )
                for g in groups:
                    fids = self._group_fids(g)
                    it = QListWidgetItem(f"{g.name}  ({len(fids)})")
                    it.setData(Qt.ItemDataRole.UserRole, fids)
                    # Gruppen-ID fuer den Gruppen-Pfad in der Matrix speichern
                    it.setData(Qt.ItemDataRole.UserRole + 1, g.id)
                    self._group_list.addItem(it)
        except Exception as e:
            print(f"[programmer_view] group list error: {e}")

    def _on_group_clicked(self, item: QListWidgetItem):
        # Gruppen-ID VOR dem Publish setzen (Matrix liest sie beim SELECTION_CHANGED)
        gid = item.data(Qt.ItemDataRole.UserRole + 1)
        try:
            self._state.set_selected_group_id(gid)
        except Exception:
            pass
        self._select_fids(item.data(Qt.ItemDataRole.UserRole) or [], add=False)

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
