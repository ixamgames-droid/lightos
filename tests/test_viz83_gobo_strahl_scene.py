"""VIZ-83: das Gobo FORMT den Strahl, statt nur Lichtkreise dazuzulegen.

Befund (Videos der Buehnen-Show): mit aktivem Gobo blieb der normale
Lichtkegel komplett stehen, und im Bodenfleck erschienen ZUSAETZLICHE
Lichtkreise. Ursache: nur die Bodenscheibe bekam das Muster; der Kegel blieb
voll, und der SpotLight leuchtete am Boden weiter den runden Fleck aus.

Erwartet und hier ueber den Produktivweg (Payload aus Python -> push_script)
geprueft:

* Gobo aktiv -> der Kegel traegt die Teilstrahl-Maske des Motivs (der volle
  Kegel ist weg: der groesste Teil des Umfangs ist dunkel, mehrere getrennte
  helle Teilstrahlen bleiben), der SpotLight ist gedrosselt.
* Gobo-Drehung dreht Kegel (und damit die Teilstrahlen) und Bodenmuster.
* "Gobo 3" ohne Motiv-Wort ergibt ein Motiv (VIZ-82).
* Offen -> Kegel wie bisher (weisse Maske, volle SpotLight-Staerke).
* Keine neue Geometrie, kein neues Objekt, kein Material-Neubau je Update.
"""
import json
import math
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

from src.ui.visualizer.dmx_push import push_script
from src.ui.visualizer.visualizer_service import _build_fixture_payload

_app = QApplication.instance() or QApplication([])

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HTML_PATH = os.path.join(_REPO, "src", "ui", "visualizer", "stage_scene.html")

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05

_SIGNAL_SPECS = [
    ("fixtureAdded", (str,)), ("fixtureRemoved", (int,)),
    ("allFixtures", (str,)), ("settingsChanged", (str,)),
    ("viewModeChanged", (str,)), ("editModeChanged", (str,)),
    ("stageLoaded", (str,)), ("addStageObject", (str,)),
    ("addStageObjectData", (str,)), ("removeStageObject", (str,)),
    ("selectStageObject", (str,)), ("applyFixtureTransform", (str,)),
    ("alignSelected", (str,)), ("distributeSelected", (str,)),
    ("cameraReset", ()), ("brightnessSignal", (float,)),
    ("brightnessAutoSignal", ()), ("updateStageObject", (str,)),
    ("resizeModeSignal", (bool,)), ("pixelRatioSignal", (float,)),
]


def _make_mock_bridge_class():
    attrs = {name: Signal(*types) for name, types in _SIGNAL_SPECS}

    @Slot()
    def requestFixtures(self):
        pass

    @Slot(result=str)
    def pollControl(self):
        return "{}"

    attrs["requestFixtures"] = requestFixtures
    attrs["pollControl"] = pollControl
    attrs["requestFullResync"] = Signal()
    return type("MockVisualizerBridgeViz83", (QObject,), attrs)


_MockBridge = _make_mock_bridge_class()


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


class _Range:
    def __init__(self, lo, hi, name):
        self.range_from, self.range_to, self.name = lo, hi, name
        self.kind = ""


class _Ch:
    def __init__(self, attribute, ranges=()):
        self.attribute = attribute
        self.ranges = list(ranges)


_FID = 830001


class _Fx:
    fid = _FID
    fixture_type = "moving_head"


_KANAELE = [
    _Ch("intensity"), _Ch("color_r"), _Ch("color_g"), _Ch("color_b"),
    _Ch("pan"), _Ch("tilt"),
    _Ch("gobo_wheel", [_Range(0, 9, "Offen / kein Gobo"),
                       _Range(10, 19, "Gobo 6 (Spirale)"),
                       _Range(20, 29, "Gobo 5 (Punkte)"),
                       _Range(30, 39, "Gobo 3")]),
    _Ch("gobo_rotation"),
    _Ch("prism", [_Range(0, 9, "Aus"), _Range(10, 255, "3 Facet Prism")]),
    _Ch("prism_rotation"),
]

_GRUND = {"intensity": 255, "color_r": 255, "color_g": 255, "color_b": 255,
          "pan": 128, "tilt": 128, "gobo_wheel": 0, "gobo_rotation": 0,
          "prism": 0, "prism_rotation": 0}


def _payload(**attrs):
    a = dict(_GRUND)
    a.update(attrs)
    return _build_fixture_payload(_Fx(), a, _KANAELE)


def _geraet(fid=_FID):
    return {"fid": fid, "type": "moving_head", "model": "moving_head",
            "x": 0, "y": 6, "z": 0, "rotX": 0, "rotY": 0, "rotZ": 0,
            "r": 0, "g": 0, "b": 0, "intensity": 0, "pan": 128, "tilt": 128}


