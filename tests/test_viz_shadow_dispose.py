"""A3D-07 — GPU-Shadow-Map-Leak beim Fixture-Loeschen.

``removeFixture`` (fixtures.js) entfernt ein Fixture via ``f.group.traverse(disposeObj)``.
Der Per-Fixture-``SpotLight`` haengt als Kind an ``root`` und wird mit-traversiert, aber
``disposeObj`` (grid_floor.js) gab bislang NUR geometry+material frei, NICHT
``spot.shadow`` (WebGLRenderTarget) -> die Shadow-Map leckte pro Show-Reload (waechst
bis Context-Loss auf schwachen GPUs, z. B. Adreno-Surface).

Fix: ``disposeObj`` gibt zusaetzlich ``light.shadow`` frei. Da ``disposeObj`` genau
ueber den ``f.group.traverse``-Pfad auf den SpotLight angewandt wird, deckt das den
Leak ab (und etwaige Pro-Kopf-Lichter). Getestet ueber den deterministischen Seam
``window.__lightos.disposeObj`` (offscreen drosselt Post-Load-Signale — direkter Aufruf
statt Fixture-Add/Remove ueber die Bridge).
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
from PySide6.QtCore import QObject, QUrl, Slot

_app = QApplication.instance() or QApplication([])

_HTML_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "src", "ui", "visualizer", "stage_scene.html"))

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 12.0
_POLL_INTERVAL_S = 0.05


class _MiniBridge(QObject):
    @Slot(result=str)
    def pollControl(self):
        return "{}"


class ShadowDisposeJsTest(unittest.TestCase):
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
        self._bridge = _MiniBridge()
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)
        self._loaded_ok = []
        self._view.loadFinished.connect(self._loaded_ok.append)
        self._load_and_wait()
        self._poll_until_true("window.__lightosAppReady === true")

    def tearDown(self):
        try:
            self._view.deleteLater()
        except Exception:
            pass
        self._pump(0.2)

    def _pump(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)

    def _load_and_wait(self):
        self._loaded_ok.clear()
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}")
        self._view.load(url)
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded_ok and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded_ok and self._loaded_ok[-1], "stage_scene.html laden fehlgeschlagen")

    def _eval(self, js_expr):
        box = []
        self._view.page().runJavaScript(js_expr, lambda r: box.append(r))
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

    def test_disposeobj_disposes_light_shadow(self):
        raw = self._eval(
            "(function(){"
            "  var calls = 0;"
            "  var light = { isLight: true, shadow: { dispose: function(){ calls++; } } };"
            "  window.__lightos.disposeObj(light);"
            "  return JSON.stringify({ calls: calls });"
            "})()"
        )
        self.assertTrue(raw, "JS lieferte kein Ergebnis")
        self.assertEqual(json.loads(raw)["calls"], 1,
                         "disposeObj hat light.shadow.dispose() nicht (genau einmal) aufgerufen")

    def test_disposeobj_still_disposes_geometry_and_material(self):
        # Regression: der neue Light-Zweig darf die normale geometry/material-Freigabe
        # (Nicht-Lichter) nicht beeintraechtigen.
        raw = self._eval(
            "(function(){"
            "  var g = 0, m = 0;"
            "  var mesh = { geometry: { dispose: function(){ g++; } },"
            "               material: { dispose: function(){ m++; } } };"
            "  window.__lightos.disposeObj(mesh);"
            "  return JSON.stringify({ g: g, m: m });"
            "})()"
        )
        r = json.loads(raw)
        self.assertEqual(r["g"], 1, "geometry.dispose nicht aufgerufen")
        self.assertEqual(r["m"], 1, "material.dispose nicht aufgerufen")

    def test_disposeobj_light_without_shadow_does_not_throw(self):
        raw = self._eval(
            "(function(){"
            "  try {"
            "    window.__lightos.disposeObj({ isLight: true });"        # kein shadow
            "    window.__lightos.disposeObj({ isLight: true, shadow: null });"
            "    return JSON.stringify({ ok: true });"
            "  } catch (e) { return JSON.stringify({ ok: false, err: String(e) }); }"
            "})()"
        )
        r = json.loads(raw)
        self.assertTrue(r["ok"], f"disposeObj warf bei Light ohne Shadow: {r.get('err')}")


if __name__ == "__main__":
    unittest.main()
