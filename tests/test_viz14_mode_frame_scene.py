"""VIZ-14 (Modus-Indikator): permanenter Ansehen/Bauen-Viewport-Rahmen, getrieben
von view.editMode ueber setEditMode() — End-to-End in einer ECHTEN QWebEngine.

Erster, bewusst kleiner Slice von Plan-Item 1 ("Zwei Hauptmodi"): etabliert das
Ansehen/Bauen-Vokabular VISUELL (Gegenmittel zum "Modus-Wirrwarr"), bevor die
grosse State-Machine-Kollabierung (Produktentscheidung noetig) drankommt. Reines
DOM/CSS + ein Aufruf in setEditMode — keine Python/Poll/Render-Loop-Aenderung.

Belegt: (1) Rahmen existiert, (2) Default = Ansehen (vor dem ersten Poll),
(3) Direkt-Drive setEditMode('edit'/'stage'/'view') schaltet data-mode+Chip,
(4) der ECHTE PULL-Poll-Pfad (s.editMode via bridge.js) schaltet ebenso,
(5) Regressions-Guard: der Rahmen fuehrt KEINEN Dauer-Render ein (Loop faellt in
Idle), (6) der Rahmen ist pointer-events:none (schluckt keine Canvas-Klicks).

Eigene Isolate-Datei (wie test_viz14_selection_scene.py): jede QWebEngine-Ladung
stresst den offscreen-Chromium — die Isolate-Gate faehrt pro Datei einen Prozess.
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

# Signale, die bridge.js#tryChannel() connectet (Slots <- JS separat als Slot).
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


# XPLAT-15: nach JEDEM Test die uebrig gebliebenen Top-Level-Widgets WIRKLICH
# abbauen. `deleteLater()` allein stellt `DeferredDelete` nie zu — die Objekte
# ueberleben mitsamt Kindern, Signalen und (bei Views) Renderern. Segmentiert
# faellt das nicht auf, weil jede Datei allein laeuft; in einem Prozess mit
# genug angesammeltem Zustand ist es dieselbe Klasse Zeitzuender, die vor
# XPLAT-09 neun scheinbar gruene viz-Dateien zum Segfault brachte.
# Muster + Begruendung: tests/_qt_lifecycle.py, Vorbild test_views.py.
import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    # QApplication lokal importieren: manche Dateien holen es nur INNERHALB
    # ihrer Tests, dann gibt es den Modulnamen hier nicht (3 Dateien liefen
    # genau darauf in einen NameError).
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


class ModeFrameSceneTest(unittest.TestCase):
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
        # XPLAT-09: deleteLater() allein raeumt hier nichts ab — processEvents()
        # stellt DeferredDelete nicht zu. Der View ueberlebt dann mitsamt Page,
        # Channel und Renderer, waehrend die parentlose Bridge mit der
        # TestCase-Instanz stirbt: dangling registriertes QObject -> SIGSEGV.
        # Ausfuehrliche Herleitung in tests/_qt_lifecycle.py.
        destroy_webengine_view(self._view, _pump)
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

    def _stats(self):
        return json.loads(self._eval("JSON.stringify(window.__lightos.renderStats())"))

    def _tick(self):
        self._eval("window.__lightos.__renderTick(); true")

    def _settle(self, max_rounds=30):
        last = None
        for _ in range(max_rounds):
            self._tick()
            s = self._stats()
            if (not s["dirty"]) and (not s["live"]) and s["count"] == last:
                return s
            last = s["count"]
        self.fail(f"Render-Loop stabilisiert nicht: {self._stats()}")

    # HISTORIE (XPLAT-09, aufgehoben 2026-07-29): hier stand die Auflage „BEWUSST
    # NUR 2 Testmethoden", weil >~3 sequentielle QWebEngine-Vollladungen in EINEM
    # Prozess den offscreen-Chromium-Renderer kippten. Das war kein Chromium-Limit,
    # sondern der kaputte Teardown: ``deleteLater()`` + ``processEvents()`` stellt
    # DeferredDelete nie zu, der alte View ueberlebte mitsamt Channel und Renderer,
    # waehrend die parentlose Bridge starb — dangling registriertes QObject
    # (Details in tests/_qt_lifecycle.py). Seit ``destroy_webengine_view``
    # im tearDown sind 8 aufeinanderfolgende Vollladungen in einem Prozess gemessen
    # gruen — die Deckelung ist damit NICHT mehr noetig.
    #
    # Das Buendeln vieler Checks pro Ladung bleibt hier trotzdem stehen: es ist
    # inzwischen eine reine Laufzeit-Entscheidung (jede Vollladung kostet ~4 s),
    # kein Stabilitaets-Workaround mehr. Neue Testmethoden duerfen ergaenzt werden.
    # Das Entzerren der gebuendelten Assertions ist als eigenes Item erfasst.

    # XPLAT-13: die Assertions lagen frueher in EINER Methode auf EINER Ladung
    # (Erbe der XPLAT-09-Deckelung). Jede Vollladung kostet ~4 s -- dafuer sagt
    # ein roter Lauf jetzt, WAS kaputt ist, statt nur "irgendwas am Rahmen".
    F = "document.getElementById('mode-frame')"
    CHIP = "document.getElementById('mode-frame-chip')"

    def _frische_seite(self):
        self._load_and_wait()
        self._poll_until_true("!!window.__lightosAppReady")

    def test_rahmen_existiert(self):
        self._frische_seite()
        self.assertEqual(self._eval(f"!!{self.F}"), True, "#mode-frame fehlt im DOM")

    def test_startet_auf_ansehen(self):
        """Default kommt aus dem HTML (data-mode), also schon VOR dem ersten Poll."""
        self._frische_seite()
        self.assertEqual(self._eval(f"{self.F}.dataset.mode"), "view")
        self.assertEqual(self._eval(f"{self.CHIP}.textContent"), "ANSEHEN")

    def test_rahmen_schluckt_keine_canvas_klicks(self):
        """★ `pointer-events:none` ist hier kein Feinschliff: der Rahmen liegt
        vollflaechig ueber dem Canvas — ohne das waeren Auswahl, Gizmo und Orbit
        tot, und zwar lautlos."""
        self._frische_seite()
        self.assertEqual(
            self._eval(f"getComputedStyle({self.F}).pointerEvents"), "none",
            "#mode-frame ist interaktiv (schluckt Canvas-Klicks -> Auswahl/Gizmo/Orbit tot)")

    def test_umschalten_treibt_rahmen_und_chip(self):
        """Direkt-Drive ueber die exponierte setEditMode — beide Bauen-Varianten
        und zurueck."""
        self._frische_seite()
        self._eval("window.__lightos.setEditMode('edit'); true")
        self.assertEqual(self._eval(f"{self.F}.dataset.mode"), "build")
        self.assertEqual(self._eval(f"{self.CHIP}.textContent.indexOf('Fixtures') >= 0"), True)
        self._eval("window.__lightos.setEditMode('stage'); true")
        self.assertEqual(self._eval(f"{self.F}.dataset.mode"), "build")
        # 'Buehne' — ohne Umlaut-Vergleich: Teil-String 'hne'.
        self.assertEqual(self._eval(f"{self.CHIP}.textContent.indexOf('hne') >= 0"), True)
        self._eval("window.__lightos.setEditMode('view'); true")
        self.assertEqual(self._eval(f"{self.F}.dataset.mode"), "view")
        self.assertEqual(self._eval(f"{self.CHIP}.textContent"), "ANSEHEN")

    def test_rahmen_rendert_nicht_dauerhaft(self):
        """Regressions-Guard: der Rahmen ist reines DOM. Fuehrte er eine
        Dauer-Animation ein, liefe der On-Demand-Loop fuer immer auf voller rAF."""
        self._frische_seite()
        self._eval("window.__lightos.setEditMode('edit'); true")
        s = self._settle()   # muss Idle erreichen (dirty=false, live=false, count ruht)
        self.assertFalse(s["live"], "Modus-Rahmen fuehrte eine Dauer-Animation ein")
        c = s["count"]
        for _ in range(3):
            self._tick()
        self.assertEqual(self._stats()["count"], c, "Modus-Rahmen rendert dauerhaft (Gate offen)")

    def test_real_poll_path_drives_frame(self):
        """Der ECHTE PULL-Poll-Pfad (bridge.js s.editMode -> setEditMode)."""
        self._frische_seite()
        self._bridge_obj._poll_payload = '{"editMode": "stage"}'
        self._poll_until_true(
            "document.getElementById('mode-frame').dataset.mode === 'build'",
            timeout_s=8.0)
        self.assertEqual(
            self._eval("document.getElementById('mode-frame-chip').textContent.indexOf('hne') >= 0"),
            True)


if __name__ == "__main__":
    unittest.main()
