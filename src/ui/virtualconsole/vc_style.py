"""Gemeinsame 3D-/Haptik-Optik fuer Virtual-Console-Bedienelemente.

Zentraler Paint-Helfer, damit Buttons (und spaeter Slider/SpeedDial) einen
einheitlichen, plastischen Pad-Look bekommen: eine leicht gewoelbte Taste, die
aus einer dunklen Wanne herausragt (Tiefe), mit Bevel-Kanten (Licht oben,
Schatten unten) und einem Druck-/Aktiv-Feedback:

  * **raised** (Normal): Taste sitzt oben, darunter ein farbiger „Rand" als
    sichtbare Tastendicke -> wirkt erhaben.
  * **pressed**: Taste faehrt auf den Rand herunter, Verlauf kehrt sich um
    (dunkel oben) -> wirkt eingedrueckt (haptisch, ohne echtes 3D).
  * **lit** (aktiv/gedrueckt-gehalten): heller Grundton + weicher Glow-Ring,
    damit ein aktiver Toggle auf einen Blick auffaellt.

Bewusst *kein* echtes 3D — nur Verlauf + Bevel + Schatten (guenstig, deutlich,
Touch-freundlich). Alles rein via QPainter, keine externen Assets.
"""
from __future__ import annotations
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QLinearGradient, QPen, QBrush, QPainter

# Tastendicke: wie weit die Taste beim Druck faellt (px). Gleich der Hoehe des
# sichtbaren farbigen Randes im Normalzustand.
DEPTH = 4
# Eckenradius der Taste (weiche Pad-Optik).
RADIUS = 8
# Innenrand zwischen Widget-Kante und Taste (die dunkle Wanne).
MARGIN = 2


def key_rect(rect, pressed: bool) -> QRectF:
    """Die Taste-„Face"-Flaeche (obere Sichtflaeche) im Widget-Rechteck.

    Im Normalzustand sitzt sie oben und laesst darunter ``DEPTH`` px fuer den
    Rand frei; gedrueckt faehrt sie um ``DEPTH`` nach unten (auf den Rand).
    """
    rf = QRectF(rect)
    # Breite/Hoehe robust klemmen (winzige Widgets -> nie negativ); unten Platz
    # fuer die Tastendicke reservieren, gedrueckt um DEPTH nach unten versetzen.
    w = max(1.0, rf.width() - 2 * MARGIN)
    h = max(1.0, rf.height() - 2 * MARGIN - DEPTH)
    x = rf.left() + MARGIN
    y = rf.top() + MARGIN + (DEPTH if pressed else 0.0)
    return QRectF(x, y, w, h)


def _tray_color(base: QColor) -> QColor:
    """Dunkle Wanne, aus der die Taste ragt (aus dem Grundton abgeleitet)."""
    return base.darker(260)


def paint_button_surface(painter: QPainter, rect, base: QColor,
                         pressed: bool, lit: bool, radius: float = RADIUS) -> QRectF:
    """Malt die plastische Tastenflaeche und liefert das Face-Rechteck zurueck.

    Der Aufrufer zeichnet Text/Badges/Zustands-Rahmen anschliessend in das
    zurueckgegebene Face-Rechteck (so sitzt alles auf der erhabenen Taste).
    """
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    full = QRectF(rect)
    # 1) Ganze Flaeche dunkel fuellen (quadratisch, deckt auch die Ecken) -> der
    #    schmale Rand um die runde Taste wirkt als Wanne und blendet in den
    #    dunklen VC-Canvas, unabhaengig davon, was die Basisklasse vorgefuellt hat.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.fillRect(full, _tray_color(base))

    face = key_rect(rect, pressed)

    # Effektiver Grundton: aktiv -> heller (Glow-Basis).
    b = base.lighter(150) if lit else base

    # 2) Erhabener Zustand: farbiger „Rand" (Tastendicke) als Verlauf unter der
    #    Face — von der Face-Farbe nach unten dunkler -> liest sich als Seite.
    if not pressed:
        edge = QRectF(face)
        edge.translate(0, DEPTH)
        eg = QLinearGradient(edge.topLeft(), edge.bottomLeft())
        eg.setColorAt(0.0, b.darker(200))
        eg.setColorAt(1.0, b.darker(300))
        painter.setBrush(QBrush(eg))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(edge, radius, radius)

    # 3) Face-Verlauf (gewoelbte Oberflaeche).
    grad = QLinearGradient(face.topLeft(), face.bottomLeft())
    if pressed:
        # eingedrueckt: dunkel oben, minimal heller unten (konkav).
        grad.setColorAt(0.0, b.darker(150))
        grad.setColorAt(1.0, b.darker(105))
    else:
        # erhaben: hell oben, dunkler unten (konvex, Licht von oben).
        grad.setColorAt(0.0, b.lighter(142))
        grad.setColorAt(0.55, b)
        grad.setColorAt(1.0, b.darker(120))
    painter.setBrush(QBrush(grad))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(face, radius, radius)

    # 4) Kanten-Detail.
    if pressed:
        # Innen-Schatten am oberen Rand: die „Wand" der Vertiefung wirft Schatten
        # -> die Taste sieht klar eingesenkt aus.
        sh = QColor(0, 0, 0, 110)
        painter.setPen(QPen(sh, 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(face.adjusted(1.0, 1.0, -1.0, 2.0), radius, radius)
    else:
        # Bevel: dezente Licht-Kante oben (Glanzlicht der Woelbung).
        hi = QColor(255, 255, 255, 65)
        painter.setPen(QPen(hi, 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        top = QRectF(face.adjusted(1.2, 1.2, -1.2, -1.2))
        painter.drawRoundedRect(top, radius - 1, radius - 1)

    # 5) Aktiv-Glow: weicher heller Ring um die Face.
    if lit:
        glow = base.lighter(210)
        glow.setAlpha(160)
        painter.setPen(QPen(glow, 2.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(face.adjusted(0.8, 0.8, -0.8, -0.8), radius, radius)

    painter.restore()
    return face
