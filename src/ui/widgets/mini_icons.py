"""Programmatisch gezeichnete Mini-Icons fuer Listen/Baeume (UI-ICONS-01).

Zweck: in allen Ordner-/Listen-Ansichten (Bibliothek, Patch, Fixture-Gruppen,
Funktions-Manager) links neben dem Namen ein kleines Symbol zeigen, damit auf
einen Blick klar ist, *was* ein Eintrag ist:

  * Snaps  -> gelber Punkt
  * Effekte/Funktionen -> typ-spezifisches Glyph (RGB-Matrix = kleine Matrix,
    Chaser = Pfeile, Audio = Wellenform, …) in der Bibliotheks-Typfarbe
  * Ordner -> Ordner-Symbol
  * Fixtures -> Geraetetyp (Moving Head, PAR, LED-Bar, Strobe, Dimmer, …)

Alle Icons werden mit QPainter auf transparente Pixmaps gezeichnet (keine
externen Bilddateien) und nach (kind, size) gecacht. Die Farben sind bewusst an
die bereits genutzte Bibliotheks-Farbcodierung (snap_file_panel) angelehnt.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QPolygonF, QPainterPath, QFont,
)

# ── Farben (an snap_file_panel._FUNC_COLORS / _SNAP_COLOR angelehnt) ───────────
_SNAP      = "#FFD700"   # gelb
_FOLDER    = "#d9b25a"   # warmes ocker
_SCENE     = "#5ec8ff"   # hellblau
_CHASER    = "#ff9a55"   # orange
_SEQUENCE  = "#ff77bb"   # pink
_COLLECTION= "#b388ff"   # violett
_SHOW      = "#cfcfcf"   # hellgrau
_AUDIO     = "#9aa0a6"   # grau
_EFFECT    = "#5effa6"   # gruen (EFX / Layered / Carousel)
_SCRIPT    = "#88ddcc"   # teal
_MATRIX    = "#ffd166"   # gold-orange (Rahmen der Mini-Matrix)

# Fixture-Typ-Farben (heller als die dunklen Tabellen-Hintergruende in patch_view)
_FX_MOVING  = "#4aa3ff"
_FX_PAR     = "#5fd35f"
_FX_BAR     = "#e0c64a"
_FX_STROBE  = "#ff6b6b"
_FX_DIMMER  = "#b8b8b8"
_FX_OTHER   = "#8a8aa0"
_FX_SCANNER = "#5ab4e8"
_FX_LASER   = "#cc55ff"
_FX_SMOKE   = "#a0a8b0"
_FX_HAZER   = "#88b8b0"
_FX_SPIDER  = "#5ab0ff"


# ── Cache ─────────────────────────────────────────────────────────────────────
_cache: dict[tuple[str, int], QIcon] = {}


def _pixmap(size: int) -> tuple[QPixmap, QPainter]:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    return pm, p


def _qc(c) -> QColor:
    return c if isinstance(c, QColor) else QColor(c)


# ── Einzelne Glyph-Maler (Canvas 0..size) ─────────────────────────────────────

def _draw_dot(p: QPainter, s: int, color):
    """Gefuellter Kreis mit dunklem Rand (Snap / Szene / generisch)."""
    col = _qc(color)
    p.setBrush(QBrush(col))
    p.setPen(QPen(col.darker(160), max(1.0, s * 0.06)))
    m = s * 0.22
    p.drawEllipse(QRectF(m, m, s - 2 * m, s - 2 * m))


def _draw_folder(p: QPainter, s: int, color):
    col = _qc(color)
    p.setPen(QPen(col.darker(170), max(1.0, s * 0.06)))
    p.setBrush(QBrush(col))
    x0, y0 = s * 0.12, s * 0.28
    w, h = s * 0.76, s * 0.5
    # Reiter
    tab = QRectF(x0, y0 - s * 0.12, w * 0.45, s * 0.16)
    p.drawRoundedRect(tab, s * 0.05, s * 0.05)
    # Korpus
    p.drawRoundedRect(QRectF(x0, y0, w, h), s * 0.08, s * 0.08)


def _draw_chevrons(p: QPainter, s: int, color):
    """Zwei Pfeil-Winkel ›› (Chaser/Lauflicht)."""
    pen = QPen(_qc(color), max(1.4, s * 0.13))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for dx in (-s * 0.18, s * 0.14):
        cx = s * 0.5 + dx
        poly = QPolygonF([
            QPointF(cx - s * 0.12, s * 0.28),
            QPointF(cx + s * 0.10, s * 0.5),
            QPointF(cx - s * 0.12, s * 0.72),
        ])
        p.drawPolyline(poly)


def _draw_lines(p: QPainter, s: int, color):
    """Drei horizontale Linien (Sequence/Liste)."""
    pen = QPen(_qc(color), max(1.3, s * 0.11))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    for i, y in enumerate((0.32, 0.5, 0.68)):
        x1 = s * 0.26
        x2 = s * (0.74 if i != 1 else 0.66)
        p.drawLine(QPointF(x1, s * y), QPointF(x2, s * y))


def _draw_stack(p: QPainter, s: int, color):
    """Zwei versetzte Rechtecke (Collection)."""
    col = _qc(color)
    p.setPen(QPen(col.darker(170), max(1.0, s * 0.06)))
    p.setBrush(QBrush(col.lighter(115)))
    p.drawRoundedRect(QRectF(s * 0.18, s * 0.18, s * 0.5, s * 0.5), s * 0.06, s * 0.06)
    p.setBrush(QBrush(col))
    p.drawRoundedRect(QRectF(s * 0.34, s * 0.34, s * 0.5, s * 0.5), s * 0.06, s * 0.06)


def _draw_play(p: QPainter, s: int, color):
    """Play-Dreieck (Show)."""
    col = _qc(color)
    p.setPen(QPen(col.darker(170), max(1.0, s * 0.05)))
    p.setBrush(QBrush(col))
    tri = QPolygonF([
        QPointF(s * 0.34, s * 0.26),
        QPointF(s * 0.74, s * 0.5),
        QPointF(s * 0.34, s * 0.74),
    ])
    p.drawPolygon(tri)


def _draw_wave(p: QPainter, s: int, color):
    """Vertikale Balken unterschiedlicher Hoehe (Audio/Wellenform)."""
    col = _qc(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(col))
    heights = [0.32, 0.6, 0.85, 0.5, 0.7, 0.36]
    n = len(heights)
    bw = s * 0.62 / (2 * n - 1)
    x = s * 0.19
    for hfac in heights:
        bh = s * 0.62 * hfac
        y = s * 0.5 - bh / 2
        p.drawRoundedRect(QRectF(x, y, bw, bh), bw * 0.4, bw * 0.4)
        x += 2 * bw


def _draw_curve(p: QPainter, s: int, color):
    """Liegende Acht / Lissajous (EFX)."""
    pen = QPen(_qc(color), max(1.4, s * 0.11))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(s * 0.5, s * 0.5)
    path.cubicTo(s * 0.18, s * 0.16, s * 0.18, s * 0.84, s * 0.5, s * 0.5)
    path.cubicTo(s * 0.82, s * 0.16, s * 0.82, s * 0.84, s * 0.5, s * 0.5)
    p.drawPath(path)


def _draw_brackets(p: QPainter, s: int, color):
    """</>  (Script)."""
    pen = QPen(_qc(color), max(1.4, s * 0.12))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolyline(QPolygonF([
        QPointF(s * 0.38, s * 0.28), QPointF(s * 0.2, s * 0.5), QPointF(s * 0.38, s * 0.72)]))
    p.drawPolyline(QPolygonF([
        QPointF(s * 0.62, s * 0.28), QPointF(s * 0.8, s * 0.5), QPointF(s * 0.62, s * 0.72)]))


def _draw_layers(p: QPainter, s: int, color):
    """Drei gestapelte Rauten (Layered-Effekt)."""
    col = _qc(color)
    p.setPen(QPen(col.darker(170), max(1.0, s * 0.05)))
    cx = s * 0.5
    for i, cy in enumerate((0.66, 0.5, 0.34)):
        shade = col.lighter(100 + i * 16)
        p.setBrush(QBrush(shade))
        dia = QPolygonF([
            QPointF(cx, s * (cy - 0.16)),
            QPointF(cx + s * 0.26, s * cy),
            QPointF(cx, s * (cy + 0.16)),
            QPointF(cx - s * 0.26, s * cy),
        ])
        p.drawPolygon(dia)


def _draw_carousel(p: QPainter, s: int, color):
    """Kreis-Pfeil (Carousel/Rotation)."""
    pen = QPen(_qc(color), max(1.4, s * 0.11))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    m = s * 0.26
    rect = QRectF(m, m, s - 2 * m, s - 2 * m)
    # offener Bogen
    p.drawArc(rect, 40 * 16, 280 * 16)
    # Pfeilspitze am Bogenende
    tip = QPointF(s * 0.5 + (s * 0.5 - m) * 0.77, s * 0.5 - (s * 0.5 - m) * 0.64)
    p.setBrush(QBrush(_qc(color)))
    p.setPen(Qt.PenStyle.NoPen)
    a = s * 0.13
    p.drawPolygon(QPolygonF([
        QPointF(tip.x() - a, tip.y() - a * 0.2),
        QPointF(tip.x() + a * 0.4, tip.y() - a),
        QPointF(tip.x() + a * 0.2, tip.y() + a * 0.5),
    ]))


def _draw_matrix(p: QPainter, s: int, _color):
    """Kleine 3x3-Matrix aus bunten Zellen (RGB-Matrix) — wie vom Nutzer gewuenscht."""
    cells = [
        _FX_STROBE, _MATRIX,   _SCENE,
        _MATRIX,    _SCENE,    _EFFECT,
        _SCENE,     _EFFECT,   _FX_STROBE,
    ]
    n = 3
    gap = s * 0.06
    total = s * 0.74
    cw = (total - gap * (n - 1)) / n
    x0 = (s - total) / 2
    y0 = (s - total) / 2
    p.setPen(Qt.PenStyle.NoPen)
    for r in range(n):
        for c in range(n):
            p.setBrush(QBrush(_qc(cells[r * n + c])))
            x = x0 + c * (cw + gap)
            y = y0 + r * (cw + gap)
            p.drawRoundedRect(QRectF(x, y, cw, cw), cw * 0.22, cw * 0.22)


def _draw_moving_head(p: QPainter, s: int, color):
    """Kopf (Kreis) auf Buegel (Moving Head)."""
    col = _qc(color)
    # Basis/Buegel
    p.setPen(QPen(col.darker(150), max(1.2, s * 0.08)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(s * 0.22, s * 0.30, s * 0.56, s * 0.56), 20 * 16, 140 * 16)
    # Kopf
    p.setPen(QPen(col.darker(160), max(1.0, s * 0.05)))
    p.setBrush(QBrush(col))
    p.drawEllipse(QRectF(s * 0.34, s * 0.30, s * 0.32, s * 0.32))
    # Linse
    p.setBrush(QBrush(col.lighter(150)))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(s * 0.43, s * 0.39, s * 0.14, s * 0.14))


def _draw_par(p: QPainter, s: int, color):
    """PAR: Kreis mit Lichtkegel."""
    col = _qc(color)
    # Kegel
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(col.lighter(150)))
    cone = QPolygonF([
        QPointF(s * 0.5, s * 0.5),
        QPointF(s * 0.86, s * 0.26),
        QPointF(s * 0.86, s * 0.74),
    ])
    p.drawPolygon(cone)
    # Gehaeuse
    p.setPen(QPen(col.darker(160), max(1.0, s * 0.05)))
    p.setBrush(QBrush(col))
    p.drawEllipse(QRectF(s * 0.16, s * 0.30, s * 0.4, s * 0.4))


def _draw_bar(p: QPainter, s: int, color):
    """LED-Bar: Reihe aus Punkten."""
    col = _qc(color)
    p.setPen(QPen(col.darker(160), max(1.0, s * 0.05)))
    p.setBrush(QBrush(col.darker(115)))
    p.drawRoundedRect(QRectF(s * 0.12, s * 0.38, s * 0.76, s * 0.24), s * 0.08, s * 0.08)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(col.lighter(140)))
    n = 4
    for i in range(n):
        x = s * 0.2 + i * (s * 0.6 / (n - 1))
        p.drawEllipse(QRectF(x - s * 0.05, s * 0.44, s * 0.1, s * 0.1))


def _draw_strobe(p: QPainter, s: int, color):
    """Strobe: Blitz."""
    col = _qc(color)
    p.setPen(QPen(col.darker(160), max(1.0, s * 0.05)))
    p.setBrush(QBrush(col))
    bolt = QPolygonF([
        QPointF(s * 0.56, s * 0.16),
        QPointF(s * 0.30, s * 0.56),
        QPointF(s * 0.48, s * 0.56),
        QPointF(s * 0.42, s * 0.84),
        QPointF(s * 0.72, s * 0.42),
        QPointF(s * 0.52, s * 0.42),
    ])
    p.drawPolygon(bolt)


def _draw_dimmer(p: QPainter, s: int, color):
    """Dimmer: Gluehfaden-Kreis."""
    col = _qc(color)
    p.setPen(QPen(col, max(1.2, s * 0.07)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(s * 0.26, s * 0.2, s * 0.48, s * 0.48))
    pen = QPen(col.lighter(140), max(1.0, s * 0.06))
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.43, s * 0.7), QPointF(s * 0.43, s * 0.82))
    p.drawLine(QPointF(s * 0.57, s * 0.7), QPointF(s * 0.57, s * 0.82))


def _draw_scanner(p: QPainter, s: int, color):
    """Scanner: Spiegel auf Sockel mit Lichtstrahl."""
    col = _qc(color)
    # Sockel
    p.setPen(QPen(col.darker(160), max(1.0, s * 0.06)))
    p.setBrush(QBrush(col.darker(130)))
    p.drawRoundedRect(QRectF(s * 0.2, s * 0.72, s * 0.6, s * 0.14), s * 0.04, s * 0.04)
    # Spiegel (geneigtes Oval)
    p.setBrush(QBrush(col))
    p.save()
    p.translate(s * 0.5, s * 0.5)
    p.rotate(-35)
    p.drawEllipse(QRectF(-s * 0.22, -s * 0.1, s * 0.44, s * 0.2))
    p.restore()
    # Lichtstrahl (Keil nach rechts-oben)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(col.lighter(160)))
    beam = QPolygonF([
        QPointF(s * 0.56, s * 0.44),
        QPointF(s * 0.88, s * 0.12),
        QPointF(s * 0.82, s * 0.18),
    ])
    p.drawPolygon(beam)


def _draw_laser(p: QPainter, s: int, color):
    """Laser: Geraet mit Strahlenfaecher."""
    col = _qc(color)
    # Geraetegehaeuse
    p.setPen(QPen(col.darker(160), max(1.0, s * 0.05)))
    p.setBrush(QBrush(col.darker(115)))
    p.drawRoundedRect(QRectF(s * 0.12, s * 0.58, s * 0.32, s * 0.26), s * 0.06, s * 0.06)
    # Strahlenfaecher (3 duenne Linien von Emitter-Punkt aus)
    pen = QPen(col.lighter(150), max(1.0, s * 0.055))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    origin = QPointF(s * 0.44, s * 0.71)
    targets = [
        QPointF(s * 0.88, s * 0.18),
        QPointF(s * 0.76, s * 0.12),
        QPointF(s * 0.62, s * 0.10),
    ]
    for t in targets:
        p.drawLine(origin, t)


def _draw_smoke(p: QPainter, s: int, color):
    """Smoke: Maschinengehaeuse mit Duese und Rauchwolke."""
    col = _qc(color)
    # Gehaeuse
    p.setPen(QPen(col.darker(150), max(1.0, s * 0.06)))
    p.setBrush(QBrush(col.darker(110)))
    p.drawRoundedRect(QRectF(s * 0.14, s * 0.52, s * 0.5, s * 0.34), s * 0.06, s * 0.06)
    # Duese (kleines Rechteck rechts)
    p.setBrush(QBrush(col))
    p.drawRoundedRect(QRectF(s * 0.64, s * 0.60, s * 0.12, s * 0.16), s * 0.03, s * 0.03)
    # Rauchwolke (3 kleine Kreise oben)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(col.lighter(130)))
    for cx, cy, r in (
        (s * 0.38, s * 0.38, s * 0.12),
        (s * 0.52, s * 0.30, s * 0.10),
        (s * 0.26, s * 0.33, s * 0.09),
    ):
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))


def _draw_spider(p: QPainter, s: int, color):
    """Spider / Dual-LED-Bar: zwei parallele horizontale Balken mit Kreis-Enden."""
    col = _qc(color)
    bar_h = s * 0.14
    gap = s * 0.16
    # Beide Balken vertikal zentriert mit 'gap' Abstand zwischen ihnen
    y_top = s * 0.5 - gap / 2 - bar_h
    y_bot = s * 0.5 + gap / 2
    x0 = s * 0.14
    x1 = s * 0.86
    bar_w = x1 - x0
    for y in (y_top, y_bot):
        # Balken-Rechteck
        p.setPen(QPen(col.darker(160), max(1.0, s * 0.05)))
        p.setBrush(QBrush(col.darker(115)))
        p.drawRoundedRect(QRectF(x0, y, bar_w, bar_h), bar_h * 0.4, bar_h * 0.4)
        # Kleiner Kreis an jedem Balkenende
        r = s * 0.07
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(col.lighter(150)))
        cy = y + bar_h / 2
        p.drawEllipse(QRectF(x0 - r, cy - r, r * 2, r * 2))
        p.drawEllipse(QRectF(x1 - r, cy - r, r * 2, r * 2))


def _draw_hazer(p: QPainter, s: int, color):
    """Hazer: Maschinengehaeuse mit Duese und feinerer Nebelwolke."""
    col = _qc(color)
    # Gehaeuse
    p.setPen(QPen(col.darker(150), max(1.0, s * 0.06)))
    p.setBrush(QBrush(col.darker(110)))
    p.drawRoundedRect(QRectF(s * 0.12, s * 0.50, s * 0.52, s * 0.36), s * 0.07, s * 0.07)
    # Duese (oben rechts am Gehaeuse)
    p.setBrush(QBrush(col))
    p.drawRoundedRect(QRectF(s * 0.64, s * 0.46, s * 0.14, s * 0.12), s * 0.03, s * 0.03)
    # Nebelwolke: 4 kleine halbdurchsichtige Kreise, breiter gestreut
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(col.lighter(145)))
    for cx, cy, r in (
        (s * 0.72, s * 0.34, s * 0.09),
        (s * 0.82, s * 0.26, s * 0.08),
        (s * 0.64, s * 0.28, s * 0.07),
        (s * 0.78, s * 0.18, s * 0.07),
    ):
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))


# ── kind -> (Maler, Farbe) ────────────────────────────────────────────────────
_PAINTERS = {
    "snap":       (_draw_dot,      _SNAP),
    "folder":     (_draw_folder,   _FOLDER),
    "scene":      (_draw_dot,      _SCENE),
    "chaser":     (_draw_chevrons, _CHASER),
    "sequence":   (_draw_lines,    _SEQUENCE),
    "collection": (_draw_stack,    _COLLECTION),
    "show":       (_draw_play,     _SHOW),
    "efx":        (_draw_curve,    _EFFECT),
    "rgbmatrix":  (_draw_matrix,   _MATRIX),
    "audio":      (_draw_wave,     _AUDIO),
    "script":     (_draw_brackets, _SCRIPT),
    "layered":    (_draw_layers,   _EFFECT),
    "carousel":   (_draw_carousel, _EFFECT),
    # Fixtures
    "fx_moving_head": (_draw_moving_head, _FX_MOVING),
    "fx_par":         (_draw_par,         _FX_PAR),
    "fx_led_bar":     (_draw_bar,         _FX_BAR),
    "fx_strobe":      (_draw_strobe,      _FX_STROBE),
    "fx_dimmer":      (_draw_dimmer,      _FX_DIMMER),
    "fx_scanner":     (_draw_scanner,     _FX_SCANNER),
    "fx_laser":       (_draw_laser,       _FX_LASER),
    "fx_smoke":       (_draw_smoke,       _FX_SMOKE),
    "fx_hazer":       (_draw_hazer,       _FX_HAZER),
    "fx_spider":      (_draw_spider,      _FX_SPIDER),
    "fx_other":       (_draw_dot,         _FX_OTHER),
}


def icon_for_kind(kind: str, size: int = 16) -> QIcon:
    """Liefert (gecacht) ein Mini-Icon fuer einen normalisierten kind-String.

    Unbekannte kinds → kleiner grauer Punkt (nie ein Fehler/leeres Icon)."""
    key = (kind, size)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    painter_fn, color = _PAINTERS.get(kind, (_draw_dot, _FX_OTHER))
    pm, p = _pixmap(size)
    try:
        painter_fn(p, size, color)
    finally:
        p.end()
    icon = QIcon(pm)
    _cache[key] = icon
    return icon


# ── High-Level-Helfer ─────────────────────────────────────────────────────────

def snap_icon(size: int = 16) -> QIcon:
    return icon_for_kind("snap", size)


def folder_icon(size: int = 16) -> QIcon:
    return icon_for_kind("folder", size)


def kind_for_function(f) -> str:
    """Normalisierter kind-String fuer eine Funktion (gleiche Logik wie die
    Bibliotheks-Farbcodierung in snap_file_panel)."""
    if getattr(f, "is_script", False):
        return "script"
    if getattr(f, "is_layered_effect", False):
        return "layered"
    if getattr(f, "is_carousel", False):
        return "carousel"
    ft = getattr(f, "function_type", None)
    name = getattr(ft, "value", str(ft))
    return {
        "Scene": "scene", "Chaser": "chaser", "Sequence": "sequence",
        "Collection": "collection", "Show": "show", "EFX": "efx",
        "RGBMatrix": "rgbmatrix", "Audio": "audio",
    }.get(name, "scene")


def function_icon(f, size: int = 16) -> QIcon:
    return icon_for_kind(kind_for_function(f), size)


def fixture_icon(fixture_type: str, size: int = 16) -> QIcon:
    """Icon fuer einen Geraetetyp (moving_head/par/led_bar/strobe/dimmer/…)."""
    ft = (fixture_type or "other").strip().lower()
    kind = f"fx_{ft}" if f"fx_{ft}" in _PAINTERS else "fx_other"
    return icon_for_kind(kind, size)


# Module-level cache for the lazy-imported is_spider_fixture callable.
_is_spider_fixture_fn = None
_is_spider_fixture_loaded = False


def fixture_icon_for(fixture, size: int = 16) -> QIcon:
    """Icon fuer ein PatchedFixture-Objekt mit Spider-Erkennung.

    Prueft via is_spider_fixture (lazy import aus src.core.app_state), ob das
    Geraet ein Spider ist, und liefert dann das Spider-Icon. Bei jedem anderen
    Typ delegiert es an fixture_icon. Schlaegt der Import fehl, wird immer auf
    das Typ-Icon zurueckgefallen — mini_icons bleibt standalone importierbar.
    """
    global _is_spider_fixture_fn, _is_spider_fixture_loaded
    if not _is_spider_fixture_loaded:
        _is_spider_fixture_loaded = True
        try:
            from src.core.app_state import is_spider_fixture as _fn
            _is_spider_fixture_fn = _fn
        except Exception:
            _is_spider_fixture_fn = None
    try:
        if _is_spider_fixture_fn is not None and _is_spider_fixture_fn(fixture):
            return icon_for_kind("fx_spider", size)
    except Exception:
        pass
    return fixture_icon(getattr(fixture, "fixture_type", "other"), size)
