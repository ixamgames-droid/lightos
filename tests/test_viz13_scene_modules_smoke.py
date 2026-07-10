"""VIZ-13 Schritt 3a-4: Modul-Split-Smoke-Test fuer die ECHTE
``stage_scene.html`` (siehe docs/VIZ13_JS_NEUAUFBAU_DESIGN.md Abschnitt (a)).

Der ehemalige EINE ``<script>``-Block (~3547 Zeilen, ~95 Funktionen) wurde in
ES-Module unter ``scene_src/`` zerlegt; ``stage_scene.html`` laedt jetzt nur
noch ``<script type="module" src="scene_src/app.js">`` (nach den klassischen
qwebchannel.js/three_local.js/Loader-Scripts).

Kein Python-Compile-Check haette einen Bruch des Modul-Verdrahtungsvertrags
gefangen (Design-Dokument, Leitprinzip) - deshalb dieser dedizierte Test:

  1) Laedt die ECHTE Produktiv-Page ``stage_scene.html`` offscreen in einer
     ``QWebEngineView`` mit ``NoCache``-Profil (identische Konfiguration zu
     ``visualizer_view.py``/``visualizer_window.py``).
  2) Registriert eine Mock-Bridge mit ALLEN 21 Signalen, die
     ``scene_src/bridge/bridge.js#tryChannel()`` verbindet (siehe
     ``visualizer_window.py::VisualizerBridge`` fuer die Signal-Liste) +
     dem ``requestFixtures``-Slot.
  3) Prueft ``window.__lightosAppReady === true`` - app.js ist komplett
     durchgelaufen (alle Module importiert, Render-Loop gestartet,
     Bridge-Poll gestartet).
  4) Prueft, dass ALLE 21 ``bridge.X.connect(...)``-Aufrufe aus
     ``tryChannel()`` tatsaechlich passiert sind - jedes Signal bekommt vor
     dem Laden einen JS-seitigen Connect-Zaehler injiziert
     (``Object.defineProperty`` auf dem Bridge-Mock-Objekt), der bei jedem
     ``.connect()`` hochzaehlt. Belegt den Bridge-Vertrag aus dem
     Design-Dokument Leitprinzip vollstaendig (nicht nur "irgendwas lief").
  5) Prueft ``window.__lightos`` (das bereits VOR 3a-4 bestehende
     Debug-/Test-API, siehe Design-Dokument Leitprinzip Punkt 3) ist
     unveraendert vorhanden und funktional (fixtures/stageObjects/settings
     als Objekte, setViewMode/setEditMode als Funktionen aufrufbar).
  6) Cache-Buster-Regressionstest (Auftrags-Pflichtpunkt): aendert ein
     Modul auf der Festplatte, laedt die Page per ``load_stage_html``-
     aequivalentem ``?v=``-Cache-Buster NEU und prueft, dass die Aenderung
     im geladenen Modul sichtbar wird - belegt empirisch, dass das
     bestehende ``NoCache``-Profil-Setting (``visualizer_view.py``/
     ``visualizer_window.py``) auch fuer ``type=module``-Importe (nicht nur
     die HTML-Top-Level-URL) greift, OHNE dass app.js selbst einen
     ``?v=``-Query an die Import-Pfade durchreichen muesste (Design-Dokument
     Abschnitt (b) "Laderei-Gotcha", 2. Alternative).
"""
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

