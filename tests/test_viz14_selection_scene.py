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


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


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
        try:
            self._view.deleteLater()
        except Exception:
            pass
        _pump(0.2)

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

        # Basislinie der Echo-Aufrufe (Initial-Load kann updateOutlines(true) mit
        # leerer Auswahl ausloesen -> "[]"; KEIN Echo unserer Auswahl).
        baseline = list(getattr(self._bridge_obj, "_fixture_selection_calls", []))

        # Python pusht die Auswahl in den Poll-Zustand; der JS-Poll (130ms) zieht
        # sie und wendet sie an.
        self._bridge_obj._poll_payload = '{"selection": "[2, 4]"}'
        applied = self._poll_until_true(
            "JSON.stringify(window.__lightos.view.selectedFids) === '[2,4]'")
        self.assertTrue(applied, "gepushte Auswahl [2,4] nicht in der 3D-Szene angekommen")

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
        self._settle()   # Idle-Baseline vor der Auswahl

        # Auswahl pushen -> Identify-Flash startet -> Live-Probe aktiv.
        self._bridge_obj._poll_payload = '{"selection": "[2, 4]"}'
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
        self._settle()

        # Auswahl pushen -> Flash aktiv.
        self._bridge_obj._poll_payload = '{"selection": "[2, 4]"}'
        self._poll_until_true("window.__lightos.renderStats().live === true", timeout_s=8.0)
        # Einmal ticken, damit der Puls laeuft (_pulseDirty=true, Ringe verstellt).
        self._tick()
        self.assertTrue(self._stats()["live"], "Flash sollte noch aktiv sein")

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

        # Danach idle: der Settle ist EINMALIG (kein Loop) — weitere Ticks rendern nicht.
        c_after = self._stats()["count"]
        for _ in range(3):
            self._tick()
        self.assertEqual(
            self._stats()["count"], c_after,
            "Settle-Render war nicht einmalig (Dauer-Render nach Reset)")


if __name__ == "__main__":
    unittest.main()
