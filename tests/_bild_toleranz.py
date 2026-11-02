"""UI-90: Bildvergleich mit Toleranz fuer die skalierten Kachelwege der 2D-Ansicht.

Grenze (Entscheidung von A, 01.11.2026): hoechstens ``MAX_STUFE`` Stufen je
Kanal UND hoechstens ``MAX_ANTEIL`` der Pixel abweichend. Verglichen wird
immer gegen den direkten Zeichenweg. Ungeskaliert (Zoom 1, Pixeldichte 1)
bleibt der Kachel-Cache bitgleich — dafuer gilt weiter ``==``.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage

MAX_STUFE = 2
MAX_ANTEIL = 0.02


def _feld(img: QImage) -> np.ndarray:
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()
    roh = np.frombuffer(img.constBits(), dtype=np.uint8, count=img.sizeInBytes())
    return roh.reshape(h, img.bytesPerLine())[:, : w * 4].reshape(h, w, 4).astype(np.int16)


def abweichung(a: QImage, b: QImage) -> tuple[int, float]:
    """(groesste Abweichung je Kanal, Anteil abweichender Pixel)."""
    assert (a.width(), a.height()) == (b.width(), b.height()), "verschiedene Groessen"
    d = np.abs(_feld(a) - _feld(b))
    pixel = d.max(axis=2)
    return int(pixel.max()), float((pixel > 0).mean())


def innerhalb(a: QImage, b: QImage, max_stufe: int = MAX_STUFE,
              max_anteil: float = MAX_ANTEIL) -> tuple[bool, str]:
    stufe, anteil = abweichung(a, b)
    ok = stufe <= max_stufe and anteil <= max_anteil
    return ok, f"max {stufe} Stufen, {anteil * 100:.3f} % der Pixel abweichend"
