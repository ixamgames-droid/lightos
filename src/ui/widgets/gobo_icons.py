"""Programmatisch gezeichnete Gobo-Vorschau-Icons (wiederverwendbar).

Zweck: Gobo-Kacheln im Programmer (und spaeter VC/anderen Fixtures) zeigen
nicht nur Text, sondern eine kleine grafische Vorschau des Gobo-Musters.

Die Zuordnung Muster ↔ Gobo ist **datengetrieben**: aus dem Namen der
``ChannelRange`` (z. B. "Gobo 6 (Spirale)") wird per Schluesselwort das
Muster erkannt. Unbekannte Namen bekommen ein neutrales nummeriertes Icon —
es wird kein Muster geraten. Dadurch koennen andere Fixtures dieselben Icons
nutzen, indem sie ihre Range-Namen entsprechend beschreiben.

Alle Icons werden mit QPainter auf transparente Pixmaps gezeichnet (keine
externen Bilddateien, wie mini_icons.py) und nach (style, size, shake, nummer)
gecacht. Optik: helles Muster auf dunkler Kreisflaeche ("Blick in den Beam").
"""
from __future__ import annotations

import math
import re

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath, QFont

_BG = QColor("#1b212a")      # dunkle Kreisflaeche
_FG = QColor("#f2ead2")      # warmweisses Gobo-Muster
_RIM = QColor("#46505c")     # Kreisrand
_SHAKE = QColor("#ffb347")   # Shake-Marker

# Muster-Stile in der Reihenfolge der ZQ02001-Gobos 1..7 (Doku-Referenz).
STYLES = ("ring_slits", "ovals", "circle_of_circles", "tetris",
          "dots", "spiral", "zebra")

# Schluesselwort → Stil (deutsch + englisch, bewusst eindeutig gehalten).
_KEYWORDS = [
    ("ring_slits",        ("ring", "spalte", "spalten", "slit")),
    ("ovals",             ("oval",)),
    ("circle_of_circles", ("kreis aus", "kreisen", "circle of")),
    ("tetris",            ("tetris",)),
    ("dots",              ("punkte", "dots")),
    ("spiral",            ("spirale", "spiral")),
    ("zebra",             ("zebra", "streifen", "stripes")),
    ("open",              ("kein gobo", "offen", "open", "leer")),
]

_cache: dict[tuple, QPixmap] = {}


def gobo_style_for(name: str) -> str:
    """Erkennt das Muster aus einem Range-Namen. "" = unbekannt (neutral)."""
    n = (name or "").lower()
    for style, words in _KEYWORDS:
        if any(w in n for w in words):
            return style
    return ""


def gobo_number_for(name: str) -> int | None:
    """Extrahiert die Gobo-Nummer aus Namen wie "Gobo 3 Shake" (oder None)."""
    m = re.search(r"gobo\s*(\d+)", (name or "").lower())
    return int(m.group(1)) if m else None


def is_shake_name(name: str) -> bool:
    return "shake" in (name or "").lower() or "wackel" in (name or "").lower()


# ── Muster-Maler (zeichnen ins Innere des Kreises, Radius r um Mitte c) ──────

def _pen(width: float) -> QPen:
    pen = QPen(_FG, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


def _draw_ring_slits(p: QPainter, c: QPointF, r: float):
    """Gobo 1: heller Ring, Mitte dunkel, drei dunkle Spalten im Ring."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pen(r * 0.42))
    rect = QRectF(c.x() - r * 0.62, c.y() - r * 0.62, r * 1.24, r * 1.24)
    # drei Bogensegmente mit Luecken (Spalten); Qt-Winkel in 1/16 Grad
    for start in (15, 135, 255):
        p.drawArc(rect, start * 16, 90 * 16)


def _draw_ovals(p: QPainter, c: QPointF, r: float):
    """Gobo 2: Ovale von innen klein nach aussen gross."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pen(max(1.2, r * 0.12)))
    for f in (0.3, 0.6, 0.92):
        p.drawEllipse(QRectF(c.x() - r * f, c.y() - r * f * 0.62,
                             2 * r * f, 2 * r * f * 0.62))


def _draw_circle_of_circles(p: QPainter, c: QPointF, r: float):
    """Gobo 3: ein grosser Kreis, der aus vielen kleinen Kreisen besteht."""
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_FG))
    n, rr = 9, r * 0.17
    for i in range(n):
        a = 2 * math.pi * i / n
        x = c.x() + r * 0.66 * math.cos(a)
        y = c.y() + r * 0.66 * math.sin(a)
        p.drawEllipse(QRectF(x - rr, y - rr, 2 * rr, 2 * rr))


