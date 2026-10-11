"""WEB-11: Symbole der Handy-Konsole fuer den Startbildschirm zeichnen.

Erzeugt die PNG-Dateien unter ``src/web/static/icons/`` — selbst gezeichnet,
nach dem Motiv des App-Symbols (Lichtkegel in Farben, drei Leuchtpunkte), keine
fremden Bilder. Vollflaechiger Hintergrund in der Farbe des Pult-Designs: iOS
und Android schneiden die Ecken selbst zu.

    QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/web11_symbole.py
      (Windows: venv/Scripts/python.exe, Linux/macOS: ./venv/bin/python)

Die Dateien sind eingecheckt; das Skript braucht man nur, wenn sich das Motiv
aendern soll.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (QColor, QGuiApplication, QImage, QLinearGradient,
                           QPainter, QPolygonF, QRadialGradient)

ZIEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "src", "web", "static", "icons")

#: Dateiname -> (Kantenlaenge, Anteil der Flaeche, den das Motiv einnimmt).
#: „maskable": Android schneidet bis auf einen Kreis von 80 % zu — das Motiv
#: bleibt deshalb in der sicheren Mitte.
SYMBOLE = {
    "konsole-192.png": (192, 0.86),
    "konsole-512.png": (512, 0.86),
    "konsole-maskable-512.png": (512, 0.60),
    "apple-touch-icon-180.png": (180, 0.82),
}

HINTERGRUND = "#0d1117"
KEGEL = ("#f85149", "#e3b341", "#e6edf3", "#3fb950", "#58a6ff")
PUNKTE = ("#f85149", "#3fb950", "#58a6ff")


def zeichne(kante: int, anteil: float) -> QImage:
    bild = QImage(kante, kante, QImage.Format.Format_RGB32)
    bild.fill(QColor(HINTERGRUND))
    p = QPainter(bild)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    m = kante * anteil                      # Kantenlaenge des Motivs
    x0 = (kante - m) / 2
    y0 = (kante - m) / 2
    spitze = QPointF(kante / 2, y0 + m * 0.20)
    unten = y0 + m * 0.80
    links, rechts = x0 + m * 0.14, x0 + m * 0.86
    breite = (rechts - links) / len(KEGEL)
    for i, farbe in enumerate(KEGEL):
        verlauf = QLinearGradient(spitze, QPointF(kante / 2, unten))
        hell = QColor(farbe)
        hell.setAlphaF(0.95)
        matt = QColor(farbe)
        matt.setAlphaF(0.45)
        verlauf.setColorAt(0.0, hell)
        verlauf.setColorAt(1.0, matt)
        p.setBrush(verlauf)
        p.drawPolygon(QPolygonF([spitze,
                                 QPointF(links + i * breite, unten),
                                 QPointF(links + (i + 1) * breite, unten)]))
    # Lampe: weicher Schein und heller Kern
    schein = QRadialGradient(spitze, m * 0.17)
    schein.setColorAt(0.0, QColor(255, 255, 255, 235))
    schein.setColorAt(0.45, QColor(230, 237, 243, 150))
    schein.setColorAt(1.0, QColor(230, 237, 243, 0))
    p.setBrush(schein)
    p.drawEllipse(spitze, m * 0.17, m * 0.17)
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(spitze, m * 0.055, m * 0.055)
    # drei Leuchtpunkte unter dem Kegel
    r = m * 0.035
    for i, farbe in enumerate(PUNKTE):
        mitte = QPointF(kante / 2 + (i - 1) * m * 0.16, y0 + m * 0.91)
        hof = QColor(farbe)
        hof.setAlphaF(0.35)
        p.setBrush(hof)
        p.drawEllipse(mitte, r * 1.9, r * 1.9)
        p.setBrush(QColor(farbe))
        p.drawEllipse(mitte, r, r)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(mitte, r * 0.45, r * 0.45)
    p.end()
    return bild


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    os.makedirs(ZIEL, exist_ok=True)
    for name, (kante, anteil) in SYMBOLE.items():
        pfad = os.path.join(ZIEL, name)
        if not zeichne(kante, anteil).save(pfad, "PNG"):
            print(f"[web11_symbole] ERROR: {name} nicht geschrieben")
            return 1
        print(f"[web11_symbole] {name}: {kante} x {kante} px")
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
