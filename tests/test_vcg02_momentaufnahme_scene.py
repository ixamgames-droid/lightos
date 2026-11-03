"""VCG-02: Momentaufnahme aus der ECHTEN 3D-Szene (QWebEngine + three.js).

``window.__lightos.momentaufnahme()`` muss ein Bild der Szene liefern, obwohl
der Renderer ohne ``preserveDrawingBuffer`` laeuft: nach dem Compositing ist
der Zeichenpuffer leer (transparent), ein nacktes ``toDataURL`` gaebe ein
leeres Bild. Belegt wird: PNG in Canvas-Groesse, deckend, in der hellen
Hintergrundfarbe — und der ganze Dialog-Weg (3D-Ansicht finden, aufnehmen,
zuschneiden, in den Asset-Cache legen) gegen dieselbe Seite.
"""
import base64
import tempfile
import json
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QObject, QUrl, Signal, Slot
from _qt_lifecycle import destroy_webengine_view  # XPLAT-09
import _webgl_gate                      # QA-74

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

    @Slot(str)
    def fixtureSelectionChanged(self, fids_json):
        pass

    attrs["fixtureSelectionChanged"] = fixtureSelectionChanged
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





class MomentaufnahmeSzenenTest(unittest.TestCase):
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
        # Bewusst OHNE show(): ein gezeigter offscreen-View verlor hier den
        # GL-Kontext in 6 von 6 Laeufen (XPLAT-17-Bild), die Bildpruefung von
        # test_viz101 laeuft ohne show() stabil. Die Sichtbarkeitsregel der
        # Suche prueft test_vcg02_tastenbild_aus_3d.py.
        self._view.resize(640, 360)
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
        # QA-86: Stufe fest, sonst waehlt die GPU-Probe des Testrechners
        # (Windows/ANGLE meldet 16 Textur-Einheiten -> 'low', Prisma gedeckelt).
        url.setQuery(f"v={int(time.time() * 1000)}&gputier=high")
        self._view.load(url)
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded_ok and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded_ok, "loadFinished nie ausgeloest (Timeout)")
        self.assertTrue(self._loaded_ok[-1], "loadFinished(ok=False)")

    def _warte_auf_szene(self, _zweiter_versuch=False):
        # QA-74: EINE Quelle fuer "die Szene kam nicht hoch - was nun?" —
        # einmal neu laden, beim wiederholten GL-Ausfall ueberspringen.
        try:
            self._poll_until_true("!!window.__lightosAppReady")
        except AssertionError as e:
            diagnose = _webgl_gate.szenen_diagnose(self._view, _pump, 3.0)
            if _webgl_gate.nach_szenen_timeout(
                    e, diagnose, zweiter_versuch=_zweiter_versuch):
                _pump(1.0)
                self._load_and_wait()
                return self._warte_auf_szene(_zweiter_versuch=True)

    def _eval(self, js_expr):
        # ★ QA-VIZ-TESTS (2026-08-05): ein JS-Wurf kam hier als leerer String
        # zurueck — ununterscheidbar von einem echten Ergebnis. Und an rund 25
        # Stellen wird der Rueckgabewert ohnehin verworfen ("...; true"), ein
        # TypeError mitten im Ausdruck sah damit aus wie ein bestandener
        # Schritt. Die Huelle faengt den Wurf im Seitenkontext und macht ihn zum
        # Testfehler, statt ihn zu verschlucken.
        # (0,eval) ist INDIREKTES eval: es liefert den Completion-Wert der
        # LETZTEN Anweisung — "a(); true" bleibt also true, die bestehenden
        # Aufrufe behalten ihre Bedeutung unveraendert.
        _huelle = ("(function(){try{return JSON.stringify(['ok',(0,eval)("
                   + json.dumps(js_expr) + ")]);}"
                   "catch(e){return JSON.stringify(['err',String(e)]);}})()")
        box = []
        self._view.page().runJavaScript(_huelle, lambda result: box.append(result))
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(box, f"runJavaScript-Callback nie ausgeloest fuer: {js_expr}")
        self.assertTrue(box[0], f"runJavaScript lieferte nichts fuer: {js_expr}")
        art, wert = json.loads(box[0])
        self.assertNotEqual(art, "err", f"JS warf bei '{js_expr}': {wert}")
        return wert

    def _poll_until_true(self, js_expr, timeout_s=_POLL_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            last = self._eval(js_expr)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout beim Warten auf truthy '{js_expr}' (letzter: {last!r})")



    def _gl_weg(self):
        """GL-Kontext offscreen verloren? Dann ist die Bildpruefung nicht
        moeglich -> ueberspringen (wie test_viz101_licht_durch_wand_scene.py),
        statt an einer ungeprueften Zusicherung zu scheitern (QA-74)."""
        return self._eval(
            "(function(){var c=document.getElementsByTagName('canvas')[0];"
            "var g=c&&(c.getContext('webgl2')||c.getContext('webgl'));"
            "return !g || g.isContextLost();})()")

    def _bild(self):
        url = self._eval("window.__lightos.momentaufnahme()")
        if not url and self._gl_weg():
            self.skipTest("GL-Kontext offscreen verloren — Bildpruefung nur mit Kontext")
        self.assertTrue(isinstance(url, str) and url.startswith("data:image/png;base64,"),
                        f"keine PNG-Data-URL: {str(url)[:60]!r}")
        bild = QImage()
        bild.loadFromData(base64.b64decode(url.split(",", 1)[1]))
        self.assertFalse(bild.isNull(), "PNG nicht lesbar")
        return bild

    def test_aufnahme_zeigt_die_szene_und_landet_als_tastenbild(self):
        from src.core.show import vc_assets
        from src.ui.virtualconsole import vc_momentaufnahme as mom
        from src.ui.virtualconsole.vc_gallery_dialog import VCGalleryDialog
        from PySide6.QtWidgets import QWidget

        self._load_and_wait()
        self._warte_auf_szene()
        # Heller Hintergrund (#b0b0b8): ein leerer Puffer waere transparent.
        # Ohne show() hat die Seite keinen Sichtbereich — wie test_viz101 einen
        # festen vorgeben, damit der Renderer eine echte Zeichenflaeche bekommt.
        self._eval("Object.defineProperty(window, 'innerWidth', {value: 320, configurable: true});"
                   "Object.defineProperty(window, 'innerHeight', {value: 180, configurable: true});"
                   "window.dispatchEvent(new Event('resize')); true")
        self._eval("window.__lightos.setBrightnessManual(1.0); true")
        _pump(0.3)   # Compositing laufen lassen -> Puffer ohne preserve leer
        if self._gl_weg():
            self.skipTest("GL-Kontext offscreen verloren — Bildpruefung nur mit Kontext")

        bild = self._bild()
        breite, hoehe = json.loads(self._eval(
            "(function(){var c=document.getElementsByTagName('canvas')[0];"
            "return JSON.stringify([c.width, c.height]);})()"))
        self.assertGreater(breite, 1)
        self.assertEqual((bild.width(), bild.height()), (breite, hoehe))
        mitte = bild.pixelColor(bild.width() // 2, 4)
        self.assertEqual(mitte.alpha(), 255, f"Aufnahme leer/transparent: {mitte.name()}")
        self.assertGreater(mitte.red(), 120, f"nicht der helle Hintergrund: {mitte.name()}")

        # Ganzer Dialog-Weg gegen dieselbe Seite.
        vc_assets.set_cache_dir_for_test(tempfile.mkdtemp(prefix="vcg02_szene_"))
        try:
            self._view._lightos_3d_szene = True       # setzt sonst load_stage_html
            mom_finde = mom.finde_3d_ansicht
            mom.finde_3d_ansicht = lambda: self._view  # nicht gezeigt, s. setUp
            self.addCleanup(setattr, mom, "finde_3d_ansicht", mom_finde)
            taste = QWidget()
            taste.resize(120, 120)
            dlg = VCGalleryDialog(taste)
            meldungen = []
            dlg._melden = meldungen.append
            dlg._aus_3d_aufnehmen()
            deadline = time.monotonic() + _POLL_TIMEOUT_S
            while dlg.selected_key is None and not meldungen \
                    and time.monotonic() < deadline:
                _app.processEvents()
                time.sleep(_POLL_INTERVAL_S)
            dlg._stop_movies()
            if meldungen and self._gl_weg():
                self.skipTest("GL-Kontext waehrend der Aufnahme verloren")
            self.assertEqual(meldungen, [])
            self.assertTrue(vc_assets.is_valid_key(dlg.selected_key or ""))
            tbild = QImage(vc_assets.resolve(dlg.selected_key))
            self.assertEqual(tbild.width(), tbild.height())          # Taste 1:1
            self.assertLessEqual(tbild.width(), mom.MAX_PX)
            self.assertEqual(tbild.pixelColor(tbild.width() // 2, 1).alpha(), 255)
        finally:
            vc_assets.set_cache_dir_for_test(None)


if __name__ == "__main__":
    unittest.main()
