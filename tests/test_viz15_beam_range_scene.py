"""VIZ-15: globale Max-Strahllaenge — die Rechnung, in echter QWebEngine.

Drei Grenzen treffen in ``beamLengthScale`` aufeinander, und **welche gewinnt,
ist die Aussage**: die Grundlaenge des Geraetetyps, der Abstand zum
Bodenauftreffpunkt (VIZ-BEAM-OCCLUSION) und die neue globale Obergrenze. Ein
Test, der nur „der Kegel wurde kuerzer" prueft, haette jede der drei falsch
verdrahtet durchgewinkt — deshalb wird die Funktion mit Zahlen gefahren.

Der zweite Teil ist ein Rueckfallschutz: ``applyOptics`` setzte die Y-Skalierung
frueher hart auf ``1``. Das ging nur gut, WEIL ``applyFloorAim`` zufaellig danach
lief und die Laenge neu setzte — eine unsichtbare Reihenfolge-Abhaengigkeit, die
beim naechsten Umsortieren der updateDmx-Kette gerissen waere.
"""
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

_GRUND = 8.0        # Grundlaenge eines Moving-Head-Kegels (fixtures.js)


def _pump(seconds):
    ende = time.monotonic() + seconds
    while time.monotonic() < ende:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


class MaxBeamRangeSceneTest(unittest.TestCase):
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

    def _k(self, dist, maxrange):
        d = "Infinity" if dist == float("inf") else repr(dist)
        return float(self._eval(
            f"window.__lightos.beamLengthScale({_GRUND}, {d}, {maxrange})"))

    def test_welche_grenze_gewinnt(self):
        self._load_and_wait()
        unendlich = float("inf")

        # Nichts gesetzt: volle Grundlaenge.
        self.assertAlmostEqual(self._k(unendlich, 0), 1.0, places=6)
        # Deckel groesser als der Grundkegel aendert nichts — ein hoch
        # haengender Scheinwerfer soll nicht ploetzlich weiter leuchten.
        self.assertAlmostEqual(self._k(unendlich, 100), 1.0, places=6)

        # ★ DER NEUE FALL: kein Bodenauftreffpunkt (waagerechter oder nach oben
        # gerichteter Kopf) — bis VIZ-15 blieb der Kegel hier auf voller Laenge,
        # weil setBeamLength nur im Bodentreffer-Zweig lief.
        self.assertAlmostEqual(self._k(unendlich, 5), 5 / _GRUND, places=6)

        # Boden naeher als der Deckel: der Boden gewinnt.
        self.assertAlmostEqual(self._k(3.0, 5), 3 / _GRUND, places=6)
        # Deckel naeher als der Boden: der Deckel gewinnt.
        self.assertAlmostEqual(self._k(6.0, 4), 4 / _GRUND, places=6)
        # Ohne Deckel entscheidet allein der Boden.
        self.assertAlmostEqual(self._k(3.0, 0), 3 / _GRUND, places=6)

        # Mindestlaenge: ein Kegel mit Laenge 0 waere ein unsichtbarer Punkt.
        self.assertAlmostEqual(self._k(0.001, 0), 0.15 / _GRUND, places=6)

        # Unbrauchbarer Abstand heisst "kein Auftreffpunkt", NICHT "Laenge 0" —
        # sonst liesse ein einzelnes NaN den Kegel verschwinden.
        self.assertAlmostEqual(float(self._eval(
            f"window.__lightos.beamLengthScale({_GRUND}, NaN, 0)")), 1.0, places=6)
        # Ohne bekannte Grundlaenge gibt es nichts zu skalieren.
        self.assertAlmostEqual(float(self._eval(
            "window.__lightos.beamLengthScale(0, 5, 5)")), 1.0, places=6)

        # ── Rueckfallschutz: applyOptics darf die LAENGE nicht plattmachen ──
        # Die Y-Achse gehoert setBeamLength (Boden + Deckel), Zoom/Iris/Frost
        # aendern nur die WEITE. Ein hartes `scale.set(k, 1, k)` funktionierte
        # frueher nur, weil applyFloorAim zufaellig danach lief.
        self._eval("""
        (function () {
          window.__brProbe = {
            beam: { scale: { x: 1, y: 0.4, z: 1,
                             set(a, b, c) { this.x = a; this.y = b; this.z = c; } } },
            spot: { angle: 0.3, penumbra: 0.6 },
            baseSpotAngle: 0.3,
          };
          window.__lightos.applyOptics(window.__brProbe, { zoom: 255 });
          return true;
        })()
        """)
        self.assertAlmostEqual(
            float(self._eval("window.__brProbe.beam.scale.y")), 0.4,
            places=6, msg="applyOptics darf die Kegel-LAENGE nicht zuruecksetzen")
        self.assertGreater(
            float(self._eval("window.__brProbe.beam.scale.x")), 1.0,
            "... die WEITE aber sehr wohl aendern (sonst prueft der Test nichts)")


if __name__ == "__main__":
    unittest.main()
