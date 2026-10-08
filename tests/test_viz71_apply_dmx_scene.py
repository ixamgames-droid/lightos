"""VIZ-71: DMX kommt in der Szene ueber EINE Stelle an — ``applyDmx``.

Laeuft gegen die ECHTE Produktiv-Seite (offscreen QtWebEngine). Wie in den
anderen Szenen-Tests wird JS direkt per ``runJavaScript`` getrieben: eine
offscreen-Seite drosselt Post-Load-Signale, ``runJavaScript`` nicht (und genau
das ist seit VIZ-71 auch der Produktivweg des DMX-Pushs).

Abgedeckt (Entwurf VIZ-71, T10–T13):
  * T10 (N1): DMX fuer ein noch nicht gebautes Geraet geht nicht verloren —
    das Geraet zeigt nach dem Bau den DMX-Stand statt dunkel.
  * T11 (N2): ein Neubau desselben Geraets behaelt den letzten DMX-Stand.
  * T12: ``pan: 0`` heisst ganz links, nicht Mitte (``??`` statt ``||``).
  * T13: ein Eintrag mit AELTERER Sequenznummer wird verworfen.
Dazu: das Push-Skript aus ``dmx_push.py`` liefert vor dem Laden ``-1`` und
danach eine Zahl, ein entferntes Geraet vergisst seinen Stand.
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
    return type("MockVisualizerBridgeViz71", (QObject,), attrs)


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


_FID = 710001


def _geraet(fid=_FID, **extra):
    """So, wie Python ein Geraet baut: mit den festen Nullen aus
    ``_fixture_to_dict`` (dunkel, Pan/Tilt Mitte)."""
    d = {"fid": fid, "type": "moving_head", "model": "moving_head",
         "x": 0, "y": 6, "z": 0, "r": 0, "g": 0, "b": 0, "intensity": 0,
         "pan": 128, "tilt": 128}
    d.update(extra)
    return d


def _rot(fid=_FID, **extra):
    d = {"fid": fid, "r": 255, "g": 0, "b": 0, "intensity": 255,
         "pan": 128, "tilt": 128}
    d.update(extra)
    return d


class Viz71ApplyDmxSceneTest(unittest.TestCase):
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

    def tearDown(self):
        destroy_webengine_view(self._view, _pump)
        self._view = None

    # ── Helfer ───────────────────────────────────────────────────────────────
    def _load_and_wait(self):
        url = QUrl.fromLocalFile(_HTML_PATH)
        # QA-86: Stufe fest, sonst waehlt die GPU-Probe des Testrechners
        # (Windows/ANGLE meldet 16 Textur-Einheiten -> 'low', Prisma gedeckelt).
        url.setQuery(f"v={int(time.time() * 1000)}&gputier=high")
        self._view.load(url)
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded_ok and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded_ok and self._loaded_ok[-1], "Seite nicht geladen")
        self._poll_until_true("!!window.__lightosAppReady")

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

    def _apply(self, arr, seq="undefined"):
        seq_js = json.dumps(seq) if seq != "undefined" else "undefined"
        return self._eval("window.__lightos.applyDmx(%s, %s)" % (json.dumps(arr), seq_js))

    def _bauen(self, data):
        self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(json.dumps([data])),
            "!!window.__lightos.fixtures['%d']" % data["fid"])

    def _spot(self, fid=_FID):
        return json.loads(self._eval(
            "(function(){ const f = window.__lightos.fixtures['%d'];"
            " if (!f) return 'null';"
            " return JSON.stringify({i: f.spot.intensity, r: f.spot.color.r,"
            " g: f.spot.color.g, b: f.spot.color.b, pan: f._lastPanRad || 0}); })()" % fid))

    # ── T10 (N1) ─────────────────────────────────────────────────────────────
    def test_dmx_vor_dem_bau_geht_nicht_verloren(self):
        self._load_and_wait()
        n = self._apply([_rot()], 5)
        self.assertEqual(n, 0, "das Geraet gibt es noch nicht — nichts angewandt")
        self._bauen(_geraet())
        s = self._spot()
        self.assertGreater(s["i"], 0, "Geraet nach dem Bau dunkel (N1: DMX verpufft)")
        self.assertAlmostEqual(s["r"], 1.0, places=2)
        self.assertAlmostEqual(s["g"], 0.0, places=2)

    # ── T11 (N2) ─────────────────────────────────────────────────────────────
    def test_neubau_behaelt_den_letzten_dmx_stand(self):
        self._load_and_wait()
        self._bauen(_geraet())
        self.assertEqual(self._apply([_rot()], 1), 1)
        self.assertGreater(self._spot()["i"], 0)
        # Neubau (Einmessen/Platzieren/Wiedereinblenden): Marke setzen und
        # warten, bis das Objekt ersetzt ist.
        self._eval("window.__lightos.fixtures['%d'].__alt = true" % _FID)
        self._emit_until_true(
            lambda: self._bridge_obj.fixtureAdded.emit(json.dumps(_geraet())),
            "(function(){ const f = window.__lightos.fixtures['%d'];"
            " return !!f && !f.__alt; })()" % _FID)
        s = self._spot()
        self.assertGreater(s["i"], 0, "Neubau setzte das Geraet auf dunkel (N2)")
        self.assertAlmostEqual(s["r"], 1.0, places=2)

    # ── T12 ──────────────────────────────────────────────────────────────────
    def test_pan_null_ist_nicht_die_mitte(self):
        self._load_and_wait()
        self._bauen(_geraet())
        self._apply([_rot(pan=128)], 1)
        mitte = self._spot()["pan"]
        self._apply([_rot(pan=0)], 2)
        links = self._spot()["pan"]
        self.assertAlmostEqual(mitte, 0.0, places=3)
        self.assertGreater(abs(links - mitte), 0.1,
                           "pan 0 wurde wie 128 behandelt (d.pan||128)")

    # ── T13 ──────────────────────────────────────────────────────────────────
    def test_aeltere_sequenz_wird_verworfen(self):
        self._load_and_wait()
        self._bauen(_geraet())
        self._apply([_rot()], 10)
        blau = {"fid": _FID, "r": 0, "g": 0, "b": 255, "intensity": 255,
                "pan": 128, "tilt": 128}
        self.assertEqual(self._apply([blau], 9), 0, "ueberholter Eintrag angewandt")
        self.assertAlmostEqual(self._spot()["r"], 1.0, places=2)
        self.assertEqual(self._apply([blau], [11]), 1, "Seq-Liste je Eintrag")
        s = self._spot()
        self.assertAlmostEqual(s["b"], 1.0, places=2)
        self.assertAlmostEqual(s["r"], 0.0, places=2)
        # Ohne Nummer (Alt-Aufrufer) gilt der Eintrag immer.
        self.assertEqual(self._apply([_rot()]), 1)
        self.assertAlmostEqual(self._spot()["r"], 1.0, places=2)

    # ── Push-Skript + Aufraeumen ──────────────────────────────────────────────
    def test_push_skript_meldet_bereitschaft_als_zahl(self):
        from src.ui.visualizer.dmx_push import push_script
        self._load_and_wait()
        self._bauen(_geraet())
        r = self._eval(push_script([(3, _rot())]))
        self.assertEqual(r, 1, "Rueckgabe muss eine Zahl sein (Anzahl angewandt)")
        self.assertAlmostEqual(self._spot()["r"], 1.0, places=2)
        # Ohne window.__lightos (Seite laedt noch): -1.
        r = self._eval("(function(){ const L = window.__lightos;"
                       " delete window.__lightos;"
                       " const r = (%s); window.__lightos = L; return r; })()"
                       % push_script([(4, _rot())]))
        self.assertEqual(r, -1)

    def test_entferntes_geraet_vergisst_seinen_stand(self):
        self._load_and_wait()
        self._bauen(_geraet())
        self._apply([_rot()], 1)
        self.assertEqual(self._eval("window.__lightos.dmxCacheInfo().size"), 1)
        self._emit_until_true(
            lambda: self._bridge_obj.fixtureRemoved.emit(_FID),
            "!window.__lightos.fixtures['%d']" % _FID)
        self.assertEqual(self._eval("window.__lightos.dmxCacheInfo().size"), 0)
        # Neu platziert: ohne frischen DMX wieder mit den Nullen der Liste.
        self._bauen(_geraet())
        self.assertEqual(self._spot()["i"], 0)

    def test_volle_liste_raeumt_reste_weg(self):
        self._load_and_wait()
        self._apply([_rot(fid=_FID), _rot(fid=_FID + 1)], 1)
        self.assertEqual(self._eval("window.__lightos.dmxCacheInfo().size"), 2)
        self._bauen(_geraet(_FID))
        self.assertEqual(self._eval("window.__lightos.dmxCacheInfo().size"), 1,
                         "Eintrag einer fid ausserhalb der vollen Liste blieb liegen")


class Viz71QuelltextTest(unittest.TestCase):
    """T6: der Signal-Weg fuer DMX ist weg — statisch, laeuft ohne GPU."""

    def _js(self, *teile):
        return open(os.path.join(_REPO, "src", "ui", "visualizer", "scene_src", *teile),
                    encoding="utf-8").read()

    def test_kein_dmxbatch_connect_mehr(self):
        self.assertNotIn("bridge.dmxBatch.connect", self._js("bridge", "bridge.js"))

    def test_kein_oder_default_fuer_pan_tilt(self):
        for teile in (("bridge", "bridge.js"), ("bridge", "dmx_apply.js"),
                      ("fixtures", "fixtures.js")):
            code = "\n".join(z for z in self._js(*teile).splitlines()
                             if not z.lstrip().startswith("//"))
            for muster in ("pan||128", "tilt||128", "pan || 128", "tilt || 128"):
                self.assertNotIn(muster, code, f"{teile[-1]}: {muster}")


if __name__ == "__main__":
    unittest.main()
