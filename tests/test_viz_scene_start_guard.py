"""VIZ-SCENE-SELFHEAL: Waechter fuer eine Szene, die nicht hochkommt.

Die Luecke, die es schliesst: der Render-Prozess lebt, ``loadFinished`` meldet
Erfolg — und die Szene ist trotzdem tot, weil ``scene/renderer.js`` den
``WebGLRenderer`` beim Modul-Import baut und der bei verlorenem GL-Kontext
wirft. Gemessen am 2026-08-01 im Test-Gate (XPLAT-17): ``RasterDecoderImpl:
Context lost during MakeCurrent`` -> ``THREE.WebGLRenderer: Error creating
WebGL context``. Bis hierher blieb die 3D-Ansicht danach dauerhaft schwarz,
ohne Meldung und ohne Log — ``__lightosAppReady`` las ausschliesslich die
Testsuite, nie die App.

Der Loewenanteil hier laeuft OHNE Qt: ``schedule`` ist als Parameter
herausgezogen, die Tests reichen ein sofort feuerndes ``lambda`` herein und
pruefen den kompletten Ablauf ohne Ereignisschleife und ohne Wartezeit.
Der eine WebEngine-Test am Ende belegt das, was eine Attrappe grundsaetzlich
nicht kann: dass der fruehe error-Listener wirklich in der AUSGELIEFERTEN
stage_scene.html steht und dass eine gesunde Ladung ihn nicht ausloest.
"""
import gc
import os
import time
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.ui.visualizer.visualizer_window as VW


class _FakeSignal:
    def __init__(self):
        self.slots = []

    def connect(self, fn):
        self.slots.append(fn)

    def emit(self, *args):
        for fn in list(self.slots):
            fn(*args)


class _FakePage:
    """``runJavaScript(js, cb)`` ruft ``cb`` sofort mit dem gestellten Wert."""

    def __init__(self, antwort):
        self.antwort = antwort
        self.aufrufe = []

    def runJavaScript(self, js, cb):
        self.aufrufe.append(js)
        cb(self.antwort)


class _FakeView:
    def __init__(self, antwort):
        self.loadFinished = _FakeSignal()
        self._page = _FakePage(antwort)

    def page(self):
        return self._page


class SceneStartVerdictTest(unittest.TestCase):
    """Die reine Entscheidung — ohne Qt, ohne View, ohne Zeit."""

    def test_bereite_szene_ist_ok_und_setzt_das_kontingent_zurueck(self):
        guard = VW.RenderCrashGuard(max_restarts=1, window_s=120.0)
        guard.should_restart(100.0)              # Kontingent verbraucht
        self.assertEqual(VW.scene_start_verdict(True, guard, 101.0), "ok")
        # Nach dem Zuruecksetzen darf ein SPAETERER Ausfall wieder neu laden —
        # sonst waere ein einziger Schluckauf am Sitzungsanfang ein
        # lebenslanges Verbot der Selbstheilung.
        self.assertEqual(VW.scene_start_verdict(False, guard, 102.0), "neu_laden")

    def test_erster_ausfall_laedt_neu_zweiter_gibt_auf(self):
        guard = VW.RenderCrashGuard(max_restarts=1, window_s=120.0)
        self.assertEqual(VW.scene_start_verdict(False, guard, 10.0), "neu_laden")
        self.assertEqual(VW.scene_start_verdict(False, guard, 11.0), "aufgeben")

    def test_ausserhalb_des_fensters_wieder_erlaubt(self):
        """Zwei Ausfaelle mit 10 Minuten Abstand sind kein Schleifenverdacht."""
        guard = VW.RenderCrashGuard(max_restarts=1, window_s=120.0)
        self.assertEqual(VW.scene_start_verdict(False, guard, 10.0), "neu_laden")
        self.assertEqual(VW.scene_start_verdict(False, guard, 700.0), "neu_laden")


