"""VIZ-56: MVR-Matrix <-> LightOS-Position und -Drehung (reine Funktionen).

**MVR** (DIN SPEC 15800): Millimeter, Z zeigt nach OBEN, rechtshaendig. Eine
Lage ist eine 4x3-Matrix ``{u1,u2,u3}{v1,v2,v3}{w1,w2,w3}{o1,o2,o3}``: ``u``,
``v``, ``w`` sind die Bilder der lokalen X-, Y- und Z-Achse (die SPALTEN der
Drehung), ``o`` ist der Ursprung. Verschachtelte Layer/Gruppen tragen eigene
Matrizen; die Weltlage ist das Produkt von aussen nach innen
(:func:`verkette`).

**LightOS** (``src/core/stage/scene_graph.py``, ``aim.py``): Meter, Y zeigt
nach OBEN, rechtshaendig wie Three.js. Positionen ``(x, y, z)`` sind
Weltwerte; Drehungen ``(rx, ry, rz)`` in GRAD, Euler-Reihenfolge XYZ
(``aim._mount_matrix``). Ein Geraet mit Drehung ``(0, 0, 0)`` strahlt nach
unten ``(0, -1, 0)``.

**Basiswechsel** MVR -> LightOS: ``B = [[1,0,0],[0,0,1],[0,-1,0]]`` (det = +1,
die Haendigkeit bleibt), also ``(x, y, z)_LightOS = (x, z, -y)_MVR / 1000``.
Die Drehung wird mit demselben Wechsel umgerechnet: ``R_L = B · R_MVR · Bᵀ``.
Ein GDTF-Geraet strahlt lokal nach ``-Z`` (GDTF: Ruhelage haengend, Strahl
nach unten) — ``B · (0,0,-1) = (0,-1,0)`` ist genau die LightOS-Ruhelage. Eine
Einheitsmatrix in der MVR heisst daher Drehung ``(0, 0, 0)`` in LightOS.

Das Publikum liegt in MVR-Dateien ueblicherweise bei ``-Y`` (vorn), in LightOS
damit bei ``+Z`` — die Seite, die die Live View unten zeichnet.
"""
from __future__ import annotations

import math
import re

from src.core.stage.aim import _euler_xyz_from_matrix, _mount_matrix

Matrix3 = tuple[tuple[float, float, float], ...]

#: MVR -> LightOS (Zeilen).
B = ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0))
#: LightOS -> MVR (= Bᵀ).
BT = ((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0))


class MvrMatrix:
    """Lage im MVR-Format: Drehung ``r`` (3x3, Zeilen; Spalten = u, v, w) und
    Ursprung ``o`` in Millimetern."""

    __slots__ = ("r", "o")

    def __init__(self, r: Matrix3 | None = None,
                 o: tuple[float, float, float] = (0.0, 0.0, 0.0)):
        self.r = tuple(tuple(float(x) for x in z) for z in
                       (r or ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))))
        self.o = tuple(float(x) for x in o)

    @classmethod
    def aus_uvwo(cls, u, v, w, o) -> "MvrMatrix":
        r = tuple((u[i], v[i], w[i]) for i in range(3))
        return cls(r, o)

    @property
    def u(self):
        return tuple(self.r[i][0] for i in range(3))

    @property
    def v(self):
        return tuple(self.r[i][1] for i in range(3))

    @property
    def w(self):
        return tuple(self.r[i][2] for i in range(3))

    def als_text(self) -> str:
        """Im Dateiformat ``{u}{v}{w}{o}`` (6 Nachkommastellen)."""
        def f(t):
            return "{" + ",".join(_zahl_text(x) for x in t) + "}"
        return f(self.u) + f(self.v) + f(self.w) + f(self.o)

    def __repr__(self) -> str:
        return f"MvrMatrix({self.als_text()})"


EINHEIT = MvrMatrix()

