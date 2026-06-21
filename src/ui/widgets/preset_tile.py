"""Generische Schnellwahl-Kacheln fuer Fixture-Kanaele (M2.3 / Abschnitt 13).

Ein wiederverwendbares ``PresetTile`` (Label + optionale Farbe(n)/Icon + DMX-
Payload) plus fertige Capability-Bars fuer Farbe, Shutter/Strobe und Gobo.
Die Wheel-/Shutter-Presets kommen ausschliesslich aus den ``ChannelRange``-
Daten des Fixtures (kein Raten) — fehlen sie, bleibt nur der Fader.

Ausbau 2026-06-10 (Moving-Head-Initiative, siehe docs/MOVING_HEADS.md):
- PresetTile kann Split-Farben (``color2``) und ein Icon-Pixmap anzeigen.
- Farbrad-Kacheln zeigen die echte(n) Farbe(n) des Slots (aus dem Range-Namen
  abgeleitet, nur fuer Slots mit kind "color"/"open").
- ShutterQuickBar: Status-Kacheln + Strobe-Speed-Slider + DMX-Bereichslegende.
- GoboQuickBar: Gobo-Kacheln mit grafischer Vorschau (gobo_icons), Shake-
  Kacheln mit einstellbarer Geschwindigkeit, Gobo-Wechsel-Slider.
- ColorWheelAutoBar: Auto-Farbwechsel der Hardware (Range kind "rotate") +
  Software-Simulation ueber einen waehlbaren Slot-Bereich.
- ResetActionButton: Reset/Rekalibrierung mit Sicherheitsabfrage und
  automatischem Ruecksetzen des Kanals.
"""
from __future__ import annotations

import re

from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout,
                               QGridLayout, QSizePolicy, QSlider, QPushButton,
                               QComboBox, QCheckBox, QMessageBox, QGroupBox,
                               QFormLayout)
from PySide6.QtCore import Qt, Signal, QTimer


