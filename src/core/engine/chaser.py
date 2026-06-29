"""Chaser function — steps through a list of functions in sequence."""
from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from .function import Function, FunctionType, RunOrder, Direction
from . import fade_curve as fc

if TYPE_CHECKING:
    from src.core.dmx.universe import Universe
    from src.core.database.models import PatchedFixture


@dataclass
class ChaserStep:
    function_id: int
    fade_in: float = 0.0    # seconds (overrides child function fade_in)
    hold: float = 1.0       # seconds (how long step stays at full)
    fade_out: float = 0.0   # seconds
    note: str = ""
    # Fade-Kurven formen den Verlauf (wirken auf Scene-Children beim Einblenden).
    fade_in_curve: fc.FadeCurve = field(default_factory=fc.linear)
    fade_out_curve: fc.FadeCurve = field(default_factory=fc.linear)

    def total_duration(self) -> float:
        return self.fade_in + self.hold + self.fade_out


class Chaser(Function):
    """
    QLC+ Chaser: steps through ChaserStep objects, each pointing to another
    Function. Supports Loop, SingleShot, PingPong and Random run orders.
    """

    function_type = FunctionType.Chaser
    tempo_sync_default = True

    def __init__(self, name: str = "Neuer Chaser", fid: int | None = None):
        super().__init__(name, fid)
        self.steps: list[ChaserStep] = []
        self.run_order: RunOrder = RunOrder.Loop
        self.direction: Direction = Direction.Forward
        self.speed: float = 1.0         # multiplier (1.0 = normal)
        self.audio_triggered: bool = False  # if True: BPMManager beat advances steps
        self.beats_per_step: int = 1    # bei audio_triggered: alle N Beats weiter
        self._step_idx: int = 0
        self._step_elapsed: float = 0.0
        self._ping_pong_dir: int = 1    # +1 forward, -1 backward
        self._visited: set[int] = set()  # for random
        self._pending_advance: bool = False  # set by trigger_next_step()
        self._beat_counter: int = 0     # zaehlt Beats fuer beats_per_step
        # Crossfade-Status (EE-01): der Chaser blendet selbst zwischen den
        # Schritten, weil der Per-Frame-Clear im Renderer ein Snapshotten des
        # Vorgaengerwerts in der Scene unmoeglich macht. _from_values = der zuletzt
        # ausgegebene Frame (Ausgangspunkt der Blende), _cur_output = aktueller Frame.
        self._from_values: dict[tuple[int, int], int] = {}
        self._cur_output: dict[tuple[int, int], int] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_start(self):
        if self.direction == Direction.Backward:
            self._step_idx = len(self.steps) - 1
        else:
            self._step_idx = 0
        self._step_elapsed = 0.0
        self._ping_pong_dir = 1 if self.direction == Direction.Forward else -1
        self._visited = set()
        self._beat_counter = 0
        self._from_values = {}
        self._cur_output = {}
        # Beat-getriggerte Chaser brauchen einen laufenden BPM-Takt — sonst
        # stehen sie still. Default 120 BPM starten, falls noch keine BPM gesetzt.
        if self.audio_triggered:
            try:
                from .bpm_manager import get_bpm_manager
                bm = get_bpm_manager()
                if bm.bpm <= 0:
                    bm.set_bpm(120.0)
            except Exception:
                pass
        # WP-Tempo: Step-Zaehler zuruecksetzen + ankern. „Taktgleich" (align_on_start,
        # Default) klinkt auf das gemeinsame Beat-Raster des Bus ein (note_groove_start
        # legt bei frischer Groove den Downbeat auf jetzt -> sauberer Start auf der Eins);
        # bewusst frei (False) ankert auf die eigene aktuelle Bus-Position. bus_for_effect
        # erzeugt feste Buses A-D bei Bedarf, damit eine A-D-Bindung sofort greift.
        self._synced_target_prev = None
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

    def _on_stop(self):
        self._step_idx = 0
        self._step_elapsed = 0.0

    # ── write ─────────────────────────────────────────────────────────────────

    def trigger_next_step(self):
        """Wird von einem externen Beat-Event aufgerufen (z. B. BPMManager).
        Zaehlt Beats und setzt _pending_advance erst nach beats_per_step Beats."""
        per = max(1, int(self.beats_per_step or 1))
        self._beat_counter += 1
        if self._beat_counter >= per:
            self._beat_counter = 0
            self._pending_advance = True

    def _advance_from_bus(self, universes, patch_cache, function_registry,
                          effective_dt: float) -> bool:
        """WP-Tempo: Liegt der Chaser auf einem LAUFENDEN Tempo-Bus, treibt die
        Bus-Position das Stepping — 1 Step je ``beats_per_step`` Beats, durch
        ``tempo_multiplier`` skaliert (×2 = doppelt so schnell, ÷2 = halb). So laufen
        mehrere Chaser/Effekte auf demselben Bus phasenkohaerent. Liefert True, wenn so
        behandelt; sonst False -> der normale Audio-/Zeit-Pfad in write() laeuft weiter."""
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
            # F5: nur bei AKTIVEM Freeze den aktuellen Schritt HALTEN (weiter ausgeben,
            # NICHT weiterschalten); sonst Free-Run/Audio-Fallback wie bisher.
            if _tbm is not None and _tbm.is_frozen():
                self._render_and_blend(universes, patch_cache, function_registry)
                return True
            return False
        mult = getattr(self, "tempo_multiplier", 1.0) or 1.0
        anchor = getattr(self, "_beat_anchor", 0.0)
        per = max(1e-9, float(self.beats_per_step or 1))
        target = int(round(((pos - anchor) * mult) / per, 9))
        prev = getattr(self, "_synced_target_prev", None)
        if prev is None or target < prev:
            self._synced_target_prev = target  # (Re-)Sync ohne Sprung
        elif target > prev:
            steps = min(target - prev, max(1, len(self.steps)))
            self._synced_target_prev = target
            for _ in range(steps):
                self._from_values = dict(self._cur_output)
                self._step_elapsed = 0.0
                if not self._advance_step():
                    self._running = False
                    return True
        self._render_and_blend(universes, patch_cache, function_registry)
        self._step_elapsed += effective_dt
        self._elapsed += effective_dt
        return True

    def sync_phase(self):
        """WP-Tempo / Speed-Dial-Sync: bus-synchron -> auf die aktuelle Bus-Position
        re-ankern (Step-Zaehler neu, gemeinsam mit der sync_group); frei -> auf den
        Startschritt zuruecksetzen."""
        self._synced_target_prev = None
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
        self._step_idx = (len(self.steps) - 1) if self.direction == Direction.Backward else 0
        self._step_elapsed = 0.0

    def write(self, universes: dict[int, "Universe"],
              patch_cache: list["PatchedFixture"],
              dt: float,
              function_registry: dict[int, Function] | None = None):
        if not self._running or not self.steps:
            return
        # Re-Entrancy-Schutz: Referenziert ein Schritt (direkt oder zyklisch über
        # weitere Chaser) diesen Chaser selbst, würde _render_child_target ->
        # child.write() endlos rekursiv aufrufen (Absturz). Ist dieser Chaser
        # bereits weiter oben im aktuellen Render-Stack aktiv, brechen wir hier
        # ab. Das Flag wird nach jedem verschachtelten write() zurückgesetzt,
        # legitime (azyklische) Verschachtelung bleibt also erlaubt.
        if getattr(self, "_rendering", False):
            return
        self._rendering = True
        try:
            effective_dt = dt * self.speed

            # WP-Tempo: Tempo-Bus treibt das Stepping (×2/÷2, phasenkohaerent), falls
            # gesetzt + Bus laeuft. Sonst faellt es auf Audio/Zeit zurueck.
            if self._advance_from_bus(universes, patch_cache, function_registry, effective_dt):
                return

            if self.audio_triggered:
                # Step-Advance ist nur per Beat-Trigger
                if self._pending_advance:
                    self._pending_advance = False
                    self._from_values = dict(self._cur_output)
                    advanced = self._advance_step()
                    if not advanced:
                        self._running = False
                        return
                    self._step_elapsed = 0.0
                self._render_and_blend(universes, patch_cache, function_registry)
                self._step_elapsed += effective_dt
                self._elapsed += effective_dt
                return

            # Zeitbasiert: aktuellen Schritt rendern + ueber fade_in einblenden.
            self._render_and_blend(universes, patch_cache, function_registry)
            self._step_elapsed += effective_dt
            self._elapsed += effective_dt

            step = self.steps[self._step_idx]
            total = step.total_duration()
            if total <= 0:
                total = 0.001
            # Advance step when duration elapses
            if self._step_elapsed >= total:
                self._from_values = dict(self._cur_output)
                self._step_elapsed = 0.0
                advanced = self._advance_step()
                if not advanced:
                    self._running = False
        finally:
            self._rendering = False

    # ── Crossfade-Rendering (EE-01) ────────────────────────────────────────────

    def _render_and_blend(self, universes: dict[int, "Universe"],
                          patch_cache: list["PatchedFixture"],
                          function_registry: dict[int, Function] | None):
        """Rendert den aktuellen Schritt und blendet ihn vom zuletzt
        ausgegebenen Frame (_from_values) ueber step.fade_in weich ein.
        Schreibt den Mischwert direkt in die Scratch-Universen und merkt sich
        das Ergebnis als _cur_output fuer die naechste Blende."""
        if not function_registry or not self.steps:
            return
        step = self.steps[self._step_idx]
        child = function_registry.get(step.function_id)
        target = self._render_child_target(
            child, universes, patch_cache, function_registry)

        # Blend-Fortschritt entlang fade_in (durch die Kurve geformt).
        fade_in = max(0.0, float(getattr(step, "fade_in", 0.0)))
        if fade_in <= 0.0:
            t = 1.0
        else:
            frac = min(1.0, self._step_elapsed / fade_in)
            curve = getattr(step, "fade_in_curve", None)
            t = curve.eval(frac) if curve is not None else frac

        out: dict[tuple[int, int], int] = {}
        keys = set(target) | set(self._from_values)
        for key in keys:
            src = self._from_values.get(key, 0)
            dst = target.get(key, 0)
            val = int(round(src + (dst - src) * t))
            val = 0 if val < 0 else (255 if val > 255 else val)
            out[key] = val
            u, addr = key
            uni = universes.get(u)
            if uni is not None and 1 <= addr <= 512:
                uni.set_channel(addr, val)
        self._cur_output = out

    @staticmethod
    def _render_child_target(child, universes, patch_cache, function_registry
                             ) -> dict[tuple[int, int], int]:
        """Liefert die Zielwerte {(univ, addr): value} des Schritt-Childs ohne
        dessen eigene Blende. Trick: das Child wird in zwei Scratch-Kopien mit
        unterschiedlichem Hintergrund (0x00 / 0xFF) gerendert — Kanaele, die in
        beiden gleich sind, hat das Child absolut gesetzt; abweichende Kanaele
        hat es unberuehrt gelassen. So lassen sich auch bewusst auf 0 gesetzte
        Kanaele von nicht beschriebenen unterscheiden."""
        from src.core.dmx.universe import Universe
        if child is None:
            return {}

        def _render(bg: int) -> dict[int, bytes]:
            temp = {}
            for u in universes:
                tu = Universe(u)
                if bg:
                    tu.set_range(1, bytes([bg]) * Universe.SIZE)
                temp[u] = tu
            saved_running = child._running
            saved_elapsed = child._elapsed
            saved_fade_in = getattr(child, "fade_in", None)
            try:
                child._running = True
                if saved_fade_in is not None:
                    child.fade_in = 0.0  # Chaser besitzt die Blende
                child.write(temp, patch_cache, 0.0, function_registry)
            except Exception:
                pass
            finally:
                child._running = saved_running
                child._elapsed = saved_elapsed
                if saved_fade_in is not None:
                    child.fade_in = saved_fade_in
            return {u: tu.get_all() for u, tu in temp.items()}

        a = _render(0x00)
        b = _render(0xFF)
        target: dict[tuple[int, int], int] = {}
        for u, av in a.items():
            bv = b.get(u, av)
            for i in range(512):
                if av[i] == bv[i]:  # vom Child absolut gesetzt
                    target[(u, i + 1)] = av[i]
        return target

    def _advance_step(self) -> bool:
        """Move to next step. Returns False if sequence is finished."""
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

        elif self.run_order == RunOrder.Random:
            available = [i for i in range(n) if i not in self._visited]
            if not available:
                self._visited = set()
                available = list(range(n))
            self._step_idx = random.choice(available)
            self._visited.add(self._step_idx)
            return True

        return True

    # ── Live-Build-API (APC-Probier To-Do #2) ────────────────────────────────
    # Ein echter Szenen-Chaser laesst sich damit LIVE zusammenstecken: per
    # VC-Button/MIDI den aktuellen Programmer als Schritt aufnehmen, einen
    # bestehenden Look anhaengen, den letzten/alle Schritte verwerfen. Die VC
    # erreicht alles ueber do_action (effect_live-Dispatcher).

    def add_step(self, function_id: int, fade_in: float = 0.0, hold: float = 1.0,
                 fade_out: float = 0.0, note: str = "") -> int:
        """Haengt einen Schritt an, der auf eine bestehende Funktion zeigt."""
        self.steps.append(ChaserStep(function_id=int(function_id),
                                      fade_in=float(fade_in), hold=float(hold),
                                      fade_out=float(fade_out), note=note))
        return len(self.steps) - 1

    def capture_step(self, hold: float = 1.0, fade_in: float = 0.0,
                     fade_out: float = 0.0, name: str | None = None) -> int | None:
        """Erfasst den AKTUELLEN Programmer-Zustand als neue Scene-Funktion und
        haengt sie als Schritt an. Gibt den Step-Index zurueck oder None, wenn
        der Programmer leer ist bzw. kein State verfuegbar (Live-Step-Capture)."""
        try:
            from src.core.app_state import (
                get_state, get_channels_for_patched, resolve_attr_channels)
            from .function_manager import get_function_manager
        except Exception:
            return None
        state = get_state()
        prog = {fid: dict(attrs) for fid, attrs in state.programmer.items()}
        if not prog:
            return None
        fm = get_function_manager()
        scene = fm.new_scene(name or f"{self.name} · Schritt {len(self.steps) + 1}")
        # Aufgenommene Schritt-Szenen unter dem Chaser-Namen gruppieren.
        scene.folder = getattr(self, "folder", "") or f"{self.name} (Schritte)"
        patched = {f.fid: f for f in state.get_patched_fixtures()}
        for fid, attrs in prog.items():
            fx = patched.get(fid)
            if fx is None:
                continue
            # Mehrkopf (X-6): vorkommens-bewusst aufloesen statt eines
            # ``{attribute: channel}``-Dicts, das bei wiederholten Attributen
            # (zwei ``color_r`` beim Spider) kollidiert — sonst landet der
            # Kopf-0-Wert auf dem ZWEITEN Kanal und ``color_r#1`` verfaellt.
            for ch_no, _mkey, val in resolve_attr_channels(get_channels_for_patched(fx), attrs):
                scene.set_value(fid, ch_no, int(val))
        return self.add_step(scene.id, fade_in=fade_in, hold=hold,
                             fade_out=fade_out, note="captured")

    def list_params(self) -> list:
        """Live steuerbare Parameter (analog EFX/Matrix) — macht den Chaser auf
        VC-Fader/Encoder mappbar."""
        from .rgb_matrix_meta import ParamSpec  # lazy: Import-Zyklus vermeiden
        return [
            ParamSpec("speed", "Tempo", "float", 1.0, 0.05, 8.0, 0.05,
                      "Geschwindigkeits-Faktor"),
            ParamSpec("step_duration", "Schritt-Dauer (s)", "float", 1.0, 0.05, 60.0, 0.05,
                      "Gesamtdauer pro Chaser-Schritt; passt Hold/Fades aller Schritte an"),
            ParamSpec("step_hold", "Schritt halten (s)", "float", 1.0, 0.0, 60.0, 0.05,
                      "Haltezeit aller Chaser-Schritte"),
            ParamSpec("step_fade", "Schritt-Fade ein+aus (s)", "float", 0.0, 0.0, 10.0, 0.05,
                      "Setzt Fade-In und Fade-Out aller Chaser-Schritte gemeinsam"),
            ParamSpec("step_fade_in", "Schritt Fade-In (s)", "float", 0.0, 0.0, 10.0, 0.05,
                      "Einblendzeit aller Chaser-Schritte"),
            ParamSpec("step_fade_out", "Schritt Fade-Out (s)", "float", 0.0, 0.0, 10.0, 0.05,
                      "Ausblendzeit aller Chaser-Schritte"),
            ParamSpec("direction", "Richtung", "select", Direction.Forward.value,
                      options=tuple(d.value for d in Direction)),
            ParamSpec("run_order", "Modus", "select", RunOrder.Loop.value,
                      options=tuple(r.value for r in RunOrder)),
            # WP-Tempo: Anbindung an einen Tempo-Bus (A/B/C/D) — leer = frei.
            ParamSpec("tempo_bus_id", "Tempo-Bus", "select", "Global",
                      options=("Global", "", "A", "B", "C", "D"),
                      tooltip="Auf welchen Tempo-Bus synchronisieren (leer = frei, "
                              "Global = Master-BPM, A–D = eigene Buses)"),
            ParamSpec("tempo_multiplier", "Tempo ×", "float", 1.0, 0.0625, 16.0, 0.25,
                      "Verhältnis zum Bus (frei, z. B. 0.5 halb, 2 doppelt, 3 dreifach)"),
            ParamSpec("phase_offset", "Tempo-Versatz (Beats)", "float", 0.0, 0.0, 1.0, 0.05,
                      "Phasen-Versatz in Beats (versetzter Start auf dem Bus)"),
        ]

    def _avg_step_attr(self, attr: str, default: float = 0.0) -> float:
        if not self.steps:
            return default
        vals = [float(getattr(s, attr, default)) for s in self.steps]
        return sum(vals) / len(vals)

    def _avg_step_duration(self) -> float:
        if not self.steps:
            return 0.0
        return sum(float(s.total_duration()) for s in self.steps) / len(self.steps)

    def _set_all_step_attr(self, attr: str, value: float, lo: float, hi: float) -> bool:
        if not self.steps:
            return False
        v = max(lo, min(hi, float(value)))
        for step in self.steps:
            setattr(step, attr, v)
        return True

    def _set_all_step_duration(self, value: float) -> bool:
        if not self.steps:
            return False
        total = max(0.05, min(60.0, float(value)))
        for step in self.steps:
            fade_in = max(0.0, float(getattr(step, "fade_in", 0.0)))
            fade_out = max(0.0, float(getattr(step, "fade_out", 0.0)))
            fade_sum = fade_in + fade_out
            if fade_sum <= total:
                step.hold = total - fade_sum
                continue
            if fade_sum > 0.0:
                scale = total / fade_sum
                step.fade_in = fade_in * scale
                step.fade_out = fade_out * scale
            step.hold = 0.0
        return True

    def get_param(self, key: str):
        if key == "speed":
            return self.speed
        if key == "step_duration":
            return self._avg_step_duration()
        if key == "step_hold":
            return self._avg_step_attr("hold", 1.0)
        if key == "step_fade":
            return max(self._avg_step_attr("fade_in", 0.0),
                       self._avg_step_attr("fade_out", 0.0))
        if key == "step_fade_in":
            return self._avg_step_attr("fade_in", 0.0)
        if key == "step_fade_out":
            return self._avg_step_attr("fade_out", 0.0)
        if key == "direction":
            return self.direction.value
        if key == "run_order":
            return self.run_order.value
        if key == "tempo_bus_id":
            return getattr(self, "tempo_bus_id", "")
        if key == "tempo_multiplier":
            return getattr(self, "tempo_multiplier", 1.0)
        if key == "phase_offset":
            return getattr(self, "phase_offset", 0.0)
        return None

    def set_param(self, key: str, value) -> bool:
        if key == "speed":
            self.speed = max(0.05, min(8.0, float(value)))
            return True
        if key == "step_duration":
            return self._set_all_step_duration(value)
        if key == "step_hold":
            return self._set_all_step_attr("hold", value, 0.0, 60.0)
        if key == "step_fade":
            ok_in = self._set_all_step_attr("fade_in", value, 0.0, 10.0)
            ok_out = self._set_all_step_attr("fade_out", value, 0.0, 10.0)
            return ok_in or ok_out
        if key == "step_fade_in":
            return self._set_all_step_attr("fade_in", value, 0.0, 10.0)
        if key == "step_fade_out":
            return self._set_all_step_attr("fade_out", value, 0.0, 10.0)
        if key == "direction":
            try:
                self.direction = Direction(str(value))
            except ValueError:
                s = str(value).lower()
                self.direction = (Direction.Backward
                                  if s.startswith(("back", "rück", "ruck", "rev"))
                                  else Direction.Forward)
            return True
        if key == "run_order":
            try:
                self.run_order = RunOrder(str(value))
                return True
            except ValueError:
                return False
        if key == "tempo_bus_id":
            self.tempo_bus_id = str(value or "").strip()
            # Exklusiv: ein bus-gebundener Chaser steppt ueber den Tempo-Bus; der alte
            # audio_triggered-Pfad (BPMManager-Beat) wuerde sonst parallel mitzaehlen.
            # Der Bus gewinnt -> audio_triggered abschalten.
            if self.tempo_bus_id:
                self.audio_triggered = False
            return True
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

    def do_action(self, action: str, **kw) -> bool:
        """Live-Aktionen fuer VC-Buttons/MIDI-Notes (analog Matrix/EFX)."""
        a = str(action)
        if a in ("capture_step", "captureStep", "add_current", "grab_step"):
            return self.capture_step(hold=float(kw.get("hold", 1.0)),
                                     fade_in=float(kw.get("fade_in", 0.0))) is not None
        if a in ("add_step", "addStep"):
            fid = kw.get("function_id")
            if fid is None:
                return False
            self.add_step(fid, fade_in=float(kw.get("fade_in", 0.0)),
                          hold=float(kw.get("hold", 1.0)))
            return True
        if a in ("remove_last_step", "removeLastStep", "undo_step"):
            if not self.steps:
                return False
            self.steps.pop()
            if self._step_idx >= len(self.steps):
                self._step_idx = max(0, len(self.steps) - 1)
            return True
        if a in ("clear_steps", "clearSteps"):
            self.steps.clear()
            self._step_idx = 0
            return True
        if a in ("restart", "reset", "retrigger"):
            self._on_start()
            return True
        if a in ("reverse_direction", "reverseDirection"):
            self.direction = (Direction.Backward if self.direction == Direction.Forward
                              else Direction.Forward)
            return True
        if a in ("toggle_bounce", "toggleBounce", "toggle_pingpong"):
            self.run_order = (RunOrder.Loop if self.run_order == RunOrder.PingPong
                              else RunOrder.PingPong)
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
        """(key, label) der Chaser-Live-Aktionen fuer die Bindungs-UI (VC/MIDI)."""
        return [
            ("capture_step",     "Schritt aufnehmen"),
            ("remove_last_step", "Letzten Schritt löschen"),
            ("clear_steps",      "Alle Schritte löschen"),
            ("reverse_direction", "Richtung"),
            ("toggle_bounce",    "Ping-Pong"),
            ("restart",          "Neustart"),
            ("tap",              "Tap-Tempo"),
        ]

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "run_order": self.run_order.value,
            "direction": self.direction.value,
            "speed": self.speed,
            "audio_triggered": self.audio_triggered,
            "beats_per_step": self.beats_per_step,
            "steps": [
                self._step_to_dict(s)
                for s in self.steps
            ],
        })
        return d

    @staticmethod
    def _step_to_dict(s: "ChaserStep") -> dict:
        d = {
            "function_id": s.function_id,
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
    def from_dict(cls, d: dict) -> "Chaser":
        c = cls(name=d.get("name", "Chaser"), fid=d.get("id"))
        c.run_order = RunOrder(d.get("run_order", "Loop"))
        c.direction = Direction(d.get("direction", "Forward"))
        c.speed = d.get("speed", 1.0)
        c.audio_triggered = bool(d.get("audio_triggered", False))
        c.beats_per_step = int(d.get("beats_per_step", 1))
        for sd in d.get("steps", []):
            step = ChaserStep(
                function_id=sd["function_id"],
                fade_in=sd.get("fade_in", 0.0),
                hold=sd.get("hold", 1.0),
                fade_out=sd.get("fade_out", 0.0),
                note=sd.get("note", ""),
            )
            if "fade_in_curve" in sd:
                step.fade_in_curve = fc.FadeCurve.from_dict(sd["fade_in_curve"])
            if "fade_out_curve" in sd:
                step.fade_out_curve = fc.FadeCurve.from_dict(sd["fade_out_curve"])
            c.steps.append(step)
        return c