_ZAHL = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_GRUPPE = re.compile(r"\{\s*(" + _ZAHL + r")\s*[,;\s]\s*(" + _ZAHL + r")\s*[,;\s]\s*("
                     + _ZAHL + r")\s*\}")


def lies_matrix(text: str) -> MvrMatrix | None:
    """``"{1,0,0}{0,1,0}{0,0,1}{100,200,3000}"`` -> :class:`MvrMatrix`.
    ``None`` bei unlesbarem Text oder nicht endlichen Zahlen."""
    gruppen = _GRUPPE.findall(text or "")
    if len(gruppen) != 4:
        return None
    werte = [tuple(float(x) for x in g) for g in gruppen]
    if not all(math.isfinite(x) for g in werte for x in g):
        return None
    return MvrMatrix.aus_uvwo(*werte)


def _zahl_text(x: float) -> str:
    t = f"{x:.6f}".rstrip("0").rstrip(".")
    return "0" if t in ("", "-0") else t


def _mul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3))
                 for i in range(3))


def _mv(a, v):
    return tuple(sum(a[i][k] * v[k] for k in range(3)) for i in range(3))


def verkette(aussen: MvrMatrix, innen: MvrMatrix) -> MvrMatrix:
    """Lage eines Kindes in der Welt: ``aussen · innen``."""
    r = _mul(aussen.r, innen.r)
    d = _mv(aussen.r, innen.o)
    return MvrMatrix(r, tuple(aussen.o[i] + d[i] for i in range(3)))


def _orthonormal(r) -> Matrix3:
    """Skalierung und kleine Schiefe aus einer Drehung nehmen (Gram-Schmidt
    der Spalten u, v; w = u x v). Entartete Matrix -> Einheit."""
    u = [r[i][0] for i in range(3)]
    v = [r[i][1] for i in range(3)]
    nu = math.sqrt(sum(x * x for x in u))
    if nu < 1e-12:
        return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    u = [x / nu for x in u]
    d = sum(u[i] * v[i] for i in range(3))
    v = [v[i] - d * u[i] for i in range(3)]
    nv = math.sqrt(sum(x * x for x in v))
    if nv < 1e-12:
        return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    v = [x / nv for x in v]
    w = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
         u[0] * v[1] - u[1] * v[0]]
    return tuple((u[i], v[i], w[i]) for i in range(3))


def _rund(x: float, stellen: int) -> float:
    y = round(x, stellen)
    return 0.0 if y == 0 else y


def mvr_zu_lightos(m: MvrMatrix) -> tuple[tuple[float, float, float],
                                           tuple[float, float, float]]:
    """MVR-Weltmatrix -> ``((x, y, z) in m, (rx, ry, rz) in Grad)``."""
    ox, oy, oz = m.o
    pos = (_rund(ox / 1000.0, 6), _rund(oz / 1000.0, 6), _rund(-oy / 1000.0, 6))
    rl = _mul(_mul(B, _orthonormal(m.r)), BT)
    rot = tuple(_rund(w, 4) for w in _euler_xyz_from_matrix(rl))
    # -180 und 180 sind dieselbe Drehung; eine Schreibweise.
    rot = tuple(180.0 if abs(w + 180.0) < 1e-9 else w for w in rot)
    return pos, rot


def lightos_zu_mvr(pos, rot) -> MvrMatrix:
    """Umkehrung von :func:`mvr_zu_lightos` (fuer den spaeteren Export)."""
    x, y, z = (float(w) for w in pos)
    rl = _mount_matrix(*(float(w) for w in rot))
    rm = _mul(_mul(BT, rl), B)
    return MvrMatrix(rm, (x * 1000.0, -z * 1000.0, y * 1000.0))


def strahl_richtung(rot) -> tuple[float, float, float]:
    """Wohin der Ruhe-Strahl ``(0,-1,0)`` eines Geraets mit Drehung ``rot``
    in LightOS zeigt (Welt) — fuer Tests und Plausibilitaet."""
    r = _mount_matrix(*(float(w) for w in rot))
    return tuple(-r[i][1] for i in range(3))
