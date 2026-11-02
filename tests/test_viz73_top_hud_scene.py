"""VIZ-73: Bauen-Modus, Reiter Fixtures — Werkzeugleiste ("Bewegen · Zielen ·
Nachfahren"), Modus-Banner ("BEWEGEN – …"), Trace-Einstellungen und die Pille
"Selektion: FIXTURE x1" duerfen sich oben mittig nicht ueberdecken.

Vorher sassen alle vier absolut oben mittig (top 8/10/42/66 px) — die Leiste lag
mitten auf dem Banner-Text. Jetzt stapelt #top-hud sie untereinander.

Beleg in einer ECHTEN QWebEngine: die Bounding-Boxes der sichtbaren Elemente
(getBoundingClientRect per runJavaScript) schneiden sich bei 1800x950, 1280x800,
1024x700 und schmalen Sichtbereichen bis 640x480, in 3D und 2D, fuer jedes
Werkzeug paarweise nicht, liegen ganz im Sichtbereich,
der Banner-Text ist nicht abgeschnitten, und auch die Ecken-Elemente (#overlay
oben links, Modus-Chip oben rechts) werden nicht ueberdeckt.
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



# Die 3D-Ansicht ist nur ein Teil des App-Fensters (rechte Spalte 330-420 px,
# links die Bibliothek): bei 1280 px Fensterbreite bleiben oft unter 900 px
# Sichtbereich. Deshalb auch schmale Sichtbereiche — 901/800/640 decken beide
# Seiten der 900-px-Grenze (@media in stage_scene.html) ab.
_FENSTER = [(1800, 950), (1280, 800), (1024, 700), (901, 600), (800, 600), (640, 480)]
_ANSICHTEN = ["3D", "2D"]   # 2D: #overlay ist breiter ("... | 2D Top View")
_WERKZEUGE = ["move_xz", "aim", "trace"]

_JS_BOXEN = r"""(function(){
  function box(id){
    var e = document.getElementById(id);
    if (!e) return null;
    var cs = getComputedStyle(e);
    if (cs.display === 'none' || cs.visibility === 'hidden') return null;
    var r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return null;
    return {id:id, l:r.left, t:r.top, r:r.right, b:r.bottom,
            sw:e.scrollWidth, cw:e.clientWidth, sh:e.scrollHeight, ch:e.clientHeight};
  }
  var ids = ['edit-toolbar','trace-panel','mode-banner','selection-banner',
             'overlay','mode-frame-chip'];
  var out = [];
  for (var i = 0; i < ids.length; i++) { var b = box(ids[i]); if (b) out.push(b); }
  return JSON.stringify({w: window.innerWidth, h: window.innerHeight, boxen: out});
})()"""


def _schneiden(a, b):
    return a["l"] < b["r"] and b["l"] < a["r"] and a["t"] < b["b"] and b["t"] < a["b"]


class TopHudUeberlappungTest(unittest.TestCase):
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
        # Echtes Layout VOR dem Laden (wie test_viz14_place_ghost_scene.py):
        # ohne show() liefert getBoundingClientRect() kein brauchbares Mass.
        self._view.resize(*_FENSTER[0])
        self._view.show()
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


    def _fenster(self, w, h):
        self._view.resize(w, h)
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while time.monotonic() < deadline:
            _app.processEvents()
            if self._eval("window.innerWidth") == w and self._eval("window.innerHeight") == h:
                return
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Sichtbereich wurde nicht {w}x{h}: "
                  f"{self._eval('window.innerWidth')}x{self._eval('window.innerHeight')}")

    def _pruefe(self, w, h, werkzeug):
        self._eval(f"window.setEditTool('{werkzeug}'); true")
        _pump(0.1)
        daten = json.loads(self._eval(_JS_BOXEN))
        boxen = {b["id"]: b for b in daten["boxen"]}
        ort = f"{w}x{h}, Werkzeug {werkzeug}"
        erwartet = {"edit-toolbar", "mode-banner", "selection-banner"}
        if werkzeug == "trace":
            erwartet.add("trace-panel")
        fehlend = erwartet - set(boxen)
        self.assertFalse(fehlend, f"{ort}: nicht sichtbar: {sorted(fehlend)}")
        hud = [boxen[i] for i in ("edit-toolbar", "trace-panel", "mode-banner",
                                  "selection-banner") if i in boxen]
        alle = list(boxen.values())
        for i, a in enumerate(hud):
            # ganz im Sichtbereich
            self.assertGreaterEqual(a["l"], 0, f"{ort}: {a['id']} links abgeschnitten {a}")
            self.assertLessEqual(a["r"], daten["w"], f"{ort}: {a['id']} rechts abgeschnitten {a}")
            self.assertGreaterEqual(a["t"], 0, f"{ort}: {a['id']} oben abgeschnitten {a}")
            # Inhalt nicht abgeschnitten (vollstaendig lesbar)
            self.assertLessEqual(a["sw"], a["cw"] + 1, f"{ort}: {a['id']} Inhalt zu breit {a}")
            self.assertLessEqual(a["sh"], a["ch"] + 1, f"{ort}: {a['id']} Inhalt zu hoch {a}")
            for b in alle:
                if b is a:
                    continue
                self.assertFalse(_schneiden(a, b),
                                 f"{ort}: {a['id']} ueberdeckt {b['id']}: {a} / {b}")

    def test_bauen_banner_und_leiste_ueberlappen_nicht(self):
        self._load_and_wait()
        self._poll_until_true("!!window.__lightosAppReady")
        self._bridge_obj._poll_payload = '{"editMode": "edit"}'
        self._poll_until_true(
            "document.getElementById('mode-frame').dataset.mode === 'build'", timeout_s=8.0)
        # Auswahl ueber den echten Poll-Pfad -> Pille "Selektion: FIXTURE x1"
        self._bridge_obj._poll_payload = '{"editMode": "edit", "selection": "[1]"}'
        self._poll_until_true(
            "getComputedStyle(document.getElementById('selection-banner')).display !== 'none'",
            timeout_s=8.0)
        self.assertIn("FIXTURE x1", self._eval(
            "document.getElementById('selection-banner').textContent"))
        for ansicht in _ANSICHTEN:
            self._eval(f"window.__lightos.setViewMode('{ansicht}'); true")
            self.assertIn(ansicht, self._eval(
                "document.getElementById('mode-text').textContent"))
            for w, h in _FENSTER:
                self._fenster(w, h)
                for werkzeug in _WERKZEUGE:
                    with self.subTest(ansicht=ansicht, fenster=f"{w}x{h}", werkzeug=werkzeug):
                        self._pruefe(w, h, werkzeug)
        self._eval("window.__lightos.setViewMode('3D'); true")

        # Gegenprobe Reiter Buehne (gleiche Ladung — eine zweite WebGL-Vollladung
        # im selben Prozess bekam hier offscreen keinen WebGL-Kontext mehr):
        # ohne Werkzeugleiste rutscht das Banner nach oben und bleibt frei.
        self._eval("window.__lightos.setEditMode('stage'); true")
        _pump(0.1)
        for w, h in _FENSTER:
            self._fenster(w, h)
            boxen = {x["id"]: x for x in json.loads(self._eval(_JS_BOXEN))["boxen"]}
            self.assertNotIn("edit-toolbar", boxen)
            self.assertIn("mode-banner", boxen)
            for x in boxen.values():
                if x["id"] != "mode-banner":
                    self.assertFalse(_schneiden(boxen["mode-banner"], x),
                                     f"{w}x{h} Buehne: mode-banner ueberdeckt {x['id']}")
            self.assertLessEqual(boxen["mode-banner"]["r"], w)
            self.assertGreaterEqual(boxen["mode-banner"]["l"], 0)

if __name__ == "__main__":
    unittest.main()
