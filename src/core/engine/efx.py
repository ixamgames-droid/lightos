"""EFX Engine — Automatische Pan/Tilt Bewegungsmuster wie in QLC+.

Wie die RGB-Matrix ist EFX seit dem Programmer-Umbau eine **echte Funktion**
(`Function`-Subklasse, `FunctionType.EFX`, Marker ``"motion": True`` zur
Unterscheidung von LayeredEffect/Carousel, die sich denselben Typ teilen).
Dadurch wird die Bewegung im zentralen Renderer ins DMX geschrieben (write()),
erscheint in der Bibliothek und ist auf VC/MIDI legbar.
"""
from __future__ import annotations
import math
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from .function import Function, FunctionType

if TYPE_CHECKING:
    from src.core.dmx.universe import Universe
    from src.core.database.models import PatchedFixture


class EfxAlgorithm(str, Enum):
    CIRCLE    = "Circle"
    EIGHT     = "Eight"
    LINE      = "Line"
    DIAMOND   = "Diamond"
    SQUARE    = "Square"
    TRAPEZ    = "Trapez"
    LISSAJOUS = "Lissajous"
    RANDOM    = "Random"
    TRIANGLE  = "Triangle"
    CUSTOM    = "Custom Path"


# Formen mit harten Kanten (echte Polygone, scharfe Ecken): Phase laeuft die
# Eckpunkte linear ab — jede Kante bekommt denselben Phasen-Anteil (1/n). Damit
# fahren Quadrat/Dreieck/Raute/Trapez WIRKLICH zur Ecke (kein „verschliffenes"
# Abschneiden wie bei der frueheren Trig-Naeherung). Reihenfolge = Umlaufsinn.
def _polygon_verts(algo: "EfxAlgorithm", hw: float, hh: float):
    if algo == EfxAlgorithm.SQUARE:
        return ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))
    if algo == EfxAlgorithm.DIAMOND:
        return ((0.0, -hh), (hw, 0.0), (0.0, hh), (-hw, 0.0))
    if algo == EfxAlgorithm.TRAPEZ:
        # schmale Oberkante (halbe Breite), volle Unterkante.
        return ((-hw * 0.5, -hh), (hw * 0.5, -hh), (hw, hh), (-hw, hh))
    if algo == EfxAlgorithm.TRIANGLE:
        return ((0.0, -hh), (hw, hh), (-hw, hh))
    return None


@dataclass
class EfxFixture:
    fid: int
    start_offset: float = 0.0   # Phase-Offset 0.0–1.0 (für Fan-Effekte)
    pan_attr:  str = "pan"
    tilt_attr: str = "tilt"


def _find_fixture(patch_cache, fid):
    for fx in patch_cache or ():
        if getattr(fx, "fid", None) == fid:
            return fx
    return None


def advance_phase(phase: float, bounce_dir: float, delta: float,
                  direction: str, loop: bool) -> tuple[float, float]:
    """Schreibt eine 0..1-Phase um ``delta`` fort, gibt ``(phase, bounce_dir)``
    zurueck. EINE Quelle der Richtungs-/Bounce-Logik fuer ``EfxInstance._advance``
    UND die Vorschau-Widgets (``efx_view``), damit Vorschau und echte Bewegung
    IDENTISCH sind — inklusive One-Shot-Bounce: einmal hin und zurueck, dann HALTEN
    (``bounce_dir`` -> 0), statt in der Vorschau endlos weiterzuschwingen.
    RANDOM und Bus-Sync behandelt der Aufrufer separat (vor diesem Aufruf)."""
    if not loop and direction != "bounce":
        # One-Shot (Loop aus): Phase klemmt am Ende, Position wird gehalten.
        if direction == "backward":
            return max(0.0, phase - delta), bounce_dir
        return min(1.0, phase + delta), bounce_dir
    if direction == "backward":
        return (phase - delta) % 1.0, bounce_dir
    if direction == "bounce":
        if bounce_dir == 0.0 and loop:
            bounce_dir = 1.0  # nach beendetem One-Shot wieder loopen
        phase += delta * bounce_dir
        if phase >= 1.0:
            return 1.0, -1.0
        if phase <= 0.0:
            # One-Shot-Bounce: einmal hin und zurueck, dann halten.
            return 0.0, (1.0 if loop else 0.0)
        return phase, bounce_dir
    return (phase + delta) % 1.0, bounce_dir


