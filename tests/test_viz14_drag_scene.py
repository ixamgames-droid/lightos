"""VIZ-14 Drag-Haelfte — END-TO-END durch eine ECHTE QWebEngine.

Der eigentliche Beweis dieser Runde. Gemessen wird der Weg, den ein Drag aus der
Qt-Geraeteliste in der Seite nimmt: ``dragover`` fuehrt den Geist mit, ``drop``
schickt GENAU DIESES Geraet an die Bruecke.

Warum ueber echte Drag-Ereignisse und nicht ueber eine Selbstauskunft: der Drag
kommt von aussen (Qt -> QWebEngineView -> Seite). Dass diese Kette traegt, wurde
vor dem Bauen gemessen; dass die Seite richtig darauf reagiert, misst dieser
Test — mit ``DataTransfer``-Nutzlast, wie sie Qt liefert.
"""
import json
import os
import time
import unittest
import warnings

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
    ("alignSelected", (str,)), ("distributeSelected", (str,)),
    ("arrangeSelected", (str,)), ("cameraReset", ()),
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
    def placeFixture(self, j):
        self._placed = getattr(self, "_placed", []) + [j]

    attrs["placeFixture"] = placeFixture
    attrs["requestFullResync"] = Signal()
    return type("MockVisualizerBridge", (QObject,), attrs)


_MockVisualizerBridge = _make_mock_bridge_class()


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


