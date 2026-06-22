"""SpiderBarsView — gemeinsame Live-Visualisierung eines Doppel-/Mehrbar-Spiders.

Ein Spider (z. B. U King SPIDER14, Mini-Spider, Twinscan, Butterfly …) hat
KEINEN Pan, sondern **mehrere separate Tilt-Motoren** — meist zwei (Bar Links /
Bar Rechts), bei manchen Modellen aber 3–8. Dieses Widget zeichnet jede Bar als
um einen oberen Drehpunkt schwenkende Lichtleiste, deren Winkel aus dem
jeweiligen Tilt-Wert (0..255) abgeleitet wird.

Wiederverwendet von:
  - ``SpiderPositionTool`` (statisch: spiegelt die Regler) und
  - ``SpiderEfxPreview`` (animiert: Tilt aus der laufenden EFX-Figur).

Bewusst zustandslos gegenueber dem Programmer/Render-Pfad: nur Darstellung.
"""
from __future__ import annotations
import math
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QFont
from PySide6.QtWidgets import QWidget, QSizePolicy

# Tilt 0..255 -> Schwenkwinkel relativ zur Senkrechten (nach unten). 128 = gerade
# nach unten (0 deg), 0/255 = maximal nach hinten/vorne. +/-75 deg liest sich als
# klar erkennbarer Scheren-Ausschlag ohne die Bars uebereinander zu legen.
_MAX_SWING_DEG = 75.0

# Farb-Palette zur Unterscheidung der Bars (warm=L, blau=R, dann weitere).
BAR_COLORS = ["#ffb347", "#58a6ff", "#3fb950", "#ff7b72",
              "#d2a8ff", "#ffa657", "#79c0ff", "#a5d6ff"]


def tilt_to_swing_deg(tilt: int) -> float:
    """Tilt-Byte (0..255) -> Schwenkwinkel in Grad (0 = senkrecht nach unten)."""
    t = max(0, min(255, int(tilt)))
    return (t - 127.5) / 127.5 * _MAX_SWING_DEG


class SpiderBarsView(QWidget):
    """Zeichnet N schwenkende Lichtleisten (Bars) eines Spiders.

    ``set_tilts(values)`` ODER ``set_tilts(v0, v1, …)`` setzt die Tilt-Werte
    (0..255) — die Bar-Anzahl ergibt sich aus der Anzahl der Werte. ``labels``
    optional fuer die Beschriftung (sonst „1","2",… bzw. „L","R" bei genau 2).
    """

    def __init__(self, parent=None, count: int = 2):
        super().__init__(parent)
        self._tilts = [128] * max(1, int(count))
        self._labels: list[str] | None = None
        self.setMinimumSize(200, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_tilts(self, *values):
        """Tilt-Werte setzen — entweder als Liste/Tupel oder als Einzelargumente."""
        if len(values) == 1 and isinstance(values[0], (list, tuple)):
            vals = list(values[0])
        else:
            vals = list(values)
        if not vals:
            return
        self._tilts = [max(0, min(255, int(v))) for v in vals]
        self.update()

    def set_labels(self, labels):
        self._labels = list(labels) if labels else None
        self.update()

    def tilts(self) -> list[int]:
        return list(self._tilts)

    def _label_for(self, i: int, n: int) -> str:
        if self._labels and i < len(self._labels):
            return self._labels[i]
        if n == 2:
            return ("L", "R")[i]
        return str(i + 1)

    # ── Zeichnen ───────────────────────────────────────────────────────────────

    def _draw_bar(self, p: QPainter, pivot: QPointF, tilt: int, length: float,
                  color: QColor, label: str):
        ang = math.radians(tilt_to_swing_deg(tilt))
        # 0 deg = nach unten (+y); positiver Winkel schwenkt nach rechts.
        dx = math.sin(ang) * length
        dy = math.cos(ang) * length
        tip = QPointF(pivot.x() + dx, pivot.y() + dy)

        # Schwenk-Bogen (dezent), zeigt den Tilt-Bereich an.
        p.setPen(QPen(QColor("#222b36"), 1, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(pivot, length, length)

        # Bar als dicke Leiste mit LED-Punkten.
        p.setPen(QPen(color, 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(pivot, tip)
        for k in range(1, 5):
            f = k / 5.0
            p.setPen(QPen(QColor("#0d1117"), 1))
            p.setBrush(QBrush(color))
            p.drawEllipse(QPointF(pivot.x() + dx * f, pivot.y() + dy * f), 3.2, 3.2)

        # Drehpunkt
        p.setPen(QPen(QColor("#0d1117"), 1))
        p.setBrush(QBrush(QColor("#c9d1d9")))
        p.drawEllipse(pivot, 4, 4)

        # Label + Tilt-Wert an der Spitze
        p.setPen(QColor("#8b949e"))
        f = QFont()
        f.setPixelSize(10)
        p.setFont(f)
        p.drawText(QPointF(tip.x() - 6, tip.y() + 16), f"{label} {tilt}")

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        p.fillRect(rect, QColor("#0d1117"))

        n = max(1, len(self._tilts))
        w = rect.width()
        h = rect.height()
        # Gehaeuse-Balken oben (die Bars haengen daran, kein Pan/Yoke).
        hub_w = min(w * 0.78, 120 + n * 60)
        hub_x = (w - hub_w) / 2.0
        hub_y = h * 0.16
        p.setPen(QPen(QColor("#30363d"), 1))
        p.setBrush(QBrush(QColor("#161b22")))
        p.drawRoundedRect(int(hub_x), int(hub_y - 10), int(hub_w), 18, 4, 4)

        # Drehpunkte gleichmaessig ueber das Gehaeuse verteilen.
        length = min(h * 0.55, hub_w / (n + 1) * 0.95, 90)
        for i in range(n):
            px = hub_x + hub_w * (i + 1) / (n + 1)
            piv = QPointF(px, hub_y)
            color = QColor(BAR_COLORS[i % len(BAR_COLORS)])
            self._draw_bar(p, piv, self._tilts[i], length, color,
                           self._label_for(i, n))
        p.end()