class SceneStartGuardWiringTest(unittest.TestCase):
    def setUp(self):
        self._reloads = []
        self._orig_load = VW.load_stage_html
        VW.load_stage_html = lambda v: self._reloads.append(v)
        self._logs = []
        self._orig_log = VW.log_bridge_exception
        VW.log_bridge_exception = lambda name, exc: self._logs.append((name, str(exc)))

    def tearDown(self):
        VW.load_stage_html = self._orig_load
        VW.log_bridge_exception = self._orig_log

    def _sofort(self):
        """Zeitgeber, der die Pruefung sofort ausfuehrt statt nach 8 s."""
        return lambda ms, fn: fn()

    def test_gesunde_szene_laedt_nichts_neu(self):
        view = _FakeView([True, ""])
        meldungen = []
        VW.install_scene_start_guard(view, status_cb=meldungen.append,
                                     schedule=self._sofort())
        view.loadFinished.emit(True)
        self.assertEqual(self._reloads, [])
        self.assertEqual(meldungen, [])
        self.assertEqual(self._logs, [])

    def test_tote_szene_laedt_genau_einmal_neu_dann_meldung(self):
        view = _FakeView([False, "Error creating WebGL context."])
        meldungen = []
        resyncs = []
        VW.install_scene_start_guard(
            view, status_cb=meldungen.append,
            on_reloaded=lambda: resyncs.append(1), schedule=self._sofort())

        view.loadFinished.emit(True)
        self.assertEqual(len(self._reloads), 1, "erster Ausfall muss neu laden")
        self.assertEqual(resyncs, [1], "nach dem Reload muss voll re-synct werden")
        self.assertEqual(meldungen, [], "beim ersten Versuch noch keine Meldung")

        # Der Reload feuert ein zweites loadFinished — und wieder kommt nichts hoch.
        view.loadFinished.emit(True)
        self.assertEqual(len(self._reloads), 1, "KEIN zweiter Auto-Reload")
        self.assertEqual(len(meldungen), 1, "jetzt muss es sichtbar werden")
        self.assertIn("3D-Szene startet nicht", meldungen[0])

    def test_der_echte_js_fehler_landet_im_log(self):
        """Ohne den Grund stuende im Log nur "kam nicht hoch" — mit ihm die
        Zeile, die den Unterschied zwischen Triage und Diagnose macht."""
        view = _FakeView([False, "Error creating WebGL context."])
        VW.install_scene_start_guard(view, schedule=self._sofort())
        view.loadFinished.emit(True)
        self.assertTrue(self._logs, "Ausfall muss geloggt werden")
        name, text = self._logs[0]
        self.assertEqual(name, "sceneStartTimeout")
        self.assertIn("Error creating WebGL context", text)

    def test_ohne_js_fehler_sagt_das_log_das_ausdruecklich(self):
        view = _FakeView([False, ""])
        VW.install_scene_start_guard(view, schedule=self._sofort())
        view.loadFinished.emit(True)
        self.assertIn("kein JS-Fehler gemeldet", self._logs[0][1])

    def test_fehlgeschlagene_ladung_geht_den_waechter_nichts_an(self):
        """``loadFinished(False)`` heisst: die SEITE kam nicht an. Darum
        kuemmert sich Chromium/der Aufrufer — hier waere eine zweite,
        konkurrierende Reload-Quelle nur schaedlich."""
        view = _FakeView([False, "egal"])
        geplant = []
        VW.install_scene_start_guard(
            view, schedule=lambda ms, fn: geplant.append(fn))
        view.loadFinished.emit(False)
        self.assertEqual(geplant, [], "nichts eingeplant")
        self.assertEqual(self._reloads, [])

    def test_verzoegerung_entspricht_dem_timeout(self):
        view = _FakeView([True, ""])
        geplant = []
        VW.install_scene_start_guard(
            view, timeout_s=3.0, schedule=lambda ms, fn: geplant.append(ms))
        view.loadFinished.emit(True)
        self.assertEqual(geplant, [3000])

    def test_veraltete_pruefung_feuert_nicht_gegen_die_neue_seite(self):
        """Die Szene wird auch im Normalbetrieb neu geladen (Qualitaetsstufen-
        Wechsel, Stage-Reload, Selbstheilung des RenderCrashGuard). Eine noch
        schwebende Pruefung der ALTEN Ladung darf die NEUE nicht anfassen —
        sonst loest ausgerechnet ein gewoehnlicher Reload ein zweites Laden
        aus, waehrend das erste noch laeuft."""
        view = _FakeView([False, "Error creating WebGL context."])
        geplant = []
        VW.install_scene_start_guard(
            view, schedule=lambda ms, fn: geplant.append(fn))

        view.loadFinished.emit(True)      # Ladung 1 -> Pruefung 1 eingeplant
        view.loadFinished.emit(True)      # Ladung 2 -> Pruefung 2 eingeplant
        self.assertEqual(len(geplant), 2)

        geplant[0]()                      # die VERALTETE Pruefung
        self.assertEqual(self._reloads, [], "alte Pruefung darf nichts tun")

        geplant[1]()                      # die aktuelle
        self.assertEqual(len(self._reloads), 1, "die aktuelle muss greifen")

    def test_waechter_haelt_die_view_nur_schwach(self):
        """STAB-10: View -> Timer -> Closure -> View waere ein GC-Zyklus um den
        Owner — genau die Klasse, die beim Teardown nativ knallt. Stirbt die
        View vor dem Zeitgeber, muss der Rueckruf folgenlos verpuffen."""
        view = _FakeView([False, "Error creating WebGL context."])
        geplant = []
        VW.install_scene_start_guard(
            view, schedule=lambda ms, fn: geplant.append(fn))
        view.loadFinished.emit(True)
        ref = __import__("weakref").ref(view)
        del view
        gc.collect()
        self.assertIsNone(ref(), "der Waechter darf die View nicht am Leben halten")
        geplant[0]()                      # darf nicht werfen
        self.assertEqual(self._reloads, [], "tote View laedt nichts neu")


