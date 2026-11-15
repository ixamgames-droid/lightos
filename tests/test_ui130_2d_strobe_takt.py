"""UI-130: die 2D-Ansicht zeichnet schneller, solange ein Strobe blinkt.

**Befund (Sitzung D, 15.11.2026, echte App, 250 %, 80 Geraete).** Takt 100 ms
und UI-86-Budget 0,25 ergaben bei ~34 ms je Bild 7-8 Bilder/s. Die 2D-Ansicht
zeigte deshalb jeden Strobe ab 5 Hz als dasselbe langsame Blinken (VIZ-104).

**Gemessen** (je 10 s, Bedienungs-Verzug p95 ueberall 29-34 ms):

    Takt / Budget    Bilder/s   UI-Thread-Anteil
    100 ms / 0,25      7,4          0,25   (bisher)
     50 ms / 0,40     13,6          0,48
     50 ms / 0,50     16,0          0,58
     33 ms / 1,00     21,3          0,76

**Nach dem Bau** (68 blinkende Geraete, Strobe ~10 Hz): bisher 4,9-6,4
Bilder/s. Mit 0,40 10-12 Bilder/s, Anteil 0,45 - nach einmal geoeffnetem
3D-Fenster aber 0,62, weil ein Bild dann ~60 statt ~40 ms kostet und das
Budget nur paintEvent misst. Mit 0,33 (Strobe-Takt) 8 Bilder/s, Anteil
0,30-0,37.

Vorgabe der Leitung: nur unter 0,5 und adaptiv. Deshalb gilt der schnellere
Takt nur, solange ein Geraet sichtbar blinkt (und noch 1 s danach), und nie
bei sichtbarem 3D-Fenster - das setzt sein Bild im selben UI-Thread zusammen
(VIZ-70) und zeigt den Strobe selbst.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMainWindow             # noqa: E402

from src.ui.views import live_view                                  # noqa: E402

_app = QApplication.instance() or QApplication([])


class VisualizerWindow(QMainWindow):
    """Stellvertreter: die Ansicht erkennt das 3D-Fenster am Klassennamen."""


class StrobeTaktTest(unittest.TestCase):

    def setUp(self):
        c = live_view.StageCanvas()
        c._update_timer.stop()               # Takt hier von Hand
        self.zeit = [100.0]
        c._uhr = lambda: self.zeit[0]
        self.addCleanup(c.deleteLater)
        self.c = c

    def _blinkt(self, hz=5.0):
        """Ein Geraet blinkt im Bild - derselbe Weg wie beim Zeichnen
        (Rechteck-Effekt auf dem Dimmer, ohne Shutter-Kanal)."""
        leer = {"strobe": [], "uni": 1, "fp": (42,)}
        return self.c._strobe_aus_steckbrief(leer, lambda _u, _a: 0, {"square": {42: hz}})

    def test_ohne_strobe_wie_bisher(self):
        c = self.c
        self.assertEqual(c._takt_ms(), c.RENDER_INTERVAL_MS)
        self.assertEqual(c._takt_ms(), 100)
        self.assertEqual(c._ui_anteil(), c.MAX_UI_ANTEIL)

    def test_blinkendes_geraet_schaltet_den_strobe_takt_ein(self):
        c = self.c
        self._blinkt()
        self.assertEqual(c._takt_ms(), c.STROBE_TAKT_MS)
        self.assertEqual(c._ui_anteil(), c.STROBE_UI_ANTEIL)
        self.assertLess(c.STROBE_UI_ANTEIL, 0.5, "Vorgabe: UI-Thread-Anteil unter 0,5")

    def test_nachlauf_dann_wieder_grundtakt(self):
        c = self.c
        self._blinkt()
        self.zeit[0] += c.STROBE_NACHLAUF_S - 0.1
        self.assertEqual(c._takt_ms(), c.STROBE_TAKT_MS)
        self.zeit[0] += 0.2
        self.assertEqual(c._takt_ms(), c.RENDER_INTERVAL_MS)

    def test_dauerlicht_schaltet_nicht_um(self):
        c = self.c
        leer = {"strobe": [], "uni": 1, "fp": (42,)}
        self.assertEqual(c._strobe_aus_steckbrief(leer, lambda _u, _a: 0, {"square": {}}),
                         (0.0, True))
        self.assertEqual(c._takt_ms(), c.RENDER_INTERVAL_MS)

    def test_nicht_bei_sichtbarem_3d_fenster(self):
        c = self.c
        w = VisualizerWindow()
        w.show()
        self.addCleanup(w.deleteLater)
        self.addCleanup(w.close)
        QApplication.processEvents()
        self._blinkt()
        self.assertEqual(c._takt_ms(), c.RENDER_INTERVAL_MS)
        w.hide()
        QApplication.processEvents()
        self.zeit[0] += c.DREID_PRUEF_S          # gemerkt, s. naechster Test
        self.assertEqual(c._takt_ms(), c.STROBE_TAKT_MS)

    def test_3d_fenster_wird_nicht_je_geraet_gesucht(self):
        """Nachmessung in der echten App (15.11., 68 blinkende Geraete): je
        Geraet und Bild fragte ``_blink_an`` -> ``_strobe_bildrate`` ->
        ``_takt_ms``/``_ui_anteil`` nach dem 3D-Fenster, und jede Frage lief
        ueber alle Top-Level-Fenster. Ein Bild kostete so 70-95 statt ~40 ms,
        und die 2D-Ansicht zeichnete WENIGER Bilder als ohne UI-130."""
        c = self.c
        n = [0]
        echt = QApplication.topLevelWidgets

        def zaehlen():
            n[0] += 1
            return echt()

        with mock.patch.object(QApplication, "topLevelWidgets", side_effect=zaehlen):
            for _ in range(68):                  # ein Bild, 68 blinkende Geraete
                self._blinkt()
                c._strobe_bildrate()
            self.assertLessEqual(n[0], 1, f"{n[0]} Suchen in einem Bild")
            self.zeit[0] += c.DREID_PRUEF_S
            c._takt_ms()
            self.assertEqual(n[0], 2, "nach DREID_PRUEF_S wird wieder gesucht")

    def test_budget_haelt_den_anteil_unter_der_vorgabe(self):
        """Bei 34 ms je Bild (gemessen, 250 %): Abstand = 34 / 0,33 = 103 ms."""
        c = self.c
        c._zeichenzeiten.extend([0.034] * 5)
        self._blinkt()
        abstand = c._bild_abstand_s()
        self.assertAlmostEqual(abstand, 0.034 / c.STROBE_UI_ANTEIL, places=4)
        self.assertLess(0.034 / abstand, 0.5)
        self.assertAlmostEqual(c._strobe_bildrate(), 1.0 / abstand, places=4)
        # ohne Strobe wie bisher: 34 / 0,25 = 136 ms
        self.zeit[0] += c.STROBE_NACHLAUF_S + 1.0
        self.assertAlmostEqual(c._bild_abstand_s(), 0.034 / c.MAX_UI_ANTEIL, places=4)

    def test_zeitgeber_folgt_dem_takt(self):
        c = self.c
        c._darf_zeichnen = lambda: True
        c._animiert = True
        c._update_timer.setInterval(c.RENDER_INTERVAL_MS)
        self._blinkt()
        c._on_render_tick()
        self.assertEqual(c._update_timer.interval(), c.STROBE_TAKT_MS)
        self.zeit[0] += c.STROBE_NACHLAUF_S + 1.0
        c._naechstes_bild = 0.0
        c._on_render_tick()
        self.assertEqual(c._update_timer.interval(), c.RENDER_INTERVAL_MS)


if __name__ == "__main__":
    unittest.main()
