"""Fade-Kurven — formen den zeitlichen Verlauf eines Fades (GrandMA3-Phaser-artig).

Eine ``FadeCurve`` bildet den Fade-Fortschritt ``progress`` (0..1) auf die
"Completion" (0..1) ab — also wie weit der Fade bereits vollzogen ist.

  * Fade-In:  value = start + (target - start) * curve.eval(progress)
  * Fade-Out: completion = curve.eval(progress);  retained = 1 - completion

Damit lassen sich beide Richtungen mit denselben Presets beschreiben:
``LINEAR`` (Gerade), ``EASE_IN`` (langsamer Start), ``EASE_OUT`` (schneller
Start), ``S_CURVE`` (sanft an beiden Enden) und ``SNAP`` (hält, dann harter
Sprung am Ende — z. B. für abruptes Aus).

Die Auswertung läuft im DMX-Tick (~30–44 Hz) und ist bewusst allokationsfrei.
"""
from __future__ import annotations
from dataclasses import dataclass, field


Point = tuple[float, float]


def _clamp01(v: float) -> float:
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


@dataclass
class FadeCurve:
    """Benannte Fade-Kurve aus sortierten Kontrollpunkten (x, y) in [0, 1].

    ``mode`` = "linear" interpoliert geradlinig zwischen den Punkten,
    "smooth" nutzt monotone kubische Hermite-Interpolation (Fritsch–Carlson),
    die garantiert nicht über-/unterschwingt — ideal für Fades.
    """
    name: str = "Linear"
    mode: str = "linear"                       # "linear" | "smooth"
    points: list[Point] = field(default_factory=lambda: [(0.0, 0.0), (1.0, 1.0)])

    def __post_init__(self):
        self._normalize()

    # ── Punkt-Verwaltung ──────────────────────────────────────────────────────

    def _normalize(self):
        """Clampt alle Punkte nach [0,1], sortiert nach x, sichert die
        Endpunkte bei x=0 und x=1 und entfernt doppelte x-Werte."""
        pts = [(_clamp01(x), _clamp01(y)) for (x, y) in self.points]
        pts.sort(key=lambda p: p[0])
        if not pts or pts[0][0] > 0.0:
            pts.insert(0, (0.0, pts[0][1] if pts else 0.0))
        if pts[-1][0] < 1.0:
            pts.append((1.0, pts[-1][1]))
        # Doppelte x zusammenfassen (letzter gewinnt), aber Endpunkt-Sprünge
        # (z. B. SNAP bei x≈1) sollen erhalten bleiben → nur exakte Duplikate.
        cleaned: list[Point] = []
        for p in pts:
            if cleaned and p[0] == cleaned[-1][0]:
                cleaned[-1] = p
            else:
                cleaned.append(p)
        self.points = cleaned

    def set_points(self, points: list[Point]):
        self.points = list(points)
        self._normalize()

    # ── Auswertung ────────────────────────────────────────────────────────────

    def eval(self, t: float) -> float:
        """Completion (0..1) für Fortschritt ``t`` (0..1)."""
        t = _clamp01(t)
        pts = self.points
        n = len(pts)
        if n == 1:
            return _clamp01(pts[0][1])

        # Segment finden: pts[i].x <= t <= pts[i+1].x
        i = 0
        while i < n - 2 and t > pts[i + 1][0]:
            i += 1
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        dx = x1 - x0
        if dx <= 1e-9:
            return _clamp01(y1)
        u = (t - x0) / dx

        if self.mode != "smooth":
            return _clamp01(y0 + (y1 - y0) * u)

        # Monotone kubische Hermite (Fritsch–Carlson) für dieses Segment.
        m0 = self._tangent(i)
        m1 = self._tangent(i + 1)
        u2 = u * u
        u3 = u2 * u
        h00 = 2 * u3 - 3 * u2 + 1
        h10 = u3 - 2 * u2 + u
        h01 = -2 * u3 + 3 * u2
        h11 = u3 - u2
        y = h00 * y0 + h10 * dx * m0 + h01 * y1 + h11 * dx * m1
        return _clamp01(y)

    def _tangent(self, i: int) -> float:
        """Monotonie-erhaltende Tangente am Punkt i (Fritsch–Carlson)."""
        pts = self.points
        n = len(pts)

        def secant(a: int, b: int) -> float:
            dx = pts[b][0] - pts[a][0]
            return (pts[b][1] - pts[a][1]) / dx if dx > 1e-9 else 0.0

        if i == 0:
            d = secant(0, 1)
        elif i == n - 1:
            d = secant(n - 2, n - 1)
        else:
            s_left = secant(i - 1, i)
            s_right = secant(i, i + 1)
            # Vorzeichenwechsel oder Plateau → Tangente 0 (kein Überschwingen)
            if s_left * s_right <= 0.0:
                d = 0.0
            else:
                d = (s_left + s_right) / 2.0
                # Tangente begrenzen, damit Monotonie erhalten bleibt
                d = max(-3.0 * min(abs(s_left), abs(s_right)),
                        min(d, 3.0 * min(abs(s_left), abs(s_right))))
        return d

    # ── Serialisierung ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "mode": self.mode,
            "points": [[round(x, 5), round(y, 5)] for (x, y) in self.points],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FadeCurve":
        pts = [(float(p[0]), float(p[1])) for p in d.get("points", [])]
        return cls(
            name=d.get("name", "Linear"),
            mode=d.get("mode", "linear"),
            points=pts or [(0.0, 0.0), (1.0, 1.0)],
        )

    def copy(self) -> "FadeCurve":
        return FadeCurve(name=self.name, mode=self.mode, points=list(self.points))

    def is_linear_default(self) -> bool:
        """True, wenn die Kurve eine reine 0→1-Gerade ist (Standard).
        Wird genutzt, um nur abweichende Kurven zu serialisieren."""
        return (self.mode == "linear"
                and self.points == [(0.0, 0.0), (1.0, 1.0)])


# ── Presets ────────────────────────────────────────────────────────────────────

def linear() -> FadeCurve:
    return FadeCurve("Linear", "linear", [(0.0, 0.0), (1.0, 1.0)])


def ease_in() -> FadeCurve:
    # langsamer Start, schnelles Ende
    return FadeCurve("Ease In", "smooth", [(0.0, 0.0), (0.6, 0.2), (1.0, 1.0)])


def ease_out() -> FadeCurve:
    # schneller Start, langsames Ende
    return FadeCurve("Ease Out", "smooth", [(0.0, 0.0), (0.4, 0.8), (1.0, 1.0)])


def s_curve() -> FadeCurve:
    return FadeCurve("S-Curve", "smooth",
                     [(0.0, 0.0), (0.2, 0.03), (0.8, 0.97), (1.0, 1.0)])


def snap() -> FadeCurve:
    # hält bei 0, springt erst ganz am Ende auf 1 → abrupter Wechsel
    return FadeCurve("Snap", "linear", [(0.0, 0.0), (0.999, 0.0), (1.0, 1.0)])


def presets() -> list[FadeCurve]:
    """Liste der eingebauten Presets (jeweils frische Kopien)."""
    return [linear(), ease_in(), ease_out(), s_curve(), snap()]


_LINEAR_SINGLETON = linear()


def default_curve() -> FadeCurve:
    """Geteilte Linear-Kurve für Stellen ohne eigene Kurve (read-only nutzen)."""
    return _LINEAR_SINGLETON
