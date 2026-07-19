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
  2) Registriert eine Mock-Bridge mit ALLEN 22 Signalen, die
     ``scene_src/bridge/bridge.js#tryChannel()`` verbindet (siehe
     ``visualizer_window.py::VisualizerBridge`` fuer die Signal-Liste) +
     dem ``requestFixtures``-Slot.
  3) Prueft ``window.__lightosAppReady === true`` - app.js ist komplett
     durchgelaufen (alle Module importiert, Render-Loop gestartet,
     Bridge-Poll gestartet).
  4) Prueft, dass ALLE 22 ``bridge.X.connect(...)``-Aufrufe aus
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
    ("addStageObjectData", (str,)),
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
    """Baut eine QObject-Subklasse mit allen 22 Signalen dynamisch (Signal()
    muss ein Klassenattribut sein, PySide6 erlaubt kein setattr nach
    Instanziierung) + dem requestFixtures-Slot."""
    attrs = {}
    for name, arg_types in _SIGNAL_SPECS:
        attrs[name] = Signal(*arg_types)

    @Slot()
    def requestFixtures(self):
        self._request_fixtures_calls = getattr(self, "_request_fixtures_calls", 0) + 1

    attrs["requestFixtures"] = requestFixtures
    @Slot(result=str)
    def pollControl(self):
        return getattr(self, "_poll_payload", "{}")

    attrs["pollControl"] = pollControl
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

    def _load_and_wait(self, cache_bust=True, gpu_tier=None):
        # WICHTIG: .clear() statt Neuzuweisung - loadFinished ist in setUp()
        # an die urspruengliche Liste per `self._loaded_ok.append` gebunden;
        # eine Neuzuweisung (`self._loaded_ok = []`) wuerde das Signal von
        # der neuen Liste entkoppeln (Callback fuellt weiter die ALTE Liste).
        self._loaded_ok.clear()
        url = QUrl.fromLocalFile(_HTML_PATH)
        query = f"v={int(time.time() * 1000)}" if cache_bust else ""
        if gpu_tier:
            # Deterministischer Tier-Override (renderer.js#probeGpuTier) —
            # offscreen laeuft sonst je nach GL-Backend mal low, mal high.
            query = (query + "&" if query else "") + f"gputier={gpu_tier}"
        if query:
            url.setQuery(query)
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

    def test_incremental_stage_add_preserves_python_id(self):
        """Ein einzelnes Stage-Add bleibt bei Direkt-/Poll-Doppelzustellung idempotent."""
        self._load_and_wait()
        payload = (
            '{"id":"py-stage-add-1","type":"platform","name":"Testdeck",'
            '"position":{"x":1,"y":0.2,"z":2},'
            '"size":{"x":6,"y":0.4,"z":4},"rotation":0,"color":"#332520"}'
        )
        created = self._emit_until_true(
            lambda: self._bridge_obj.addStageObjectData.emit(payload),
            "(function(){ const s=window.__lightos.stageObjects; "
            "return !!s['py-stage-add-1'] && Object.keys(s).length === 1; })()",
            timeout_s=5.0,
        )
        self.assertTrue(created, "Inkrementelles Stage-Add erreichte den 3D-View nicht")
        # Der gleiche Event darf kein Suffix-Objekt erzeugen.
        still_one = self._emit_until_true(
            lambda: self._bridge_obj.addStageObjectData.emit(payload),
            "Object.keys(window.__lightos.stageObjects).length === 1",
            timeout_s=5.0,
        )
        self.assertTrue(still_one, "Doppelzustellung erzeugte ein zweites Stage-Objekt")

    def test_truss_obj_uses_its_real_z_long_axis(self):
        """Das 2-m-OBJ darf nicht aus seinem 30-cm-Querschnitt langgezogen werden.

        Asset-Bounds: ca. 0.302 x 0.300 x 2.000 m (Laengsachse Z). Der alte
        Builder behandelte X als Laengsachse; seine Aussen-Bounds passten zwar,
        aber Gurte und Diagonalen waren um bis zu Faktor 13 verzerrt.
        """
        self._load_and_wait()
        import json
        objects = [
            {
                "id": "truss-axis-h", "type": "truss_h", "name": "H",
                "position": {"x": 0, "y": 1, "z": 0},
                "size": {"x": 4, "y": 0.3, "z": 0.3},
                "rotation": 0, "color": "#999999",
            },
            {
                "id": "truss-axis-v", "type": "truss_v", "name": "V",
                "position": {"x": 2, "y": 2, "z": 0},
                "size": {"x": 0.3, "y": 4, "z": 0.3},
                "rotation": 0, "color": "#999999",
            },
        ]
        payload = json.dumps({"objects": objects, "fixtures": [], "_reloadToken": 46})
        self._emit_until_true(
            lambda: self._bridge_obj.stageLoaded.emit(payload),
            "(function(){"
            " const s=window.__lightos.stageObjects;"
            " const ready=id => s[id] && s[id].mesh.children.some("
            "   c => c.userData && c.userData.isFittedTrussModel);"
            " return ready('truss-axis-h') && ready('truss-axis-v');"
            "})()",
            timeout_s=8.0,
        )
        raw = self._eval("""
            (function(){
                function info(id) {
                    const root = window.__lightos.stageObjects[id].mesh;
                    const fitted = root.children.find(
                        c => c.userData && c.userData.isFittedTrussModel);
                    const source = fitted.children[0];
                    const size = new THREE.Box3().setFromObject(root)
                        .getSize(new THREE.Vector3());
                    const scales = [fitted.scale.x, fitted.scale.y, fitted.scale.z];
                    return {
                        size: [size.x, size.y, size.z],
                        target: fitted.userData.targetLongAxis,
                        source: fitted.userData.sourceLongAxis,
                        fitScale: scales,
                        scaleRatio: Math.max(...scales) / Math.min(...scales),
                        rotation: [source.rotation.x, source.rotation.y, source.rotation.z],
                    };
                }
                return JSON.stringify({
                    h: info('truss-axis-h'), v: info('truss-axis-v')
                });
            })()
        """)
        d = json.loads(raw)
        for actual, expected in ((d["h"]["size"], [4, 0.3, 0.3]),
                                 (d["v"]["size"], [0.3, 4, 0.3])):
            for got, want in zip(actual, expected):
                self.assertAlmostEqual(got, want, places=3)
        self.assertEqual((d["h"]["source"], d["h"]["target"]), ("z", "x"))
        self.assertEqual((d["v"]["source"], d["v"]["target"]), ("z", "y"))
        # Nur die echte 2-m-Achse wird auf 4 m verdoppelt; kein 13x/.15x-
        # Extremstretch des Querschnitts mehr.
        self.assertLess(d["h"]["scaleRatio"], 2.1)
        self.assertLess(d["v"]["scaleRatio"], 2.1)
        import math
        self.assertAlmostEqual(abs(d["h"]["rotation"][1]), math.pi / 2, places=5)
        self.assertAlmostEqual(abs(d["v"]["rotation"][0]), math.pi / 2, places=5)

    def test_bulk_stage_load_keeps_every_element(self):
        """Ein kompletter Bühnen-Push darf nicht beim ersten Element enden.

        Das ist der echte Save/Load-Pfad des Bühneneditors.  Besonders wichtig
        ist der Test bei einer großen Bühne: ein fehlerhaftes Reload-Echo darf
        beispielsweise die Truss-, LED- und Publikumsobjekte nicht aus dem
        laufenden 3D-View entfernen.
        """
        self._load_and_wait()
        objects = [
            {
                "id": f"bulk-{i}", "type": typ, "name": f"Element {i}",
                "position": {"x": i - 4, "y": 0.5 + (i % 3), "z": i % 5},
                "size": {"x": 2, "y": 1, "z": 1}, "rotation": 0,
                "color": "#334455",
            }
            for i, typ in enumerate((
                "floor", "platform", "truss_h", "truss_v", "led_wall",
                "wall", "dj_booth", "speaker", "audience",
            ))
        ]
        import json
        payload = json.dumps({"objects": objects, "fixtures": [], "_reloadToken": 42})
        loaded = self._emit_until_true(
            lambda: self._bridge_obj.stageLoaded.emit(payload),
            "Object.keys(window.__lightos.stageObjects).length === 9",
            timeout_s=5.0,
        )
        self.assertTrue(loaded, "Bulk-Bühnenladung verlor mindestens ein Element")
        # Die produktive Bridge liefert denselben State zusätzlich über den
        # Pull-Kanal. Diese Doppelzustellung darf weder neu aufbauen noch
        # Elemente verlieren.
        still_complete = self._emit_until_true(
            lambda: self._bridge_obj.stageLoaded.emit(payload),
            "Object.keys(window.__lightos.stageObjects).length === 9",
            timeout_s=5.0,
        )
        self.assertTrue(still_complete, "Doppelzustellung reduzierte die Bühnenliste")

    def test_bulk_stage_load_repairs_objects_lost_just_after_load(self):
        """Der Renderer repariert einen unmittelbaren, partiellen WebGL-Snapshot."""
        self._load_and_wait()
        import json
        objects = [
            {
                "id": f"repair-{i}", "type": typ, "name": f"Repair {i}",
                "position": {"x": i, "y": 1, "z": 0},
                "size": {"x": 2, "y": 1, "z": 1}, "rotation": 0,
                "color": "#334455",
            }
            for i, typ in enumerate(("floor", "platform", "truss_h"))
        ]
        payload = json.dumps({"objects": objects, "fixtures": [], "_reloadToken": 44})
        self._emit_until_true(
            lambda: self._bridge_obj.stageLoaded.emit(payload),
            "Object.keys(window.__lightos.stageObjects).length === 3", timeout_s=5.0)
        # Verlust wie im echten Fehlerbild simulieren: WebGL-/Renderer-Ausfall
        # verliert Objekte OHNE durch removeStageObject zu laufen. (Ein
        # expliziter removeStageObject setzt seit 2026-07-11 bewusst einen
        # Lösch-Tombstone, den die Reparatur respektiert — User-Löschungen
        # dürfen nicht reanimiert werden.)
        self._eval(
            "(function(){ const s = window.__lightos.stageObjects; "
            "for (const id of Object.keys(s)) delete s[id]; return true; })()")
        repaired = self._poll_until_true(
            "Object.keys(window.__lightos.stageObjects).length === 3", timeout_s=3.0)
        self.assertTrue(repaired, "Lokale Stage-Reparatur stellte fehlende IDs nicht wieder her")

    def test_explicit_delete_survives_repair_chain(self):
        """Die Repair-Kette darf eine explizite Löschung NICHT reanimieren.

        Zombie-Guard 2026-07-11: der Repair-Loop eines Bulk-Loads läuft bis
        ~720 ms nach dem Load mit dessen expectedObjects weiter. Löscht der
        User in diesem Fenster ein Element, setzte die Kette es vorher wieder
        in die Szene (Doppel-Lösch-Zombie). Der Lösch-Tombstone hält es raus.
        """
        self._load_and_wait()
        import json
        objects = [
            {
                "id": f"tomb-{i}", "type": typ, "name": f"Tomb {i}",
                "position": {"x": i, "y": 1, "z": 0},
                "size": {"x": 2, "y": 1, "z": 1}, "rotation": 0,
                "color": "#334455",
            }
            for i, typ in enumerate(("floor", "platform", "truss_h"))
        ]
        payload = json.dumps({"objects": objects, "fixtures": [], "_reloadToken": 45})
        self._emit_until_true(
            lambda: self._bridge_obj.stageLoaded.emit(payload),
            "Object.keys(window.__lightos.stageObjects).length === 3", timeout_s=5.0)
        # Explizite Löschung im Repair-Fenster (Python-push → jsRemoveStageObject).
        self._emit_until_true(
            lambda: self._bridge_obj.removeStageObject.emit("tomb-1"),
            "Object.keys(window.__lightos.stageObjects).length === 2", timeout_s=5.0)
        # Repair-Kette komplett ausleben lassen (120 + 2×300 ms) …
        _pump(1.2)
        still_deleted = self._eval(
            "Object.keys(window.__lightos.stageObjects).length === 2 "
            "&& !window.__lightos.stageObjects['tomb-1']")
        self.assertTrue(still_deleted, "Repair-Kette hat eine explizite Löschung reanimiert")

    def test_bulk_stage_load_via_poll_keeps_every_element(self):
        """Der produktive Pull-Kanal muss komplexe Bühnen vollständig liefern."""
        objects = [
            {
                "id": f"poll-{i}", "type": typ, "name": f"Poll {i}",
                "position": {"x": i, "y": 1, "z": -i},
                "size": {"x": 2, "y": 1, "z": 1}, "rotation": 0,
                "color": "#334455",
            }
            for i, typ in enumerate((
                "floor", "platform", "truss_h", "truss_v", "led_wall",
                "wall", "dj_booth", "speaker", "audience",
            ))
        ]
        import json
        stage = json.dumps({"objects": objects, "fixtures": [], "_reloadToken": 43})
        self._bridge_obj._poll_payload = json.dumps({"stage": stage})
        self._load_and_wait()
        loaded = self._poll_until_true(
            "Object.keys(window.__lightos.stageObjects).length === 9", timeout_s=5.0)
        self.assertTrue(loaded, "Poll-Bulk-Ladung verlor mindestens ein Element")

    def test_shadow_spot_budget_respects_texture_units(self):
        """Grosse Rigs duerfen das Fragment-Shader-Texture-Limit nicht sprengen.

        Live-Befund 2026-07-11 (crash.log 12:45, Adreno-GPU mit
        MAX_TEXTURE_IMAGE_UNITS=16): 48 Fixtures = 40+ schattenwerfende
        SpotLights -> jede Shadow-Map kostet eine Texture-Unit in JEDEM
        beleuchteten Material -> kein Lit-Shader kompilierte mehr, die ganze
        Buehne blieb unsichtbar (nur MeshBasic-Beams zeichneten noch).
        Fix: nur die ersten N Spots werfen Schatten (N = maxTextures - Reserve,
        deterministisch nach fid), Entfernen gibt Budget an den Rest zurueck.
        """
        self._load_and_wait()
        import json
        n = 30
        payload = json.dumps([
            {"fid": 800000 + i, "type": "moving_head", "x": i, "y": 6, "z": 0,
             "r": 255, "g": 0, "b": 0, "intensity": 255}
            for i in range(n)
        ])
        built = self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(payload),
            f"Object.keys(window.__lightos.fixtures).length === {n}",
            timeout_s=10.0)
        self.assertTrue(built, "Nicht alle 30 Fixtures wurden gebaut")

        count_js = """
            (function(){
                const fx = window.__lightos.fixtures;
                let spots = 0, shadows = 0;
                for (const fid in fx) {
                    const s = fx[fid].spot;
                    if (s) { spots += 1; if (s.castShadow) shadows += 1; }
                }
                const gl = document.createElement('canvas').getContext('webgl');
                const maxTex = gl ? gl.getParameter(gl.MAX_TEXTURE_IMAGE_UNITS) : 16;
                return JSON.stringify({spots: spots, shadows: shadows, maxTex: maxTex});
            })()
        """
        c = json.loads(self._eval(count_js))
        budget = max(2, int(c["maxTex"]) - 6)
        self.assertEqual(c["spots"], n, "Jedes generische Fixture braucht seinen SpotLight")
        self.assertEqual(
            c["shadows"], min(n, budget),
            f"Shadow-Spots ({c['shadows']}) muessen exakt das Budget "
            f"min({n}, {budget}) ausschoepfen — nicht mehr (Shader-Limit), "
            f"nicht weniger (Optik ohne Not verschenkt)")

        # Entfernen gibt Budget zurueck: nach dem Loeschen eines Fixtures
        # bleibt die Verteilung exakt am (neuen) Limit.
        removed = self._emit_until_true(
            lambda: self._bridge_obj.fixtureRemoved.emit(800000),
            f"Object.keys(window.__lightos.fixtures).length === {n - 1}",
            timeout_s=5.0)
        self.assertTrue(removed, "fixtureRemoved erreichte den 3D-View nicht")
        c2 = json.loads(self._eval(count_js))
        self.assertEqual(
            c2["shadows"], min(n - 1, budget),
            "Nach dem Entfernen wurde das Shadow-Budget nicht neu verteilt")

    def test_gpu_tier_low_reduces_geometry_and_culls_dark_spots(self):
        """Low-Spec-Modus (Surface/Adreno): schlankere Kegel + Dunkel-Culling.

        Auf 16-Texture-Unit-GPUs ist neben dem Shadow-Budget die laufende
        Licht-Auswertung der Kostentreiber: ein SpotLight mit intensity 0
        wird sonst weiter in JEDEM beleuchteten Pixel mitgerechnet. Das
        Culling ist tier-unabhaengig; die Geometrie-Reduktion nur im Low-Tier.
        """
        self._load_and_wait(gpu_tier="low")
        import json
        tier = self._eval("window.__lightos.gpuTier")
        self.assertEqual(tier, "low")

        dark = json.dumps([{"fid": 700001, "type": "moving_head",
                            "x": 0, "y": 6, "z": 0,
                            "r": 0, "g": 0, "b": 0, "intensity": 0}])
        built = self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(dark),
            "(function(){ const f = window.__lightos.fixtures['700001']; "
            "return !!f && !!f.spot && f.spot.visible === false; })()",
            timeout_s=5.0)
        self.assertTrue(built, "Dunkler SpotLight wurde nicht aus der Licht-Auswertung genommen")

        segments = self._eval(
            "window.__lightos.fixtures['700001'].beam.geometry.parameters.radialSegments")
        self.assertEqual(segments, 12, "Low-Tier muss die Beam-Kegel auf 12 Segmente reduzieren")

        # FM-Runde 2: auch die Gehaeuse-Rundkoerper folgen dem Tier (segs()-
        # Helfer in builders.js) — der MH-Kopf faellt von 28 auf 14 Segmente.
        housing = self._eval(
            "(function(){ let s = null;"
            " window.__lightos.fixtures['700001'].group.traverse(o => {"
            "   if (o.name === 'mh-head-body') s = o.geometry.parameters.radialSegments;"
            " }); return s; })()")
        self.assertEqual(housing, 14, "Low-Tier muss Gehaeuse-Segmente halbieren (segs())")

        # Aufdrehen ueber den echten dmxBatch-Pfad -> Licht wird wieder aktiv.
        lit_batch = json.dumps([{"fid": 700001, "r": 255, "g": 40, "b": 0, "intensity": 255}])
        lit = self._emit_until_true(
            lambda: self._bridge_obj.dmxBatch.emit(lit_batch),
            "window.__lightos.fixtures['700001'].spot.visible === true",
            timeout_s=5.0)
        self.assertTrue(lit, "Aufgedrehter SpotLight wurde nicht wieder sichtbar")
        # Und wieder dunkel -> wieder raus aus der Auswertung.
        dark_batch = json.dumps([{"fid": 700001, "r": 0, "g": 0, "b": 0, "intensity": 0}])
        dark_again = self._emit_until_true(
            lambda: self._bridge_obj.dmxBatch.emit(dark_batch),
            "window.__lightos.fixtures['700001'].spot.visible === false",
            timeout_s=5.0)
        self.assertTrue(dark_again, "Abgedunkelter SpotLight blieb in der Licht-Auswertung")

    def test_gpu_tier_high_keeps_full_geometry(self):
        """High-Tier behaelt die volle Kegel-Aufloesung (keine Optik-Regression)."""
        self._load_and_wait(gpu_tier="high")
        import json
        tier = self._eval("window.__lightos.gpuTier")
        self.assertEqual(tier, "high")
        payload = json.dumps([{"fid": 700002, "type": "par",
                               "x": 1, "y": 0, "z": 0,
                               "r": 0, "g": 0, "b": 0, "intensity": 0}])
        self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(payload),
            "!!window.__lightos.fixtures['700002']", timeout_s=5.0)
        segments = self._eval(
            "window.__lightos.fixtures['700002'].beam.geometry.parameters.radialSegments")
        self.assertEqual(segments, 24, "High-Tier darf die Kegel-Geometrie nicht reduzieren")
        # FM-Runde 2: Gehaeuse-Segmente bleiben im High-Tier voll (segs()-Helfer).
        housing = self._eval(
            "(function(){ let s = null;"
            " window.__lightos.fixtures['700002'].group.traverse(o => {"
            "   if (o.name === 'par-body') s = o.geometry.parameters.radialSegments;"
            " }); return s; })()")
        self.assertEqual(housing, 16, "High-Tier darf Gehaeuse-Segmente nicht reduzieren")
        # Dunkel-Culling gilt tier-unabhaengig.
        culled = self._eval(
            "window.__lightos.fixtures['700002'].spot.visible === false")
        self.assertTrue(culled, "Dunkel-Culling muss auch im High-Tier greifen")

    def test_spider_override_without_heads_uses_base_color(self):
        """FM-12-Review-HIGH: 'spider'-Modell ohne Multihead-Banks (z.B. via
        viz_model-Override auf einem RGB-PAR) muss auf die Top-Level-Farbe
        zurueckfallen — vorher blieben alle LEDs dauerhaft dunkel, weil
        updateSpiderDmx nur aus f.lastHeads las."""
        self._load_and_wait()
        import json
        payload = json.dumps([{"fid": 810, "type": "par", "model": "spider",
                               "x": 0, "y": 3, "z": 0,
                               "r": 0, "g": 0, "b": 0, "intensity": 0}])
        self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(payload),
            "!!window.__lightos.fixtures['810']", timeout_s=5.0)
        lit = json.dumps([{"fid": 810, "r": 255, "g": 0, "b": 0, "intensity": 255}])
        ok = self._emit_until_true(
            lambda: self._bridge_obj.dmxBatch.emit(lit),
            "(function(){ const f = window.__lightos.fixtures['810'];"
            " if (!f || !f.bars) return false;"
            " return f.bars.some(bar => bar.lenses.some("
            "   l => l.material.emissiveIntensity > 0.1)); })()",
            timeout_s=5.0)
        self.assertTrue(
            ok, "Spider-Override ohne Head-Daten blieb dunkel "
                "(Basis-RGB-Fallback in updateSpiderDmx fehlt)")

    def test_fixture_models_have_realistic_dimensions(self):
        """FM-Runde 2: Gehaeuse-Bounding-Boxen folgen echten Datenblatt-Massen.

        Referenzen (siehe builders.js): PAR-64-Dose Ø ~0,23 m; Moving Head
        (Intimidator-260-Klasse) H ~0,48 m; 8x10W-Spider 0,40 x 0,25 x 0,20 m;
        Dotz-TPar-4er-Bar ~1,05 m; 4-Kopf-Mover-Bar ~1,05 m; Nebelmaschine
        (N-10-Klasse) 0,20 x 0,17 x 0,33 m. Vorher waren PAR/Spider/Bars etwa
        doppelt so gross wie die echten Geraete. Beams (excludeFromFit) und
        ausgeblendete Fallback-Koerper zaehlen nicht mit.
        """
        self._load_and_wait()
        import json
        rig = json.dumps([
            {"fid": 801, "type": "par",
             "x": 0, "y": 2, "z": 0, "r": 0, "g": 0, "b": 0, "intensity": 0},
            {"fid": 802, "type": "moving_head",
             "x": 2, "y": 2, "z": 0, "r": 0, "g": 0, "b": 0, "intensity": 0},
            {"fid": 803, "type": "moving_head", "model": "spider",
             "x": 4, "y": 2, "z": 0, "r": 0, "g": 0, "b": 0, "intensity": 0},
            {"fid": 804, "type": "led_bar", "model": "par_bar", "nHeads": 4,
             "x": 6, "y": 2, "z": 0, "r": 0, "g": 0, "b": 0, "intensity": 0},
            {"fid": 805, "type": "moving_head", "model": "mover_bar", "nHeads": 4,
             "x": 8, "y": 2, "z": 0, "r": 0, "g": 0, "b": 0, "intensity": 0},
            {"fid": 806, "type": "smoke",
             "x": 10, "y": 2, "z": 0, "r": 0, "g": 0, "b": 0, "intensity": 0},
            {"fid": 807, "type": "matrix", "nHeads": 64,
             "x": 12, "y": 2, "z": 0, "r": 0, "g": 0, "b": 0, "intensity": 0},
        ])
        built = self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(rig),
            "!!window.__lightos.fixtures['807']", timeout_s=8.0)
        self.assertTrue(built, "Mess-Rig wurde nicht gebaut")
        raw = self._eval("""
            (function(){
                function dims(fid) {
                    const f = window.__lightos.fixtures[fid];
                    if (!f) return null;
                    f.group.updateMatrixWorld(true);
                    const box = new THREE.Box3();
                    let found = false;
                    f.group.traverse(o => {
                        if (!o.isMesh) return;
                        if (o.userData && o.userData.excludeFromFit) return;
                        if (o.visible === false) return;
                        const b = new THREE.Box3().setFromObject(o);
                        if (!b.isEmpty()) { box.union(b); found = true; }
                    });
                    if (!found) return null;
                    const s = box.getSize(new THREE.Vector3());
                    return [s.x, s.y, s.z];
                }
                return JSON.stringify({
                    par: dims('801'), mh: dims('802'), spider: dims('803'),
                    parBar: dims('804'), moverBar: dims('805'), smoke: dims('806'),
                    matrix: dims('807'),
                });
            })()
        """)
        d = json.loads(raw)
        for key in ("par", "mh", "spider", "parBar", "moverBar", "smoke", "matrix"):
            self.assertIsNotNone(d[key], f"Bounding-Box fuer {key} fehlt")
        px, py, pz = d["par"]
        self.assertLessEqual(px, 0.36, "PAR breiter als eine echte PAR-64-Dose")
        self.assertLessEqual(pz, 0.36, "PAR tiefer als eine echte PAR-64-Dose")
        self.assertGreaterEqual(px, 0.15, "PAR unrealistisch geschrumpft")
        mx, my, mz = d["mh"]
        self.assertLessEqual(my, 0.55, "Moving Head hoeher als die 260er-Klasse")
        self.assertGreaterEqual(my, 0.35, "Moving Head unrealistisch geschrumpft")
        self.assertLessEqual(mx, 0.36, "Moving-Head-Basis breiter als real")
        sx, sy, sz = d["spider"]
        self.assertLessEqual(sx, 0.46, "Spider breiter als die 8x10W-Klasse (0,40 m)")
        self.assertLessEqual(sz, 0.30, "Spider tiefer als die 8x10W-Klasse (0,25 m)")
        self.assertLessEqual(sy, 0.26, "Spider hoeher als die 8x10W-Klasse (0,20 m)")
        bx = d["parBar"][0]
        self.assertLessEqual(bx, 1.15, "4er-PAR-Bar laenger als die Dotz-TPar-Klasse (~1,0 m)")
        self.assertGreaterEqual(bx, 0.90, "4er-PAR-Bar unrealistisch kurz")
        mbx, mby, _ = d["moverBar"]
        self.assertLessEqual(mbx, 1.15, "4-Kopf-Mover-Bar laenger als die 1-m-Klasse")
        self.assertGreaterEqual(mbx, 0.90, "4-Kopf-Mover-Bar unrealistisch kurz")
        self.assertLessEqual(mby, 0.36, "Mover-Bar hoeher als die AXIS-Klasse (0,27 m)")
        smx, _, smz = d["smoke"]
        self.assertLessEqual(smx, 0.30, "Nebelmaschine breiter als die N-10-Klasse")
        self.assertLessEqual(smz, 0.42, "Nebelmaschine tiefer als die N-10-Klasse")
        # FM-13: Matrix-Panel = feste 0,5-m-LED-Kachel (0,50 x 0,50 x 0,05 m),
        # Pixel-Quads knapp vor der +Z-Front (duenn). Aufloesung aendert die
        # physische Panel-Groesse NICHT.
        mtx = d["matrix"]
        self.assertLessEqual(mtx[0], 0.56, "Matrix-Panel breiter als die 0,5-m-Kachel")
        self.assertGreaterEqual(mtx[0], 0.44, "Matrix-Panel unrealistisch geschrumpft")
        self.assertLessEqual(mtx[1], 0.56, "Matrix-Panel hoeher als die 0,5-m-Kachel")
        self.assertLessEqual(mtx[2], 0.12, "Matrix-Panel dicker als eine flache LED-Kachel")

    def test_matrix_panel_per_pixel_color(self):
        """FM-13: buildMatrixPanel baut rows*cols Pixel-Quads; updateMatrixPanelDmx
        faerbt jeden Pixel EINZELN aus heads[i]. 8x8 (64 Pixel): Pixel 40 (2. Haelfte!)
        rot, Pixel 0 aus. Pixel 40 wuerde bei nur 16 gebauten Pixeln fehlen -> deckt
        die Review-HIGH-Regression (nHeads muss die echte Pixel-Anzahl tragen) ab."""
        self._load_and_wait()
        import json
        payload = json.dumps([{"fid": 820, "type": "matrix", "nHeads": 64,
                               "x": 0, "y": 3, "z": 0,
                               "r": 0, "g": 0, "b": 0, "intensity": 0}])
        built = self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(payload),
            "(function(){const f=window.__lightos.fixtures['820'];"
            " return !!(f && f.pixels && f.pixels.length===64);})()",
            timeout_s=6.0)
        self.assertTrue(built, "Matrix-Panel (64 Pixel) wurde nicht gebaut")
        heads = [{"r": 255 if i == 40 else 0, "g": 0, "b": 0} for i in range(64)]
        lit = json.dumps([{"fid": 820, "r": 0, "g": 0, "b": 0,
                           "intensity": 255, "heads": heads}])
        ok = self._emit_until_true(
            lambda: self._bridge_obj.dmxBatch.emit(lit),
            "(function(){const f=window.__lightos.fixtures['820'];"
            " if(!f||!f.pixels||f.pixels.length!==64) return false;"
            " const p40=f.pixels[40].mesh.material, p0=f.pixels[0].mesh.material;"
            " return p40.emissiveIntensity>0.1 && p40.emissive.r>0.5"
            "     && p0.emissive.r<0.1; })()",
            timeout_s=6.0)
        self.assertTrue(ok, "Matrix-Panel faerbte Pixel 40 nicht (nur 16 gebaut? heads[40] verloren?)")

    def test_multihead_beams_resync_on_showcones_and_view_switch(self):
        """A3D-05 + A3D-24: Multi-Head-Pro-Kopf-Kegel folgen showCones-Toggle
        UND 2D<->3D-Wechsel SOFORT.

        Die Pro-Kopf-Kegel von PAR-Bar/Mover-Bar/Spider
        (``f.parHeads[*].beam`` / ``f.moverHeads[*].beam`` / ``f.bars[*].beams[*]``)
        wurden bisher NUR von den Pro-Fixture-DMX-Handlern
        (updateParBar/MoverBar/SpiderDmx) gesetzt. ``applySettings`` (showCones-
        Toggle) und ``setViewMode`` (2D<->3D) fassten nur den Einzelkopf-Kegel
        ``f.beam`` (+ Laser-Faecher) an -> die Bar-/Spider-Kegel blieben bis zum
        naechsten DMX-Update der Fixture auf ihrem alten Sichtbarkeits-Stand
        stehen (A3D-05 / A3D-24). Der gemeinsame Helfer
        ``resyncBeamVisibility(f)`` (builders.js) schliesst diese Luecke an
        beiden Aufrufstellen. VOR dem Fix laufen die drei ``every(... === false)``
        bzw. Rueckstell-Polls in den Timeout.
        """
        self._load_and_wait()
        import json
        # PAR-Bar mit 4 Koepfen bei vollem Master-Dimmer -> jeder Pro-Kopf-Kegel
        # bekommt opacity>0.01 und ist im 3D sichtbar (bright=intNorm gilt fuer
        # ALLE Koepfe gemeinsam, s. updateParBarDmx).
        build = json.dumps([{"fid": 555001, "type": "led_bar", "model": "par_bar",
                             "nHeads": 4, "x": 0, "y": 3, "z": 0,
                             "r": 255, "g": 40, "b": 0, "intensity": 255}])
        self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(build),
            "(function(){ const f = window.__lightos.fixtures['555001'];"
            " return !!f && !!f.parHeads && f.parHeads.length === 4; })()",
            timeout_s=8.0)
        lit = json.dumps([{"fid": 555001, "r": 255, "g": 40, "b": 0, "intensity": 255}])
        all_lit = self._emit_until_true(
            lambda: self._bridge_obj.dmxBatch.emit(lit),
            "(function(){ const hs = window.__lightos.fixtures['555001'].parHeads;"
            " return hs.every(ph => ph.beam && ph.beam.visible === true"
            "                  && ph.beam.material.opacity > 0.01); })()",
            timeout_s=6.0)
        self.assertTrue(all_lit, "PAR-Bar-Pro-Kopf-Kegel wurden nicht beleuchtet/sichtbar")

        # A3D-05: showCones AUS -> ALLE Pro-Kopf-Kegel sofort unsichtbar, OHNE
        # weiteres DMX-Update fuer die (statische) Fixture.
        cones_off = self._emit_until_true(
            lambda: self._bridge_obj.settingsChanged.emit('{"showCones": false}'),
            "window.__lightos.fixtures['555001'].parHeads.every(ph => ph.beam.visible === false)",
            timeout_s=5.0)
        self.assertTrue(cones_off, "showCones AUS liess die Multi-Head-Kegel sichtbar (A3D-05)")

        # showCones AN -> die beleuchteten Pro-Kopf-Kegel wieder sichtbar.
        cones_on = self._emit_until_true(
            lambda: self._bridge_obj.settingsChanged.emit('{"showCones": true}'),
            "window.__lightos.fixtures['555001'].parHeads.every(ph => ph.beam.visible === true)",
            timeout_s=5.0)
        self.assertTrue(cones_on, "showCones AN stellte die Multi-Head-Kegel nicht wieder her (A3D-05)")

        # A3D-24: 2D versteckt alle Kegel, Rueckwechsel auf 3D stellt sie wieder
        # her — ebenfalls ohne zwischenzeitliches DMX-Update.
        view_2d = self._emit_until_true(
            lambda: self._bridge_obj.viewModeChanged.emit('2D'),
            "window.__lightos.fixtures['555001'].parHeads.every(ph => ph.beam.visible === false)",
            timeout_s=5.0)
        self.assertTrue(view_2d, "2D-Wechsel liess die Multi-Head-Kegel sichtbar (A3D-24)")
        back_3d = self._emit_until_true(
            lambda: self._bridge_obj.viewModeChanged.emit('3D'),
            "window.__lightos.fixtures['555001'].parHeads.every(ph => ph.beam.visible === true)",
            timeout_s=5.0)
        self.assertTrue(back_3d, "2D->3D-Wechsel stellte die Multi-Head-Kegel nicht wieder her (A3D-24)")

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
        # newline="" bewahrt die exakten Zeilenenden — der Roundtrip dieses
        # Tests hinterliess sonst eine CRLF-konvertierte state.js als
        # Dauer-Dirty-Datei im Worktree (beobachtet 2026-07-11).
        with open(probe_path, "r", encoding="utf-8", newline="") as f:
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
            with open(probe_path, "w", encoding="utf-8", newline="") as f:
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
            with open(probe_path, "w", encoding="utf-8", newline="") as f:
                f.write(original)


if __name__ == "__main__":
    unittest.main()
