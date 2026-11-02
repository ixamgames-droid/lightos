"""UI-90: Bildvergleich mit Toleranz fuer die skalierten Kachelwege der 2D-Ansicht.

Grenze (Entscheidung von A, 01.11.2026): hoechstens ``MAX_STUFE`` Stufen je
Kanal UND hoechstens ``MAX_ANTEIL`` der Pixel abweichend, und zwar nur an
Kanten. Verglichen wird immer gegen den direkten Zeichenweg. Ungeskaliert
(Zoom 1, Pixeldichte 1) bleibt der Kachel-Cache bitgleich — dafuer gilt
weiter ``==``.

UI-109: „nur Kanten“ wird jetzt auch geprueft (``MAX_INNEN``). Der Anteil
allein zaehlt ueber das ganze Testbild; ein kleines Symbol, das komplett um 2
Stufen falsch war, blieb darunter (0,76 % bei Zoom 1,37). Eine Kante ist ein
Pixel der Referenz, das sich von mindestens einem seiner 8 Nachbarn
unterscheidet — gleichmaessige Flaechen sind also streng, Kantenpixel und
Verlaeufe duerfen um bis zu ``MAX_STUFE`` abweichen. Gemessen ueber alle
UI-90-Faelle (Glow, Gehaeuse, Ring, alle Symbole bei 250 %): 0 Abweichungen
abseits einer Kante.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage

MAX_STUFE = 2
MAX_ANTEIL = 0.02
MAX_INNEN = 0


def _feld(img: QImage) -> np.ndarray:
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()
    roh = np.frombuffer(img.constBits(), dtype=np.uint8, count=img.sizeInBytes())
    return roh.reshape(h, img.bytesPerLine())[:, : w * 4].reshape(h, w, 4).astype(np.int16)


def _kanten(f: np.ndarray) -> np.ndarray:
    """Pixel, die sich von mindestens einem ihrer 8 Nachbarn unterscheiden."""
    h, w, _ = f.shape
    p = np.pad(f, ((1, 1), (1, 1), (0, 0)), mode="edge")
    k = np.zeros((h, w), dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                k |= (f != p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]).any(axis=2)
    return k


def abweichung(a: QImage, b: QImage) -> tuple[int, float, int]:
    """(groesste Abweichung je Kanal, Anteil abweichender Pixel, abweichende
    Pixel abseits jeder Kante der Referenz ``a``)."""
    assert (a.width(), a.height()) == (b.width(), b.height()), "verschiedene Groessen"
    fa = _feld(a)
    d = np.abs(fa - _feld(b))
    pixel = d.max(axis=2)
    innen = int(((pixel > 0) & ~_kanten(fa)).sum())
    return int(pixel.max()), float((pixel > 0).mean()), innen


def innerhalb(a: QImage, b: QImage, max_stufe: int = MAX_STUFE,
              max_anteil: float = MAX_ANTEIL, max_innen: int = MAX_INNEN) -> tuple[bool, str]:
    stufe, anteil, innen = abweichung(a, b)
    ok = stufe <= max_stufe and anteil <= max_anteil and innen <= max_innen
    return ok, (f"max {stufe} Stufen, {anteil * 100:.3f} % der Pixel abweichend, "
                f"{innen} davon abseits einer Kante")