class EfxInstance(Function):
    """EFX-Bewegung als echte Funktion.

    ``fixtures`` ist die eigene Geraeteliste (EfxFixture mit pan/tilt-Attr).
    Animationsrate = ``speed_hz`` (bewusst getrennt vom Function.speed-Master).
    """

    function_type = FunctionType.EFX
    tempo_sync_default = True

    def __init__(self, name: str = "EFX", fid: int | None = None):
        super().__init__(name, fid)
        self.algorithm: EfxAlgorithm = EfxAlgorithm.CIRCLE
        self.fixtures: list[EfxFixture] = []
        # Gruppen-Bindung (NUR Programmer-Listen-Scope): unter welcher Fixture-
        # Gruppe dieser EFX im Programmer aufgelistet wird. Bewusst per Gruppen-
        # NAME (stabil ueber Show-Save/Load — DB-ids aendern sich beim Neuladen,
        # siehe rgb_matrix.source_group). None = ungebunden -> erscheint in jeder
        # Gruppe. Beeinflusst NICHT das Rendering/DMX.
        self.source_group: str | None = None
        # Entwurfs-/Commit-Status (Programmer „Entwurf bis Speichern"). True =
        # dauerhaft (serialisiert, an source_group gebunden). False = Live-Entwurf:
        # laeuft zur Vorschau im FunctionManager, wird aber NICHT in die Show
        # serialisiert und beim Wechsel/Verwerfen entfernt. Default True ->
        # geladene/bestehende EFX sind automatisch committed (back-compat);
        # from_dict erbt diesen Default (kein Key, bewusst nicht serialisiert).
        self.committed: bool = True
        # Geometrie
        self.width = 100.0   # 0–255
        self.height = 100.0
        self.x_offset = 128.0
        self.y_offset = 128.0
        self.rotation = 0.0   # Grad
        self.x_freq = 1.0     # für Lissajous
        self.y_freq = 1.0
        self.x_phase = 0.0
        self.y_phase = 90.0
        # Timing
        self.speed_hz = 0.5     # Umdrehungen pro Sekunde
        self.direction = "forward"  # "forward" / "backward" / "bounce"
        # Sichtbarkeit: wenn True, oeffnet write() zusaetzlich Dimmer (=255) und
        # Shutter (Open-Wert), damit bewegte Moving Heads nicht dunkel bleiben
        # (M0.4). Standard False = nur Pan/Tilt, Helligkeit kommt anderswoher.
        self.open_beam = False
        # M4.2: Phasen-Verteilung ueber die Gruppe. spread=1.0 verteilt die
        # Geraete gleichmaessig ueber einen vollen Zyklus (Fan), 0.0 = synchron.
        self.spread = 1.0
        self.mirror = False     # jedes 2. Geraet gespiegelt (Pan invertiert)
        # Geraete-Verhaeltnis: WIE die Koepfe zueinander durch die Figur laufen.
        # Orthogonal zur globalen Richtung (direction) und zur Einzelgeraete-Phase
        # (EfxFixture.start_offset).
        #   "sync"   = alle Koepfe synchron (gemeinsam dieselbe Figur)
        #   "fan"    = gleichmaessig ueber die Figur verteilt (spread = Anteil 0..1,
        #              bei 2 Koepfen und spread=1 => 180 Grad versetzt)
        #   "offset" = fester Versatz pro Geraet in Grad (phase_offset_deg)
        self.phase_mode = "fan"
        self.phase_offset_deg = 0.0   # nur fuer phase_mode == "offset"
        # Gegenlaeufig: jedes 2. Geraet durchlaeuft die Figur in umgekehrter
        # Richtung (z. B. zwei Koepfe, einer im Uhrzeigersinn, einer dagegen).
        self.counter_rotate = False
        # Dual-Tilt-Spider (>=2 Tilt-Koepfe, kein Pan): WIE die einzelnen Tilt-
        # Koepfe INNERHALB eines Geraets zueinander laufen. Jeder Kopf k bekommt
        # die Tilt-Komponente der Figur bei Phasen-Versatz (k/head_count)*head_spread
        # -> eine Welle/Chase rollt ueber die Bars (ersetzt die frueher starre
        # 255-tilt-Spiegelung). 0 = alle Koepfe synchron, 1 = gleichmaessig ueber
        # einen vollen Figur-Zyklus verteilt. Orthogonal zur Geraete-Phase
        # (phase_mode/spread, die wirkt ZWISCHEN Geraeten).
        # Default 1.0 = die klassische gegengleiche Schere: bei 2 Tilt-Koepfen
        # liegt Kopf 1 um (1/2)*1.0 = 0.5 Zyklus = 180 Grad versetzt, die Bars
        # schwenken also GEGENPHASIG (Modul-Docstring) statt nur 90 Grad versetzt.
        self.head_spread = 1.0
        # T-9: 16-bit-Ausgabe. Wenn True und das Geraet hat pan_fine/tilt_fine,
        # wird die Sub-Step-Praezision der berechneten Float-Position in die
        # Fine-Kanaele geschrieben (geschmeidige Bewegung statt 256 Stufen).
        # coarse bleibt bit-identisch (Truncation), fine = Rest -> additiv/sicher.
        self.bit16 = True
        # Relativ/additiv (To-Do #7): Bewegung um die aktuelle Pan/Tilt-Position
        # JEDES Geraets (beim Start aus dem Programmer geschnappt) statt um die
        # feste Mitte x_offset/y_offset — „fahr zur Buehne, dann dort die Acht".
        self.relative = False
        # RANDOM: zufaellige Wegpunkte im Feld (width x height). random_seed macht
        # die Sequenz reproduzierbar (persistiert); jeder neue Start bzw. „Neue Bahn"
        # (reseed) erzeugt eine andere Bahn. Der Walk laeuft kontinuierlich und
        # wiederholt sich nie (monotoner Fortschritt durch eine unendliche Sequenz).
        self.random_seed = random.randint(1, 2_000_000_000)
        # Loop: True = Endlosbewegung (Standard). False = One-Shot — die Phase
        # klemmt am Ende (Position wird gehalten), bis neu gestartet wird.
        self.loop = True
        # Custom Path (EfxAlgorithm.CUSTOM): Referenz auf einen Pfad der
        # EfxPathLibrary (path_id) + eingebettete Kopie (path_data), damit die
        # Show auch ohne Bibliothekseintrag abspielbar bleibt.
        self.path_id: str | None = None
        self.path_data: dict | None = None
        self._embedded_path = None  # EfxPath-Cache aus path_data
        # State
        self._phase = 0.0
        self._bounce_dir = 1.0
        self._last_tick = 0.0
        # Relativ-Modus: pro Geraet das beim Start geschnappte Zentrum (Pan, Tilt).
        self._centers: dict[int, tuple[float, float]] = {}
        # RANDOM: monoton fortlaufender Fortschritt (1.0 = ein Wegpunkt weiter).
        self._rand_progress = 0.0

    # Anzahl Wegpunkte, die die _calc-VORSCHAU eines RANDOM-EFX zeigt.
    _RANDOM_PREVIEW = 8

    def _on_start(self):
        self._last_tick = time.monotonic()
        self._rand_progress = 0.0
        if not self.loop:
            # One-Shot: deterministisch am Anfang (bzw. Ende bei backward)
            # starten, damit jeder Start die komplette Bewegung abspielt.
            self._phase = 1.0 if self.direction == "backward" else 0.0
            self._bounce_dir = 1.0
        # Relativ (To-Do #7): aktuelle Pan/Tilt-Position je Geraet als Zentrum
        # merken (aus dem Programmer). Ohne gesetzte Position bleibt es bei der
        # festen Mitte (x_offset/y_offset).
        self._centers = {}
        if self.relative:
            try:
                from src.core.app_state import get_state
                prog = get_state().programmer
                for fx in self.fixtures:
                    p = prog.get(fx.fid, {})
                    pan, tilt = p.get(fx.pan_attr), p.get(fx.tilt_attr)
                    if pan is not None or tilt is not None:
                        self._centers[fx.fid] = (
                            float(pan if pan is not None else self.x_offset),
                            float(tilt if tilt is not None else self.y_offset))
            except Exception:
                self._centers = {}
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
        """WP-Tempo / Speed-Dial-Sync: bus-synchron -> auf die aktuelle Bus-Position
        re-ankern (local_beats startet bei 0, gemeinsam mit der sync_group). Frei ->
        Phase/Random-Walk auf 0 zuruecksetzen (wie do_action('reset'))."""
        bus_id = getattr(self, "tempo_bus_id", "") or ""
        if bus_id:
            try:
                from src.core.engine.tempo_bus import get_tempo_bus_manager
                bus = get_tempo_bus_manager().bus_for_effect(bus_id)
                if bus is not None:
                    self._beat_anchor = bus.take_anchor()
                    return
            except Exception:
                pass
        self._phase = 1.0 if (not self.loop and self.direction == "backward") else 0.0
        self._rand_progress = 0.0

    def _sync_from_bus(self) -> bool:
        """WP-Tempo: Liegt dieser EFX auf einem LAUFENDEN Tempo-Bus, wird die Phase
        direkt aus der Bus-Position abgeleitet (phasenkohaerent, exakte ×-Verhaeltnisse)
        statt aus dt akkumuliert. Liefert True, wenn so behandelt; sonst False — dann
        laeuft der normale dt-Pfad in _advance byte-identisch weiter (Free-Run).

        effect_pos = (bus.position - _beat_anchor) * tempo_multiplier + phase_offset
        (Einheit Beats; bei mult=1 ist 1 Beat eine volle Figur-Umrundung). direction/
        loop/bounce werden auf effect_pos abgebildet:
          forward loop  -> _phase = effect_pos % 1
          backward loop -> _phase = (-effect_pos) % 1
          bounce        -> Dreieck 0->1->0 ueber 2 Beats
          one-shot      -> einmal 0->1 (bzw. 1->0 backward), dann am Ende gehalten
          RANDOM        -> _rand_progress = ±effect_pos (unbeschraenkter Walk)."""
        bus_id = getattr(self, "tempo_bus_id", "") or ""
        if not bus_id:
            return False
        _tbm = None
        try:
            from src.core.engine.tempo_bus import get_tempo_bus_manager
            _tbm = get_tempo_bus_manager()
            bus = _tbm.get(bus_id)
        except Exception:
            bus = None
        if bus is None:
            return False
        bpm, _bc, _bp, pos = bus.snapshot()
        if bpm <= 0:
            # F5: nur bei AKTIVEM Freeze die Phase HALTEN (True = dt-Pfad ueberspringen);
            # sonst Free-Run-Fallback wie bisher (Bus nur noch nicht gestartet).
            return bool(_tbm is not None and _tbm.is_frozen())
        mult = getattr(self, "tempo_multiplier", 1.0) or 1.0
        off = getattr(self, "phase_offset", 0.0) or 0.0
        anchor = getattr(self, "_beat_anchor", 0.0)
        # round(...,9) gegen Float-Kanten (Polygon-Ecken / Bounce-Umkehrpunkte).
        effect_pos = round((pos - anchor) * mult + off, 9)
        if self.algorithm == EfxAlgorithm.RANDOM:
            self._rand_progress = -effect_pos if self.direction == "backward" else effect_pos
            return True
        if not self.loop and self.direction != "bounce":
            if self.direction == "backward":
                self._phase = max(0.0, 1.0 - effect_pos)
            else:
                # auf [0,1] klemmen (negativer phase_offset darf nicht unter 0 ziehen).
                self._phase = max(0.0, min(1.0, effect_pos))
            return True
        if self.direction == "bounce":
            if self.loop:
                tri = effect_pos % 2.0
                self._phase = tri if tri <= 1.0 else (2.0 - tri)
            else:
                # One-Shot-Bounce: einmal 0->1->0, dann am Ende bei 0.0 HALTEN —
                # wie der Free-Run-Pfad (_bounce_dir=0 nach einer Runde), statt endlos
                # weiterzuschwingen.
                e = min(2.0, max(0.0, effect_pos))
                self._phase = e if e <= 1.0 else (2.0 - e)
            return True
        if self.direction == "backward":
            self._phase = (-effect_pos) % 1.0
        else:
            self._phase = effect_pos % 1.0
        return True

    def _advance(self, dt: float):
        """Treibt die Phase um dt Sekunden voran (Richtung beachtet).
        Effektive Rate = speed_hz × Function.speed-Master, damit VC-Slider
        (EFFECT_SPEED / globaler SPEED) das EFX-Tempo steuern."""
        # WP-Tempo: bus-synchron? -> Phase direkt aus der Bus-Position ableiten
        # (statt dt zu akkumulieren). Free-Run laeuft sonst unveraendert weiter.
        if self._sync_from_bus():
            return
        delta = self.speed_hz * max(0.0, float(self.speed)) * dt
        if self.algorithm == EfxAlgorithm.RANDOM:
            # Random ignoriert Loop/Bounce/Phase: kontinuierlicher, nie endender
            # Walk durch eine unendliche Zufalls-Wegpunkt-Sequenz.
            self._rand_progress += (-delta if self.direction == "backward" else delta)
            return
        # Richtungs-/Bounce-Logik zentral (eine Quelle, identisch zur Vorschau):
        self._phase, self._bounce_dir = advance_phase(
            self._phase, self._bounce_dir, delta, self.direction, self.loop)

    def _fan_for(self, i: int, n: int) -> float:
        """Phasen-Versatz (0..) des i-ten Geraets gemaess Geraete-Verhaeltnis
        (phase_mode). Einzige Quelle fuer Engine UND Vorschau (Werte-gleich)."""
        if n <= 1:
            return 0.0
        mode = getattr(self, "phase_mode", "fan")
        if mode == "sync":
            return 0.0
        if mode == "offset":
            return i * (float(getattr(self, "phase_offset_deg", 0.0)) / 360.0)
        return (i / n) * self.spread   # "fan"

    def _fixture_center(self, fx: "EfxFixture") -> tuple[float, float]:
        """Mitte, um die das Geraet die Figur faehrt: im Relativ-Modus das beim
        Start geschnappte Zentrum (To-Do #7), sonst die feste Mitte
        (x_offset/y_offset)."""
        if self.relative and fx.fid in self._centers:
            return self._centers[fx.fid]
        return self.x_offset, self.y_offset

    def _fixture_phase(self, i: int, n: int, fx: "EfxFixture") -> float:
        """Figur-Phase 0..1 des i-ten Geraets: globale Phase (+ Gegenlauf bei
        jedem 2. Geraet) + Einzelgeraete-Offset + Geraete-Faecher (phase_mode).
        Einzige Quelle fuer _values UND die Kopf-Pan+Tilt-Welle (_head_pan_tilts)
        — bei Aenderung wirkt beides konsistent."""
        counter = bool(getattr(self, "counter_rotate", False))
        base = -self._phase if (counter and i % 2 == 1) else self._phase
        return (base + fx.start_offset + self._fan_for(i, n)) % 1.0

    def _values(self) -> dict[int, dict[str, int]]:
        """{fid: {pan_attr: val, tilt_attr: val}} fuer die aktuelle Phase."""
        result = {}
        n = len(self.fixtures)
        is_random = (self.algorithm == EfxAlgorithm.RANDOM)
        counter = bool(getattr(self, "counter_rotate", False))
        for i, fx in enumerate(self.fixtures):
            cx, cy = self._fixture_center(fx)
            if is_random:
                # Kontinuierlicher Random-Walk im Feld; spread>0 dekorreliert die
                # Geraete (jeder faehrt eine andere Zufallsbahn), spread=0 synchron.
                offs = 0.0 if getattr(self, "phase_mode", "fan") == "sync" \
                    else (i * 1.7 * self.spread if n > 1 else 0.0)
                progress = -self._rand_progress if (counter and i % 2 == 1) else self._rand_progress
                x, y = self._random_xy(progress + offs)
                pan = max(0, min(255, cx + x))
                tilt = max(0, min(255, cy + y))
            else:
                pan, tilt = self._calc(self._fixture_phase(i, n, fx), cx, cy)
            if self.mirror and (i % 2 == 1):
                pan = 255 - pan
            result[fx.fid] = self._pan_tilt_attrs(fx, pan, tilt)
        return result

    def _head_pan_tilts(self, fid: int,
                        head_count: int) -> list[tuple[int, str, float, str, float]]:
        """Pan+Tilt-Werte der ZUSAETZLICHEN Koepfe (k=1..head_count-1) eines
        Mehrkopf-Fixtures bei der aktuellen Phase. Jeder Kopf faehrt die Figur um
        (k/head_count)*head_spread phasenversetzt -> eine Pan+Tilt-Welle/Chase
        rollt ueber die Koepfe (FM-16b; verallgemeinert die fruehere tilt-only
        Spider-Kopf-Welle, ersetzt die starre Kopf-0-Spiegelung via
        resolve_attr_channels). Liefert (k, pan_attr, pan_float, tilt_attr,
        tilt_float) je Zusatzkopf; Geraete-Spiegelung (mirror — nur Pan, wie in
        _values) ist bereits angewandt, invert_pan/invert_tilt NICHT (der Aufrufer
        wendet sie pro Achse an, exakt wie apply_pan_tilt_orientation es fuer
        Kopf 0 macht). Kopf 0 steckt schon in den Basis-Attrs aus _values()."""
        out: list[tuple[int, str, float, str, float]] = []
        if head_count < 2:
            return out
        n = len(self.fixtures)
        i = next((idx for idx, f in enumerate(self.fixtures) if f.fid == fid), None)
        if i is None:
            return out
        fx = self.fixtures[i]
        pa, ta = fx.pan_attr, fx.tilt_attr
        cx, cy = self._fixture_center(fx)
        hs = max(0.0, float(getattr(self, "head_spread", 1.0)))
        counter = bool(getattr(self, "counter_rotate", False))
        mirror_dev = bool(getattr(self, "mirror", False)) and (i % 2 == 1)
        is_random = (self.algorithm == EfxAlgorithm.RANDOM)
        base_phase = self._fixture_phase(i, n, fx)  # bei RANDOM ungenutzt
        for k in range(1, head_count):
            if is_random:
                # Jeder Kopf wandert eine eigene Zufallsbahn (Dekorrelation via
                # k*1.7*hs, wie in _values). Gegenlauf ist GERAETE-weit (i%2, wie
                # Kopf 0 in _values) — NICHT pro Kopf, sonst brechen bei hs=0 die
                # Koepfe auseinander statt synchron zu laufen (Review-Fund).
                prog = -self._rand_progress if (counter and i % 2 == 1) else self._rand_progress
                x, y = self._random_xy(prog + k * 1.7 * hs)
                pval, tval = cx + x, cy + y
            else:
                phase = (base_phase + (k / head_count) * hs) % 1.0
                pval, tval = self._calc(phase, cx, cy)
            if mirror_dev:            # wie _values: mirror kippt NUR Pan
                pval = 255.0 - pval
            out.append((k, pa, max(0.0, min(255.0, pval)),
                        ta, max(0.0, min(255.0, tval))))
        return out

    @staticmethod
    def _polygon(phase: float, verts) -> tuple[float, float]:
        """Position auf einem Polygon (harte Kanten). Die Phase 0..1 laeuft die
        Eckpunkte v0->v1->...->v0 linear ab; jede Kante bekommt 1/n der Phase, die
        Figur faehrt also exakt in jede Ecke (scharfe Ecken, kein Spline)."""
        n = len(verts)
        if n == 0:
            return 0.0, 0.0
        fp = (phase % 1.0) * n
        seg = int(fp) % n
        tt = fp - math.floor(fp)
        x0, y0 = verts[seg]
        x1, y1 = verts[(seg + 1) % n]
        return x0 + (x1 - x0) * tt, y0 + (y1 - y0) * tt

    @staticmethod
    def _split16(v: float) -> tuple[int, int]:
        """255er-Float -> (coarse, fine) als 16-bit MSB/LSB. Truncation, damit
        coarse exakt int(v) bleibt (keine Regression ggü. der 8-bit-Ausgabe)."""
        v16 = max(0, min(65535, int(float(v) * 256.0)))
        return v16 >> 8, v16 & 0xFF

    def _pan_tilt_attrs(self, fx: "EfxFixture", pan: float, tilt: float) -> dict:
        """Pan/Tilt-Schicht eines Geraets; bei bit16 zusaetzlich die Fine-Werte.
        Fine-Keys schaden Geraeten ohne Fine-Kanal nicht (write() schreibt nur
        vorhandene Kanaele)."""
        if not self.bit16:
            return {fx.pan_attr: int(max(0, min(255, pan))),
                    fx.tilt_attr: int(max(0, min(255, tilt)))}
        pc, pf = self._split16(max(0.0, min(255.0, pan)))
        tc, tf = self._split16(max(0.0, min(255.0, tilt)))
        return {fx.pan_attr: pc, f"{fx.pan_attr}_fine": pf,
                fx.tilt_attr: tc, f"{fx.tilt_attr}_fine": tf}

    # ── Random-Wegpunkte (To-Do: echtes Random in definierbarem Feld) ──────────
    def _random_waypoint(self, k: int) -> tuple[float, float]:
        """Zufaelliger Wegpunkt (Offset um die Mitte) im Feld width x height.
        Deterministisch aus (random_seed, Index k): gleicher Seed -> reproduzierbar,
        jeder Index ein anderer Punkt -> die Sequenz wiederholt sich nie."""
        seed = ((int(self.random_seed) * 2654435761) ^ (int(k) * 40503)) & 0x7FFFFFFF
        rng = random.Random(seed)
        hw, hh = self.width / 2.0, self.height / 2.0
        return (rng.uniform(-hw, hw), rng.uniform(-hh, hh))

    def _random_xy(self, progress: float) -> tuple[float, float]:
        """Position entlang des Random-Walks: weich (Cosinus-Ease) von Wegpunkt
        floor(progress) zum naechsten."""
        seg = math.floor(progress)
        tt = progress - seg
        x0, y0 = self._random_waypoint(seg)
        x1, y1 = self._random_waypoint(seg + 1)
        s = (1.0 - math.cos(max(0.0, min(1.0, tt)) * math.pi)) / 2.0
        return (x0 + (x1 - x0) * s, y0 + (y1 - y0) * s)

    def tick(self) -> dict[int, dict[str, int]]:
        """Nur fuer die Vorschau (zeitbasiert via monotonic)."""
        if not self._running:
            return {}
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        self._advance(dt)
        return self._values()

    def assign_movers_auto(self, allow_all: bool = True) -> int:
        """Weist bewegliche Geraete zu, falls die eigene ``fixtures``-Liste leer
        ist: zuerst die aktuelle Auswahl, sonst (nur wenn ``allow_all``) alle
        gepatchten Movingheads. Mover-Erkennung via ``app_state.mover_fids`` —
        gemeinsame Quelle mit dem EFX-Editor (``_patched_movers``). Hat sie bereits
        Geraete, bleibt sie unberuehrt. Gibt die Geraeteanzahl danach zurueck.

        Fuer den VC-Trigger-Pfad gedacht (analog UI-04 im EFX-Tab): ein per Button
        gestarteter EFX ohne Geraete laeuft sonst stumm (``write()`` No-Op)."""
        if self.fixtures:
            return len(self.fixtures)
        try:
            from src.core.app_state import get_state, mover_fids
        except Exception:
            return 0
        try:
            sel = [int(f) for f in get_state().get_selected_fids()]
        except Exception:
            sel = []
        movers = mover_fids(sel) if sel else []
        if not movers and allow_all:
            movers = mover_fids(None)
        if movers:
            self.fixtures = [EfxFixture(fid=fid) for fid in movers]
        return len(self.fixtures)

    def write(self, universes: dict[int, "Universe"],
              patch_cache: list["PatchedFixture"],
              dt: float,
              function_registry=None):
        """Per-Frame-Output: schreibt Pan/Tilt der EFX-Geraete ins DMX."""
        if not self._running or not self.fixtures:
            return
        self._advance(dt)
        try:
            from src.core.app_state import (get_channels_for_patched,
                                            apply_pan_tilt_orientation,
                                            open_value_for,
                                            resolve_attr_channels)
        except Exception:
            return
        values = self._values()
        for fid, attrs in values.items():
            fx = _find_fixture(patch_cache, fid)
            if fx is None:
                continue
            universe = universes.get(fx.universe)
            if universe is None:
                continue
            chans = get_channels_for_patched(fx)
            # M0.4: Sichtbarkeit — Dimmer voll + Shutter offen, damit bewegte
            # Moving Heads nicht dunkel bleiben.
            if self.open_beam:
                attrs = dict(attrs)
                attrs["intensity"] = 255
                if any(ch.attribute == "shutter" for ch in chans):
                    attrs["shutter"] = open_value_for(fx, "shutter")
            # M0.2: Pan/Tilt-Invert/Swap des Geraets anwenden.
            attrs = apply_pan_tilt_orientation(fx, attrs)
            # FM-16b: Mehrkopf-Fixtures (>=2 Pan- ODER >=2 Tilt-Kanaele) — jeder
            # weitere Kopf faehrt die Figur um head_spread phasenversetzt: eine
            # Pan+Tilt-Welle/Chase rollt ueber die Koepfe. Nur Achsen mit >=2
            # Kanaelen werden pro Kopf bespielt: reine Dual-Tilt-Spider (0 Pan)
            # bleiben tilt-only (unveraendert), Voll-Mehrkopf-Mover (Hydrabeam/
            # MOVBAR4/…) bekommen jetzt AUCH pro-Kopf-Pan statt der Kopf-0-
            # Spiegelung via resolve_attr_channels. invert_pan/invert_tilt/swap
            # je Zusatzkopf identisch wie Kopf 0 (dieselbe apply_pan_tilt_orientation
            # pro Kopf, unten im Loop).
            tilt_heads = sum(1 for c in chans if (c.attribute or "") == "tilt")
            pan_heads = sum(1 for c in chans if (c.attribute or "") == "pan")
            head_count = max(pan_heads, tilt_heads)
            if head_count >= 2 and (("tilt" in attrs) or ("pan" in attrs)):
                attrs = dict(attrs)
                for k, pa, pval, ta, tval in self._head_pan_tilts(fid, head_count):
                    # Kopf k EXAKT wie Kopf 0 behandeln: BEIDE Achsen packen und
                    # durch dieselbe apply_pan_tilt_orientation schicken. Nur mit
                    # beiden Achsen koppelt invert das 16-bit-Paar bitidentisch
                    # (Float-Invert 255-pval vor _split16 waere um bis zu 256
                    # daneben) UND swap tauscht symmetrisch — eine Teil-Achse
                    # wuerde swap sonst in die falsche Achse schieben und die
                    # vorhandene loeschen (Review-Fund: Swap auf Dual-Tilt-Spider
                    # riss die Kopf-Welle ab). resolve_attr_channels schreibt danach
                    # NUR die attr#k-Keys, fuer die das Fixture wirklich einen
                    # Kopf-k-Kanal hat — fehlende Achsen (Pan beim Spider,
                    # ueberzaehlige Koepfe der kuerzeren Achse) bleiben folgenlos.
                    if self.bit16:
                        pc, pf = self._split16(pval)
                        tc, tf = self._split16(tval)
                        head = {pa: pc, f"{pa}_fine": pf, ta: tc, f"{ta}_fine": tf}
                    else:
                        head = {pa: int(max(0, min(255, pval))),
                                ta: int(max(0, min(255, tval)))}
                    head = apply_pan_tilt_orientation(fx, head)
                    for bkey, val in head.items():
                        attrs[f"{bkey}#{k}"] = val
            # Mehrkopf-Vorkommens-Aufloesung zentral (eine Quelle, identisch zur
            # frueheren Inline-seen-Schleife): resolve_attr_channels mappt jedes
            # attr/attr#N auf sein Kanal-Vorkommen, Kopf>0 spiegelt Kopf 0 als
            # Fallback. Kanaele ohne passenden Wert werden uebersprungen.
            for ch_no, _key, val in resolve_attr_channels(chans, attrs):
                addr = fx.address + ch_no - 1
                if 1 <= addr <= 512:
                    universe.set_channel(addr, max(0, min(255, int(val))))

    def _calc(self, phase: float, cx: float | None = None,
              cy: float | None = None) -> tuple[float, float]:
        t = phase * 2 * math.pi
        hw = self.width / 2
        hh = self.height / 2
        algo = self.algorithm

        if algo == EfxAlgorithm.CIRCLE:
            x = math.cos(t) * hw
            y = math.sin(t) * hh

        elif algo == EfxAlgorithm.EIGHT:
            x = math.sin(t) * hw
            y = math.sin(2 * t) * hh / 2

        elif algo == EfxAlgorithm.LINE:
            x = math.cos(t) * hw
            y = 0.0

        elif algo in (EfxAlgorithm.DIAMOND, EfxAlgorithm.SQUARE,
                      EfxAlgorithm.TRAPEZ, EfxAlgorithm.TRIANGLE):
            # Echte Polygone mit harten Kanten / scharfen Ecken (Raute, Quadrat,
            # Trapez, Dreieck). Phase laeuft die Eckpunkte linear ab — die Figur
            # faehrt WIRKLICH in jede Ecke, statt sie (wie die alte Trig-Naeherung
            # bei Quadrat/Raute) diagonal abzuschneiden.
            x, y = self._polygon(phase, _polygon_verts(algo, hw, hh))

        elif algo == EfxAlgorithm.LISSAJOUS:
            xf = self.x_freq
            yf = self.y_freq
            xp = math.radians(self.x_phase)
            yp = math.radians(self.y_phase)
            x = math.cos(t * xf + xp) * hw
            y = math.sin(t * yf + yp) * hh

        elif algo == EfxAlgorithm.RANDOM:
            # Echtes Random: zufaellige Wegpunkte im Feld (width x height), weich
            # verbunden. _calc liefert die VORSCHAU (ein Durchlauf ueber _RANDOM_PREVIEW
            # Wegpunkte); der Live-Output laeuft kontinuierlich/endlos ueber _values.
            x, y = self._random_xy(phase * float(self._RANDOM_PREVIEW))

        elif algo == EfxAlgorithm.CUSTOM:
            # Custom Path: Punkte normiert 0..1 (x=Pan, y=Tilt), zentriert um
            # 0.5 und über Breite/Höhe skaliert — Size/Rotation/Zentrum wirken
            # damit genauso wie bei den eingebauten Formen.
            path = self._resolve_path()
            if path is not None:
                u, v = path.sample(phase)
                x = (u - 0.5) * self.width
                y = (v - 0.5) * self.height
            else:
                x, y = 0.0, 0.0
        else:
            x, y = 0.0, 0.0

        # Rotation anwenden
        if self.rotation != 0.0:
            rad = math.radians(self.rotation)
            cos_r = math.cos(rad)
            sin_r = math.sin(rad)
            rx = x * cos_r - y * sin_r
            ry = x * sin_r + y * cos_r
            x, y = rx, ry

        cx = self.x_offset if cx is None else cx
        cy = self.y_offset if cy is None else cy
        pan  = max(0, min(255, cx + x))
        tilt = max(0, min(255, cy + y))
        return pan, tilt

    # ── Custom Path ───────────────────────────────────────────────────────────

    def set_custom_path(self, path) -> None:
        """Weist einen EfxPath zu (Referenz + eingebettete Kopie) und schaltet
        auf den Custom-Algorithmus um."""
        if path is None:
            self.path_id = None
            self.path_data = None
            self._embedded_path = None
            return
        self.path_id = path.id
        self.path_data = path.to_dict()
        self._embedded_path = path
        self.algorithm = EfxAlgorithm.CUSTOM

    def _resolve_path(self):
        """Aktiven EfxPath bestimmen: bevorzugt die Bibliothek (Live-Edits
        wirken sofort), sonst die in der Show eingebettete Kopie."""
        try:
            from .efx_path import EfxPath, get_efx_path_library
        except Exception:
            return None
        if self.path_id:
            p = get_efx_path_library().find(self.path_id)
            if p is not None:
                return p
        if self._embedded_path is None and self.path_data:
            try:
                self._embedded_path = EfxPath.from_dict(self.path_data)
            except Exception:
                self._embedded_path = None
        return self._embedded_path

    # ── Live-Programming-API (VC/MIDI, analog RgbMatrixInstance) ─────────────
    #
    # effect_live.py erkennt Funktionen mit list_params/set_param automatisch —
    # damit sind EFX ab jetzt auf Fader/Encoder/Buttons der virtuellen Konsole
    # und auf MIDI-Controls mappbar (gleiche Mechanik wie Chaser/Matrix).

    def list_params(self) -> list:
        from .rgb_matrix_meta import ParamSpec  # lazy: Import-Zyklus vermeiden
        from .efx_path import get_efx_path_library
        path_names = tuple(p.name for p in get_efx_path_library().all())
        algos = tuple(a.value for a in EfxAlgorithm)
        specs = [
            ParamSpec("speed", "Geschwindigkeit (Hz)", "float", 0.5, 0.01, 10.0, 0.1,
                      "Umdrehungen pro Sekunde"),
            ParamSpec("intensity", "Intensität", "float", 1.0, 0.0, 1.0, 0.01,
                      "Per-Effekt-Master (0..1) — wirkt nur auf Dimmer/Shutter "
                      "(bei aktivem 'Dimmer/Shutter öffnen'); auf reine "
                      "Pan/Tilt-Bewegung ohne Dimmer hat der Master keinen Effekt"),
            ParamSpec("size", "Größe", "float", 100.0, 0.0, 255.0, 5.0,
                      "setzt Pan- und Tilt-Hub gemeinsam"),
            ParamSpec("width", "Breite (Pan-Hub)", "float", 100.0, 0.0, 255.0, 5.0),
            ParamSpec("height", "Höhe (Tilt-Hub)", "float", 100.0, 0.0, 255.0, 5.0),
            ParamSpec("x_offset", "Zentrum Pan", "float", 128.0, 0.0, 255.0, 5.0),
            ParamSpec("y_offset", "Zentrum Tilt", "float", 128.0, 0.0, 255.0, 5.0),
            ParamSpec("rotation", "Rotation", "float", 0.0, 0.0, 360.0, 5.0),
            ParamSpec("spread", "Streuung (Fan)", "float", 1.0, 0.0, 1.0, 0.05,
                      "Phasen-Verteilung über die Gruppe (nur bei Verhältnis 'Fächer')"),
            ParamSpec("head_spread", "Welle über Köpfe (Spider)", "float",
                      1.0, 0.0, 1.0, 0.05,
                      "Dual-Tilt-Spider: Phasen-Versatz der einzelnen Tilt-Köpfe "
                      "zueinander (0 = alle synchron, 1 = volle Welle über die Bars)"),
            ParamSpec("phase_mode", "Verhältnis der Geräte", "select", "fan",
                      options=("sync", "fan", "offset"),
                      tooltip="sync = alle Köpfe gleich · fan = gleichmäßig verteilt "
                              "· offset = fester Versatz pro Gerät (Grad)"),
            ParamSpec("phase_offset_deg", "Versatz pro Gerät (°)", "float",
                      0.0, 0.0, 360.0, 5.0,
                      "nur bei Verhältnis 'offset': jeder Kopf um so viel Grad versetzt"),
            ParamSpec("counter_rotate", "Gegenläufig", "bool", False,
                      tooltip="jedes 2. Gerät läuft die Figur entgegengesetzt "
                              "(z. B. zwei Köpfe gegenläufig im Kreis)"),
            ParamSpec("direction", "Richtung", "select", "forward",
                      options=("forward", "backward", "bounce")),
            ParamSpec("loop", "Loop", "bool", True,
                      tooltip="aus = One-Shot: Bewegung läuft einmal und hält am Ende"),
            ParamSpec("mirror", "Spiegeln", "bool", False),
            ParamSpec("relative", "Relativ (additiv)", "bool", False,
                      tooltip="Bewegung um die aktuelle Pan/Tilt-Position (beim Start "
                              "aus dem Programmer) statt um die feste Mitte"),
            ParamSpec("open_beam", "Dimmer/Shutter öffnen", "bool", False),
            ParamSpec("bit16", "16-bit (Fine-Kanäle)", "bool", True,
                      tooltip="Pan/Tilt zusätzlich über pan_fine/tilt_fine ausgeben "
                              "(geschmeidigere Bewegung; Geräte ohne Fine ignorieren es)"),
            ParamSpec("algorithm", "Form", "select", EfxAlgorithm.CIRCLE.value,
                      options=algos),
            # WP-Tempo: Anbindung an einen Tempo-Bus (A/B/C/D) — leer = frei/eigene
            # Geschwindigkeit. Eigene Keys (NICHT phase_offset_deg/speed-Kollision).
            ParamSpec("tempo_bus_id", "Tempo-Bus", "select", "Global",
                      options=("Global", "", "A", "B", "C", "D"),
                      tooltip="Auf welchen Tempo-Bus synchronisieren (leer = frei, "
                              "Global = Master-BPM, A–D = eigene Buses)"),
            ParamSpec("tempo_multiplier", "Tempo ×", "float", 1.0, 0.0625, 16.0, 0.25,
                      "Verhältnis zum Bus (frei, z. B. 0.5 halb, 2 doppelt, 3 dreifach)"),
            ParamSpec("phase_offset", "Tempo-Versatz (Beats)", "float", 0.0, 0.0, 1.0, 0.05,
                      "Phasen-Versatz in Beats (versetzter Start auf dem Bus)"),
        ]
        if path_names:
            specs.append(ParamSpec("path", "Custom Path", "select",
                                   path_names[0], options=path_names,
                                   tooltip="gespeicherten Pfad auswählen"))
        return specs

    def get_param(self, key: str):
        if key == "speed":
            return self.speed_hz
        if key == "intensity":
            return self.intensity
        if key == "size":
            return max(self.width, self.height)
        if key == "algorithm":
            return self.algorithm.value
        if key == "path":
            p = self._resolve_path()
            return p.name if p is not None else None
        if key in ("width", "height", "x_offset", "y_offset", "rotation",
                   "spread", "head_spread", "direction", "loop", "mirror",
                   "open_beam", "relative", "bit16", "phase_mode",
                   "phase_offset_deg", "counter_rotate"):
            return getattr(self, key)
        if key == "tempo_bus_id":
            return getattr(self, "tempo_bus_id", "")
        if key == "tempo_multiplier":
            return getattr(self, "tempo_multiplier", 1.0)
        if key == "phase_offset":
            return getattr(self, "phase_offset", 0.0)
        return None

    def set_param(self, key: str, value) -> bool:
        if key == "speed":
            self.speed_hz = max(0.01, min(10.0, float(value))); return True
        if key == "intensity":
            self.intensity = max(0.0, min(1.0, float(value))); return True
        if key == "size":
            v = max(0.0, min(255.0, float(value)))
            self.width = v
            self.height = v
            return True
        if key in ("width", "height"):
            setattr(self, key, max(0.0, min(255.0, float(value)))); return True
        if key in ("x_offset", "y_offset"):
            setattr(self, key, max(0.0, min(255.0, float(value)))); return True
        if key == "rotation":
            self.rotation = float(value) % 360.0; return True
        if key == "spread":
            self.spread = max(0.0, min(1.0, float(value))); return True
        if key == "head_spread":
            self.head_spread = max(0.0, min(1.0, float(value))); return True
        if key == "phase_mode":
            s = str(value).lower()
            self.phase_mode = s if s in ("sync", "fan", "offset") else "fan"
            return True
        if key == "phase_offset_deg":
            self.phase_offset_deg = float(value) % 360.0; return True
        if key == "counter_rotate":
            self.counter_rotate = bool(value); return True
        if key == "direction":
            s = str(value).lower()
            if s.startswith(("back", "rück", "ruck", "rev")):
                self.direction = "backward"
            elif s.startswith("bounce"):
                self.direction = "bounce"
            else:
                self.direction = "forward"
            return True
        if key == "loop":
            self.loop = bool(value); return True
        if key == "mirror":
            self.mirror = bool(value); return True
        if key == "relative":
            self.relative = bool(value); return True
        if key == "open_beam":
            self.open_beam = bool(value); return True
        if key == "bit16":
            self.bit16 = bool(value); return True
        if key == "algorithm":
            try:
                self.algorithm = EfxAlgorithm(str(value))
                return True
            except ValueError:
                return False
        if key == "path":
            from .efx_path import get_efx_path_library
            lib = get_efx_path_library()
            p = lib.find(str(value)) or lib.find_by_name(str(value))
            if p is None:
                return False
            self.set_custom_path(p)
            return True
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
        return False

    def _cycle_path(self, step: int) -> bool:
        """Zum nächsten/vorherigen Pfad der Bibliothek wechseln."""
        from .efx_path import get_efx_path_library
        paths = get_efx_path_library().all()
        if not paths:
            return False
        ids = [p.id for p in paths]
        try:
            i = ids.index(self.path_id)
        except ValueError:
            i = -step  # noch kein Pfad: bei "next" beim ersten beginnen
        self.set_custom_path(paths[(i + step) % len(paths)])
        return True

    def do_action(self, action: str, **kw) -> bool:
        """Live-Aktionen für VC-Buttons/MIDI-Notes (analog RgbMatrixInstance)."""
        a = str(action)
        if a in ("restart", "reset", "retrigger"):
            self._phase = 1.0 if (not self.loop and self.direction == "backward") else 0.0
            self._bounce_dir = 1.0
            self._rand_progress = 0.0
            return True
        if a in ("reseed", "new_path", "newPath", "shuffle"):
            # „Neue Bahn": andere Zufalls-Sequenz fuer RANDOM.
            self.random_seed = random.randint(1, 2_000_000_000)
            self._rand_progress = 0.0
            return True
        if a in ("toggle_loop", "toggleLoop"):
            self.loop = not self.loop
            return True
        if a in ("reverse_direction", "reverseDirection"):
            self.direction = "forward" if self.direction == "backward" else "backward"
            return True
        if a in ("toggle_bounce", "toggleBounce"):
            self.direction = "forward" if self.direction == "bounce" else "bounce"
            return True
        if a in ("toggle_mirror", "toggleMirror"):
            self.mirror = not self.mirror
            return True
        if a in ("toggle_counter", "toggleCounter", "toggle_counter_rotate"):
            self.counter_rotate = not self.counter_rotate
            return True
        if a in ("toggle_relative", "toggleRelative", "toggle_additive"):
            self.relative = not self.relative
            return True
        if a in ("toggle_open_beam", "toggleOpenBeam"):
            self.open_beam = not self.open_beam
            return True
        if a in ("toggle_bit16", "toggle16bit", "toggle_16bit"):
            self.bit16 = not self.bit16
            return True
        if a in ("next_path", "nextPath"):
            return self._cycle_path(+1)
        if a in ("prev_path", "previous_path", "prevPath"):
            return self._cycle_path(-1)
        if a in ("next_algorithm", "nextAlgorithm", "next_form"):
            algos = list(EfxAlgorithm)
            self.algorithm = algos[(algos.index(self.algorithm) + 1) % len(algos)]
            return True
        if a in ("prev_algorithm", "prevAlgorithm", "previous_algorithm"):
            algos = list(EfxAlgorithm)
            self.algorithm = algos[(algos.index(self.algorithm) - 1) % len(algos)]
            return True
        if a in ("apply_selection", "applySelection", "assign_selection"):
            # Fixture-Liste aus der aktuellen Auswahl neu aufbauen
            # (nur Geräte mit Pan UND Tilt, Reihenfolge = Auswahlreihenfolge).
            try:
                from src.core.app_state import get_state, get_channels_for_patched
                state = get_state()
                fids = [int(f) for f in state.get_selected_fids()]
                patched = {f.fid: f for f in state.get_patched_fixtures()}
                movers = []
                for fid in fids:
                    fx = patched.get(fid)
                    if fx is None:
                        continue
                    attrs = {ch.attribute for ch in get_channels_for_patched(fx)}
                    if "pan" in attrs and "tilt" in attrs:
                        movers.append(fid)
                if not movers:
                    return False
                self.fixtures = [EfxFixture(fid=fid) for fid in movers]
                return True
            except Exception:
                return False
        if a in ("tap", "tap_tempo", "tapTempo"):
            try:
                from .bpm_manager import get_bpm_manager
                get_bpm_manager().tap()
                return True
            except Exception:
                return False
        return False

    def list_actions(self) -> list[tuple[str, str]]:
        """(key, label) der EFX-Live-Aktionen für die Bindungs-UI (VC/MIDI)."""
        return [
            ("restart",          "Neustart"),
            ("toggle_loop",      "Loop an/aus"),
            ("reverse_direction","Richtung"),
            ("toggle_bounce",    "Bounce"),
            ("next_path",        "Pfad +"),
            ("prev_path",        "Pfad −"),
            ("next_algorithm",   "Form +"),
            ("prev_algorithm",   "Form −"),
            ("toggle_mirror",    "Spiegeln"),
            ("toggle_counter",   "Gegenläufig"),
            ("toggle_relative",  "Relativ/additiv"),
            ("reseed",           "Neue Bahn (Random)"),
            ("toggle_open_beam", "Beam öffnen"),
            ("toggle_bit16",     "16-bit an/aus"),
            ("apply_selection",  "Auf Auswahl anwenden"),
            ("tap",              "Tap-Tempo"),
        ]

    def to_dict(self) -> dict:
        d = super().to_dict()  # id, name, type, intensity, speed, folder
        d.update({
            "motion": True,  # Diskriminator ggü. LayeredEffect/Carousel (gleicher Typ)
            "algorithm": self.algorithm.value,
            # Gruppen-Bindung (Programmer-Listen-Scope) — per Name, stabil ueber Save/Load.
            "source_group": self.source_group,
            "fixtures": [{"fid": f.fid, "offset": f.start_offset} for f in self.fixtures],
            "width": self.width, "height": self.height,
            "x_offset": self.x_offset, "y_offset": self.y_offset,
            "rotation": self.rotation,
            "x_freq": self.x_freq, "y_freq": self.y_freq,
            "x_phase": self.x_phase, "y_phase": self.y_phase,
            "speed_hz": self.speed_hz, "direction": self.direction,
            "open_beam": self.open_beam, "spread": self.spread,
            "head_spread": self.head_spread,
            "mirror": self.mirror,
            "phase_mode": self.phase_mode,
            "phase_offset_deg": self.phase_offset_deg,
            "counter_rotate": self.counter_rotate,
            "relative": self.relative,
            "bit16": self.bit16,
            "random_seed": self.random_seed,
            "loop": self.loop,
            "path_id": self.path_id,
            "path": self.path_data,
        })
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "EfxInstance":
        e = cls(name=d.get("name", "EFX"), fid=d.get("id"))
        e.algorithm = EfxAlgorithm(d.get("algorithm", "Circle"))
        # Gruppen-Bindung (Programmer-Listen-Scope). Fehlender Key (Alt-Shows) ODER
        # leerer String = ungebunden (None) -> erscheint in jeder Gruppe.
        _sg = d.get("source_group")
        e.source_group = str(_sg) if _sg else None
        e.fixtures = [
            EfxFixture(fid=f.get("fid") if isinstance(f, dict) else getattr(f, "fid", None),
                       start_offset=(f.get("offset", 0) if isinstance(f, dict) else getattr(f, "start_offset", 0)))
            for f in d.get("fixtures", [])
            if (isinstance(f, dict) and f.get("fid") is not None)
            or (not isinstance(f, dict) and getattr(f, "fid", None) is not None)
        ]
        for k in ("width","height","x_offset","y_offset","rotation",
                  "x_freq","y_freq","x_phase","y_phase","speed_hz","spread",
                  "head_spread"):
            if k in d:
                setattr(e, k, float(d[k]))
        e.direction = d.get("direction", "forward")
        e.open_beam = bool(d.get("open_beam", False))
        e.mirror = bool(d.get("mirror", False))
        pm = str(d.get("phase_mode", "fan")).lower()
        e.phase_mode = pm if pm in ("sync", "fan", "offset") else "fan"
        e.phase_offset_deg = float(d.get("phase_offset_deg", 0.0))
        e.counter_rotate = bool(d.get("counter_rotate", False))
        e.relative = bool(d.get("relative", False))
        e.bit16 = bool(d.get("bit16", True))
        if d.get("random_seed") is not None:
            e.random_seed = int(d["random_seed"])
        e.loop = bool(d.get("loop", True))
        e.path_id = d.get("path_id") or None
        pd = d.get("path")
        e.path_data = dict(pd) if isinstance(pd, dict) else None
        return e
