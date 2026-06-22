"""Gemeinsame Umrechnung zwischen Live-View-2D-Pixelkoordinaten und der
3D-Welt (Meter, Top-Down).

Damit eine in der **Live View** platzierte Position automatisch im **3D-
Visualizer** landet (und umgekehrt), nutzen beide Ansichten denselben Bezug.
Die Live View ist die Quelle der Top-Down-X/Z; die Hoehe (Y) und die Rotation
sind 3D-eigene Zusatzdaten.

Bezug bewusst kompatibel zur historischen Migration in
``live_view._load_positions`` gewaehlt::

    px = x3d * PX_PER_M + ORIGIN_PX[0]
    py = z3d * PX_PER_M + ORIGIN_PX[1]

so dass bestehende Shows (mit bereits gespeicherten ``live_view_positions``)
ohne Versatz uebernommen werden.
"""
from __future__ import annotations

# Pixel pro Meter (Live-View-Weltpixel <-> 3D-Meter).
PX_PER_M: float = 20.0
# Pixel-Position, die dem 3D-Ursprung (0, 0) entspricht (Buehnenmitte/-front).
ORIGIN_PX: tuple[float, float] = (300.0, 200.0)


def live_to_world3d(px: float, py: float) -> tuple[float, float]:
    """Live-View-Pixel (px, py) -> 3D-Top-Down (x, z) in Metern."""
    x = (float(px) - ORIGIN_PX[0]) / PX_PER_M
    z = (float(py) - ORIGIN_PX[1]) / PX_PER_M
    return (x, z)


def world3d_to_live(x: float, z: float) -> tuple[float, float]:
    """3D-Top-Down (x, z) in Metern -> Live-View-Pixel (px, py)."""
    px = float(x) * PX_PER_M + ORIGIN_PX[0]
    py = float(z) * PX_PER_M + ORIGIN_PX[1]
    return (px, py)


# Typ-abhaengige Default-Montagehoehe (Y) fuer den Auto-Patch ins 3D. Die Live
# View kennt keine Hoehe — Moving Heads/Scanner haengen ueblicherweise an einer
# Trasse, alles andere steht eher bodennah.
_DEFAULT_Y: dict[str, float] = {
    "moving_head": 6.0,
    "scanner": 6.0,
}
_DEFAULT_Y_FALLBACK: float = 0.6


def default_height_for(fixture_type: str | None) -> float:
    """Sinnvolle 3D-Default-Hoehe (Meter) fuer einen Fixture-Typ."""
    return _DEFAULT_Y.get((fixture_type or "").lower(), _DEFAULT_Y_FALLBACK)


def normalize_rotation(val) -> tuple[float, float, float]:
    """Fixture-Ausrichtung als (rx, ry, rz) in Grad zurueckgeben.

    Multi-Achsen-Rotation: rx = Kippen (Pitch, Boden->Decke), ry = Drehen um die
    Hochachse (Yaw, frueher die EINZIGE Achse), rz = Roll. Akzeptiert beide
    Formate, damit alte Shows weiter laden:
      * ``None``                       -> (0, 0, 0)
      * einzelner Float/Int (Alt-Show) -> (0, val, 0)   # nur Y-Drehung
      * Sequenz mit >=3 Werten         -> (val[0], val[1], val[2])
      * Sequenz mit genau 1 Wert       -> (0, val[0], 0)
    """
    if val is None:
        return (0.0, 0.0, 0.0)
    if isinstance(val, (int, float)):
        return (0.0, float(val), 0.0)
    try:
        if len(val) >= 3:
            return (float(val[0]), float(val[1]), float(val[2]))
        if len(val) == 1:
            return (0.0, float(val[0]), 0.0)
    except Exception:
        pass
    return (0.0, 0.0, 0.0)