def _draw_tetris(p: QPainter, c: QPointF, r: float):
    """Gobo 4: Tetris-Muster (verschachtelte Quadrate/L-Formen)."""
    p.setPen(QPen(_BG, max(1.0, r * 0.07)))
    p.setBrush(QBrush(_FG))
    u = r * 0.42
    cells = [(-1.4, -1.4), (-0.4, -1.4),            # oben: 2er-Riegel
             (-0.4, -0.4), (0.6, -0.4),             # Mitte: versetzt (S-Form)
             (-1.4, 0.6), (-0.4, 0.6), (0.6, 0.6)]  # unten: 3er-Riegel
    for gx, gy in cells:
        p.drawRect(QRectF(c.x() + gx * u, c.y() + gy * u, u, u))


def _draw_dots(p: QPainter, c: QPointF, r: float):
    """Gobo 5: unterschiedlich grosse, verstreute Kreise."""
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_FG))
    spots = [(-0.45, -0.4, 0.30), (0.42, -0.45, 0.18), (0.5, 0.18, 0.26),
             (-0.15, 0.28, 0.16), (-0.55, 0.45, 0.2), (0.05, -0.1, 0.11)]
    for gx, gy, gr in spots:
        rr = r * gr
        p.drawEllipse(QRectF(c.x() + gx * r - rr, c.y() + gy * r - rr,
                             2 * rr, 2 * rr))


def _draw_spiral(p: QPainter, c: QPointF, r: float):
    """Gobo 6: Spirale."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pen(max(1.4, r * 0.16)))
    path = QPainterPath()
    turns, steps = 2.6, 60
    for i in range(steps + 1):
        t = i / steps
        a = 2 * math.pi * turns * t
        rad = r * 0.92 * t
        pt = QPointF(c.x() + rad * math.cos(a), c.y() + rad * math.sin(a))
        if i == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    p.drawPath(path)


def _draw_zebra(p: QPainter, c: QPointF, r: float):
    """Gobo 7: Zebra-Muster (helle Streifen)."""
    clip = QPainterPath()
    clip.addEllipse(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r))
    p.save()
    p.setClipPath(clip)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_FG))
    w = r * 0.34
    x = c.x() - r
    while x < c.x() + r:
        p.drawRect(QRectF(x, c.y() - r, w * 0.55, 2 * r))
        x += w
    p.restore()


_PAINTERS = {
    "ring_slits": _draw_ring_slits,
    "ovals": _draw_ovals,
    "circle_of_circles": _draw_circle_of_circles,
    "tetris": _draw_tetris,
    "dots": _draw_dots,
    "spiral": _draw_spiral,
    "zebra": _draw_zebra,
}


def gobo_pixmap(style: str, size: int = 28, shake: bool = False,
                number: int | None = None) -> QPixmap:
    """Pixmap fuer ein Gobo-Muster. ``style`` aus STYLES, "open" oder ""
    (neutral; mit ``number`` als Beschriftung). ``shake`` ergaenzt orange
    Vibrations-Marker."""
    key = (style, int(size), bool(shake), number)
    pm = _cache.get(key)
    if pm is not None:
        return pm

    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    c = QPointF(size / 2, size / 2)
    r = size * 0.42
    # dunkle Kreisflaeche mit Rand
    p.setPen(QPen(_RIM, max(1.0, size * 0.05)))
    p.setBrush(QBrush(QColor("#3a4250") if style == "open" else _BG))
    p.drawEllipse(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r))

    painter_fn = _PAINTERS.get(style)
    if painter_fn is not None:
        painter_fn(p, c, r)
    elif style != "open" and number is not None:
        # neutrales Fallback-Icon: Nummer im Kreis (kein geratenes Muster)
        p.setPen(QPen(_FG))
        f = QFont()
        f.setPixelSize(int(size * 0.5))
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 0, size, size),
                   Qt.AlignmentFlag.AlignCenter, str(number))

    if shake:
        # Vibrations-Marker: zwei kurze Boegen rechts oben ausserhalb des Rads
        pen = QPen(_SHAKE, max(1.2, size * 0.07))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for f in (1.06, 1.3):
            rect = QRectF(c.x() - r * f, c.y() - r * f, 2 * r * f, 2 * r * f)
            p.drawArc(rect, 25 * 16, 40 * 16)

    p.end()
    _cache[key] = pm
    return pm


def gobo_pixmap_for_name(name: str, size: int = 28,
                         shake: bool | None = None) -> QPixmap:
    """Bequem-Variante: Muster, Nummer und Shake direkt aus dem Range-Namen."""
    if shake is None:
        shake = is_shake_name(name)
    return gobo_pixmap(gobo_style_for(name), size=size, shake=shake,
                       number=gobo_number_for(name))