def _contrast(hex_color: str) -> str:
    """Schwarz/Weiss-Textfarbe je nach Helligkeit des Hintergrunds."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return "#111" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#f0f0f0"
    except Exception:
        return "#f0f0f0"


class PresetTile(QFrame):
    """Anklickbare Kachel mit Label, optionaler Farbe (oder Split-Farbpaar
    ``color``/``color2``), optionalem Icon-Pixmap und Nutzlast (Payload).
    Beim Klick wird ``clicked(payload)`` emittiert (Payload = beliebiges Objekt,
    z. B. ``{"color_r": 255}`` oder ``("shutter", 4)``)."""

    clicked = Signal(object)

    def __init__(self, label: str, payload, color: str | None = None,
                 color2: str | None = None, pixmap=None,
                 touch: bool = False, tooltip: str = "", parent=None):
        super().__init__(parent)
        self._payload = payload
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        base_h = (44 if touch else 34) + (22 if pixmap is not None else 0)
        self.setMinimumSize(72 if touch else 60, base_h)
        if tooltip:
            self.setToolTip(tooltip)

        if color and color2 and color2 != color:
            # Split-Farbe: halbe/halbe Diagonale via Stylesheet-Gradient
            bg = (f"qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                  f"stop:0 {color}, stop:0.499 {color}, "
                  f"stop:0.501 {color2}, stop:1 {color2})")
            fg = _contrast(color)
        else:
            bg = color or "#2a2f37"
            fg = _contrast(color) if color else "#e6edf3"
        self.setStyleSheet(
            f"PresetTile {{ background:{bg}; border:1px solid #30363d; "
            f"border-radius:5px; }} "
            f"PresetTile:hover {{ border:1px solid #58a6ff; }}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(1)
        if pixmap is not None:
            ico = QLabel()
            ico.setPixmap(pixmap)
            ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ico.setStyleSheet("background:transparent;")
            lay.addWidget(ico)
        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{fg}; font-size:11px; background:transparent;")
        lay.addWidget(lbl)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._payload)
        super().mousePressEvent(e)


def _grid(tiles: list[PresetTile], cols: int) -> QWidget:
    w = QWidget()
    g = QGridLayout(w)
    g.setContentsMargins(0, 0, 0, 0)
    g.setSpacing(4)
    for i, t in enumerate(tiles):
        g.addWidget(t, i // cols, i % cols)
    return w


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color:#9aa4af; font-size:11px;")
    return lbl


def _legend_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color:#7d8590; font-size:10px;")
    return lbl


# ── Capability → Presets ─────────────────────────────────────────────────────

# Benannte Basisfarben fuer RGB(W)-Schnellwahl. Payload setzt nur RGBW/A/UV;
# nicht vorhandene Kanaele ignoriert der Renderer.
COLOR_PRESETS = [
    ("Weiß",    "#ffffff", {"color_w": 255, "color_r": 255, "color_g": 255, "color_b": 255}),
    ("Rot",     "#ff3030", {"color_r": 255, "color_g": 0, "color_b": 0, "color_w": 0}),
    ("Orange",  "#ff8000", {"color_r": 255, "color_g": 105, "color_b": 0, "color_w": 0}),
    ("Gelb",    "#ffe000", {"color_r": 255, "color_g": 210, "color_b": 0, "color_w": 0}),
    ("Grün",    "#30d030", {"color_r": 0, "color_g": 255, "color_b": 0, "color_w": 0}),
    ("Cyan",    "#00d0d0", {"color_r": 0, "color_g": 255, "color_b": 255, "color_w": 0}),
    ("Blau",    "#3060ff", {"color_r": 0, "color_g": 0, "color_b": 255, "color_w": 0}),
    ("Violett", "#a040ff", {"color_r": 150, "color_g": 0, "color_b": 255, "color_w": 0}),
    ("Magenta", "#ff40c0", {"color_r": 255, "color_g": 0, "color_b": 200, "color_w": 0}),
    ("Aus",     "#181818", {"color_r": 0, "color_g": 0, "color_b": 0, "color_w": 0,
                            "color_a": 0, "color_uv": 0}),
]

# Farbwort → Hex fuer Farbrad-Slot-Namen (deutsch + englisch). Reihenfolge
# wichtig: "hellblau" muss vor "blau" geprueft werden.
_NAME_COLOR_WORDS = [
    ("hellblau", "#7fd4ff"), ("light blue", "#7fd4ff"), ("lightblue", "#7fd4ff"),
    ("tuerkis", "#00d0d0"), ("türkis", "#00d0d0"), ("cyan", "#00d0d0"),
    ("magenta", "#ff40c0"),
    ("violett", "#a040ff"), ("purple", "#a040ff"), ("lila", "#a040ff"),
    ("rosa", "#ff8fc8"), ("pink", "#ff8fc8"),
    ("orange", "#ff8000"), ("amber", "#ffbf00"),
    ("gelb", "#ffe000"), ("yellow", "#ffe000"),
    ("gruen", "#30d030"), ("grün", "#30d030"), ("green", "#30d030"),
    ("blau", "#3060ff"), ("blue", "#3060ff"),
    ("rot", "#ff3030"), ("red", "#ff3030"),
    ("weiss", "#ffffff"), ("weiß", "#ffffff"), ("white", "#ffffff"),
    ("offen", "#ffffff"), ("open", "#ffffff"),
]


def _color_word_hex(part: str) -> str | None:
    for word, hexc in _NAME_COLOR_WORDS:
        if word in part:
            if word == "rot" and "rotation" in part:
                continue   # "Farbrotation" ist kein Rot
            return hexc
    return None


def slot_colors_for_name(name: str) -> list[str]:
    """Leitet 0–2 Anzeigefarben aus einem Farbrad-Slot-Namen ab.
    "Rot" → [rot], "Hellblau/Rosa" → [hellblau, rosa], "Gobo 1" → []."""
    n = (name or "").lower()
    parts = [p.strip() for p in re.split(r"[/+]", n) if p.strip()]
    out: list[str] = []
    for part in parts:
        hexc = _color_word_hex(part)
        if hexc:
            out.append(hexc)
    # "Weiß / Offen" → zweimal weiss → eine Farbe reicht
    if len(out) == 2 and out[0] == out[1]:
        out = out[:1]
    return out[:2]


def _range_mid(r) -> int:
    return max(0, min(255, (int(r.range_from) + int(r.range_to)) // 2))


def shutter_presets(channel) -> list[tuple[str, int]]:
    """(Label, DMX-Wert)-Liste fuer Shutter aus ChannelRange-Daten.
    Ohne Ranges: konventioneller Fallback Auf=255 / Zu=0."""
    ranges = list(getattr(channel, "ranges", None) or [])
    out: list[tuple[str, int]] = []
    open_r = [r for r in ranges if (getattr(r, "kind", "") or "") == "open"]
    closed_r = [r for r in ranges if (getattr(r, "kind", "") or "") == "closed"]
    strobe_r = [r for r in ranges if (getattr(r, "kind", "") or "") == "strobe"]
    if open_r:
        out.append(("Auf", _range_mid(open_r[0])))
    if closed_r:
        out.append(("Zu", _range_mid(closed_r[0])))
    if strobe_r:
        r = strobe_r[0]
        lo, hi = int(r.range_from), int(r.range_to)
        span = max(1, hi - lo)
        out.append(("Strobe langsam", lo + span // 5))
        out.append(("Strobe mittel", lo + span // 2))
        out.append(("Strobe schnell", hi - span // 10))
    if not ranges:
        out = [("Auf", 255), ("Zu", 0)]
    return out


def wheel_slots(channel) -> list[tuple[str, int]]:
    """(Label, DMX-Wert)-Liste fuer ein Color-/Gobo-Wheel aus den Ranges
    (Mittelwert je Bereich). Ohne Ranges leer (-> nur Fader)."""
    ranges = list(getattr(channel, "ranges", None) or [])
    return [((getattr(r, "name", "") or "?"), _range_mid(r)) for r in ranges]


def wheel_slot_info(channel) -> list[dict]:
    """Reiche Slot-Infos fuer ein Wheel: Liste von Dicts mit ``label``,
    ``value`` (Mittelwert), ``kind``, ``from``, ``to``. Ohne Ranges leer."""
    out: list[dict] = []
    for r in (getattr(channel, "ranges", None) or []):
        out.append({
            "label": getattr(r, "name", "") or "?",
            "value": _range_mid(r),
            "kind": (getattr(r, "kind", "") or ""),
            "from": int(r.range_from),
            "to": int(r.range_to),
        })
    return out


def _ranges_legend(channel) -> str:
    """Kompakte Text-Legende aller DMX-Bereiche eines Kanals."""
    parts = [f"{int(r.range_from)}–{int(r.range_to)} {getattr(r, 'name', '')}"
             for r in (getattr(channel, "ranges", None) or [])]
    return " · ".join(parts)


def _slot_speed_value(slot: dict, percent: int) -> int:
    """DMX-Wert innerhalb eines Slots fuer eine Geschwindigkeit 0–100 %
    (hoeherer Wert im Bereich = schneller)."""
    lo, hi = int(slot["from"]), int(slot["to"])
    pct = max(0, min(100, int(percent)))
    return lo + round((hi - lo) * pct / 100)


# ── Fertige Bars ─────────────────────────────────────────────────────────────

class _ApplyMixin:
    def _set_on_fixtures(self, attr: str, value: int):
        for f in self._fixtures:
            self._state.set_programmer_value(f.fid, attr, int(value))

    def _apply_payload(self, payload: dict):
        # P6: Farb-Payloads pro Fixture an dessen Farbsystem anpassen —
        # RGBW-Geraete bekommen Weiss ueber den W-Kanal statt RGB+W doppelt.
        from src.core.color_utils import adapt_color_payload, fixture_attr_set
        for f in self._fixtures:
            adapted = adapt_color_payload(fixture_attr_set(f), payload)
            for attr, value in adapted.items():
                self._state.set_programmer_value(f.fid, attr, int(value))


class ColorQuickBar(QWidget, _ApplyMixin):
    """Benannte Farb-Kacheln (RGB) + Color-Wheel-Slots als farbige Kacheln
    (inkl. Split-Farben) + Auto-Farbwechsel-Steuerung."""

    def __init__(self, fixtures, state, attrs_present: set,
                 color_wheel_channel=None, touch: bool = False, parent=None):
        super().__init__(parent)
        self._fixtures = fixtures
        self._state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        has_rgb = bool(attrs_present & {"color_r", "color_g", "color_b", "color_w"})
        if has_rgb:
            tiles = []
            for name, hexc, payload in COLOR_PRESETS:
                t = PresetTile(name, payload, color=hexc, touch=touch)
                t.clicked.connect(self._apply_payload)
                tiles.append(t)
            lay.addWidget(_grid(tiles, cols=5))

        slots = wheel_slot_info(color_wheel_channel) if color_wheel_channel else []
        if slots:
            attr = color_wheel_channel.attribute
            # Farb-Slots (Voll- und Split-Farben) als farbige Direktwahl-Kacheln.
            # Andere Slots (unbekannter kind) bleiben neutrale Kacheln; der
            # Auto-Bereich (kind "rotate") wird separat unten gesteuert.
            wt = []
            split_tiles = []   # P10: Split-/Half-Colors separat einklappbar
            color_slots: list[dict] = []
            for s in slots:
                if s["kind"] == "rotate":
                    continue
                colors = (slot_colors_for_name(s["label"])
                          if s["kind"] in ("color", "open") else [])
                if s["kind"] in ("color", "open"):
                    color_slots.append(s)
                t = PresetTile(
                    s["label"], {attr: s["value"]},
                    color=colors[0] if colors else None,
                    color2=colors[1] if len(colors) > 1 else None,
                    touch=touch, tooltip=f"DMX {s['from']}–{s['to']}")
                t.clicked.connect(self._apply_payload)
                # Zwei Anzeigefarben = Split-/Half-Color -> in den
                # Aufklapp-Bereich, damit Raeder mit vielen Farben
                # uebersichtlich bleiben (Vollfarben bleiben direkt sichtbar).
                if len(colors) > 1:
                    split_tiles.append(t)
                else:
                    wt.append(t)
            if wt:
                lay.addWidget(_section_label("Farbrad:"))
                lay.addWidget(_grid(wt, cols=4))
            if split_tiles:
                from src.ui.widgets.collapsible_section import CollapsibleSection
                lay.addWidget(CollapsibleSection(
                    f"Split-/Half-Colors ({len(split_tiles)})",
                    _grid(split_tiles, cols=4), collapsed=True,
                    prefs_key="programmer_split_colors"))

            rotate = next((s for s in slots if s["kind"] == "rotate"), None)
            open_slot = next((s for s in slots if s["kind"] == "open"), None)
            if rotate is not None or len(color_slots) >= 2:
                lay.addWidget(ColorWheelAutoBar(
                    attr, color_slots, rotate, open_slot,
                    fixtures, state, touch=touch))


class ColorWheelAutoBar(QWidget, _ApplyMixin):
    """Auto-Farbwechsel fuers Color Wheel.

    Zwei Wege (siehe docs/MOVING_HEADS.md, Abschnitt Farbrotation):
    - **Hardware:** der "rotate"-Bereich des Rads (z. B. DMX 140–255 beim
      ZQ02001) — laeuft im Geraet, immer ueber ALLE Farben, Tempo per Slider.
    - **Software-Simulation:** LightOS schaltet das Rad per Timer durch einen
      waehlbaren Slot-Bereich (z. B. nur Farbe 1–3 oder nur Split-Farben).
      Grenzen: laeuft nur solange der Programmer offen ist, harte Wechsel
      (Farbraeder koennen nicht faden), wird nicht in Snaps/Szenen als
      Animation gespeichert.
    """

    def __init__(self, attr: str, color_slots: list[dict], rotate_slot,
                 open_slot, fixtures, state, touch: bool = False, parent=None):
        super().__init__(parent)
        self._fixtures = fixtures
        self._state = state
        self._attr = attr
        self._slots = list(color_slots)
        self._open_value = int(open_slot["value"]) if open_slot else 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # ── Hardware-Rotation (eigene beschriftete Gruppe) ───────────────
        # Eigene QGroupBox + ausreichend Abstand: früher lagen Hardware-Zeile,
        # Von/Bis-Combos und Software-Speed-Slider mit nur 3px ineinander und
        # überlappten unter --touch (hohe Combos). Gruppen + Stapeln behebt das.
        if rotate_slot is not None:
            self._rotate = rotate_slot
            grp_hw = QGroupBox("Auto-Farbwechsel (Hardware)")
            hwl = QVBoxLayout(grp_hw)
            hwl.addWidget(_legend_label(
                f"Hardware-Rotation des Farbrads (DMX {rotate_slot['from']}–"
                f"{rotate_slot['to']}) — läuft im Gerät über alle Farben."))
            row = QHBoxLayout()
            row.addWidget(QLabel("langsam"))
            self._hw_speed = QSlider(Qt.Orientation.Horizontal)
            self._hw_speed.setRange(0, 100)
            self._hw_speed.setValue(30)
            self._hw_speed.valueChanged.connect(self._hw_speed_changed)
            row.addWidget(self._hw_speed, stretch=1)
            row.addWidget(QLabel("schnell"))
            b_start = QPushButton("Start")
            b_start.clicked.connect(self._hw_start)
            row.addWidget(b_start)
            b_stop = QPushButton("Stopp")
            b_stop.setToolTip("Zurück auf Weiß/Offen")
            b_stop.clicked.connect(self._all_stop)
            row.addWidget(b_stop)
            hwl.addLayout(row)
            lay.addWidget(grp_hw)
        else:
            self._rotate = None
            self._hw_speed = None

        # ── Software-Simulation (eigene Gruppe, Von/Bis gestapelt) ────────
        self._sw_timer = QTimer(self)
        self._sw_timer.timeout.connect(self._sw_tick)
        self._sw_index = 0
        if len(self._slots) >= 2:
            grp_sw = QGroupBox("Farbwechsel (Software)")
            swl = QVBoxLayout(grp_sw)
            self._cb_from = QComboBox()
            self._cb_to = QComboBox()
            for s in self._slots:
                self._cb_from.addItem(s["label"])
                self._cb_to.addItem(s["label"])
            self._cb_to.setCurrentIndex(len(self._slots) - 1)
            # Von/Bis untereinander (QFormLayout) → kein horizontales Klippen
            # unter --touch (zwei breite Combos passen nicht in eine Zeile).
            form = QFormLayout()
            form.setContentsMargins(0, 0, 0, 0)
            form.setFieldGrowthPolicy(
                QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            form.addRow("Von:", self._cb_from)
            form.addRow("Bis:", self._cb_to)
            swl.addLayout(form)
            self._chk_split = QCheckBox("Nur Split-Farben")
            has_split = any("/" in s["label"] or "+" in s["label"]
                            for s in self._slots)
            self._chk_split.setVisible(has_split)
            swl.addWidget(self._chk_split)

            row2 = QHBoxLayout()
            row2.addWidget(QLabel("langsam"))
            self._sw_speed = QSlider(Qt.Orientation.Horizontal)
            self._sw_speed.setRange(0, 100)
            self._sw_speed.setValue(40)
            self._sw_speed.valueChanged.connect(self._sw_speed_changed)
            row2.addWidget(self._sw_speed, stretch=1)
            row2.addWidget(QLabel("schnell"))
            self._btn_sw = QPushButton("Start")
            self._btn_sw.setCheckable(True)
            self._btn_sw.toggled.connect(self._sw_toggled)
            row2.addWidget(self._btn_sw)
            swl.addLayout(row2)
            swl.addWidget(_legend_label(
                "Software-Wechsel: LightOS schaltet das Farbrad selbst um "
                "(nur solange der Programmer aktiv ist, harte Wechsel)."))
            lay.addWidget(grp_sw)

    # Hardware --------------------------------------------------------------
    def _hw_value(self) -> int:
        return _slot_speed_value(self._rotate, self._hw_speed.value())

    def _hw_start(self):
        self._stop_sw()
        self._set_on_fixtures(self._attr, self._hw_value())

    def _hw_speed_changed(self, _v):
        # Tempo live nachfuehren, wenn die Hardware-Rotation gerade laeuft
        if self._hw_running():
            self._set_on_fixtures(self._attr, self._hw_value())

    def _hw_running(self) -> bool:
        if self._rotate is None or not self._fixtures:
            return False
        try:
            val = self._state.get_programmer_value(
                self._fixtures[0].fid, self._attr)
        except Exception:
            return False
        return val is not None and self._rotate["from"] <= val <= self._rotate["to"]

    # Software --------------------------------------------------------------
    def _sw_interval_ms(self) -> int:
        # 0 % → 1500 ms, 100 % → 120 ms
        return int(1500 - (1500 - 120) * self._sw_speed.value() / 100)

    def _sw_selected_slots(self) -> list[dict]:
        if self._chk_split.isChecked():
            return [s for s in self._slots
                    if "/" in s["label"] or "+" in s["label"]]
        i0, i1 = self._cb_from.currentIndex(), self._cb_to.currentIndex()
        if i0 > i1:
            i0, i1 = i1, i0
        return self._slots[i0:i1 + 1]

    def _sw_toggled(self, on: bool):
        if on:
            self._btn_sw.setText("Stopp")
            self._sw_index = 0
            self._sw_tick()
            self._sw_timer.start(self._sw_interval_ms())
        else:
            self._btn_sw.setText("Start")
            self._sw_timer.stop()

    def _sw_speed_changed(self, _v):
        if self._sw_timer.isActive():
            self._sw_timer.start(self._sw_interval_ms())

    def _sw_tick(self):
        slots = self._sw_selected_slots()
        if not slots:
            return
        slot = slots[self._sw_index % len(slots)]
        self._sw_index += 1
        self._set_on_fixtures(self._attr, slot["value"])

    def _stop_sw(self):
        if self._sw_timer.isActive():
            self._btn_sw.setChecked(False)

    def _all_stop(self):
        self._stop_sw()
        self._set_on_fixtures(self._attr, self._open_value)


class ShutterQuickBar(QWidget, _ApplyMixin):
    """Shutter-/Strobe-Schnellwahl: Status-Kacheln aus den Range-Namen,
    Strobe-Speed-Slider (langsam → schnell) und DMX-Bereichslegende.
    Liegt im Intensity-Tab direkt beim Dimmer (siehe docs/MOVING_HEADS.md)."""

    def __init__(self, channel, fixtures, state, touch: bool = False, parent=None):
        super().__init__(parent)
        self._fixtures = fixtures
        self._state = state
        self._attr = channel.attribute
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        ranges = list(getattr(channel, "ranges", None) or [])
        strobe_r = next((r for r in ranges
                         if (getattr(r, "kind", "") or "") == "strobe"), None)

        # Status-Kacheln: Open/Closed direkt aus den Range-Namen, dazu
        # Strobe-Stufen (langsam/mittel/schnell) aus dem Strobe-Bereich.
        tiles = []
        if ranges:
            for r in ranges:
                kind = (getattr(r, "kind", "") or "")
                if kind == "open":
                    tiles.append(PresetTile(
                        getattr(r, "name", "Auf"), _range_mid(r),
                        color="#1f6f3f", touch=touch,
                        tooltip=f"DMX {int(r.range_from)}–{int(r.range_to)}"))
                elif kind == "closed":
                    tiles.append(PresetTile(
                        getattr(r, "name", "Zu"), _range_mid(r),
                        color="#5a1f1f", touch=touch,
                        tooltip=f"DMX {int(r.range_from)}–{int(r.range_to)}"))
            if strobe_r is not None:
                lo, hi = int(strobe_r.range_from), int(strobe_r.range_to)
                span = max(1, hi - lo)
                for label, val in (("Strobe langsam", lo + span // 5),
                                   ("Strobe mittel", lo + span // 2),
                                   ("Strobe schnell", hi - span // 10)):
                    tiles.append(PresetTile(label, val, color="#3a2f5a",
                                            touch=touch,
                                            tooltip=f"DMX {val}"))
        else:
            tiles = [PresetTile("Auf", 255, color="#1f6f3f", touch=touch),
                     PresetTile("Zu", 0, color="#5a1f1f", touch=touch)]
        for t in tiles:
            t.clicked.connect(lambda v: self._set_on_fixtures(self._attr, v))
        lay.addWidget(_grid(tiles, cols=3))

        # Strobe-Geschwindigkeit stufenlos (innerhalb des Strobe-Bereichs).
        if strobe_r is not None:
            row = QHBoxLayout()
            row.addWidget(_section_label("Strobe-Geschwindigkeit:"))
            row.addWidget(QLabel("langsam"))
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(int(strobe_r.range_from), int(strobe_r.range_to))
            sl.setValue(int(strobe_r.range_from))
            sl.valueChanged.connect(
                lambda v: self._set_on_fixtures(self._attr, v))
            if touch:
                sl.setMinimumHeight(30)
            row.addWidget(sl, stretch=1)
            row.addWidget(QLabel("schnell"))
            lay.addLayout(row)

        legend = _ranges_legend(channel)
        if legend:
            lay.addWidget(_legend_label(legend))


class GoboQuickBar(QWidget, _ApplyMixin):
    """Gobo-Schnellwahl aus den Ranges des gobo_wheel-Kanals.

    Mit kind-Daten (M1.2): Kacheln mit grafischer Gobo-Vorschau (gobo_icons),
    eigene Shake-Kacheln mit Geschwindigkeits-Slider und ein Slider fuer den
    Gobo-Wechsel-Bereich (kind "rotate"). Ohne kind-Daten: neutrale Kacheln
    fuer alle Slots (Fallback, wie bisher)."""

    def __init__(self, channel, fixtures, state, touch: bool = False, parent=None):
        super().__init__(parent)
        self._fixtures = fixtures
        self._state = state
        self._attr = channel.attribute
        self._shake_pct = 50
        self._active_shake: dict | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        slots = wheel_slot_info(channel)
        static = [s for s in slots if s["kind"] == "gobo"]
        shakes = [s for s in slots if s["kind"] == "shake"]
        opens = [s for s in slots if s["kind"] == "open"]
        rotate = next((s for s in slots if s["kind"] == "rotate"), None)

        if not (static or shakes or rotate):
            # Fallback ohne kind-Daten: alle Slots als neutrale Text-Kacheln.
            tiles = []
            for label, val in wheel_slots(channel):
                t = PresetTile(label, val, touch=touch)
                t.clicked.connect(lambda v: self._set_on_fixtures(self._attr, v))
                tiles.append(t)
            if tiles:
                lay.addWidget(_grid(tiles, cols=4))
            else:
                lay.addWidget(QLabel(
                    "Keine Gobo-Slots im Profil hinterlegt — Fader nutzen."))
            return

        try:
            from src.ui.widgets.gobo_icons import gobo_pixmap_for_name
        except Exception:
            gobo_pixmap_for_name = None
        icon_size = 30 if touch else 24

        def _short(label: str) -> str:
            return re.sub(r"\s*\(.*?\)", "", label).strip()

        # Reihe 1: Kein Gobo + statische Gobos (mit Vorschau-Icon)
        tiles = []
        if opens:
            o = opens[0]
            pm = (gobo_pixmap_for_name(o["label"], size=icon_size, shake=False)
                  if gobo_pixmap_for_name else None)
            t = PresetTile("Kein Gobo", o["value"], pixmap=pm, touch=touch,
                           tooltip=f"DMX {o['from']}–{o['to']}")
            t.clicked.connect(lambda v: self._set_on_fixtures(self._attr, v))
            tiles.append(t)
        for s in static:
            pm = (gobo_pixmap_for_name(s["label"], size=icon_size)
                  if gobo_pixmap_for_name else None)
            t = PresetTile(_short(s["label"]), s["value"], pixmap=pm,
                           touch=touch,
                           tooltip=f"{s['label']} — DMX {s['from']}–{s['to']}")
            t.clicked.connect(self._on_static_clicked)
            tiles.append(t)
        if tiles:
            lay.addWidget(_section_label("Gobo:"))
            lay.addWidget(_grid(tiles, cols=4))

        # Reihe 2: Shake-Gobos mit einstellbarer Geschwindigkeit
        if shakes:
            st = []
            for s in shakes:
                pm = (gobo_pixmap_for_name(s["label"], size=icon_size,
                                           shake=True)
                      if gobo_pixmap_for_name else None)
                t = PresetTile(_short(s["label"]), s, pixmap=pm, touch=touch,
                               tooltip=f"{s['label']} — DMX {s['from']}–{s['to']}"
                                       f" (höher = schneller)")
                t.clicked.connect(self._on_shake_clicked)
                st.append(t)
            lay.addWidget(_section_label("Gobo-Shake (Wackeln):"))
            lay.addWidget(_grid(st, cols=4))
            row = QHBoxLayout()
            row.addWidget(_section_label("Shake-Geschwindigkeit:"))
            row.addWidget(QLabel("langsam"))
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(0, 100)
            sl.setValue(self._shake_pct)
            sl.valueChanged.connect(self._on_shake_speed)
            if touch:
                sl.setMinimumHeight(30)
            row.addWidget(sl, stretch=1)
            row.addWidget(QLabel("schnell"))
            lay.addLayout(row)

        # Reihe 3: Gobo-Wechsel (alle nacheinander, Tempo aus dem Wert)
        if rotate is not None:
            row = QHBoxLayout()
            row.addWidget(_section_label(
                f"Gobo-Wechsel (DMX {rotate['from']}–{rotate['to']}):"))
            row.addWidget(QLabel("langsam"))
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(int(rotate["from"]), int(rotate["to"]))
            sl.setValue(int(rotate["from"]))
            sl.valueChanged.connect(self._on_rotate_speed)
            if touch:
                sl.setMinimumHeight(30)
            row.addWidget(sl, stretch=1)
            row.addWidget(QLabel("schnell"))
            b_stop = QPushButton("Stopp")
            b_stop.setToolTip("Zurück auf 'Kein Gobo'")
            stop_val = opens[0]["value"] if opens else 0
            b_stop.clicked.connect(
                lambda: self._set_on_fixtures(self._attr, stop_val))
            row.addWidget(b_stop)
            lay.addLayout(row)

        legend = _ranges_legend(channel)
        if legend:
            lay.addWidget(_legend_label(legend))

    def _on_static_clicked(self, value):
        self._active_shake = None
        self._set_on_fixtures(self._attr, int(value))

    def _on_shake_clicked(self, slot: dict):
        self._active_shake = slot
        self._set_on_fixtures(self._attr,
                              _slot_speed_value(slot, self._shake_pct))

    def _on_shake_speed(self, pct: int):
        self._shake_pct = int(pct)
        if self._active_shake is not None:
            self._set_on_fixtures(self._attr,
                                  _slot_speed_value(self._active_shake, pct))

    def _on_rotate_speed(self, value: int):
        self._active_shake = None
        self._set_on_fixtures(self._attr, int(value))


class ResetActionButton(QPushButton, _ApplyMixin):
    """Sicherer Reset-/Rekalibrierungs-Button fuer Moving Heads.

    Sendet nach Bestaetigung den Reset-Wert (ChannelRange kind "reset",
    Mittelwert) auf den Reset-Kanal und setzt den Kanal nach ``hold_ms``
    automatisch auf den Default zurueck — der Reset kann also nicht
    versehentlich dauerhaft aktiv bleiben. Haltedauer 4 s (Annahme, siehe
    docs/MOVING_HEADS.md)."""

    HOLD_MS = 4000

    def __init__(self, channel, fixtures, state, parent=None):
        super().__init__("⟳ Moving Head Reset…", parent)
        self._fixtures = fixtures
        self._state = state
        self._attr = channel.attribute
        self._idle = int(getattr(channel, "default_value", 0) or 0)
        reset_r = next((r for r in (getattr(channel, "ranges", None) or [])
                        if (getattr(r, "kind", "") or "") == "reset"), None)
        self._reset_value = _range_mid(reset_r) if reset_r is not None else 255
        rng_txt = (f"DMX {int(reset_r.range_from)}–{int(reset_r.range_to)}"
                   if reset_r is not None else "DMX 255")
        self.setToolTip(f"Reset/Rekalibrierung auslösen ({rng_txt}, "
                        f"wird nach {self.HOLD_MS // 1000} s automatisch "
                        f"zurückgesetzt)")
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self):
        ans = QMessageBox.question(
            self, "Moving Head Reset",
            "Reset/Rekalibrierung wirklich auslösen?\n\n"
            "Die ausgewählten Moving Heads fahren dabei in ihre Home-Position "
            "— während einer laufenden Show ist das deutlich sichtbar.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._trigger_reset()

    def _trigger_reset(self):
        self.setEnabled(False)
        self.setText("Reset läuft…")
        self._set_on_fixtures(self._attr, self._reset_value)
        QTimer.singleShot(self.HOLD_MS, self._make_revert())

    def _make_revert(self):
        # Revert-Closure haelt nur state/fids — funktioniert auch, wenn der
        # Button (Tab-Rebuild) inzwischen zerstoert wurde.
        state, attr, idle = self._state, self._attr, self._idle
        fids = [f.fid for f in self._fixtures]
        btn = self

        def _revert():
            for fid in fids:
                try:
                    state.set_programmer_value(fid, attr, idle)
                except Exception:
                    pass
            try:
                btn.setEnabled(True)
                btn.setText("⟳ Moving Head Reset…")
            except RuntimeError:
                pass   # Button wurde inzwischen geloescht
        return _revert
