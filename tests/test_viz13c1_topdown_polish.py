"""VIZ-13 3c-1: Ortho-2D-Polish — Regressionstests fuer den symbolischen
2D-Top-Down-Plan (Davids Reframe 2026-07-04: Icons BEHALTEN + verbessern).

Prueft die vier Polish-Punkte gegen die ECHTE ``stage_scene.html`` (gleicher
Harness wie ``test_viz13_scene_modules_smoke.py``: offscreen QWebEngineView +
Mock-Bridge + runJavaScript-Polling; Signale werden wiederholt emittiert, weil
der QWebChannel-Connect asynchron aufbaut — siehe dortige Erklaerung):

  1) KONTRAST: jedes Icon traegt eine permanente Umriss-Linie
     (``userData.isIconOutline``); unbelichtete Icons fuellen mit dem
     helleren ``ICON_UNLIT_FILL`` (vorher 0x3a3a4a — auf dem 0x282828-Boden
     praktisch unsichtbar).
  2) TYP-GLYPHEN: ``par_bar``/``mover_bar`` haben eigene Icons mit N
     Einzel-Zellen (vorher Default-Kreis); PAR traegt einen Linsen-Ring
     (2. Umriss); Spider hat 2 Bar-Zellen. Zellen werden ueber dmxBatch
     PRO KOPF gefaerbt (zentrales tintTopDownIcon).
  3) FOOTER-HINT: #controls wechselt mit setViewMode zwischen 3D- und
     2D-Gestentext (vorher stand dauerhaft der 3D-Text da).
  4) GRUNDRISS: Buehnenobjekte bekommen im 2D einen Footprint-Umriss in der
     Typ-Farbe (STAGE_2D_COLORS.edge), der im 3D wieder verschwindet und vom
     Raycast ausgenommen ist.
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

# Muss den JS-Konstanten in scene_src/fixtures/topdown_icons.js entsprechen.
ICON_UNLIT_FILL = 0x4A4E5E
# STAGE_2D_COLORS.platform.edge in scene_src/stage/stage_objects.js.
PLATFORM_EDGE = 0xC7906A

# Signal-Liste 1:1 aus visualizer_window.py::VisualizerBridge (bridge.js
# guardet jeden Connect mit ``if (bridge.X)`` — die volle Liste haelt den
# Mock identisch zur Produktiv-Bridge).
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


# Test-Rig: 1 PAR, 1 PAR-Bar (4 Zellen), 1 Mover-Bar (4 Zellen), 1 MH, 1 Spider.
_FIXTURES_PAYLOAD = json.dumps([
    {"fid": 11, "type": "par", "x": 0, "y": 2, "z": 0,
     "r": 0, "g": 0, "b": 0, "intensity": 0},
    {"fid": 12, "type": "par", "model": "par_bar", "nHeads": 4, "rotY": 90,
     "x": 2, "y": 2, "z": 0, "r": 0, "g": 0, "b": 0, "intensity": 0},
    {"fid": 13, "type": "moving_head", "model": "mover_bar", "nHeads": 4,
     "x": 4, "y": 2, "z": 0, "r": 0, "g": 0, "b": 0, "intensity": 0},
    {"fid": 14, "type": "moving_head",
     "x": 6, "y": 2, "z": 0, "r": 0, "g": 0, "b": 0, "intensity": 0},
    {"fid": 15, "type": "moving_head", "model": "spider",
     "x": 8, "y": 2, "z": 0, "r": 0, "g": 0, "b": 0, "intensity": 0},
])


class TopDownPolishTest(unittest.TestCase):
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
            "typeof window.__lightos.fixtures['15'] === 'object'", timeout_s=8.0)

    # ── 1+2) Kontrast + Typ-Glyphen ────────────────────────────────────────────
    def test_icons_outline_cells_and_unlit_fill(self):
        self._load_and_wait()
        self._add_test_fixtures()
        raw = self._eval("""
            (function() {
                const F = window.__lightos.fixtures;
                function info(fid) {
                    const f = F[fid];
                    if (!f || !f.icon) return null;
                    let outlines = 0, opaqueLines = 0;
                    f.icon.traverse(o => {
                        if (o.userData && o.userData.isIconOutline) outlines++;
                        if (o.isLine && o.material && !o.material.transparent) opaqueLines++;
                    });
                    const cells = f.icon.userData.cells ? f.icon.userData.cells.length : 0;
                    const bodyHex = f.icon.userData.body.material.color.getHex();
                    const ring = f.icon.userData.ring;
                    const ringNoRaycast = !!ring
                        && String(ring.raycast).replace(/\\s/g, '').endsWith('{}');
                    return { outlines: outlines, cells: cells, bodyHex: bodyHex,
                             hasRing: !!ring, opaqueLines: opaqueLines,
                             ringNoRaycast: ringNoRaycast,
                             iconYaw: f.icon.rotation.y };
                }
                return JSON.stringify({
                    par: info('11'), parBar: info('12'), moverBar: info('13'),
                    mh: info('14'), spider: info('15'),
                });
            })()
        """)
        d = json.loads(raw)
        for key in ("par", "parBar", "moverBar", "mh", "spider"):
            self.assertIsNotNone(d[key], f"Icon fuer {key} fehlt")
            self.assertGreaterEqual(d[key]["outlines"], 1, f"{key}: kein permanenter Umriss")
            self.assertTrue(d[key]["hasRing"], f"{key}: Selektionsring fehlt")
            # Glyphen im Transparent-Pass: opake Linien wuerden vom
            # transparenten Body-Fill uebermalt (Review-Finding 3c-1).
            self.assertEqual(d[key]["opaqueLines"], 0,
                             f"{key}: opake Glyph-Linien (werden vom Fill uebermalt)")
            # Unsichtbarer Ring darf keine Picks stehlen.
            self.assertTrue(d[key]["ringNoRaycast"],
                            f"{key}: Selektionsring ist nicht vom Raycast ausgenommen")
        # Yaw-Init: fid 12 kommt mit rotY=90 -> Icon liegt sofort richtig
        # (vorher erst nach der ersten Rotations-Geste).
        import math
        self.assertAlmostEqual(d["parBar"]["iconYaw"], math.pi / 2, places=3)
        # PAR: Aussen-Umriss + Linsen-Ring = 2 Umrisse (Glyph-Unterscheidung
        # vom nackten Default-Kreis).
        self.assertGreaterEqual(d["par"]["outlines"], 2, "PAR-Linsen-Ring fehlt")
        # Bar-Icons: N Einzel-Zellen (FM-6-Paritaet); Spider: 2 Bar-Zellen.
        self.assertEqual(d["parBar"]["cells"], 4)
        self.assertEqual(d["moverBar"]["cells"], 4)
        self.assertEqual(d["spider"]["cells"], 2)
        # Unbelichtet (intensity 0): heller Unlit-Fill statt 0x3a3a4a.
        self.assertEqual(d["par"]["bodyHex"], ICON_UNLIT_FILL)
        self.assertEqual(d["mh"]["bodyHex"], ICON_UNLIT_FILL)

    def test_dmx_tints_cells_per_head_and_body(self):
        self._load_and_wait()
        self._add_test_fixtures()
        # PAR-Bar: 4 Koepfe rot/gruen/blau/weiss bei vollem Dimmer.
        batch_on = json.dumps([{
            "fid": 12, "r": 0, "g": 0, "b": 0, "intensity": 255,
            "heads": [
                {"r": 255, "g": 0, "b": 0}, {"r": 0, "g": 255, "b": 0},
                {"r": 0, "g": 0, "b": 255}, {"r": 255, "g": 255, "b": 255},
            ],
        }])
        self._emit_until_true(
            lambda: self._bridge_obj.dmxBatch.emit(batch_on),
            "window.__lightos.fixtures['12'].icon.userData.cells[0]"
            ".material.color.getHex() === 0xff0000", timeout_s=8.0)
        raw = self._eval("""
            (function() {
                const cells = window.__lightos.fixtures['12'].icon.userData.cells;
                return JSON.stringify({
                    hexes: cells.map(c => c.material.color.getHex()),
                    op0: cells[0].material.opacity,
                });
            })()
        """)
        d = json.loads(raw)
        self.assertEqual(d["hexes"], [0xFF0000, 0x00FF00, 0x0000FF, 0xFFFFFF])
        self.assertAlmostEqual(d["op0"], 1.0, places=2)

        # Dimmer zu -> alle Zellen zurueck auf den Unlit-Fill.
        batch_off = json.dumps([{
            "fid": 12, "r": 0, "g": 0, "b": 0, "intensity": 0,
            "heads": [{"r": 255, "g": 0, "b": 0}],
        }])
        self._emit_until_true(
            lambda: self._bridge_obj.dmxBatch.emit(batch_off),
            f"window.__lightos.fixtures['12'].icon.userData.cells[0]"
            f".material.color.getHex() === {ICON_UNLIT_FILL}", timeout_s=8.0)

        # Single-Body (PAR): Ausgabefarbe an, Unlit-Fill aus.
        par_on = json.dumps([{"fid": 11, "r": 255, "g": 0, "b": 0, "intensity": 255}])
        self._emit_until_true(
            lambda: self._bridge_obj.dmxBatch.emit(par_on),
            "window.__lightos.fixtures['11'].icon.userData.body"
            ".material.color.getHex() === 0xff0000", timeout_s=8.0)
        par_off = json.dumps([{"fid": 11, "r": 255, "g": 0, "b": 0, "intensity": 0}])
        self._emit_until_true(
            lambda: self._bridge_obj.dmxBatch.emit(par_off),
            f"window.__lightos.fixtures['11'].icon.userData.body"
            f".material.color.getHex() === {ICON_UNLIT_FILL}", timeout_s=8.0)

    # ── 3) Footer-Hint ─────────────────────────────────────────────────────────
    def test_footer_hint_follows_view_mode(self):
        self._load_and_wait()
        initial = self._eval("document.getElementById('controls').textContent")
        self.assertTrue(initial.strip().startswith("3D:"),
                        f"Initialer Hint ist nicht der 3D-Text: {initial!r}")
        self._eval("window.__lightos.setViewMode('2D'); true")
        hint2d = self._poll_until_true(
            "document.getElementById('controls').textContent.trim().startsWith('2D-Plan:') "
            "&& document.getElementById('controls').textContent")
        self.assertIn("Zoom", hint2d)
        self._eval("window.__lightos.setViewMode('3D'); true")
        self._poll_until_true(
            "document.getElementById('controls').textContent.trim().startsWith('3D:')")

    # ── 4) Grundriss-Umriss der Buehnenobjekte ─────────────────────────────────
    def test_stage_footprint_outline_in_2d(self):
        self._load_and_wait()
        sid = self._eval("window.__lightos.addStageObject('platform')")
        self.assertTrue(sid, "addStageObject('platform') lieferte keine ID")
        # 3D (Default): kein Umriss.
        self.assertTrue(self._eval(
            f"!window.__lightos.stageObjects['{sid}']._outline2d"))
        # 2D: Umriss existiert, Typ-Farbe, renderOrder 2, Kind von so.mesh,
        # vom Raycast ausgenommen.
        self._eval("window.__lightos.setViewMode('2D'); true")
        self._poll_until_true(f"!!window.__lightos.stageObjects['{sid}']._outline2d")
        raw = self._eval(f"""
            (function() {{
                const so = window.__lightos.stageObjects['{sid}'];
                const o = so._outline2d;
                return JSON.stringify({{
                    colorHex: o.material.color.getHex(),
                    renderOrder: o.renderOrder,
                    parentOk: o.parent === so.mesh,
                    depthTest: o.material.depthTest,
                    raycastNoop: o.raycast.length === 0 && String(o.raycast).indexOf('{{}}') >= 0,
                }});
            }})()
        """)
        d = json.loads(raw)
        self.assertEqual(d["colorHex"], PLATFORM_EDGE)
        self.assertEqual(d["renderOrder"], 2)
        self.assertTrue(d["parentOk"], "Umriss ist kein Kind von so.mesh")
        self.assertFalse(d["depthTest"])
        self.assertTrue(d["raycastNoop"], "Umriss ist nicht vom Raycast ausgenommen")
        # Zurueck in 3D: Umriss wird entfernt.
        self._eval("window.__lightos.setViewMode('3D'); true")
        self._poll_until_true(f"!window.__lightos.stageObjects['{sid}']._outline2d")
        # Aufraeumen crasht nicht (removeStageObject disposed den Umriss mit).
        self._eval("window.__lightos.setViewMode('2D'); true")
        self._poll_until_true(f"!!window.__lightos.stageObjects['{sid}']._outline2d")
        self._eval("window.__lightos.clearStageObjects(); true")
        self.assertTrue(self._eval(
            "Object.keys(window.__lightos.stageObjects).length === 0"))


if __name__ == "__main__":
    unittest.main()
