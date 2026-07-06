"""VIZ-13 3c-2: On-Demand-Rendering — der Loop rendert nur noch bei Aenderung.

Belegt gegen die ECHTE ``stage_scene.html`` (gleicher Harness wie
``test_viz13c1_topdown_polish.py``: offscreen QWebEngineView + Mock-Bridge +
runJavaScript-Polling):

  1) IDLE: ohne Aenderung oeffnet das Render-Gate NICHT (Zaehler konstant).
  2) dmxBatch loest einen Render aus; danach faellt der Loop zurueck in Idle.
  3) Kamera-Aenderung (JS->JS ``setCameraPreset``) loest einen Render aus.
  4) COALESCING: N x ``requestRender()`` vor dem naechsten Tick = GENAU EIN
     Render (Flag, kein Zaehler).
  5) KONTINUIERLICHE ANIMATION: solange ein Stage-Element selektiert ist
     (Puls), rendert JEDER Tick (``hasLiveAnimation``-Probe); nach dem
     Deselektieren kehrt der Loop in den Idle-Zustand zurueck.

MESS-SEMANTIK (wichtig fuer Abnahme): ``renderStats().count`` zaehlt die
GATE-OEFFNUNGEN des Loops — d.h. die Aufrufe von ``renderer.render()``,
unabhaengig davon, ob der GL-Draw offscreen tatsaechlich Pixel erzeugt.
Gate zu == ``renderer.render()`` wird NICHT gerufen; Gate offen == genau ein
Aufruf. Das haelt die Messung im offscreen-Lauf (ohne echte GPU)
deterministisch.

TIMING-UNABHAENGIG: eine offscreen/inaktive QtWebEngine-Seite drosselt rAF
UND Post-Load-Signale (Second-Brain ``reference_qwebchannel_headless_
delivery``) — deshalb treibt der Test die Loop-Ticks SELBST ueber den Hook
``window.__lightos.__renderTick()`` (identischer Tick-Body wie der rAF-Loop)
und stuetzt sich nie auf sleep/Framerate. Alle Asserts sind auch dann
korrekt, wenn der echte rAF-Loop parallel tickt: ein geschlossenes Gate
erhoeht den Zaehler nie, und ein EINMAL gesetztes Dirty-Flag wird von genau
EINEM Tick konsumiert (egal von wem).
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

_app = QApplication.instance() or QApplication([])

_HTML_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "src", "ui", "visualizer", "stage_scene.html"))

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05

# Signal-Liste 1:1 aus visualizer_window.py::VisualizerBridge (gleicher Mock
# wie in test_viz13c1_topdown_polish.py / test_viz13c_updatedmx_registry.py).
_SIGNAL_SPECS = [
    ("fixtureAdded", (str,)),
    ("fixtureRemoved", (int,)),
    ("dmxBatch", (str,)),
    ("allFixtures", (str,)),
    ("settingsChanged", (str,)),
    ("viewModeChanged", (str,)),
    ("editModeChanged", (str,)),
    ("stageLoaded", (str,)),
    ("addStageObject", (str,)),
    ("removeStageObject", (str,)),
    ("selectStageObject", (str,)),
    ("applyFixtureTransform", (str,)),
    ("alignSelected", (str,)),
    ("distributeSelected", (str,)),
    ("cameraReset", ()),
    ("brightnessSignal", (float,)),
    ("brightnessAutoSignal", ()),
    ("updateStageObject", (str,)),
    ("resizeModeSignal", (bool,)),
    ("pixelRatioSignal", (float,)),
]


def _make_mock_bridge_class():
    attrs = {}
    for name, arg_types in _SIGNAL_SPECS:
        attrs[name] = Signal(*arg_types)

    @Slot()
    def requestFixtures(self):
        self._request_fixtures_calls = getattr(self, "_request_fixtures_calls", 0) + 1

    attrs["requestFixtures"] = requestFixtures
    attrs["requestFullResync"] = Signal()

    return type("MockVisualizerBridge", (QObject,), attrs)


_MockVisualizerBridge = _make_mock_bridge_class()


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


# Mini-Rig: 1 PAR + 1 Moving Head reichen fuer alle Faelle.
_FIXTURES_PAYLOAD = json.dumps([
    {"fid": 11, "type": "par", "x": 0, "y": 2, "z": 0,
     "r": 0, "g": 0, "b": 0, "intensity": 0},
    {"fid": 14, "type": "moving_head",
     "x": 4, "y": 2, "z": 0, "r": 0, "g": 0, "b": 0, "intensity": 0},
])


class OnDemandRenderingTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(_HTML_PATH), f"stage_scene.html fehlt: {_HTML_PATH}")
        self._view = QWebEngineView()
        try:
            profile = self._view.page().profile()
            profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
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
        try:
            self._view.deleteLater()
        except Exception:
            pass
        _pump(0.2)

    # ── Harness (identisch zum 3c-1-Muster) ───────────────────────────────────
    def _load_and_wait(self):
        self._loaded_ok.clear()
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}")
        self._view.load(url)
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded_ok and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded_ok, "loadFinished nie ausgeloest (Timeout)")
        self.assertTrue(self._loaded_ok[-1], "loadFinished(ok=False)")
        self.assertTrue(self._poll_until_true("!!window.__lightosAppReady"))

    def _eval(self, js_expr):
        box = []
        self._view.page().runJavaScript(js_expr, lambda result: box.append(result))
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
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
        self.fail(f"Timeout beim Warten auf truthy '{js_expr}' (letzter Wert: {last!r})")

    def _emit_until_true(self, emit_fn, js_expr, timeout_s=_POLL_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            emit_fn()
            last = self._eval(js_expr)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout nach wiederholtem Emit fuer '{js_expr}' (letzter Wert: {last!r})")

    def _add_test_fixtures(self):
        self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(_FIXTURES_PAYLOAD),
            "typeof window.__lightos.fixtures['14'] === 'object'", timeout_s=8.0)

    # ── On-Demand-Helfer ───────────────────────────────────────────────────────
    def _stats(self):
        return json.loads(self._eval("JSON.stringify(window.__lightos.renderStats())"))

    def _tick(self):
        """Einen Loop-Tick deterministisch ausfuehren (rAF-unabhaengig)."""
        self._eval("window.__lightos.__renderTick(); true")

    def _settle(self, max_rounds=25):
        """Tickt, bis das Gate zu ist und der Zaehler sich nicht mehr bewegt
        (konsumiert Init-/Setup-Dirty aus Load, addFixture, Bridge-Pushes)."""
        last_count = None
        for _ in range(max_rounds):
            self._tick()
            s = self._stats()
            if (not s["dirty"]) and (not s["live"]) and s["count"] == last_count:
                return s
            last_count = s["count"]
        self.fail(f"Render-Loop stabilisiert nicht (letzter Stand: {self._stats()})")

    # ── 1) Idle rendert nicht ─────────────────────────────────────────────────
    def test_idle_does_not_render(self):
        self._load_and_wait()
        self._add_test_fixtures()
        s0 = self._settle()
        for _ in range(3):
            self._tick()
        s1 = self._stats()
        self.assertEqual(s1["count"], s0["count"],
                         "Idle-Ticks haben gerendert (Gate offen ohne Aenderung)")
        self.assertFalse(s1["dirty"], "Dirty-Flag im Idle gesetzt")
        self.assertFalse(s1["live"], "Live-Animation im Idle aktiv")

    # ── 2) dmxBatch -> Render, danach wieder Idle ─────────────────────────────
    def test_dmx_batch_triggers_render_then_idle(self):
        self._load_and_wait()
        self._add_test_fixtures()
        s0 = self._settle()
        batch = json.dumps([{"fid": 11, "r": 255, "g": 0, "b": 0, "intensity": 255}])
        self._emit_until_true(
            lambda: self._bridge_obj.dmxBatch.emit(batch),
            "window.__lightos.fixtures['11'].beam.material.color.getHex() === 0xff0000",
            timeout_s=8.0)
        st = self._stats()
        self.assertTrue(st["dirty"] or st["count"] > s0["count"],
                        "dmxBatch hat kein requestRender ausgeloest")
        self._tick()
        s1 = self._stats()
        self.assertGreater(s1["count"], s0["count"], "kein Render nach dmxBatch")
        self.assertFalse(s1["dirty"], "Dirty-Flag nach Render nicht geloescht")
        # Danach wieder Idle: weitere Ticks rendern nicht.
        base = s1["count"]
        for _ in range(3):
            self._tick()
        self.assertEqual(self._stats()["count"], base,
                         "Loop rendert nach dmxBatch-Konsum weiter (kein Idle)")

    # ── 3) Kamera-Aenderung -> genau ein Render ───────────────────────────────
    def test_camera_change_triggers_exactly_one_render(self):
        self._load_and_wait()
        self._add_test_fixtures()
        s0 = self._settle()
        # JS->JS (umgeht die Post-Load-Signal-Drossel): Preset setzt theta/phi
        # -> updateCamera() -> requestRender(). Ein EINZELNES Dirty-Flag wird
        # von genau EINEM Tick konsumiert — egal ob unserem oder einem echten
        # rAF-Tick -> Zaehler steigt um GENAU 1.
        self._eval("window.__lightos.setCameraPreset('top'); true")
        self._tick()
        s1 = self._stats()
        self.assertEqual(s1["count"], s0["count"] + 1,
                         "Kamera-Preset ergab nicht genau EINEN Render")
        self.assertFalse(s1["dirty"])

    # ── 4) Coalescing: N x requestRender = 1 Render ───────────────────────────
    def test_request_render_coalesces(self):
        self._load_and_wait()
        s0 = self._settle()
        self._eval("for (let i = 0; i < 7; i++) window.__lightos.requestRender(); true")
        self._tick()
        s1 = self._stats()
        self.assertEqual(s1["count"], s0["count"] + 1,
                         "7x requestRender ergab nicht genau EINEN Render (Coalescing)")
        self._tick()
        self.assertEqual(self._stats()["count"], s0["count"] + 1,
                         "Folge-Tick hat ohne neues Dirty gerendert")

    # ── 5) Stage-Selektion (Puls) haelt den Loop live, Deselektion -> Idle ────
    def test_stage_selection_pulse_keeps_rendering(self):
        self._load_and_wait()
        sid = self._eval("window.__lightos.addStageObject('platform')")
        self.assertTrue(sid, "addStageObject('platform') lieferte keine ID")
        self._settle()
        # Selektieren (Signal, wiederholt bis zugestellt): Probe kippt auf live.
        self._emit_until_true(
            lambda: self._bridge_obj.selectStageObject.emit(sid),
            "window.__lightos.renderStats().live === true", timeout_s=8.0)
        c0 = self._stats()["count"]
        for _ in range(3):
            self._tick()
        s1 = self._stats()
        self.assertGreaterEqual(s1["count"], c0 + 3,
                                "Puls-Selektion rendert nicht jeden Tick")
        # Puls mutiert wirklich (Emissive != 0 am selektierten Element).
        em = json.loads(self._eval(f"""
            (function() {{
                const so = window.__lightos.stageObjects['{sid}'];
                let e = null;
                so.mesh.traverse(c => {{
                    if (!e && c.isMesh && c.material && c.material.emissive) e = c.material.emissive;
                }});
                if (!e && so.mesh.isMesh && so.mesh.material) e = so.mesh.material.emissive;
                return JSON.stringify(e ? {{ r: e.r, g: e.g, b: e.b }} : null);
            }})()
        """))
        self.assertIsNotNone(em, "kein Emissive-Material am Stage-Element")
        self.assertGreater(em["r"], 0.0, "Puls-Emissive nicht angewendet")
        # Deselektieren -> live false -> nach Konsum wieder Idle.
        self._emit_until_true(
            lambda: self._bridge_obj.selectStageObject.emit(""),
            "window.__lightos.renderStats().live === false", timeout_s=8.0)
        s2 = self._settle()
        for _ in range(3):
            self._tick()
        self.assertEqual(self._stats()["count"], s2["count"],
                         "Loop rendert nach Deselektion weiter (kein Idle)")


if __name__ == "__main__":
    unittest.main()
