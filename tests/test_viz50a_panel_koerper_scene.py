"""VIZ-50a — der 3D-Koerper eines Panels, in echter QWebEngine gemessen.

Der Python-Teil (``test_viz50a_panel_geometrie.py``) belegt, dass die
Rasterform hinterlegt, migriert und bis in die Nutzlast durchgereicht wird.
Hier wird gemessen, was daraus im Bild WIRD — denn genau dort sass der Fehler:

* ``buildMatrixPanel`` leitete die Form aus der Pixelzahl ab
  (``cols = ceil(sqrt(48)) = 7``) und baute ein 7x7-Quadrat mit 49 Feldern,
* das Gehaeuse war eine fest quadratische 0,5-m-Kachel (``PW = PH = 0.5``),
  unabhaengig vom Geraet.

Robins ZQ06121 ist real eine 12 Spalten breite, 4 Reihen hohe Leiste. Im 3D
stand ein Quadrat, und ein waagerechtes Lauflicht sprang dort nach 7 statt nach
12 Pixeln in die naechste Zeile — die Vorschau taugte fuer dieses Geraet weder
zur Positionskontrolle noch zum Programmieren.

★ Gemessen wird ueber den ECHTEN Weg: ``bridge.allFixtures`` -> ``addFixture``
-> Registry -> ``buildMatrixPanel``, also dieselbe Kette, die im Betrieb laeuft.
Ein Test, der ``buildMatrixPanel`` direkt aufruft, haette die Registry-Zeile
(``o.gridCols``/``o.gridRows``) nicht abgedeckt — und genau so ist VIZ-51 fuer
``pixelOrder`` durchgefallen: Feld vorhanden, Funktion richtig, Nutzlast leer.

★★ Arrays reisen ueber die QtWebEngine-Bruecke nicht zuverlaessig zurueck.
Deshalb fragt jede Messung einen EINZELNEN Zahlen-/Wahrheitswert ab; das Zaehlen
und Vergleichen passiert JS-seitig.
"""
import json
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                       # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView            # noqa: E402
from PySide6.QtWebEngineCore import (QWebEngineSettings,         # noqa: E402
                                     QWebEngineProfile)
from PySide6.QtWebChannel import QWebChannel                     # noqa: E402
from PySide6.QtCore import QObject, QUrl, Signal, Slot           # noqa: E402
from _qt_lifecycle import destroy_webengine_view                 # noqa: E402

_app = QApplication.instance() or QApplication([])

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HTML_PATH = os.path.join(_ROOT, "src", "ui", "visualizer", "stage_scene.html")
_JS_DIR = os.path.join(_ROOT, "src", "ui", "visualizer", "scene_src", "fixtures")

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05

# Signal-Liste wie in test_viz13_scene_modules_smoke.py (bridge.js#tryChannel).
_SIGNAL_SPECS = [
    ("fixtureAdded", (str,)), ("fixtureRemoved", (int,)), ("dmxBatch", (str,)),
    ("allFixtures", (str,)), ("settingsChanged", (str,)),
    ("viewModeChanged", (str,)), ("editModeChanged", (str,)),
    ("stageLoaded", (str,)), ("addStageObject", (str,)),
    ("addStageObjectData", (str,)), ("removeStageObject", (str,)),
    ("selectStageObject", (str,)), ("applyFixtureTransform", (str,)),
    ("alignSelected", (str,)), ("distributeSelected", (str,)),
    ("cameraReset", ()), ("brightnessSignal", (float,)),
    ("brightnessAutoSignal", ()), ("updateStageObject", (str,)),
    ("resizeModeSignal", (bool,)), ("pixelRatioSignal", (float,)),
]


def _make_mock_bridge_class():
    attrs = {name: Signal(*args) for name, args in _SIGNAL_SPECS}

    @Slot()
    def requestFixtures(self):
        pass

    @Slot(result=str)
    def pollControl(self):
        return "{}"

    attrs["requestFixtures"] = requestFixtures
    attrs["pollControl"] = pollControl
    attrs["requestFullResync"] = Signal()
    return type("MockVisualizerBridge", (QObject,), attrs)


_MockBridge = _make_mock_bridge_class()


def _pump(seconds):
    ende = time.monotonic() + seconds
    while time.monotonic() < ende:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


