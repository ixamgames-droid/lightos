"""Laser View — Steuer-UI für DMX-Laser (LAS-02).

Eingebettet als Programmer-Tab (``follow_selection=True``), sichtbar nur wenn
die Auswahl Laser-Fixtures enthält (siehe ``fixture_has_laser_capability``).
Sektionen:

- **Mustergruppe A/B/A+B**: Laser wie der Ehaho L2600 doppeln ihre Kanäle für
  eine zweite Mustergruppe — im Patch als 2. Vorkommen derselben Attribute
  (Mehrkopf-Konvention, Kopf 0 = A, Kopf 1 = B / ``attr#1``).
- **Modus-Schnellwahl**: die Shutter-Ranges (Aus/Auto/Sound/Muster) als Kacheln.
- **Regler**: ein Range-beschrifteter Slider pro Laser-Kanal des Templates.
- **Muster-Paletten**: benannte Presets der Laser-Werte (``PaletteType.LASER``),
  gespeichert über die bestehende Palette-Engine (verwalten im Paletten-Tab).

Werte fließen ausschließlich über ``set_programmer_value(fid, attr, head=)`` —
kein eigener Render-Pfad. Laser-Safety: diese View schreibt nur auf explizite
Nutzeraktion; es gibt keinen Auto-Start.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QSlider,
    QSpinBox, QComboBox, QPushButton, QRadioButton, QButtonGroup,
    QScrollArea, QGroupBox, QInputDialog, QFrame,
)
from PySide6.QtCore import Qt

from src.core.app_state import get_state, get_channels_for_patched
from src.core.attr_groups import attr_label
from src.ui.weak_slots import weak_slot, weak_slot_fwd

# Nicht-``laser_*``-Attribute, die auf einem Laser-Fixture zur Laser-Steuerung
# gehören (Musterauswahl = gobo_wheel, Rotation = gobo_rotation usw.).
LASER_EXTRA_ATTRS = ("shutter", "gobo_wheel", "gobo_rotation", "zoom",
                     "color_wheel", "macro", "speed")


def fixture_has_laser_capability(fx) -> bool:
    """True, wenn das gepatchte Gerät als Laser steuerbar ist: entweder per
    ``fixture_type == 'laser'`` oder weil es ``laser_*``-Kanäle besitzt."""
    if (getattr(fx, "fixture_type", "") or "").lower() == "laser":
        return True
    try:
        channels = get_channels_for_patched(fx)
    except Exception:
        return False
    return any((getattr(ch, "attribute", "") or "").startswith("laser_")
               for ch in channels)


def _range_value(rng) -> int:
    """Anfahr-Wert für einen ChannelRange: Punktbereich → der Wert selbst,
    Band → Bandmitte (liegt sicher im Bereich, egal wie die Grenzen fallen)."""
    lo = int(getattr(rng, "range_from", 0) or 0)
    hi = int(getattr(rng, "range_to", lo) or lo)
    return lo if lo == hi else (lo + hi) // 2


def _sorted_ranges(ch) -> list:
    return sorted(getattr(ch, "ranges", None) or (),
                  key=lambda r: int(getattr(r, "range_from", 0) or 0))


class _ChannelRow(QWidget):
    """Eine Regler-Zeile: Label + Slider + Spin + Range-Auswahl (ComboBox)."""

    def __init__(self, channel, on_change, parent=None):
        super().__init__(parent)
        self.attribute = channel.attribute
        self._on_change = on_change
        self._ranges = _sorted_ranges(channel)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        lbl = QLabel(attr_label(self.attribute))
        lbl.setMinimumWidth(130)
        lbl.setToolTip(getattr(channel, "name", "") or "")
        lay.addWidget(lbl)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 255)
        lay.addWidget(self._slider, stretch=1)

        self._spin = QSpinBox()
        self._spin.setRange(0, 255)
        self._spin.setFixedWidth(56)
        lay.addWidget(self._spin)

        self._combo = QComboBox()
        self._combo.setMinimumWidth(170)
        self._combo.addItem("— Bereich wählen —", None)
        for r in self._ranges:
            lo = int(getattr(r, "range_from", 0) or 0)
            hi = int(getattr(r, "range_to", lo) or lo)
            name = getattr(r, "name", "") or f"{lo}-{hi}"
            self._combo.addItem(f"{lo}-{hi}  {name}", _range_value(r))
        self._combo.setVisible(bool(self._ranges))
        lay.addWidget(self._combo)

        self._slider.valueChanged.connect(self._slider_changed)
        self._spin.valueChanged.connect(self._spin_changed)
        self._combo.currentIndexChanged.connect(self._combo_changed)

    # -- interne Sync-Helfer (Signale beim Spiegeln blocken) ------------------
    def _sync_widgets(self, value: int):
        for w in (self._slider, self._spin):
            w.blockSignals(True)
            w.setValue(value)
            w.blockSignals(False)
        self._combo.blockSignals(True)
        idx = 0
        for i, r in enumerate(self._ranges, start=1):
            lo = int(getattr(r, "range_from", 0) or 0)
            hi = int(getattr(r, "range_to", lo) or lo)
            if lo <= value <= hi:
                idx = i
                break
        self._combo.setCurrentIndex(idx)
        self._combo.blockSignals(False)

    def _emit(self, value: int):
        self._sync_widgets(value)
        self._on_change(self.attribute, value)

    def _slider_changed(self, v: int):
        self._emit(int(v))

    def _spin_changed(self, v: int):
        self._emit(int(v))

    def _combo_changed(self, _idx: int):
        val = self._combo.currentData()
        if val is not None:
            self._emit(int(val))

    def set_value(self, value: int):
        """Wert von außen anzeigen (ohne zu schreiben)."""
        self._sync_widgets(max(0, min(255, int(value))))


class LaserView(QWidget):
    """Laser-Steuerseite (Programmer-Tab). Arbeitet auf der Programmer-Auswahl."""

    def __init__(self, parent=None, follow_selection: bool = False):
        super().__init__(parent)
        self._follow = bool(follow_selection)
        self._fixtures: list = []
        self._network_fids: list[int] = []
        self._rows: dict[str, _ChannelRow] = {}
        self._template_sig: tuple = ()
        self._head_mode: str = "A"          # "A" | "B" | "AB"

        self._build_ui()
        self._subscribe()
        self.refresh_from_selection()

    # ------------------------------------------------------------------ UI --
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self._info = QLabel("Kein Laser in der Auswahl.")
        self._info.setStyleSheet("color:#8b949e;")
        root.addWidget(self._info)

        # ── Sicherheit (Netzwerk-Streaming-Laser) ─────────────────────────
        # Scharfschalten + Not-Aus + Framequelle. Nur sichtbar, wenn ein
        # Netzwerk-Laser (Ether Dream / IDN) in der Auswahl ist — DMX-Laser
        # geben über die normale DMX-Pipeline aus, nicht über den Streamer.
        self._safety_box = QGroupBox("Laser-Ausgabe (Netzwerk)")
        sb = QVBoxLayout(self._safety_box)
        arm_row = QHBoxLayout()
        self._btn_arm = QPushButton("🔒 UNSCHARF — Ausgabe geblockt")
        self._btn_arm.setCheckable(True)
        self._btn_arm.setMinimumHeight(40)
        self._btn_arm.toggled.connect(weak_slot(self._on_arm_toggled))
        arm_row.addWidget(self._btn_arm, stretch=1)
        self._btn_estop = QPushButton("⏹ NOT-AUS")
        self._btn_estop.setMinimumHeight(40)
        self._btn_estop.setStyleSheet(
            "QPushButton{background:#8b0000;color:#fff;font-weight:bold;"
            "border:1px solid #b30000;border-radius:5px;padding:6px 14px;}"
            "QPushButton:hover{background:#b30000;}")
        self._btn_estop.clicked.connect(weak_slot(self._on_estop))
        arm_row.addWidget(self._btn_estop)
        sb.addLayout(arm_row)
        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Ausgabe:"))
        self._combo_figure = QComboBox()
        self._combo_figure.addItem("Testmuster (Kreis)", None)
        try:
            from src.core.laser.figure import builtin_figures
            for fig in builtin_figures():
                self._combo_figure.addItem(f"Figur: {fig.name}", fig)
        except Exception as e:
            print(f"[laser_view] builtin figures error: {e}")
        self._combo_figure.currentIndexChanged.connect(
            weak_slot(self._on_figure_changed))
        src_row.addWidget(self._combo_figure, stretch=1)
        sb.addLayout(src_row)
        self._arm_hint = QLabel(
            "Beim Scharfschalten tritt echtes Laserlicht aus. "
            "Publikum/Augen schützen, Not-Aus bereithalten.")
        self._arm_hint.setWordWrap(True)
        self._arm_hint.setStyleSheet("color:#8b949e;font-size:10px;")
        sb.addWidget(self._arm_hint)
        root.addWidget(self._safety_box)
        self._update_arm_button()

        # Mustergruppe (Kopf 0/1) — nur sichtbar, wenn das Gerät doppelte
        # Laser-Attribute hat (z. B. L2600 34ch: Gruppe A + B).
        self._head_box = QGroupBox("Mustergruppe")
        hb = QHBoxLayout(self._head_box)
        self._head_group = QButtonGroup(self)
        for label, key in (("Gruppe A", "A"), ("Gruppe B", "B"),
                           ("A + B", "AB")):
            rb = QRadioButton(label)
            rb.setChecked(key == "A")
            self._head_group.addButton(rb)
            rb.toggled.connect(weak_slot_fwd(self._on_head_mode_toggled, key))
            hb.addWidget(rb)
        hb.addStretch(1)
        root.addWidget(self._head_box)

        # Modus-Schnellwahl (Shutter-Ranges als Kacheln).
        self._mode_box = QGroupBox("Laser-Modus")
        self._mode_lay = QHBoxLayout(self._mode_box)
        self._mode_lay.setSpacing(6)
        root.addWidget(self._mode_box)

        # Muster-Paletten (PaletteType.LASER) — Anlegen hier, Verwalten im
        # Paletten-Tab.
        self._pal_box = QGroupBox("Muster-Paletten")
        pv = QVBoxLayout(self._pal_box)
        self._pal_grid = QGridLayout()
        self._pal_grid.setSpacing(6)
        pv.addLayout(self._pal_grid)
        pal_btns = QHBoxLayout()
        btn_save = QPushButton("💾 Muster speichern…")
        btn_save.setToolTip("Aktuelle Laser-Werte der Auswahl als benanntes "
                            "Muster ablegen (Verwalten im Paletten-Tab).")
        btn_save.clicked.connect(self._save_palette)
        pal_btns.addWidget(btn_save)
        pal_btns.addStretch(1)
        pv.addLayout(pal_btns)
        root.addWidget(self._pal_box)

        # Regler-Bereich (scrollbar).
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._rows_host = QWidget()
        self._rows_lay = QVBoxLayout(self._rows_host)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.setSpacing(4)
        self._rows_lay.addStretch(1)
        scroll.setWidget(self._rows_host)
        root.addWidget(scroll, stretch=1)

    def _subscribe(self):
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            if self._follow:
                sync.subscribe_widget(SyncEvent.SELECTION_CHANGED, self,
                                      lambda *_: self._on_selection_changed())
            sync.subscribe_widget(SyncEvent.PALETTE_CHANGED, self,
                                  lambda *_: self._rebuild_palettes())
            sync.subscribe_widget(SyncEvent.SHOW_LOADED, self,
                                  lambda *_: self._on_show_loaded())
        except Exception as e:
            print(f"[laser_view] sync subscribe error: {e}")

    def _on_show_loaded(self):
        # Safety: eine neu geladene Show startet UNSCHARF und ohne aktive
        # Figuren — Scharfschalten ist immer eine bewusste Nutzeraktion.
        lo = self._laser_output()
        if lo is not None:
            lo.set_armed(False)
            lo.clear_figures()
        try:
            self._btn_arm.setChecked(False)
            self._combo_figure.setCurrentIndex(0)
            self._update_arm_button()
        except RuntimeError:
            pass
        self.refresh_from_selection()

    # ---------------------------------------------------------- Selection --
    def _on_selection_changed(self):
        # Unsichtbar: nicht bei jedem fremden Tab-Klick Widgets neu bauen —
        # showEvent holt den Sync nach (Muster aus efx_view/rgb_matrix_view).
        try:
            if not self.isVisible():
                self._stale = True
                return
        except RuntimeError:
            return
        self.refresh_from_selection()

    def showEvent(self, event):  # noqa: N802 (Qt-API)
        super().showEvent(event)
        if getattr(self, "_stale", True):
            self.refresh_from_selection()

    def refresh_from_selection(self):
        """Auswahl einlesen, Template bilden, Regler/Kacheln (neu) aufbauen."""
        self._stale = False
        state = get_state()
        try:
            selected = set(state.get_selected_fids())
        except Exception:
            selected = set()
        self._fixtures = [
            f for f in state.get_patched_fixtures()
            if getattr(f, "fid", None) in selected
            and fixture_has_laser_capability(f)
        ]

        if not self._fixtures:
            self._info.setText(
                "Kein Laser in der Auswahl — links ein Laser-Gerät wählen.")
            self._head_box.setVisible(False)
            self._mode_box.setVisible(False)
        else:
            names = ", ".join(
                str(getattr(f, "name", None) or getattr(f, "fixture_name", "")
                    or f"fid {getattr(f, 'fid', '?')}")
                for f in self._fixtures[:4])
            more = len(self._fixtures) - 4
            self._info.setText(
                f"{len(self._fixtures)} Laser: {names}"
                + (f" … (+{more})" if more > 0 else ""))
            self._head_box.setVisible(self._max_head_count() > 1)

        # Safety-Box nur für Netzwerk-Streaming-Laser in der Auswahl.
        self._network_fids = [
            int(getattr(f, "fid"))
            for f in self._fixtures
            if (getattr(f, "protocol", "") or "").lower()
            in ("etherdream", "idn")]
        self._safety_box.setVisible(bool(self._network_fids))
        self._apply_figure_to_selection()

        template = self._template_channels()
        sig = tuple((ch.attribute, int(getattr(ch, "channel_number", 0) or 0))
                    for ch in template)
        if sig != self._template_sig:
            self._template_sig = sig
            self._rebuild_rows(template)
            self._rebuild_mode_tiles(template)
        self._load_values()
        self._rebuild_palettes()

    # ── Safety / Framequelle (LAS-07) ─────────────────────────────────────
    def _laser_output(self):
        try:
            return get_state().ensure_laser_output()
        except Exception as e:
            print(f"[laser_view] laser output unavailable: {e}")
            return None

    def _update_arm_button(self):
        armed = self._btn_arm.isChecked()
        if armed:
            self._btn_arm.setText("🔓 SCHARF — Laser gibt Licht aus")
            self._btn_arm.setStyleSheet(
                "QPushButton{background:#8a6d00;color:#fff;font-weight:bold;"
                "border:1px solid #d4a200;border-radius:5px;padding:6px 14px;}")
        else:
            self._btn_arm.setText("🔒 UNSCHARF — Ausgabe geblockt")
            self._btn_arm.setStyleSheet(
                "QPushButton{background:#21262d;color:#8b949e;"
                "border:1px solid #30363d;border-radius:5px;padding:6px 14px;}")

    def _on_arm_toggled(self, checked: bool):
        lo = self._laser_output()
        if lo is not None:
            lo.set_armed(bool(checked))
        self._update_arm_button()

    def _on_estop(self):
        lo = self._laser_output()
        if lo is not None:
            lo.estop_all()
        # Nach Not-Aus zurück auf unscharf — bewusstes Wieder-Scharfschalten nötig.
        self._btn_arm.setChecked(False)
        self._update_arm_button()
        if lo is not None:
            lo.clear_estop_all()

    def _on_figure_changed(self, _idx: int):
        self._apply_figure_to_selection()

    def _apply_figure_to_selection(self):
        """Setzt die gewählte Figur (oder Testmuster=None) als Framequelle für
        alle Netzwerk-Laser der aktuellen Auswahl."""
        lo = self._laser_output()
        if lo is None:
            return
        figure = self._combo_figure.currentData()
        for fid in getattr(self, "_network_fids", []):
            lo.set_figure(fid, figure)

    def _template_channels(self) -> list:
        """Vereinigung der Laser-Kanäle aller selektierten Laser (ein Kanal je
        Attribut; Kanäle MIT Ranges als Repräsentant bevorzugt — dasselbe
        Muster wie der Attribut-Editor des Programmers)."""
        union: dict[str, object] = {}
        order: dict[str, int] = {}
        for f in self._fixtures:
            try:
                channels = get_channels_for_patched(f)
            except Exception:
                continue
            for ch in channels:
                attr = getattr(ch, "attribute", "") or ""
                if not (attr.startswith("laser_") or attr in LASER_EXTRA_ATTRS):
                    continue
                prev = union.get(attr)
                if prev is None or (not getattr(prev, "ranges", None)
                                    and getattr(ch, "ranges", None)):
                    union[attr] = ch
                order.setdefault(
                    attr, int(getattr(ch, "channel_number", 0) or 0))
        return sorted(union.values(),
                      key=lambda c: order.get(c.attribute, 999))

    def _max_head_count(self) -> int:
        """Höchste Vorkommens-Zahl eines Laser-Attributs über die Auswahl —
        >1 bedeutet: das Gerät hat eine zweite Mustergruppe (Kopf 1)."""
        best = 1
        for f in self._fixtures:
            try:
                channels = get_channels_for_patched(f)
            except Exception:
                continue
            counts: dict[str, int] = {}
            for ch in channels:
                attr = getattr(ch, "attribute", "") or ""
                if attr.startswith("laser_") or attr in LASER_EXTRA_ATTRS:
                    counts[attr] = counts.get(attr, 0) + 1
            if counts:
                best = max(best, max(counts.values()))
        return best

    # ------------------------------------------------------------- Aufbau --
    def _rebuild_rows(self, template: list):
        while self._rows_lay.count() > 1:
            item = self._rows_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._rows = {}
        for ch in template:
            row = _ChannelRow(ch, self._write_value)
            self._rows[ch.attribute] = row
            self._rows_lay.insertWidget(self._rows_lay.count() - 1, row)

    def _rebuild_mode_tiles(self, template: list):
        while self._mode_lay.count():
            item = self._mode_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        shutter = next((ch for ch in template if ch.attribute == "shutter"),
                       None)
        ranges = _sorted_ranges(shutter) if shutter is not None else []
        self._mode_box.setVisible(bool(ranges))
        if not ranges:
            return
        try:
            from src.ui.widgets.preset_tile import PresetTile
        except Exception as e:
            print(f"[laser_view] preset_tile import error: {e}")
            return
        kind_colors = {"closed": "#21262d", "open": "#1a4a2a",
                       "sound": "#1a3a5c"}
        for r in ranges:
            name = getattr(r, "name", "") or "?"
            tile = PresetTile(
                name, _range_value(r),
                color=kind_colors.get(getattr(r, "kind", "") or ""),
                tooltip=f"Shutter → {_range_value(r)}")
            tile.clicked.connect(weak_slot_fwd(self._on_mode_tile_clicked))
            self._mode_lay.addWidget(tile)
        self._mode_lay.addStretch(1)

    def _rebuild_palettes(self):
        while self._pal_grid.count():
            item = self._pal_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        try:
            from src.core.engine.palette import (PaletteType,
                                                 get_palette_manager)
            from src.ui.widgets.preset_tile import PresetTile
        except Exception as e:
            print(f"[laser_view] palette import error: {e}")
            return
        palettes = get_palette_manager().get_by_type(PaletteType.LASER)
        for i, p in enumerate(palettes):
            tile = PresetTile(p.name, p.name, color="#2a0a3a",
                              tooltip="Muster auf die ausgewählten Laser "
                                      "anwenden")
            tile.clicked.connect(weak_slot(self._apply_palette, p))
            self._pal_grid.addWidget(tile, i // 4, i % 4)
        self._pal_box.setVisible(True)

    # ------------------------------------------------------------- Werte ---
    def _heads_for(self, fx, attr: str) -> list[int]:
        """Zu beschreibende Köpfe je Modus — Kopf 1 nur, wenn das Gerät ein
        2. Vorkommen des Attributs wirklich hat (ENG-03-Muster)."""
        try:
            count = sum(
                1 for ch in get_channels_for_patched(fx)
                if (getattr(ch, "attribute", "") or "") == attr)
        except Exception:
            count = 0
        if count <= 0:
            return []
        heads = {"A": [0], "B": [1], "AB": [0, 1]}[self._head_mode]
        return [h for h in heads if h == 0 or count > h]

    def _write_value(self, attr: str, value: int):
        state = get_state()
        for f in self._fixtures:
            fid = getattr(f, "fid", None)
            if fid is None:
                continue
            for head in self._heads_for(f, attr):
                state.set_programmer_value(fid, attr, int(value), head=head)

    def _load_values(self):
        if not self._fixtures:
            return
        state = get_state()
        first = self._fixtures[0]
        fid = getattr(first, "fid", None)
        read_head = 1 if self._head_mode == "B" else 0
        for attr, row in self._rows.items():
            try:
                val = state.get_programmer_value(fid, attr, head=read_head)
            except TypeError:
                val = state.get_programmer_value(fid, attr)
            except Exception:
                val = None
            row.set_value(int(val) if val is not None else 0)

    def _on_head_mode_toggled(self, key: str, on: bool):
        """Bound-Slot statt Lambda (STAB-10): nur der AKTIV werdende
        Radio-Button schaltet die Mustergruppe."""
        if on:
            self._set_head_mode(key)

    def _on_mode_tile_clicked(self, value):
        """Bound-Slot statt Lambda (STAB-10): Shutter-Kachel schreibt den Wert."""
        self._write_value("shutter", int(value))

    def _set_head_mode(self, mode: str):
        self._head_mode = mode
        self._load_values()

    # ----------------------------------------------------------- Paletten --
    def _save_palette(self):
        if not self._fixtures:
            return
        name, ok = QInputDialog.getText(
            self, "Muster speichern",
            "Name für das Laser-Muster (aktuelle Werte der Auswahl):")
        name = (name or "").strip()
        if not ok or not name:
            return
        try:
            from src.core.engine.palette import (Palette, PaletteType,
                                                 get_palette_manager)
            manager = get_palette_manager()
            fids = [getattr(f, "fid") for f in self._fixtures]
            existing = manager.find(name)
            if existing is not None and existing.type == PaletteType.LASER:
                existing.record_from_programmer(fids)
                manager._notify_palettes_changed()
            else:
                p = Palette(name=name, type=PaletteType.LASER)
                p.record_from_programmer(fids)
                manager.add(p)
        except Exception as e:
            print(f"[laser_view] save palette error: {e}")
        self._rebuild_palettes()

    def _apply_palette(self, palette):
        fids = [getattr(f, "fid") for f in self._fixtures]
        if not fids:
            return
        try:
            palette.apply_to_programmer(fids)
        except Exception as e:
            print(f"[laser_view] apply palette error: {e}")
        self._load_values()
