"""EFX Engine — Automatische Pan/Tilt Bewegungsmuster wie in QLC+."""
from __future__ import annotations
import math
import time
import threading
from dataclasses import dataclass, field
from enum import Enum


class EfxAlgorithm(str, Enum):
    CIRCLE    = "Circle"
    EIGHT     = "Eight"
    LINE      = "Line"
    DIAMOND   = "Diamond"
    SQUARE    = "Square"
    LISSAJOUS = "Lissajous"
    RANDOM    = "Random"
    TRIANGLE  = "Triangle"


@dataclass
class EfxFixture:
    fid: int
    start_offset: float = 0.0   # Phase-Offset 0.0–1.0 (für Fan-Effekte)
    pan_attr:  str = "pan"
    tilt_attr: str = "tilt"


@dataclass
class EfxInstance:
    name: str
    algorithm: EfxAlgorithm = EfxAlgorithm.CIRCLE
    fixtures: list[EfxFixture] = field(default_factory=list)

    # Geometrie
    width: float  = 100.0   # 0–255
    height: float = 100.0
    x_offset: float = 128.0
    y_offset: float = 128.0
    rotation: float = 0.0   # Grad
    x_freq: float = 1.0     # für Lissajous
    y_freq: float = 1.0
    x_phase: float = 0.0
    y_phase: float = 90.0

    # Timing
    speed_hz: float = 0.5     # Umdrehungen pro Sekunde
    direction: str = "forward" # "forward" / "backward" / "bounce"

    # State
    _phase: float = 0.0
    _bounce_dir: float = 1.0
    _running: bool = False
    _last_tick: float = 0.0

    def start(self):
        self._running = True
        self._last_tick = time.monotonic()

    def stop(self):
        self._running = False

    def tick(self) -> dict[int, dict[str, int]]:
        """Berechnet aktuelle Pan/Tilt Werte für alle Fixtures. Gibt {fid: {attr: val}} zurück."""
        if not self._running:
            return {}

        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now

        # Phase fortschreiten
        delta = self.speed_hz * dt
        if self.direction == "backward":
            self._phase -= delta
        elif self.direction == "bounce":
            self._phase += delta * self._bounce_dir
            if self._phase >= 1.0:
                self._phase = 1.0
                self._bounce_dir = -1.0
            elif self._phase <= 0.0:
                self._phase = 0.0
                self._bounce_dir = 1.0
        else:
            self._phase += delta
        self._phase %= 1.0

        result = {}
        n = len(self.fixtures)
        for i, fx in enumerate(self.fixtures):
            offset = fx.start_offset + (i / max(n, 1)) if n > 1 else fx.start_offset
            phase = (self._phase + offset) % 1.0
            pan, tilt = self._calc(phase)
            result[fx.fid] = {
                fx.pan_attr:  int(pan),
                fx.tilt_attr: int(tilt),
            }
        return result

    def _calc(self, phase: float) -> tuple[float, float]:
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

        elif algo == EfxAlgorithm.DIAMOND:
            x = math.cos(t) * hw
            y = (abs(math.cos(t)) - 0.5) * 2 * hh * math.sin(t)

        elif algo == EfxAlgorithm.SQUARE:
            # Quadratische Bewegung (squished)
            x = math.copysign(hw, math.cos(t)) if abs(math.cos(t)) > abs(math.sin(t)) else math.cos(t) * hw
            y = math.copysign(hh, math.sin(t)) if abs(math.sin(t)) > abs(math.cos(t)) else math.sin(t) * hh

        elif algo == EfxAlgorithm.LISSAJOUS:
            xf = self.x_freq
            yf = self.y_freq
            xp = math.radians(self.x_phase)
            yp = math.radians(self.y_phase)
            x = math.cos(t * xf + xp) * hw
            y = math.sin(t * yf + yp) * hh

        elif algo == EfxAlgorithm.TRIANGLE:
            # Dreieck
            t_n = phase  # 0..1
            if t_n < 0.5:
                x = (t_n * 4 - 1) * hw
                y = hh
            else:
                x = 0.0
                y = ((1 - t_n) * 4 - 1) * hh

        elif algo == EfxAlgorithm.RANDOM:
            # Pseudo-Random via Fourier-Näherung
            x = (math.sin(t) * 0.6 + math.sin(2.3 * t) * 0.3 + math.sin(5.1 * t) * 0.1) * hw
            y = (math.cos(t * 1.7) * 0.5 + math.cos(3.1 * t) * 0.4 + math.cos(0.7 * t) * 0.1) * hh
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

        pan  = max(0, min(255, self.x_offset + x))
        tilt = max(0, min(255, self.y_offset + y))
        return pan, tilt

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "algorithm": self.algorithm.value,
            "fixtures": [{"fid": f.fid, "offset": f.start_offset} for f in self.fixtures],
            "width": self.width, "height": self.height,
            "x_offset": self.x_offset, "y_offset": self.y_offset,
            "rotation": self.rotation,
            "x_freq": self.x_freq, "y_freq": self.y_freq,
            "x_phase": self.x_phase, "y_phase": self.y_phase,
            "speed_hz": self.speed_hz, "direction": self.direction,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EfxInstance":
        e = cls(name=d["name"])
        e.algorithm = EfxAlgorithm(d.get("algorithm", "Circle"))
        e.fixtures = [
            EfxFixture(fid=f.get("fid") if isinstance(f, dict) else getattr(f, "fid", None),
                       start_offset=(f.get("offset", 0) if isinstance(f, dict) else getattr(f, "start_offset", 0)))
            for f in d.get("fixtures", [])
            if (isinstance(f, dict) and f.get("fid") is not None)
            or (not isinstance(f, dict) and getattr(f, "fid", None) is not None)
        ]
        for k in ("width","height","x_offset","y_offset","rotation",
                  "x_freq","y_freq","x_phase","y_phase","speed_hz"):
            if k in d:
                setattr(e, k, float(d[k]))
        e.direction = d.get("direction", "forward")
        return e
