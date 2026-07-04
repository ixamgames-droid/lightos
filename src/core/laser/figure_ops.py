"""Geometrie-Generatoren + Vereinfachung für Laser-Figuren (LAS-14).

Rein und ohne Qt: erzeugt normierte ``FigurePoint``-Listen (−1..+1) für die
Formwerkzeuge des Zeichen-Studios (Kreis / Ellipse / Rechteck / Linie /
regelmäßiges Polygon / Stern) und vereinfacht Freihand-Striche per
Ramer-Douglas-Peucker, damit ein Fingerzug nicht hunderte Rohpunkte hinterlässt.

Alle Generatoren liefern reine Stützpunkt-Listen (Farbe optional, Default weiß);
das Werkzeug-/UI-Layer (LAS-14b) setzt daraus eine :class:`LaserFigure` zusammen.
Koordinaten wie im ganzen Laser-Stack: −1..+1, 0,0 = Mitte, +y = oben.
"""
from __future__ import annotations

import math

from .figure import FigurePoint

RGB = tuple


def _clamp(v: float) -> float:
    return -1.0 if v < -1.0 else (1.0 if v > 1.0 else v)


def _pt(x: float, y: float, color) -> FigurePoint:
    r, g, b = color
    return FigurePoint(x=_clamp(x), y=_clamp(y), r=r, g=g, b=b)


def regular_polygon(sides: int, *, cx: float = 0.0, cy: float = 0.0,
                    r: float = 0.9, rotation: float = -math.pi / 2,
                    color=(1.0, 1.0, 1.0)) -> list:
    """``sides``-Eck um (cx, cy), Radius ``r``. ``rotation`` = Startwinkel
    (Default −π/2 = erster Punkt oben)."""
    sides = max(3, int(sides))
    return [_pt(cx + r * math.cos(rotation + 2 * math.pi * k / sides),
                cy + r * math.sin(rotation + 2 * math.pi * k / sides), color)
            for k in range(sides)]


def circle(*, cx: float = 0.0, cy: float = 0.0, r: float = 0.9,
           segments: int = 48, color=(1.0, 1.0, 1.0)) -> list:
    """Kreis als ``segments``-Eck (genug Ecken für runde Optik)."""
    return regular_polygon(segments, cx=cx, cy=cy, r=r, color=color)


def ellipse(*, cx: float = 0.0, cy: float = 0.0, rx: float = 0.9,
            ry: float = 0.6, segments: int = 48,
            color=(1.0, 1.0, 1.0)) -> list:
    segments = max(3, int(segments))
    return [_pt(cx + rx * math.cos(2 * math.pi * k / segments),
                cy + ry * math.sin(2 * math.pi * k / segments), color)
            for k in range(segments)]


def rectangle(*, cx: float = 0.0, cy: float = 0.0, w: float = 1.6,
              h: float = 1.2, color=(1.0, 1.0, 1.0)) -> list:
    """Achsen-paralleles Rechteck (4 Ecken, im Uhrzeigersinn ab links-unten)."""
    hw, hh = w / 2.0, h / 2.0
    return [_pt(cx - hw, cy - hh, color), _pt(cx + hw, cy - hh, color),
            _pt(cx + hw, cy + hh, color), _pt(cx - hw, cy + hh, color)]


def line(x1: float, y1: float, x2: float, y2: float, *,
         color=(1.0, 1.0, 1.0)) -> list:
    return [_pt(x1, y1, color), _pt(x2, y2, color)]


def star(*, cx: float = 0.0, cy: float = 0.0, r_outer: float = 0.9,
         r_inner: float = 0.4, points: int = 5,
         rotation: float = -math.pi / 2, color=(1.0, 1.0, 1.0)) -> list:
    """``points``-zackiger Stern: abwechselnd Außen-/Innenradius (2·points
    Stützpunkte)."""
    n = max(2, int(points))
    out = []
    for k in range(2 * n):
        rr = r_outer if k % 2 == 0 else r_inner
        a = rotation + math.pi * k / n
        out.append(_pt(cx + rr * math.cos(a), cy + rr * math.sin(a), color))
    return out


def rdp_simplify(points: list, epsilon: float = 0.02) -> list:
    """Ramer-Douglas-Peucker auf der (x, y)-Polylinie. Behält die Endpunkte und
    die Original-``FigurePoint``e (Farbe/Blank) der erhaltenen Stützpunkte.
    ``epsilon`` = Toleranz in normierten Einheiten (größer = stärker vereinfacht).
    Iterativ (kein Rekursionslimit bei langen Fingerzügen)."""
    n = len(points)
    if n < 3 or epsilon <= 0:
        return list(points)
    keep = [False] * n
    keep[0] = keep[n - 1] = True
    eps2 = epsilon * epsilon
    stack = [(0, n - 1)]
    while stack:
        i0, i1 = stack.pop()
        if i1 <= i0 + 1:
            continue
        ax, ay = points[i0].x, points[i0].y
        bx, by = points[i1].x, points[i1].y
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        best_d, best_i = -1.0, -1
        for i in range(i0 + 1, i1):
            px, py = points[i].x, points[i].y
            if seg2 <= 1e-12:                     # entartetes Segment (a==b)
                d = (px - ax) ** 2 + (py - ay) ** 2
            else:                                 # Abstand² zur Geraden a→b
                t = ((px - ax) * dx + (py - ay) * dy) / seg2
                qx, qy = ax + t * dx, ay + t * dy
                d = (px - qx) ** 2 + (py - qy) ** 2
            if d > best_d:
                best_d, best_i = d, i
        if best_i > 0 and best_d > eps2:
            keep[best_i] = True
            stack.append((i0, best_i))
            stack.append((best_i, i1))
    return [points[i] for i in range(n) if keep[i]]
