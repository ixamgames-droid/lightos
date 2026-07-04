"""Tests für die Geometrie-Generatoren + RDP-Vereinfachung (LAS-14).

Reine Mathematik, kein Qt.
"""
from __future__ import annotations
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.laser.figure import FigurePoint
from src.core.laser import figure_ops as fo


# ------------------------------------------------------------- Generatoren --

def test_regular_polygon_count_and_radius():
    pts = fo.regular_polygon(6, r=0.8)
    assert len(pts) == 6
    for p in pts:
        assert abs(math.hypot(p.x, p.y) - 0.8) < 1e-6


def test_regular_polygon_first_vertex_on_vertical_axis():
    # Default rotation=-pi/2 → erster Punkt auf der vertikalen Achse unten
    # (y≈-r); exakt wie die alte _regular_polygon → Builtins bleiben stabil.
    p = fo.regular_polygon(4, r=1.0)[0]
    assert abs(p.x) < 1e-6
    assert abs(p.y + 1.0) < 1e-6


def test_regular_polygon_min_three_sides():
    assert len(fo.regular_polygon(1)) == 3       # auf 3 hochgezogen


def test_circle_segments():
    assert len(fo.circle(segments=32)) == 32


def test_ellipse_axes():
    pts = fo.ellipse(rx=0.9, ry=0.3, segments=40)
    assert len(pts) == 40
    assert max(abs(p.x) for p in pts) > max(abs(p.y) for p in pts)


def test_rectangle_corners():
    pts = fo.rectangle(w=1.0, h=0.5)
    assert len(pts) == 4
    xs = sorted({round(p.x, 3) for p in pts})
    ys = sorted({round(p.y, 3) for p in pts})
    assert xs == [-0.5, 0.5]
    assert ys == [-0.25, 0.25]


def test_line_two_points():
    pts = fo.line(-0.5, 0.1, 0.5, 0.1)
    assert len(pts) == 2
    assert all(abs(p.y - 0.1) < 1e-9 for p in pts)


def test_star_point_count_and_radii():
    pts = fo.star(points=5, r_outer=0.9, r_inner=0.3)
    assert len(pts) == 10                        # 2 * points
    radii = [round(math.hypot(p.x, p.y), 3) for p in pts]
    assert max(radii) == 0.9 and min(radii) == 0.3


def test_clamp_keeps_in_field():
    # Radius > 1 wird auf −1..+1 geklemmt.
    pts = fo.regular_polygon(4, r=2.0)
    assert all(-1.0 <= p.x <= 1.0 and -1.0 <= p.y <= 1.0 for p in pts)


def test_color_applied():
    pts = fo.circle(segments=8, color=(0.2, 0.4, 0.6))
    assert all((p.r, p.g, p.b) == (0.2, 0.4, 0.6) for p in pts)


# --------------------------------------------------------------------- RDP --

def test_rdp_collapses_collinear():
    # 10 kollineare Punkte → nur die beiden Endpunkte bleiben.
    pts = [FigurePoint(x=t / 9.0, y=0.0) for t in range(10)]
    out = fo.rdp_simplify(pts, epsilon=0.01)
    assert len(out) == 2
    assert out[0].x == pts[0].x and out[-1].x == pts[-1].x


def test_rdp_keeps_significant_corner():
    # Ecke in der Mitte bleibt erhalten (Dreiecks-Knick).
    pts = [FigurePoint(-1.0, 0.0), FigurePoint(0.0, 1.0), FigurePoint(1.0, 0.0)]
    out = fo.rdp_simplify(pts, epsilon=0.05)
    assert len(out) == 3


def test_rdp_preserves_endpoints_and_payload():
    pts = [FigurePoint(0.0, 0.0, r=0.1, g=0.2, b=0.3),
           FigurePoint(0.5, 0.001), FigurePoint(1.0, 0.0, blank=True)]
    out = fo.rdp_simplify(pts, epsilon=0.1)
    assert len(out) == 2                         # Mittelpunkt fällt weg
    assert (out[0].r, out[0].g, out[0].b) == (0.1, 0.2, 0.3)
    assert out[-1].blank is True


def test_rdp_noop_for_short_or_zero_epsilon():
    two = [FigurePoint(0, 0), FigurePoint(1, 1)]
    assert fo.rdp_simplify(two, 0.01) == two
    many = [FigurePoint(t / 9.0, 0.0) for t in range(10)]
    assert len(fo.rdp_simplify(many, 0.0)) == 10   # epsilon<=0 → unverändert


def test_rdp_handles_degenerate_segment():
    # Erster == letzter Punkt (geschlossene Schleife als offene Liste): darf
    # nicht crashen; ein weit entfernter Punkt bleibt.
    pts = [FigurePoint(0.0, 0.0), FigurePoint(0.9, 0.9), FigurePoint(0.0, 0.0)]
    out = fo.rdp_simplify(pts, epsilon=0.05)
    assert len(out) == 3


# ---------------------------------------------------------- Integration ----

def test_builtin_figures_use_ops_and_stay_stable():
    from src.core.laser.figure import builtin_figures
    figs = {f.name: f for f in builtin_figures()}
    assert set(figs) == {"Kreis", "Dreieck", "Quadrat", "Linie"}
    assert len(figs["Dreieck"].points) == 3
    assert len(figs["Kreis"].points) == 24
    assert figs["Linie"].closed is False
    assert all(abs(p.y) < 1e-9 for p in figs["Linie"].points)
