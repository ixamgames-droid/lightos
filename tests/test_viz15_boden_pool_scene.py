"""VIZ-15: aus dem Bodenfleck wird ein Licht-Pool — in echter QWebEngine.

Vorher war er eine `CircleGeometry` mit gleichmaessiger Deckkraft und FESTEM
Radius: eine Scheibe mit harter Kante, immer gleich gross, egal wie weit der
Scheinwerfer weg stand oder wie eng der Zoom war. Echtes Licht macht beides
nicht.

★ **Der Test, auf den es ankommt, ist der Grauverlauf.** `alphaMap` liest in
three.js den **Gruenkanal** der Textur, nicht deren Alphakanal. Der naheliegende
Einfall — weiss mit fallendem Alpha — ergibt einen KONSTANTEN Gruenwert und
damit gar keinen Verlauf: der Rand bliebe hart, und zwar ohne dass man es dem
Code ansieht. Deshalb liest dieser Test die erzeugte Textur wirklich aus und
vergleicht Pixel von innen nach aussen.
"""
import json
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QObject, QUrl
from _qt_lifecycle import destroy_webengine_view  # XPLAT-09

_app = QApplication.instance() or QApplication([])

_HTML_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "src", "ui", "visualizer", "stage_scene.html"))

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05

_BASIS = 1.2      # POOL_BASIS_RADIUS (floor_pool.js) = Radius aus createFloorSpot


def _pump(seconds):
    ende = time.monotonic() + seconds
    while time.monotonic() < ende:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


class BodenPoolSceneTest(unittest.TestCase):
    def setUp(self):
        self._view = QWebEngineView()
        try:
            self._view.page().profile().setHttpCacheType(
                QWebEngineProfile.HttpCacheType.NoCache)
        except Exception:
            pass
        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self._obj = QObject()
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._obj)
        self._view.page().setWebChannel(self._channel)
        self._loaded = []
        self._view.loadFinished.connect(self._loaded.append)

    def tearDown(self):
        destroy_webengine_view(self._view, _pump)   # XPLAT-09
        self._view = None

    def _eval(self, js):
        box = []
        self._view.page().runJavaScript(js, box.append)
        ende = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < ende:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(box, f"runJavaScript ohne Callback: {js}")
        return box[0]

    def _load_and_wait(self):
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}")
        self._view.load(url)
        ende = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded and time.monotonic() < ende:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded and self._loaded[-1], "Page nicht geladen")
        ende = time.monotonic() + _POLL_TIMEOUT_S
        while time.monotonic() < ende:
            if self._eval("!!window.__lightosAppReady"):
                return
            time.sleep(_POLL_INTERVAL_S)
        self.fail("Szene wurde nicht bereit")

    def test_falloff_ist_ein_echter_grauverlauf(self):
        """Von innen nach aussen muss der GRUENKANAL fallen — sonst ist die
        alphaMap wirkungslos und der Rand bleibt hart."""
        self._load_and_wait()
        # ★ JSON.stringify ist Pflicht, nicht Geschmack: ein nacktes Array
        #   ueberlebt die runJavaScript-Bruecke NICHT (`return [[1,2],[3,4]]`
        #   kommt als leerer String an). Nachgemessen 2026-08-01 — ohne das
        #   sah der Test wie ein Textur-Fehler aus, obwohl der Verlauf stimmte.
        roh = self._eval("""
        (function () {
          const tex = window.__lightos.poolFalloffTexture();
          if (!tex || !tex.image) return "null";
          const cv = tex.image;
          const ctx = cv.getContext('2d');
          const m = cv.width / 2;
          // Proben auf einem Radius: Mitte, Viertel, Halb, Dreiviertel, Rand.
          const out = [0, 0.25, 0.5, 0.75, 0.98].map(function (t) {
            const d = ctx.getImageData(Math.round(m + t * (m - 1)), m, 1, 1).data;
            return [d[1], d[3]];   // [Gruen, Alpha]
          });
          return JSON.stringify(out);
        })()
        """)
        werte = json.loads(roh)
        self.assertIsNotNone(werte, "Falloff-Textur wurde nicht erzeugt")
        self.assertTrue(werte, "keine Proben aus der Textur gelesen")
        gruen = [int(g) for g, _a in werte]
        alpha = [int(a) for _g, a in werte]

        self.assertEqual(alpha, [255] * len(alpha),
                         "Der Verlauf muss im GRUENKANAL liegen, nicht im Alpha — "
                         "three.js liest fuer alphaMap ausschliesslich Gruen.")
        self.assertGreater(gruen[0], 240, "innen muss es voll hell sein")
        self.assertLess(gruen[-1], 40, "aussen muss es auf null auslaufen")
        for i in range(len(gruen) - 1):
            self.assertGreaterEqual(
                gruen[i], gruen[i + 1],
                f"der Verlauf darf nach aussen nicht wieder heller werden: {gruen}")
        self.assertGreater(len(set(gruen)), 2,
                           f"ein echter Verlauf, keine zwei Stufen: {gruen}")

    def test_poolgroesse_folgt_abstand_und_zoom(self):
        self._load_and_wait()
        k = lambda d, w: float(self._eval(
            f"window.__lightos.floorPoolScale({d}, {w})"))

        # Doppelter Abstand = doppelter Radius (gleicher Winkel).
        eng = k(4.0, 0.20)
        weit = k(8.0, 0.20)
        self.assertAlmostEqual(weit / eng, 2.0, places=4,
                               msg="der Fleck muss mit dem Abstand wachsen")

        # Groesserer Oeffnungswinkel = groesserer Fleck (das ist der Zoom-Pfad:
        # applyOptics zieht spot.angle mit).
        self.assertGreater(k(6.0, 0.35), k(6.0, 0.15),
                           "weiter Zoom muss einen groesseren Fleck ergeben")

        # Der Faktor ist relativ zum Grundradius der Scheibe.
        import math
        self.assertAlmostEqual(k(5.0, 0.20), math.tan(0.20) * 5.0 / _BASIS, places=4)

        # Grenzen: nah dran wird nicht zum Punkt, quer durch die Halle nicht zur
        # halben Szene.
        self.assertAlmostEqual(k(0.05, 0.20), 0.25 / _BASIS, places=4)
        self.assertAlmostEqual(k(500.0, 0.20), 12.0 / _BASIS, places=4)

        # Unbrauchbare Eingaben lassen den Grundradius stehen — ein Fleck, der
        # bei einem NaN auf null zusammenfaellt, waere schlimmer als einer in
        # der falschen Groesse.
        for js in ("NaN, 0.2", "Infinity, 0.2", "-3, 0.2", "5, NaN",
                   "5, 0", "5, -1"):
            self.assertAlmostEqual(
                float(self._eval(f"window.__lightos.floorPoolScale({js})")), 1.0,
                places=6, msg=f"floorPoolScale({js}) muss auf 1 zurueckfallen")

    def test_falloff_textur_wird_geteilt_nicht_pro_geraet_gebaut(self):
        """Eine Textur fuer alle Fixtures. Pro Geraet eine eigene waere bei 48
        Movern 48 Uploads fuer denselben Verlauf."""
        self._load_and_wait()
        self.assertTrue(self._eval(
            "window.__lightos.poolFalloffTexture() === "
            "window.__lightos.poolFalloffTexture()"),
            "die Falloff-Textur muss zwischengespeichert sein")


if __name__ == "__main__":
    unittest.main()