# Zustand des Kegels: welche Maske, wie viel vom Umfang hell (Mittelzeile der
# Masken-Textur), wie viele getrennte helle Teilstrahlen, Drehung, Spot.
_ZUSTAND_JS = """
(function(){
  const L = window.__lightos;
  const f = L.fixtures['%d'];
  if (!f) return 'null';
  const map = f.beam.material.map;
  let hell = -1, strahlen = -1;
  if (map && map.image && map.image.getContext) {
    const c = map.image, g = c.getContext('2d');
    const zeile = g.getImageData(0, Math.floor(c.height / 2), c.width, 1).data;
    let n = 0, wechsel = 0, vorher = zeile[(c.width - 1) * 4] > 127;
    for (let x = 0; x < c.width; x++) {
      const an = zeile[x * 4] > 127;
      if (an) n++;
      if (an && !vorher) wechsel++;
      vorher = an;
    }
    hell = n / c.width; strahlen = wechsel;
  }
  const geos = new Set(); let objekte = 0;
  f.group.traverse(o => { objekte++; if (o.geometry) geos.add(o.geometry.uuid); });
  if (f.floorSpot && f.floorSpot.geometry) geos.add(f.floorSpot.geometry.uuid);
  return JSON.stringify({
    mapOffen: map === L.__beamGoboTexture(''),
    mapSpirale: !!map && map === L.__beamGoboTexture('spiral'),
    mapPunkte: !!map && map === L.__beamGoboTexture('dots'),
    mapKreise: !!map && map === L.__beamGoboTexture('circle_of_circles'),
    hell: hell, strahlen: strahlen,
    beamRot: f.beam.rotation.y,
    prismRot: (f.prismCones || []).map(m => m.rotation.y),
    fleckRot: f.floorSpot ? f.floorSpot.rotation.z : null,
    fleckMuster: !!(f.floorSpot && f.floorSpot.material.map),
    spot: f.spot.intensity,
    beamOpacity: f.beam.material.opacity,
    beamSichtbar: f.beam.visible,
    matVersion: f.beam.material.version,
    geos: geos.size, objekte: objekte,
  });
})()
"""


