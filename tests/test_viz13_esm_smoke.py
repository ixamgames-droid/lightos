"""VIZ-13 Schritt 3a-1/3a-2: ESM-Machbarkeits-Beleg (Build-Strategie
empirisch fixieren, siehe docs/VIZ13_JS_NEUAUFBAU_DESIGN.md Abschnitt (b))
+ three-Wrapper-Modul-Beleg (Abschnitt (a), ``three/three.js``).

Laedt die TEST-ONLY Probe-Page (``stage_scene_esm_probe.html``) in einer
ECHTEN ``QWebEngineView`` (offscreen) und prueft:

  1) ``window.__lightosEsmOk === true`` — das importierte ES-Modul
     (``scene_src/app.js`` -> ``scene_src/probe_util.js``) wurde ausgefuehrt.
  2) ``window.__lightosEsmProbe.hasThree`` / ``.hasVector3`` — das Modul sah
     das von ``three_local.js`` (klassisches Script, laeuft VOR dem Modul)
     gesetzte globale ``window.THREE`` (Belegt Weg A: globales THREE +
     UMD-Controls statt three_local.js->ESM-Migration).
  3) ``typeof qt.webChannelTransport !== 'undefined'`` — die WebChannel-
     Bruecke ist zum Zeitpunkt der Pruefung vorhanden. ``type=module``-
     Scripts sind implizit ``defer`` (laufen NACH allen klassischen
     Scripts inkl. ``qwebchannel.js``); das bestaetigt, dass ein
     ``tryChannel()``-artiges Poll-Muster (``setTimeout(fn, 200)``) im
     Bridge-Modul mit dieser Ladereihenfolge klarkommt.
  4) ``window.__lightosEsmProbe.wrapperSceneOk`` — ein Modul, das
     ``{ Scene }`` ueber den neuen Wrapper (``scene_src/three/three.js``)
     importiert, kann fehlerfrei ``new Scene()`` instanziieren und das
     Ergebnis ist eine echte ``window.THREE.Scene``-Instanz (3a-2).
  5) ``window.__lightosEsmProbe.state*Ok`` — das neue ``scene_src/state.js``
     (VIZ-13 3a-3) ist fehlerfrei importierbar, liefert die erwarteten leeren
     State-Objekte und der ``view``-Getter/Setter-Accessor (statt eines
     re-exportierten ``let`` - Design-Risiko 1) ist les- und schreibbar.

Bewusst OHNE Renderer-Instanziierung: WebGL ist im offscreen-Testlauf
(``QT_QPA_PLATFORM=offscreen``) nicht verfuegbar — ``probe_util.js`` fasst
nur den THREE-Namespace an bzw. instanziiert ein ``THREE.Scene`` (kein GL
noetig), niemals ``new THREE.WebGLRenderer(...)``.

Kein Python-Compile-Check haette einen Bruch der Lade-Konstellation
gefangen (Design-Dokument, Leitprinzip) — deshalb dieser dedizierte
Smoke-Test statt eines reinen Datei-Existenz-Checks.
"""
import json
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QObject, QUrl

_app = QApplication.instance() or QApplication([])

_PROBE_HTML = os.path.join(
    os.path.dirname(__file__), "..", "src", "ui", "visualizer",
    "stage_scene_esm_probe.html")
_PROBE_HTML = os.path.normpath(_PROBE_HTML)

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05