# ════════════════════════════════════════════════════════════════════════════
# 1. Die Rasterform-Funktion selbst (rein, ohne three.js)
# ════════════════════════════════════════════════════════════════════════════

class PanelGridRechnungTest(unittest.TestCase):
    """``panelGrid`` ist die EINE Quelle der Rasterform (VIZ-51) — 3D-Panel und
    2D-Icon gehen beide hier durch. Sie bekommt mit VIZ-50a einen zweiten
    Eingang: die hinterlegte Form. Der Bestandspfad darf sich dabei nicht um
    einen Pixel bewegen."""

    def setUp(self):
        self._view = QWebEngineView()
        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self._geladen = []
        self._view.loadFinished.connect(self._geladen.append)

    def tearDown(self):
        destroy_webengine_view(self._view, _pump)
        self._view = None

    def _rechne(self, faelle):
        """``faelle`` = [(n, gridCols, gridRows), ...] -> [[cols, rows, count,
        explizit], ...]. Ein Modul-HTML neben ``pixel_order.js``, damit der
        relative ESM-Import greift (Muster aus test_element_orientierung.py)."""
        html = f"""<!doctype html><meta charset="utf-8">
        <script type="module">
        import {{ panelGrid }} from './pixel_order.js';
        const faelle = {json.dumps(faelle)};
        window.__out = JSON.stringify(faelle.map(function (f) {{
          const g = panelGrid(f[0], f[1], f[2]);
          return [g.cols, g.rows, g.count, g.explizit ? 1 : 0];
        }}));
        </script>"""
        tmp = os.path.join(_JS_DIR, "_viz50a_grid_tmp.html")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(html)
        self.addCleanup(lambda: os.path.exists(tmp) and os.unlink(tmp))

        self._view.load(QUrl.fromLocalFile(tmp))
        ende = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._geladen and time.monotonic() < ende:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._geladen and self._geladen[-1], "Seite nicht geladen")

        box = []
        ende = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < ende:
            self._view.page().runJavaScript("window.__out || ''", box.append)
            ende2 = time.monotonic() + 2
            while not box and time.monotonic() < ende2:
                _app.processEvents()
                time.sleep(_POLL_INTERVAL_S)
            if box and not box[0]:
                box.clear()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(box and box[0], "JS lieferte kein Ergebnis")
        return json.loads(box[0])

    def test_alles_auf_einmal(self):
        """Ein Seitenladen, alle Faelle — die QWebEngine-Startzeit dominiert
        sonst die Laufzeit dieser Datei."""
        faelle = [
            # (a) BESTANDSPFAD: ohne Angabe exakt die alte Wurzelformel.
            (16, 0, 0), (48, 0, 0), (64, 0, 0), (144, 0, 0), (12, 0, 0),
            (1, 0, 0), (0, 0, 0), (300, 0, 0),
            # (b) hinterlegte Form
            (48, 12, 4), (16, 4, 4), (144, 12, 12), (8, 8, 1),
            # (c) nur EINE Zahl bekannt
            (48, 12, 0), (48, 0, 4),
            # (d) Form passt nicht zur Pixelzahl (falsch gepatcht)
            (50, 12, 4), (24, 12, 4),
            # (e) Muell
            (48, -3, -3), (48, None, None),
        ]
        e = self._rechne(faelle)
        cols, rows, count, expl = 0, 1, 2, 3

        # ── (a) Bestandsschutz: Zahl fuer Zahl die alte Formel ──────────────
        import math
        for i, (n, _c, _r) in enumerate(faelle[:8]):
            erw_count = max(1, min(256, int(n or 16)))
            erw_cols = math.ceil(math.sqrt(erw_count))
            erw_rows = math.ceil(erw_count / erw_cols)
            self.assertEqual(
                [e[i][count], e[i][cols], e[i][rows]],
                [erw_count, erw_cols, erw_rows],
                f"ohne hinterlegte Form muss panelGrid({n}) die alte Formel "
                f"liefern — sonst aendert sich das Bild JEDES Bestandspanels")
            self.assertEqual(e[i][expl], 0,
                             "eine GERATENE Form darf sich nicht als hinterlegt "
                             "ausgeben (daran haengen die Gehaeusemasse)")

        # ── (b) hinterlegte Form gewinnt ────────────────────────────────────
        self.assertEqual([e[8][cols], e[8][rows], e[8][expl]], [12, 4, 1],
                         "48 Zonen mit hinterlegtem 4x12 muessen 12x4 ergeben, "
                         "nicht das geratene 7x7")
        self.assertEqual([e[9][cols], e[9][rows], e[9][expl]], [4, 4, 1])
        self.assertEqual([e[10][cols], e[10][rows], e[10][expl]], [12, 12, 1])
        self.assertEqual([e[11][cols], e[11][rows], e[11][expl]], [8, 1, 1],
                         "eine einzeilige Leiste ist eine gueltige Form")

        # ── (c) eine Zahl genuegt ───────────────────────────────────────────
        self.assertEqual([e[12][cols], e[12][rows]], [12, 4])
        self.assertEqual([e[13][cols], e[13][rows]], [12, 4])

        # ── (d) das Raster muss ALLE Pixel fassen ───────────────────────────
        self.assertEqual([e[14][cols], e[14][rows]], [12, 5],
                         "50 Pixel in ein 12x4 zu zwingen liesse zwei Pixel "
                         "unterhalb des Gehaeuses schweben")
        self.assertEqual([e[15][cols], e[15][rows]], [12, 4],
                         "weniger Pixel als Felder ist zulaessig — ein Panel "
                         "darf Luecken haben (das 7x7 hatte immer eine)")

        # ── (e) Muell faellt auf den Ratepfad zurueck ───────────────────────
        for i in (16, 17):
            self.assertEqual([e[i][cols], e[i][rows], e[i][expl]], [7, 7, 0],
                             "unbrauchbare Angaben duerfen nicht als Form gelten")


