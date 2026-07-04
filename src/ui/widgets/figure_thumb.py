"""Mini-Vorschau einer :class:`LaserFigure` als Pixmap + anklickbare Kachel
(LAS-17, Bibliotheks-Leiste des Zeichen-Studios).

Rein UI, keine Ausgabe: zeichnet die Figur-Segmente (Farbe je Zielpunkt, blanke
Segmente gestrichelt/dunkel) verkleinert in eine Kachel. Klick lädt die Figur.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from src.core.laser.figure import LaserFigure


def _qcolor(r: float, g: float, b: float) -> QColor:
    return QColor(int(r * 255), int(g * 255), int(b * 255))


def render_figure_pixmap(fig: LaserFigure, w: int, h: int,
                         bg: str = "#0d1117") -> QPixmap:
    """Verkleinerte Vorschau der Figur (−1..+1, +y oben) in ein ``w×h``-Pixmap.
    Leere/1-Punkt-Figuren → nur Hintergrund."""
    pm = QPixmap(w, h)
    pm.fill(QColor(bg))
    pts = list(getattr(fig, "points", []) or [])
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    m = 6
    s = min(w, h) - 2 * m
    ox = (w - s) // 2
    oy = (h - s) // 2

    def to_px(x, y):
        return (int(ox + (x + 1.0) * 0.5 * s), int(oy + (1.0 - y) * 0.5 * s))

    if len(pts) >= 2:
        seq = list(range(len(pts)))
        if getattr(fig, "closed", False):
            seq.append(0)
        for a, b in zip(seq, seq[1:]):
            pa, pb = pts[a], pts[b]
            x1, y1 = to_px(pa.x, pa.y)
            x2, y2 = to_px(pb.x, pb.y)
            if getattr(pb, "blank", False):
                p.setPen(QPen(QColor("#3a3f46"), 1, Qt.PenStyle.DashLine))
            else:
                p.setPen(QPen(_qcolor(pb.r, pb.g, pb.b), 2))
            p.drawLine(x1, y1, x2, y2)
    elif len(pts) == 1:
        x, y = to_px(pts[0].x, pts[0].y)
        p.setBrush(_qcolor(pts[0].r, pts[0].g, pts[0].b))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(x - 3, y - 3, 6, 6)
    p.end()
    return pm


class FigureTile(QWidget):
    """Anklickbare Kachel: Mini-Vorschau oben + Name unten. ``on_click(fig)``
    wird beim Antippen gerufen (Bibliotheks-Figur laden)."""

    THUMB_W = 84
    THUMB_H = 60

    def __init__(self, figure: LaserFigure, on_click, parent=None):
        super().__init__(parent)
        self._fig = figure
        self._on_click = on_click        # callback(fig) — bewusst kein Qt-Signal
        self._name = getattr(figure, "name", "") or "—"
        self._pm = render_figure_pixmap(figure, self.THUMB_W, self.THUMB_H)
        self.setFixedSize(self.THUMB_W + 8, self.THUMB_H + 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{self._name} laden")

    def paintEvent(self, event):  # noqa: N802 (Qt-API)
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#161b22"))
        p.setPen(QPen(QColor("#30363d"), 1))
        p.drawRect(3, 3, self.THUMB_W + 1, self.THUMB_H + 1)
        p.drawPixmap(4, 4, self._pm)
        p.setPen(QColor("#c9d1d9"))
        f = QFont(); f.setPixelSize(10); p.setFont(f)
        p.drawText(QRect(0, self.THUMB_H + 6, self.width(), 14),
                   Qt.AlignmentFlag.AlignCenter,
                   self._name[:14] + ("…" if len(self._name) > 14 else ""))
        p.end()

    def mousePressEvent(self, ev):  # noqa: N802 (Qt-API)
        if self._on_click is not None:
            self._on_click(self._fig)
