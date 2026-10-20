"""UI-105: Geraetenummer und Kurzname im Gruppen-Raster ueberlappen nicht.

Bis 2026-10-20 zeichnete ``FixtureGridWidget.paintEvent`` die Nummer mittig in
die Zelle und den Kurznamen mittig in dasselbe Rechteck, nur 14 px tiefer
gerechnet (also 7 px versetzt) — beide lagen in jeder Zellgroesse uebereinander.
Jetzt kommt die Lage aus ``zell_text_rechtecke`` (Hoehen aus den fontMetrics).

Geprueft wird bei 100/125/150 % Schrift-Skalierung (Punktgroesse x Faktor, so
wie Windows die logische DPI anhebt) und ueber kleine bis grosse Zellen:
- passt beides, ueberlappen die Rechtecke nicht und liegen in der Zelle;
- ist die Zelle zu klein, entfaellt der Kurzname (die Nummer bleibt);
- Gegenprobe: die alte Rechnung ueberlappt in genau diesen Faellen — der
  Ueberlappungs-Test erkennt den Fehler also wirklich;
- das paintEvent nutzt die neue Lage (kein fester 14-px-Versatz mehr).
"""
from __future__ import annotations

import inspect
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication

from src.ui.views.fixture_group_view import FixtureGridWidget

_app = QApplication.instance() or QApplication([])

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


SKALEN = (1.0, 1.25, 1.5)
ZELLEN = (16, 24, 28, 32, 40, 48, 64, 96, 160)   # Zellkante in px (vor dem 2-px-Rand)


def _fonts(f: float):
    big = QFont("Segoe UI")
    big.setPointSizeF(9 * f)
    big.setBold(True)
    small = QFont("Segoe UI")
    small.setPointSizeF(7 * f)
    return big, small


def _text_rect(rect: QRect, font: QFont) -> QRect:
    """Wo ein mittig ausgerichteter Einzeiler in ``rect`` tatsaechlich steht
    (Hoehe aus den fontMetrics, senkrecht zentriert)."""
    h = QFontMetrics(font).height()
    return QRect(rect.x(), rect.y() + (rect.height() - h) // 2, rect.width(), h)


def _alte_lage(rect: QRect, big: QFont, small: QFont):
    """Die Rechnung bis 2026-10-20 (paintEvent: Name 14 px tiefer, 14 px kuerzer)."""
    alt_small = QRect(rect.x(), rect.y() + 14, rect.width(), rect.height() - 14)
    return _text_rect(rect, big), _text_rect(alt_small, small)


class ZellTextLageTest(unittest.TestCase):
    def test_keine_ueberlappung_bei_allen_skalen_und_zellgroessen(self):
        for f in SKALEN:
            big, small = _fonts(f)
            for kante in ZELLEN:
                with self.subTest(skala=f, zelle=kante):
                    cell = QRect(2, 2, kante - 4, kante - 4)
                    b, s = FixtureGridWidget.zell_text_rechtecke(cell, big, small)
                    self.assertGreaterEqual(b.height(), QFontMetrics(big).height())
                    if s is None:
                        continue
                    self.assertFalse(b.intersects(s), f"{b} schneidet {s}")
                    self.assertTrue(cell.contains(b) and cell.contains(s),
                                    f"{b}/{s} ausserhalb {cell}")
                    self.assertEqual(s.height(), QFontMetrics(small).height())

    def test_zu_kleine_zelle_laesst_namen_weg(self):
        for f in SKALEN:
            big, small = _fonts(f)
            hb, hs = QFontMetrics(big).height(), QFontMetrics(small).height()
            cell = QRect(0, 0, 60, hb + hs - 1)
            b, s = FixtureGridWidget.zell_text_rechtecke(cell, big, small)
            self.assertIsNone(s, f"Skala {f}: Name muss entfallen")
            self.assertEqual(b.center().y(), cell.center().y())
            # genau passend: beide da
            cell = QRect(0, 0, 60, hb + hs)
            self.assertIsNotNone(FixtureGridWidget.zell_text_rechtecke(cell, big, small)[1])

    def test_grosse_zelle_zeigt_beides(self):
        for f in SKALEN:
            big, small = _fonts(f)
            b, s = FixtureGridWidget.zell_text_rechtecke(QRect(2, 2, 92, 92), big, small)
            self.assertIsNotNone(s)
            self.assertLess(b.bottom(), s.top())

    def test_gegenprobe_alte_lage_ueberlappt(self):
        """Die alte Rechnung faellt durch denselben Ueberlappungs-Test — in jeder
        Zellgroesse, in der der Name gezeichnet wurde."""
        for f in SKALEN:
            big, small = _fonts(f)
            for kante in ZELLEN:
                cell = QRect(2, 2, kante - 4, kante - 4)
                if cell.height() - 14 <= 0:
                    continue
                b, s = _alte_lage(cell, big, small)
                with self.subTest(skala=f, zelle=kante):
                    self.assertTrue(b.intersects(s), f"alt: {b} / {s}")


class PaintNutztNeueLageTest(unittest.TestCase):
    def _grid(self, kante: int) -> FixtureGridWidget:
        g = FixtureGridWidget()
        g.cols = g.rows = 4
        g.setMinimumSize(0, 0)
        g.resize(kante * 4, kante * 4)
        g.positions = {(0, 0): 1, (1, 0): "2:0"}
        g.update_fixture_labels({1: "Spot links", 2: "LED-Bar"})
        return g

    def test_paint_zeichnet_in_die_berechneten_rechtecke(self):
        for kante in (24, 80):
            g = self._grid(kante)
            echt = FixtureGridWidget.zell_text_rechtecke
            ergebnisse = []

            def spion(rect, big, small):
                r = echt(rect, big, small)
                ergebnisse.append(r)
                return r

            with mock.patch.object(FixtureGridWidget, "zell_text_rechtecke",
                                   staticmethod(spion)):
                g.grab()
            with self.subTest(zelle=kante):
                self.assertEqual(len(ergebnisse), 2)
                for b, s in ergebnisse:
                    if kante >= 80:
                        self.assertIsNotNone(s)
                        self.assertFalse(b.intersects(s))
                    else:
                        self.assertIsNone(s)

    def test_kein_fester_pixelversatz_mehr(self):
        src = inspect.getsource(FixtureGridWidget.paintEvent)
        self.assertNotIn("+ 14", src)
        self.assertNotIn("- 14", src)
        self.assertIn("zell_text_rechtecke", src)


if __name__ == "__main__":
    unittest.main()
