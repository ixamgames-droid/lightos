"""UI-86: 2D-Ansicht bei hoher Pixeldichte zeichnet zu teuer.

Gemessen am Windows-Rig mit 200 % Skalierung: ~58 ms je Neuzeichnen der
2D-Ansicht im UI-Thread, bei 10 Bildern/s also mehr als die Haelfte des
Threads. Zwei Ursachen, zwei Absicherungen:

- **Bildrate aus der gemessenen Zeichenzeit.** Der Takt zeichnet nur so oft,
  dass die Zeichenzeit rund ein Viertel des UI-Threads belegt. Haengt allein an
  der gemessenen Zeit (austauschbare Uhr), nicht an Rechner oder Pixeldichte;
  schnelles Zeichnen behaelt die volle Rate.
- **Hintergrund-Cache auf den sichtbaren Ausschnitt.** Bei 200 % ueberschritt
  die ganze Flaeche die Speichergrenze des Caches, er fiel aus und Raster,
  Buehne und Publikum wurden je Bild neu gezeichnet.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QPaintEvent
from PySide6.QtWidgets import QApplication, QScrollArea

from _qt_lifecycle import destroy_all_top_level_widgets

from src.core.app_state import get_state
from src.ui.views import live_view

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(_app)


class _Uhr:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def vor(self, s):
        self.t += s


def _fx(fid, address):
    return SimpleNamespace(fid=fid, universe=1, address=address,
                           label=f"PAR-{fid}", fixture_type="PAR")


class _Fall(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        if 1 not in self.state.universes:
            self.state.universes[1] = self.state.output_manager.add_universe(1)
        self.fixtures = [_fx(1, 1), _fx(2, 11)]
        self.state.get_patched_fixtures = lambda: self.fixtures
        self.addCleanup(lambda: self.state.__dict__.pop("get_patched_fixtures", None))

    def _canvas(self, zoom=1.0, welt=(600, 400)):
        c = live_view.StageCanvas()
        c._update_timer.stop()             # Takt hier von Hand
        c.zoom = zoom
        c.world_w, c.world_h = welt
        c.grid_visible, c.grid_size = True, 50
        c._fixture_size = 30.0
        c._apply_canvas_size()
        c._positions = {1: (150.0, 200.0), 2: (400.0, 200.0)}
        c._nn_gap = {1: 1e9, 2: 1e9}
        c._running_functions = lambda: []
        return c


# ════════════════════════════════════════════════════════════════════════════
# 1. Bildrate aus der gemessenen Zeichenzeit
# ════════════════════════════════════════════════════════════════════════════

class BildrateTest(_Fall):
    def _lauf(self, zeichenzeit_s, sekunden=20.0, animiert=True):
        """Spielt ``sekunden`` Takt-Betrieb mit falscher Uhr durch: jedes vom
        Takt angeforderte Bild kostet ``zeichenzeit_s``. Liefert (Bilder,
        Anteil der Zeichenzeit an der Gesamtzeit)."""
        c = self._canvas()
        c.show()
        _app.processEvents()
        uhr = _Uhr()
        c._uhr = uhr
        c._zeichne = lambda ev, voll=True: uhr.vor(zeichenzeit_s)
        bilder = []

        def _update(*_a):
            bilder.append(uhr.t)
            c.paintEvent(QPaintEvent(c.rect()))
            c._animiert = animiert
        c.update = _update
        c._animiert = animiert
        takt = c.RENDER_INTERVAL_MS / 1000.0
        start = uhr.t
        naechster = start
        while uhr.t - start < sekunden:
            # Der Timer feuert im Raster; ein Bild, das laenger dauert als ein
            # Takt, laesst die verpassten Takte ausfallen (wie QTimer).
            if uhr.t < naechster:
                uhr.t = naechster
            c._on_render_tick()
            while naechster <= uhr.t:
                naechster += takt
        dauer = uhr.t - start
        return bilder, len(bilder) * zeichenzeit_s / dauer

    def test_hidpi_58ms_bleibt_bei_einem_viertel(self):
        bilder, anteil = self._lauf(0.058)
        self.assertLessEqual(anteil, 0.27,
                             f"2D-Ansicht belegt {anteil:.0%} des UI-Threads")
        # ... und bremst nicht staerker als noetig (~4 Bilder/s statt 10).
        self.assertGreaterEqual(anteil, 0.21)
        rate = len(bilder) / 20.0
        self.assertGreater(rate, 3.6)
        self.assertLess(rate, 4.7)

    def test_schnelles_zeichnen_behaelt_volle_rate(self):
        for zeit in (0.002, 0.020, 0.025):
            bilder, _anteil = self._lauf(zeit, sekunden=10.0)
            self.assertGreaterEqual(
                len(bilder), 99,
                f"{zeit * 1000:.0f} ms je Bild darf nicht gebremst werden")

    def test_regel_haengt_nur_an_der_zeit(self):
        for zeit in (0.035, 0.090, 0.150, 0.240):
            _bilder, anteil = self._lauf(zeit)
            self.assertLessEqual(anteil, 0.28, f"{zeit * 1000:.0f} ms je Bild")
            self.assertGreaterEqual(anteil, 0.17, f"{zeit * 1000:.0f} ms je Bild")

    def test_nie_seltener_als_ein_bild_je_sekunde(self):
        bilder, _anteil = self._lauf(0.6, sekunden=30.0)
        abstaende = [b - a for a, b in zip(bilder, bilder[1:])]
        # Abstand = Wartezeit bis zum naechsten Bild; das Bild selbst (0,6 s)
        # blockiert den Thread ohnehin, mehr als die Obergrenze kommt nicht dazu.
        self.assertLessEqual(max(abstaende[3:]), 1.0 + 0.6 + 0.1)

    def test_ausreisser_bremst_nicht(self):
        c = self._canvas()
        uhr = _Uhr()
        c._uhr = uhr
        kosten = [0.003, 0.003, 0.400, 0.003, 0.003]
        c._zeichne = lambda ev, voll=True: uhr.vor(kosten.pop(0))
        for _ in range(5):
            c.paintEvent(QPaintEvent(c.rect()))
        self.assertEqual(c._bild_abstand_s(), 0.0,
                         "ein einzelnes langsames Bild darf die Rate nicht senken")

    def test_aenderung_nach_ruhe_kommt_im_naechsten_takt(self):
        """Die Bremse gilt fuer Dauerlast; eine einzelne Aenderung nach einer
        ruhigen Phase erscheint ohne Zusatzverzoegerung."""
        c = self._canvas()
        c.show()
        _app.processEvents()
        uhr = _Uhr()
        c._uhr = uhr
        c._zeichne = lambda ev, voll=True: uhr.vor(0.058)
        for _ in range(5):
            c.paintEvent(QPaintEvent(c.rect()))
        self.assertGreater(c._bild_abstand_s(), 0.2)
        c._animiert = False
        calls = []
        c.update = lambda *a: calls.append(uhr.t)
        c._on_render_tick()                # erste Signatur
        self.assertEqual(len(calls), 1)
        for _ in range(8):                 # 0,8 s nichts los
            uhr.vor(0.1)
            c._on_render_tick()
        self.assertEqual(len(calls), 1)
        uni = self.state.universes[1]
        alt = uni.get_channel(1)
        self.addCleanup(uni.set_channel, 1, alt)
        uni.set_channel(1, (alt + 77) % 256)
        uhr.vor(0.1)
        c._on_render_tick()
        self.assertEqual(len(calls), 2, "Aenderung muss sofort erscheinen")
        # Die zweite, direkt folgende Aenderung wartet dagegen das Budget ab,
        # geht aber nicht verloren.
        uni.set_channel(1, (alt + 99) % 256)
        uhr.vor(0.1)
        c._on_render_tick()
        self.assertEqual(len(calls), 2)
        uhr.vor(0.1)
        c._on_render_tick()
        self.assertEqual(len(calls), 3, "gebremste Aenderung muss nachkommen")

    def test_teilbild_zaehlt_nicht_als_messung(self):
        sa = QScrollArea()
        sa.resize(300, 200)
        c = self._canvas(zoom=2.0)
        sa.setWidget(c)
        sa.show()
        _app.processEvents()
        uhr = _Uhr()
        c._uhr = uhr
        c._zeichenzeiten.clear()
        c._zeichne = lambda ev, voll=True: uhr.vor(0.001)
        c.paintEvent(QPaintEvent(QRect(0, 0, 20, 20)))     # nur eine Ecke
        self.assertEqual(len(c._zeichenzeiten), 0)
        c.paintEvent(QPaintEvent(c.rect()))
        self.assertEqual(len(c._zeichenzeiten), 1)

    def test_wiedereinblenden_zeichnet_sofort(self):
        c = self._canvas()
        c.show()
        _app.processEvents()
        uhr = _Uhr()
        c._uhr = uhr
        c._zeichne = lambda ev, voll=True: uhr.vor(0.058)
        for _ in range(5):
            c.paintEvent(QPaintEvent(c.rect()))
        calls = []
        c.update = lambda *a: calls.append(1)
        c._on_render_tick()
        c.set_active(False)
        c.set_active(True)
        c._update_timer.stop()
        c._on_render_tick()
        self.assertEqual(len(calls), 2)


# ════════════════════════════════════════════════════════════════════════════
# 2. Hintergrund-Cache auf den sichtbaren Ausschnitt
# ════════════════════════════════════════════════════════════════════════════

class AusschnittCacheTest(_Fall):
    def _im_scrollbereich(self, zoom, welt=(1200, 800), fenster=(640, 420)):
        sa = QScrollArea()
        sa.resize(*fenster)
        c = self._canvas(zoom=zoom, welt=welt)
        sa.setWidget(c)
        sa.show()
        _app.processEvents()
        return sa, c

    def test_cache_greift_bei_200_prozent(self):
        """1200x800 bei Zoom 1,5 und doppelter Pixeldichte: 8,6 Mio Pixel, mehr
        als die Grenze — der Cache fiel aus. Sichtbar ist aber nur ein Fenster."""
        sa, c = self._im_scrollbereich(1.5)
        c.devicePixelRatioF = lambda: 2.0
        self.assertGreater(c.width() * c.height() * 4, c.BG_CACHE_MAX_PIXEL)
        pm = c._hintergrund_pixmap()
        self.assertIsNotNone(pm, "Hintergrund-Cache greift bei 200 % nicht")
        self.assertLessEqual(pm.width() * pm.height(), c.BG_CACHE_MAX_PIXEL)
        sicht = c.visibleRegion().boundingRect()
        self.assertTrue(c._bg_rect.contains(sicht))
        self.assertLess(c._bg_rect.width() * c._bg_rect.height(),
                        c.width() * c.height())

    def test_kleiner_scrollschritt_baut_nicht_neu(self):
        sa, c = self._im_scrollbereich(1.5)
        c.devicePixelRatioF = lambda: 2.0
        pm = c._hintergrund_pixmap()
        self.assertIsNotNone(pm)
        sa.horizontalScrollBar().setValue(40)
        sa.verticalScrollBar().setValue(30)
        _app.processEvents()
        self.assertIs(c._hintergrund_pixmap(), pm)
        # Weit gescrollt -> der Ausschnitt verlaesst das Stueck -> neu.
        sa.horizontalScrollBar().setValue(sa.horizontalScrollBar().maximum())
        sa.verticalScrollBar().setValue(sa.verticalScrollBar().maximum())
        _app.processEvents()
        pm2 = c._hintergrund_pixmap()
        self.assertIsNotNone(pm2)
        self.assertIsNot(pm2, pm)
        self.assertTrue(c._bg_rect.contains(c.visibleRegion().boundingRect()))

    def test_ausschnitt_ist_pixelgleich(self):
        """Das Bild mit Ausschnitt-Cache gleicht dem direkt gezeichneten — an
        mehreren Scroll-Stellen, auch mit ungeradem Zoom."""
        for zoom in (2.0, 1.37, 3.0):
            sa, c = self._im_scrollbereich(zoom)
            c.BG_CACHE_MAX_PIXEL = 700_000       # ganze Flaeche passt nicht
            self.assertGreater(c.width() * c.height(), c.BG_CACHE_MAX_PIXEL)
            hb, vb = sa.horizontalScrollBar(), sa.verticalScrollBar()
            for fx, fy in ((0.0, 0.0), (0.33, 0.5), (1.0, 1.0)):
                hb.setValue(int(hb.maximum() * fx))
                vb.setValue(int(vb.maximum() * fy))
                _app.processEvents()
                c._bg_pixmap = None
                c.BG_CACHE_MAX_PIXEL = 700_000
                mit = sa.viewport().grab().toImage()
                self.assertIsNotNone(c._bg_pixmap,
                                     f"kein Ausschnitt-Cache (Zoom {zoom})")
                self.assertNotEqual(c._bg_rect, c.rect())
                c.BG_CACHE_MAX_PIXEL = 0         # Cache aus -> direkt
                ohne = sa.viewport().grab().toImage()
                self.assertEqual(mit, ohne,
                                 f"Bild weicht ab (Zoom {zoom}, Stelle {fx}/{fy})")
            sa.close()

    def test_kleine_flaeche_wird_weiter_ganz_gecacht(self):
        """100 %: unveraendert ein Bild ueber die ganze Flaeche."""
        sa, c = self._im_scrollbereich(1.0)
        pm = c._hintergrund_pixmap()
        self.assertIsNotNone(pm)
        self.assertEqual(c._bg_rect, c.rect())
        sa.horizontalScrollBar().setValue(sa.horizontalScrollBar().maximum())
        _app.processEvents()
        self.assertIs(c._hintergrund_pixmap(), pm)

    def test_ganzes_bild_groesser_als_grenze_zeichnet_direkt(self):
        """Ein Abzug der ganzen Flaeche (grab) braucht mehr als die Grenze —
        dann direkt zeichnen statt ein zu kleines Stueck zu verwenden."""
        sa, c = self._im_scrollbereich(2.0)
        c.BG_CACHE_MAX_PIXEL = 700_000
        mit = c.grab().toImage()
        c.BG_CACHE_MAX_PIXEL = 0
        self.assertEqual(mit, c.grab().toImage())

    def test_abzug_ueber_den_sichtbaren_ausschnitt_hinaus(self):
        """Wird mehr neu gezeichnet als gerade sichtbar ist (Abzug eines
        Teilstuecks), muss das Cache-Bild auch dieses Stueck abdecken — sonst
        bliebe dort wegen des deckenden Zeichnens Altes stehen."""
        sa, c = self._im_scrollbereich(2.0)
        stueck = QRect(500, 300, 700, 500)
        self.assertFalse(c.visibleRegion().boundingRect().contains(stueck))
        c.BG_CACHE_MAX_PIXEL = 1_200_000
        c._bg_pixmap = None                # das Bild aus show() verwerfen
        mit = c.grab(stueck).toImage()
        self.assertIsNotNone(c._bg_pixmap)
        self.assertTrue(c._bg_rect.contains(stueck))
        self.assertNotEqual(c._bg_rect, c.rect())
        c.BG_CACHE_MAX_PIXEL = 0
        self.assertEqual(mit, c.grab(stueck).toImage())


if __name__ == "__main__":
    unittest.main()
