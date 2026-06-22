"""Inverse-Kinematik: Moving-Head auf einen 3D-Zielpunkt ausrichten.

Gegeben die Welt-Position eines Moving Heads, seine Montage-Ausrichtung (die
Multi-Achsen-Rotation ``visualizer_rotations`` in Grad, Euler XYZ wie Three.js)
und einen Welt-Zielpunkt, berechnet :func:`aim_pan_tilt` die Pan-/Tilt-DMX-Werte
(0..255), sodass der Strahl auf das Ziel zeigt. **Jeder Kopf an einer anderen
Position bekommt eigene Werte** — genau das, was fuer „beide Moving Heads auf den
gleichen Punkt" gebraucht wird.

Konvention (deckungsgleich mit dem 3D-Visualizer ``stage_scene.html``):

* Welt: ``x`` rechts, ``y`` hoch, ``z`` vorne/hinten (Meter).
* Strahl-Ruhelage (pan=tilt=128): senkrecht nach unten ``(0, -1, 0)``.
* ``panRad  = (pan  - 128) / 128 * pi``      (Pan  ~ 360 Grad, Drehung um Y)
* ``tiltRad = (tilt - 128) / 128 * pi/2``    (Tilt ~ 180 Grad, Kippen um lokale X)
* ``strahl_lokal = Ry(panRad) * Rx(tiltRad) * (0,-1,0)
                 = (-sin t * sin p, -cos t, -sin t * cos p)``

Die Montage-Rotation ``R`` (Euler XYZ, Grad) wird zuerst entfernt:
``d_lokal = R^T * d_welt`` (R orthonormal). Damit deckt der Solver die GANZE
untere Halbkugel ab; Ziele oberhalb der Kopf-Hoehe werden auf „horizontal"
geklemmt (Grenze des Visualizer-Modells — echte 270-Grad-Tilt-Geraete koennen
weiter, das braucht aber Kalibrierung pro Fixture, siehe TODO im Projekt-Memo).
"""
from __future__ import annotations

import math


def _mount_matrix(rx_deg: float, ry_deg: float, rz_deg: float):
    """Rotationsmatrix R (lokal->welt) fuer Euler-Order 'XYZ' wie in Three.js.

    Rueckgabe als 3 Zeilen-Tupel (row-major), sodass ``welt = R * lokal``.
    """
    x = math.radians(rx_deg); y = math.radians(ry_deg); z = math.radians(rz_deg)
    a, b = math.cos(x), math.sin(x)
    c, d = math.cos(y), math.sin(y)
    e, f = math.cos(z), math.sin(z)
    ae, af, be, bf = a * e, a * f, b * e, b * f
    # exakt Three.js Matrix4.makeRotationFromEuler, order 'XYZ' (column-major te
    # dort -> hier als Zeilen der 3x3):
    r00 = c * e;          r01 = -c * f;         r02 = d
    r10 = af + be * d;    r11 = ae - bf * d;    r12 = -b * c
    r20 = bf - ae * d;    r21 = be + af * d;    r22 = a * c
    return ((r00, r01, r02), (r10, r11, r12), (r20, r21, r22))


def _mat_transpose_mul(R, v):
    """R^T * v (v aus Welt in den lokalen Frame)."""
    vx, vy, vz = v
    # Spalten von R sind Zeilen von R^T:
    lx = R[0][0] * vx + R[1][0] * vy + R[2][0] * vz
    ly = R[0][1] * vx + R[1][1] * vy + R[2][1] * vz
    lz = R[0][2] * vx + R[1][2] * vy + R[2][2] * vz
    return (lx, ly, lz)


