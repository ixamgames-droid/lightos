"""VIZ-PRISMA-3D: aus einem Strahl werden mehrere — in echter QWebEngine.

Prisma ist eine andere Klasse Arbeit als Zoom/Iris (Skalierung) oder
Fokus/Frost (EINE Materialzahl, `spot.penumbra`): es braucht zusaetzliche
Kegel, also Geometrie im 44-Hz-Pfad. Deshalb prueft diese Datei nicht nur „sieht
man mehr Strahlen", sondern vor allem die drei Entscheidungen, mit denen die
Kosten klein bleiben:

1. **Geteilte Geometrie UND geteiltes Material** — ein Prisma allokiert nichts
   pro Frame, und Farbe/Deckkraft stimmen automatisch, weil `applyGenericColor`
   in JEDEM Frame in dasselbe Material schreibt. Der Test prueft die
   IDENTITAET der Objekte, nicht ihre Gleichheit: zwei Materialien mit
   denselben Werten waeren zwei Wahrheiten, und die zweite wuerde beim naechsten
   Farbwechsel stehenbleiben.
2. **Faul gebaut, sofort abgeraeumt** — ist das Prisma aus (Default in 4/4
   Profilen), existiert kein einziger zusaetzlicher Kegel.
3. **Deckel auf schwachen GPUs** — hoechstens 3 Facetten auf der Low-Spec-Stufe.

Ausgefuehrt wird der echte Modulcode (Seam ueber `window.__lightos`), nicht der
Quelltext gegreppt — dieselbe Lehre wie bei der ersten Optik-Test-Fassung: eine
falsche Formel mit richtigen Konstanten haette ein Regex-Test durchgewinkt.
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
    attrs["requestFullResync"] = Signal()
    return type("MockVisualizerBridge", (QObject,), attrs)


_MockVisualizerBridge = _make_mock_bridge_class()


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


# Ein gestelltes Fixture mit ECHTEM Beam-Mesh an einem Elternknoten — applyPrism
# legt wirkliche Kegel an, also braucht es hier auch wirkliche three.js-Objekte.
_FAKE_FIXTURE = """
(function () {
  const T = window.THREE;
  const host = new T.Group();
  const geo = new T.ConeGeometry(1, 7, 12, 1, true);
  const mat = new T.MeshBasicMaterial({ transparent: true, opacity: 0.5 });
  const beam = new T.Mesh(geo, mat);
  beam.position.y = -3.5;
  beam.visible = true;
  host.add(beam);
  window.__prismHost = host;
  window.__prismProbe = { beam: beam, baseSpotAngle: 0.30 };
  return true;
})()
"""


class Prisma3DSceneTest(unittest.TestCase):
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
        self._loaded_ok = []
        self._view.loadFinished.connect(self._loaded_ok.append)

    def tearDown(self):
        destroy_webengine_view(self._view, _pump)   # XPLAT-09
        self._view = None

    def _eval(self, js):
        box = []
        self._view.page().runJavaScript(js, lambda r: box.append(r))
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(box, f"runJavaScript ohne Callback: {js}")
        return box[0]

    def _poll_until_true(self, js, timeout_s=_POLL_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            last = self._eval(js)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout bei '{js}' (letzter: {last!r})")

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

    # ── Ladung 1: die reine Zahl-Funktion + der ganze Kegel-Lebenszyklus ──────
    # Bewusst EINE Seiten-Ladung fuer alles (>~3 Vollladungen pro Prozess
    # kippen den offscreen-Chromium-Renderer, s. Nachbardateien).
    def test_prisma_lebenszyklus_und_deckel(self):
        self._load_and_wait()

        # 1) prismFacetCount ist rein: Zahl rein, Zahl raus.
        z = lambda roh, low="false": self._eval(
            f"window.__lightos.prismFacetCount({roh}, {low})")
        self.assertEqual(z(0), 0, "0 = kein Prisma")
        self.assertEqual(z(1), 0, "ein einzelner Strahl IST der Hauptstrahl")
        self.assertEqual(z(6), 6)
        self.assertEqual(z(99), 12, "harter Deckel gegen unsinnige Zahlen")
        self.assertEqual(z(8, "true"), 3,
                         "Low-Spec deckelt auf 3 — ein 8-fach-Prisma auf jedem "
                         "Mover waere das Achtfache der Beam-Geometrie")
        self.assertEqual(z("NaN"), 0, "Unsinn darf keine Kegel bauen")

        # 2) Aus heisst: es existiert NICHTS.
        self._eval(_FAKE_FIXTURE)
        self._eval("window.__lightos.applyPrism(window.__prismProbe, {prism: 0})")
        self.assertEqual(self._eval("window.__prismHost.children.length"), 1,
                         "ausgeschaltet darf kein zusaetzlicher Knoten haengen")

        # 3) Einschalten: n-1 Nebenstrahlen um die Mitte.
        self._eval("window.__lightos.applyPrism(window.__prismProbe, {prism: 6})")
        self.assertEqual(self._eval("window.__prismProbe.prismCones.length"), 5,
                         "6 Facetten = Hauptstrahl + 5 Nebenstrahlen")
        self.assertEqual(self._eval("window.__prismHost.children.length"), 2,
                         "genau EINE Gruppe zusaetzlich am Elternknoten")

        # 4) Der Kern der Kostenrechnung: IDENTISCHE Geometrie und Material.
        self.assertTrue(self._eval(
            "window.__prismProbe.prismCones.every(m =>"
            " m.geometry === window.__prismProbe.beam.geometry)"),
            "Geometrie muss geteilt sein, nicht kopiert")
        self.assertTrue(self._eval(
            "window.__prismProbe.prismCones.every(m =>"
            " m.material === window.__prismProbe.beam.material)"),
            "Material muss geteilt sein — sonst friert die Farbe der "
            "Nebenstrahlen beim naechsten DMX-Frame ein")

        # 5) Aus der Fit-Bounding-Box heraushalten (wie der Hauptstrahl).
        self.assertTrue(self._eval(
            "window.__prismProbe.prismCones.every(m => m.userData.excludeFromFit)"),
            "sonst zoomt 'Auswahl einpassen' wegen der Faecher-Kegel heraus")

        # 6) Drehung: 0..255 auf eine volle Umdrehung. Vollausschlag ist 255,
        #    nicht 256 — bei 128 also etwas MEHR als eine halbe Drehung. Die
        #    Erwartung wird deshalb ausgerechnet statt auf pi gerundet, sonst
        #    prueft der Test seine eigene Ungenauigkeit.
        import math
        self._eval("window.__lightos.applyPrism(window.__prismProbe,"
                   " {prism_rotation: 128})")
        rot = float(self._eval("window.__prismProbe.prismGroup.rotation.y"))
        self.assertAlmostEqual(rot, (128 / 255) * 2 * math.pi, places=4)
        # 255 muss die volle Umdrehung sein, 0 der Anfang — sonst haette das
        # Geraet einen toten Bereich am Ende des Kanals.
        self._eval("window.__lightos.applyPrism(window.__prismProbe,"
                   " {prism_rotation: 255})")
        self.assertAlmostEqual(
            float(self._eval("window.__prismProbe.prismGroup.rotation.y")),
            2 * math.pi, places=4)
        self.assertEqual(self._eval("window.__prismProbe.prismCones.length"), 5,
                         "ein Batch ohne `prism` darf das Prisma nicht abschalten")

        # 7) Facettenwechsel baut um, statt zu stapeln.
        self._eval("window.__lightos.applyPrism(window.__prismProbe, {prism: 3})")
        self.assertEqual(self._eval("window.__prismProbe.prismCones.length"), 2)
        self.assertEqual(self._eval("window.__prismHost.children.length"), 2,
                         "keine Alt-Gruppe zurueckgelassen")

        # 8) Ausschalten raeumt wirklich ab — und laesst die GETEILTEN
        #    Ressourcen des Hauptstrahls unangetastet. Ein dispose() hier
        #    haette dem Hauptstrahl die Geometrie unter den Fuessen weggezogen.
        self._eval("window.__lightos.applyPrism(window.__prismProbe, {prism: 0})")
        self.assertEqual(self._eval("window.__prismHost.children.length"), 1)
        self.assertFalse(self._eval("!!window.__prismProbe.prismCones"))
        self.assertTrue(self._eval(
            "!!(window.__prismProbe.beam.geometry &&"
            " window.__prismProbe.beam.geometry.attributes &&"
            " window.__prismProbe.beam.geometry.attributes.position)"),
            "der Hauptstrahl muss seine Geometrie behalten haben")

        # 9) Sichtbarkeit und Kegelweite folgen dem Hauptstrahl.
        self._eval("window.__lightos.applyPrism(window.__prismProbe, {prism: 4})")
        self._eval("window.__prismProbe.beam.visible = false;"
                   " window.__prismProbe.beam.scale.set(2, 1, 2);"
                   " window.__lightos.applyPrism(window.__prismProbe, {prism: 4})")
        self.assertTrue(self._eval(
            "window.__prismProbe.prismCones.every(m => m.visible === false)"),
            "Nebenstrahlen duerfen nicht leuchten, wenn die Mitte aus ist")
        self.assertTrue(self._eval(
            "window.__prismProbe.prismCones.every(m => Math.abs(m.scale.x - 2) < 1e-6)"),
            "Kegelweite (Zoom/Iris/Frost) muss mitwandern")

        # 10) Ein Geraet ohne Prisma-Kanal bekommt gar nichts — der Payload
        #     enthaelt dann keinen Schluessel, und der Aufruf muss folgenlos
        #     bleiben (kein erfundener Default, dieselbe Regel wie bei Zoom).
        self._eval("window.__prismProbe.__vorher ="
                   " window.__prismHost.children.length")
        self._eval("window.__lightos.applyPrism(window.__prismProbe, {zoom: 200})")
        self.assertEqual(
            self._eval("window.__prismHost.children.length"),
            self._eval("window.__prismProbe.__vorher"),
            "ein Batch ohne Prisma-Schluessel darf nichts anfassen")


if __name__ == "__main__":
    unittest.main()
