"""VIZ-14 (Empty-State): eine leere Bühne soll wie ein Anfang aussehen, nicht
wie ein Fehler — End-to-End in einer ECHTEN QWebEngine.

Plan-Item 4 nennt neben dem Labels-Overlay ausdruecklich den
„Empty-State-Hinweis". Bisher zeigte der Visualizer bei einer neuen Show nur
Grid und Boden: das ist der NORMALZUSTAND, sieht aber aus wie „da fehlt was",
und nirgends steht, was der naechste Schritt waere.

Belegt: (1) der Hinweis ist bei leerer Szene da, (2) das erste GERAET blendet
ihn aus, (3) das erste BUEHNENOBJEKT ebenso (beides zaehlt als Inhalt),
(4) Entfernen bringt ihn zurueck, (5) er ist ``pointer-events: none`` —
sonst schluckte ausgerechnet der Hinweis den Klick, mit dem der Nutzer
anfangen will, (6) er weckt den On-Demand-Render-Loop NICHT (reines DOM).

Eigene Isolate-Datei (wie die anderen VIZ-14-Szenen-Tests): jede
QWebEngine-Ladung stresst den offscreen-Chromium.
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
    ("alignSelected", (str,)), ("distributeSelected", (str,)), ("cameraReset", ()),
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


class EmptyStateSceneTest(unittest.TestCase):
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
        destroy_webengine_view(self._view, _pump)   # XPLAT-09
        self._view = None

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
        self._poll_until_true("!!window.__lightosAppReady")
        self._warte_auf_bridge()

    def _warte_auf_bridge(self, timeout_s=_POLL_TIMEOUT_S):
        """Warten, BIS die JS-Seite den WebChannel verdrahtet hat.

        ``tryChannel()`` laeuft asynchron (setTimeout, 200-ms-Retry) — ein
        ``emit`` davor verpufft ersatzlos, weil noch niemand connectet ist.
        Genau das machte diesen Test flaky (2 von 4 Laeufen rot, immer an der
        ersten Signal-Zustellung). Erkennungszeichen: die JS-Seite ruft beim
        Connect ``bridge.requestFixtures()`` — der Mock zaehlt das mit."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if getattr(self._bridge_obj, "_request_fixtures_calls", 0) > 0:
                return
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.fail("JS hat den WebChannel nicht verdrahtet (requestFixtures nie gerufen)")

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
        self.fail(f"Timeout beim Warten auf truthy '{js_expr}' (letzter: {last!r})")

    def _sichtbar(self):
        return self._eval(
            "(function(){var e=document.getElementById('empty-state');"
            " return !!e && !e.hidden;})()")

    def _stats(self):
        return json.loads(self._eval("JSON.stringify(window.__lightos.renderStats())"))

    def _settle(self, max_rounds=30):
        last = None
        for _ in range(max_rounds):
            self._eval("window.__lightos.__renderTick(); true")
            s = self._stats()
            if (not s["dirty"]) and (not s["live"]) and s["count"] == last:
                return s
            last = s["count"]
        self.fail(f"Render-Loop stabilisiert nicht: {self._stats()}")

    # ── Alle Checks in EINER Ladung: jede Vollladung kostet ~4 s ──────────────

    def test_empty_state_folgt_dem_inhalt(self):
        self._load_and_wait()

        # (1) leere Szene -> Hinweis da
        self.assertTrue(self._sichtbar(),
                        "leere Buehne ohne Hinweis sieht aus wie ein Fehler")
        self.assertEqual(self._eval(
            "getComputedStyle(document.getElementById('empty-state')).pointerEvents"),
            "none",
            "(5) der Hinweis darf den Klick nicht schlucken, mit dem der Nutzer "
            "gerade anfangen will")

        # (6) reines DOM: der Loop muss danach in Idle fallen duerfen
        s_ruhe = self._settle()
        self.assertFalse(s_ruhe["live"], "Empty-State haelt den Render-Loop wach")

        # (2) erstes GERAET blendet aus
        self._bridge_obj.fixtureAdded.emit(json.dumps({
            "fid": 1, "label": "P1", "type": "par", "model": "par", "nHeads": 0,
            "x": 0, "y": 3, "z": 0, "rotX": 0, "rotY": 0, "rotZ": 0,
        }))
        # ERST auf die Zustellung des Signals warten, DANN auf die Wirkung —
        # sonst misst der Test sein eigenes Timing statt des Verhaltens.
        self._poll_until_true("Object.keys(window.__lightos.fixtures).length > 0")
        self._poll_until_true(
            "(function(){var e=document.getElementById('empty-state');"
            " return !!e && e.hidden;})()")

        # (4) letztes Geraet weg -> Hinweis zurueck
        self._bridge_obj.fixtureRemoved.emit(1)
        self._poll_until_true("Object.keys(window.__lightos.fixtures).length === 0")
        self._poll_until_true(
            "(function(){var e=document.getElementById('empty-state');"
            " return !!e && !e.hidden;})()")

        # (3) auch ein BUEHNENOBJEKT zaehlt als Inhalt
        self._eval("window.__lightos.addStageObject('truss_h'); true")
        self._poll_until_true(
            "(function(){var e=document.getElementById('empty-state');"
            " return !!e && e.hidden;})()")

        # und wieder leeren
        self._eval("window.__lightos.clearStageObjects(); true")
        self._poll_until_true(
            "(function(){var e=document.getElementById('empty-state');"
            " return !!e && !e.hidden;})()")


if __name__ == "__main__":
    unittest.main()
