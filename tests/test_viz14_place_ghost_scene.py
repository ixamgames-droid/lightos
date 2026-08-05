"""VIZ-14: der Platzier-Geist — End-to-End in einer ECHTEN QWebEngine.

Platzieren war blind: Rechtsklick in die Szene setzt das naechste noch
unplatzierte Geraet an diese Stelle — man sah WEDER wo es landet, NOCH ob es an
einer Traverse haengen wird, NOCH ueberhaupt, dass gerade etwas zu platzieren
ist. Der Geist zeigt alle drei Dinge, bevor geklickt wird (Plan §3
„Drag&Drop + Ghost-Preview, Auto-Hang auf Truss" — das Ghost-Stueck).

Belegt: (1) ohne offene Platzierung KEIN Geist (er darf nicht im Weg stehen,
wenn es nichts zu platzieren gibt), (2) mit offener Platzierung folgt er dem
Zeiger im Bau-Modus, (3) im Ansehen-Modus bleibt er weg (dort platziert man
nicht), (4) er faengt keine Eingabe — sonst schluckte ausgerechnet die Vorschau
den Klick, der platzieren soll.
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


class PlaceGhostSceneTest(unittest.TestCase):
    def setUp(self):
        self._view = QWebEngineView()
        try:
            self._view.page().profile().setHttpCacheType(
                QWebEngineProfile.HttpCacheType.NoCache)
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
        # Ohne echtes Layout liefert getBoundingClientRect() 0x0 und die
        # A3D-41-NaN-Waechter verwerfen jede Zeiger-Eingabe still (Lehre aus
        # dem Deselect-Test: der war zweimal rot, ohne dass Code fehlte).
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
        try:
            self._poll_until_true("!!window.__lightosAppReady")
        except AssertionError as e:                      # XPLAT-19
            raise AssertionError(
                f"{e} | Szenen-Diagnose: {self._szenen_diagnose()}") from None

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

    def _zurueck_auf_den_schirm(self, x, z):
        """Den Boden-Punkt (x, 0, z) mit der Kamera der Szene zurueck auf den
        Bildschirm rechnen — Gegenrichtung von `intersectGround()`.

        ★ QA-VIZ-TESTS (2026-08-05): der Test belegte bisher nur, dass der Geist
        sich BEWEGT. Eine vertauschte oder gespiegelte Achse haette er bestanden,
        obwohl der Geist dann irgendwo anders stuende als der Zeiger — und genau
        das ist die Zusicherung („folgt dem Zeiger"). Der Rueckweg prueft sie
        ohne jede Annahme ueber die Kamerastellung: die Kamera steht schraeg,
        Bildschirm-X und Welt-X sind NICHT dieselbe Achse.
        Vector3 kommt ueber `.clone()` einer vorhandenen Position — das
        THREE-Modul selbst ist nicht global.
        """
        roh = self._eval(
            "JSON.stringify((function(){"
            " var cam = window.__lightos.view.activeCam;"
            f" var p = cam.position.clone().set({x}, 0, {z}).project(cam);"
            " var r = document.querySelector('canvas').getBoundingClientRect();"
            " return [((p.x + 1) / 2) * r.width + r.left,"
            "         ((1 - p.y) / 2) * r.height + r.top];})())")
        return json.loads(roh)

    def test_geist_folgt_dem_zeiger_nur_wenn_es_etwas_zu_platzieren_gibt(self):
        self._load_and_wait()
        self._eval("window.__lightos.setEditMode('edit'); true")

        # (1) nichts offen -> kein Geist
        self._hover(400, 320)
        self.assertFalse(self._geist()["sichtbar"],
                         "ohne offene Platzierung darf kein Geist im Weg stehen")

        # (2) etwas offen -> Geist folgt dem Zeiger
        self._eval("window.__lightos.setPlaceableCount(2); true")
        self._hover(360, 300)
        g1 = self._geist()
        self.assertTrue(g1["sichtbar"], "mit offener Platzierung fehlt der Geist")
        self._hover(520, 380)
        g2 = self._geist()
        self.assertTrue(g2["sichtbar"])
        self.assertNotEqual((round(g1["x"], 2), round(g1["z"], 2)),
                            (round(g2["x"], 2), round(g2["z"], 2)),
                            "der Geist folgt dem Zeiger nicht")

        # ★ und er steht WO der Zeiger hinzeigt, nicht bloss irgendwo anders:
        # den Bodenpunkt des Geistes zurueck auf den Schirm rechnen und mit der
        # Zeigerposition vergleichen. Das Raster (settings.gridStep, 1 m) rundet
        # den Punkt — bei rund 20 px je Meter sind das bis zu ~10 px; 60 px
        # Toleranz laesst das durch und faengt eine vertauschte/gespiegelte
        # Achse trotzdem sicher (die liegt hunderte Pixel daneben).
        for (px, py), g in (((360, 300), g1), ((520, 380), g2)):
            sx, sy = self._zurueck_auf_den_schirm(g["x"], g["z"])
            self.assertLess(
                ((sx - px) ** 2 + (sy - py) ** 2) ** 0.5, 60.0,
                f"der Geist steht nicht unter dem Zeiger: Zeiger ({px}, {py}), "
                f"Geist bei ({g['x']}, {g['z']}) = Schirm ({sx:.0f}, {sy:.0f})")

        # (4) er faengt keine Eingabe: ein Strahl von schraeg oben mitten
        # durch ihn darf ihn NICHT treffen — sonst schluckte ausgerechnet die
        # Vorschau den Klick, der platzieren soll. Gemessen, nicht behauptet.
        self.assertEqual(g2["raycastTreffer"], 0,
                         "der Geist faengt Strahlen ab und wuerde den "
                         "Platzier-Klick schlucken")

        # (3) Ansehen-Modus: kein Geist (dort platziert man nicht)
        self._eval("window.__lightos.setEditMode('view'); true")
        self._hover(400, 320)
        self.assertFalse(self._geist()["sichtbar"],
                         "im Ansehen-Modus hat der Geist nichts zu suchen")


if __name__ == "__main__":
    unittest.main()
