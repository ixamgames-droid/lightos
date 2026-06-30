"""Matrix Engine — LED-Grid Effekte wie in QLC+.

Seit dem Programmer-Umbau ist eine Matrix eine **echte Funktion**
(`Function`-Subklasse, `FunctionType.RGBMatrix`). Dadurch:
  - wird sie im zentralen Renderer (`AppState._render_frame` →
    `FunctionManager.tick`) tatsaechlich ins DMX geschrieben (write()),
  - erscheint sie in der Bibliothek und ist auf VC-Buttons/Fader + MIDI legbar,
  - wird sie ueber den normalen `functions`-Block der Show gespeichert.

Der Matrix-Style (RGB/RGBW/Dimmer/Shutter) ist eine Kanalmaske: je Style
werden NUR die passenden Kanaele geschrieben, alle anderen bleiben unangetastet
(damit sich mehrere Matrix-Effekte ueberlagern ohne sich zu ueberschreiben).

Das Fixture-Grid sind einfach die fids der gewaehlten Geraete (1×N), siehe
`RgbMatrixView` (follow_selection).
"""
from __future__ import annotations
import math
import random
import time
from enum import Enum
from typing import TYPE_CHECKING

from .function import Function, FunctionType

if TYPE_CHECKING:
    from src.core.dmx.universe import Universe
    from src.core.database.models import PatchedFixture


class MatrixStyle(str, Enum):
    RGB     = "RGB"
    RGBW    = "RGBW"
    DIMMER  = "Dimmer"
    SHUTTER = "Shutter"


class RgbAlgorithm(str, Enum):
    PLAIN      = "Plain"
    # ── Konsolidierte Grundalgorithmen (Phase 3) ──────────────────────────────
    # Richtungs-/Bewegungs-Varianten sind jetzt PARAMETER (axis / movement /
    # origin / blend), nicht mehr eigene Algorithmen. Alte Shows werden ueber
    # _LEGACY_ALGO_MAP transparent migriert (siehe apply_dict).
    CHASE      = "Chase"      # Lauflicht: axis H/V/Diag · movement normal/bounce/center_out/outside_in · Schweif (ex-Komet) · color_cycle (ex-Multicolor)
    WIPE       = "Wipe"       # Wisch: axis · movement · edge_fade
    WAVE       = "Wave"       # Welle: origin links/rechts/oben/unten/center/radial (ex-Welle H / Diagonal-Welle / Ripple)
    GRADIENT   = "Gradient"   # Farbverlauf ueber die Color-Sequence: axis · blend smooth/steps (ex-Gradient H/V / Color Scroll)
    RAINBOW    = "Rainbow"    # Phase 4: + movement/spread/saturation/value
    FILL       = "Fill"       # Phase 4: zeitlicher Aufbau ueber fill_speed/loop_mode, Richtung, Kante
    RANDOM     = "Random"     # Phase 4: vereinheitlicht — mode dimmer/color/strobe/flash/sparkle/pulse, nur echte Fixtures (ex-Sparkle)
    COLORFADE  = "Color Fade" # Phase 4: Multi-Color-Crossfade ueber die Color-Sequence (deaktivierte Farben werden uebersprungen)
    STROBE     = "Strobe"     # ganzes Feld an/aus (Tempo = Speed)
    CHECKER    = "Schachbrett" # benachbarte Zellen abwechselnd Farbe A/B (rot-blau / rot-aus), optional pro Beat tauschen
    # ── Texturen / Einzel-Looks (bewusst eigenstaendig, nicht verschmolzen) ────
    RADAR      = "Radar"
    SPIRAL     = "Spirale"
    SINEPLASMA = "Sine Plasma"
    PINWHEEL   = "Windrad"               # rotierende Segmente c1/c2
    BREATHE    = "Atmen (Puls)"          # ganzes Feld pulsiert in c1 (Sinus)
    FIRE       = "Feuer"                 # flackernder Flammen-Look c1→c2
    RAIN       = "Regen"                 # fallende Tropfen je Spalte


# Migration: alte (Varianten-)Algorithmus-Namen -> (neuer Grundalgorithmus, params).
# Wird in apply_dict angewandt, BEVOR der Enum-Wert gebildet wird, damit alte
# Shows mit entfernten Algorithmen weiter laden (Rueckwaertskompatibilitaet #18).
_LEGACY_ALGO_MAP: dict[str, tuple[str, dict]] = {
    "Chase Horizontal":    ("Chase", {"axis": "H", "movement": "normal"}),
    "Chase Vertical":      ("Chase", {"axis": "V", "movement": "normal"}),
    "Chase Diagonal":      ("Chase", {"axis": "Diag", "movement": "normal"}),
    "Bounce H":            ("Chase", {"axis": "H", "movement": "bounce"}),
    "Bounce V":            ("Chase", {"axis": "V", "movement": "bounce"}),
    "Center→Außen":        ("Chase", {"movement": "center_out"}),
    "Außen→Center":        ("Chase", {"movement": "outside_in"}),
    "Komet Horizontal":    ("Chase", {"axis": "H", "movement": "normal", "fade": 0.3, "runner_width": 1}),
    "Chase Multicolor":    ("Chase", {"axis": "H", "movement": "normal", "runner_count": 1, "color_cycle": True}),
    "Wipe Horizontal":     ("Wipe", {"axis": "H"}),
    "Wipe Vertical":       ("Wipe", {"axis": "V"}),
    "Welle Horizontal":    ("Wave", {"origin": "left"}),
    "Diagonal Welle":      ("Wave", {"origin": "diag"}),
    "Ripple (Ringe)":      ("Wave", {"origin": "radial"}),
    "Gradient Horizontal": ("Gradient", {"axis": "H", "blend": "smooth"}),
    "Gradient Vertikal":   ("Gradient", {"axis": "V", "blend": "smooth"}),
    "Color Scroll":        ("Gradient", {"axis": "H", "blend": "steps"}),
    # Phase 4: Sparkle ist jetzt ein Random-Modus (kein eigener Algorithmus mehr).
    "Sparkle":             ("Random", {"mode": "sparkle"}),
}


# Farbe = (R, G, B) als int 0-255
Color = tuple[int, int, int]


def lerp_color(a: Color, b: Color, t: float) -> Color:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def hsv_to_rgb(h: float, s: float, v: float) -> Color:
    """h 0-360, s 0-1, v 0-1"""
    h = h % 360
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c
    if h < 60:   r, g, b = c, x, 0
    elif h < 120: r, g, b = x, c, 0
    elif h < 180: r, g, b = 0, c, x
    elif h < 240: r, g, b = 0, x, c
    elif h < 300: r, g, b = x, 0, c
    else:         r, g, b = c, 0, x
    return int((r+m)*255), int((g+m)*255), int((b+m)*255)


def _find_fixture(patch_cache, fid):
    for fx in patch_cache or ():
        if getattr(fx, "fid", None) == fid:
            return fx
    return None


def _axis_coord(col: int, row: int, cols: int, rows: int, axis: str) -> tuple[int, int]:
    """Position und Laenge entlang der gewaehlten Bewegungsachse — gemeinsame
    Logik fuer Chase/Wipe/Gradient, damit Richtung nicht je Algorithmus dupliziert
    wird. H=(col,cols), V=(row,rows), Diag=(col+row, cols+rows-1)."""
    if axis == "V":
        return row, max(1, rows)
    if axis in ("Diag", "diag", "Diagonal", "diagonal"):
        return col + row, max(1, cols + rows - 1)
    return col, max(1, cols)  # H (Default)


def _scale(rgb: Color, b: float) -> Color:
    """Skaliert eine Farbe mit Helligkeit b (0..1, geklemmt)."""
    if b <= 0.0:
        return (0, 0, 0)
    if b > 1.0:
        b = 1.0
    return (int(rgb[0] * b), int(rgb[1] * b), int(rgb[2] * b))


def grid_from_positions(positions: dict, cols: int, rows: int) -> list:
    """Baut eine dichte fixture_grid-Liste (Laenge cols*rows) mit None-Luecken
    aus einem {"col,row": fid}-Dict (FixtureGroup.positions_json). Out-of-range-
    Schluessel werden ignoriert; nicht belegte Zellen bleiben None (Luecke)."""
    grid: list = [None] * (cols * rows)
    for key, fid in (positions or {}).items():
        try:
            c_str, r_str = str(key).split(",")
            c, r = int(c_str), int(r_str)
        except Exception:
            continue
        if 0 <= c < cols and 0 <= r < rows:
            grid[r * cols + c] = int(fid)
    return grid


def is_gap(fixture_grid: list, idx: int) -> bool:
    """True, wenn die Matrix-Zelle ``idx`` eine bewusste Luecke ist
    (raeumlich vorhanden, aber kein echtes Fixture → kein Output, keine Farbe).

    Klar getrennt von „Zelle existiert raeumlich": die Zelle bleibt Teil der
    Matrixstruktur, bekommt aber nie Farbe/Dimmer/Strobe (Vorschau zeichnet sie
    sichtbar leer). Ein **leeres** fixture_grid (noch keine Geraete-Zuweisung)
    gilt als luecken-frei → die geraeteunabhaengige Demo-/Such-Vorschau zeigt
    weiterhin alle Zellen."""
    if not fixture_grid:
        return False
    if idx < 0 or idx >= len(fixture_grid):
        return True
    return fixture_grid[idx] is None


def _clamp8(v) -> int:
    try:
        return max(0, min(255, int(round(float(v)))))
    except (TypeError, ValueError):
        return 0


class ColorSequence:
    """Geordnete, live-editierbare Farbliste — das kanonische Farbmodell der
    Matrix (Anforderung #12).

    Jeder Eintrag ist ``[(r,g,b), enabled]``. Deaktivierte Farben werden von
    Fade-/Sequence-Effekten **uebersprungen**, bleiben aber erhalten (Live-
    Toggle). ``active_index`` = aktuell ausgewaehlte Farbe (fuer next/prev/
    selected-Aktionen der virtuellen Konsole).

    Rueckwaertskompatibilitaet: ``RgbMatrixInstance.color1/2/3`` sind Properties,
    die auf die ersten drei Eintraege zeigen — alter Code/alte Shows mit nur
    drei festen Farben funktionieren unveraendert weiter.
    """
    __slots__ = ("entries", "active_index")

    def __init__(self, colors=None):
        self.entries: list[list] = []
        for c in (colors or []):
            self.add(c)
        self.active_index = 0

    # ── Editieren ──────────────────────────────────────────────────────────
    def add(self, rgb, enabled: bool = True, index: int | None = None) -> int:
        entry = [(_clamp8(rgb[0]), _clamp8(rgb[1]), _clamp8(rgb[2])), bool(enabled)]
        if index is None or index >= len(self.entries):
            self.entries.append(entry)
        else:
            self.entries.insert(max(0, index), entry)
        return len(self.entries) - 1

    def remove(self, index: int):
        if 0 <= index < len(self.entries):
            self.entries.pop(index)
            if self.active_index >= len(self.entries):
                self.active_index = max(0, len(self.entries) - 1)

    def toggle(self, index: int):
        if 0 <= index < len(self.entries):
            self.entries[index][1] = not self.entries[index][1]

    def set_enabled(self, index: int, on: bool):
        if 0 <= index < len(self.entries):
            self.entries[index][1] = bool(on)

    def set_color(self, index: int, rgb):
        if 0 <= index < len(self.entries):
            self.entries[index][0] = (_clamp8(rgb[0]), _clamp8(rgb[1]), _clamp8(rgb[2]))

    def move(self, src: int, dst: int):
        if 0 <= src < len(self.entries) and 0 <= dst < len(self.entries):
            e = self.entries.pop(src)
            self.entries.insert(dst, e)

    # ── Lesen ──────────────────────────────────────────────────────────────
    def color_at(self, index: int, default: Color = (0, 0, 0)) -> Color:
        """Farbe an Position ``index``. Out-of-range faellt graceful auf die
        letzte vorhandene Farbe zurueck (damit color2/color3 nie crashen)."""
        if 0 <= index < len(self.entries):
            return self.entries[index][0]
        if self.entries:
            return self.entries[-1][0] if index >= 0 else self.entries[0][0]
        return default

    def enabled_colors(self) -> list[Color]:
        """Nur aktive Farben (fuer Fade/Sequence). Garantiert mind. 1 Eintrag."""
        out = [rgb for rgb, on in self.entries if on]
        if out:
            return out
        if self.entries:
            return [self.entries[0][0]]
        return [(0, 0, 0)]

    def all_colors(self) -> list[Color]:
        return [rgb for rgb, _on in self.entries]

    def selected(self, default: Color = (0, 0, 0)) -> Color:
        return self.color_at(self.active_index, default)

    def next(self) -> int:
        if self.entries:
            self.active_index = (self.active_index + 1) % len(self.entries)
        return self.active_index

    def prev(self) -> int:
        if self.entries:
            self.active_index = (self.active_index - 1) % len(self.entries)
        return self.active_index

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        """Iteriert ueber ALLE Eintraege und liefert deren ``(r,g,b)``-Tupel
        (konsistent mit ``len()``, das ebenfalls alle Eintraege zaehlt). So gilt
        ``list(seq) == seq.all_colors()`` und ``len(list(seq)) == len(seq)``."""
        return iter(rgb for rgb, _on in self.entries)

    def __getitem__(self, index: int) -> Color:
        """``(r,g,b)``-Tupel an ``index`` mit normaler Listen-Index-Semantik
        (negative Indizes erlaubt, Out-of-range wirft ``IndexError`` — anders als
        das graceful ``color_at()``, damit Iteration/Slicing korrekt terminiert)."""
        return self.entries[index][0]

    # ── Persistenz ───────────────────────────────────────────────────────────
    def to_list(self) -> list:
        return [{"rgb": list(rgb), "on": bool(on)} for rgb, on in self.entries]

    @classmethod
    def from_list(cls, data) -> "ColorSequence":
        seq = cls()
        for item in data or []:
            try:
                if isinstance(item, dict):
                    seq.add(tuple(item.get("rgb", (0, 0, 0))), item.get("on", True))
                else:
                    seq.add(tuple(item), True)
            except Exception:
                continue
        return seq