# ════════════════════════════════════════════════════════════════════════════
# 2. Der gebaute Koerper in der echten Szene
# ════════════════════════════════════════════════════════════════════════════

_BALKEN = 500101      # 48 Zonen, hinterlegt 4x12
_GERATEN = 500102     # 48 Zonen, KEINE Angabe -> Bestandsverhalten (7x7)
_HOCHKANT = 500103    # 48 Zonen, hinterlegt 4x12, um 90° montiert
_KACHEL = 500104      # 64 Zonen, hinterlegt 8x8 (Form == Ratewert)
# ★ 12 Zonen OHNE Angabe: der Ratepfad liefert hier ein NICHT quadratisches
# 4x3. Genau dieses Geraet unterscheidet „Masse nur bei hinterlegter Form" von
# „Masse immer aus dem Raster" — bei 48 Zonen (7x7) waeren beide gleich, und die
# Zusage „ohne Angabe aendert sich nichts" waere unpruefbar.
_GERATEN_SCHIEF = 500105


def _payload():
    def p(fid, **kw):
        d = {"fid": fid, "label": f"P{fid}", "type": "matrix", "model": "matrix",
             "nHeads": 48, "pixelOrder": "rowwise", "elementRotation": 0,
             "elementFlip": False, "gridRows": 0, "gridCols": 0,
             "x": 0, "y": 5, "z": 0, "rotX": 0, "rotY": 0, "rotZ": 0,
             "r": 0, "g": 0, "b": 0, "intensity": 0, "pan": 128, "tilt": 128}
        d.update(kw)
        return d
    return json.dumps([
        p(_BALKEN, gridRows=4, gridCols=12),
        p(_GERATEN),
        p(_HOCHKANT, gridRows=4, gridCols=12, elementRotation=90),
        p(_KACHEL, nHeads=64, gridRows=8, gridCols=8),
        p(_GERATEN_SCHIEF, nHeads=12),
    ])


# JS-Helfer: das Gehaeuse ist das einzige BoxGeometry-Mesh eines Panels
# (Pixel sind PlaneGeometry, das Label ist ein Sprite).
_HELFER = """
window.__viz50a = {
  koerper: function (fid) {
    const f = window.__lightos.fixtures[String(fid)];
    let box = null;
    f.group.traverse(function (o) {
      if (!box && o.isMesh && o.geometry && o.geometry.type === 'BoxGeometry') box = o;
    });
    return box;
  },
  breite: function (fid) { return this.koerper(fid).geometry.parameters.width; },
  hoehe:  function (fid) { return this.koerper(fid).geometry.parameters.height; },
  px:     function (fid) { return window.__lightos.fixtures[String(fid)].pixels; },
  spalten: function (fid) {
    return this.px(fid).reduce(function (m, p) { return Math.max(m, p.c); }, 0) + 1;
  },
  zeilen: function (fid) {
    return this.px(fid).reduce(function (m, p) { return Math.max(m, p.r); }, 0) + 1;
  },
  // 2D-Draufsicht: dieselben Pixel als Icon-Zellen (userData.cells).
  zelle: function (fid, i) {
    return window.__lightos.fixtures[String(fid)].icon.userData.cells[i];
  },
};
true
"""