class Viz83GoboStrahlSceneTest(unittest.TestCase):
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
        self._bridge_obj = _MockBridge()
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._bridge_obj)
        self._view.page().setWebChannel(self._channel)
        self._loaded_ok = []
        self._view.loadFinished.connect(self._loaded_ok.append)
        self._seq = 0

    def tearDown(self):
        destroy_webengine_view(self._view, _pump)
        self._view = None

    def _load_and_wait(self):
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}")
        self._view.load(url)
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded_ok and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded_ok and self._loaded_ok[-1], "Seite nicht geladen")
        self._poll_until_true("!!window.__lightosAppReady")
        self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(json.dumps([_geraet()])),
            "!!window.__lightos.fixtures['%d']" % _FID)

    def _eval(self, js_expr):
        box = []
        self._view.page().runJavaScript(js_expr, lambda result: box.append(result))
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(0.01)
        self.assertTrue(box, f"runJavaScript-Callback nie ausgeloest fuer: {js_expr}")
        return box[0]

    def _poll_until_true(self, js_expr, timeout_s=_POLL_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            last = self._eval(js_expr)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout beim Warten auf '{js_expr}' (letzter Wert: {last!r})")

    def _emit_until_true(self, emit_fn, js_expr, timeout_s=_POLL_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            emit_fn()
            last = self._eval(js_expr)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout nach wiederholtem Emit: '{js_expr}' (letzter Wert: {last!r})")

    def _push(self, *payloads):
        entries = []
        for p in payloads:
            self._seq += 1
            entries.append((self._seq, p))
        n = self._eval(push_script(entries))
        self.assertEqual(n, len(payloads), "Push erreichte das Geraet nicht")

    def _z(self):
        return json.loads(self._eval(_ZUSTAND_JS % _FID))

    # ── Tests ────────────────────────────────────────────────────────────────
    def test_offen_bleibt_der_volle_kegel(self):
        self._load_and_wait()
        self._push(_payload(gobo_wheel=0))
        z = self._z()
        self.assertTrue(z["mapOffen"], f"offener Kegel ohne weisse Maske: {z}")
        self.assertAlmostEqual(z["hell"], 1.0, places=6)
        self.assertAlmostEqual(z["spot"], 3.0, places=6)
        self.assertFalse(z["fleckMuster"])
        self.assertTrue(z["beamSichtbar"])

    def test_gobo_ersetzt_den_vollen_kegel_durch_teilstrahlen(self):
        self._load_and_wait()
        self._push(_payload(gobo_wheel=0))
        offen = self._z()
        self._push(_payload(gobo_wheel=25))            # "Gobo 5 (Punkte)"
        z = self._z()
        self.assertTrue(z["mapPunkte"], f"Kegel traegt die Punkte-Maske nicht: {z}")
        self.assertLess(z["hell"], 0.5, "voller Kegel noch sichtbar")
        self.assertGreater(z["hell"], 0.05, "keine Teilstrahlen mehr")
        self.assertGreaterEqual(z["strahlen"], 10, f"zu wenige Teilstrahlen: {z}")
        self.assertTrue(z["beamSichtbar"])
        self.assertTrue(z["fleckMuster"], "Bodenfleck ohne Muster")
        # Der unmaskierbare SpotLight leuchtet den runden Fleck nicht mehr voll.
        self.assertLess(z["spot"], offen["spot"] * 0.5)
        self.assertGreater(z["spot"], 0.0)
        # Zurueck auf offen: alles wie vorher.
        self._push(_payload(gobo_wheel=0))
        zurueck = self._z()
        self.assertTrue(zurueck["mapOffen"])
        self.assertAlmostEqual(zurueck["spot"], offen["spot"], places=6)
        self.assertAlmostEqual(zurueck["beamOpacity"], offen["beamOpacity"], places=6)

    def test_spirale_ist_eine_wendel(self):
        self._load_and_wait()
        self._push(_payload(gobo_wheel=15))            # "Gobo 6 (Spirale)"
        z = self._z()
        self.assertTrue(z["mapSpirale"], z)
        self.assertLess(z["hell"], 0.5)
        self.assertGreaterEqual(z["strahlen"], 3)
        # Wendel: oben und unten liegen die Streifen an verschiedenen Stellen.
        versatz = self._eval("""(function(){
          const c = window.__lightos.__beamGoboTexture('spiral').image;
          const g = c.getContext('2d');
          const o = g.getImageData(0, 2, c.width, 1).data;
          const u = g.getImageData(0, c.height - 3, c.width, 1).data;
          let gleich = 0;
          for (let x = 0; x < c.width; x++) if ((o[x*4] > 127) === (u[x*4] > 127)) gleich++;
          return gleich / c.width; })()""")
        self.assertLess(versatz, 0.9, "Spirale laeuft nicht schraeg")

    def test_nummeriertes_gobo_ergibt_motiv(self):
        """VIZ-82: "Gobo 3" ohne Motiv-Wort -> festes Motiv, Strahl zerfaellt."""
        self.assertEqual(_payload(gobo_wheel=35)["gobo"], "circle_of_circles")
        self._load_and_wait()
        self._push(_payload(gobo_wheel=35))
        z = self._z()
        self.assertTrue(z["mapKreise"], z)
        self.assertLess(z["hell"], 0.5)
        self.assertEqual(z["strahlen"], 7)

    def test_drehung_dreht_teilstrahlen_prisma_und_bodenmuster(self):
        self._load_and_wait()
        self._push(_payload(gobo_wheel=25, gobo_rotation=64, prism=50))
        z = self._z()
        soll = 64 / 255 * 2 * math.pi
        self.assertAlmostEqual(z["beamRot"], soll, places=4)
        self.assertAlmostEqual(z["fleckRot"], soll, places=4)
        self.assertEqual(len(z["prismRot"]), 2)
        for r in z["prismRot"]:
            self.assertAlmostEqual(r, soll, places=4)
        self._push(_payload(gobo_wheel=25, gobo_rotation=0, prism=50))
        z = self._z()
        self.assertAlmostEqual(z["beamRot"], 0.0, places=6)

    def test_dimmer_fade_kommt_bei_gobo_an(self):
        """Die Gobo-Anhebung darf die Deckkraft nicht vor 100 % Dimmer kappen."""
        self._load_and_wait()
        werte = []
        for dimmer in (179, 204, 230, 255):          # ~0,70 ... 1,0
            self._push(_payload(gobo_wheel=25, intensity=dimmer))
            werte.append(self._z()["beamOpacity"])
        for a, b in zip(werte, werte[1:]):
            self.assertGreater(b, a + 1e-3, f"Deckkraft steigt nicht mit dem Dimmer: {werte}")
        self.assertLessEqual(werte[-1], 1.0 + 1e-9)

    def test_keine_neue_geometrie_und_kein_materialneubau_je_update(self):
        self._load_and_wait()
        self._push(_payload(gobo_wheel=0))
        vorher = self._z()
        for w in (15, 25, 35, 0, 25, 15, 0, 35):
            for rot in (0, 90, 200):
                self._push(_payload(gobo_wheel=w, gobo_rotation=rot))
        self._push(_payload(gobo_wheel=0))
        nachher = self._z()
        self.assertEqual(nachher["geos"], vorher["geos"])
        self.assertEqual(nachher["objekte"], vorher["objekte"])
        self.assertEqual(nachher["matVersion"], vorher["matVersion"],
                         "Gobo-Wechsel hat das Kegel-Material neu gebaut")
        self.assertTrue(nachher["mapOffen"])


if __name__ == "__main__":
    unittest.main()