class DimmerSequence:
    """Geordnete, live-editierbare Dimmerwert-Liste — das Pendant zu
    :class:`ColorSequence` fuer den Dimmer-Style (ENG-08).

    Jeder Eintrag ist ``[level, enabled]`` mit ``level`` 0..255. Deaktivierte
    Stufen werden von der Sequenz **uebersprungen**, bleiben aber erhalten
    (Live-Toggle). ``active_index`` = aktuell ausgewaehlte Stufe (fuer
    next/prev/selected). So kann ein Dimmer-Chase pro Runde durch beliebig
    viele *explizite* Helligkeitswerte schalten (z. B. 255, 50, 100) — genau
    wie die Farbauswahl bei einer Color-Matrix, nur mit Dimmerwerten.
    """
    __slots__ = ("entries", "active_index")

    def __init__(self, levels=None):
        self.entries: list[list] = []
        for v in (levels or []):
            self.add(v)
        self.active_index = 0

    # ── Editieren ──────────────────────────────────────────────────────────
    def add(self, level, enabled: bool = True, index: int | None = None) -> int:
        entry = [_clamp8(level), bool(enabled)]
        if index is None or index >= len(self.entries):
            self.entries.append(entry)
        else:
            self.entries.insert(max(0, index), entry)
        return len(self.entries) - 1

    def remove(self, index: int):
        if 0 <= index < len(self.entries):
            self.entries.pop(index)
            if self.active_index >= len(self.entries):
                self.active_index = max(0, len(self.entries) - 1)

    def toggle(self, index: int):
        if 0 <= index < len(self.entries):
            self.entries[index][1] = not self.entries[index][1]

    def set_enabled(self, index: int, on: bool):
        if 0 <= index < len(self.entries):
            self.entries[index][1] = bool(on)

    def set_level(self, index: int, level):
        if 0 <= index < len(self.entries):
            self.entries[index][0] = _clamp8(level)

    def move(self, src: int, dst: int):
        if 0 <= src < len(self.entries) and 0 <= dst < len(self.entries):
            e = self.entries.pop(src)
            self.entries.insert(dst, e)

    # ── Lesen ──────────────────────────────────────────────────────────────
    def level_at(self, index: int, default: int = 0) -> int:
        """Stufe an Position ``index``. Out-of-range faellt graceful auf die
        letzte vorhandene Stufe zurueck."""
        if 0 <= index < len(self.entries):
            return self.entries[index][0]
        if self.entries:
            return self.entries[-1][0] if index >= 0 else self.entries[0][0]
        return default

    def enabled_levels(self) -> list[int]:
        """Nur aktive Stufen (fuer die Runden-Sequenz). Garantiert mind. 1."""
        out = [v for v, on in self.entries if on]
        if out:
            return out
        if self.entries:
            return [self.entries[0][0]]
        return [255]

    def all_levels(self) -> list[int]:
        return [v for v, _on in self.entries]

    def selected(self, default: int = 255) -> int:
        return self.level_at(self.active_index, default)

    def next(self) -> int:
        if self.entries:
            self.active_index = (self.active_index + 1) % len(self.entries)
        return self.active_index

    def prev(self) -> int:
        if self.entries:
            self.active_index = (self.active_index - 1) % len(self.entries)
        return self.active_index

    def __len__(self) -> int:
        return len(self.entries)

    # ── Persistenz ───────────────────────────────────────────────────────────
    def to_list(self) -> list:
        return [{"level": int(v), "on": bool(on)} for v, on in self.entries]

    @classmethod
    def from_list(cls, data) -> "DimmerSequence":
        seq = cls()
        for item in data or []:
            try:
                if isinstance(item, dict):
                    seq.add(item.get("level", 0), item.get("on", True))
                else:
                    seq.add(item, True)
            except Exception:
                continue
        return seq


