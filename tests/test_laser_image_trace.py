"""LAS-19: Bild-Gitter → Laser-Figur (Komponenten + Moore-Tracing + Figur).

Reine Logik, kein Qt — validiert vor allem, dass das Kontur-Tracing korrekt ist.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.laser.image_trace import (connected_components, trace_component,
                                        image_grid_to_figure)


def _solid(n):
    return [[1] * n for _ in range(n)]


def _border_cells(r0, c0, n):
    return {(r, c) for r in range(r0, r0 + n) for c in range(c0, c0 + n)
            if r in (r0, r0 + n - 1) or c in (c0, c0 + n - 1)}


# ------------------------------------------------------- Komponenten --------

def test_components_four_corners():
    grid = [[1, 0, 1], [0, 0, 0], [1, 0, 1]]
    assert len(connected_components(grid)) == 4


def test_components_one_blob():
    assert len(connected_components(_solid(5))) == 1


def test_components_empty():
    assert connected_components([[0, 0], [0, 0]]) == []


# ------------------------------------------------------- Moore-Tracing ------

def test_trace_square_perimeter_exact():
    # 4x4 Vollquadrat → Rand = 12 Zellen, alle auf dem Rand, keine doppelt.
    comp = {(r, c) for r in range(4) for c in range(4)}
    b = trace_component(comp)
    assert len(b) == 12
    assert set(b) == _border_cells(0, 0, 4)
    assert len(set(b)) == len(b)            # keine Doppel


def test_trace_single_pixel():
    assert trace_component({(2, 2)}) == [(2, 2)]


def test_trace_closed_loop_starts_at_min():
    comp = {(r, c) for r in range(5) for c in range(5)}
    b = trace_component(comp)
    assert b[0] == (0, 0)                    # oberste-linkeste Startzelle
    # benachbarte Randzellen sind je 8er-Nachbarn (geschlossener Weg)
    for (r1, c1), (r2, c2) in zip(b, b[1:]):
        assert max(abs(r1 - r2), abs(c1 - c2)) == 1


# ------------------------------------------------------- Figur --------------

def test_square_becomes_few_corners():
    fig = image_grid_to_figure(_solid(11), epsilon=0.05)
    assert 4 <= len(fig.points) <= 9        # RDP: Quadrat ~4 Ecken
    # In −1..+1 und geklemmt.
    assert all(-1.0 <= p.x <= 1.0 and -1.0 <= p.y <= 1.0 for p in fig.points)


def test_two_blobs_get_blank_jump():
    # Zwei getrennte 4x4-Quadrate nebeneinander.
    rows = 4
    grid = [[0] * 11 for _ in range(rows)]
    for r in range(rows):
        for c in range(4):
            grid[r][c] = 1
        for c in range(7, 11):
            grid[r][c] = 1
    fig = image_grid_to_figure(grid, epsilon=0.05)
    assert any(p.blank for p in fig.points)  # dunkler Sprung dazwischen
    assert fig.closed is False               # Composite offen


def test_min_area_filters_noise():
    # Ein Einzelpixel + ein großes Quadrat → nur das Quadrat.
    grid = [[0] * 12 for _ in range(12)]
    grid[0][11] = 1                          # Rauschen (1 Pixel)
    for r in range(2, 10):
        for c in range(2, 10):
            grid[r][c] = 1
    fig = image_grid_to_figure(grid, epsilon=0.05, min_area=6)
    assert len(fig.points) >= 4
    assert not any(p.blank for p in fig.points)   # nur EINE Kontur, kein Sprung


def test_empty_grid_is_empty_figure():
    assert image_grid_to_figure([]).points == []
    assert image_grid_to_figure([[0, 0], [0, 0]]).points == []


def test_y_axis_up():
    # Oberste Bildzeile (r=0) muss in +y (oben) landen.
    grid = [[1, 1, 1], [0, 0, 0], [0, 0, 0]]
    fig = image_grid_to_figure(grid, epsilon=0.01, min_area=1)
    assert max(p.y for p in fig.points) > 0