def _clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def aim_pan_tilt(
    pos,
    target,
    rot_deg=(0.0, 0.0, 0.0),
    pan_range_deg: float = 360.0,
    tilt_range_deg: float = 180.0,
    pan_zero_dmx: float = 128.0,
    tilt_zero_dmx: float = 128.0,
    *,
    invert_pan: bool = False,
    invert_tilt: bool = False,
    swap_pan_tilt: bool = False,
):
    """Pan/Tilt-DMX (0..255) berechnen, damit der Strahl von ``pos`` (mit Montage-
    Ausrichtung ``rot_deg`` = (rx,ry,rz) Grad) auf ``target`` zeigt.

    ``pan_range_deg``/``tilt_range_deg`` = physischer Bewegungsbereich des Geraets
    (z.B. 540/270), ``*_zero_dmx`` = DMX-Wert der Mitte. Grad->DMX nutzt genau
    diesen Bereich, damit DMX UND 3D-Visualizer-Beam zusammenpassen. Defaults
    360/180/128 entsprechen der bisherigen (generischen) Abbildung.

    ``pos`` / ``target``: (x, y, z) in Metern. Gibt ``(pan, tilt)`` als ints zurueck.
    Bei ``pos == target`` (kein Richtungsvektor) -> Ruhelage (Nullpunkt).
    """
    dx = float(target[0]) - float(pos[0])
    dy = float(target[1]) - float(pos[1])
    dz = float(target[2]) - float(pos[2])
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-9:
        return (int(round(pan_zero_dmx)), int(round(tilt_zero_dmx)))
    dw = (dx / length, dy / length, dz / length)

    # Montage-Rotation entfernen -> Richtung im lokalen Kopf-Frame
    R = _mount_matrix(rot_deg[0], rot_deg[1], rot_deg[2])
    lx, ly, lz = _mat_transpose_mul(R, dw)

    # Tilt: theta = Neigung gegen Nadir (gerade-runter) in [0, pi]; groessere
    # Bereiche (z.B. 270 Grad) koennen ueber die Horizontale hinaus nach oben.
    theta = math.acos(_clamp(-ly, -1.0, 1.0))

    sin_t = math.sin(theta)
    if sin_t < 1e-6:
        # Strahl ~ senkrecht nach unten -> Pan unbestimmt, Ruhelage behalten
        pan_rad = 0.0
    else:
        # -sin t * sin p = lx ; -sin t * cos p = lz  ->  p = atan2(-lx, -lz)
        pan_rad = math.atan2(-lx, -lz)

    # Grad -> DMX ueber den physischen Bereich (gleiche Abbildung wie Visualizer):
    #   dmx = zero + winkel / (bereich/2) * 128
    half_pan = max(1.0, pan_range_deg / 2.0)
    half_tilt = max(1.0, tilt_range_deg / 2.0)
    pan = pan_zero_dmx + (math.degrees(pan_rad) / half_pan) * 128.0
    tilt = tilt_zero_dmx + (math.degrees(theta) / half_tilt) * 128.0

    if swap_pan_tilt:
        pan, tilt = tilt, pan
    if invert_pan:
        pan = 255.0 - pan
    if invert_tilt:
        tilt = 255.0 - tilt

    pi = int(round(_clamp(pan, 0.0, 255.0)))
    ti = int(round(_clamp(tilt, 0.0, 255.0)))
    return (pi, ti)


# ── Statische Fixtures (PAR etc.): die ganze Montage-Ausrichtung drehen ──────
# Ein statischer Strahler hat kein Pan/Tilt — um ihn auf einen Punkt zu richten,
# drehen wir die Fixture-Gruppe selbst (visualizer_rotations). Anders als beim
# Moving-Head-Visual KANN ein statischer Strahler dabei auch nach oben zeigen
# (z.B. Boden-PAR an die Decke).

def _rx(a):
    c, s = math.cos(a), math.sin(a)
    return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))


def _ry(a):
    c, s = math.cos(a), math.sin(a)
    return ((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c))


def _matmul(A, B):
    return tuple(
        tuple(sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3))
        for i in range(3)
    )


def _euler_xyz_from_matrix(R):
    """Euler-Winkel (rx, ry, rz) in GRAD aus Rotationsmatrix R extrahieren —
    Konvention Three.js Order 'XYZ' (inverse zu :func:`_mount_matrix`)."""
    m02 = _clamp(R[0][2], -1.0, 1.0)
    ry = math.asin(m02)
    if abs(R[0][2]) < 0.9999999:
        rx = math.atan2(-R[1][2], R[2][2])
        rz = math.atan2(-R[0][1], R[0][0])
    else:
        rx = math.atan2(R[2][1], R[1][1])
        rz = 0.0
    return (math.degrees(rx), math.degrees(ry), math.degrees(rz))


def aim_orientation(pos, target):
    """Montage-Ausrichtung (rx, ry, rz) in GRAD (Euler XYZ) berechnen, damit der
    nach unten zeigende Ruhe-Strahl ``(0,-1,0)`` eines statischen Fixtures von
    ``pos`` auf ``target`` zeigt. Volle Kugel (auch nach oben)."""
    dx = float(target[0]) - float(pos[0])
    dy = float(target[1]) - float(pos[1])
    dz = float(target[2]) - float(pos[2])
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-9:
        return (0.0, 0.0, 0.0)
    dx, dy, dz = dx / length, dy / length, dz / length
    theta = math.acos(_clamp(-dy, -1.0, 1.0))   # [0, pi] — volle Neigung
    if math.sin(theta) < 1e-6:
        p = 0.0
    else:
        p = math.atan2(-dx, -dz)
    R = _matmul(_ry(p), _rx(theta))             # Yaw nach Pitch (auf Ruhe-Strahl)
    return _euler_xyz_from_matrix(R)


