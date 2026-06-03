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
    CHASE_H    = "Chase Horizontal"
    CHASE_V    = "Chase Vertical"
    CHASE_DIAG = "Chase Diagonal"
    WIPE_H     = "Wipe Horizontal"
    WIPE_V     = "Wipe Vertical"
    RAINBOW    = "Rainbow"
    RANDOM     = "Random"
    SPARKLE    = "Sparkle"
    RADAR      = "Radar"
    SINEPLASMA = "Sine Plasma"
    # Mehrfarbiges Lauflicht: c1/c2/c3 als wandernde Baender (jeder Pixel zeigt
    # reihum eine der drei Farben). Fuer „3 Farben -> Lauflicht" auf einer Gruppe.
    COLOR_SCROLL = "Color Scroll"
    # Mehrfarbiges Chase: genau EIN Pixel an, dessen Farbe pro Durchlauf zwischen
    # c1/c2/c3 wechselt (klassisches Lauflicht in wechselnden Farben).
    CHASE_MULTI  = "Chase Multicolor"
    # Koordinatenbasierte Algorithmen (I2.3)
    CENTER_OUT = "Center→Außen"
    OUTER_IN   = "Außen→Center"
    BOUNCE_H   = "Bounce H"
    BOUNCE_V   = "Bounce V"
    DIAG_WAVE  = "Diagonal Welle"
    SPIRAL     = "Spirale"


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

    def __init__(self, name: str = "RGB Matrix", fid: int | None = None, *,
                 cols: int = 8, rows: int = 4,
                 fixture_grid: list[int] | None = None,
                 algorithm: RgbAlgorithm = RgbAlgorithm.CHASE_H,
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
        self.algorithm = algorithm
        self.color1 = color1
        self.color2 = color2
        self.color3 = color3
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
        self.white_amount: int = 100       # 0–100 %, RGBW-Weissanteil
        self.intensity_min: int = 0        # Dimmer-Style Untergrenze
        self.intensity_max: int = 255      # Dimmer-Style Obergrenze
        self.shutter_min: int = 0          # Shutter-Style Untergrenze
        self.shutter_max: int = 255        # Shutter-Style Obergrenze
        # Phase 4: unbeschraenkte Phase (kein % max(cols,rows) mehr)
        self._step: float = 0.0
        self._last_tick: float = 0.0
        # Phase 4: Algorithmus-Parameter-Dict
        self.params: dict = {}

    def _on_start(self):
        self._step = 0.0
        self._last_tick = time.monotonic()

    # ── Style-Hilfsmethoden ───────────────────────────────────────────────────

    def _pixel_brightness(self, rgb: Color) -> float:
        """Helligkeit eines Pixels als 0.0..1.0 (max-Kanal)."""
        return max(rgb) / 255.0

    def _scalar_level(self, rgb: Color, lo: int, hi: int) -> int:
        """Mappt die Pixel-Helligkeit in [lo, hi] und gibt einen int-Wert 0..255 zurueck."""
        L = self._pixel_brightness(rgb)
        return max(0, min(255, int(round(lo + (hi - lo) * L))))

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
                v = self._scalar_level(rgb, self.intensity_min, self.intensity_max)
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
        und liefert {fid: {color_r/g/b}}. Der echte Output laeuft ueber write()."""
        if not self._running or not self.fixture_grid:
            return {}
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        # Effektive Rate = Basisrate (matrix_speed) × Function.speed-Master.
        # So steuern VC-Slider (EFFECT_SPEED / globaler SPEED) das Matrix-Tempo.
        rate = self.matrix_speed * max(0.0, float(self.speed))
        # Phase 4: unbeschraenkter Akkumulator (kein % mehr)
        self._step = self._step + rate * dt

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
        # Effektive Rate = Basisrate (matrix_speed) × Function.speed-Master.
        # So steuern VC-Slider (EFFECT_SPEED / globaler SPEED) das Matrix-Tempo.
        rate = self.matrix_speed * max(0.0, float(self.speed))
        # Phase 4: unbeschraenkter Akkumulator (kein % mehr)
        self._step = self._step + rate * dt
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
            for ch in get_channels_for_patched(fx):
                attr = (ch.attribute or "").lower()
                # ── Style-Kanalmaske ────────────────────────────────────────
                if self.style in (MatrixStyle.RGB, MatrixStyle.RGBW):
                    if attr == "color_r":
                        val = r
                    elif attr == "color_g":
                        val = g
                    elif attr == "color_b":
                        val = b
                    elif attr == "color_w" and self.style == MatrixStyle.RGBW:
                        val = round(min(r, g, b) * self.white_amount / 100)
                    elif attr in ("intensity", "dimmer", "master"):
                        if not self.drive_intensity:
                            continue
                        val = 255
                    else:
                        continue  # andere Kanaele unangetastet lassen
                elif self.style == MatrixStyle.DIMMER:
                    if attr in ("intensity", "dimmer", "master"):
                        val = self._scalar_level(rgb, self.intensity_min, self.intensity_max)
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
        # Richtung anwenden: reverse negiert die Phase
        p = -phase if self.direction == "reverse" else phase
        pixels: list[Color] = [(0, 0, 0)] * (cols * rows)
        algo = self.algorithm

        for row in range(rows):
            for col in range(cols):
                idx = row * cols + col
                c1, c2, c3 = self.color1, self.color2, self.color3

                if algo == RgbAlgorithm.PLAIN:
                    pixels[idx] = c1

                elif algo == RgbAlgorithm.CHASE_H:
                    runner_count = max(1, int(self.params.get("runner_count", 1)))
                    runner_width = max(1, int(self.params.get("runner_width", 1)))
                    invert = bool(self.params.get("invert", False))
                    pos = int(p) % cols
                    spacing = cols / runner_count
                    on = False
                    for k in range(runner_count):
                        start = (pos + int(round(k * spacing))) % cols
                        for w in range(runner_width):
                            if (start + w) % cols == col:
                                on = True
                                break
                        if on:
                            break
                    lit = on != invert  # XOR: invert dreht An/Aus um
                    pixels[idx] = c1 if lit else (0, 0, 0)

                elif algo == RgbAlgorithm.CHASE_V:
                    runner_count = max(1, int(self.params.get("runner_count", 1)))
                    runner_width = max(1, int(self.params.get("runner_width", 1)))
                    invert = bool(self.params.get("invert", False))
                    pos = int(p) % rows
                    spacing = rows / runner_count
                    on = False
                    for k in range(runner_count):
                        start = (pos + int(round(k * spacing))) % rows
                        for w in range(runner_width):
                            if (start + w) % rows == row:
                                on = True
                                break
                        if on:
                            break
                    lit = on != invert
                    pixels[idx] = c1 if lit else (0, 0, 0)

                elif algo == RgbAlgorithm.CHASE_DIAG:
                    on = (row + col + int(p)) % 2 == 0
                    pixels[idx] = c1 if on else c2

                elif algo == RgbAlgorithm.WIPE_H:
                    t = (p % cols) / cols
                    pixels[idx] = c1 if col / cols < t else c2

                elif algo == RgbAlgorithm.WIPE_V:
                    t = (p % rows) / rows
                    pixels[idx] = c1 if row / rows < t else c2

                elif algo == RgbAlgorithm.RAINBOW:
                    hue = ((col + row * 0.5 + p * 30) % 360)
                    pixels[idx] = hsv_to_rgb(hue, 1.0, 1.0)

                elif algo == RgbAlgorithm.RANDOM:
                    import random
                    r = random.randint(0, 1)
                    pixels[idx] = [c1, c2, c3][r % 3]

                elif algo == RgbAlgorithm.SPARKLE:
                    import random
                    on = random.random() < 0.1
                    pixels[idx] = c1 if on else (0, 0, 0)

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

                elif algo == RgbAlgorithm.COLOR_SCROLL:
                    # Wandernde 3-Farben-Baender: jeder Pixel zeigt reihum c1/c2/c3.
                    palette = (c1, c2, c3)
                    pixels[idx] = palette[(col - int(p)) % 3]

                elif algo == RgbAlgorithm.CHASE_MULTI:
                    # Ein laufender Pixel, dessen Farbe pro Runde wechselt.
                    pos = int(p) % cols
                    if pos == col:
                        rounds = int(p) // cols
                        pixels[idx] = (c1, c2, c3)[rounds % 3]
                    else:
                        pixels[idx] = (0, 0, 0)

                # ── Koordinatenbasierte Algorithmen (I2.3) ────────────────────

                elif algo == RgbAlgorithm.CENTER_OUT:
                    # Expandierender Quadrat-Ring ab Mitte (Chebyshev-Distanz).
                    # Auf 1×N wirkt er beidseitig (symmetrisch um die Mitte).
                    cx = (cols - 1) / 2.0
                    cy = (rows - 1) / 2.0
                    c1 = self.color1
                    off = (0, 0, 0)
                    invert = bool(self.params.get("invert", False))
                    width = max(1, int(self.params.get("runner_width", 1)))
                    maxr = max(cx, cy)
                    d = max(abs(col - cx), abs(row - cy))
                    front = p % (maxr + width + 1)
                    lit = (d <= front) and (d > front - width)
                    pixels[idx] = c1 if (lit != invert) else off

                elif algo == RgbAlgorithm.OUTER_IN:
                    # Kontrahierender Ring von aussen nach innen.
                    cx = (cols - 1) / 2.0
                    cy = (rows - 1) / 2.0
                    c1 = self.color1
                    off = (0, 0, 0)
                    invert = bool(self.params.get("invert", False))
                    width = max(1, int(self.params.get("runner_width", 1)))
                    maxr = max(cx, cy)
                    d2 = maxr - max(abs(col - cx), abs(row - cy))
                    front = p % (maxr + width + 1)
                    lit = (d2 <= front) and (d2 > front - width)
                    pixels[idx] = c1 if (lit != invert) else off

                elif algo == RgbAlgorithm.BOUNCE_H:
                    # Pingpong-Laeufer ueber die Spalten.
                    c1 = self.color1
                    off = (0, 0, 0)
                    invert = bool(self.params.get("invert", False))
                    width = max(1, int(self.params.get("runner_width", 1)))
                    span = max(1, cols - 1)
                    pos = span - abs((int(p) % (2 * span)) - span)
                    lit = abs(col - pos) < width
                    pixels[idx] = c1 if (lit != invert) else off

                elif algo == RgbAlgorithm.BOUNCE_V:
                    # Pingpong-Laeufer ueber die Reihen.
                    c1 = self.color1
                    off = (0, 0, 0)
                    invert = bool(self.params.get("invert", False))
                    width = max(1, int(self.params.get("runner_width", 1)))
                    span = max(1, rows - 1)
                    pos = span - abs((int(p) % (2 * span)) - span)
                    lit = abs(row - pos) < width
                    pixels[idx] = c1 if (lit != invert) else off

                elif algo == RgbAlgorithm.DIAG_WAVE:
                    # Wandernde Diagonalbande.
                    c1 = self.color1
                    off = (0, 0, 0)
                    invert = bool(self.params.get("invert", False))
                    width = max(1, int(self.params.get("runner_width", 1)))
                    period = max(2, cols + rows - 1)
                    band = (col + row - int(p)) % period
                    lit = band < width
                    pixels[idx] = c1 if (lit != invert) else off

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

        return pixels

    def _generate(self) -> list[Color]:
        """Back-Compat-Wrapper fuer MatrixPreview und _DemoGrid in effect_mini_preview.py."""
        return self._render(self._step)

    def to_dict(self) -> dict:
        d = super().to_dict()  # id, name, type, intensity, speed, folder
        d.update({
            "cols": self.cols, "rows": self.rows,
            "fixture_grid": self.fixture_grid,
            "algorithm": self.algorithm.value,
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
        self.algorithm = RgbAlgorithm(d.get("algorithm", "Plain"))
        self.color1 = tuple(d.get("color1", [255, 0, 0]))
        self.color2 = tuple(d.get("color2", [0, 0, 255]))
        self.color3 = tuple(d.get("color3", [0, 255, 0]))
        # Animationsrate: neuer Key "matrix_speed"; Alt-Shows hatten "speed".
        self.matrix_speed = float(d.get("matrix_speed", d.get("speed", 1.0)))
        self.direction = d.get("direction", "forward")
        # drive_intensity: R1-Default True fuer Alt-Shows (ohne Key) bleibt hell.
        self.drive_intensity = bool(d.get("drive_intensity", True))
        # Phase-3-Style-Felder (Default RGB damit Alt-Shows unveraendert bleiben).
        self.style = MatrixStyle(d.get("style", "RGB"))
        self.white_amount = int(d.get("white_amount", 100))
        self.intensity_min = int(d.get("intensity_min", 0))
        self.intensity_max = int(d.get("intensity_max", 255))
        self.shutter_min = int(d.get("shutter_min", 0))
        self.shutter_max = int(d.get("shutter_max", 255))
        # Phase-4-Parameter
        self.params = dict(d.get("params", {}))

    @classmethod
    def from_dict(cls, d: dict) -> "RgbMatrixInstance":
        m = cls(name=d.get("name", "RGB Matrix"), fid=d.get("id"))
        m.apply_dict(d)
        return m
