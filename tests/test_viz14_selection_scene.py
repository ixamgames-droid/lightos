"""VIZ-14 (Slice 1b): globale/Programmer-Auswahl -> 3D-Outlines, End-to-End in
einer ECHTEN QWebEngine.

Belegt den vollen Rueckrichtungs-Weg, den ein reiner Python-Test NICHT fangen
kann: Python legt die Auswahl in den pollControl-Zustand (``{"selection": ...}``)
-> bridge.js#pollControl-Callback (idempotenter ``_pSel``-Guard) ->
``jsApplyExternalSelection`` (tools.js) -> ``view.selectedFids`` + Outlines OHNE
Echo an Python.

BEWUSST eigene, schlanke Datei (nicht an test_viz13_scene_modules_smoke.py
angehaengt): jede QWebEngine-Ladung stresst den offscreen-Chromium-Renderer;
die Isolate-Gate faehrt pro Datei einen eigenen Prozess, so bleibt diese Ladung
von der ohnehin schweren Smoke-Suite entkoppelt.

Mock-Bridge wie in der Produktiv-Bridge (alle in bridge.js#tryChannel
verbundenen Signale + pollControl-Slot). Zusaetzlich ein aufzeichnender
``fixtureSelectionChanged``-Slot (JS->Python-Echo), damit der Test belegt, dass
die extern gepushte Auswahl NICHT zurueckechot (Loop-Brecher updateOutlines(false)).
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

# Signale, die bridge.js#tryChannel() connectet (1:1 zur echten VisualizerBridge,
# Slots <- JS werden separat als Slot gebaut). selectFixtures ist NICHT dabei:
# es wird per Poll konsumiert (nicht via signal.connect), die Mock-Bridge braucht
# es daher nicht.
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

    # Echo-Slot wie in der echten Bridge — zeichnet auf, damit der Test belegen
    # kann, dass die von Python gepushte Auswahl NICHT zurueckechot.
    @Slot(str)
    def fixtureSelectionChanged(self, fids_json):
        self._fixture_selection_calls = getattr(self, "_fixture_selection_calls", [])
        self._fixture_selection_calls.append(fids_json)

    attrs["fixtureSelectionChanged"] = fixtureSelectionChanged
    attrs["requestFullResync"] = Signal()
    return type("MockVisualizerBridge", (QObject,), attrs)


_MockVisualizerBridge = _make_mock_bridge_class()

# ★ QA-VIZ-TESTS (2026-08-05): DREI Geraete auf der Buehne, zwei davon in der
# Auswahl. Bis hierhin lief diese Datei auf einer LEEREN Buehne — die Datei
# enthielt keine einzige Referenz auf `__lightos.fixtures`, die Outline-Schleife
# (tools.js#updateOutlines) lief also null Mal, und man konnte den kompletten
# Code, der den Auswahl-Ring baut, loeschen, ohne einen dieser Tests rot zu
# bekommen. `view.selectedFids` zu setzen ist der halbe Weg; der Beleg ist erst
# der RING am Geraet. fid 7 ist die Gegenprobe: unselektiert muss er dunkel
# bleiben, sonst wuerde ein "alle Ringe an" ebenfalls bestehen.
# Poll-"fixtures" ist ein JSON-STRING (bridge.js JSON.parse't ihn).
_FIXTURES = [
    {"fid": 2, "type": "par", "x": -3, "y": 3, "z": 0, "label": "L"},
    {"fid": 4, "type": "par", "x": 0, "y": 3, "z": 0, "label": "M"},
    {"fid": 7, "type": "par", "x": 3, "y": 3, "z": 0, "label": "R"},
]
_FIXTURES_JSON = json.dumps(_FIXTURES)
# Beide Poll-Zustaende tragen DIESELBE fixtures-Zeichenkette: bridge.js wendet
# sie nur bei Aenderung an (_pFix-Guard), der zweite Zustand baut die Geraete
# also nicht neu, er legt nur die Auswahl dazu.
_POLL_FIXTURES = json.dumps({"fixtures": _FIXTURES_JSON})
_POLL_FIXTURES_UND_AUSWAHL = json.dumps(
    {"fixtures": _FIXTURES_JSON, "selection": "[2, 4]"})

# tools.js: Basis-Deckkraft der beiden Auswahl-Ringe (der Identify-Puls
# moduliert sie mit k in [0.25, 1.0] — deshalb wird auf > 0 geprueft, nicht auf
# Gleichheit, ausser nach dem Settle).
_SELBORDER_BASIS = 0.85
_ICON_RING_BASIS = 1.0


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


class ExternalSelectionSceneTest(unittest.TestCase):
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

    def _stats(self):
        return json.loads(self._eval("JSON.stringify(window.__lightos.renderStats())"))

    def _geraete_aufbauen(self):
        """Drei Geraete ueber den Poll-Resync-Pfad auf die Buehne stellen.
        Ohne sie misst diese Datei die Auswahl-Optik an einer leeren Szene."""
        self._bridge_obj._poll_payload = _POLL_FIXTURES
        self._poll_until_true(
            "Object.keys(window.__lightos.fixtures).length === 3", timeout_s=8.0)

    def _ringe(self):
        """Der SICHTBARE Auswahl-Zustand je Geraet, direkt am Material gelesen:
        {fid: (Deckkraft des 2D-Icon-Rings, Deckkraft des 3D-Rings oder None)}.
        `_selBorder` entsteht ueberhaupt nur in der Outline-Schleife — fehlt er,
        hat der Auswahl-Code nicht gearbeitet."""
        roh = self._eval(
            "JSON.stringify(Object.keys(window.__lightos.fixtures).map(function(k){"
            " var f = window.__lightos.fixtures[k];"
            " var r = f.icon && f.icon.userData && f.icon.userData.ring;"
            " var b = f._selBorder;"
            " return [Number(k), r ? r.material.opacity : null,"
            "         (b && b.visible) ? b.material.opacity : null]; }))")
        return {fid: (ring, rand) for fid, ring, rand in json.loads(roh)}

    def _tick(self):
        # Einen Loop-Tick deterministisch ausfuehren (rAF-unabhaengig; offscreen
        # drosselt rAF, s. render_loop.js) — identischer Tick-Body wie der rAF-Loop.
        self._eval("window.__lightos.__renderTick(); true")

    def _settle(self, max_rounds=30):
        """Tickt bis das Dirty-Gate zu ist und der Zaehler ruht (konsumiert
        Init-/Auswahl-Dirty). Scheitert, wenn der Loop nicht in Idle faellt."""
        last = None
        for _ in range(max_rounds):
            self._tick()
            s = self._stats()
            if (not s["dirty"]) and (not s["live"]) and s["count"] == last:
                return s
            last = s["count"]
        self.fail(f"Render-Loop stabilisiert nicht: {self._stats()}")

    def test_external_selection_applies_to_scene_without_echo(self):
        self._load_and_wait()
        self._poll_until_true("!!window.__lightosAppReady")
        # view (u.a. selectedFids) ist als Test/Debug-Hook exponiert (app.js).
        self.assertEqual(
            self._eval("Array.isArray(window.__lightos.view.selectedFids)"), True,
            "window.__lightos.view.selectedFids nicht als Array exponiert")

        # ★ Geraete AUF die Buehne, bevor die Auswahl gemessen wird.
        self._geraete_aufbauen()
        vorher = self._ringe()
        for fid in (2, 4, 7):
            self.assertEqual(vorher[fid][0], 0.0,
                             f"Geraet {fid} traegt vor der Auswahl schon einen Ring")
            self.assertIsNone(vorher[fid][1],
                              f"Geraet {fid} hat vor der Auswahl schon einen 3D-Rand")

        # Basislinie der Echo-Aufrufe (Initial-Load kann updateOutlines(true) mit
        # leerer Auswahl ausloesen -> "[]"; KEIN Echo unserer Auswahl).
        baseline = list(getattr(self._bridge_obj, "_fixture_selection_calls", []))

        # Python pusht die Auswahl in den Poll-Zustand; der JS-Poll (130ms) zieht
        # sie und wendet sie an.
        self._bridge_obj._poll_payload = _POLL_FIXTURES_UND_AUSWAHL
        applied = self._poll_until_true(
            "JSON.stringify(window.__lightos.view.selectedFids) === '[2,4]'")
        self.assertTrue(applied, "gepushte Auswahl [2,4] nicht in der 3D-Szene angekommen")

        # ★ Und jetzt der eigentliche Beleg: die Geraete SEHEN auch ausgewaehlt
        # aus. Ohne diesen Block bestand der Test auch dann, wenn die komplette
        # Outline-Schleife fehlte.
        nachher = self._ringe()
        for fid in (2, 4):
            self.assertIsNotNone(
                nachher[fid][1],
                f"Geraet {fid} ist ausgewaehlt, hat aber keinen sichtbaren "
                f"3D-Auswahl-Ring — die Outline-Schleife hat nicht gearbeitet")
            self.assertGreater(
                nachher[fid][1], 0.0,
                f"der 3D-Auswahl-Ring an Geraet {fid} ist voellig durchsichtig")
            self.assertLessEqual(nachher[fid][1], _SELBORDER_BASIS + 1e-6)
            self.assertGreater(
                nachher[fid][0], 0.0,
                f"der 2D-Icon-Ring an Geraet {fid} blieb dunkel")
            self.assertLessEqual(nachher[fid][0], _ICON_RING_BASIS + 1e-6)
        # Gegenprobe: das NICHT gewaehlte Geraet bleibt unmarkiert — sonst
        # bestuende der Test auch bei "alle Ringe an".
        self.assertEqual(nachher[7][0], 0.0,
                         "das nicht gewaehlte Geraet 7 traegt einen Icon-Ring")
        self.assertIsNone(nachher[7][1],
                          "das nicht gewaehlte Geraet 7 traegt einen 3D-Auswahl-Ring")

        # Echo-Guard: die extern angewandte Auswahl darf NICHT zurueckgemeldet
        # worden sein (sonst Loop). Neue Calls seit der Basislinie ohne [2,4].
        _pump(0.4)
        new_calls = list(getattr(self._bridge_obj, "_fixture_selection_calls", []))[len(baseline):]
        self.assertNotIn(
            "[2,4]", new_calls,
            f"Auswahl echot via fixtureSelectionChanged zurueck (Loop-Gefahr): {new_calls!r}")

        # Idempotenz-Beleg: erneutes, gleiches Payload loest KEINEN weiteren
        # Apply/Echo aus (bridge.js _pSel-Guard).
        before = len(list(getattr(self._bridge_obj, "_fixture_selection_calls", [])))
        _pump(0.4)
        after = len(list(getattr(self._bridge_obj, "_fixture_selection_calls", [])))
        self.assertEqual(before, after, "unveraenderte Auswahl loeste weitere Echo-Calls aus (nicht idempotent)")

    def test_identify_pulse_decays_to_idle_despite_persistent_selection(self):
        """VIZ-14 (Slice 1c): Identify-Decay-Flash. Eine Auswahl-Aenderung laesst die
        Ringe kurz pulsieren (Live-Probe haelt den On-Demand-Loop am Rendern) und
        faellt danach in Idle zurueck — OBWOHL die Auswahl (seit 1b persistent)
        bestehen bleibt (F1: kein Dauer-rAF). Echo-frei (F2)."""
        self._load_and_wait()
        self._poll_until_true("!!window.__lightosAppReady")
        self._geraete_aufbauen()   # ★ ohne Geraete pulsiert nichts
        self._settle()   # Idle-Baseline vor der Auswahl

        # Auswahl pushen -> Identify-Flash startet -> Live-Probe aktiv.
        self._bridge_obj._poll_payload = _POLL_FIXTURES_UND_AUSWAHL
        self._poll_until_true("window.__lightos.renderStats().live === true", timeout_s=8.0)

        # Waehrend des Flash-Fensters rendert jeder Tick (Live-Probe haelt das Gate offen).
        c0 = self._stats()["count"]
        for _ in range(3):
            self._tick()
        self.assertGreater(
            self._stats()["count"], c0,
            "Identify-Flash rendert nicht — Live-Probe haelt das Dirty-Gate nicht offen")

        # ★ F1: Fenster ablaufen lassen (> SELECTION_PULSE_MS=1500ms) -> Idle.
        _pump(1.8)
        self._poll_until_true("window.__lightos.renderStats().live === false", timeout_s=8.0)
        # Die Auswahl bleibt bestehen — genau das macht den Decay-Beweis aus:
        self.assertEqual(
            self._eval("JSON.stringify(window.__lightos.view.selectedFids)"), "[2,4]",
            "Auswahl muss fuer den Decay-Beweis persistent bleiben")
        settled = self._settle()
        c1 = settled["count"]
        for _ in range(3):
            self._tick()
        self.assertEqual(
            self._stats()["count"], c1,
            "Loop rendert nach Ablauf des Flash-Fensters weiter (Dauer-rAF trotz statischer Auswahl)")

        # ★ F2: die extern gepushte Auswahl darf NICHT via fixtureSelectionChanged echon.
        calls = list(getattr(self._bridge_obj, "_fixture_selection_calls", []))
        self.assertNotIn("[2,4]", calls, f"Identify-Puls echot die Auswahl zurueck (Loop-Gefahr): {calls!r}")

    def test_identify_pulse_renders_settle_frame_on_expiry(self):
        """VIZ-14 (Slice 1c, Defect-#1-Guard): am Fenster-Ende muss der Reset auf
        Basis-Deckkraft GENAU EINMAL gerendert werden — sonst friert der Auswahl-
        Ring bei einer gedimmten Puls-Deckkraft ein (in statischer Szene rendert
        das Gate sonst nicht mehr). Deterministisch via Test-Seam
        __expireSelectionPulse (kein 1.5s-Echtzeit-Warten, kein rAF-Race)."""
        self._load_and_wait()
        self._poll_until_true("!!window.__lightosAppReady")
        self._geraete_aufbauen()   # ★ ohne Geraete gibt es keinen Ring zum Einfrieren
        self._settle()

        # Auswahl pushen -> Flash aktiv.
        self._bridge_obj._poll_payload = _POLL_FIXTURES_UND_AUSWAHL
        self._poll_until_true("window.__lightos.renderStats().live === true", timeout_s=8.0)
        # Einmal ticken, damit der Puls laeuft (_pulseDirty=true, Ringe verstellt).
        self._tick()
        self.assertTrue(self._stats()["live"], "Flash sollte noch aktiv sein")

        # ★ Der Puls moduliert die Ring-Deckkraft WIRKLICH. Ohne diese Messung
        # belegte der Test nur, dass gerendert wird — nicht, dass sich am Ring
        # etwas tut. Die Abtastungen liegen (Runde ueber den Qt-Loop) jeweils
        # >= 50 ms auseinander, bei ~3 Hz also weit ueber eine Sinus-Flanke.
        proben = []
        for _ in range(5):
            proben.append(self._ringe()[2][1])
            self._tick()
        self.assertNotIn(None, proben, "der 3D-Auswahl-Ring fehlt waehrend des Pulses")
        self.assertGreater(
            max(proben) - min(proben), 0.05,
            f"die Ring-Deckkraft steht waehrend des Identify-Pulses still: {proben}")

        # Fenster deterministisch beenden.
        self._eval("window.__lightos.__expireSelectionPulse(); true")
        self.assertFalse(self._stats()["live"], "Flash-Fenster nicht beendet")

        # ★ Der naechste Tick MUSS rendern (Settle-Frame) — sonst bliebe der Ring
        # bei der zuletzt gerenderten Puls-Deckkraft haengen (Defect #1).
        c_before = self._stats()["count"]
        self._tick()
        self.assertGreater(
            self._stats()["count"], c_before,
            "Settle-Frame wurde nicht gerendert — Auswahl-Ring friert gedimmt ein (Defect #1)")

        # ★ Und der Ring steht danach auf BASIS-Deckkraft, nicht auf irgendeinem
        # Puls-Zwischenwert. Genau das ist Defect #1 — der Render-Zaehler allein
        # konnte es nie zeigen.
        endstand = self._ringe()
        for fid in (2, 4):
            self.assertAlmostEqual(
                endstand[fid][1], _SELBORDER_BASIS, places=6,
                msg=f"der 3D-Auswahl-Ring an Geraet {fid} blieb nach dem Puls "
                    f"gedimmt stehen ({endstand[fid][1]})")
            self.assertAlmostEqual(
                endstand[fid][0], _ICON_RING_BASIS, places=6,
                msg=f"der 2D-Icon-Ring an Geraet {fid} blieb nach dem Puls gedimmt")

        # Danach idle: der Settle ist EINMALIG (kein Loop) — weitere Ticks rendern nicht.
        c_after = self._stats()["count"]
        for _ in range(3):
            self._tick()
        self.assertEqual(
            self._stats()["count"], c_after,
            "Settle-Render war nicht einmalig (Dauer-Render nach Reset)")


if __name__ == "__main__":
    unittest.main()