class PanelKoerperSceneTest(unittest.TestCase):

    def setUp(self):
        self.assertTrue(os.path.isfile(_HTML_PATH), f"fehlt: {_HTML_PATH}")
        self._view = QWebEngineView()
        try:
            prof = self._view.page().profile()
            prof.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
        except Exception:
            pass
        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self._bridge = _MockBridge()
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)
        self._geladen = []
        self._view.loadFinished.connect(self._geladen.append)

    def tearDown(self):
        destroy_webengine_view(self._view, _pump)
        self._view = None

    def _eval(self, js):
        box = []
        self._view.page().runJavaScript(js, box.append)
        ende = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < ende:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(box, f"runJavaScript ohne Callback: {js}")
        return box[0]

    def _zahl(self, js):
        wert = self._eval(js)
        self.assertIsNotNone(wert, f"kein Wert fuer: {js}")
        return float(wert)

    def _aufbauen(self):
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}")
        self._view.load(url)
        ende = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._geladen and time.monotonic() < ende:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._geladen and self._geladen[-1], "Page nicht geladen")
        ende = time.monotonic() + _POLL_TIMEOUT_S
        bereit = False
        while time.monotonic() < ende:
            if self._eval("!!window.__lightosAppReady"):
                bereit = True
                break
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(bereit, "Szene wurde nicht bereit")

        # Der WebChannel-Connect ist deferred — wie im Smoke-Test wiederholt
        # emittieren, bis die Fixtures wirklich in der Szene stehen.
        nutzlast = _payload()
        ende = time.monotonic() + _POLL_TIMEOUT_S
        da = False
        while time.monotonic() < ende:
            self._bridge.allFixtures.emit(nutzlast)
            if self._eval(f"typeof window.__lightos.fixtures['{_KACHEL}'] "
                          f"=== 'object'"):
                da = True
                break
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(da, "allFixtures kam nie an (addFixture nie gelaufen)")
        self._eval(_HELFER)

    def test_der_koerper_folgt_der_hinterlegten_form(self):
        """★ Die Abnahme des Items in einem Test: mit hinterlegter 12x4-Geometrie
        steht im 3D eine 12x4-Leiste — nicht das geratene 7x7-Quadrat. Und ein
        Geraet OHNE Angabe sieht exakt aus wie bisher."""
        self._aufbauen()

        # ── (1) Das Raster ──────────────────────────────────────────────────
        self.assertEqual(self._zahl(f"window.__viz50a.spalten({_BALKEN})"), 12)
        self.assertEqual(self._zahl(f"window.__viz50a.zeilen({_BALKEN})"), 4)
        self.assertEqual(self._zahl(f"window.__viz50a.px({_BALKEN}).length"), 48,
                         "kein Pixel darf verloren gehen")

        # ── (2) Das GEHAEUSE: breiter als hoch ──────────────────────────────
        breite = self._zahl(f"window.__viz50a.breite({_BALKEN})")
        hoehe = self._zahl(f"window.__viz50a.hoehe({_BALKEN})")
        self.assertGreater(
            breite, hoehe * 2.5,
            f"ein 12x4-Balken muss deutlich breiter als hoch sein "
            f"(gemessen {breite:.3f} x {hoehe:.3f}) — vorher war beides fest 0,5")
        self.assertAlmostEqual(breite / hoehe, 3.0, places=6,
                               msg="das Seitenverhaeltnis muss dem Raster folgen")
        self.assertAlmostEqual(breite, 0.5, places=6,
                               msg="die laengere Kante behaelt das Bestandsmass")

        # ── (3) Quadratische Zellen ─────────────────────────────────────────
        # Ein mitskalierender Rand ist der Unterschied zwischen quadratischen
        # Zellen und leicht gestauchten — mit festem Rand faellt es nur auf,
        # wenn man nachmisst. Also nachmessen.
        gw = self._zahl(f"window.__viz50a.px({_BALKEN})[1].mesh.position.x"
                        f" - window.__viz50a.px({_BALKEN})[0].mesh.position.x")
        gh = self._zahl(f"window.__viz50a.px({_BALKEN})[0].mesh.position.y"
                        f" - window.__viz50a.px({_BALKEN})[12].mesh.position.y")
        self.assertAlmostEqual(gw, gh, places=6,
                               msg="die Pixel-Zellen sind nicht quadratisch")

    def test_ein_waagerechtes_lauflicht_laeuft_waagerecht(self):
        """★ Die Wirkung, die der Nutzer sieht. Bei 12 Spalten liegen die
        DMX-Pixel 0..11 in EINER Zeile; beim geratenen 7x7 sprang die Figur
        nach dem siebten Pixel eine Zeile tiefer — im 3D lief sie im Zickzack,
        am Rig geradeaus."""
        self._aufbauen()

        self.assertEqual(self._zahl(f"window.__viz50a.px({_BALKEN})[11].r"), 0,
                         "Pixel 11 gehoert bei 12 Spalten noch in die erste Zeile")
        self.assertEqual(
            self._zahl(f"Math.abs(window.__viz50a.px({_BALKEN})[11].mesh.position.y"
                       f" - window.__viz50a.px({_BALKEN})[0].mesh.position.y)"
                       f" < 1e-9 ? 1 : 0"), 1,
            "Pixel 0 und 11 muessen auf gleicher Hoehe liegen")
        self.assertEqual(
            self._zahl(f"window.__viz50a.px({_BALKEN})[11].mesh.position.x >"
                       f" window.__viz50a.px({_BALKEN})[0].mesh.position.x ? 1 : 0"),
            1, "die Figur muss nach RECHTS laufen")
        self.assertEqual(self._zahl(f"window.__viz50a.px({_BALKEN})[12].r"), 1,
                         "erst Pixel 12 beginnt die zweite Zeile")

        # Gegenprobe am geratenen Panel: dort ist genau das nicht so.
        self.assertEqual(self._zahl(f"window.__viz50a.px({_GERATEN})[11].r"), 1,
                         "beim geratenen 7x7 liegt Pixel 11 in Zeile 1 — genau "
                         "das ist der Fehler, den die Geometrie behebt")

    def test_2d_icon_schneidet_dasselbe_raster(self):
        """★ 2D und 3D duerfen dasselbe Panel nicht verschieden schneiden.
        VIZ-51 hat genau diese Abweichung fuer die Reihenfolge beseitigt und
        `panelGrid` dafuer zur EINEN Quelle gemacht — eine Geometrie, die nur
        im 3D ankommt, risse sie wieder auf: die Draufsicht zeigte 7x7, das
        Modell daneben 12x4."""
        self._aufbauen()

        # Zelle 11 liegt bei 12 Spalten in derselben Icon-Zeile wie Zelle 0
        # (die Draufsicht laeuft in Z statt in Y).
        self.assertEqual(
            self._zahl(f"Math.abs(window.__viz50a.zelle({_BALKEN}, 11).position.z"
                       f" - window.__viz50a.zelle({_BALKEN}, 0).position.z)"
                       f" < 1e-9 ? 1 : 0"), 1,
            "das 2D-Icon schneidet das Panel anders als das 3D-Modell")
        self.assertEqual(
            self._zahl(f"window.__viz50a.zelle({_BALKEN}, 11).position.x >"
                       f" window.__viz50a.zelle({_BALKEN}, 0).position.x ? 1 : 0"), 1)
        # Gegenprobe: ohne Angabe bleibt es beim geratenen 7x7, also Zeilenwechsel.
        self.assertEqual(
            self._zahl(f"window.__viz50a.zelle({_GERATEN}, 11).position.z >"
                       f" window.__viz50a.zelle({_GERATEN}, 0).position.z ? 1 : 0"), 1,
            "beim geratenen Panel muss Zelle 11 eine Icon-Zeile tiefer liegen")

    def test_ohne_angabe_bleibt_alles_wie_es_war(self):
        """★ Positivkontrolle und Abnahmebedingung zugleich: kein Geraet ohne
        hinterlegte Geometrie darf sich veraendern. Eine Aenderung, die jedes
        Panel umbaut, waere so unbrauchbar wie gar keine."""
        self._aufbauen()

        self.assertEqual(self._zahl(f"window.__viz50a.spalten({_GERATEN})"), 7)
        self.assertEqual(self._zahl(f"window.__viz50a.zeilen({_GERATEN})"), 7)
        self.assertAlmostEqual(self._zahl(f"window.__viz50a.breite({_GERATEN})"),
                               0.5, places=6)
        self.assertAlmostEqual(self._zahl(f"window.__viz50a.hoehe({_GERATEN})"),
                               0.5, places=6)
        # Die Zellgroesse ist die alte Rechnung (0.5 - 2*0.02) / 7.
        gw = self._zahl(f"window.__viz50a.px({_GERATEN})[1].mesh.position.x"
                        f" - window.__viz50a.px({_GERATEN})[0].mesh.position.x")
        self.assertAlmostEqual(gw, (0.5 - 0.04) / 7, places=6,
                               msg="die Zellgroesse eines geratenen Panels hat "
                                   "sich veraendert")

        # ★ Der Fall, der die Zusage ueberhaupt pruefbar macht: 12 Zonen ohne
        # Angabe ergeben ein GERATENES 4x3 — also ein nicht quadratisches
        # Raster. Wuerden die Gehaeusemasse dem Raster auch dann folgen, waere
        # dieses Panel ploetzlich 0,5 x 0,375 gross, ohne dass jemand etwas
        # ueber das Geraet ausgesagt hat. Bei den 48 Zonen oben (7x7) faellt
        # derselbe Fehler nicht auf.
        self.assertEqual(self._zahl(f"window.__viz50a.spalten({_GERATEN_SCHIEF})"), 4)
        self.assertEqual(self._zahl(f"window.__viz50a.zeilen({_GERATEN_SCHIEF})"), 3)
        self.assertAlmostEqual(
            self._zahl(f"window.__viz50a.breite({_GERATEN_SCHIEF})"), 0.5, places=6)
        self.assertAlmostEqual(
            self._zahl(f"window.__viz50a.hoehe({_GERATEN_SCHIEF})"), 0.5, places=6,
            msg="ein GERATENES Raster darf keine Gehaeuseform behaupten")

    def test_eine_form_gleich_dem_ratewert_aendert_nichts(self):
        """★★ Der schaerfere Fall derselben Zusage: das Panel HAT eine
        hinterlegte Form (8x8), sie stimmt nur zufaellig mit dem Ratewert
        ueberein. Dann muss das Bild identisch bleiben — sonst haengt das
        Aussehen daran, OB jemand die Form eingetragen hat, statt WELCHE."""
        self._aufbauen()

        self.assertEqual(self._zahl(f"window.__viz50a.spalten({_KACHEL})"), 8)
        self.assertEqual(self._zahl(f"window.__viz50a.zeilen({_KACHEL})"), 8)
        self.assertAlmostEqual(self._zahl(f"window.__viz50a.breite({_KACHEL})"),
                               0.5, places=6)
        self.assertAlmostEqual(self._zahl(f"window.__viz50a.hoehe({_KACHEL})"),
                               0.5, places=6)
        gw = self._zahl(f"window.__viz50a.px({_KACHEL})[1].mesh.position.x"
                        f" - window.__viz50a.px({_KACHEL})[0].mesh.position.x")
        self.assertAlmostEqual(gw, (0.5 - 0.04) / 8, places=6)

    def test_hochkant_montiert_steht_der_balken_hochkant(self):
        """VIZ-52 hat die Montage-Drehung eingefuehrt, aber die Form blieb
        quadratisch — man SAH die Drehung am Gehaeuse nicht. Mit hinterlegter
        Geometrie dreht sich jetzt auch der Koerper mit: aus 12 breit x 4 hoch
        wird 4 breit x 12 hoch."""
        self._aufbauen()

        self.assertEqual(self._zahl(f"window.__viz50a.spalten({_HOCHKANT})"), 4)
        self.assertEqual(self._zahl(f"window.__viz50a.zeilen({_HOCHKANT})"), 12)
        breite = self._zahl(f"window.__viz50a.breite({_HOCHKANT})")
        hoehe = self._zahl(f"window.__viz50a.hoehe({_HOCHKANT})")
        self.assertAlmostEqual(hoehe / breite, 3.0, places=6,
                               msg="ein hochkant montierter Balken muss hochkant "
                                   "stehen, nicht nur seine Pixel umsortieren")
        self.assertAlmostEqual(hoehe, 0.5, places=6)


if __name__ == "__main__":
    unittest.main()