# ── Formen-Nachfahren: eine Form auf einer Zielflaeche abtasten ──────────────
# Moving Heads sollen eine Form (Kreis/Linie/Rechteck) auf einer Wand/Flaeche
# "nachfahren", obwohl sie an festen Plaetzen stehen — jeder Kopf bekommt pro
# Form-Punkt sein EIGENES Pan/Tilt (via aim_pan_tilt). Die Form liegt in einer
# Ebene (Mittelpunkt + Normale); Masse in Metern.

def _vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _vscale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _vcross(a, b):
    return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0])


def _vnorm(a):
    L = math.sqrt(a[0]*a[0] + a[1]*a[1] + a[2]*a[2])
    if L < 1e-9:
        return (0.0, 0.0, 0.0)
    return (a[0]/L, a[1]/L, a[2]/L)


def plane_basis(normal):
    """Zwei orthonormale In-Ebenen-Achsen (u, v) zu einer Flaechennormale.
    u liegt moeglichst horizontal (fuer Waende = links/rechts), v = n x u."""
    n = _vnorm(normal)
    if abs(n[1]) < 0.9:
        ref = (0.0, 1.0, 0.0)        # Welt-Hoch -> u wird horizontal
    else:
        ref = (1.0, 0.0, 0.0)        # bei Boden/Decke: u entlang X
    u = _vnorm(_vcross(ref, n))
    v = _vnorm(_vcross(n, u))
    return u, v


def circle_points(center, radius, normal, count=36, phase=0.0):
    """``count`` Punkte eines Kreises (Radius m) in der Ebene durch ``center``
    mit Normale ``normal``. ``phase`` (rad) dreht den Startpunkt."""
    u, v = plane_basis(normal)
    pts = []
    n = max(1, int(count))
    for i in range(n):
        a = phase + 2.0 * math.pi * i / n
        c, s = math.cos(a), math.sin(a)
        off = _vadd(_vscale(u, radius * c), _vscale(v, radius * s))
        pts.append(_vadd(center, off))
    return pts


def line_points(p0, p1, count=24):
    """``count`` Punkte gleichmaessig auf der Strecke p0->p1 (3D, Meter)."""
    n = max(2, int(count))
    return [
        (p0[0] + (p1[0]-p0[0]) * i/(n-1),
         p0[1] + (p1[1]-p0[1]) * i/(n-1),
         p0[2] + (p1[2]-p0[2]) * i/(n-1))
        for i in range(n)
    ]


def rect_points(center, width, height, normal, per_side=8):
    """Rechteck-Umriss (Breite/Hoehe m) in der Ebene um ``center``."""
    u, v = plane_basis(normal)
    hw, hh = width / 2.0, height / 2.0
    corners = [
        _vadd(center, _vadd(_vscale(u, -hw), _vscale(v, -hh))),
        _vadd(center, _vadd(_vscale(u,  hw), _vscale(v, -hh))),
        _vadd(center, _vadd(_vscale(u,  hw), _vscale(v,  hh))),
        _vadd(center, _vadd(_vscale(u, -hw), _vscale(v,  hh))),
    ]
    pts = []
    for i in range(4):
        seg = line_points(corners[i], corners[(i + 1) % 4], per_side + 1)
        pts.extend(seg[:-1])   # letzten Punkt (= naechster Start) auslassen
    return pts


def trace_pan_tilt(pos, points, rot_deg=(0.0, 0.0, 0.0),
                   pan_range_deg=360.0, tilt_range_deg=180.0,
                   pan_zero_dmx=128.0, tilt_zero_dmx=128.0,
                   invert_pan=False, invert_tilt=False, swap_pan_tilt=False):
    """Pan/Tilt-DMX-Folge fuer EINEN Kopf an ``pos``, der ``points`` der Reihe
    nach anpeilt. Rueckgabe: Liste ``[(pan, tilt), ...]``."""
    out = []
    for p in points:
        out.append(aim_pan_tilt(
            pos, p, rot_deg,
            pan_range_deg=pan_range_deg, tilt_range_deg=tilt_range_deg,
            pan_zero_dmx=pan_zero_dmx, tilt_zero_dmx=tilt_zero_dmx,
            invert_pan=invert_pan, invert_tilt=invert_tilt, swap_pan_tilt=swap_pan_tilt,
        ))
    return out
