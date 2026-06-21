"""Sequence Function — Variante des Chasers gebunden an eine Fixture-Selektion.

Im Gegensatz zum Chaser (der andere Functions als Steps verkettet) operiert
eine Sequence direkt auf einer Liste von Fixtures: jeder Step ist ein Dict
{fid: {attribute: value}} mit Zeitparametern.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from .function import Function, FunctionType, RunOrder, Direction
from . import fade_curve as fc

if TYPE_CHECKING:
    from src.core.dmx.universe import Universe
    from src.core.database.models import PatchedFixture


@dataclass
class SequenceStep:
    # values: dict[fid_str, dict[attribute_str, int 0-255]]
    values: dict = field(default_factory=dict)
    fade_in: float = 0.5
    hold: float = 1.0
    fade_out: float = 0.0
    note: str = ""
    # Fade-Kurven formen Ein- und Ausblenden des Crossfades.
    fade_in_curve: fc.FadeCurve = field(default_factory=fc.linear)
    fade_out_curve: fc.FadeCurve = field(default_factory=fc.linear)

    def total_duration(self) -> float:
        return self.fade_in + self.hold + self.fade_out


class Sequence(Function):
    """
    QLC+ Sequence: Cue-Stack-aehnliche Liste fixierter Werte fuer eine
    festgelegte Fixture-Selektion. Schreibt Werte direkt in die Universen.
    """

    function_type = FunctionType.Sequence

    def __init__(self, name: str = "Neue Sequence", fid: int | None = None):
        super().__init__(name, fid)
        self.steps: list[SequenceStep] = []
        self.bound_fixtures: list[int] = []   # fids
        self.run_order: RunOrder = RunOrder.Loop
        self.direction: Direction = Direction.Forward
        self.speed: float = 1.0
        self._step_idx: int = 0
        self._step_elapsed: float = 0.0
        self._ping_pong_dir: int = 1
        self._prev_values: dict[int, dict[str, int]] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_start(self):
        if self.direction == Direction.Backward:
            self._step_idx = max(0, len(self.steps) - 1)
        else:
            self._step_idx = 0
        self._step_elapsed = 0.0
        self._ping_pong_dir = 1 if self.direction == Direction.Forward else -1
        self._prev_values = {}
        # WP-Tempo: bei Bus-Sync auf die aktuelle Bus-Position ankern + Step-Zaehler
        # zuruecksetzen, damit die Sequence gemeinsam mit der sync_group bei 0 startet.
        self._synced_target_prev = None
        bus_id = getattr(self, "tempo_bus_id", "") or ""
        if bus_id:
            try:
                from src.core.engine.tempo_bus import get_tempo_bus_manager
                bus = get_tempo_bus_manager().get(bus_id)
                if bus is not None:
                    self._beat_anchor = bus.take_anchor()
            except Exception:
                pass

    def _on_stop(self):
        self._step_idx = 0
        self._step_elapsed = 0.0

    # ── Builder ──────────────────────────────────────────────────────────────

    def add_step_from_programmer(self, programmer: dict, fade_in=0.5, hold=1.0, fade_out=0.0):
        """Erstellt einen Step aus aktuellem Programmer-Inhalt der bound_fixtures."""
        vals = {}
        for fid in self.bound_fixtures:
            if fid in programmer:
                # JSON-Key muss str sein bei Serialisierung
                vals[str(fid)] = dict(programmer[fid])
        self.steps.append(SequenceStep(
            values=vals, fade_in=fade_in, hold=hold, fade_out=fade_out))

    # ── write ─────────────────────────────────────────────────────────────────

    def _bus_steps_to_advance(self):
        """WP-Tempo: Anzahl Step-Advances fuer DIESEN Frame, wenn die Sequence auf
        einem LAUFENDEN Tempo-Bus liegt — 1 Step je ``beats_per_step`` Beats (Default 1),
        durch ``tempo_multiplier`` skaliert (×2/÷2). None = nicht bus-synchron -> der
        Aufrufer nutzt den Zeit-Pfad (>= Step-Dauer)."""
        bus_id = getattr(self, "tempo_bus_id", "") or ""
        if not bus_id:
            return None
        try:
            from src.core.engine.tempo_bus import get_tempo_bus_manager
            bus = get_tempo_bus_manager().get(bus_id)
        except Exception:
            bus = None
        if bus is None:
            return None
        bpm, _bc, _bp, pos = bus.snapshot()
        if bpm <= 0:
            return None  # Bus aus -> Zeit-Fallback
        mult = getattr(self, "tempo_multiplier", 1.0) or 1.0
        anchor = getattr(self, "_beat_anchor", 0.0)
        per = max(1e-9, float(getattr(self, "beats_per_step", 1) or 1))
        target = int(round(((pos - anchor) * mult) / per, 9))
        prev = getattr(self, "_synced_target_prev", None)
        if prev is None or target < prev:
            self._synced_target_prev = target  # (Re-)Sync ohne Sprung
            return 0
        n = target - prev
        self._synced_target_prev = target
        return min(n, max(1, len(self.steps)))

    def sync_phase(self):
        """WP-Tempo / Speed-Dial-Sync: bus-synchron -> auf die Bus-Position re-ankern
        (gemeinsam mit der sync_group); frei -> auf den Startschritt zuruecksetzen."""
        self._synced_target_prev = None
        bus_id = getattr(self, "tempo_bus_id", "") or ""
        if bus_id:
            try:
                from src.core.engine.tempo_bus import get_tempo_bus_manager
                bus = get_tempo_bus_manager().get(bus_id)
                if bus is not None:
                    self._beat_anchor = bus.take_anchor()
                    return
            except Exception:
                pass
        self._step_idx = max(0, len(self.steps) - 1) if self.direction == Direction.Backward else 0
        self._step_elapsed = 0.0

    def write(self, universes, patch_cache, dt, function_registry=None):
        if not self._running or not self.steps:
            return

        effective_dt = dt * self.speed
        step = self.steps[self._step_idx]
        total = step.total_duration()
        if total <= 0:
            total = 0.001

        # Compute mix factor 0..1 across fade_in/hold/fade_out (kurvengeformt)
        t = self._step_elapsed
        if t < step.fade_in:
            p = t / step.fade_in if step.fade_in > 0 else 1.0
            mix = step.fade_in_curve.eval(p)
        elif t < step.fade_in + step.hold:
            mix = 1.0
        elif step.fade_out > 0:
            # p läuft 0→1 über die Fade-Out-Zeit; eval = bereits Ausgeblendetes
            p = (t - step.fade_in - step.hold) / step.fade_out
            mix = 1.0 - step.fade_out_curve.eval(p)
        else:
            mix = 0.0
        mix = max(0.0, min(1.0, mix))

        # Apply values
        from src.core.app_state import get_channels_for_patched
        # Build fid -> PF lookup
        pf_by_fid = {f.fid: f for f in patch_cache}
        for fid_str, attrs in step.values.items():
            try:
                fid = int(fid_str)
            except ValueError:
                continue
            pf = pf_by_fid.get(fid)
            if pf is None or pf.universe not in universes:
                continue
            channels = get_channels_for_patched(pf)
            for ch in channels:
                if ch.attribute in attrs:
                    target = attrs[ch.attribute]
                    prev = self._prev_values.get(fid, {}).get(ch.attribute, 0)
                    val = int(prev + (target - prev) * mix)
                    dmx_addr = pf.address + ch.channel_number - 1
                    if 1 <= dmx_addr <= 512:
                        universes[pf.universe].set_channel(dmx_addr, val)

        self._step_elapsed += effective_dt
        self._elapsed += effective_dt

        # WP-Tempo: Step-Advance bus-getrieben (falls gesetzt + Bus laeuft), sonst
        # zeitbasiert wie bisher (>= Step-Dauer). Der Crossfade-Mix oben bleibt von
        # _step_elapsed/fade_in getrieben — nur der Advance-AUSLOESER aendert sich.
        n_adv = self._bus_steps_to_advance()
        advance_now = n_adv if n_adv is not None else (1 if self._step_elapsed >= total else 0)
        for _ in range(advance_now):
            # aktuellen Step als prev fuer den naechsten Crossfade merken
            self._prev_values = {}
            for fid_str, attrs in self.steps[self._step_idx].values.items():
                try:
                    fid = int(fid_str)
                except ValueError:
                    continue
                self._prev_values[fid] = dict(attrs)
            self._step_elapsed = 0.0
            if not self._advance_step():
                self._running = False
                break

    def _advance_step(self) -> bool:
        if not self.steps:
            return False
        n = len(self.steps)

        if self.run_order == RunOrder.SingleShot:
            next_idx = self._step_idx + (1 if self.direction == Direction.Forward else -1)
            if next_idx < 0 or next_idx >= n:
                return False
            self._step_idx = next_idx
            return True

        elif self.run_order == RunOrder.Loop:
            if self.direction == Direction.Forward:
                self._step_idx = (self._step_idx + 1) % n
            else:
                self._step_idx = (self._step_idx - 1) % n
            return True

        elif self.run_order == RunOrder.PingPong:
            next_idx = self._step_idx + self._ping_pong_dir
            if next_idx >= n:
                self._ping_pong_dir = -1
                next_idx = max(0, n - 2)
            elif next_idx < 0:
                self._ping_pong_dir = 1
                next_idx = min(n - 1, 1)
            self._step_idx = next_idx
            return True

        return True

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "bound_fixtures": list(self.bound_fixtures),
            "run_order": self.run_order.value,
            "direction": self.direction.value,
            "speed": self.speed,
            "steps": [self._step_to_dict(s) for s in self.steps],
        })
        return d

    @staticmethod
    def _step_to_dict(s: "SequenceStep") -> dict:
        d = {
            "values": s.values,
            "fade_in": s.fade_in,
            "hold": s.hold,
            "fade_out": s.fade_out,
            "note": s.note,
        }
        if not s.fade_in_curve.is_linear_default():
            d["fade_in_curve"] = s.fade_in_curve.to_dict()
        if not s.fade_out_curve.is_linear_default():
            d["fade_out_curve"] = s.fade_out_curve.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Sequence":
        sq = cls(name=d.get("name", "Sequence"), fid=d.get("id"))
        sq.bound_fixtures = [int(x) for x in d.get("bound_fixtures", [])]
        sq.run_order = RunOrder(d.get("run_order", "Loop"))
        sq.direction = Direction(d.get("direction", "Forward"))
        sq.speed = float(d.get("speed", 1.0))
        for sd in d.get("steps", []):
            step = SequenceStep(
                values=sd.get("values", {}),
                fade_in=sd.get("fade_in", 0.5),
                hold=sd.get("hold", 1.0),
                fade_out=sd.get("fade_out", 0.0),
                note=sd.get("note", ""),
            )
            if "fade_in_curve" in sd:
                step.fade_in_curve = fc.FadeCurve.from_dict(sd["fade_in_curve"])
            if "fade_out_curve" in sd:
                step.fade_out_curve = fc.FadeCurve.from_dict(sd["fade_out_curve"])
            sq.steps.append(step)
        return sq
