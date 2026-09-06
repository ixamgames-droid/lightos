"""Scene function — stores fixture channel values and fades them in."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from .function import Function, FunctionType
from . import fade_curve as fc

if TYPE_CHECKING:
    from src.core.dmx.universe import Universe
    from src.core.database.models import PatchedFixture


@dataclass
class SceneValue:
    fixture_id: int
    channel: int        # 1-based channel offset within fixture
    value: int          # 0-255


class Scene(Function):
    """
    QLC+ Scene: a snapshot of fixture channel values that fades in
    over self.fade_in seconds using linear interpolation.
    """

    function_type = FunctionType.Scene

    def __init__(self, name: str = "Neue Szene", fid: int | None = None):
        super().__init__(name, fid)
        self.fade_in: float = 0.0    # seconds
        self.fade_out: float = 0.0
        self.hold: float = 0.0       # 0 = infinite
        self.fade_in_curve: fc.FadeCurve = fc.linear()  # Form des Einblendens
        self._values: list[SceneValue] = []
        self._start_vals: dict[tuple[int, int], int] = {}   # (fid, ch) -> start dmx value
        self._done: bool = False

    # ── Value management ──────────────────────────────────────────────────────

    def set_value(self, fixture_id: int, channel: int, value: int):
        value = max(0, min(255, int(value)))
        for sv in self._values:
            if sv.fixture_id == fixture_id and sv.channel == channel:
                sv.value = value
                return
        self._values.append(SceneValue(fixture_id, channel, value))

    def get_value(self, fixture_id: int, channel: int) -> int | None:
        for sv in self._values:
            if sv.fixture_id == fixture_id and sv.channel == channel:
                return sv.value
        return None

    def remove_value(self, fixture_id: int, channel: int):
        self._values = [sv for sv in self._values
                        if not (sv.fixture_id == fixture_id and sv.channel == channel)]

    def clear(self):
        self._values.clear()

    @property
    def values(self) -> list[SceneValue]:
        return list(self._values)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_start(self):
        self._done = False
        # ENG-20: je Lauf EINMAL melden, nicht je Frame. ``write`` laeuft mit
        # der Bildrate; ein Hinweis pro Frame waere in Sekunden unlesbar und
        # wuerde die echte Meldung im Rauschen begraben.
        self._verworfen_gemeldet = set()
        # snapshot cleared — start values are captured on first write call

    def _on_stop(self):
        self._start_vals.clear()
        self._done = False

    # ── write ─────────────────────────────────────────────────────────────────

    def write(self, universes: dict[int, "Universe"],
              patch_cache: list["PatchedFixture"],
              dt: float,
              function_registry=None):
        if not self._running:
            return

        # Snapshot current DMX values on first frame
        if self._elapsed == 0.0:
            self._start_vals = {}
            for sv in self._values:
                fixture = _find_fixture(patch_cache, sv.fixture_id)
                if fixture is None:
                    continue
                universe = universes.get(fixture.universe)
                if universe is None:
                    continue
                dmx_addr = fixture.address + sv.channel - 1
                if 1 <= dmx_addr <= 512:
                    self._start_vals[(sv.fixture_id, sv.channel)] = universe.get_channel(dmx_addr)

        self._elapsed += dt

        # Compute fade progress (durch die Fade-Kurve geformt)
        if self.fade_in > 0.0:
            t = self.fade_in_curve.eval(min(1.0, self._elapsed / self.fade_in))
        else:
            t = 1.0

        # Ausblend-Phase: laeuft nach Ablauf von hold ueber fade_out Sekunden.
        # out_factor rampt von 1.0 -> 0.0 (mit derselben Kurvenform wie fade_in,
        # auf die umgekehrte Progression angewandt) und wird auf den fertig
        # eingeblendeten Szenenwert multipliziert. Erst NACH Ablauf von fade_out
        # wird die Szene gestoppt; fade_out<=0 verhaelt sich wie bisher (sofort).
        out_factor = 1.0
        fade_out_done = False
        if t >= 1.0 and self.hold > 0.0:
            hold_elapsed = self._elapsed - self.fade_in
            if hold_elapsed >= self.hold:
                if self.fade_out > 0.0:
                    out_elapsed = hold_elapsed - self.hold
                    prog = min(1.0, out_elapsed / self.fade_out)
                    # gleiche Kurvenform, auf den verbleibenden Anteil angewandt
                    out_factor = self.fade_in_curve.eval(1.0 - prog)
                    fade_out_done = out_elapsed >= self.fade_out
                else:
                    fade_out_done = True

        # Write interpolated values to DMX
        for sv in self._values:
            fixture = _find_fixture(patch_cache, sv.fixture_id)
            if fixture is None:
                continue
            universe = universes.get(fixture.universe)
            if universe is None:
                continue
            grund = self._warum_nicht_schreibbar(fixture, sv)
            if grund:
                self._melde_einmal(fixture, sv, grund)
                continue
            dmx_addr = fixture.address + sv.channel - 1
            if not (1 <= dmx_addr <= 512):
                continue
            start = self._start_vals.get((sv.fixture_id, sv.channel), 0)
            current = int((start + (sv.value - start) * t) * out_factor)
            universe.set_channel(dmx_addr, max(0, min(255, current)))

        # Handle hold + auto-stop (erst NACH abgeschlossener Ausblend-Phase)
        if fade_out_done:
            self._running = False
            self._done = True

    # ── ENG-20: nicht in fremde Geraete schreiben ────────────────────────────

    def _warum_nicht_schreibbar(self, fixture, sv) -> str:
        """Warum dieser gespeicherte Wert NICHT ausgegeben werden darf — sonst "".

        ★ Der Unterschied zu allen anderen Stellen, die ``fx.address +
        channel - 1`` rechnen: dort kommt die Kanalnummer aus der LEBENDEN
        Kanalliste des Geraets und kann per Konstruktion nicht ueberlaufen.
        Hier kommt sie aus der GESPEICHERTEN Szene und beschreibt einen
        Zustand, den es womoeglich nicht mehr gibt.

        Zwei Gruende, beide gemessen:

        * **Kanalzahl** (ENG-20): ein Geraet auf Adresse 7 mit heute 6 Kanaelen
          und gespeichertem Kanal 10 schreibt auf Adresse 16 — in den Nachbarn.
          Gemessen an Hydra@7 (6 Kanaele) neben PAR@13: die 200 landete auf 16.
        * **Netzwerk-Laser**: deren ``address`` ist ein bedeutungsloser
          Platzhalter (``fixture_uses_dmx``). Der Kommentar dort verlangt
          ausdruecklich, dass JEDE Stelle mit dieser Rechnung vorher fragt —
          ``scene.py`` tat es nicht. Gemessen: ein Laser@1 schrieb seinen
          „Kanal 3" auf Adresse 3, also in einen echten PAR.

        ⚠️ Fehlt die Kanalzahl (Alt-Objekte, Mocks), wird NICHT verworfen. Die
        sichere Richtung ist hier „schreiben wie bisher": eine Szene, die
        stumm nichts mehr tut, ist auf der Buehne schlimmer als eine, die zu
        viel tut — dieselbe Abwaegung, die Robin bei FM-45/2 getroffen hat.
        """
        try:
            from src.core.app_state import fixture_uses_dmx
            if not fixture_uses_dmx(fixture):
                return ("das Geraet gibt nicht ueber DMX aus (Netzwerk-Laser), "
                        "seine Adresse ist ein Platzhalter")
        except Exception:
            pass                        # im Zweifel schreiben, s. Docstring
        anzahl = getattr(fixture, "channel_count", None)
        try:
            anzahl = int(anzahl) if anzahl is not None else None
        except (TypeError, ValueError):
            anzahl = None
        if anzahl is not None and not (1 <= sv.channel <= anzahl):
            return (f"Kanal {sv.channel} gibt es dort nicht mehr — das Geraet "
                    f"hat heute {anzahl}")
        return ""

    def _melde_einmal(self, fixture, sv, grund: str):
        """Einmal je Lauf und je (Geraet, Kanal) — nicht je Frame."""
        gemeldet = getattr(self, "_verworfen_gemeldet", None)
        if gemeldet is None:
            gemeldet = self._verworfen_gemeldet = set()
        schluessel = (sv.fixture_id, sv.channel)
        if schluessel in gemeldet:
            return
        gemeldet.add(schluessel)
        print(f"[Scene] {self.name!r}: Wert fuer Geraet {sv.fixture_id} "
              f"verworfen — {grund}. Szene neu speichern, dann ist der Rest "
              f"wieder sauber (ENG-20).")

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "fade_in": self.fade_in,
            "fade_out": self.fade_out,
            "hold": self.hold,
            "values": [
                {"fid": sv.fixture_id, "ch": sv.channel, "val": sv.value}
                for sv in self._values
            ],
        })
        # Kurve nur speichern, wenn sie von der Standard-Geraden abweicht.
        if not self.fade_in_curve.is_linear_default():
            d["fade_in_curve"] = self.fade_in_curve.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Scene":
        s = cls(name=d.get("name", "Szene"), fid=d.get("id"))
        s.fade_in = d.get("fade_in", 0.0)
        s.fade_out = d.get("fade_out", 0.0)
        s.hold = d.get("hold", 0.0)
        if "fade_in_curve" in d:
            s.fade_in_curve = fc.FadeCurve.from_dict(d["fade_in_curve"])
        for v in d.get("values", []):
            s.set_value(v["fid"], v["ch"], v["val"])
        return s


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_fixture(patch_cache: list["PatchedFixture"], fid: int):
    for f in patch_cache:
        if f.fid == fid:
            return f
    return None