_HTML_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "src", "ui", "visualizer", "stage_scene.html"))


class SceneErrorListenerTest(unittest.TestCase):
    """Der error-Listener in der AUSGELIEFERTEN stage_scene.html.

    Eine Attrappe koennte hier nichts belegen: die Frage ist gerade, ob das
    Script-Tag wirklich in der HTML steht, frueh genug, und ob eine gesunde
    Ladung es in Ruhe laesst.
    """

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import QWebEngineSettings
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtCore import QObject
        self._view = QWebEngineView()
        s = self._view.settings()
        s.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        # qt.webChannelTransport muss existieren, sonst scheitert bridge.js —
        # und ein dadurch gesetzter Fehler waere kein ehrlicher Testbefund.
        self._obj = QObject()
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._obj)
        self._view.page().setWebChannel(self._channel)
        self._loaded = []
        self._view.loadFinished.connect(self._loaded.append)

    def tearDown(self):
        from _qt_lifecycle import destroy_webengine_view   # XPLAT-09
        destroy_webengine_view(self._view, self._pump)
        self._view = None

    def _pump(self, sekunden=0.2):
        ende = time.monotonic() + sekunden
        while time.monotonic() < ende:
            self._app.processEvents()
            time.sleep(0.01)

    def _eval(self, js):
        from PySide6.QtCore import QUrl  # noqa: F401  (Symmetrie zu den Nachbarn)
        box = []
        self._view.page().runJavaScript(js, box.append)
        ende = time.monotonic() + 10.0
        while not box and time.monotonic() < ende:
            self._app.processEvents()
            time.sleep(0.05)
        self.assertTrue(box, f"runJavaScript-Callback blieb aus: {js}")
        return box[0]

    def test_listener_faengt_den_ersten_fehler_und_haelt_ihn_fest(self):
        from PySide6.QtCore import QUrl
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}")
        self._view.load(url)
        ende = time.monotonic() + 40.0
        while not self._loaded and time.monotonic() < ende:
            self._app.processEvents()
            time.sleep(0.05)
        self.assertTrue(self._loaded and self._loaded[-1], "Page nicht geladen")

        # 1) Der Listener ist da — und zwar als Eigenschaft der Seite, nicht
        #    erst durch unser Zutun.
        self.assertEqual(
            self._eval("typeof window.__lightosSceneError"), "undefined",
            "eine gerade geladene Seite darf keinen Szenen-Fehler melden")

        # 2) Er faengt einen Fehler ...
        self._eval("window.dispatchEvent(new ErrorEvent('error',"
                   " {message: 'Error creating WebGL context.'})); 1")
        self.assertEqual(self._eval("window.__lightosSceneError"),
                         "Error creating WebGL context.")

        # 3) ... und der ERSTE bleibt stehen. Die spaeteren sind seine Folgen;
        #    wer sie ueberschreiben liesse, haette am Ende die harmloseste
        #    Meldung im Log statt der Ursache.
        self._eval("window.dispatchEvent(new ErrorEvent('error',"
                   " {message: 'Folgefehler'})); 1")
        self.assertEqual(self._eval("window.__lightosSceneError"),
                         "Error creating WebGL context.")

        # 4) ★ XPLAT-19: Der Vertrag, auf dem die Szenen-Diagnose der drei
        #    show()-Testdateien steht. Die feuert nur im seltenen Fehlerfall —
        #    verrottet einer dieser Namen, meldet sie ab da fuer JEDEN Ausfall
        #    stumm „undefined", und niemand merkt es, weil das ja genau nach
        #    einem kaputten Szenen-Start aussieht. Deshalb hier, auf der
        #    laufenden Seite, einmal festgenagelt (kostet keine zweite Ladung).
        for name, erwartet in (("window.__lightosAppReady", True),
                               ("window.THREE", True),
                               ("window.__lightos", True)):
            self.assertNotEqual(
                self._eval(f"typeof {name}"), "undefined",
                f"{name} fehlt — die XPLAT-19-Diagnose koennte einen echten "
                f"Ausfall nicht mehr von einer Namensaenderung unterscheiden")
        self.assertTrue(
            self._eval("(window.qt && !!window.qt.webChannelTransport) === true"),
            "die Diagnose liest den WebChannel-Transport ueber window.qt")
        self.assertGreater(
            self._eval("document.getElementsByTagName('canvas').length"), 0,
            "die Diagnose unterscheidet 'Renderer hing sein Canvas nie ein' "
            "ueber die Canvas-Zahl — auf einer gesunden Seite ist sie > 0")


if __name__ == "__main__":
    unittest.main()
