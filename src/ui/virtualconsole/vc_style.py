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
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QLinearGradient, QRadialGradient, QPen, QBrush, QPainter

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
        # Bevel (saettigungs-UNABHAENGIG, VC3D-03): ein Gradient-Stift von hellem
        # Weiss (oben) ueber transparent zu Dunkel (unten) zeichnet Glanz- und
        # Schattenkante der Woelbung. Noetig, weil QColor.lighter() auf voll
        # gesaettigten Farben (V bereits 255) den Verlauf-Top NICHT aufhellt ->
        # ohne feste Kanten wirkte das Pad auf reinem Rot/Blau/Gruen flach.
        inner = QRectF(face.adjusted(1.2, 1.2, -1.2, -1.2))
        bevel = QLinearGradient(inner.topLeft(), inner.bottomLeft())
        bevel.setColorAt(0.0, QColor(255, 255, 255, 130))   # helle Glanzkante oben
        bevel.setColorAt(0.5, QColor(255, 255, 255, 20))
        bevel.setColorAt(1.0, QColor(0, 0, 0, 95))           # dunkle Schattenkante unten
        painter.setPen(QPen(QBrush(bevel), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(inner, radius - 1, radius - 1)

    # 5) Aktiv-Glow: weicher heller Ring um die Face.
    if lit:
        glow = base.lighter(210)
        glow.setAlpha(160)
        painter.setPen(QPen(glow, 2.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(face.adjusted(0.8, 0.8, -0.8, -0.8), radius, radius)

    painter.restore()
    return face


def paint_slider_handle(painter: QPainter, rect, base: QColor) -> None:
    """Plastischer Fader-Griff (horizontaler Balken) — VC3D-02.

    Gewoelbte Oberflaeche (Licht oben, Schatten unten) + saettigungs-unabhaengige
    Bevel-Kante (wie VC3D-03) + mittige Griff-Rille (haptisch). Reines QPainter,
    konsistent mit ``paint_button_surface``. Ersetzt ein flaches ``fillRect``."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    rf = QRectF(rect)
    rad = min(3.0, rf.height() / 2.0)
    # Woelbung: hell oben -> Basis -> dunkel unten (konvex, Licht von oben).
    grad = QLinearGradient(rf.topLeft(), rf.bottomLeft())
    grad.setColorAt(0.0, base.lighter(150))
    grad.setColorAt(0.5, base)
    grad.setColorAt(1.0, base.darker(140))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(grad))
    painter.drawRoundedRect(rf, rad, rad)
    # Bevel-Kante: heller Glanz oben -> dunkle Schattenkante unten (liest auch auf
    # voll gesaettigten Farben, da fixe Weiss/Schwarz-Alpha statt lighter()).
    inner = rf.adjusted(0.8, 0.8, -0.8, -0.8)
    if inner.width() > 0 and inner.height() > 0:
        bevel = QLinearGradient(inner.topLeft(), inner.bottomLeft())
        bevel.setColorAt(0.0, QColor(255, 255, 255, 150))
        bevel.setColorAt(0.5, QColor(255, 255, 255, 15))
        bevel.setColorAt(1.0, QColor(0, 0, 0, 110))
        painter.setPen(QPen(QBrush(bevel), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(inner, rad, rad)
    # Mittige Griff-Rille (nur wenn hoch genug) — zwei 1px-Linien (Schatten+Glanz).
    if rf.height() >= 6 and rf.width() >= 10:
        cy = rf.center().y()
        painter.setPen(QPen(QColor(0, 0, 0, 90), 1.0))
        painter.drawLine(QPointF(rf.left() + 4, cy), QPointF(rf.right() - 4, cy))
        painter.setPen(QPen(QColor(255, 255, 255, 55), 1.0))
        painter.drawLine(QPointF(rf.left() + 4, cy - 1.0), QPointF(rf.right() - 4, cy - 1.0))
    painter.restore()


def paint_dial_knob(painter: QPainter, center, radius: float, base: QColor) -> None:
    """Plastische Dreh-Knopf-Flaeche (Kreis) HINTER Arcs/Nadel — VC3D-02.

    Radialer Verlauf (Lichtquelle oben-links) + Rand-Glanz oben / Schatten unten,
    damit Wert-Arc + Nadel auf einem physisch wirkenden Knopf sitzen. Vor den Arcs
    zeichnen. Reines QPainter."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    cx, cy, r = float(center.x()), float(center.y()), float(radius)
    if r <= 0:
        painter.restore()
        return
    # Radialer Verlauf, Lichtquelle oben-links -> Woelbung.
    rg = QRadialGradient(cx - r * 0.35, cy - r * 0.35, r * 1.4)
    rg.setColorAt(0.0, base.lighter(155))
    rg.setColorAt(0.6, base)
    rg.setColorAt(1.0, base.darker(160))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(rg))
    painter.drawEllipse(QPointF(cx, cy), r, r)
    # Rand: Glanzkante oben, Schattenkante unten (saettigungs-unabhaengig).
    rim = QLinearGradient(cx, cy - r, cx, cy + r)
    rim.setColorAt(0.0, QColor(255, 255, 255, 120))
    rim.setColorAt(0.5, QColor(255, 255, 255, 12))
    rim.setColorAt(1.0, QColor(0, 0, 0, 110))
    painter.setPen(QPen(QBrush(rim), 1.4))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QPointF(cx, cy), max(0.5, r - 0.8), max(0.5, r - 0.8))
    painter.restore()
