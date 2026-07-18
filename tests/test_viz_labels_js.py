"""VIZ-LABELS (Davids Auftrag 2026-07-18) — JS-Gating-Test.

Belegt, dass der globale ``settings.showLabels``-Schalter das Fixture-Label-Gate
in ``scene_src/fixtures/labels.js`` tatsaechlich steuert — nicht nur, dass das
Feld existiert. Getestet ueber den deterministischen Test-Seam
``window.__lightos.updateLabelZoomVisibility`` (offscreen drosselt Post-Load-
Signale, daher direkter Aufruf statt push — s. reference_qwebchannel_headless_
delivery). Eine synthetische Fixture wird EXAKT auf die Kameraposition gesetzt
(Distanz 0 < 28 m), sodass allein ``showLabels`` ueber die Sichtbarkeit
entscheidet.

Die Modul-Import-Integritaet von ``labels.js`` (neuer ``import { settings }``)
deckt zusaetzlich ``test_viz13_scene_modules_smoke.py`` ab (bei kaputtem Import
wuerde ``__lightosAppReady`` nie true).
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
    """Minimal-Bridge: ``tryChannel()`` in bridge.js ist vollstaendig defensiv
    (``if (bridge.X)`` pro Signal), daher reicht der Poll-Slot, damit die Page
    ohne Fehler bis ``__lightosAppReady`` durchlaeuft."""
    @Slot(result=str)
    def pollControl(self):
        return "{}"


class LabelGateJsTest(unittest.TestCase):
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
        self.assertTrue(self._loaded_ok, "loadFinished nie ausgeloest (Timeout)")
        self.assertTrue(self._loaded_ok[-1], "stage_scene.html konnte nicht geladen werden")

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

    def test_default_show_labels_true(self):
        self._load_and_wait()
        self._poll_until_true("window.__lightosAppReady === true")
        self.assertTrue(self._eval("window.__lightos.settings.showLabels === true"),
                        "showLabels-Default ist nicht true")

    def test_gate_honors_show_labels(self):
        self._load_and_wait()
        self._poll_until_true("window.__lightosAppReady === true")
        # Kamera muss initialisiert sein (cameras.js befuellt view.activeCam).
        self._poll_until_true("!!(window.__lightos && window.__lightos.view && window.__lightos.view.activeCam)")
        # Rueckgabe als JSON-String (runJavaScript serialisiert ein rohes
        # JS-Objekt mit Bool-Werten unzuverlaessig -> leerer QVariant).
        raw = self._eval(
            "(function(){"
            "  var L = window.__lightos;"
            "  var cam = L.view.activeCam;"
            "  var p = cam.position.clone();"          # synthetische Fixture AN der Kamera -> Distanz 0
            "  var f = { group: { position: p }, label: { visible: true } };"
            "  var fx = { 999999: f };"
            "  L.settings.showLabels = false;"
            "  L.updateLabelZoomVisibility(fx, cam, '3D');"
            "  var off = f.label.visible;"
            "  L.settings.showLabels = true;"
            "  L.updateLabelZoomVisibility(fx, cam, '3D');"
            "  var on = f.label.visible;"
            "  L.updateLabelZoomVisibility(fx, cam, '2D');"   # 2D zeigt NIE Labels
            "  var in2d = f.label.visible;"
            "  L.settings.showLabels = true;"                 # sauberen Zustand hinterlassen
            "  return JSON.stringify({ off: off, on: on, in2d: in2d });"
            "})()"
        )
        self.assertTrue(raw, "JS-Gate lieferte kein Ergebnis")
        result = json.loads(raw)
        self.assertFalse(result["off"], "showLabels=false blendet das Label NICHT aus")
        self.assertTrue(result["on"], "showLabels=true zeigt das Label NICHT (bei Distanz 0)")
        self.assertFalse(result["in2d"], "Label ist im 2D-Modus sichtbar (darf es nicht)")


if __name__ == "__main__":
    unittest.main()
