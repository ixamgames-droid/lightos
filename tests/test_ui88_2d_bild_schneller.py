"""UI-88: ein Bild der 2D-Ansicht kostet bei hoher Pixeldichte deutlich weniger.

Gemessen bei 250 % Skalierung (RX-580-PC, Buehnen-Show mit 80 Geraeten,
laufende Effekte): 59–98 ms je Bild, davon 40 ms in 278 ``drawEllipse``. Der
Kachel-Cache aus VIZ-78 gilt nur ohne skalierte Umlenkung — bei jeder
Pixeldichte ungleich 1 fiel er komplett aus (0 Treffer).

Abgesichert:

* **Zwischenbild in Geraetepixeln.** Bei Pixeldichte != 1 zeichnet die Flaeche
  in ein eigenes Bild (Pixeldichte als gewoehnliche Skalierung) und legt es 1:1
  auf das Fenster. Dort greift der Kachel-Cache wieder — bitgleich zum direkten
  Zeichnen in dieses Bild.
* **Einrasten.** Im Zwischenbild sitzt jedes Symbol auf ganzen Geraetepixeln,
  damit gleiche Formen dieselbe Kachel treffen.
* **Hintergrund als Kopie.** Der Hintergrund-Cache kommt ohne Qts Weg fuer
  skalierte Bilder ins Zwischenbild — mit demselben Ergebnis.
* **Steckbriefe gestaffelt.** Nach dem Hoechstalter baut nicht mehr EIN Bild
  alle Steckbriefe neu (einmal je Sekunde ein doppelt so langes Bild), sondern
  jedes Bild hoechstens einen Teil.
* **Pixeldichte 1 unveraendert:** kein Zwischenbild, gleicher Weg wie bisher.
"""
import os
import random
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from _qt_lifecycle import destroy_all_top_level_widgets

import src.ui.views.live_view as LV
from test_viz78_liveview_zeichnen import (      # noqa: E402
    _KANAELE, _OmAttrappe, _UniGetAll, _fixture)

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(_app)


_TYPEN = ("par", "par", "par", "moving_head", "moving_head", "led_bar", "spider",
          "strobe", "laser", "hazer", "par", "par")


