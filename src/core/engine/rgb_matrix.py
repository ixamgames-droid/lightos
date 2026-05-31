"""RGB Matrix Engine — LED-Grid Effekte wie in QLC+."""
from __future__ import annotations
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


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


@dataclass
class RgbMatrixInstance:
    name: str
    cols: int = 8
    rows: int = 4
    # Fixture-Grid: list of fids row-major (len = cols*rows)
    fixture_grid: list[int] = field(default_factory=list)
    algorithm: RgbAlgorithm = RgbAlgorithm.CHASE_H
    color1: Color = (255, 0, 0)
    color2: Color = (0, 0, 255)
    color3: Color = (0, 255, 0)
    speed: float = 1.0     # Schritte pro Sekunde
    direction: str = "forward"
    _step: float = 0.0
    _last_tick: float = 0.0
    _running: bool = False

    def start(self):
        self._running = True
        self._last_tick = time.monotonic()

    def stop(self):
        self._running = False

    def tick(self) -> dict[int, dict[str, int]]:
        if not self._running or not self.fixture_grid:
            return {}
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        self._step = (self._step + self.speed * dt) % max(self.cols, self.rows, 1)

        grid = self._generate()
        result = {}
        for idx, fid in enumerate(self.fixture_grid):
            if idx >= len(grid):
                break
            r, g, b = grid[idx]
            result[fid] = {"color_r": r, "color_g": g, "color_b": b}
        return result

    def _generate(self) -> list[Color]:
        cols, rows = self.cols, self.rows
        step = self._step
        pixels: list[Color] = [(0, 0, 0)] * (cols * rows)
        algo = self.algorithm

        for row in range(rows):
            for col in range(cols):
                idx = row * cols + col
                c1, c2, c3 = self.color1, self.color2, self.color3

                if algo == RgbAlgorithm.PLAIN:
                    pixels[idx] = c1

                elif algo == RgbAlgorithm.CHASE_H:
                    on = int(step) % cols == col
                    pixels[idx] = c1 if on else (0, 0, 0)

                elif algo == RgbAlgorithm.CHASE_V:
                    on = int(step) % rows == row
                    pixels[idx] = c1 if on else (0, 0, 0)

                elif algo == RgbAlgorithm.CHASE_DIAG:
                    on = (row + col + int(step)) % 2 == 0
                    pixels[idx] = c1 if on else c2

                elif algo == RgbAlgorithm.WIPE_H:
                    t = (step % cols) / cols
                    pixels[idx] = c1 if col / cols < t else c2

                elif algo == RgbAlgorithm.WIPE_V:
                    t = (step % rows) / rows
                    pixels[idx] = c1 if row / rows < t else c2

                elif algo == RgbAlgorithm.RAINBOW:
                    hue = ((col + row * 0.5 + step * 30) % 360)
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
                    cx, cy = cols / 2, rows / 2
                    angle = math.atan2(row - cy, col - cx)
                    norm = (angle + math.pi) / (2 * math.pi)
                    beam = (step * 0.1) % 1.0
                    diff = abs(norm - beam)
                    if diff > 0.5:
                        diff = 1.0 - diff
                    brightness = max(0.0, 1.0 - diff * 8)
                    r2 = int(c1[0] * brightness)
                    g2 = int(c1[1] * brightness)
                    b2 = int(c1[2] * brightness)
                    pixels[idx] = (r2, g2, b2)

                elif algo == RgbAlgorithm.SINEPLASMA:
                    v = (math.sin(col * 0.8 + step) +
                         math.sin(row * 0.8 + step * 0.7) +
                         math.sin((col + row) * 0.5 + step * 1.3)) / 3
                    t = (v + 1) / 2
                    pixels[idx] = lerp_color(c1, c2, t)

        return pixels

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "cols": self.cols, "rows": self.rows,
            "fixture_grid": self.fixture_grid,
            "algorithm": self.algorithm.value,
            "color1": list(self.color1),
            "color2": list(self.color2),
            "color3": list(self.color3),
            "speed": self.speed,
            "direction": self.direction,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RgbMatrixInstance":
        m = cls(name=d["name"])
        m.cols = d.get("cols", 8)
        m.rows = d.get("rows", 4)
        m.fixture_grid = d.get("fixture_grid", [])
        m.algorithm = RgbAlgorithm(d.get("algorithm", "Plain"))
        m.color1 = tuple(d.get("color1", [255, 0, 0]))
        m.color2 = tuple(d.get("color2", [0, 0, 255]))
        m.color3 = tuple(d.get("color3", [0, 255, 0]))
        m.speed = float(d.get("speed", 1.0))
        m.direction = d.get("direction", "forward")
        return m
