"""Neutrales Laser-Frame-Modell + Safety-Clamping (LAS-05).

Die UI/Engine spricht NIE protokollspezifische Strukturen (kein
``dac_point`` nach außen), sondern :class:`LaserPoint`/:class:`LaserFrame`
in normierten Einheiten: x/y in -1..+1 (Scanner-Vollausschlag), Farben 0..1.
Jedes Backend übersetzt selbst in sein Wire-Format.

Safety: :func:`clamp_frame` ist die PFLICHT-Stufe zwischen Muster-Berechnung
und Senden — unabhängig davon, was Programmer/Effekte liefern. Sie begrenzt
Scan-Ausschlag, Punktrate und Helligkeit und blankt Frames, die zu wenige
Punkte haben (stehende Strahlen = Verletzungsgefahr).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class LaserPoint:
    """Ein Galvo-Punkt: Position normiert -1..+1, Farbe 0..1."""
    x: float
    y: float
    r: float = 1.0
    g: float = 1.0
    b: float = 1.0
    blanked: bool = False


@dataclass
class LaserFrame:
    """Eine Punktliste + Wiedergaberate (Punkte pro Sekunde)."""
    points: list[LaserPoint] = field(default_factory=list)
    pps: int = 20000

    def blank_copy(self) -> "LaserFrame":
        """Gleiche Geometrie, aber komplett dunkel (Blackout/E-Stop-Pfad:
        Galvos bewegen sich weiter, es tritt kein Licht aus)."""
        return LaserFrame(
            points=[replace(p, blanked=True) for p in self.points],
            pps=self.pps,
        )


@dataclass
class LaserLimits:
    """Harte Ausgabe-Grenzen — greifen NACH Programmer/Effekten, immer.

    ``max_size``: maximaler Scan-Ausschlag als Anteil des Vollausschlags
    (0.1..1.0). Kleinere Werte = engerer, sicherer Scanbereich.
    ``min_points``: Frames mit weniger Punkten werden komplett geblankt —
    wenige Punkte bündeln die Energie (stehende Strahlen).
    ``intensity``: globaler Helligkeits-Faktor 0..1 (Not-Dimmer).
    """
    max_size: float = 1.0
    min_pps: int = 1000
    max_pps: int = 30000
    min_points: int = 16
    max_points: int = 4096
    intensity: float = 1.0


def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def clamp_frame(frame: LaserFrame, limits: LaserLimits) -> LaserFrame:
    """Erzwingt die Limits auf einer Kopie des Frames (Original unberührt)."""
    size = max(0.1, min(1.0, float(limits.max_size)))
    inten = _clamp01(float(limits.intensity))
    pps = max(int(limits.min_pps), min(int(limits.max_pps), int(frame.pps)))

    points = list(frame.points)[: max(0, int(limits.max_points))]
    too_few = len(points) < int(limits.min_points)

    out: list[LaserPoint] = []
    for p in points:
        out.append(LaserPoint(
            x=max(-size, min(size, float(p.x))),
            y=max(-size, min(size, float(p.y))),
            r=_clamp01(float(p.r)) * inten,
            g=_clamp01(float(p.g)) * inten,
            b=_clamp01(float(p.b)) * inten,
            blanked=bool(p.blanked) or too_few,
        ))
    return LaserFrame(points=out, pps=pps)
