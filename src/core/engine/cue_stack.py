"""CueStack — Führt eine Cueliste aus mit Crossfades."""
from __future__ import annotations
import threading
import time
from .cue import Cue

TICK = 0.02  # 50 Hz Fade-Update


class FadeState:
    """Laufender Fade zwischen zwei Cue-Zuständen."""

    def __init__(self, from_vals: dict, to_vals: dict,
                 duration: float, delay: float):
        self.from_vals = from_vals    # {fid: {attr: int}}
        self.to_vals = to_vals
        self.duration = max(duration, 0.001)
        self.delay = delay
        self.start_time = time.monotonic()
        self.done = False

    def current_values(self) -> dict[int, dict[str, int]]:
        now = time.monotonic()
        elapsed = now - self.start_time - self.delay
        if elapsed < 0:
            return self.from_vals
        t = min(1.0, elapsed / self.duration)
        # S-Kurve (Ease-In-Out)
        t = t * t * (3 - 2 * t)
        if t >= 1.0:
            self.done = True
            return self.to_vals

        result: dict[int, dict[str, int]] = {}
        all_fids = set(self.from_vals) | set(self.to_vals)
        for fid in all_fids:
            from_f = self.from_vals.get(fid, {})
            to_f = self.to_vals.get(fid, {})
            all_attrs = set(from_f) | set(to_f)
            merged = {}
            for attr in all_attrs:
                fv = from_f.get(attr, 0)
                tv = to_f.get(attr, fv)
                merged[attr] = int(fv + (tv - fv) * t)
            result[fid] = merged
        return result


class CueStack:
    def __init__(self, name: str = "Neue Cueliste"):
        self.name = name
        self.cues: list[Cue] = []
        self.loop = False
        self._current_idx = -1
        self._fade: FadeState | None = None
        self._output: dict[int, dict[str, int]] = {}
        self._lock = threading.Lock()
        self._follow_timer: threading.Timer | None = None
        self._on_cue_change: list = []        # callbacks(idx, cue)
        self._on_output_change: list = []     # callbacks(output_dict)

    # ── Navigation ────────────────────────────────────────────────────────────

    def go(self):
        with self._lock:
            self._cancel_follow()
            if not self.cues:
                return
            next_idx = self._current_idx + 1
            if next_idx >= len(self.cues):
                if self.loop:
                    next_idx = 0
                else:
                    return
            self._fade_to(next_idx)

    def back(self):
        with self._lock:
            self._cancel_follow()
            if not self.cues or self._current_idx <= 0:
                return
            self._fade_to(self._current_idx - 1, use_fade_out=True)

    def go_to(self, number: float):
        with self._lock:
            for i, cue in enumerate(self.cues):
                if abs(cue.number - number) < 0.001:
                    self._fade_to(i)
                    return

    def stop(self):
        with self._lock:
            self._cancel_follow()
            self._fade = None
            self._output = {}
            self._current_idx = -1
        self._emit_output()

    @property
    def current_cue(self) -> Cue | None:
        if 0 <= self._current_idx < len(self.cues):
            return self.cues[self._current_idx]
        return None

    @property
    def current_index(self) -> int:
        return self._current_idx

    # ── Cue-Verwaltung ────────────────────────────────────────────────────────

    def add_cue(self, cue: Cue):
        self.cues.append(cue)
        self.cues.sort(key=lambda c: c.number)

    def remove_cue(self, number: float):
        self.cues = [c for c in self.cues if abs(c.number - number) > 0.001]

    def update_cue(self, cue: Cue):
        for i, c in enumerate(self.cues):
            if abs(c.number - cue.number) < 0.001:
                self.cues[i] = cue
                return
        self.add_cue(cue)

    # ── Tick (wird von Engine-Timer aufgerufen) ───────────────────────────────

    def tick(self) -> dict[int, dict[str, int]] | None:
        """Gibt aktuellen Output zurück oder None wenn kein Fade läuft."""
        with self._lock:
            if self._fade is None:
                return None
            vals = self._fade.current_values()
            if self._fade.done:
                self._fade = None
            self._output = vals
        self._emit_output()
        return vals

    def get_output(self) -> dict[int, dict[str, int]]:
        return dict(self._output)

    # ── Internes ──────────────────────────────────────────────────────────────

    def _fade_to(self, idx: int, use_fade_out: bool = False):
        cue = self.cues[idx]
        from_vals = dict(self._output)
        fade_time = cue.fade_out if use_fade_out else cue.fade_in
        self._fade = FadeState(
            from_vals, cue.values, fade_time, cue.delay_in
        )
        self._current_idx = idx
        for cb in self._on_cue_change:
            try:
                cb(idx, cue)
            except Exception:
                pass
        if cue.follow is not None and cue.follow >= 0:
            self._follow_timer = threading.Timer(
                cue.follow + fade_time, self.go
            )
            self._follow_timer.daemon = True
            self._follow_timer.start()

    def _cancel_follow(self):
        if self._follow_timer:
            self._follow_timer.cancel()
            self._follow_timer = None

    def _emit_output(self):
        for cb in self._on_output_change:
            try:
                cb(self._output)
            except Exception:
                pass

    def subscribe_cue(self, cb):
        self._on_cue_change.append(cb)

    def subscribe_output(self, cb):
        self._on_output_change.append(cb)

    # ── Serialisierung ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "loop": self.loop,
            "cues": [c.to_dict() for c in self.cues],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CueStack":
        stack = cls(d.get("name", "Cueliste"))
        stack.loop = d.get("loop", False)
        for cd in d.get("cues", []):
            stack.add_cue(Cue.from_dict(cd))
        return stack