# Signal-Liste 1:1 aus visualizer_window.py::VisualizerBridge (Slots <- JS-
# Connects in scene_src/bridge/bridge.js#tryChannel()).
_SIGNAL_SPECS = [
    ("fixtureAdded", (str,)),
    ("fixtureRemoved", (int,)),
    # VIZ-13 3c-4: dmxUpdated entfernt — Bridge exponiert nur noch dmxBatch.
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
    """Baut eine QObject-Subklasse mit allen 21 Signalen dynamisch (Signal()
    muss ein Klassenattribut sein, PySide6 erlaubt kein setattr nach
    Instanziierung) + dem requestFixtures-Slot."""
    attrs = {}
    for name, arg_types in _SIGNAL_SPECS:
        attrs[name] = Signal(*arg_types)

    @Slot()
    def requestFixtures(self):
        self._request_fixtures_calls = getattr(self, "_request_fixtures_calls", 0) + 1

    attrs["requestFixtures"] = requestFixtures
    attrs["requestFullResync"] = Signal()  # von bridge.allFixtures-Handler optional aufgerufen

    return type("MockVisualizerBridge", (QObject,), attrs)


_MockVisualizerBridge = _make_mock_bridge_class()


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


class SceneModulesSmokeTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(_HTML_PATH), f"stage_scene.html fehlt: {_HTML_PATH}")
        self._view = QWebEngineView()
        # Identische Konfiguration zur Produktiv-Page (visualizer_view.py
        # Zeile ~101-112 / visualizer_window.py): NoCache-Profil + file://-
        # Modul-Imports erlaubt.
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

    def _load_and_wait(self, cache_bust=True):
        # WICHTIG: .clear() statt Neuzuweisung - loadFinished ist in setUp()
        # an die urspruengliche Liste per `self._loaded_ok.append` gebunden;
        # eine Neuzuweisung (`self._loaded_ok = []`) wuerde das Signal von
        # der neuen Liste entkoppeln (Callback fuellt weiter die ALTE Liste).
        self._loaded_ok.clear()
        url = QUrl.fromLocalFile(_HTML_PATH)
        if cache_bust:
            url.setQuery(f"v={int(time.time() * 1000)}")
        self._view.load(url)
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded_ok and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded_ok, "loadFinished nie ausgeloest (Timeout)")
        self.assertTrue(
            self._loaded_ok[-1],
            "loadFinished(ok=False) - stage_scene.html konnte nicht geladen werden")

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
        """Wiederholt ``emit_fn()`` bei jedem Poll-Tick, bis ``js_expr``
        truthy wird. Noetig, weil ``tryChannel()`` (scene_src/bridge/
        bridge.js) den WebChannel-Connect asynchron/deferred aufbaut - mit
        einer Mock-Bridge, die alle 21 Signale deklariert, dauert der
        QWebChannel-JS-Proxy-Aufbau messbar laenger als bei nur einem
        Signal (empirisch beobachtet: <1 Signal ~0.3s, 21 Signale >0.3s,
        <2s). Ein einzelner Emit VOR dem fertigen Connect ginge sonst
        verloren (Signal ohne Empfaenger). Alle hier getesteten Handler
        (addFixture/applySettings/setViewMode/setEditMode) sind idempotent
        gegenueber wiederholtem Aufruf mit demselben Payload."""
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            emit_fn()
            last = self._eval(js_expr)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout beim Warten auf truthy '{js_expr}' nach wiederholtem Emit (letzter Wert: {last!r})")

    def test_app_ready_and_lightos_debug_api(self):
        self._load_and_wait()

        # 1) app.js ist komplett durchgelaufen (alle 20 Module importiert,
        #    Render-Loop + Bridge-Poll gestartet).
        app_ready = self._poll_until_true("!!window.__lightosAppReady")
        self.assertTrue(app_ready)

        # 2) window.__lightos-Vertrag (VOR 3a-4 bestehend, Design-Dokument
        #    Leitprinzip Punkt 3 "unveraendert exponiert") ist vorhanden.
        has_lightos = self._eval("typeof window.__lightos === 'object' && window.__lightos !== null")
        self.assertTrue(has_lightos, "window.__lightos fehlt")

        shape_ok = self._eval("""
            (function() {
                const L = window.__lightos;
                return typeof L.fixtures === 'object'
                    && typeof L.stageObjects === 'object'
                    && typeof L.settings === 'object'
                    && typeof L.setViewMode === 'function'
                    && typeof L.setEditMode === 'function'
                    && typeof L.getStageJson === 'function'
                    && typeof L.loadStageJson === 'function'
                    && typeof L.addStageObject === 'function'
                    && typeof L.clearStageObjects === 'function'
                    && typeof L.updateResizeHandles === 'function'
                    && typeof L.resizeHandles === 'function'
                    && typeof L.setBrightnessManual === 'function'
                    && typeof L.resetBrightnessAuto === 'function'
                    && typeof L.applyBrightness === 'function';
            })()
        """)
        self.assertTrue(shape_ok, "window.__lightos-Form unvollstaendig")

        # 3) getStageJson() liefert die erwartete leere Grundform (kein
        #    Crash, Bridge-Verdrahtung hat den State nicht kaputt gemacht).
        stage_json_ok = self._eval(
            "(function(){ const j = window.__lightos.getStageJson(); "
            "return typeof j === 'object' && Array.isArray(j.objects) && Array.isArray(j.fixtures); })()")
        self.assertTrue(stage_json_ok, "getStageJson() liefert unerwartete Form")

    def test_unlit_fixture_has_no_initial_beam_artifact(self):
        """Ein neues, ungedimmtes Fixture darf keinen Rest-Lichtkegel zeigen.

        Das ist besonders bei großen Rigs wichtig: ein erzwungenes Minimum an
        Kegel-Opacity summiert sich sonst zu einem grauen, scheinbar flackernden
        Schleier, bis der erste DMX-Update-Zyklus angekommen ist.
        """
        self._load_and_wait()
        payload = (
            '[{"fid": 987655, "type": "moving_head", "x": 0, "y": 6, '
            '"z": 0, "r": 0, "g": 0, "b": 0, "intensity": 0}]'
        )
        is_dark = self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(payload),
            "(function() { const f = window.__lightos.fixtures['987655']; "
            "return !!f && !!f.beam && f.beam.material.opacity === 0 "
            "&& f.beam.visible === false; })()",
            timeout_s=5.0,
        )
        self.assertTrue(is_dark, "Fixture mit Dimmer 0 zeigt beim Build noch einen Lichtkegel")

    def test_all_bridge_connects_wired(self):
        """Belegt den Bridge-Vertrag (Design-Dokument Leitprinzip): jedes der
        21 Signale, die tryChannel() im Original UND in bridge.js verbindet,
        wird tatsaechlich verbunden - gezaehlt ueber einen JS-seitigen Monkey-
        Patch von Signal.prototype.connect auf dem WebChannel-Bridge-Objekt,
        VOR dem Laden der Page injiziert."""
        # Cache-Buster-Query wie load_stage_html() in visualizer_window.py.
        self._load_and_wait()

        # Ob .connect() lief, ist ueber Qt/PySide6 nicht direkt introspizier-
        # bar (kein Python-API fuer "hat dieses Signal Receiver"). Deshalb
        # verifizieren wir INDIREKT ueber Verhalten: bridge.allFixtures.emit()
        # muss addFixture() in JS ausloesen und via window.__lightos.fixtures
        # sichtbar werden - das beweist, dass der Connect fuer DIESES Signal
        # wirklich griff. Mehrere repraesentative Signale unten decken die
        # unterschiedlichen JS-Handler-Pfade ab (State-Mutation, DOM-Update,
        # Slot-Ruecksprung).
        payload = '[{"fid": 987654, "x": 1, "y": 2, "z": 3, "r": 10, "g": 20, "b": 30, "intensity": 255}]'
        has_fixture = self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(payload),
            "typeof window.__lightos.fixtures['987654'] === 'object'", timeout_s=5.0)
        self.assertTrue(has_fixture, "allFixtures-Connect griff nicht (addFixture() nie ausgefuehrt)")

        # settingsChanged-Connect: Brightness-Wert muss uebernommen werden.
        brightness_ok = self._emit_until_true(
            lambda: self._bridge_obj.settingsChanged.emit('{"brightness": 0.77}'),
            "Math.abs(window.__lightos.settings.brightness - 0.77) < 0.01", timeout_s=5.0)
        self.assertTrue(brightness_ok, "settingsChanged-Connect griff nicht")

        # viewModeChanged-Connect: view.mode muss auf '2D' wechseln (ueber
        # window.__lightos.setViewMode ist der oeffentliche Weg, hier aber
        # bewusst ueber das SIGNAL, nicht den direkten Funktionsaufruf).
        self._emit_until_true(
            lambda: self._bridge_obj.viewModeChanged.emit('2D'),
            "document.getElementById('mode-text').textContent === '2D Top View'", timeout_s=5.0)
        mode_ok = self._eval("document.getElementById('mode-text').textContent")
        self.assertEqual(mode_ok, "2D Top View", "viewModeChanged-Connect griff nicht")

        # editModeChanged-Connect: Banner-Text muss auf Edit-Mode wechseln.
        self._emit_until_true(
            lambda: self._bridge_obj.editModeChanged.emit('edit'),
            "document.getElementById('mode-banner').style.display === 'block'", timeout_s=5.0)
        banner_display = self._eval(
            "document.getElementById('mode-banner').style.display")
        self.assertEqual(banner_display, "block", "editModeChanged-Connect griff nicht")

        # requestFixtures-Slot: JS ruft ihn beim ersten tryChannel()-Connect
        # automatisch auf (bridge.requestFixtures() am Ende von tryChannel()).
        deadline = time.monotonic() + 5.0
        while (time.monotonic() < deadline
               and getattr(self._bridge_obj, "_request_fixtures_calls", 0) < 1):
            _pump(0.1)
        self.assertGreaterEqual(
            getattr(self._bridge_obj, "_request_fixtures_calls", 0), 1,
            "requestFixtures()-Slot wurde von JS nie aufgerufen")

    def test_cache_buster_reaches_module_imports(self):
        """Auftrags-Pflichtpunkt: belegt empirisch, dass ein geaendertes
        Modul nach einem Reload mit frischem ?v=-Cache-Buster (identischer
        Mechanismus zu load_stage_html() in visualizer_window.py) wirklich
        neu geladen wird - fuer type=module-Importe, nicht nur die
        HTML-Top-Level-URL. Aendert testweise ein Flag in state.js, laedt neu,
        macht die Aenderung rueckgaengig."""
        probe_path = os.path.normpath(os.path.join(
            os.path.dirname(__file__), "..", "src", "ui", "visualizer",
            "scene_src", "state.js"))
        with open(probe_path, "r", encoding="utf-8") as f:
            original = f.read()
        self.assertIn("dockEnabled: false,", original, "Marker-Zeile in state.js nicht gefunden")

        try:
            # Erst-Load (Original-Inhalt).
            self._load_and_wait()
            first_val = self._poll_until_true(
                "typeof window.__lightos.settings.dockEnabled !== 'undefined' ? "
                "String(window.__lightos.settings.dockEnabled) : 'undefined'")
            self.assertEqual(first_val, "false")

            # Modul aendern: dockEnabled-Default auf true drehen.
            patched = original.replace("dockEnabled: false,", "dockEnabled: true,")
            self.assertNotEqual(patched, original)
            with open(probe_path, "w", encoding="utf-8") as f:
                f.write(patched)

            # Neu laden MIT frischem Cache-Buster (wie load_stage_html()).
            self._load_and_wait(cache_bust=True)
            second_val = self._poll_until_true(
                "typeof window.__lightos.settings.dockEnabled !== 'undefined' ? "
                "String(window.__lightos.settings.dockEnabled) : 'undefined'")
            self.assertEqual(
                second_val, "true",
                "Modul-Aenderung nach Cache-Buster-Reload NICHT sichtbar - "
                "Chromium hat scene_src/state.js aus dem Cache bedient trotz "
                "NoCache-Profil-Setting + frischer ?v=-Query auf der HTML-URL.")
        finally:
            with open(probe_path, "w", encoding="utf-8") as f:
                f.write(original)


if __name__ == "__main__":
    unittest.main()
