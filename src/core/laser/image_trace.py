"""Bild → Laser-Figur (LAS-19): ein Schwarz-Weiß-Raster in Vektor-Konturen
umwandeln, damit man ein Bild importieren und (auf Netz-/ILDA-Lasern) ausgeben
kann.

Rein und ohne Qt — arbeitet auf einem 2D-Gitter aus 0/1 (1 = Vordergrund). Die
Qt-Anbindung (QImage → Gitter) liegt im UI-Layer. Pipeline:

  Gitter → zusammenhängende Komponenten (4er-Nachbarschaft) → äußere Kontur je
  Komponente (Moore-Nachbar-Tracing) → normiert −1..+1 (+y oben) → RDP-vereinfacht
  → zu einer :class:`LaserFigure` zusammengesetzt (dunkle Blank-Sprünge zwischen
  den Sub-Konturen).

Bewusst v1: nur ÄUSSERE Konturen (keine Löcher), kein Anti-Aliasing — für einen
Laser (Linienzeichnung) ist die Silhouette/Outline das Sinnvolle.
"""
from __future__ import annotations

from .figure import FigurePoint, LaserFigure
from .figure_ops import rdp_simplify

# 8 Nachbarn im Uhrzeigersinn (Zeile, Spalte).
_NB = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]


def connected_components(grid: list) -> list:
    """4er-Nachbarschafts-Komponenten der Vordergrundzellen (truthy) als Liste
    von Zell-Mengen ``{(r, c), …}``. Iterativ (kein Rekursionslimit)."""
    if not grid:
        return []
    rows, cols = len(grid), len(grid[0])
    seen = [[False] * cols for _ in range(rows)]
    comps = []
    for r0 in range(rows):
        for c0 in range(cols):
            if not grid[r0][c0] or seen[r0][c0]:
                continue
            comp = set()
            stack = [(r0, c0)]
            seen[r0][c0] = True
            while stack:
                r, c = stack.pop()
                comp.add((r, c))
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = r + dr, c + dc
                    if (0 <= nr < rows and 0 <= nc < cols
                            and grid[nr][nc] and not seen[nr][nc]):
                        seen[nr][nc] = True
                        stack.append((nr, nc))
            comps.append(comp)
    return comps


def trace_component(comp: set) -> list:
    """Äußere Kontur einer Komponente per Moore-Nachbar-Tracing. Ergebnis:
    geordnete Zellen ``[(r, c), …]`` im Uhrzeigersinn (geschlossene Schleife)."""
    if not comp:
        return []
    start = min(comp)                       # oberste, dann linkeste Zelle
    if len(comp) == 1:
        return [start]

    def is_fg(r, c):
        return (r, c) in comp

    p = start
    b_off = (0, -1)                          # betreten von Westen (dort Hintergrund)
    boundary = [start]
    guard = 0
    limit = 8 * len(comp) + 16               # sichere Obergrenze
    while guard < limit:
        guard += 1
        bi = _NB.index(b_off)
        nxt = None
        for k in range(1, 9):               # im Uhrzeigersinn nach dem Backtrack
            dr, dc = _NB[(bi + k) % 8]
            if is_fg(p[0] + dr, p[1] + dc):
                nxt = (p[0] + dr, p[1] + dc)
                break
        if nxt is None:
            break                            # isolierte Zelle
        b_off = (p[0] - nxt[0], p[1] - nxt[1])
        p = nxt
        if p == start:
            break                            # Schleife geschlossen
        boundary.append(p)
    return boundary


def _grid_dims(grid: list) -> tuple:
    return (len(grid), len(grid[0]) if grid else 0)


def image_grid_to_figure(grid: list, *, name: str = "Bild",
                         epsilon: float = 0.02, min_area: int = 6,
                         color=(1.0, 1.0, 1.0)) -> LaserFigure:
    """0/1-Gitter → :class:`LaserFigure`. Kleine Komponenten (< ``min_area``
    Zellen) werden als Rauschen verworfen. Mehrere Konturen werden mit dunklen
    Blank-Sprüngen aneinandergehängt; jede Sub-Kontur kehrt sichtbar zum Start
    zurück (geschlossen)."""
    rows, cols = _grid_dims(grid)
    if rows == 0 or cols == 0:
        return LaserFigure(name=name, points=[], closed=False)
    span = float(max(rows, cols, 1))
    r0 = (rows - 1) / 2.0
    c0 = (cols - 1) / 2.0
    cr, cg, cb = color

    def norm(r, c):
        # Bildkoordinaten → −1..+1, zentriert, +y oben (Zeile invertiert).
        x = (c - c0) / (span / 2.0)
        y = -(r - r0) / (span / 2.0)
        x = max(-1.0, min(1.0, x))
        y = max(-1.0, min(1.0, y))
        return x, y

    out: list = []
    for comp in connected_components(grid):
        if len(comp) < min_area:
            continue
        cells = trace_component(comp)
        if len(cells) < 2:
            continue
        pts = [FigurePoint(*norm(r, c), r=cr, g=cg, b=cb) for r, c in cells]
        pts = rdp_simplify(pts, epsilon)
        if len(pts) < 2:
            continue
        if out:                              # dunkler Sprung zur nächsten Kontur
            jump = FigurePoint(pts[0].x, pts[0].y, r=cr, g=cg, b=cb, blank=True)
            out.append(jump)
            out.extend(FigurePoint(p.x, p.y, r=cr, g=cg, b=cb) for p in pts[1:])
            out.append(FigurePoint(pts[0].x, pts[0].y, r=cr, g=cg, b=cb))
        else:
            out.extend(pts)
            out.append(FigurePoint(pts[0].x, pts[0].y, r=cr, g=cg, b=cb))
    # Composite ist offen (Sub-Konturen schließen sich selbst); Einzelkontur zu.
    return LaserFigure(name=name, points=out, closed=False)
