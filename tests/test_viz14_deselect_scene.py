"""VIZ-14: ein leer gezogenes Marquee im 3D waehlt jetzt WIRKLICH ab.

Slice 1a nahm eine Asymmetrie bewusst in Kauf: ein leeres 3D-Marquee raeumte
die Outlines, liess die globale/Programmer-Auswahl aber stehen — beide liefen
erst bei der naechsten NEUEN Auswahl wieder zusammen.

★ Der Grund war gut: ``fixtureSelectionChanged("[]")`` feuert auch OHNE Zutun
des Nutzers (Moduswechsel, Fixture-Entfernen, View-Wechsel). Wer das
durchreicht, wischt mit einem blossen 3D-Moduswechsel die Programmer-Auswahl
weg. Die Loesung ist deshalb NICHT, den Guard zu entfernen, sondern den
User-Intent von spuriosen Leer-Emits zu trennen: ein eigener Kanal
(``fixtureSelectionCleared``), den nur das leer gezogene Marquee benutzt.

Gemessen wird ueber den ECHTEN Zeigerpfad (handlePointerDown/Move/Up), nicht
ueber eine nachgerechnete Formel — der Intent entsteht genau dort.

Belegt: (1) leeres Marquee meldet das Deselect, (2) ein Marquee MIT Treffern
meldet es nicht (dort greift der normale Auswahl-Kanal), (3) mit Shift wird
nichts gemeldet (Shift ist additiv, kein Deselect), (4) war vorher schon nichts
ausgewaehlt, wird auch nichts gemeldet (kein Rauschen).
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
    def fixtureSelectionChanged(self, j):
        self._selections = getattr(self, "_selections", []) + [j]

    attrs["fixtureSelectionChanged"] = fixtureSelectionChanged

    @Slot()
    def fixtureSelectionCleared(self):
        self._cleared = getattr(self, "_cleared", 0) + 1

    attrs["fixtureSelectionCleared"] = fixtureSelectionCleared
    attrs["requestFullResync"] = Signal()
    return type("MockVisualizerBridge", (QObject,), attrs)


_MockVisualizerBridge = _make_mock_bridge_class()


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


class DeselectSceneTest(unittest.TestCase):
    def setUp(self):
        self._view = QWebEngineView()
        try:
            profile = self._view.page().profile()
            profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
        except Exception:
            pass
        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self._bridge_obj = _MockVisualizerBridge()
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._bridge_obj)
        self._view.page().setWebChannel(self._channel)
        self._view.resize(800, 600)
        # Ohne echtes Layout liefert getBoundingClientRect() 0x0 -> die
        # A3D-41-NaN-Waechter im Zeigerpfad verwerfen den Aufruf, und der Test
        # misst nichts. show() reicht auch unter QT_QPA_PLATFORM=offscreen.
        self._view.show()
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
        self.assertTrue(self._loaded_ok and self._loaded_ok[-1], "Page nicht geladen")
        self._poll_until_true("!!window.__lightosAppReady")
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while time.monotonic() < deadline:
            if getattr(self._bridge_obj, "_request_fixtures_calls", 0) > 0:
                return
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.fail("JS hat den WebChannel nicht verdrahtet")

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
        self.fail(f"Timeout bei '{js_expr}' (letzter: {last!r})")

    def _marquee(self, x1, y1, x2, y2, shift=False):
        """Echter Zeigerpfad: Down -> Move -> Up (Marquee braucht Edit-Modus)."""
        self._eval(
            f"window.__lightos.__handlePointerDown({x1}, {y1}, {str(shift).lower()});"
            f"window.__lightos.__handlePointerMove({x2}, {y2}, false);"
            f"window.__lightos.__handlePointerUp({str(shift).lower()}); true")
        _pump(0.3)

    def test_leeres_marquee_waehlt_wirklich_ab(self):
        self._load_and_wait()
        self._eval("window.__lightos.setEditMode('edit'); true")
        self._bridge_obj.fixtureAdded.emit(json.dumps({
            "fid": 1, "label": "P1", "type": "par", "model": "par", "nHeads": 0,
            "x": 0, "y": 3, "z": 0, "rotX": 0, "rotY": 0, "rotZ": 0}))
        self._poll_until_true("Object.keys(window.__lightos.fixtures).length === 1")

        # (4) nichts ausgewaehlt -> leeres Marquee meldet NICHTS (kein Rauschen)
        self._eval("window.__lightos.view.selectedFids = []; true")
        self._marquee(700, 500, 780, 560)
        self.assertEqual(getattr(self._bridge_obj, "_cleared", 0), 0,
                         "ohne vorherige Auswahl gibt es nichts abzuwaehlen")

        # (1) etwas ausgewaehlt + leer gezogen -> Deselect wird gemeldet
        self._eval("window.__lightos.view.selectedFids = [1]; true")
        self._marquee(700, 500, 780, 560)
        self.assertEqual(getattr(self._bridge_obj, "_cleared", 0), 1,
                         "ein leer gezogenes Marquee ist ein ausdrueckliches "
                         "Abwaehlen und muss gemeldet werden")

        # (3) mit Shift wird NICHTS gemeldet — Shift ist additiv
        self._eval("window.__lightos.view.selectedFids = [1]; true")
        self._marquee(700, 500, 780, 560, shift=True)
        self.assertEqual(getattr(self._bridge_obj, "_cleared", 0), 1,
                         "Shift addiert zur Auswahl, es waehlt nicht ab")

        # (2) Marquee MIT Treffer meldet kein Deselect (normaler Auswahl-Kanal)
        #
        # ★ QA-VIZ-TESTS (2026-08-05): zweites Geraet dazu, und die
        # Auswahl-Meldungen werden VORHER zurueckgesetzt. Bis hierhin stuetzte
        # sich die einzige Positivkontrolle dieses Tests auf
        # `assertTrue(_selections)` — und die Liste war durch den Initial-Load
        # und die drei vorangegangenen LEEREN Marquees laengst gefuellt
        # (updateOutlines meldet bedingungslos). Waere die Treffer-Auswahl
        # komplett ausgefallen, waere der Test gruen geblieben. Jetzt zaehlt der
        # INHALT einer frischen Meldung: "[1,2]" kann nur aus der
        # Treffer-Berechnung des Marquees stammen — Geraet 2 war vorher NICHT
        # ausgewaehlt, es muss also im Rechteck gefunden worden sein.
        self._bridge_obj.fixtureAdded.emit(json.dumps({
            "fid": 2, "label": "P2", "type": "par", "model": "par", "nHeads": 0,
            "x": 3, "y": 3, "z": 0, "rotX": 0, "rotY": 0, "rotZ": 0}))
        self._poll_until_true("Object.keys(window.__lightos.fixtures).length === 2")
        self._eval("window.__lightos.view.selectedFids = [1]; true")
        self._bridge_obj._selections = []
        self._marquee(0, 0, 800, 600)
        self.assertEqual(getattr(self._bridge_obj, "_cleared", 0), 1,
                         "ein Marquee mit Treffern ist kein Deselect")
        frisch = list(getattr(self._bridge_obj, "_selections", []))
        self.assertIn("[1,2]", frisch,
                      "das Marquee hat die getroffenen Geraete nicht gemeldet — "
                      f"die Treffer-Auswahl laeuft nicht (Meldungen: {frisch!r})")
        self.assertEqual(
            self._eval("JSON.stringify(window.__lightos.view.selectedFids)"), "[1,2]",
            "die Szene selbst haelt nach dem Treffer-Marquee nicht beide Geraete")


if __name__ == "__main__":
    unittest.main()
