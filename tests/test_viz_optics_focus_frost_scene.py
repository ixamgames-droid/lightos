"""VIZ-MH-OPTICS: Fokus und Frost weichen die Kegelkante auf — in echter QWebEngine.

Zoom und Iris sind seit PR #523 im 3D angekommen. Offen blieb die Kantenschärfe.

★ **Fokus ist ausdrücklich KEINE 0→255-Rampe** — und das ist der Kern dieser
Ergänzung. Physikalisch ist Fokus eine *beidseitige* mechanische Verstellung:
die Linse läuft von nah nach fern, scharf ist sie irgendwo dazwischen. Eine
monotone Abbildung wäre schlicht falsch.

Wo „dazwischen" liegt, sagt die Fixture-Library selbst: **jedes** eingebaute
Profil mit Fokus-Kanal setzt den Default auf 128 (4 von 4 nachgezählt), während
Frost und Prisma bei 0 stehen (4 von 4). Ein Default von 128 heißt „Mitte des
Wegs" — die beste verfügbare Aussage darüber, welche Stellung der Profil-Autor
für normal hielt. Also: scharf bei 128, zu beiden Enden weicher. Frost dagegen
ist monoton (0 = kein Diffusor, 255 = voll).

**Warum dieser Test die Funktionen wirklich ausführt statt den Quelltext zu
greppen:** die erste Fassung der Optik-Tests prüfte per Regex, ob bestimmte
Konstanten in `optics.js` stehen. Das hätte eine falsche *Formel* mit richtigen
Konstanten anstandslos durchgewinkt — und genau die Formel ist hier die Aussage.
`opticsSoftness` und `applyOptics` sind rein (kein Szenen-Zustand, keine
three.js-Abhängigkeit), deshalb kann der Test sie mit einem gestellten
Fixture-Objekt aufrufen und Zahlen zurückrechnen.
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

_SIGNAL_SPECS = [
    ("fixtureAdded", (str,)), ("fixtureRemoved", (int,)), ("dmxBatch", (str,)),
    ("allFixtures", (str,)), ("settingsChanged", (str,)), ("viewModeChanged", (str,)),
    ("editModeChanged", (str,)), ("stageLoaded", (str,)), ("addStageObject", (str,)),
    ("addStageObjectData", (str,)), ("removeStageObject", (str,)),
    ("selectStageObject", (str,)), ("applyFixtureTransform", (str,)),
    ("alignSelected", (str,)), ("distributeSelected", (str,)),
    ("arrangeSelected", (str,)), ("cameraReset", ()),
    ("brightnessSignal", (float,)), ("brightnessAutoSignal", ()),
    ("updateStageObject", (str,)), ("resizeModeSignal", (bool,)),
    ("pixelRatioSignal", (float,)),
]


def _make_mock_bridge_class():
    attrs = {name: Signal(*arg_types) for name, arg_types in _SIGNAL_SPECS}

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
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


# Ein gestelltes Fixture: nur die Felder, die applyOptics anfasst. Der
# scale.set-Aufruf wird mitgeschrieben, damit der Test die Aufweitung sieht.
_FAKE_FIXTURE = """
(function () {
  const f = {
    beam: { scale: { x: 1, y: 1, z: 1,
                     set(a, b, c) { this.x = a; this.y = b; this.z = c; } } },
    spot: { angle: 0.30, penumbra: 0.60 },
    baseSpotAngle: 0.30,
  };
  window.__optProbe = f;
  return true;
})()
"""


class OpticsFocusFrostSceneTest(unittest.TestCase):
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
        self._bridge_obj = _MockVisualizerBridge()
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._bridge_obj)
        self._view.page().setWebChannel(self._channel)
        self._loaded_ok = []
        self._view.loadFinished.connect(self._loaded_ok.append)

    def tearDown(self):
        destroy_webengine_view(self._view, _pump)   # XPLAT-09
        self._view = None

    def _eval(self, js):
        box = []
        self._view.page().runJavaScript(js, lambda r: box.append(r))
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(box, f"runJavaScript ohne Callback: {js}")
        return box[0]

    def _poll_until_true(self, js, timeout_s=_POLL_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            last = self._eval(js)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout bei '{js}' (letzter: {last!r})")

    def _load_and_wait(self):
        self._loaded_ok.clear()
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}")
        self._view.load(url)
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded_ok and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded_ok and self._loaded_ok[-1], "Page nicht geladen")
        self._poll_until_true("!!window.__lightosAppReady")

    def _weich(self, focus=None, frost=None):
        """opticsSoftness mit echten Zahlen ausfuehren."""
        f = "undefined" if focus is None else str(focus)
        fr = "undefined" if frost is None else str(frost)
        return float(self._eval(f"window.__lightos.opticsSoftness({f}, {fr})"))

    def _anwenden(self, **dmx):
        """applyOptics auf ein frisches gestelltes Fixture; liefert die Zahlen."""
        self._eval(_FAKE_FIXTURE)
        self._eval("window.__lightos.applyOptics(window.__optProbe, "
                   + json.dumps(dmx) + ")")
        roh = self._eval("JSON.stringify({penumbra: window.__optProbe.spot.penumbra,"
                         " skala: window.__optProbe.beam.scale.x,"
                         " winkel: window.__optProbe.spot.angle})")
        return json.loads(roh)

    # ── Die Kennlinie ───────────────────────────────────────────────────────
    def test_fokus_ist_bei_128_am_schaerfsten_und_zu_BEIDEN_enden_weicher(self):
        """Der Kern: eine monotone 0→255-Rampe wäre physikalisch falsch."""
        self._load_and_wait()
        mitte = self._weich(focus=128)
        unten = self._weich(focus=0)
        oben = self._weich(focus=255)
        self.assertAlmostEqual(mitte, 0.0, delta=0.01,
                               msg="bei 128 muss der Kegel scharf sein")
        self.assertGreater(unten, 0.9, "DMX 0 muss weich sein")
        self.assertGreater(oben, 0.9, "DMX 255 muss weich sein")
        # und wirklich BEIDSEITIG, nicht nur zufaellig an den Enden:
        self.assertGreater(self._weich(focus=64), self._weich(focus=100))
        self.assertGreater(self._weich(focus=192), self._weich(focus=160))

    def test_frost_ist_dagegen_monoton(self):
        self._load_and_wait()
        werte = [self._weich(frost=v) for v in (0, 64, 128, 192, 255)]
        self.assertAlmostEqual(werte[0], 0.0, delta=0.01, msg="kein Frost = scharf")
        self.assertAlmostEqual(werte[-1], 1.0, delta=0.01, msg="voller Frost = ganz weich")
        for a, b in zip(werte, werte[1:]):
            self.assertLess(a, b, f"Frost nicht monoton: {werte}")

    def test_fokus_und_frost_addieren_sich_nicht_ueber_1(self):
        """Beide diffundieren; die verbleibende SCHÄRFE multipliziert sich.
        Additiv könnte die Weichheit über 1 laufen und die Penumbra ungültig
        werden."""
        self._load_and_wait()
        w = self._weich(focus=0, frost=255)
        self.assertLessEqual(w, 1.0)
        self.assertGreaterEqual(w, self._weich(focus=0))
        self.assertGreaterEqual(w, self._weich(frost=255))

    # ── Die Wirkung auf die Szene ───────────────────────────────────────────
    def test_weiche_kante_landet_wirklich_auf_der_penumbra(self):
        self._load_and_wait()
        scharf = self._anwenden(focus=128)
        weich = self._anwenden(focus=0)
        self.assertLess(scharf["penumbra"], 0.2,
                        "scharfer Fokus muss eine harte Kante geben")
        self.assertGreater(weich["penumbra"], 0.8,
                           "unscharfer Fokus muss eine weiche Kante geben")

    def test_geraet_ohne_fokus_und_frost_behaelt_seine_kante(self):
        """★ Dieselbe Falle wie der erfundene 128er-Zoom-Default: ein
        Scheinwerfer ohne diese Kanäle darf keine erfundene Kantenschärfe
        bekommen. Zoom allein darf die Penumbra nicht anfassen."""
        self._load_and_wait()
        nur_zoom = self._anwenden(zoom=200)
        self.assertAlmostEqual(nur_zoom["penumbra"], 0.60, delta=0.001,
                               msg="Penumbra ohne Fokus/Frost-Kanal veraendert")
        self.assertGreater(nur_zoom["skala"], 1.0, "Zoom hat gar nicht gewirkt")

    def test_frost_weitet_den_kegel_auf_fokus_nicht(self):
        """Frost streut real; eine unscharfe Kante ist dagegen keine breitere."""
        self._load_and_wait()
        ohne = self._anwenden(frost=0)
        voll = self._anwenden(frost=255)
        nur_fokus = self._anwenden(focus=0)
        self.assertGreater(voll["skala"], ohne["skala"] * 1.1,
                           "voller Frost weitet den Kegel nicht auf")
        self.assertAlmostEqual(nur_fokus["skala"], 1.0, delta=0.001,
                               msg="Fokus darf die Kegelbreite nicht aendern")

    def test_werte_bleiben_stehen_wenn_ein_batch_sie_nicht_nennt(self):
        """Der Service schickt DIFFERENTIELL — ein Batch ohne `frost` heißt
        „unverändert" und darf die Kante nicht zurückspringen lassen."""
        self._load_and_wait()
        self._eval(_FAKE_FIXTURE)
        self._eval("window.__lightos.applyOptics(window.__optProbe, {frost: 255})")
        self._eval("window.__lightos.applyOptics(window.__optProbe, {zoom: 128})")
        p = float(self._eval("window.__optProbe.spot.penumbra"))
        self.assertGreater(p, 0.8, "Frost wurde von einem zoom-only-Batch vergessen")

    def test_spotwinkel_bleibt_gueltig(self):
        """Ein SpotLight-Winkel >= PI/2 ist ungültig; Zoom weit + Frost voll ist
        der grösste Fall, den die Kette erzeugen kann."""
        self._load_and_wait()
        extrem = self._anwenden(zoom=255, frost=255)
        self.assertLess(extrem["winkel"], 3.14159 / 2)


if __name__ == "__main__":
    unittest.main()
