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

**Gegenpruefung der Leitung (16.11.):** "blinkt" hiess zuerst nur "Strobe-
Frequenz > 0". Ein Strobe-Wert bei Helligkeit 0 (Blackout, geparkter
Strobe-Kanal) liess den 50-ms-Takt dauerhaft laufen, obwohl nichts zu sehen
war; bei verdeckter Flaeche blieb der Zeitgeber auf 50 ms stehen. Jetzt
zaehlt ein Geraet nur, wenn das Bild es hell zeichnet (``SichtbarLeuchtenTest``).
"""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
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

    def test_verdeckte_flaeche_stellt_den_zeitgeber_zurueck(self):
        """Der Zeitgeber wurde nur nach einem Bild umgestellt. Wird die Flaeche
        im Strobe-Takt verdeckt oder minimiert, feuerte er weiter alle 50 ms."""
        c = self.c
        c._update_timer.setInterval(c.STROBE_TAKT_MS)
        self._blinkt()
        c._darf_zeichnen = lambda: False
        c._on_render_tick()
        self.assertEqual(c._update_timer.interval(), c.RENDER_INTERVAL_MS)

    def test_dunkles_geraet_zaehlt_nicht(self):
        c = self.c
        leer = {"strobe": [], "uni": 1, "fp": (42,)}
        hz, _an = c._strobe_aus_steckbrief(leer, lambda _u, _a: 0,
                                           {"square": {42: 5.0}}, False)
        self.assertEqual(hz, 5.0, "die Frequenz wird weiter gemeldet (Anzeige)")
        self.assertEqual(c._takt_ms(), c.RENDER_INTERVAL_MS)

    def test_blink_effekt_ueberbrueckt_seine_dunkle_haelfte(self):
        """Ein Rechteck-Effekt auf dem Dimmer ist die halbe Periode dunkel. Bei
        0,4 Hz sind das 1,25 s - laenger als der Nachlauf. Der Takt darf dabei
        nicht je Periode hin- und herspringen (die Blitzfolge rechnet mit der
        Bildrate)."""
        c = self.c
        leer = {"strobe": [], "uni": 1, "fp": (42,)}
        vorab = {"square": {42: 0.4}}
        c._strobe_aus_steckbrief(leer, lambda _u, _a: 255, vorab, True)
        for _ in range(12):                      # dunkle Haelfte, 1,2 s
            self.zeit[0] += 0.1
            c._strobe_aus_steckbrief(leer, lambda _u, _a: 0, vorab, False)
            self.assertEqual(c._takt_ms(), c.STROBE_TAKT_MS)
        self.zeit[0] += 1.4                      # Effekt aus: 2,6 s > 1 Periode
        self.assertEqual(c._takt_ms(), c.RENDER_INTERVAL_MS)

    def test_nachlauf_hat_einen_deckel(self):
        c = self.c
        leer = {"strobe": [], "uni": 1, "fp": (42,)}
        c._strobe_aus_steckbrief(leer, lambda _u, _a: 255, {"square": {42: 0.01}}, True)
        self.zeit[0] += c.STROBE_NACHLAUF_MAX_S - 0.1
        self.assertEqual(c._takt_ms(), c.STROBE_TAKT_MS)
        self.zeit[0] += 0.2
        self.assertEqual(c._takt_ms(), c.RENDER_INTERVAL_MS)

    def test_zurueckgestellte_uhr_haelt_den_takt_nicht_fest(self):
        c = self.c
        self._blinkt()
        self.zeit[0] -= 3600.0
        self.assertEqual(c._takt_ms(), c.RENDER_INTERVAL_MS)


def _kanal(n, attr, ranges=()):
    return SimpleNamespace(channel_number=n, attribute=attr, ranges=list(ranges),
                           name=attr)


_SHUTTER_BEREICHE = (
    SimpleNamespace(range_from=0, range_to=9, name="Offen", kind="open"),
    SimpleNamespace(range_from=10, range_to=255, name="Strobe 5 Hz", kind="strobe"),
)
# Geraet mit Dimmer (Kanal 1) und Shutter (Kanal 5)
_MIT_DIMMER = [_kanal(1, "intensity"), _kanal(2, "color_r"), _kanal(3, "color_g"),
               _kanal(4, "color_b"), _kanal(5, "shutter", _SHUTTER_BEREICHE)]
# Geraet OHNE Dimmer: RGB (1-3) und Shutter (4) - dunkel heisst hier Schwarz
_OHNE_DIMMER = [_kanal(1, "color_r"), _kanal(2, "color_g"), _kanal(3, "color_b"),
                _kanal(4, "shutter", _SHUTTER_BEREICHE)]


class _Uni:
    def __init__(self, werte):
        self.werte = werte

    def get_channel(self, a):
        return self.werte.get(a, 0)

    def get_all(self):
        return bytes(self.werte.get(i, 0) for i in range(1, 513))


class _Ausgang:
    """Output-Manager-Attrappe: ``frames[u]`` = zuletzt gesendetes Bild."""

    def __init__(self):
        self.frames = {}

    def get_display_frame(self, u):
        return self.frames.get(u)


class SichtbarLeuchtenTest(unittest.TestCase):
    """Durch den echten Zeichenweg (``grab`` -> ``paintEvent``): der schnellere
    Takt gilt nur, wenn das Bild ein blinkendes Geraet auch hell zeichnet."""

    def setUp(self):
        c = live_view.StageCanvas()
        c._update_timer.stop()
        self.zeit = [100.0]
        c._uhr = lambda: self.zeit[0]
        self.addCleanup(c.deleteLater)
        self.c = c
        self.kanaele = _MIT_DIMMER
        orig = live_view.get_channels_for_patched
        live_view.get_channels_for_patched = lambda _f: self.kanaele
        self.addCleanup(setattr, live_view, "get_channels_for_patched", orig)
        st = c._state
        self.addCleanup(setattr, st, "universes", st.universes)
        self.aus = _Ausgang()
        self.addCleanup(setattr, st, "output_manager", st.output_manager)
        st.output_manager = self.aus
        fx = SimpleNamespace(fid=1, universe=1, address=1, label="F1",
                             fixture_type="par", pan_range_deg=540,
                             tilt_range_deg=270, pan_zero_dmx=128,
                             tilt_zero_dmx=128, aim_offset_pan=0.0,
                             aim_offset_tilt=0.0)
        st.get_patched_fixtures = lambda: [fx]
        self.addCleanup(vars(st).pop, "get_patched_fixtures", None)
        c._positions = {1: (100.0, 100.0)}
        c.resize(300, 250)

    def _bild(self, werte, gesendet=None):
        """Ein Bild zeichnen; liefert die Strobe-Frequenz, die es gesehen hat."""
        c = self.c
        c._state.universes = {1: _Uni(werte)}
        self.aus.frames = {} if gesendet is None else {1: gesendet}
        gesehen = []
        echt = c._strobe_aus_steckbrief

        def merken(*a, **kw):
            erg = echt(*a, **kw)
            gesehen.append(erg[0])
            return erg
        with mock.patch.object(c, "_strobe_aus_steckbrief", side_effect=merken):
            c.grab()
        self.assertEqual(len(gesehen), 1, "das Geraet wurde nicht gezeichnet")
        return gesehen[0]

    def test_strobe_wert_bei_helligkeit_null_bleibt_grundtakt(self):
        c = self.c
        hz = self._bild({1: 0, 2: 255, 3: 255, 4: 255, 5: 100})
        self.assertEqual(hz, 5.0, "Voraussetzung: der Strobe-Kanal meldet 5 Hz")
        self.assertEqual(c._takt_ms(), c.RENDER_INTERVAL_MS)
        self.assertEqual(c._takt_ms(), 100)
        self.assertEqual(c._ui_anteil(), c.MAX_UI_ANTEIL)
        # der Zeitgeber selbst bleibt beim Grundtakt
        c._update_timer.setInterval(c.RENDER_INTERVAL_MS)
        c._darf_zeichnen = lambda: True
        c._animiert = True
        c._on_render_tick()
        self.assertEqual(c._update_timer.interval(), c.RENDER_INTERVAL_MS)

    def test_strobe_wert_mit_helligkeit_schaltet_um(self):
        c = self.c
        self.assertEqual(self._bild({1: 255, 2: 255, 3: 255, 4: 255, 5: 100}), 5.0)
        self.assertEqual(c._takt_ms(), c.STROBE_TAKT_MS)

    def test_blackout_im_gesendeten_bild_bleibt_grundtakt(self):
        """WYSIWYG: der Rohpuffer steht auf voll + Strobe, gesendet wird nach
        dem Blackout Helligkeit 0 - der Strobe-Kanal behaelt seinen Wert."""
        c = self.c
        roh = {1: 255, 2: 255, 3: 255, 4: 255, 5: 100}
        gesendet = bytearray(512)
        gesendet[1:5] = bytes([255, 255, 255, 100])          # Dimmer (Kanal 1) = 0
        self.assertEqual(self._bild(roh, bytes(gesendet)), 5.0)
        self.assertEqual(c._takt_ms(), c.RENDER_INTERVAL_MS)

    def test_geraet_ohne_dimmer_in_schwarz_bleibt_grundtakt(self):
        """Ohne Dimmer-Kanal meldet die Ansicht Helligkeit 255; dunkel ist so
        ein Geraet, wenn seine Farbe Schwarz ist."""
        c = self.c
        self.kanaele = _OHNE_DIMMER
        self.assertEqual(self._bild({1: 0, 2: 0, 3: 0, 4: 100}), 5.0)
        self.assertEqual(c._takt_ms(), c.RENDER_INTERVAL_MS)
        c._patch_geaendert()
        self.assertEqual(self._bild({1: 0, 2: 80, 3: 0, 4: 100}), 5.0)
        self.assertEqual(c._takt_ms(), c.STROBE_TAKT_MS)

    def test_nach_dem_abdunkeln_noch_der_nachlauf(self):
        c = self.c
        self._bild({1: 255, 2: 255, 3: 255, 4: 255, 5: 100})
        self._bild({1: 0, 2: 255, 3: 255, 4: 255, 5: 100})
        self.assertEqual(c._takt_ms(), c.STROBE_TAKT_MS)
        self.zeit[0] += c.STROBE_NACHLAUF_S + 0.1
        self._bild({1: 0, 2: 255, 3: 255, 4: 255, 5: 100})
        self.assertEqual(c._takt_ms(), c.RENDER_INTERVAL_MS)


if __name__ == "__main__":
    unittest.main()
