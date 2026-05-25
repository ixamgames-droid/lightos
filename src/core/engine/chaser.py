"""Chaser function — steps through a list of functions in sequence."""
from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from .function import Function, FunctionType, RunOrder, Direction

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

    def total_duration(self) -> float:
        return self.fade_in + self.hold + self.fade_out


class Chaser(Function):
    """
    QLC+ Chaser: steps through ChaserStep objects, each pointing to another
    Function. Supports Loop, SingleShot, PingPong and Random run orders.
    """

    function_type = FunctionType.Chaser

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

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_start(self):
        if self.direction == Direction.Backward:
            self._step_idx = len(self.steps) - 1
        else:
            self._step_idx = 0
        self._step_elapsed = 0.0
        self._ping_pong_dir = 1 if self.direction == Direction.Forward else -1
        self._visited = set()

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

    def write(self, universes: dict[int, "Universe"],
              patch_cache: list["PatchedFixture"],
              dt: float,
              function_registry: dict[int, Function] | None = None):
        if not self._running or not self.steps:
            return

        effective_dt = dt * self.speed
        step = self.steps[self._step_idx]
        total = step.total_duration()
        if total <= 0:
            total = 0.001

        if self.audio_triggered:
            # Step-Advance ist nur per Beat-Trigger
            if self._pending_advance:
                self._pending_advance = False
                advanced = self._advance_step()
                if not advanced:
                    self._running = False
                    return
                step = self.steps[self._step_idx]
                self._step_elapsed = 0.0
            # Aktuelle Step laufen lassen (Scene write)
            if function_registry:
                child = function_registry.get(step.function_id)
                if child is not None:
                    child._running = True
                    child._elapsed = self._step_elapsed
                    child.write(universes, patch_cache, 0.0, function_registry)
                    child._running = False
            self._step_elapsed += effective_dt
            self._elapsed += effective_dt
            return

        # Run the child function for this step
        if function_registry:
            child = function_registry.get(step.function_id)
            if child is not None:
                # Ensure child is "running" for write to work
                child._running = True
                child._elapsed = self._step_elapsed
                child.write(universes, patch_cache, 0.0, function_registry)
                child._running = False

        self._step_elapsed += effective_dt
        self._elapsed += effective_dt

        # Advance step when duration elapses
        if self._step_elapsed >= total:
            self._step_elapsed = 0.0
            advanced = self._advance_step()
            if not advanced:
                self._running = False

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
                {
                    "function_id": s.function_id,
                    "fade_in": s.fade_in,
                    "hold": s.hold,
                    "fade_out": s.fade_out,
                    "note": s.note,
                }
                for s in self.steps
            ],
        })
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
            c.steps.append(ChaserStep(
                function_id=sd["function_id"],
                fade_in=sd.get("fade_in", 0.0),
                hold=sd.get("hold", 1.0),
                fade_out=sd.get("fade_out", 0.0),
                note=sd.get("note", ""),
            ))
        return c