def _pump(seconds):
    """Verarbeitet Qt-Events fuer ``seconds`` Sekunden (Wanduhr), damit der
    offscreen-QWebEngineView-Prozess (separater Chromium-Renderprozess)
    laden/das Modul ausfuehren kann."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


class EsmProbeSmokeTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(
            os.path.isfile(_PROBE_HTML),
            f"Probe-HTML fehlt: {_PROBE_HTML}")
        self._view = QWebEngineView()
        s = self._view.settings()
        # Identische Settings wie die Produktiv-Page (visualizer_view.py /
        # visualizer_window.py load_stage_html): file://-Import von
        # scene_src/*.js braucht LocalContentCanAccessFileUrls.
        s.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        # qt.webChannelTransport existiert im JS erst, NACHDEM ein
        # QWebChannel auf der Page registriert wurde (page().setWebChannel) -
        # identisch zur Produktiv-Konstellation (Visualizer3DView._setup_channel
        # / VisualizerWindow: channel.registerObject + setWebChannel VOR dem
        # ersten load()). Ohne das waere Pruefung 3) unten sinnlos (immer
        # 'undefined', unabhaengig vom Timing-Beleg).
        self._channel_obj = QObject()
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._channel_obj)
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
        url = QUrl.fromLocalFile(_PROBE_HTML)
        self._view.load(url)
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded_ok and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded_ok, "loadFinished nie ausgeloest (Timeout)")
        self.assertTrue(
            self._loaded_ok[-1],
            "loadFinished(ok=False) - Probe-Page konnte nicht geladen werden")

    def _eval(self, js_expr):
        """Synchron per Poll: ``runJavaScript`` ist async (Callback), also
        Ergebnis in einer Box einsammeln und auf den Callback warten."""
        box = []
        self._view.page().runJavaScript(js_expr, lambda result: box.append(result))
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(box, f"runJavaScript-Callback nie ausgeloest fuer: {js_expr}")
        return box[0]

    def _poll_until_true(self, js_expr, timeout_s=_POLL_TIMEOUT_S):
        """Pollt einen JS-Ausdruck bis er truthy wird (das Modul ist
        implizit deferred - laeuft ggf. erst nach ein paar Event-Loop-
        Durchlaeufen NACH loadFinished)."""
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            last = self._eval(js_expr)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout beim Warten auf truthy '{js_expr}' (letzter Wert: {last!r})")

    def test_esm_module_executes_and_sees_three_and_webchannel(self):
        self._load_and_wait()

        # 1) Modul lief (window.__lightosEsmOk gesetzt von app.js).
        esm_ok = self._poll_until_true("!!window.__lightosEsmOk")
        self.assertTrue(esm_ok)

        # 2) Modul sah window.THREE (three_local.js lief vor dem Modul-Script).
        # Bewusst ueber JSON.stringify + json.loads statt direkter Objekt-
        # Rueckgabe: runJavaScript() liefert komplexe JS-Objekte ueber die
        # PySide6-Bruecke empirisch NICHT zuverlaessig als dict (beobachtet:
        # kommt als leerer String '' zurueck, obwohl das Objekt im Renderer
        # existiert) - der JSON-Stringify-Umweg ist der robuste Weg.
        probe_raw = self._eval("JSON.stringify(window.__lightosEsmProbe)")
        self.assertTrue(probe_raw, f"leere/undefined Probe: {probe_raw!r}")
        probe = json.loads(probe_raw)
        self.assertIsInstance(probe, dict, f"unerwartete Probe-Form: {probe_raw!r}")
        self.assertTrue(probe.get("hasThree"), f"THREE-Namespace fehlt: {probe!r}")
        self.assertTrue(probe.get("hasVector3"), f"THREE.Vector3 fehlt: {probe!r}")
        self.assertTrue(
            probe.get("wrapperSceneOk"),
            f"three-Wrapper-Modul: new Scene() ueber Scene-Import fehlgeschlagen: {probe!r}")
        self.assertTrue(probe.get("stateObjectsOk"), f"state.js Objekt-State fehlerhaft: {probe!r}")
        self.assertTrue(probe.get("stateViewModeOk"), f"state.js view.mode Getter/Setter fehlerhaft: {probe!r}")
        self.assertTrue(
            probe.get("stateViewSelectedFidsOk"),
            f"state.js view.selectedFids Getter/Setter fehlerhaft: {probe!r}")
        self.assertTrue(
            probe.get("stateViewSelectedStageIdOk"),
            f"state.js view.selectedStageId Getter/Setter fehlerhaft: {probe!r}")

        # 3) Kein Renderer wurde instanziiert (WebGL im offscreen-Lauf nicht
        #    verfuegbar) - nur Namespace-Zugriff, kein renderer/domElement.
        has_renderer_global = self._eval("typeof window.renderer !== 'undefined'")
        self.assertFalse(
            has_renderer_global,
            "Probe darf keinen Renderer instanziieren (WebGL fehlt offscreen)")

        # 4) Bridge-Timing-Beleg: qt.webChannelTransport existiert bereits
        #    (qwebchannel.js lief als erstes klassisches Script, lange vor
        #    dem deferred Modul) - ein tryChannel()-artiges Poll-Muster im
        #    spaeteren Bridge-Modul findet die Transport-Bruecke vor.
        has_qt_transport = self._eval(
            "typeof qt !== 'undefined' && typeof qt.webChannelTransport !== 'undefined'")
        self.assertTrue(
            has_qt_transport,
            "qt.webChannelTransport fehlt - Bridge-Timing-Annahme verletzt")


if __name__ == "__main__":
    unittest.main()