class RgbMatrixInstance(Function):
    """RGB-Matrix als echte Funktion.

    Das ``fixture_grid`` (row-major Liste von fids oder None, Laenge = cols*rows)
    bestimmt, welche Geraete welche „Pixel" sind — so wird der Matrix-Style direkt
    auf eine Strahler-Gruppe angewandt (1×N). Eintraege koennen ``None`` sein =
    Luecke: raeumlich vorhanden (von _render gefaerbt), aber kein Fixture wird
    angesteuert. Animationsrate = ``matrix_speed`` (Schritte/s, bewusst getrennt
    vom generischen ``Function.speed``-Master, der auf [0.1,4.0] geklemmt wird).
    ``intensity`` (Function-Master) skaliert die Ausgabe und kann so an einen
    VC-Fader gebunden werden.
    """

    function_type = FunctionType.RGBMatrix
    tempo_sync_default = True

    def __init__(self, name: str = "RGB Matrix", fid: int | None = None, *,
                 cols: int = 8, rows: int = 4,
                 fixture_grid: list[int] | None = None,
                 algorithm: RgbAlgorithm = RgbAlgorithm.CHASE,
                 color1: Color = (255, 0, 0),
                 color2: Color = (0, 0, 255),
                 color3: Color = (0, 255, 0),
                 speed: float = 1.0,
                 direction: str = "forward",
                 drive_intensity: bool = False):
        super().__init__(name, fid)
        self.cols = cols
        self.rows = rows
        # None-Eintraege = Luecken (raeumlich vorhanden, kein Fixture)
        self.fixture_grid: list[int | None] = list(fixture_grid or [])
        # Gruppen-Bindung (nur fuer die Programmer-Listen-Filterung): Name der
        # Fixture-Gruppe, fuer die dieser Matrix-Effekt erstellt wurde. Bewusst per
        # NAME (nicht DB-id), weil Gruppen beim Show-Save/Load per Name neu angelegt
        # werden und ihre id sich dabei aendern kann. None = ungebunden (erscheint
        # in jeder Gruppe). Beeinflusst NICHT das Rendering/DMX — nur, unter welcher
        # Gruppe der Effekt im Programmer aufgelistet wird.
        self.source_group: str | None = None
        self.algorithm = algorithm
        # Kanonisches Farbmodell: eine live-editierbare ColorSequence. color1/2/3
        # sind Properties darauf (Rueckwaertskompatibilitaet, siehe unten).
        self.colors = ColorSequence([color1, color2, color3])
        # Schritte pro Sekunde (Animationsrate). Getrennt vom Function.speed-Master.
        self.matrix_speed = float(speed)
        self.direction = direction
        # Treibt die Matrix auch den Dimmer-/Intensitaets-Kanal („Fader") auf voll?
        # True  = selbststaendig (Farbe wird sofort sichtbar).
        # False = NUR Farbe; Helligkeit bleibt frei fuer eine separate Dimmer-Ebene
        #         (Fader/Dimmer-Effekt) -> Matrix als reine Farb-Ebene kombinierbar.
        # HINWEIS: Default ist False fuer neue Matrizen (reine Farb-Ebene);
        # from_dict laedt True fuer Alt-Shows (Rueckwaertskompatibilitaet R1).
        self.drive_intensity = bool(drive_intensity)
        # Style-Felder (Phase 3)
        self.style: MatrixStyle = MatrixStyle.RGB
        # Legacy/No-op: RGBW-Weiss wird in write() aus rgbw_split abgeleitet; Feld nur
        # fuer Back-compat-Serialisierung, nicht in der UI/VC exponiert.
        self.white_amount: int = 100       # 0–100 %, RGBW-Weissanteil (Legacy)
        self.intensity_min: int = 0        # Dimmer-Style Untergrenze (ohne dimmer_cycle)
        self.intensity_max: int = 255      # Dimmer-Style Obergrenze (ohne dimmer_cycle)
        # ENG-08: explizite Dimmerwert-Sequenz fuer den Dimmer-Chase. Aktiv nur,
        # wenn params["dimmer_cycle"] True ist (sonst greift intensity_min/max).
        # Pendant zur ColorSequence: pro Runde die naechste explizite Stufe.
        self.dimmer_levels = DimmerSequence([255, 128, 64])
        self.shutter_min: int = 0          # Shutter-Style Untergrenze
        self.shutter_max: int = 255        # Shutter-Style Obergrenze
        # Phase 4: unbeschraenkte Phase (kein % max(cols,rows) mehr)
        self._step: float = 0.0
        self._last_tick: float = 0.0
        # Phase 4: Algorithmus-Parameter-Dict
        self.params: dict = {}
        # Phase 6: Preset-Schnappschuss fuer Live-Overrides. Live-Aenderungen der
        # virtuellen Konsole muten die laufenden Felder; clear_live_override()
        # stellt diesen Schnappschuss wieder her (gespeicherte Werte), ohne dass
        # die VC etwas dauerhaft zerstoert. Wird bei from_dict/Save gesetzt.
        self._preset: dict | None = None
        # Phase 6: Freeze/Pause — friert die Animation ein (Phase laeuft nicht weiter),
        # Ausgabe bleibt aber bestehen. Per VC-Button (do_action "toggle_freeze").
        self._frozen: bool = False
        # DEMO-04: zuletzt gesehene Bus-Position (Stall-Erkennung in _advance_step).
        # None = noch keine; ein nicht-vorrueckender Bus (bpm>0, gleiche Position) loest
        # Free-Run statt Einfrieren aus.
        self._last_bus_pos: float | None = None

    def _on_start(self):
        self._step = 0.0
        self._last_bus_pos = None
        self._last_tick = time.monotonic()
        # WP-Tempo: bei Bus-Sync ankern. „Taktgleich" (align_on_start, Default) klinkt
        # den Effekt auf das gemeinsame Beat-Raster seines Bus ein (note_groove_start
        # legt bei frischer Groove den Downbeat auf jetzt); bewusst frei (False) ankert
        # auf die eigene aktuelle Bus-Position. bus_for_effect erzeugt feste Buses A-D
        # bei Bedarf, damit eine gespeicherte/zugewiesene A-D-Bindung sofort greift.
        bus_id = getattr(self, "tempo_bus_id", "") or ""
        if bus_id:
            try:
                from src.core.engine.tempo_bus import get_tempo_bus_manager
                bus = get_tempo_bus_manager().bus_for_effect(bus_id)
                if bus is not None:
                    if getattr(self, "align_on_start", True):
                        bus.note_groove_start(self)
                        self._beat_anchor = bus.take_anchor()
                    else:
                        self._beat_anchor = bus.position()
            except Exception:
                pass

    def sync_phase(self):
        """Setzt die Animations-Phase zurueck (Speed-Dial-Sync, SPD-03). Mehrere
        Effekte lassen sich so auf einen gemeinsamen Startpunkt angleichen.

        Bus-synchron (``tempo_bus_id`` gesetzt): re-ankert auf die aktuelle Bus-Position
        (``_beat_anchor = bus.position``), sodass ``local_beats`` wieder bei 0 startet —
        so beginnen alle Effekte derselben ``sync_group`` GEMEINSAM. ``_step`` wird
        in beiden Faellen auf 0 gesetzt (gemeinsamer Animations-Startpunkt)."""
        bus_id = getattr(self, "tempo_bus_id", "") or ""
        if bus_id:
            try:
                from src.core.engine.tempo_bus import get_tempo_bus_manager
                bus = get_tempo_bus_manager().bus_for_effect(bus_id)
                if bus is not None:
                    self._beat_anchor = bus.take_anchor()
                    self._last_tick = time.monotonic()
                    self._step = 0.0
                    # ENG-10: Stall-Cache loeschen. Hatte die Matrix vorher gegen
                    # einen STEHENDEN Bus gerendert, gilt ``_last_bus_pos == pos``;
                    # ohne Reset wuerde der DEMO-04-Stall-Check (``dt>0`` + ``pos==last``)
                    # im naechsten Frame die Bus-Sync ueberspringen und free-runnen
                    # -> der gerade gesetzte Anker/Phasen-Offset (Sync-Aktion) wuerde
                    # ignoriert, bis der Bus vorrueckt.
                    self._last_bus_pos = None
                    return
            except Exception:
                pass
        self._step = 0.0
        self._last_tick = time.monotonic()

    # ── Farb-Kompatibilitaet: color1/2/3 zeigen auf die ColorSequence ──────────
    # So funktioniert aller bestehender Code (View, Show-Builder, Tests, _render),
    # waehrend die Sequence das kanonische, beliebig lange Farbmodell ist.
    @property
    def color1(self) -> Color:
        return self.colors.color_at(0, (255, 0, 0))

    @color1.setter
    def color1(self, rgb):
        self._set_seq_color(0, rgb)

    @property
    def color2(self) -> Color:
        return self.colors.color_at(1, (0, 0, 255))

    @color2.setter
    def color2(self, rgb):
        self._set_seq_color(1, rgb)

    @property
    def color3(self) -> Color:
        return self.colors.color_at(2, (0, 255, 0))

    @color3.setter
    def color3(self, rgb):
        self._set_seq_color(2, rgb)

    def _set_seq_color(self, i: int, rgb):
        """Setzt die i-te Sequence-Farbe; legt fehlende Eintraege bei Bedarf an."""
        while len(self.colors) <= i:
            self.colors.add((0, 0, 0))
        self.colors.set_color(i, rgb)

    # ── Style-Hilfsmethoden ───────────────────────────────────────────────────

    def _pixel_brightness(self, rgb: Color) -> float:
        """Helligkeit eines Pixels als 0.0..1.0 (max-Kanal)."""
        return max(rgb) / 255.0

    def _scalar_level(self, rgb: Color, lo: int, hi: int) -> int:
        """Mappt die Pixel-Helligkeit in [lo, hi] und gibt einen int-Wert 0..255 zurueck."""
        L = self._pixel_brightness(rgb)
        return max(0, min(255, int(round(lo + (hi - lo) * L))))

    def _dimmer_output(self, rgb: Color) -> int:
        """Dimmer-Kanalwert fuer ein gerendertes Pixel (ENG-08).

        Bei aktivem ``dimmer_cycle`` (nur CHASE) liefert ``_render`` bereits
        explizite Grau-Stufen ``(lvl, lvl, lvl)`` aus der ``DimmerSequence`` —
        dann den Wert *direkt* durchreichen: die programmierten Stufen SIND die
        Ausgabe, ``intensity_min``/``intensity_max`` werden bewusst ignoriert
        (sonst wuerde der gewuenschte Wert verschoben). Sonst das bisherige
        Verhalten: Pixel-Helligkeit linear in ``[intensity_min, intensity_max]``.
        """
        if self.algorithm == RgbAlgorithm.CHASE and self.params.get("dimmer_cycle"):
            return max(0, min(255, int(round(self._pixel_brightness(rgb) * 255))))
        return self._scalar_level(rgb, self.intensity_min, self.intensity_max)

    def preview_pixels(self) -> list[Color]:
        """Style-aware Pixelliste fuer die Vorschau (ruft intern _generate()).

        RGB/RGBW: unveraendert — die echten Farben.
        DIMMER:   Grau-Pixel entsprechend der Dimmer-Skalierung.
        SHUTTER:  Grau-Pixel entsprechend der Shutter-Skalierung.
        """
        grid = self._generate()
        if self.style in (MatrixStyle.RGB, MatrixStyle.RGBW):
            return grid
        if self.style == MatrixStyle.DIMMER:
            result = []
            for rgb in grid:
                v = self._dimmer_output(rgb)
                result.append((v, v, v))
            return result
        if self.style == MatrixStyle.SHUTTER:
            result = []
            for rgb in grid:
                v = self._scalar_level(rgb, self.shutter_min, self.shutter_max)
                result.append((v, v, v))
            return result
        return grid

    def tick(self) -> dict[int, dict[str, int]]:
        """Nur fuer die Vorschau (zeitbasiert via monotonic). Treibt _step voran
        und liefert {fid: {color_r/g/b}}. Der echte Output laeuft ueber write().

        Achtung: liefert IMMER rohe color_r/g/b — die Style-Kanalmaske (write()
        schreibt bei DIMMER/SHUTTER intensity/shutter statt Farbe) wird hier NICHT
        beruecksichtigt. Wer style-aware Pixel braucht, nutzt preview_pixels()
        (style-gemappte Graustufen)."""
        if not self._running or not self.fixture_grid:
            return {}
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        # WP-Tempo: self._step bus-synchron oder frei fortschreiben (Vorschau).
        self._advance_step(dt)

        grid = self._generate()
        result = {}
        for idx, fid in enumerate(self.fixture_grid):
            if fid is None:
                continue  # Luecke: kein Vorschau-Eintrag
            if idx >= len(grid):
                break
            r, g, b = grid[idx]
            result[fid] = {"color_r": r, "color_g": g, "color_b": b}
        return result

    def _advance_step(self, dt: float) -> None:
        """Schreibt ``self._step`` fort.

        Bus-synchron (``tempo_bus_id`` gesetzt UND Bus laeuft, bpm>0):
            ``self._step = (bus.position - _beat_anchor) * tempo_multiplier + phase_offset``
        — Einheit Beats (1 Schritt = 1 Beat). So koppeln zwei Matrizen auf demselben
        Bus exakt (z. B. Farbe ×1, Dimmer ×2 phasengleich), unabhaengig von Frame-Jitter
        und Startzeitpunkt, weil beide aus derselben Bus-Position + demselben Anker ableiten.
        Sonst Free-Run wie bisher: ``matrix_speed × Function.speed × dt`` (byte-identisch).
        ``_frozen`` haelt die Animation in beiden Modi an.

        DEMO-04: Ein gekoppelter Bus mit ``bpm>0``, dessen **Position nicht vorrueckt**
        (keine laufende ``advance_frame``-Schleife — Vorschau-/Probe-/Validierungs-Render,
        pausierte Bus-Uhr), friert NICHT mehr ein: er faellt auf Free-Run zurueck, statt
        dunkel zu erstarren (bei Dimmer-Style = Black-out). Erkannt am Positions-Delta
        seit dem letzten Frame; bei Bus-Wiederanlauf snappt der naechste Frame zurueck auf
        Bus-Sync. Live (Render-Thread tickt ``advance_frame`` jeden Frame) bleibt
        byte-identisch, weil die Position dort immer vorrueckt. Globaler Freeze (F5) haelt
        bewusst weiter an."""
        if self._frozen:
            return
        bus_id = getattr(self, "tempo_bus_id", "") or ""
        if bus_id:
            bus = None
            _tbm = None
            try:
                from src.core.engine.tempo_bus import get_tempo_bus_manager
                _tbm = get_tempo_bus_manager()
                bus = _tbm.get(bus_id)
            except Exception:
                bus = None
            if bus is not None:
                bpm, _bc, _bp, pos = bus.snapshot()
                if bpm > 0:
                    last = getattr(self, "_last_bus_pos", None)
                    self._last_bus_pos = pos
                    # Bus-Sync, wenn der Bus vorrueckt (``pos != last``), beim ersten
                    # Frame (``last is None``) ODER bei einer Null-dt-Re-Evaluation
                    # (``dt <= 0`` — z. B. direkt nach ``sync()`` neu auswerten): dann den
                    # bus-synchronen Wert frisch aus Position + Anker berechnen.
                    if last is None or pos != last or dt <= 0.0:
                        # Echte Bus-Synchronitaet: zwei Matrizen auf demselben Bus koppeln
                        # exakt (z. B. Farbe ×1, Dimmer ×2 phasengleich).
                        mult = getattr(self, "tempo_multiplier", 1.0) or 1.0
                        off = getattr(self, "phase_offset", 0.0) or 0.0
                        anchor = getattr(self, "_beat_anchor", 0.0)
                        # round(...,9) killt die Float-Kante an ganzzahligen Beats: die
                        # Bus-Position landet oft als N-1e-16, und int(N-1e-16)=N-1 → ein
                        # STROBE (on=int(p)%2==0) liefe genau am Beat 1 Frame falsch. 9
                        # Nachkommastellen sind fuers Rendering mehr als genug; betrifft
                        # NUR den bus-synchronen Pfad (Free-Run bleibt byte-identisch).
                        self._step = round((pos - anchor) * mult + off, 9)
                        return
                    # bpm>0, aber Position steht ueber einen echten Zeitschritt (dt>0):
                    # Bus rueckt nicht vor (keine advance_frame-Schleife) → DEMO-04:
                    # nicht einfrieren, frei weiterlaufen. Nur globaler Freeze haelt an.
                    if _tbm is not None and _tbm.is_frozen():
                        return
                else:
                    # bpm 0 (Bus noch nicht gestartet): Free-Run, ausser globalem Freeze.
                    # Anker-Position vergessen, damit der Bus-Wiederanlauf sauber re-synct.
                    self._last_bus_pos = None
                    if _tbm is not None and _tbm.is_frozen():
                        return
            else:
                self._last_bus_pos = None
        # Free-Run (alt-Verhalten, byte-identisch).
        rate = self.matrix_speed * max(0.0, float(self.speed))
        self._step = self._step + rate * dt

    def write(self, universes: dict[int, "Universe"],
              patch_cache: list["PatchedFixture"],
              dt: float,
              function_registry=None):
        """Per-Frame-Output (vom FunctionManager getickt): faerbt die Grid-Fixtures.

        Schreibt color_r/g/b je Pixel und hebt vorhandene Intensitaets-/Dimmer-
        Kanaele der beteiligten Geraete auf voll, damit die Farbe sichtbar wird
        (der Programmer-/Submaster-Dimmer skaliert spaeter im Renderer)."""
        if not self._running or not self.fixture_grid:
            return
        # WP-Tempo: self._step bus-synchron (tempo_bus_id) ODER frei (matrix_speed ×
        # Function.speed × dt, byte-identisch) fortschreiben; Freeze haelt an.
        self._advance_step(dt)
        grid = self._render(self._step)
        try:
            from src.core.app_state import get_channels_for_patched
        except Exception:
            return
        for idx, fid in enumerate(self.fixture_grid):
            if fid is None:
                continue  # Luecke: kein DMX-Schreiben
            if idx >= len(grid):
                break
            r, g, b = grid[idx]
            rgb = (r, g, b)
            fx = _find_fixture(patch_cache, fid)
            if fx is None:
                continue
            universe = universes.get(fx.universe)
            if universe is None:
                continue
            chans = get_channels_for_patched(fx)
            # M1: Per-Effekt-Master (intensity) auf die Farbkanaele anwenden — aber
            # NUR wenn der generische FunctionManager-Merge sie nicht ohnehin
            # skaliert. Der Merge skaliert pro Fixture entweder dessen Dimmer-Kanal
            # (falls vorhanden) ODER – als Fallback – die Farbkanaele. Hat das
            # Fixture also einen eigenen Dimmer, den die Matrix NICHT treibt
            # (drive_intensity False), bleibt der Dimmer unangetastet -> der Merge
            # skaliert nichts -> die Farben muessen hier gedimmt werden. Bei reinen
            # Farb-Fixtures (Fallback skaliert die Farben) oder drive_intensity True
            # (Dimmer-Kanal wird gedimmt) uebernimmt der Merge -> kein Doppel-Dimmen.
            inten = max(0.0, min(1.0, float(self.intensity)))
            has_dimmer = any((c.attribute or "").lower() in ("intensity", "dimmer", "master")
                             for c in chans)
            scale_colors = has_dimmer and not self.drive_intensity and inten < 0.999
            # Farbrad-Fallback: hat das Fixture KEINE RGB-Kanaele, aber einen
            # Farbrad-Kanal (attribute=="color"), wird der passende Slot gesetzt.
            # Der Slot-Wert wird bewusst NICHT mit intensity skaliert (das wuerde
            # den Slot verschieben → andere Farbe); Helligkeit gehoert auf den
            # Dimmer. Der RGB(W)-Pfad bleibt davon bit-identisch unberuehrt.
            has_rgb = any((c.attribute or "").lower() in ("color_r", "color_g", "color_b")
                          for c in chans)
            wheel_val: int | None = None
            if not has_rgb:
                try:
                    from src.core.color_utils import color_attrs_for_fixture
                    wheel_val = color_attrs_for_fixture(chans, rgb).get("color")
                except Exception:
                    wheel_val = None
            # RGBW: echtes Weiss -> Weissanteil cw=min(r,g,b) auf den W-Kanal, RGB
            # nur der Rest (r-cw, g-cw, b-cw). Pures Weiss laeuft damit rein ueber
            # den weissen Chip (R=G=B=0), nicht zusaetzlich ueber RGB. RGB-Style:
            # r,g,b unveraendert, der W-Kanal wird nie angefasst. Gemeinsame Quelle
            # fuer die Subtraktion: color_utils.rgbw_split (siehe test_color_white_channel).
            if self.style == MatrixStyle.RGBW:
                from src.core.color_utils import rgbw_split
                cr, cg, cb, cw = rgbw_split(r, g, b)
            else:
                cw = 0
                cr, cg, cb = r, g, b
            for ch in chans:
                attr = (ch.attribute or "").lower()
                # ── Style-Kanalmaske ────────────────────────────────────────
                if self.style in (MatrixStyle.RGB, MatrixStyle.RGBW):
                    if attr == "color_r":
                        val = cr
                    elif attr == "color_g":
                        val = cg
                    elif attr == "color_b":
                        val = cb
                    elif attr == "color_w" and self.style == MatrixStyle.RGBW:
                        val = cw
                    elif attr == "color" and not has_rgb and wheel_val is not None:
                        # Farbrad: Slot setzen, NICHT mit intensity skalieren
                        # (Helligkeit gehoert auf den Dimmer, nicht aufs Farbrad).
                        val = wheel_val
                    elif attr in ("intensity", "dimmer", "master"):
                        if not self.drive_intensity:
                            continue
                        val = 255
                    else:
                        continue  # andere Kanaele unangetastet lassen
                    if scale_colors and attr in ("color_r", "color_g", "color_b", "color_w"):
                        val = int(val * inten)
                elif self.style == MatrixStyle.DIMMER:
                    if attr in ("intensity", "dimmer", "master"):
                        val = self._dimmer_output(rgb)
                    else:
                        continue  # Farb-/Shutter-Kanaele unangetastet lassen
                elif self.style == MatrixStyle.SHUTTER:
                    if attr == "shutter":
                        val = self._scalar_level(rgb, self.shutter_min, self.shutter_max)
                    else:
                        continue  # Farb-/Dimmer-Kanaele unangetastet lassen
                else:
                    continue
                # ────────────────────────────────────────────────────────────
                addr = fx.address + ch.channel_number - 1
                if 1 <= addr <= 512:
                    universe.set_channel(addr, max(0, min(255, int(val))))

    def _render(self, phase: float) -> list[Color]:
        """Reine Rendering-Funktion der Phase (Phase 4).

        Verwendet ``phase`` statt ``self._step`` direkt, damit die Methode
        unabhaengig vom internen Zustand aufrufbar ist (z. B. Stetigkeit-Tests).
        Richtung wird hier angewandt: direction=="reverse" negiert die Phase.
        Python-Modulo liefert korrekte Ergebnisse auch fuer negative Werte.
        """
        cols, rows = self.cols, self.rows
        # MXP-02: Phasen-Versatz (versetzte Effekte).
        phase = phase + float(self.params.get("offset", 0.0))
        # Richtung anwenden: reverse negiert die Phase
        p = -phase if self.direction == "reverse" else phase
        pixels: list[Color] = [(0, 0, 0)] * (cols * rows)
        algo = self.algorithm
        # Kanonische Farben (Sequence) + c1/2/3-Sicht fuer die Textur-Algorithmen.
        enabled = self.colors.enabled_colors()
        c1, c2, c3 = self.color1, self.color2, self.color3

        # ── Konsolidierte Grundalgorithmen → eigene Render-Helfer (Phase 3) ───────
        # Bewegung/Richtung/Ursprung sind Parameter, keine eigenen Algorithmen mehr.
        if algo == RgbAlgorithm.CHASE:
            return self._render_chase(p, cols, rows, enabled)
        if algo == RgbAlgorithm.WIPE:
            return self._render_wipe(p, cols, rows, c1, c2)
        if algo == RgbAlgorithm.WAVE:
            return self._render_wave(p, cols, rows, c1, c2)
        if algo == RgbAlgorithm.GRADIENT:
            return self._render_gradient(p, cols, rows, enabled)
        if algo == RgbAlgorithm.RAINBOW:
            return self._render_rainbow(p, cols, rows)
        if algo == RgbAlgorithm.FILL:
            return self._render_fill(p, cols, rows, enabled)
        if algo == RgbAlgorithm.RANDOM:
            return self._render_random(p, cols, rows, enabled)
        if algo == RgbAlgorithm.COLORFADE:
            return self._render_colorfade(p, cols, rows, enabled)
        if algo == RgbAlgorithm.CHECKER:
            return self._render_checker(p, cols, rows, enabled)

        # ── Texturen / Einzel-Looks: per-Zelle (bewusst eigenstaendig) ────────────
        for row in range(rows):
            for col in range(cols):
                idx = row * cols + col

                if algo == RgbAlgorithm.PLAIN:
                    pixels[idx] = c1

                elif algo == RgbAlgorithm.RADAR:
                    # Phase 4: wrap-sicherer Winkelstrahl (kuerzeste Winkeldistanz mod 2pi)
                    # Kein Sprung an der 360->0-Naht, framerate-unabhaengig, rastergroessen-unabhaengig.
                    cx, cy = (cols - 1) / 2.0, (rows - 1) / 2.0
                    ang = math.atan2(row - cy, col - cx)            # -pi..pi
                    beam = (p * 0.1 * 2 * math.pi) % (2 * math.pi)  # 0..2pi, 0.1 Umdrehung/Schritt
                    signed = ((ang - beam + math.pi) % (2 * math.pi)) - math.pi  # -pi..pi, 0=am Strahl
                    d = abs(signed)
                    beam_width = float(self.params.get("beam_width", 0.15))      # Anteil (0.02..1.0)
                    fade = float(self.params.get("fade", 0.3))                   # Schweif 0..1
                    invert = bool(self.params.get("invert", False))
                    bw = max(0.01, beam_width) * math.pi
                    core = max(0.0, 1.0 - d / bw) if d <= bw else 0.0
                    tail_arc = fade * math.pi
                    tail = 0.0
                    if fade > 0 and -tail_arc <= signed < 0:        # nachlaufender Schweif hinter dem Strahl
                        tail = (1.0 + signed / tail_arc) * 0.6
                    bright = max(core, tail)
                    if invert:
                        bright = 1.0 - bright
                    pixels[idx] = (int(c1[0] * bright), int(c1[1] * bright), int(c1[2] * bright))

                elif algo == RgbAlgorithm.SINEPLASMA:
                    v = (math.sin(col * 0.8 + p) +
                         math.sin(row * 0.8 + p * 0.7) +
                         math.sin((col + row) * 0.5 + p * 1.3)) / 3
                    t = (v + 1) / 2
                    pixels[idx] = lerp_color(c1, c2, t)

                elif algo == RgbAlgorithm.SPIRAL:
                    # Rotierender Spiralarm (winkel- + radienbasiert).
                    cx = (cols - 1) / 2.0
                    cy = (rows - 1) / 2.0
                    c1 = self.color1
                    off = (0, 0, 0)
                    invert = bool(self.params.get("invert", False))
                    maxr = math.hypot(cx, cy) or 1e-9
                    ang = math.atan2(row - cy, col - cx)
                    a = (ang / (2 * math.pi)) % 1.0
                    d = math.hypot(col - cx, row - cy)
                    turns = float(self.params.get("turns", 1.0))
                    bw = max(0.01, float(self.params.get("beam_width", 0.15)))
                    s = (a + (d / maxr) * turns - p * 0.1) % 1.0
                    lit = s < bw
                    pixels[idx] = c1 if (lit != invert) else off

                # ── Texturen / Puls / Natur ───────────────────────────────────

                elif algo == RgbAlgorithm.BREATHE:
                    # Ganzes Feld pulsiert in c1; startet bei 0 (1-cos).
                    bright = (1.0 - math.cos(p)) / 2.0
                    pixels[idx] = (int(c1[0] * bright), int(c1[1] * bright), int(c1[2] * bright))

                elif algo == RgbAlgorithm.STROBE:
                    # Ganzes Feld an/aus; Tempo ueber matrix_speed/Speed-Master.
                    on = int(p) % 2 == 0
                    pixels[idx] = c1 if on else (0, 0, 0)

                elif algo == RgbAlgorithm.FIRE:
                    # Flackernder Flammen-Look: c1 (Glut) → c2 (Spitze), Spitzen
                    # eher oben (kleiner row). Zufalls-Effekt wie SPARKLE.
                    import random
                    hfac = 1.0 - (row / max(1, rows - 1)) if rows > 1 else 1.0
                    t = random.random() * hfac
                    flick = random.uniform(0.5, 1.0)
                    base = lerp_color(c1, c2, t)
                    pixels[idx] = (int(base[0] * flick), int(base[1] * flick), int(base[2] * flick))

                elif algo == RgbAlgorithm.RAIN:
                    # Fallende Tropfen je Spalte (deterministischer Versatz pro Spalte),
                    # Kopf hell, kurzer Schweif nach oben.
                    fade = float(self.params.get("fade", 0.3))
                    off_col = (col * 53) % max(1, rows)
                    head = (p * 0.8 + off_col) % rows
                    d = (row - head) % rows                 # Abstand oberhalb des Kopfes
                    taillen = max(1.0, fade * rows)
                    bright = max(0.0, 1.0 - d / taillen)
                    pixels[idx] = (int(c1[0] * bright), int(c1[1] * bright), int(c1[2] * bright))

                elif algo == RgbAlgorithm.PINWHEEL:
                    # Rotierende Segmente (Windrad) abwechselnd c1/c2.
                    cx, cy = (cols - 1) / 2.0, (rows - 1) / 2.0
                    # #5: segment_count (Fallback runner_count fuer Alt-Shows/VC).
                    seg = max(1, int(self.params.get("segment_count",
                                                     self.params.get("runner_count", 1))))
                    invert = bool(self.params.get("invert", False))
                    ang = math.atan2(row - cy, col - cx)
                    a = (ang / (2 * math.pi) + p * 0.05) % 1.0
                    even = int(a * seg * 2) % 2 == 0
                    pixels[idx] = c1 if (even != invert) else c2

        return pixels

    def _render_checker(self, p: float, cols: int, rows: int,
                        enabled: list[Color]) -> list[Color]:
        """Schachbrett/Wechsel: benachbarte Zellen abwechselnd Farbe A/B/...

        Statisches raeumliches Muster A/B/A/B ueber die Fixtures (Kachelgroesse
        ``tile``). Bei ``blink`` (Default) tauschen die Farben pro Beat
        (= Wechsellicht/Blinken): rot-blau -> blau-rot bzw. rot-aus -> aus-rot.
        Nutzt die aktiven Farben der Color-Sequence (2 = A/B; eine schwarze Farbe
        (0,0,0) ergibt 'rot-nichts'). Reihenfolge row-major (idx = row*cols+col).
        """
        n = len(enabled) or 1
        tile = max(1, int(self.params.get("tile", 1)))
        step = int(p) if bool(self.params.get("blink", True)) else 0
        pixels: list[Color] = []
        for row in range(rows):
            for col in range(cols):
                k = ((col + row) // tile + step) % n
                pixels.append(enabled[k])
        return pixels

    # ── Konsolidierte Grundalgorithmen (Phase 3) ──────────────────────────────
    # Bewegung/Richtung/Ursprung als Parameter statt als getrennte Algorithmen.
    # Luecken werden von write()/tick() ohnehin uebersprungen; _render liefert das
    # volle Raster (Lücken zaehlen raeumlich mit, bekommen aber keinen Output #6).

    def _real_indices(self, n: int) -> list[int]:
        """Indizes der Zellen mit ECHTEM Fixture (Basis fuer Random/Fill, #6).

        Leeres fixture_grid (geraeteunabhaengige Vorschau/Tests) → alle Zellen
        gelten als echt. Sonst nur die Nicht-Luecken (fixture_grid[idx] is not None).
        So waehlt Random nie eine Luecke und Fill zaehlt nur echte Fixtures."""
        fg = self.fixture_grid
        if not fg:
            return list(range(n))
        return [i for i in range(n) if i < len(fg) and fg[i] is not None]

    def _render_chase(self, p: float, cols: int, rows: int, enabled: list) -> list[Color]:
        """Lauflicht. params: axis(H/V/Diag), movement(normal/bounce/center_out/
        outside_in), runner_count, runner_width, fade(Schweif), color_cycle, invert."""
        params = self.params
        axis = str(params.get("axis", "H"))
        movement = str(params.get("movement", "normal"))
        width = max(1, int(params.get("runner_width", 1)))
        count = max(1, int(params.get("runner_count", 1)))
        # After Fade (Abschnitt 5): Nachfaden in % (0..100) -> 0..1. Alt-Shows mit
        # "fade" (0..1) werden in apply_dict migriert; hier nur der neue Key.
        fade = max(0.0, min(100.0, float(params.get("after_fade", 30.0)))) / 100.0
        invert = bool(params.get("invert", False))
        n = cols * rows
        pixels: list[Color] = [(0, 0, 0)] * n

        # ENG-08: Dimmer-Style-Chase mit eigener Dimmerwert-Sequenz — pro Runde
        # die naechste explizite Stufe (0..255) statt einer Farbe. base wird ein
        # Grau (lvl,lvl,lvl); _dimmer_output/write() reichen den Wert direkt auf
        # den Dimmer-Kanal durch (intensity_min/max werden dann ignoriert).
        # Reihenfolge normal / zufaellig / Ping-Pong (dimmer_order), Intervall
        # wie bei der Color-Sequence (dimmer_interval).
        if self.style == MatrixStyle.DIMMER and params.get("dimmer_cycle"):
            levels = self.dimmer_levels.enabled_levels()
            length_hint = cols if axis == "H" else (rows if axis == "V" else max(1, cols + rows - 1))
            interval = max(1, int(params.get("dimmer_interval", 1)))
            rnd = int(p) // max(1, length_hint * interval)   # Runden-Index (×Intervall)
            nl = len(levels)
            order = str(params.get("dimmer_order", "normal"))
            if order == "random":
                lvl = levels[random.Random((rnd * 2654435761) & 0x7FFFFFFF).randrange(nl)]
            elif order == "pingpong" and nl > 2:
                period = 2 * (nl - 1)
                pos = rnd % period
                lvl = levels[pos if pos < nl else period - pos]
            else:  # normal
                lvl = levels[rnd % nl]
            base = (lvl, lvl, lvl)
        # Farbe: optional pro Runde durch die Color-Sequence wechselnd (Abschnitt 6).
        # Reihenfolge normal / zufällig / Ping-Pong (color_order).
        elif params.get("color_cycle") and enabled:
            length_hint = cols if axis == "H" else (rows if axis == "V" else max(1, cols + rows - 1))
            # MXP-01: Farbe erst alle N Durchlaeufe wechseln (Default 1 = jeder Lauf).
            interval = max(1, int(params.get("color_interval", 1)))
            rnd = int(p) // max(1, length_hint * interval)   # Runden-Index (×Intervall)
            nc = len(enabled)
            order = str(params.get("color_order", "normal"))
            if order == "random":
                base = enabled[random.Random((rnd * 2654435761) & 0x7FFFFFFF).randrange(nc)]
            elif order == "pingpong" and nc > 2:
                period = 2 * (nc - 1)
                pos = rnd % period
                base = enabled[pos if pos < nc else period - pos]
            else:  # normal
                base = enabled[rnd % nc]
        else:
            base = self.colors.selected(enabled[0] if enabled else (255, 0, 0))

        if movement in ("center_out", "outside_in"):
            # Expandierender/kontrahierender Ring ab Matrix-Mitte (Chebyshev).
            cx, cy = (cols - 1) / 2.0, (rows - 1) / 2.0
            maxr = max(cx, cy)
            front = p % (maxr + width + 1)
            for row in range(rows):
                for col in range(cols):
                    base_d = max(abs(col - cx), abs(row - cy))
                    d = base_d if movement == "center_out" else (maxr - base_d)
                    lit = (d <= front) and (d > front - width)
                    bright = 1.0 if lit else 0.0
                    if invert:
                        bright = 1.0 - bright
                    pixels[row * cols + col] = _scale(base, bright)
            return pixels

        # Linear: normal (mit optionalem Schweif = ex-Komet) / bounce (Pingpong).
        for row in range(rows):
            for col in range(cols):
                pos, length = _axis_coord(col, row, cols, rows, axis)
                if movement == "bounce":
                    span = max(1, length - 1)
                    head = span - abs((int(p) % (2 * span)) - span)
                    bright = 1.0 if abs(pos - head) < width else 0.0
                else:  # normal
                    # runner_width = vollwertiger solider Kopf (unabhaengig vom After-
                    # Fade); danach NUR bei fade>0 ein linearer Schweif. Mehrere
                    # Laeufer akkumulieren via max(); solider Kopf darf brechen.
                    spacing = length / count
                    fadelen = fade * length
                    bright = 0.0
                    for k in range(count):
                        head = (p + k * spacing) % length
                        dist = (head - pos) % length      # wie weit pos HINTER dem Kopf liegt
                        if dist < width:                  # solider Kopf
                            bright = 1.0
                            break
                        if fade > 0.0 and dist < width + fadelen:   # linearer Schweif
                            bright = max(bright, 1.0 - (dist - width) / max(1.0, fadelen))
                if invert:
                    bright = 1.0 - bright
                pixels[row * cols + col] = _scale(base, bright)
        return pixels

    def _render_wipe(self, p: float, cols: int, rows: int, c1: Color, c2: Color) -> list[Color]:
        """Wisch c1 ueber Hintergrund c2. params: axis, movement, edge_fade."""
        params = self.params
        axis = str(params.get("axis", "H"))
        movement = str(params.get("movement", "normal"))
        edge = max(0.0, float(params.get("edge_fade", 0.0)))
        n = cols * rows
        pixels: list[Color] = [(0, 0, 0)] * n
        cx, cy = (cols - 1) / 2.0, (rows - 1) / 2.0
        maxr = max(cx, cy) or 1.0
        for row in range(rows):
            for col in range(cols):
                pos, length = _axis_coord(col, row, cols, rows, axis)
                if movement in ("center_out", "outside_in"):
                    frac = max(abs(col - cx), abs(row - cy)) / maxr
                    if movement == "outside_in":
                        frac = 1.0 - frac
                    t = (p % length) / length
                elif movement == "bounce":
                    frac = pos / length
                    tt = (p % (2 * length)) / length
                    t = tt if tt <= 1.0 else (2.0 - tt)
                else:  # normal
                    frac = pos / length
                    t = (p % length) / length
                if edge > 0.0:
                    m = max(0.0, min(1.0, (t - frac) / edge + 0.5))
                    pixels[row * cols + col] = lerp_color(c2, c1, m)
                else:
                    pixels[row * cols + col] = c1 if frac < t else c2
        return pixels

    def _render_wave(self, p: float, cols: int, rows: int, c1: Color, c2: Color) -> list[Color]:
        """Welle. params: origin(left/right/top/bottom/center/radial), density, spread."""
        params = self.params
        origin = str(params.get("origin", "left"))
        density = float(params.get("density", params.get("turns", 1.0)))
        spread = max(0.1, float(params.get("spread", 1.0)))
        n = cols * rows
        pixels: list[Color] = [(0, 0, 0)] * n
        cx, cy = (cols - 1) / 2.0, (rows - 1) / 2.0
        for row in range(rows):
            for col in range(cols):
                if origin == "radial":
                    dist = math.hypot(col - cx, row - cy)
                    v = math.sin(dist * density - p)
                    pixels[row * cols + col] = lerp_color(c1, c2, (v + 1.0) / 2.0)
                    continue
                if origin in ("top", "bottom"):
                    coord = row
                elif origin == "center":
                    coord = abs(col - cx) + abs(row - cy)
                elif origin in ("diag", "Diag"):
                    coord = col + row
                else:  # left / right
                    coord = col
                if origin in ("right", "bottom"):
                    coord = -coord
                v = math.sin(coord * 0.6 * density - p)
                bright = max(0.0, v)
                if spread != 1.0 and bright > 0.0:
                    bright = bright ** (1.0 / spread)
                pixels[row * cols + col] = _scale(c1, bright)
        return pixels

    def _render_gradient(self, p: float, cols: int, rows: int, enabled: list) -> list[Color]:
        """Scrollender Farbverlauf ueber die Color-Sequence. params: axis,
        blend(smooth/steps). steps = harte Baender (ex-Color-Scroll)."""
        params = self.params
        axis = str(params.get("axis", "H"))
        blend = str(params.get("blend", "smooth"))
        cnt = max(1, len(enabled))
        n = cols * rows
        pixels: list[Color] = [(0, 0, 0)] * n
        for row in range(rows):
            for col in range(cols):
                pos, length = _axis_coord(col, row, cols, rows, axis)
                t = ((pos / length) + p * 0.05) % 1.0
                if blend == "steps" or cnt == 1:
                    pixels[row * cols + col] = enabled[int(t * cnt) % cnt]
                else:
                    f = t * cnt
                    i0 = int(f) % cnt
                    i1 = (i0 + 1) % cnt
                    pixels[row * cols + col] = lerp_color(enabled[i0], enabled[i1], f - math.floor(f))
        return pixels

    # ── Phase 4: neue/ueberarbeitete Algorithmen ──────────────────────────────

    def _render_rainbow(self, p: float, cols: int, rows: int) -> list[Color]:
        """Regenbogen. params: movement(linear/radial/center_out/outside_in),
        spread(Hue-Zyklen ueber die Matrix), saturation, value."""
        params = self.params
        # #5: eigene Keys rainbow_movement/hue_spread (Fallback movement/spread fuer
        # Alt-Shows/VC) — verhindert Param-Bleed von CHASE/WIPE bzw. WAVE.
        movement = str(params.get("rainbow_movement", params.get("movement", "linear")))
        spread = float(params.get("hue_spread", params.get("spread", 1.0)))
        sat = max(0.0, min(1.0, float(params.get("saturation", 1.0))))
        val = max(0.0, min(1.0, float(params.get("value", 1.0))))
        n = cols * rows
        pixels: list[Color] = [(0, 0, 0)] * n
        cx, cy = (cols - 1) / 2.0, (rows - 1) / 2.0
        maxr = math.hypot(cx, cy) or 1.0
        for row in range(rows):
            for col in range(cols):
                if movement in ("radial", "center_out", "outside_in"):
                    d = math.hypot(col - cx, row - cy) / maxr
                    if movement == "outside_in":
                        d = 1.0 - d
                    hue = (d * 360.0 * spread + p * 30.0) % 360.0
                else:  # linear
                    hue = ((col + row * 0.5) / max(1, cols) * 360.0 * spread + p * 30.0) % 360.0
                pixels[row * cols + col] = hsv_to_rgb(hue, sat, val)
        return pixels

    def _fill_order(self, real: list[int], direction: str, cols: int, rows: int) -> list[int]:
        """Reihenfolge, in der echte Fixtures gefuellt werden (je Richtung)."""
        def cr(i):
            return (i % cols, i // cols)
        cx, cy = (cols - 1) / 2.0, (rows - 1) / 2.0
        if direction == "random":
            order = list(real)
            random.Random(1234567).shuffle(order)
            return order
        keys = {
            "left":        lambda i: (cr(i)[0], cr(i)[1]),
            "right":       lambda i: (-cr(i)[0], cr(i)[1]),
            "top":         lambda i: (cr(i)[1], cr(i)[0]),
            "bottom":      lambda i: (-cr(i)[1], cr(i)[0]),
            "diag":        lambda i: (cr(i)[0] + cr(i)[1]),
            "center_out":  lambda i: max(abs(cr(i)[0] - cx), abs(cr(i)[1] - cy)),
            "outside_in":  lambda i: -max(abs(cr(i)[0] - cx), abs(cr(i)[1] - cy)),
        }
        return sorted(real, key=keys.get(direction, keys["left"]))

    def _render_fill(self, p: float, cols: int, rows: int, enabled: list) -> list[Color]:
        """Zeitlicher Aufbau (Abschnitt 4): fuellt die echten Fixtures NACHEINANDER
        in der gewaehlten Reihenfolge. Style-abhaengig (WP-2):
          Dimmer/Shutter: fill_mode up (nacheinander heller) / down (nacheinander
                          dunkler) / random (zufaellige Helligkeit) — Graustufen-
                          Pixel, die die Style-Maske auf den Dimmer-/Shutter-Bereich
                          (intensity_min..max bzw. shutter_min..max) abbildet.
          RGB/RGBW:       fill_mode target (aktive Farbe) / random (zufaellige Farbe
                          aus der Sequence) / sequence (Farben der Reihe nach).
        params: fill_dir (Reihenfolge), fill_speed, fade (pro Fixture), hold,
        loop_mode (restart/stay/reverse/fadeout). Nur echte Fixtures (#6)."""
        params = self.params
        n = cols * rows
        pixels: list[Color] = [(0, 0, 0)] * n
        real = self._real_indices(n)
        k = len(real)
        if k == 0:
            return pixels
        order = self._fill_order(real, str(params.get("fill_dir", "left")), cols, rows)
        speed = max(0.05, float(params.get("fill_speed", 1.0)))
        # #5: fixture_fade (Fallback "fade" fuer Alt-Shows/VC). FILL-„hold" bleibt
        # „hold" (Halte-Schritte) — nur ColorFade-hold heisst jetzt crossfade_hold.
        fade = max(0.0, min(1.0, float(params.get("fixture_fade", params.get("fade", 0.4)))))
        hold = max(0.0, float(params.get("hold", 0.0)))
        loop_mode = str(params.get("loop_mode", "restart"))
        is_intensity = self.style in (MatrixStyle.DIMMER, MatrixStyle.SHUTTER)
        fmode = str(params.get("fill_mode", "up" if is_intensity else "target"))

        # ── Zeit -> Fuellfortschritt (in "Fixtures") + globaler Fade (fadeout) ──
        t = max(0.0, p) * speed
        span = k + hold                       # Fuellen (k) + Halten (hold)
        global_scale = 1.0
        if loop_mode == "stay":
            progress = min(float(k), t)
        elif loop_mode == "reverse":
            period = 2.0 * span
            pp = t % period
            progress = pp if pp <= span else max(0.0, 2.0 * span - pp)
        elif loop_mode == "fadeout":
            fade_len = max(1.0, float(k))
            period = span + fade_len
            pp = t % period
            if pp <= span:
                progress = min(float(k), pp)
            else:                              # voll, dann gemeinsam ausfaden
                progress = float(k)
                global_scale = max(0.0, 1.0 - (pp - span) / fade_len)
        else:  # restart
            progress = t % span

        full = int(progress)                  # vollstaendig gefuellte Fixtures
        frac = progress - full                # Fortschritt des gerade fuellenden
        a = min(1.0, frac / fade) if fade > 0.0 else (1.0 if frac >= 0.5 else 0.0)
        ncol = max(1, len(enabled))

        def _target_color(rank: int) -> Color:
            if fmode == "sequence" and enabled:
                return enabled[rank % len(enabled)]
            if fmode == "random" and enabled:
                return enabled[random.Random(((rank + 1) * 2654435761) & 0x7FFFFFFF).randrange(ncol)]
            return self.colors.selected(enabled[0] if enabled else (255, 255, 255))

        def _rand_level(rank: int) -> float:
            return random.Random(((rank + 1) * 40503) & 0x7FFFFFFF).uniform(0.3, 1.0)

        for rank, idx in enumerate(order):
            if rank < full:
                prog_f = 1.0
            elif rank == full:
                prog_f = a
            else:
                prog_f = 0.0
            if is_intensity:
                if fmode == "down":
                    bright = 1.0 - prog_f          # voll -> nacheinander aus
                elif fmode == "random":
                    bright = prog_f * _rand_level(rank)
                else:                              # up
                    bright = prog_f
                v = max(0, min(255, int(round(255 * bright * global_scale))))
                pixels[idx] = (v, v, v)            # Graustufe -> Dimmer/Shutter-Maske
            else:
                pixels[idx] = _scale(_target_color(rank), prog_f * global_scale)
        return pixels

    def _random_selection(self, real, count, bucket, scope, cols, rows, no_repeat):
        """Deterministische Auswahl von count echten Zellen je Zeit-Bucket
        (reproduzierbar → Vorschau == Output, framerate-unabhaengig). NIE Luecken."""
        def pick(bk):
            rng = random.Random((bk * 2654435761) & 0x7FFFFFFF)
            if scope in ("row", "col"):
                lines: dict = {}
                for idx in real:
                    key = (idx // cols) if scope == "row" else (idx % cols)
                    lines.setdefault(key, []).append(idx)
                ks = list(lines.keys())
                rng.shuffle(ks)
                chosen: list = []
                for k in ks[:max(1, count)]:
                    chosen.extend(lines[k])
                return chosen
            pool = list(real)
            rng.shuffle(pool)
            return pool[:min(count, len(pool))]

        sel = pick(bucket)
        if no_repeat and scope == "all" and len(real) > count:
            prev = set(pick(bucket - 1))
            if set(sel) & prev:
                pool = [i for i in real if i not in prev]
                if len(pool) >= count:
                    random.Random((bucket * 40503) & 0x7FFFFFFF).shuffle(pool)
                    sel = pool[:count]
        return sel

    def _render_random(self, p: float, cols: int, rows: int, enabled: list) -> list[Color]:
        """Vereinheitlichter Random. params: mode(dimmer/color/strobe/flash/
        sparkle/pulse), count(gleichzeitig aktive echte Fixtures), rate, scope
        (all/row/col), no_repeat, strobe_rate. Waehlt NIE eine Luecke (#6)."""
        params = self.params
        mode = str(params.get("mode", "color"))
        count = max(1, int(params.get("count", 1)))
        rate = max(0.1, float(params.get("rate", 1.0)))
        scope = str(params.get("scope", "all"))
        no_repeat = bool(params.get("no_repeat", True))
        n = cols * rows
        pixels: list[Color] = [(0, 0, 0)] * n
        real = self._real_indices(n)
        if not real:
            return pixels
        bucket = int(p * rate)
        frac = (p * rate) - bucket
        sel = self._random_selection(real, count, bucket, scope, cols, rows, no_repeat)
        first = enabled[0] if enabled else (255, 255, 255)
        sr = max(1, int(params.get("strobe_rate", 4)))
        for idx in sel:
            rng = random.Random(((idx + 1) * 1009) ^ (bucket * 9176))
            if mode == "color":
                rgb = enabled[rng.randrange(len(enabled))] if enabled else first
                bright = 1.0
            elif mode == "flash":
                rgb = enabled[rng.randrange(len(enabled))] if enabled else first
                bright = 1.0
            elif mode == "dimmer":
                rgb = first
                bright = rng.uniform(0.3, 1.0)
            elif mode == "strobe":
                rgb = first
                bright = 1.0 if (int(frac * sr * 2) % 2 == 0) else 0.0
            elif mode == "sparkle":
                rgb = first
                bright = max(0.0, 1.0 - frac / 0.4)     # kurzes Aufblitzen + Abklingen
            elif mode == "pulse":
                rgb = first
                bright = math.sin(frac * math.pi)        # weich auf/ab
            else:
                rgb = first
                bright = 1.0
            pixels[idx] = _scale(rgb, bright)
        return pixels

    def _render_colorfade(self, p: float, cols: int, rows: int, enabled: list) -> list[Color]:
        """Ganzes Feld faded durch die Color-Sequence. params: hold(0..1),
        pingpong. Deaktivierte Farben sind in enabled gar nicht enthalten →
        werden automatisch uebersprungen (#8.7)."""
        params = self.params
        # #5: crossfade_hold (Fallback "hold" fuer Alt-Shows/VC) — eigener Key, weil
        # FILL „hold" als Halte-Schritte (0..20) nutzt, ColorFade als Anteil (0..0.95).
        hold = max(0.0, min(0.95, float(params.get("crossfade_hold", params.get("hold", 0.0)))))
        pingpong = bool(params.get("pingpong", False))
        n = cols * rows
        cnt = len(enabled)
        if cnt <= 1:
            return [enabled[0] if enabled else (0, 0, 0)] * n
        if pingpong and cnt > 2:
            order = list(range(cnt)) + list(range(cnt - 2, 0, -1))
        else:
            order = list(range(cnt))
        L = len(order)
        seg = int(p) % L
        t = p - math.floor(p)
        i0 = order[seg]
        nx = order[(seg + 1) % L]
        if t < hold:
            color = enabled[i0]
        else:
            tt = (t - hold) / (1.0 - hold) if hold < 1.0 else 1.0
            color = lerp_color(enabled[i0], enabled[nx], tt)
        return [color] * n

    def _generate(self) -> list[Color]:
        """Back-Compat-Wrapper fuer MatrixPreview und _DemoGrid in effect_mini_preview.py."""
        return self._render(self._step)

    # ── Generisches Parameter-Modell (Live-Programming-Fundament, Phase 2) ─────
    # Eine einzige Quelle dafuer, welche Parameter ein Effekt hat, wie sie heissen,
    # welchen Typ/Bereich sie haben und ob sie live/mappbar sind. VC, MIDI und die
    # Programmer-UI lesen kuenftig genau hier — kein hartcodiertes Wissen mehr ueber
    # einzelne Effekt-Parameter (Anforderung #10–#13).

    def list_params(self) -> list:
        """ParamSpecs aller live steuerbaren Parameter des aktuellen Algorithmus:
        universell (speed, intensity, ggf. direction) + Farben + algo-spezifisch.

        VC und MIDI sehen dieselbe Style-/when-Auswahl wie der Matrix-Programmer:
        RGB bietet keine Dimmer-/Shutter-Grenzen an, Dimmer/Shutter keine Farben."""
        from .rgb_matrix_meta import ALGO_META, ParamSpec, visible_specs
        specs = [
            ParamSpec("speed", "Geschwindigkeit", "float", 1.0, 0.01, 20.0, 0.1,
                      "Animationsrate (Schritte/s)"),
        ]
        if self.style != MatrixStyle.SHUTTER:
            specs.append(
                ParamSpec("intensity", "Helligkeit", "float", 1.0, 0.0, 1.0, 0.01,
                          "Effekt-Master 0..1")
            )
        specs.append(
            ParamSpec("offset", "Versatz", "float", 0.0, 0.0, 16.0, 0.1,
                      "Phasen-Versatz in Schritten (versetzte Effekte)")
        )
        if self.style == MatrixStyle.DIMMER:
            specs.extend([
                ParamSpec("intensity_min", "Dimmer min", "int", 0, 0, 255, 1,
                          "Untergrenze des Dimmer-Styles"),
                ParamSpec("intensity_max", "Dimmer max", "int", 255, 0, 255, 1,
                          "Obergrenze des Dimmer-Styles"),
            ])
        elif self.style == MatrixStyle.SHUTTER:
            specs.extend([
                ParamSpec("shutter_min", "Shutter min", "int", 0, 0, 255, 1,
                          "Untergrenze des Shutter-Styles"),
                ParamSpec("shutter_max", "Shutter max", "int", 255, 0, 255, 1,
                          "Obergrenze des Shutter-Styles"),
            ])
        specs.extend([
            # WP-Tempo: Anbindung an einen Tempo-Bus (A/B/C/D) — leer = frei/eigene
            # Geschwindigkeit. Multiplier frei (×0.5/×2/×3…), Versatz in Beats.
            ParamSpec("tempo_bus_id", "Tempo-Bus", "select", "Global",
                      options=("Global", "", "A", "B", "C", "D"),
                      tooltip="Auf welchen Tempo-Bus synchronisieren (leer = frei, "
                              "Global = Master-BPM, A–D = eigene Buses)"),
            ParamSpec("tempo_multiplier", "Tempo ×", "float", 1.0, 0.0625, 16.0, 0.25,
                      "Verhältnis zum Bus (frei, z. B. 0.5 halb, 2 doppelt, 3 dreifach)"),
            ParamSpec("phase_offset", "Tempo-Versatz (Beats)", "float", 0.0, 0.0, 1.0, 0.05,
                      "Phasen-Versatz in Beats (versetzter Start auf dem Bus)"),
            # F2: Ein-/Ausblendzeit des Effekts (Hüllkurve, Function-Basis) live steuerbar
            # -> Fade-Fader in der VC (SliderMode.EFFECT_PARAM, param_key env_fade_in/out).
            ParamSpec("env_fade_in", "Fade ein (s)", "float", 0.0, 0.0, 10.0, 0.1,
                      "Einblendzeit des Effekts in Sekunden"),
            ParamSpec("env_fade_out", "Fade aus (s)", "float", 0.0, 0.0, 10.0, 0.1,
                      "Ausblendzeit des Effekts in Sekunden"),
            ParamSpec("env_fade", "Fade ein+aus (s)", "float", 0.0, 0.0, 10.0, 0.1,
                      "Komfort-Fader: setzt Einblend- UND Ausblendzeit gemeinsam auf "
                      "denselben Wert. Wer beide getrennt steuern will, nutzt „Fade ein“ "
                      "und „Fade aus“."),
        ])
        meta = ALGO_META.get(self.algorithm)
        if meta and meta.direction:
            specs.append(ParamSpec("direction", "Richtung", "select", "forward",
                                   options=("forward", "reverse"), tooltip="Laufrichtung"))
        n_colors = meta.colors if meta else 1
        if self.style in (MatrixStyle.RGB, MatrixStyle.RGBW) and n_colors > 0:
            specs.append(ParamSpec("colors", "Farben", "color_sequence", None,
                                   tooltip="Farbliste (aktiv/inaktiv, hinzufügen/entfernen)"))
        if meta:
            specs.extend(visible_specs(self.algorithm, self.style.value, self.params))
        return specs

    def get_param(self, key: str):
        """Aktuellen Wert eines Parameters lesen (key wie in list_params)."""
        if key == "speed":
            return self.matrix_speed
        if key == "intensity":
            return self.intensity
        if key == "direction":
            return self.direction
        if key == "algorithm":
            return self.algorithm.value
        if key in ("colors", "color_sequence"):
            return self.colors
        if key in ("dimmer_sequence", "dimmer_levels"):
            return self.dimmer_levels
        if key in ("color1", "color2", "color3"):
            return getattr(self, key)
        if key == "offset":
            return float(self.params.get("offset", 0.0))
        if key in ("white_amount", "intensity_min", "intensity_max", "shutter_min", "shutter_max"):
            return getattr(self, key)
        if key == "tempo_bus_id":
            return getattr(self, "tempo_bus_id", "")
        if key == "tempo_multiplier":
            return getattr(self, "tempo_multiplier", 1.0)
        if key == "phase_offset":
            return getattr(self, "phase_offset", 0.0)
        if key in ("env_fade_in", "env_fade_out"):
            return float(getattr(self, key, 0.0))
        if key == "env_fade":
            return float(getattr(self, "env_fade_in", 0.0))
        if key == "env_curve":
            return getattr(self, "env_curve", "linear")
        return self.params.get(key)

    def set_param(self, key: str, value) -> bool:
        """Setzt einen Parameter live (geklemmt). Aenderung wirkt sofort, weil
        _render bei JEDEM Frame aus diesen Feldern liest (kein Snapshot beim
        Start) — genau die Voraussetzung fuer Live-Programming (Anforderung #16)."""
        from .rgb_matrix_meta import ALGO_META  # lazy
        if key == "speed":
            self.matrix_speed = max(0.0, float(value)); return True
        if key == "intensity":
            self.intensity = max(0.0, min(1.0, float(value))); return True
        if key == "direction":
            if isinstance(value, bool):
                self.direction = "reverse" if value else "forward"
            else:
                s = str(value).lower()
                self.direction = "reverse" if s.startswith(("rev", "rück", "ruck", "back")) else "forward"
            return True
        if key == "algorithm":
            try:
                self.algorithm = RgbAlgorithm(str(value))
                return True
            except ValueError:
                # Legacy-Varianten-Namen (z. B. "Chase Horizontal") mit migrieren.
                mapped = _LEGACY_ALGO_MAP.get(str(value))
                if mapped:
                    self.algorithm = RgbAlgorithm(mapped[0])
                    for _k, _v in mapped[1].items():
                        self.params.setdefault(_k, _v)
                    return True
                return False
        if key in ("colors", "color_sequence"):
            if isinstance(value, ColorSequence):
                self.colors = value
            elif isinstance(value, list):
                if value and isinstance(value[0], dict):
                    self.colors = ColorSequence.from_list(value)
                else:
                    self.colors = ColorSequence(value)
            return True
        if key in ("dimmer_sequence", "dimmer_levels"):
            if isinstance(value, DimmerSequence):
                self.dimmer_levels = value
            elif isinstance(value, list):
                if value and isinstance(value[0], dict):
                    self.dimmer_levels = DimmerSequence.from_list(value)
                else:
                    self.dimmer_levels = DimmerSequence(value)
            return True
        if key in ("color1", "color2", "color3"):
            setattr(self, key, tuple(value)); return True
        if key == "offset":
            self.params["offset"] = max(0.0, min(16.0, float(value))); return True
        if key in ("white_amount", "intensity_min", "intensity_max", "shutter_min", "shutter_max"):
            hi = 100 if key == "white_amount" else 255
            setattr(self, key, max(0, min(hi, int(round(float(value)))))); return True
        if key == "tempo_bus_id":
            self.tempo_bus_id = str(value or "").strip(); return True
        if key == "tempo_multiplier":
            try:
                self.tempo_multiplier = max(0.0625, min(16.0, float(value)))
            except (TypeError, ValueError):
                pass
            return True
        if key == "phase_offset":
            try:
                self.phase_offset = max(0.0, min(1.0, float(value)))
            except (TypeError, ValueError):
                pass
            return True
        if key in ("env_fade_in", "env_fade_out"):
            try:
                setattr(self, key, max(0.0, min(60.0, float(value))))
            except (TypeError, ValueError):
                pass
            return True
        if key == "env_fade":
            try:
                v = max(0.0, min(60.0, float(value)))
                self.env_fade_in = v
                self.env_fade_out = v
            except (TypeError, ValueError):
                pass
            return True
        if key == "env_curve":
            self.env_curve = str(value or "linear")
            return True
        # Algo-spezifisch: in params ablegen, ueber die Meta-Spec klemmen.
        spec = None
        meta = ALGO_META.get(self.algorithm)
        if meta:
            for s in meta.params:
                if s.key == key:
                    spec = s
                    break
        if spec is not None:
            if spec.kind == "bool":
                self.params[key] = bool(value)
            elif spec.kind == "int":
                v = int(round(float(value)))
                if spec.max > spec.min:
                    v = max(int(spec.min), min(int(spec.max), v))
                self.params[key] = v
            elif spec.kind == "float":
                v = float(value)
                if spec.max > spec.min:
                    v = max(float(spec.min), min(float(spec.max), v))
                self.params[key] = v
            else:
                self.params[key] = value
            return True
        # Unbekannter Key: dennoch in params ablegen (vorwaerts-kompatibel).
        self.params[key] = value
        return True

    def _cycle_algorithm(self, step: int) -> bool:
        """Schaltet live auf den naechsten/vorherigen Algorithmus um (APC-Probier
        To-Do #3: EINE Matrix + "Form +/-"-Pad statt ein Pad je Algorithmus).

        Es wird durch alle RgbAlgorithm-Werte rotiert; leftover params des alten
        Algorithmus sind harmlos (jeder Render-Helfer liest nur seine eigenen
        Keys mit Defaults). Die Animations-Phase laeuft bewusst weiter."""
        algos = list(RgbAlgorithm)
        try:
            i = algos.index(self.algorithm)
        except ValueError:
            i = 0
        self.algorithm = algos[(i + step) % len(algos)]
        return True

    def do_action(self, action: str, **kw) -> bool:
        """Loest eine Live-Aktion aus (Buttons der virtuellen Konsole, MIDI-Notes).
        Gibt True zurueck, wenn die Aktion bekannt war (Anforderung #14)."""
        a = str(action)
        seq = self.colors
        if a in ("add_color", "addColor"):
            seq.add(tuple(kw.get("rgb", seq.selected((255, 255, 255)))), True)
            return True
        if a in ("clear_colors", "clearColors"):
            seq.entries.clear()
            seq.active_index = 0
            return True
        if a in ("remove_color", "removeColor"):
            seq.remove(int(kw.get("index", seq.active_index)))
            return True
        if a in ("toggle_color", "toggleColor"):
            seq.toggle(int(kw.get("index", seq.active_index)))
            return True
        if a in ("next_color", "nextColor"):
            seq.next(); return True
        if a in ("prev_color", "previous_color", "prevColor", "previousColor"):
            seq.prev(); return True
        if a in ("reverse_direction", "reverseDirection"):
            self.direction = "forward" if self.direction == "reverse" else "reverse"
            return True
        if a in ("next_algorithm", "nextAlgorithm", "next_form"):
            return self._cycle_algorithm(+1)
        if a in ("prev_algorithm", "prevAlgorithm", "previous_algorithm", "prev_form"):
            return self._cycle_algorithm(-1)
        if a in ("toggle_bounce", "toggleBounce"):
            cur = self.params.get("movement", "normal")
            self.params["movement"] = "normal" if cur == "bounce" else "bounce"
            return True
        if a in ("freeze",):
            self._frozen = True
            return True
        if a in ("unfreeze",):
            self._frozen = False
            return True
        if a in ("toggle_freeze", "toggleFreeze"):
            self._frozen = not self._frozen
            return True
        if a in ("clear_live_override", "clearLiveOverride"):
            self.clear_live_override()
            return True
        if a in ("commit_live", "save_live", "saveLiveChangesToPreset"):
            self.commit_live_to_preset()
            return True
        if a in ("tap", "tap_tempo", "tapTempo"):
            try:
                from .bpm_manager import get_bpm_manager
                get_bpm_manager().tap()
                return True
            except Exception:
                return False
        return False

    def list_actions(self) -> list[tuple[str, str]]:
        """Aktuell sinnvolle Matrix-Live-Aktionen für VC/MIDI."""
        from .rgb_matrix_meta import ALGO_META, visible_specs

        meta = ALGO_META.get(self.algorithm)
        actions: list[tuple[str, str]] = []
        if (self.style in (MatrixStyle.RGB, MatrixStyle.RGBW)
                and meta is not None and meta.colors > 0):
            actions.extend([
                ("next_color",   "Farbe +"),
                ("prev_color",   "Farbe −"),
                ("add_color",    "+ Farbe"),
                ("toggle_color", "Farbe an/aus"),
            ])
        actions.extend([
            ("next_algorithm", "Form +"),
            ("prev_algorithm", "Form −"),
        ])
        if meta is not None and meta.direction:
            actions.append(("reverse_direction", "Richtung"))
        movement = next(
            (spec for spec in visible_specs(
                self.algorithm, self.style.value, self.params
            ) if spec.key == "movement"),
            None,
        )
        if movement is not None and "bounce" in tuple(movement.options or ()):
            actions.append(("toggle_bounce", "Bounce"))
        actions.extend([
            ("toggle_freeze",       "Freeze"),
            ("clear_live_override", "Reset Live"),
            ("commit_live",         "Commit"),
            ("tap",                 "Tap"),
        ])
        return actions

    # ── Live-Override-Modell (Phase 6, #17) ───────────────────────────────────
    # Die VC veraendert die laufenden Felder direkt (sofort sichtbar). Der
    # Preset-Schnappschuss erlaubt es, Live-Aenderungen wieder zu verwerfen
    # (clear_live_override) oder bewusst als neuen Preset zu uebernehmen
    # (commit_live_to_preset). Gespeichert wird die Show weiterhin nur bewusst.

    def snapshot_preset(self) -> None:
        """Merkt den aktuellen Zustand als Preset (Basis fuer clear_live_override)."""
        self._preset = self.to_dict()

    def clear_live_override(self) -> None:
        """Verwirft Live-Aenderungen und faellt auf den letzten Preset zurueck."""
        if self._preset:
            running = self._running
            step = self._step
            self.apply_dict(self._preset)
            self._running = running
            self._step = step
            from . import effect_live
            effect_live.discard_live_override_tracking(self.id)

    def commit_live_to_preset(self) -> None:
        """Uebernimmt die aktuellen (live geaenderten) Werte als neuen Preset."""
        self._preset = self.to_dict()
        from . import effect_live
        effect_live.commit_live_override(self.id)

    def to_dict(self) -> dict:
        d = super().to_dict()  # id, name, type, intensity, speed, folder
        d.update({
            "cols": self.cols, "rows": self.rows,
            "fixture_grid": self.fixture_grid,
            # Gruppen-Bindung (Programmer-Listen-Scope) — per Name, stabil ueber Save/Load.
            "source_group": self.source_group,
            "algorithm": self.algorithm.value,
            # Kanonisches Farbmodell (beliebig lang, aktiv/inaktiv je Farbe).
            "color_sequence": self.colors.to_list(),
            "color_active": self.colors.active_index,
            # ENG-08: explizite Dimmerwert-Sequenz (Dimmer-Chase, dimmer_cycle).
            "dimmer_sequence": self.dimmer_levels.to_list(),
            "dimmer_active": self.dimmer_levels.active_index,
            # Abgeleitet fuer Alt-Leser (Rueckwaertskompatibilitaet): erste 3 Farben.
            "color1": list(self.color1),
            "color2": list(self.color2),
            "color3": list(self.color3),
            "matrix_speed": self.matrix_speed,
            "direction": self.direction,
            "drive_intensity": self.drive_intensity,
            # Phase-3-Style-Felder
            "style": self.style.value,
            "white_amount": self.white_amount,
            "intensity_min": self.intensity_min,
            "intensity_max": self.intensity_max,
            "shutter_min": self.shutter_min,
            "shutter_max": self.shutter_max,
            # Phase-4-Parameter
            "params": self.params,
        })
        return d

    def apply_dict(self, d: dict) -> None:
        """Setzt alle editierbaren Felder aus einem Dict (in-place).

        Wird von from_dict (Konstruktion) und _save_edit (Dirty-State-Modell) genutzt,
        damit die Feld-Zuweisung nur an einer Stelle steht (DRY).
        id und Laufzustand (_running, _step, …) werden NICHT angefasst.
        """
        self.name = d.get("name", self.name)
        self.cols = d.get("cols", 8)
        self.rows = d.get("rows", 4)
        # None-Eintraege = Luecken; alte dichte Listen (ohne None) laden unveraendert (Migration).
        self.fixture_grid = list(d.get("fixture_grid", []))
        # Gruppen-Bindung (Programmer-Listen-Scope). Fehlender Key (Alt-Shows) ODER
        # leerer String = ungebunden (None) -> erscheint in jeder Gruppe.
        _sg = d.get("source_group", getattr(self, "source_group", None))
        self.source_group = str(_sg) if _sg else None
        # Algorithmus + Migration alter Varianten-Namen → (Grundalgorithmus, params).
        # Legacy-Strings werden auf den neuen Enum-Wert + Default-Parameter gemappt,
        # BEVOR das Enum gebildet wird (sonst ValueError bei alten Shows, #18).
        algo_value = d.get("algorithm", "Plain")
        self._migrated_params: dict = {}
        _mapped = _LEGACY_ALGO_MAP.get(algo_value)
        if _mapped:
            algo_value, self._migrated_params = _mapped[0], dict(_mapped[1])
        try:
            self.algorithm = RgbAlgorithm(algo_value)
        except ValueError:
            self.algorithm = RgbAlgorithm.PLAIN
        # Farben: kanonisch ueber color_sequence; Alt-Shows ohne diesen Key
        # werden aus color1/2/3 geseedet (Migration zu "Sequence ueberall").
        if "color_sequence" in d:
            self.colors = ColorSequence.from_list(d.get("color_sequence") or [])
            if len(self.colors) == 0:
                self.colors = ColorSequence([(255, 0, 0), (0, 0, 255), (0, 255, 0)])
        else:
            self.colors = ColorSequence([
                tuple(d.get("color1", [255, 0, 0])),
                tuple(d.get("color2", [0, 0, 255])),
                tuple(d.get("color3", [0, 255, 0])),
            ])
        try:
            self.colors.active_index = int(d.get("color_active", 0))
        except (TypeError, ValueError):
            self.colors.active_index = 0
        # ENG-08: Dimmerwert-Sequenz; Alt-Shows ohne Key bekommen den Default.
        if "dimmer_sequence" in d:
            self.dimmer_levels = DimmerSequence.from_list(d.get("dimmer_sequence") or [])
            if len(self.dimmer_levels) == 0:
                self.dimmer_levels = DimmerSequence([255, 128, 64])
        else:
            self.dimmer_levels = DimmerSequence([255, 128, 64])
        try:
            self.dimmer_levels.active_index = int(d.get("dimmer_active", 0))
        except (TypeError, ValueError):
            self.dimmer_levels.active_index = 0
        # Animationsrate: neuer Key "matrix_speed"; Alt-Shows hatten "speed".
        self.matrix_speed = float(d.get("matrix_speed", d.get("speed", 1.0)))
        self.direction = d.get("direction", "forward")
        # F-17: Layer-Prioritaet (Function-Basisfeld) auch im Draft-Roundtrip
        # (_save_edit -> apply_dict) erhalten — apply_dict laedt sonst keine
        # Basisfelder. Default = aktueller Wert bzw. 0 (alt-kompatibel).
        try:
            self.priority = int(d.get("priority", getattr(self, "priority", 0)))
        except (TypeError, ValueError):
            self.priority = 0
        # ARC-04: Hüllkurven-Zeiten ebenfalls im Draft-Roundtrip erhalten.
        try:
            self.env_fade_in = max(0.0, float(d.get("env_fade_in",
                                                    getattr(self, "env_fade_in", 0.0))))
            self.env_fade_out = max(0.0, float(d.get("env_fade_out",
                                                     getattr(self, "env_fade_out", 0.0))))
        except (TypeError, ValueError):
            self.env_fade_in = self.env_fade_out = 0.0
        self.env_curve = str(d.get("env_curve",
                                   getattr(self, "env_curve", "linear")) or "linear")
        # Tempo-Sync-Felder gehoeren ebenfalls zur Function-Basis. Der Matrix-
        # Editor erzeugt seinen Draft via from_dict(to_dict()); ohne diesen
        # Roundtrip verlor der Draft die Bus-Bindung und blieb faelschlich dirty.
        self.tempo_bus_id = str(d.get(
            "tempo_bus_id", getattr(self, "tempo_bus_id", "")) or "")
        try:
            self.tempo_multiplier = float(d.get(
                "tempo_multiplier", getattr(self, "tempo_multiplier", 1.0)))
        except (TypeError, ValueError):
            self.tempo_multiplier = 1.0
        try:
            self.phase_offset = float(d.get(
                "phase_offset", getattr(self, "phase_offset", 0.0)))
        except (TypeError, ValueError):
            self.phase_offset = 0.0
        self.sync_group = str(d.get(
            "sync_group", getattr(self, "sync_group", "")) or "")
        # drive_intensity: R1-Default True fuer Alt-Shows (ohne Key) bleibt hell.
        self.drive_intensity = bool(d.get("drive_intensity", True))
        # Phase-3-Style-Felder (Default RGB damit Alt-Shows unveraendert bleiben).
        self.style = MatrixStyle(d.get("style", "RGB"))
        self.white_amount = int(d.get("white_amount", 100))
        self.intensity_min = int(d.get("intensity_min", 0))
        self.intensity_max = int(d.get("intensity_max", 255))
        self.shutter_min = int(d.get("shutter_min", 0))
        self.shutter_max = int(d.get("shutter_max", 255))
        # Parameter: gespeicherte params + Migrations-Defaults (setdefault, damit
        # explizit gespeicherte Werte Vorrang vor den Migrations-Defaults haben).
        self.params = dict(d.get("params", {}))
        for _k, _v in getattr(self, "_migrated_params", {}).items():
            self.params.setdefault(_k, _v)
        self._migrated_params = {}
        # WP-4/Abschnitt 5: Chase-"Schweif" (fade 0..1) -> "After Fade" (% 0..100).
        # Eindeutige Migration: nur CHASE, nur wenn after_fade noch fehlt — so
        # bleiben Alt-Shows kompatibel (Testfall 17) und es gibt keine Doppeldeutung.
        if (self.algorithm == RgbAlgorithm.CHASE
                and "after_fade" not in self.params and "fade" in self.params):
            try:
                self.params["after_fade"] = max(0.0, min(100.0, float(self.params["fade"]) * 100.0))
            except (TypeError, ValueError):
                self.params["after_fade"] = 30.0
            self.params.pop("fade", None)
        # #5: Param-Key-Disambiguierung — eigene Keys pro Algorithmus, damit kein
        # geteilter Key beim Algo-Wechsel durchblutet. Alt-Shows speicherten den
        # alten (geteilten) Key; hier auf den neuen umziehen, wenn der neue fehlt.
        # (Die Renderer lesen zusaetzlich mit Fallback auf den alten Key, falls die
        # params per API direkt gesetzt wurden und nie durch apply_dict liefen.)
        _key_migration = {
            RgbAlgorithm.PINWHEEL:  (("segment_count", "runner_count"),),
            RgbAlgorithm.RAINBOW:   (("hue_spread", "spread"),
                                     ("rainbow_movement", "movement")),
            RgbAlgorithm.COLORFADE: (("crossfade_hold", "hold"),),
            RgbAlgorithm.FILL:      (("fixture_fade", "fade"),),
        }
        for _new_key, _old_key in _key_migration.get(self.algorithm, ()):
            if _new_key not in self.params and _old_key in self.params:
                self.params[_new_key] = self.params.pop(_old_key)

    @classmethod
    def from_dict(cls, d: dict) -> "RgbMatrixInstance":
        m = cls(name=d.get("name", "RGB Matrix"), fid=d.get("id"))
        m.apply_dict(d)
        m.snapshot_preset()   # Phase 6: Basis fuer Live-Override-Rueckfall
        return m
