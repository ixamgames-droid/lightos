"""UI-90: neue Kachelwege der 2D-Ansicht bei Skalierung (Zoom/Pixeldichte != 1).

1. **Glow-Verlaeufe** kommen auch skaliert aus dem Kachel-Cache (vorher bei
   jedem Bild neu gerastert: ~40 je Bild bei 250 %).
2. **Fuellung + Kontur** einer Form liegen skaliert in EINER Kachel (ein
   Aufblenden statt zwei; ~150 solcher Formen je Bild bei 250 %).

Beides ist nicht mehr bitgleich zum direkten Zeichnen (Rundung der Verlaufs-
Rueckrechnung, Mischreihenfolge an Kantenpixeln). Erlaubt hat A: hoechstens
2 Stufen je Kanal UND hoechstens 2 % der Pixel abweichend, verglichen mit dem
direkten Weg (``tests/_bild_toleranz.py``). Ungeskaliert bleibt alles bitgleich
(VIZ-78). Die Gegenproben belegen, dass der Toleranz-Vergleich echte Fehler
— falsche Farbe, verschobene Kachel, veralteter Cache — weiterhin findet.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import src.ui.views.live_view as LV  # noqa: E402
from _bild_toleranz import innerhalb  # noqa: E402

_app = QApplication.instance() or QApplication([])

# 250 % Pixeldichte × Zoom 2,24 = 5,6 (wie in der App gemessen) und Zwischenstufen
ZOOMS = (0.75, 1.37, 2.5, 5.6)
LAGEN = ((60.0, 60.0), (60.5, 61.25), (73.37, 57.81))
_BG = None


def _bg() -> QImage:
    global _BG
    if _BG is None:
        _BG = QImage(300, 260, QImage.Format.Format_RGB32)
        _BG.fill(QColor(28, 30, 34))
    return _BG


def _male(fn, zoom, lage, kachel=True) -> QImage:
    img = _bg().copy()
    p = QPainter(img)
    try:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(zoom, zoom)
        p.translate(lage[0] / zoom, lage[1] / zoom)
        fn(p, LV._kachel_kontext(p) if kachel else None)
    finally:
        p.end()
    return img


def _glow(farbe=QColor(200, 40, 90)):
    stops = ((0, farbe.lighter(180)), (0.6, farbe),
             (1, QColor(farbe.red(), farbe.green(), farbe.blue(), 100)))
    br, bk = LV._verlauf(0, 0, 13.5, stops)
    return lambda p, kx: LV._form(p, kx, "e", LV._ellipse(0, 0, 12, 12), None, br, None, bk)


def _gehaeuse(farbe="#161616"):
    pen, br, pk, bk = LV._pb(farbe, "#555", 1.5)
    return lambda p, kx: LV._form(p, kx, "rr", (-28.5, -9.0, 57.0, 18.0, 4, 4), pen, br, pk, bk)


def _ring_mit_fuellung(farbe=QColor(220, 60, 30)):
    pen, pk = LV._stift(QColor(255, 255, 255, 180), 2)
    br, bk = LV._pinsel(farbe)
    return lambda p, kx: LV._form(p, kx, "e", LV._ellipse(0, 0, 10, 10), pen, br, pk, bk)


def _warm_und_vergleich(fn, zoom, lage):
    """(direkt, Kachel) — erst nach KACHEL_AB Vorkommen kommt die Kachel."""
    ref = _male(fn, zoom, lage, kachel=False)
    for _ in range(LV.KACHEL_AB):
        _male(fn, zoom, lage)
    return ref, _male(fn, zoom, lage)


class KachelwegeTest(unittest.TestCase):

    def setUp(self):
        LV._kacheln_leeren()

    def test_glow_kommt_skaliert_aus_der_kachel(self):
        for zoom in ZOOMS:
            for lage in LAGEN:
                with self.subTest(zoom=zoom, lage=lage):
                    LV._kacheln_leeren()
                    t0 = LV._KACHEL_STATS["treffer"]
                    ref, img = _warm_und_vergleich(_glow(), zoom, lage)
                    self.assertGreater(LV._KACHEL_STATS["treffer"], t0, "keine Kachel benutzt")
                    ok, info = innerhalb(ref, img)
                    self.assertTrue(ok, info)

    def test_fuellung_und_kontur_in_einer_kachel(self):
        for fn in (_gehaeuse(), _ring_mit_fuellung()):
            for zoom in ZOOMS:
                for lage in LAGEN:
                    with self.subTest(zoom=zoom, lage=lage):
                        LV._kacheln_leeren()
                        ref, img = _warm_und_vergleich(fn, zoom, lage)
                        schluessel = [k[2][0] for k in LV._KACHELN]
                        self.assertEqual(schluessel, ["bp"], schluessel)
                        t0 = LV._KACHEL_STATS["treffer"]
                        _male(fn, zoom, lage)
                        self.assertEqual(LV._KACHEL_STATS["treffer"], t0 + 1,
                                         "eine Form = ein Aufblenden")
                        ok, info = innerhalb(ref, img)
                        self.assertTrue(ok, info)

    def test_ungeskaliert_bitgleich_und_zwei_durchgaenge(self):
        for fn in (_glow(), _gehaeuse(), _ring_mit_fuellung()):
            for lage in LAGEN:
                with self.subTest(lage=lage):
                    LV._kacheln_leeren()
                    ref, img = _warm_und_vergleich(fn, 1.0, lage)
                    self.assertTrue(ref == img, "Zoom 1 muss bitgleich bleiben")
                    self.assertNotIn("bp", [k[2][0] for k in LV._KACHELN])

    def test_alle_symbole_bei_250_prozent_innerhalb_der_grenze(self):
        typen = ("par", "moving_head", "wash", "spot", "led_bar", "strobe", "dimmer",
                 "laser", "scanner", "blinder", "spider", "par_bar", "mover_bar", "other")

        def symbol(ft):
            def fn(p, _kx):
                LV.FixtureRenderer.draw(p, ft, 0, 0, 30, QColor(220, 60, 30), 255, "7",
                                        zoom=5.6, ring_segments=12, effects=["Chase"],
                                        selected=True)
            return fn

        orig = LV._kachel_kontext
        for ft in typen:
            with self.subTest(typ=ft):
                LV._kachel_kontext = lambda _p: None
                try:
                    ref = _male(symbol(ft), 5.6, (150.37, 130.6))
                finally:
                    LV._kachel_kontext = orig
                LV._kacheln_leeren()
                for _ in range(LV.KACHEL_AB):
                    _male(symbol(ft), 5.6, (150.37, 130.6))
                img = _male(symbol(ft), 5.6, (150.37, 130.6))
                ok, info = innerhalb(ref, img)
                self.assertTrue(ok, f"{ft}: {info}")


class GegenprobeTest(unittest.TestCase):
    """Der Toleranz-Vergleich muss echte Cache-Fehler weiterhin rot melden."""

    def setUp(self):
        LV._kacheln_leeren()

    def tearDown(self):
        LV._kacheln_leeren()

    def test_falsche_farbe_in_der_kachel_faellt_auf(self):
        orig = LV._form_direkt

        def falsch(painter, art, geo, pen, brush):
            # nur beim Bau einer Kachel (anderes Bild als der Hintergrund)
            if painter.device().size() != _bg().size() and brush is not None:
                c = QColor(brush.color())
                brush = type(brush)(QColor(min(255, c.red() + 12), c.green(), c.blue(), c.alpha()))
            orig(painter, art, geo, pen, brush)
        for fn in (_gehaeuse(), _ring_mit_fuellung()):
            LV._kacheln_leeren()
            ref = _male(fn, 5.6, LAGEN[1], kachel=False)
            LV._form_direkt = falsch
            try:
                for _ in range(LV.KACHEL_AB + 1):
                    img = _male(fn, 5.6, LAGEN[1])
            finally:
                LV._form_direkt = orig
            ok, info = innerhalb(ref, img)
            self.assertFalse(ok, f"falsche Farbe nicht erkannt ({info})")

    def test_verschobene_kachel_faellt_auf(self):
        for fn in (_glow(), _gehaeuse()):
            LV._kacheln_leeren()
            ref, _img = _warm_und_vergleich(fn, 5.6, LAGEN[2])
            for k, img in list(LV._KACHELN.items()):
                LV._KACHELN[k] = img.copy(QRect(-1, 0, img.width(), img.height()))
            ok, info = innerhalb(ref, _male(fn, 5.6, LAGEN[2]))
            self.assertFalse(ok, f"um 1 Pixel verschobene Kachel nicht erkannt ({info})")

    def test_veralteter_cache_faellt_auf(self):
        orig = LV._ck
        LV._ck = lambda _c: (1, 2, 3, 4)          # alle Farben teilen einen Schluessel
        try:
            rot, blau = _ring_mit_fuellung(QColor(220, 40, 40)), _ring_mit_fuellung(QColor(40, 60, 230))
            for _ in range(LV.KACHEL_AB + 1):
                _male(rot, 5.6, LAGEN[0])
            img = _male(blau, 5.6, LAGEN[0])     # trifft die rote Kachel
        finally:
            LV._ck = orig
        ok, info = innerhalb(_male(blau, 5.6, LAGEN[0], kachel=False), img)
        self.assertFalse(ok, f"veralteter Cache nicht erkannt ({info})")


if __name__ == "__main__":
    unittest.main()
