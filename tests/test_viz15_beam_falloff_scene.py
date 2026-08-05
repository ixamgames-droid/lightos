"""VIZ-15 (Phase 5, Optik): der Lichtkegel laeuft laengs aus — in echter QWebEngine.

Bis hierhin war der Kegel ein ``MeshBasicMaterial`` mit ueber die ganze Laenge
GLEICHER Deckkraft: er endete an seiner Spitze mit einer sichtbaren Kante,
statt wie echtes Licht im Dunst auszulaufen. Die Loesung ist dieselbe wie beim
Bodenfleck — EINE gemeinsame Textur als ``alphaMap``, ohne eine Zeile GLSL und
ohne neuen ``THREE.``-Namen.

Zwei Dinge muessen dabei stimmen, und **beide sind unsichtbar, wenn sie falsch
sind**:

1. **Der Verlauf muss im GRUENKANAL liegen.** ``alphaMap`` liest in three.js
   ausschliesslich Gruen. „Weiss mit fallendem Alpha" — der naheliegende
   Einfall — ergibt einen konstanten Gruenwert und damit gar keinen Verlauf.
   Derselbe Fallstrick wie in ``test_viz15_boden_pool_scene.py``.

2. **Die RICHTUNG haengt an zwei gemessenen Eigenschaften von three.js**: bei
   ``ConeGeometry`` traegt die SPITZE (+y) ``v = 1`` und die weite Basis (-y)
   ``v = 0``; ``CanvasTexture.flipY`` ist per Default ``true``, die
   Canvas-Oberkante wird also zu ``v = 1``. Und ``createBeamCone`` schiebt den
   Kegel um ``-length/2``, die Spitze sitzt damit AM GERAET.
   → Canvas oben = am Geraet = voll.

   *Drehte three.js diese UVs einmal um, verliefe der Kegel still falschherum:
   am Geraet blass, am fernen Ende hell.* Kein Test wuerde das bemerken, wenn
   er nur „es gibt einen Verlauf" prueft. Deshalb nagelt der zweite Test die
   Beziehung Position ↔ UV ausdruecklich fest.
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
from PySide6.QtCore import QObject, QUrl, Signal, Slot
from _qt_lifecycle import destroy_webengine_view  # XPLAT-09

_app = QApplication.instance() or QApplication([])

_HTML_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "src", "ui", "visualizer", "stage_scene.html"))

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05


# Poll-"fixtures" ist ein JSON-STRING (bridge.js JSON.parse't ihn) — dasselbe
# Muster wie in test_viz14_labels_scene.py. Ueber diesen Weg kommt das Geraet
# regulaer herein, statt eine interne Funktion anzurufen, die es gar nicht als
# globale gibt.
_FIXTURE = {"fid": 1, "type": "par", "x": 0, "y": 3, "z": 0, "label": "P1"}
_POLL_FIXTURES = json.dumps({"fixtures": json.dumps([_FIXTURE])})

_SIGNAL_SPECS = [
    ("fixtureAdded", (str,)), ("fixtureRemoved", (int,)), ("dmxBatch", (str,)),
    ("allFixtures", (str,)), ("settingsChanged", (str,)), ("viewModeChanged", (str,)),
    ("editModeChanged", (str,)), ("stageLoaded", (str,)), ("addStageObject", (str,)),
    ("addStageObjectData", (str,)), ("removeStageObject", (str,)),
    ("selectStageObject", (str,)), ("applyFixtureTransform", (str,)),
    ("alignSelected", (str,)), ("distributeSelected", (str,)), ("cameraReset", ()),
    ("brightnessSignal", (float,)), ("brightnessAutoSignal", ()),
    ("updateStageObject", (str,)), ("resizeModeSignal", (bool,)),
    ("pixelRatioSignal", (float,)),
]


def _make_mock_bridge_class():
    attrs = {name: Signal(*a) for name, a in _SIGNAL_SPECS}

    @Slot()
    def requestFixtures(self):
        self._request_fixtures_calls = getattr(self, "_request_fixtures_calls", 0) + 1

    attrs["requestFixtures"] = requestFixtures

    @Slot(result=str)
    def pollControl(self):
        return getattr(self, "_poll_payload", "{}")

    attrs["pollControl"] = pollControl
    attrs["requestFullResync"] = Signal()
    return type("MockVisualizerBridge", (QObject,), attrs)


_MockVisualizerBridge = _make_mock_bridge_class()


def _pump(seconds):
    ende = time.monotonic() + seconds
    while time.monotonic() < ende:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


class BeamFalloffSceneTest(unittest.TestCase):
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
        self._obj = _MockVisualizerBridge()
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

    # ── Alle Checks in EINER Ladung (jede Vollladung kostet ~4 s) ─────────────

    def test_falloff_ist_ein_echter_grauverlauf_von_der_spitze_weg(self):
        self._load_and_wait()
        # JSON.stringify ist Pflicht: ein nacktes Array ueberlebt die
        # runJavaScript-Bruecke nicht (Lehre aus dem Boden-Pool-Test).
        roh = self._eval("""
        (function () {
          const tex = window.__lightos.beamFalloffTexture();
          if (!tex || !tex.image) return "null";
          const cv = tex.image;
          const ctx = cv.getContext('2d');
          const x = Math.floor(cv.width / 2);
          // Proben von OBEN (Canvas y=0 = Spitze = am Geraet) nach UNTEN.
          const out = [0, 0.25, 0.5, 0.75, 0.99].map(function (t) {
            const y = Math.min(cv.height - 1, Math.round(t * (cv.height - 1)));
            const d = ctx.getImageData(x, y, 1, 1).data;
            return [d[1], d[3]];   // [Gruen, Alpha]
          });
          return JSON.stringify({proben: out, flipY: tex.flipY,
                                 hoehe: cv.height, breite: cv.width});
        })()
        """)
        self.assertNotEqual(roh, "null", "Falloff-Textur wurde nicht erzeugt")
        daten = json.loads(roh)
        gruen = [int(g) for g, _a in daten["proben"]]
        alpha = [int(a) for _g, a in daten["proben"]]

        self.assertEqual(
            alpha, [255] * len(alpha),
            "Der Verlauf muss im GRUENKANAL liegen, nicht im Alpha — three.js "
            "liest fuer alphaMap ausschliesslich Gruen. Mit fallendem Alpha "
            "waere der Gruenwert konstant und der Kegel bliebe flach.")
        self.assertTrue(daten["flipY"],
                        "flipY=false wuerde den Verlauf umdrehen: der Kegel "
                        "waere am Geraet blass und am fernen Ende hell")
        self.assertGreater(gruen[0], 245,
                           f"am Geraet (Canvas oben) muss der Kegel voll sein: {gruen}")
        self.assertLess(gruen[-1], 90,
                        f"am fernen Ende muss er deutlich ausgeduennt sein: {gruen}")
        self.assertGreater(
            gruen[-1], 0,
            "aber NICHT auf null: trifft der Strahl den Boden, ist genau dort "
            "der Auftreffpunkt — ein dort unsichtbarer Kegel haette keinen "
            "Bodenkontakt mehr")
        for i in range(len(gruen) - 1):
            self.assertGreaterEqual(
                gruen[i], gruen[i + 1],
                f"der Verlauf darf zum Ende hin nicht wieder heller werden: {gruen}")
        self.assertGreater(len(set(gruen)), 2,
                           f"ein echter Verlauf, keine zwei Stufen: {gruen}")

    def test_uv_orientierung_des_kegels_ist_die_angenommene(self):
        """★ Der Vertrag, an dem die Richtung des Verlaufs haengt.

        Er steht NICHT in unserem Code, sondern in three.js — und wenn er
        kippt, kippt der Kegel still mit: gleich heller Verlauf, nur
        falschherum. Genau deshalb wird er hier gemessen statt angenommen.
        """
        self._load_and_wait()
        roh = self._eval("""
        (function () {
          const geo = new (window.THREE.ConeGeometry)(1.0, 4.0, 8, 1, true);
          const pos = geo.attributes.position, uv = geo.attributes.uv;
          let yMin = Infinity, yMax = -Infinity, vBeiMin = null, vBeiMax = null;
          for (let i = 0; i < pos.count; i++) {
            const y = pos.getY(i), v = uv.getY(i);
            if (y < yMin) { yMin = y; vBeiMin = v; }
            if (y > yMax) { yMax = y; vBeiMax = v; }
          }
          geo.dispose();
          return JSON.stringify({yMin: yMin, vBeiMin: vBeiMin,
                                 yMax: yMax, vBeiMax: vBeiMax});
        })()
        """)
        d = json.loads(roh)
        self.assertAlmostEqual(
            d["vBeiMax"], 1.0, places=3,
            msg=f"die Kegel-SPITZE (+y) muss v=1 tragen, sonst zeigt der "
                f"Verlauf in die falsche Richtung: {d}")
        self.assertAlmostEqual(
            d["vBeiMin"], 0.0, places=3,
            msg=f"die weite BASIS (-y) muss v=0 tragen: {d}")

    def test_kegel_traegt_den_falloff_und_behaelt_seinen_farb_pfad(self):
        """Die Textur allein nuetzt nichts — sie muss auch am Kegel haengen.
        Und der Per-Frame-Schreibweg (Farbe/Deckkraft aus dem DMX) darf davon
        unberuehrt bleiben: `applyGenericColor` schreibt weiter `material.color`
        und `material.opacity`, die alphaMap moduliert nur darueber."""
        self._load_and_wait()
        self._obj._poll_payload = _POLL_FIXTURES
        ende = time.monotonic() + 8.0
        while time.monotonic() < ende:
            if self._eval("!!(window.__lightos.fixtures "
                          "&& window.__lightos.fixtures['1'])"):
                break
            time.sleep(_POLL_INTERVAL_S)
        zustand = self._eval("""
        (function () {
          const g = window.__lightos.fixtures['1'];
          if (!g || !g.beam) return JSON.stringify({da: false});
          const m = g.beam.material;
          return JSON.stringify({
            da: true,
            hatAlphaMap: !!m.alphaMap,
            istGeteilt: m.alphaMap === window.__lightos.beamFalloffTexture(),
            hatColor: !!m.color,
            opacityIstZahl: typeof m.opacity === 'number'});
        })()
        """)
        z = json.loads(zustand)
        self.assertTrue(z["da"], "Testgeraet kam nicht auf die Buehne")
        self.assertTrue(z["hatAlphaMap"],
                        "der Kegel traegt den Laengs-Falloff nicht — die Textur "
                        "existiert, wird aber nirgends angehaengt")
        self.assertTrue(z["istGeteilt"],
                        "jeder Kegel baut sich eine EIGENE Textur — bei 48 "
                        "Geraeten sind das 48 Uploads statt einem")
        self.assertTrue(z["hatColor"] and z["opacityIstZahl"],
                        "Farbe/Deckkraft muessen als Per-Frame-Schreibweg "
                        "erhalten bleiben (applyGenericColor)")


if __name__ == "__main__":
    unittest.main()