class _Fall(unittest.TestCase):
    DPR = 2.5

    def setUp(self):
        self.c = LV.StageCanvas()
        self.addCleanup(self.c.deleteLater)
        self.c._update_timer.stop()
        self.aufrufe = []
        orig_k = LV.get_channels_for_patched

        def kanaele(f):
            self.aufrufe.append(f.fid)
            return _KANAELE
        LV.get_channels_for_patched = kanaele
        self.addCleanup(setattr, LV, "get_channels_for_patched", orig_k)
        st = self.c._state
        self.addCleanup(setattr, st, "universes", st.universes)
        self.addCleanup(setattr, st, "output_manager", st.output_manager)
        st.output_manager = _OmAttrappe()
        self.addCleanup(vars(st).pop, "get_patched_fixtures", None)
        # Feste Uhr: Pulsring und Blinkphase aendern sich sonst von Bild zu Bild.
        import time as _time
        LV.time = SimpleNamespace(time=lambda: 1000.25, monotonic=_time.monotonic,
                                  perf_counter=_time.perf_counter)
        self.addCleanup(setattr, LV, "time", _time)
        LV._kacheln_leeren()
        self.addCleanup(LV._kacheln_leeren)
        for k in LV._KACHEL_STATS:
            LV._KACHEL_STATS[k] = 0

    def _szene(self, typen=_TYPEN, lage=None, werte=None, groesse=(420, 300)):
        fxs = [_fixture(i + 1, address=1 + 10 * i, fixture_type=t)
               for i, t in enumerate(typen)]
        self.c._state.get_patched_fixtures = lambda: fxs
        self.c._positions = lage or {
            f.fid: (40.0 + 61.3 * (i % 6), 70.0 + 113.7 * (i // 6) + 7.9 * (i % 3))
            for i, f in enumerate(fxs)}
        self.c._compute_label_gaps()
        self.c._state.universes = {1: _UniGetAll(werte or {})}
        self.c.resize(*groesse)
        return fxs

    def _dichte(self, dpr=None):
        self.c.devicePixelRatioF = lambda: (self.DPR if dpr is None else dpr)

    def _bild(self) -> QImage:
        """Ein volles Bild zeichnen und das Zwischenbild (Kopie) liefern."""
        self.c.grab()
        self.assertIsNotNone(self.c._zb, "kein Zwischenbild")
        return self.c._zb.copy()


class ZwischenbildTest(_Fall):

    def test_bei_pixeldichte_1_kein_zwischenbild(self):
        """Der Weg bei 100 % bleibt, wie er war."""
        self._szene()
        self.c.grab()
        self.assertIsNone(self.c._zb)
        self.assertIsNone(self.c._zwischenbild(self.c.rect()))

    def test_zwischenbild_liegt_in_geraetepixeln(self):
        self._szene(groesse=(420, 300))
        for dpr in (1.25, 1.5, 2.0, 2.5, 3.0):
            with self.subTest(dpr=dpr):
                self._dichte(dpr)
                bild = self._bild()
                self.assertEqual((bild.width(), bild.height()),
                                 (round(self.c.width() * dpr), round(self.c.height() * dpr)))
                self.assertEqual(bild.format(), QImage.Format.Format_RGB32)
                # Nach dem Vorlegen traegt es wieder Pixeldichte 1 (Ziel des Painters).
                self.assertEqual(self.c._zb.devicePixelRatio(), 1.0)
                self.c._zb = None

    def test_ausschnitt_mit_krummer_lage_deckt_den_bereich(self):
        """Bereich (3, 5, 101, 77) bei 2,5: Geraetepixel 7..260 x 12..205."""
        self._dichte(2.5)
        img, x0, y0, dpr = self.c._zwischenbild(QRect(3, 5, 101, 77))
        self.assertEqual((x0, y0, dpr), (7, 12, 2.5))
        self.assertEqual((img.width(), img.height()), (260 - 7, 205 - 12))

    def test_zu_grosser_bereich_zeichnet_direkt(self):
        self._szene()
        self._dichte()
        self.c.ZWISCHENBILD_MAX_PIXEL = 1000
        self.assertIsNone(self.c._zwischenbild(self.c.rect()))
        bild = self.c.grab()
        self.assertFalse(bild.isNull())
        self.assertIsNone(self.c._zb)

    def test_abschaltbar(self):
        self._szene()
        self._dichte()
        self.c.ZWISCHENBILD_MAX_PIXEL = 0
        self.c.grab()
        self.assertIsNone(self.c._zb)

    def test_teil_repaint_behaelt_das_grosse_bild(self):
        """Ein Teil-Repaint (unter der Minimap) nimmt ein Wegwerf-Bild — das
        Bild fuer den vollen Takt wird nicht bei jedem Wechsel neu angelegt."""
        self._szene()
        self._dichte()
        self._bild()
        gross = self.c._zb
        klein = self.c._zwischenbild(QRect(10, 10, 60, 40))[0]
        self.assertIsNot(klein, gross)
        self.assertIs(self.c._zb, gross)
        self.assertIs(self.c._zwischenbild(self.c.rect())[0], gross)


class KachelnImZwischenbildTest(_Fall):

    def test_cache_greift_bei_hoher_pixeldichte(self):
        """Der Befund: bei Pixeldichte != 1 gab es keinen einzigen Treffer."""
        self._szene(typen=("par",) * 12, werte={i: 200 for i in range(1, 130)})
        self._dichte()
        for _ in range(3):
            self.c.grab()
        self.assertGreater(LV._KACHEL_STATS["treffer"], 30, LV._KACHEL_STATS)
        self.assertGreater(LV._KACHEL_STATS["gebaut"], 0)

    def test_bild_mit_und_ohne_cache_gleich(self):
        """Bitgleich: Kacheln im Zwischenbild == direkt ins Zwischenbild."""
        rnd = random.Random(88)
        self._szene()
        self.c.set_selection([4])
        for dpr in (1.25, 1.5, 2.0, 2.5):
            self._dichte(dpr)
            for zoom in (1.0, 0.75, 2.24):
                self.c.set_zoom(zoom)
                werte = {i: rnd.randrange(256) for i in range(1, 130)}
                self.c._state.universes = {1: _UniGetAll(werte)}
                alt = LV.KACHEL_AB
                LV.KACHEL_AB = 10 ** 9          # nie bauen -> alles direkt
                try:
                    LV._kacheln_leeren()
                    ref = self._bild()
                finally:
                    LV.KACHEL_AB = alt
                vor = LV._KACHEL_STATS["treffer"]
                self._bild()
                self._bild()
                bild = self._bild()
                with self.subTest(dpr=dpr, zoom=zoom):
                    self.assertGreater(LV._KACHEL_STATS["treffer"], vor)
                    self.assertTrue(ref == bild)

    def test_symbole_rasten_auf_ganze_geraetepixel(self):
        """Lage 100,0 und 100,1 (250,0 / 250,25 Geraetepixel) ergeben dasselbe
        Bild; 100,3 (250,75) liegt genau einen Geraetepixel weiter rechts."""
        self._dichte(2.5)
        self.c.grid_visible = False           # Raster verschiebt sich nicht mit

        def bild(x):
            self._szene(typen=("par",), lage={1: (x, 60.0)},
                        werte={i: 180 for i in range(1, 12)}, groesse=(220, 140))
            return self._bild()
        a, b, c = bild(100.0), bild(100.1), bild(100.3)
        leer = bild(-500.0)                   # Geraet ausserhalb: nur Hintergrund
        self.assertTrue(a == b)
        self.assertFalse(a == c)
        # Nur das Symbol (Abweichung vom Hintergrund) vergleichen: derselbe
        # Umriss, genau einen Geraetepixel weiter rechts.
        w, h = a.width(), a.height()

        def symbol(img):
            return {(x, y): img.pixel(x, y) for y in range(h) for x in range(w)
                    if img.pixel(x, y) != leer.pixel(x, y)}
        sa, sc = symbol(a), symbol(c)
        self.assertGreater(len(sa), 2000, "Symbol nicht im Bild")
        self.assertEqual({(x + 1, y): p for (x, y), p in sa.items()}, sc)

    def test_hintergrund_als_kopie_gleich_dem_alten_weg(self):
        self._szene()
        for dpr in (1.25, 1.5, 2.0, 2.5):
            self._dichte(dpr)
            for zoom in (1.0, 1.7):
                self.c.set_zoom(zoom)
                neu = self._bild()
                self.assertIsNotNone(self.c._bg_pixmap, "Hintergrund-Cache aus")
                self.assertEqual(self.c._bg_pixmap.devicePixelRatio(), dpr)
                orig = self.c._hintergrund_1zu1
                self.c._hintergrund_1zu1 = lambda p, bg: False
                try:
                    alt = self._bild()
                finally:
                    self.c._hintergrund_1zu1 = orig
                with self.subTest(dpr=dpr, zoom=zoom):
                    self.assertTrue(alt == neu)


class SteckbriefGestaffeltTest(_Fall):
    """Nach dem Hoechstalter baut ein Bild nur einen Teil der Steckbriefe neu."""
    N = 40

    def _altern(self):
        self.c._steckbrief_zeit -= self.c.STECKBRIEF_MAX_ALTER_S + 0.5

    def test_ein_bild_frischt_nur_einen_teil_auf(self):
        self._szene(typen=("par",) * self.N, groesse=(420, 900))
        self.c.grab()
        self.assertEqual(sorted(self.aufrufe), list(range(1, self.N + 1)))
        self.aufrufe.clear()
        self.c.grab()
        self.assertEqual(self.aufrufe, [], "frische Steckbriefe werden nicht neu gebaut")
        self._altern()
        self.c.grab()
        je_bild = -(-self.N // self.c.STECKBRIEF_BILDER)
        self.assertEqual(len(self.aufrufe), je_bild)

    def test_nach_wenigen_bildern_sind_alle_frisch(self):
        self._szene(typen=("par",) * self.N, groesse=(420, 900))
        self.c.grab()
        self.aufrufe.clear()
        self._altern()
        for _ in range(self.c.STECKBRIEF_BILDER):
            self.c.grab()
        self.assertEqual(sorted(self.aufrufe), list(range(1, self.N + 1)),
                         "jeder genau einmal, keiner doppelt")
        self.aufrufe.clear()
        self.c.grab()
        self.assertEqual(self.aufrufe, [])

    def test_patch_aenderung_baut_sofort_alle_neu(self):
        """Das Ereignis verwirft wie bisher alles — ohne Staffelung."""
        self._szene(typen=("par",) * self.N, groesse=(420, 900))
        self.c.grab()
        self.aufrufe.clear()
        self.c._patch_geaendert()
        self.c.grab()
        self.assertEqual(len(self.aufrufe), self.N)

    def test_geaenderter_fingerabdruck_wartet_nicht_auf_die_staffel(self):
        fxs = self._szene(typen=("par",) * self.N, groesse=(420, 900))
        self.c.grab()
        self.aufrufe.clear()
        for f in fxs:
            f.address += 1
        self.c.grab()
        self.assertEqual(len(self.aufrufe), self.N)


if __name__ == "__main__":
    unittest.main()