class DragDropSceneTest(unittest.TestCase):
    """EINE WebEngine fuer die ganze Klasse.

    ``show()`` ist hier Pflicht — ohne echtes Layout liefert
    ``getBoundingClientRect()`` 0x0 und die A3D-41-NaN-Waechter verwerfen jede
    Zeiger-/Drag-Eingabe still. Eine sichtbare Ansicht kostet aber einen
    WebGL-Kontext, und drei davon nacheinander erschoepfen ihn in dieser
    Umgebung reproduzierbar („Error creating WebGL context", gemessen). Deshalb
    EINE Ansicht je Klasse; jeder Test setzt stattdessen seinen Zustand zurueck.
    """

    @classmethod
    def setUpClass(cls):
        cls._view = QWebEngineView()
        try:
            cls._view.page().profile().setHttpCacheType(
                QWebEngineProfile.HttpCacheType.NoCache)
        except Exception:
            pass
        s = cls._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        cls._bridge_obj = _MockVisualizerBridge()
        cls._channel = QWebChannel(cls._view)
        cls._channel.registerObject("bridge", cls._bridge_obj)
        cls._view.page().setWebChannel(cls._channel)
        cls._view.resize(800, 600)
        # Ohne echtes Layout liefert getBoundingClientRect() 0x0 und die
        # A3D-41-NaN-Waechter verwerfen jede Zeiger-Eingabe still (Lehre aus
        # dem Deselect-Test: der war zweimal rot, ohne dass Code fehlte).
        cls._view.show()
        cls._loaded_ok = []
        cls._view.loadFinished.connect(cls._loaded_ok.append)

    @classmethod
    def tearDownClass(cls):
        destroy_webengine_view(cls._view, _pump)   # XPLAT-09
        cls._view = None

    def setUp(self):
        """Zustand zuruecksetzen statt neu zu laden — die Seite bleibt stehen."""
        if not getattr(type(self), "_geladen", False):
            self._load_and_wait()
            type(self)._geladen = True
        self._bridge_obj._placed = []
        self._eval("window.__lightos.setEditMode('edit');"
                   " window.__lightos.setPlaceableCount(0); true")

    def _load_and_wait(self, _zweiter_versuch=False):
        self._loaded_ok.clear()
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}")
        self._view.load(url)
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded_ok and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded_ok and self._loaded_ok[-1], "Page nicht geladen")
        try:
            self._poll_until_true("!!window.__lightosAppReady")
        except AssertionError as e:
            # XPLAT-19: die Diagnose VOR dem Neuladen lesen — danach sind die
            # Flags der gescheiterten Ladung weg.
            diagnose = self._szenen_diagnose()
            # XPLAT-17: In seltenen Faellen verliert Chromium beim Start den
            # GL-Kontext IM EIGENEN Prozess („Context lost during MakeCurrent"
            # -> „Error creating WebGL context"), und three.js kommt gar nicht
            # erst hoch. Gemessen ueber 6 volle Gate-Laeufe: 1 Ausfall, und nur
            # in Dateien, die `view.show()` rufen — diese hier ist eine davon.
            #
            # Das PRODUKT heilt genau das schon: der Szenen-Start-Waechter
            # (VIZ-SCENE-SELFHEAL) laedt nach genau EINEM verlorenen Kontext neu,
            # statt schwarz zu bleiben. Der Harness zieht hier nach — derselbe
            # Vorgang, dieselbe Begrenzung auf einen Versuch.
            #
            # ★ Warum das KEINE Wiederholungslogik im verbotenen Sinn ist: es
            #   wird nur der Seiten-Aufbau wiederholt, nicht der Test. Startet
            #   die Szene wirklich nicht mehr (echte Regression), scheitert auch
            #   der zweite Versuch und das Gate bleibt rot. Und der Fall wird
            #   LAUT: die Warnung unten steht im Segment-Log, damit aus
            #   „heilt sich" nie „faellt niemandem auf" wird.
            if _zweiter_versuch:
                raise AssertionError(
                    f"{e} | Szenen-Diagnose: {diagnose}") from None
            # ★ XPLAT-19: `warnings.warn` statt `print`. Der Runner laeuft mit
            # `pytest -q ... -rf` OHNE `-s` (tools/verify_segmented.sh) — der
            # Print eines am Ende BESTANDENEN Tests wird also weggefangen und
            # ist nie zu sehen. Die Warnings-Summary erscheint dagegen immer.
            # Damit werden die selbstgeheilten Faelle erstmals zaehlbar; genau
            # die Zahl fehlt XPLAT-19, um die Rate ueberhaupt zu messen.
            warnings.warn(
                f"XPLAT-17/19: Szene kam nicht hoch, EIN Neuversuch "
                f"(wie VIZ-SCENE-SELFHEAL). Diagnose: {diagnose}",
                RuntimeWarning, stacklevel=2)
            _pump(1.0)
            self._load_and_wait(_zweiter_versuch=True)

    def _eval(self, js):
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
                   + json.dumps(js) + ")]);}"
                   "catch(e){return JSON.stringify(['err',String(e)]);}})()")
        box = []
        self._view.page().runJavaScript(_huelle, lambda result: box.append(result))
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(box, f"runJavaScript-Callback nie ausgeloest fuer: {js}")
        self.assertTrue(box[0], f"runJavaScript lieferte nichts fuer: {js}")
        art, wert = json.loads(box[0])
        self.assertNotEqual(art, "err", f"JS warf bei '{js}': {wert}")
        return wert

    def _poll_until_true(self, js, timeout_s=_POLL_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            last = self._eval(js)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout bei '{js}' (letzter: {last!r})")

    # ── XPLAT-19: Diagnose, wenn die Szene nicht hochkommt ───────────────────
    # Bisher meldete der Fehlschlag nur „Timeout bei '!!window.__lightosAppReady'
    # (letzter: False)" — also genau null Information darueber, WORAN es lag.
    # `__lightosSceneError` haelt den ersten Fehler des Szenen-Starts fest
    # (stage_scene.html, VIZ-SCENE-SELFHEAL) und wird von der Produktseite
    # laengst gelesen (visualizer_window.py) — von den Tests bis jetzt nicht.
    _DIAG_JS = ("JSON.stringify({"
                "err: String(window.__lightosSceneError || ''),"
                "ready: !!window.__lightosAppReady,"
                "three: typeof window.THREE,"
                "api: typeof window.__lightos,"
                "chan: !!(window.qt && window.qt.webChannelTransport),"
                "canvas: document.getElementsByTagName('canvas').length,"
                "doc: document.readyState})")

    def _szenen_diagnose(self, timeout_s=2.0):
        """Sieben Felder, die den Abbruch verorten: `three: "undefined"` heisst,
        schon `three_local.js` kam nicht · `three` da und `api: "undefined"`
        heisst, die ESM-Kette brach ab (typisch beim WebGLRenderer-Bau) ·
        `canvas: 0` heisst, der Renderer haengte sein Canvas nie ein · `err`
        traegt die echte Fehlerzeile.

        Bewusst NICHT ueber `self._eval`: das assertet bei Zeitueberschreitung
        und wuerde die eigentliche Fehlermeldung durch seine eigene ersetzen.
        Und bewusst ohne `getContext` — das waere genau die Ressource, die hier
        unter Verdacht steht.
        """
        box = []
        try:
            self._view.page().runJavaScript(self._DIAG_JS, box.append)
            ende = time.monotonic() + timeout_s
            while not box and time.monotonic() < ende:
                _app.processEvents()
                time.sleep(_POLL_INTERVAL_S)
        except Exception as e:              # Page/View schon tot
            return f"nicht lesbar: {e!r}"
        return box[0] if box else "kein Rueckruf (Renderer-Prozess tot?)"

    def _geist(self):
        return json.loads(self._eval("JSON.stringify(window.__lightos.placeGhostInfo())"))

    def _hover(self, x, y):
        """Zeiger bewegen — ueber den ECHTEN Hover-Pfad (globaler mousemove)."""
        self._eval(
            f"window.dispatchEvent(new MouseEvent('mousemove', "
            f"{{clientX: {x}, clientY: {y}, bubbles: true}})); true")
        _pump(0.2)

    # ── Drag-Ereignisse wie sie aus Qt kommen ────────────────────────────────

    def _drag(self, art, x, y, nutzlast="lightos-fixture:7"):
        """Echtes DragEvent mit DataTransfer — so kommt es aus der QWebEngine."""
        self._eval(
            "(() => {"
            "  const dt = new DataTransfer();"
            f"  dt.setData('text/plain', {nutzlast!r});"
            f"  const e = new DragEvent({art!r}, {{clientX: {x}, clientY: {y},"
            "     bubbles: true, cancelable: true, dataTransfer: dt});"
            "  window.dispatchEvent(e);"
            "  return true;"
            "})()")
        _pump(0.15)

    def _geist(self):
        return json.loads(self._eval("JSON.stringify(window.__lightos.placeGhostInfo())"))

    def _platziert(self):
        return [json.loads(j) for j in getattr(self._bridge_obj, "_placed", [])]

    def test_geist_folgt_dem_drag_und_der_drop_platziert_dieses_geraet(self):
        # Bewusst OHNE offene Platzierung (setUp setzt 0): wer ein bereits
        # platziertes Geraet zieht, verschiebt es — auch dafuer muss der Geist
        # erscheinen.
        self._drag("dragover", 360, 300)
        g1 = self._geist()
        self.assertTrue(g1["sichtbar"], "der Geist muss dem Drag folgen")

        self._drag("dragover", 520, 380)
        g2 = self._geist()
        self.assertNotEqual((round(g1["x"], 2), round(g1["z"], 2)),
                            (round(g2["x"], 2), round(g2["z"], 2)),
                            "der Geist folgt dem Drag nicht")

        self._drag("drop", 520, 380)
        self.assertFalse(self._geist()["sichtbar"],
                         "nach dem Drop verschwindet der Geist")

        rufe = self._platziert()
        self.assertEqual(len(rufe), 1, f"genau ein placeFixture erwartet: {rufe}")
        self.assertEqual(rufe[0]["fid"], 7,
                         "es muss das GEZOGENE Geraet sein, nicht das naechste offene")
        self.assertAlmostEqual(rufe[0]["x"], g2["x"], places=2)
        self.assertAlmostEqual(rufe[0]["z"], g2["z"], places=2)

    def test_im_ansehen_modus_wird_nicht_abgelegt(self):
        """Kein stiller Drop: ausserhalb des Bauen-Modus wird der Drag NICHT
        angenommen (kein preventDefault) — der Zeiger sagt dann von selbst, dass
        hier nichts abzulegen ist."""
        self._eval("window.__lightos.setEditMode('view'); true")
        self.assertFalse(self._eval("window.__lightos.dragDropAllowed()"))

        self._drag("dragover", 400, 320)
        self.assertFalse(self._geist()["sichtbar"])

        self._drag("drop", 400, 320)
        self.assertEqual(self._platziert(), [],
                         "im Ansehen-Modus darf nichts platziert werden")

        # Positiv-Kontrolle: dieselbe Geste im Bauen-Modus platziert sehr wohl.
        # Ohne sie waere der Test auch bei toter Drag-Kette gruen.
        self._eval("window.__lightos.setEditMode('edit'); true")
        self._drag("dragover", 400, 320)
        self._drag("drop", 400, 320)
        self.assertEqual([r["fid"] for r in self._platziert()], [7])

    def test_fremder_text_platziert_nichts(self):
        """Wer beliebigen Text ins Fenster zieht, darf kein Geraet setzen."""
        self._drag("dragover", 400, 320, nutzlast="irgendein Text")
        self._drag("drop", 400, 320, nutzlast="irgendein Text")
        self.assertEqual(self._platziert(), [])

        # Positiv-Kontrolle IM SELBEN Test: ohne sie bestuende er auch dann,
        # wenn die Drag-Ereignisse gar nicht ankommen — und bewiese nichts
        # ueber die Nutzlast-Pruefung (Fallenklasse CDX-18).
        self._drag("dragover", 400, 320)
        self._drag("drop", 400, 320)
        self.assertEqual([r["fid"] for r in self._platziert()], [7],
                         "mit gueltiger Nutzlast MUSS platziert werden")


if __name__ == "__main__":
    unittest.main()
