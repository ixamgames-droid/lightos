"""VIZ-71 Review B2/B3: der schlanke Poll (``pollControlRev``) verliert nichts.

Laeuft gegen die ECHTE Produktiv-Seite (offscreen QtWebEngine). Die Mock-Bridge
spielt ``pollControlRev`` wie Python: sie liefert nur Schluessel, deren Revision
die Seite noch nicht quittiert hat, Einmal-Events genau einmal.

  * B2: wirft ein Zustands-Handler (hier: defekte Buehne), gehen die spaeteren
    Schluessel derselben Antwort (Geraeteliste) nicht verloren, und der
    gescheiterte Schluessel bleibt unquittiert — er kommt erneut, bis er nach
    wenigen Versuchen aufgegeben wird (kein Dauer-Neubau).
  * B3: eine noch alte Geraeteliste in derselben Antwort wie das
    ``fixtureAdded`` eines frisch platzierten Geraets wirft dessen DMX-Stand
    nicht aus dem Cache — das Geraet leuchtet nach dem Bau.
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

    @Slot(str, result=str)
    def pollControlRev(self, revs_json):
        """Wie ``VisualizerBridge.pollControlRev``: nur Unquittiertes."""
        gesehen = json.loads(revs_json or "{}")
        self.gesehen.append(gesehen)
        out, neu = {}, {}
        for key, (rev, value) in self.zustand.items():
            if gesehen.get(key) != rev:
                out[key] = value
                neu[key] = rev
        if neu:
            out["_rev"] = neu
        if self.events:
            out["events"] = self.events
            self.events = []
        return json.dumps(out)

    attrs["requestFixtures"] = requestFixtures
    attrs["pollControl"] = pollControl
    attrs["pollControlRev"] = pollControlRev
    attrs["requestFullResync"] = Signal()
    return type("MockVisualizerBridgeViz71Poll", (QObject,), attrs)


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


_FID = 711001


def _geraet(fid=_FID):
    return {"fid": fid, "type": "moving_head", "model": "moving_head",
            "x": 0, "y": 6, "z": 0, "r": 0, "g": 0, "b": 0, "intensity": 0,
            "pan": 128, "tilt": 128}


class Viz71PollRobustTest(unittest.TestCase):
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
        self._b = _MockBridge()
        self._b.zustand = {}
        self._b.events = []
        self._b.gesehen = []
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._b)
        self._view.page().setWebChannel(self._channel)
        self._loaded_ok = []
        self._view.loadFinished.connect(self._loaded_ok.append)

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
        self._warte("!!window.__lightosAppReady")
        # Der Poll laeuft (130 ms-Takt), bevor der Test Zustand vorgibt.
        self._warte_py(lambda: len(self._b.gesehen) >= 2)

    def _eval(self, js_expr):
        box = []
        self._view.page().runJavaScript(js_expr, lambda result: box.append(result))
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(0.01)
        self.assertTrue(box, f"runJavaScript-Callback nie ausgeloest fuer: {js_expr}")
        return box[0]

    def _warte(self, js_expr, timeout_s=_POLL_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            last = self._eval(js_expr)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout beim Warten auf '{js_expr}' (letzter Wert: {last!r})")

    def _warte_py(self, cond, timeout_s=_POLL_TIMEOUT_S, msg="Bedingung"):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if cond():
                return
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout: {msg}")

    # ── B2 ───────────────────────────────────────────────────────────────────
    def test_defekte_buehne_kostet_die_geraeteliste_nicht(self):
        self._load_and_wait()
        self._b.zustand = {"stage": (1, "{kaputt"),
                           "fixtures": (1, json.dumps([_geraet()]))}
        self._warte("!!window.__lightos.fixtures['%d']" % _FID, timeout_s=4.0)
        # Die Geraeteliste ist quittiert, die Buehne kommt erneut ...
        self._warte_py(lambda: self._b.gesehen[-1].get("fixtures") == 1,
                       msg="fixtures nicht quittiert")
        mit_stage = [g for g in self._b.gesehen if "fixtures" in g and "stage" not in g]
        self.assertTrue(mit_stage, "die gescheiterte Buehne wurde sofort quittiert")
        # ... aber nicht endlos: nach wenigen Versuchen aufgegeben.
        self._warte_py(lambda: self._b.gesehen[-1].get("stage") == 1,
                       msg="defekte Buehne wird endlos wiederholt")

    def test_gescheiterter_schluessel_heilt_mit_neuem_wert(self):
        self._load_and_wait()
        self._b.zustand = {"stage": (1, "{kaputt")}
        self._warte_py(lambda: self._b.gesehen[-1].get("stage") == 1,
                       msg="Buehne nie aufgegeben")
        self._b.zustand = {"stage": (2, "{kaputt"),
                           "fixtures": (1, json.dumps([_geraet()]))}
        self._warte("!!window.__lightos.fixtures['%d']" % _FID, timeout_s=4.0)

    # ── B3 ───────────────────────────────────────────────────────────────────
    def test_alte_liste_raeumt_frisch_platziertes_geraet_nicht_weg(self):
        self._load_and_wait()
        # Push fuer X kommt an, bevor X gebaut ist -> Cache.
        n = self._eval("window.__lightos.applyDmx(%s, 3)" % json.dumps(
            [{"fid": _FID, "r": 255, "g": 0, "b": 0, "intensity": 255,
              "pan": 128, "tilt": 128}]))
        self.assertEqual(n, 0)
        # Dieselbe Poll-Antwort: noch die alte Liste (ohne X), danach das
        # fixtureAdded-Event fuer X.
        self._b.events = [{"t": "fixtureAdded", "j": json.dumps(_geraet())}]
        self._b.zustand = {"fixtures": (1, json.dumps([_geraet(_FID + 1)]))}
        self._warte("!!window.__lightos.fixtures['%d']" % _FID)
        i = self._eval("window.__lightos.fixtures['%d'].spot.intensity" % _FID)
        self.assertGreater(i, 0, "frisch platziertes Geraet dunkel (DMX-Cache geraeumt)")

    # ── Live-Pruefung: Show-Wechsel auf eine kleinere Show ───────────────────
    def test_volle_liste_baut_reste_der_alten_show_ab(self):
        """Live gefunden (Mega Arena -> Demo-Show): die volle Liste der neuen
        Show baute nur auf, die 20 Geraete der alten Show blieben im Bild."""
        self._load_and_wait()
        alt, bleibt = _FID + 10, _FID + 11
        self._b.zustand = {"fixtures": (1, json.dumps([_geraet(alt), _geraet(bleibt)]))}
        self._warte("!!window.__lightos.fixtures['%d'] && !!window.__lightos.fixtures['%d']"
                    % (alt, bleibt))
        self._b.zustand = {"fixtures": (2, json.dumps([_geraet(bleibt)]))}
        self._warte("!window.__lightos.fixtures['%d']" % alt, timeout_s=4.0)
        self.assertTrue(self._eval("!!window.__lightos.fixtures['%d']" % bleibt),
                        "Geraet der neuen Show faelschlich entfernt")
        self.assertEqual(self._eval("Object.keys(window.__lightos.fixtures).length"), 1)

    def test_liste_ohne_frisch_platziertes_entfernt_es_nicht(self):
        """B3-Gegenstueck zum Abbau: steht das Geraet nur im fixtureAdded
        DERSELBEN Antwort, bleibt es nach dem Abbau der Reste stehen."""
        self._load_and_wait()
        x = _FID + 20
        self._b.zustand = {"fixtures": (1, json.dumps([_geraet(x)]))}
        self._warte("!!window.__lightos.fixtures['%d']" % x)
        self._b.events = [{"t": "fixtureAdded", "j": json.dumps(_geraet(x))}]
        self._b.zustand = {"fixtures": (2, json.dumps([_geraet(x + 1)]))}
        self._warte("!!window.__lightos.fixtures['%d']" % (x + 1))
        _pump(0.4)
        self.assertTrue(self._eval("!!window.__lightos.fixtures['%d']" % x),
                        "frisch platziertes Geraet vom Rest-Abbau entfernt")


    # ── Review: Show-Wechsel mit wiederverwendeten fids ──────────────────────
    # fids beginnen je Show bei 1. Der DMX-Cache hatte nur die fid als
    # Schluessel; die volle Liste der neuen Show behielt deshalb den Eintrag
    # der alten Show, und das neue Geraet startete mit deren Licht. Python
    # zaehlt jetzt eine Show-Generation hoch (Poll-Zustand ``showGen``, dazu
    # an jedem DMX-Batch); JS leert den Cache, sobald eine neuere kommt.
    def _show(self, gen, fid, **ort):
        g = _geraet(fid)
        g.update(ort)
        self._b.zustand = {"showGen": (gen, gen),
                           "fixtures": (gen, json.dumps([g]))}

    def _neu_gebaut(self, fid):
        self._warte("(function(){ const f = window.__lightos.fixtures['%d'];"
                    " return !!f && !f.__alt; })()" % fid)

    def _licht(self, fid):
        return json.loads(self._eval(
            "(function(){ const f = window.__lightos.fixtures['%d'];"
            " return JSON.stringify({i: f.spot.intensity, r: f.spot.color.r,"
            " b: f.spot.color.b}); })()" % fid))

    def _anwenden(self, eintrag, seq, gen):
        return self._eval("window.__lightos.applyDmx(%s, %d, %d)"
                          % (json.dumps([eintrag]), seq, gen))

    def test_show_wechsel_uebernimmt_keinen_dmx_stand_der_alten_show(self):
        self._load_and_wait()
        fid = 1
        self._show(1, fid)                               # Show A
        self._warte("!!window.__lightos.fixtures['%d']" % fid)
        rot = {"fid": fid, "r": 255, "g": 0, "b": 0, "intensity": 255,
               "pan": 128, "tilt": 128}
        self.assertEqual(self._anwenden(rot, 5, 1), 1)
        self.assertGreater(self._licht(fid)["i"], 0)
        # Show B: fid 1 ist dort ein anderes Geraet an anderer Stelle.
        self._eval("window.__lightos.fixtures['%d'].__alt = true" % fid)
        self._show(2, fid, x=3, z=-2)
        self._neu_gebaut(fid)
        self.assertEqual(self._licht(fid)["i"], 0,
                         "neues Geraet startet mit dem DMX-Stand der alten Show")

    def test_neuer_show_stand_vor_der_liste_bleibt_und_alter_verfaellt(self):
        """Nach dem Show-Wechsel schiebt der Service sofort den vollen Bestand —
        der Push ist meist VOR dem naechsten Poll mit der neuen Liste da. Dieser
        Stand darf beim Leeren nicht verloren gehen; ein verspaeteter Batch der
        alten Show dagegen schon."""
        self._load_and_wait()
        fid = 1
        self._show(1, fid)
        self._warte("!!window.__lightos.fixtures['%d']" % fid)
        rot = {"fid": fid, "r": 255, "g": 0, "b": 0, "intensity": 255,
               "pan": 128, "tilt": 128}
        blau = dict(rot, r=0, b=255)
        self._anwenden(rot, 5, 1)
        self._anwenden(blau, 6, 2)                       # neue Show, vor der Liste
        self._eval("window.__lightos.fixtures['%d'].__alt = true" % fid)
        self._show(2, fid, x=3, z=-2)
        self._neu_gebaut(fid)
        l = self._licht(fid)
        self.assertGreater(l["i"], 0, "Stand der neuen Show beim Leeren verloren")
        self.assertAlmostEqual(l["b"], 1.0, places=2)
        # Ein spaeter Batch der alten Show (hoehere Seq, alte Generation).
        self.assertEqual(self._anwenden(rot, 7, 1), 0, "Batch der alten Show angewandt")
        self.assertAlmostEqual(self._licht(fid)["b"], 1.0, places=2)

    def test_neubau_in_derselben_show_behaelt_den_stand(self):
        """N2 auch mit Generation: Einmessen/refresh_fixture baut EIN Geraet
        neu, die Generation bleibt — der Stand bleibt."""
        self._load_and_wait()
        fid = 1
        self._show(1, fid)
        self._warte("!!window.__lightos.fixtures['%d']" % fid)
        rot = {"fid": fid, "r": 255, "g": 0, "b": 0, "intensity": 255,
               "pan": 128, "tilt": 128}
        self._anwenden(rot, 5, 1)
        self._eval("window.__lightos.fixtures['%d'].__alt = true" % fid)
        self._b.events = [{"t": "fixtureAdded", "j": json.dumps(_geraet(fid))}]
        self._neu_gebaut(fid)
        self.assertGreater(self._licht(fid)["i"], 0, "Neubau in derselben Show dunkel")


if __name__ == "__main__":
    unittest.main()
