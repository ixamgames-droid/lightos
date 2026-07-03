"""Laser-Zeichenfigur (LAS-07) — eine benannte, wiederverwendbare Punktliste.

Der freie Zeichenmodus baut auf diesem Modell auf: eine :class:`LaserFigure`
ist eine geometrische Vorlage (normierte Punkte −1..+1, Farbe pro Punkt,
Blank-Segmente), die der :class:`~src.core.laser.laser_output.LaserOutputManager`
pro Tick zu einem sende-fertigen :class:`~src.core.laser.frame.LaserFrame`
resampled — verschoben/skaliert nach den Programmer-Werten (laser_x/y, zoom).

Getrennt von :class:`LaserFrame`: eine Figur ist die editierbare, persistente
Vorlage (wenige Stützpunkte); der Frame ist das pro Tick berechnete,
gleichmäßig abgetastete Sende-Ergebnis (hunderte Punkte).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .frame import LaserFrame, LaserPoint


@dataclass
class FigurePoint:
    """Stützpunkt einer Figur: Position −1..+1, Farbe 0..1, Blank = unsichtbarer
    Sprung (Galvo bewegt sich hin, ohne zu leuchten)."""
    x: float
    y: float
    r: float = 1.0
    g: float = 1.0
    b: float = 1.0
    blank: bool = False

    def to_dict(self) -> dict:
        d = {"x": round(self.x, 4), "y": round(self.y, 4)}
        if (self.r, self.g, self.b) != (1.0, 1.0, 1.0):
            d.update(r=round(self.r, 3), g=round(self.g, 3), b=round(self.b, 3))
        if self.blank:
            d["blank"] = True
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "FigurePoint":
        return cls(
            x=float(d.get("x", 0.0)), y=float(d.get("y", 0.0)),
            r=float(d.get("r", 1.0)), g=float(d.get("g", 1.0)),
            b=float(d.get("b", 1.0)), blank=bool(d.get("blank", False)))


def _clampf(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


@dataclass
class LaserFigure:
    """Benannte Punktliste + Schließen-Flag (Polygon vs. offener Pfad)."""
    name: str = ""
    points: list[FigurePoint] = field(default_factory=list)
    closed: bool = True

    # ── Serialisierung ────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "closed": self.closed,
            "points": [p.to_dict() for p in self.points],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LaserFigure":
        return cls(
            name=str(d.get("name", "") or ""),
            closed=bool(d.get("closed", True)),
            points=[FigurePoint.from_dict(p) for p in d.get("points", [])])

    # ── Sample-Erzeugung ──────────────────────────────────────────────────
    def to_frame(self, sample_count: int, pps: int, *,
                 offset_x: float = 0.0, offset_y: float = 0.0,
                 scale: float = 1.0) -> LaserFrame:
        """Resampled die Figur gleichmäßig auf ``sample_count`` Punkte
        (bogenlängen-nah über Segment-Interpolation) und liefert einen
        sende-fertigen Frame. Leere/1-Punkt-Figuren → leerer Frame.

        ``offset_x/y`` verschieben, ``scale`` skaliert die Figur (aus den
        Programmer-Werten). Blank-Stützpunkte erzeugen blanke Segmente."""
        pts = self.points
        if len(pts) < 2 or sample_count < 2:
            return LaserFrame(points=[], pps=pps)

        seq = list(pts)
        if self.closed:
            seq = seq + [pts[0]]
        segs = len(seq) - 1

        out: list[LaserPoint] = []
        for i in range(sample_count):
            # Position entlang der Stützpunkt-Kette (uniform je Segment).
            t = (i / (sample_count - 1)) * segs
            seg = min(segs - 1, int(t))
            frac = t - seg
            a, b = seq[seg], seq[seg + 1]
            x = a.x + (b.x - a.x) * frac
            y = a.y + (b.y - a.y) * frac
            # Farbe vom Zielstützpunkt; ein blanker Zielpunkt blankt das Segment.
            out.append(LaserPoint(
                x=_clampf(offset_x + x * scale, -1.0, 1.0),
                y=_clampf(offset_y + y * scale, -1.0, 1.0),
                r=b.r, g=b.g, b=b.b,
                blanked=b.blank))
        return LaserFrame(points=out, pps=pps)


# ── Eingebaute Grundfiguren (Startvorlagen für den Zeichenmodus) ──────────

def _regular_polygon(n: int, name: str) -> LaserFigure:
    pts = [FigurePoint(x=math.cos(2 * math.pi * k / n - math.pi / 2),
                       y=math.sin(2 * math.pi * k / n - math.pi / 2))
           for k in range(n)]
    return LaserFigure(name=name, points=pts, closed=True)


def builtin_figures() -> list[LaserFigure]:
    """Startvorlagen: Kreis (24-Eck), Dreieck, Quadrat, Linie."""
    return [
        _regular_polygon(24, "Kreis"),
        _regular_polygon(3, "Dreieck"),
        _regular_polygon(4, "Quadrat"),
        LaserFigure(name="Linie",
                    points=[FigurePoint(-0.9, 0.0), FigurePoint(0.9, 0.0)],
                    closed=False),
    ]
