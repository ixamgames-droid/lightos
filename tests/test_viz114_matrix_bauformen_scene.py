"""VIZ-114 — LED-Matrizen im 3D in ihrer Bauform, parametrisch aus dem Profil.

Was gemessen wird (echte QWebEngine, echter Bau-Weg ``allFixtures`` ->
``addFixture`` -> Registry -> ``buildMatrixForm``):

* je Bauform (panel, vorhang, leiste, ring, saeule) steht ein Modell da, die
  MASSE folgen der Flaeche aus dem Matrix-Assistenten (FM-80),
* jedes Pixel sitzt an der Stelle, die Python fuer die Gesamt-Matrix nennt
  (``led_matrix.pixel_platz`` — dieselbe Rechnung wie die 2D-Vorschau und die
  Gesamt-Gruppe), ueber alle Universums-Teile und mit Schlangenlinie +
  Startecke unten rechts,
* ein Pixel nach dem anderen angeschaltet leuchtet genau dort,
* das Bestands-Panel (ohne Angaben) baut weiter ``buildMatrixPanel``, und
* ein 40 x 80-Vorhang (20 Teile) auf Stufe Niedrig: Bildzeit gemessen.

★★ Arrays reisen ueber die QtWebEngine-Bruecke nicht zuverlaessig zurueck —
JS rechnet, Python fragt Zahlen oder JSON-Strings ab.
"""
import json
import os
import statistics
import time
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                       # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView            # noqa: E402
from PySide6.QtWebEngineCore import (QWebEngineSettings,         # noqa: E402
                                     QWebEngineProfile)
from PySide6.QtWebChannel import QWebChannel                     # noqa: E402
from PySide6.QtCore import QObject, QUrl, Signal, Slot           # noqa: E402
from _qt_lifecycle import destroy_webengine_view                 # noqa: E402

from src.core import led_matrix as LM                            # noqa: E402

_app = QApplication.instance() or QApplication([])

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HTML_PATH = os.path.join(_ROOT, "src", "ui", "visualizer", "stage_scene.html")

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05

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


# ── Matrizen wie der Assistent sie anlegt ────────────────────────────────────

def _angaben(bauform, **kw):
    a = LM.MatrixAngaben(breite_px=20, hoehe_px=12, breite_cm=100.0,
                         hoehe_cm=60.0, bauform=bauform, format="RGB",
                         verdrahtung="schlange", startecke="unten_rechts")
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def _profil(a):
    """Gestelltes Profil mit genau den Feldern, die ``viz_form`` liest."""
    return SimpleNamespace(bauform=a.bauform, matrix_angaben=a.als_json(),
                           manufacturer=None, name="")


def _teil_nutzlast(a, fid0, x=0.0, y=4.0, z=0.0):
    """Je Teil die Nutzlast, die ``_fixture_to_dict`` baut (Raster je Modus
    aus ``profil_payload``, Lage aus ``teil_lage``, Form aus ``viz_form``)."""
    out = []
    for t in LM.teile(a):
        order, drehung, flip = LM.teil_lage(a, t)
        out.append({
            "fid": fid0 + t.index, "label": f"T{t.index + 1}", "type": "matrix",
            "model": "matrix", "nHeads": t.zeilen * a.breite_px,
            "pixelOrder": order, "elementRotation": drehung,
            "elementFlip": flip, "gridRows": t.zeilen, "gridCols": a.breite_px,
            "nWhites": 0, "whiteRows": 0, "whiteCols": 0,
            "matrixForm": LM.viz_form(_profil(a), t.name),
            "x": x, "y": y, "z": z, "rotX": 0, "rotY": 0, "rotZ": 0,
            "r": 0, "g": 0, "b": 0, "intensity": 0, "pan": 128, "tilt": 128,
        })
    return out


def _erwartete_plaetze(a):
    """[[fid, lokaler Index, Zeile, Spalte], ...] ueber die ganze Matrix."""
    out = []
    for t in LM.teile(a):
        for i in range(t.zeilen * a.breite_px):
            r, c = LM.pixel_platz(a, t.erstes_pixel + i)
            out.append([t.index, i, r, c])
    return out


# ════════════════════════════════════════════════════════════════════════════
# 1. Python: die Form-Angabe in der Nutzlast
# ════════════════════════════════════════════════════════════════════════════

class VizFormTest(unittest.TestCase):

    def test_bestand_ohne_angaben_ist_panel_ohne_masse(self):
        p = SimpleNamespace(bauform="", matrix_angaben="", manufacturer=None, name="X")
        f = LM.viz_form(p, "16ch")
        self.assertEqual(f["bauform"], "panel")
        self.assertEqual((f["pitchW"], f["pitchH"]), (0.0, 0.0))
        self.assertTrue(f["geschaetzt"])
        self.assertEqual(LM.viz_form(None)["bauform"], "panel")

    def test_teile_kennen_ihre_anzeige_zeile(self):
        a = _angaben("vorhang")                 # 20 breit -> 8 Zeilen je Teil
        tl = LM.teile(a)
        self.assertEqual([t.zeilen for t in tl], [8, 4])
        formen = [LM.viz_form(_profil(a), t.name) for t in tl]
        # Startecke unten: Teil 1 (Verdrahtung beginnt unten) liegt UNTEN.
        self.assertEqual([f["teilZeile"] for f in formen], [4, 0])
        self.assertEqual(formen[0]["bauform"], "vorhang")
        self.assertEqual((formen[0]["pitchW"], formen[0]["pitchH"]), (50.0, 50.0))
        self.assertEqual((formen[0]["breiteM"], formen[0]["hoeheM"]), (1.0, 0.6))
        self.assertEqual((formen[0]["spalten"], formen[0]["zeilen"]), (20, 12))
        self.assertFalse(formen[0]["geschaetzt"])

    def test_ohne_flaeche_geschaetzt(self):
        a = _angaben("leiste", breite_cm=0.0, hoehe_cm=0.0)
        f = LM.viz_form(_profil(a), LM.teile(a)[0].name)
        self.assertTrue(f["geschaetzt"])
        self.assertEqual(f["bauform"], "leiste")

    def test_kaputte_angaben_werfen_nicht(self):
        p = SimpleNamespace(bauform="ring", matrix_angaben="{kaputt",
                            manufacturer=None, name="")
        self.assertEqual(LM.viz_form(p, "x")["bauform"], "ring")

    def test_matrix_form_for_ohne_profil_ist_leer(self):
        from src.core.app_state import matrix_form_for
        self.assertEqual(matrix_form_for(SimpleNamespace(fixture_profile_id=None)), {})

    def test_nutzlast_traegt_die_form(self):
        """``_fixture_to_dict`` reicht ``matrixForm`` nur bei Matrizen durch."""
        import types
        from unittest.mock import patch
        from src.core.database.models import PatchedFixture
        from src.ui.visualizer import visualizer_window as VW
        fake_self = SimpleNamespace(_state=SimpleNamespace(
            visualizer_positions={}, visualizer_rotations={}, visualizer_docks={}))
        form = {"bauform": "ring", "pitchW": 10.0, "pitchH": 10.0}
        for modell, erwartet in (("matrix", form), ("par", None)):
            fake_self._viz_model_for = types.MethodType(
                lambda self, f, m=modell: m, fake_self)
            fx = PatchedFixture(fid=3, label="M", fixture_profile_id=None,
                                mode_name="x", universe=1, address=1,
                                channel_count=3, fixture_type=modell)
            with patch.object(VW, "matrix_form_for", return_value=form):
                d = VW.VisualizerBridge._fixture_to_dict(fake_self, fx)
            self.assertEqual(d["matrixForm"], erwartet, modell)

    def test_altshow_ohne_neue_felder_laedt(self):
        """VIZ-114 fuehrt kein neues Show-Feld ein — eine Alt-Show mit einem
        Matrix-Geraet (ohne Bauform/Angaben) laedt unveraendert."""
        from src.core.show.show_file import _patched_fixture_from_data
        alt = {"fid": 7, "label": "Panel", "fixture_profile_id": 1,
               "mode_name": "48ch", "universe": 1, "address": 1,
               "channel_count": 48, "fixture_type": "matrix"}
        fx = _patched_fixture_from_data(alt, 7)
        self.assertEqual(fx.fid, 7)
        self.assertEqual(fx.pixel_order, "rowwise")


# ════════════════════════════════════════════════════════════════════════════
# 2. Die gebauten Modelle in der echten Szene
# ════════════════════════════════════════════════════════════════════════════

_BAUFORMEN = ("panel", "vorhang", "leiste", "ring", "saeule")
_FID0 = {b: 600000 + 100 * k for k, b in enumerate(_BAUFORMEN)}
_BESTAND = 600900        # Panel ohne matrixForm (Bestand)
_BESTAND_PANELFORM = 600901   # matrixForm nur mit Bauform 'panel', keine Flaeche

_HELFER = """
window.__v114 = {
  f: function (fid) { return window.__lightos.fixtures[String(fid)]; },
  instanzen: function (fid) {
    let n = 0; this.f(fid).group.traverse(function (o) { if (o.isInstancedMesh) n++; });
    return n;
  },
  meshes: function (fid) {
    let n = 0; this.f(fid).group.traverse(function (o) { if (o.isMesh) n++; });
    return n;
  },
  // Abgleich Lage: jedes Pixel (fid, i) muss global (R, c) = erwartet haben.
  lageFehler: function (fid0, erwartet) {
    let fehler = 0;
    for (const e of erwartet) {
      const p = this.f(fid0 + e[0]).pixels[e[1]];
      if (!p || p.R !== e[2] || p.c !== e[3]) fehler++;
    }
    return fehler;
  },
  // Pixel nacheinander anschalten: leuchtet die Instanz an derselben Stelle?
  leuchtFehler: function (fid0, erwartet, stichprobe) {
    let fehler = 0;
    const L = window.__lightos;
    for (let k = 0; k < erwartet.length; k += stichprobe) {
      const e = erwartet[k];
      const fid = fid0 + e[0], f = this.f(fid);
      const heads = [];
      for (let i = 0; i < f.matrixInstanz.anzahl; i++)
        heads.push(i === e[1] ? {r: 255, g: 0, b: 0} : {r: 0, g: 0, b: 0});
      L.applyDmx([{fid: fid, r: 0, g: 0, b: 0, intensity: 255, heads: heads}]);
      const fa = f.matrixInstanz.farben;
      let hell = -1, nHell = 0;
      for (let i = 0; i < f.matrixInstanz.anzahl; i++)
        if (fa[3 * i] > 0.5) { hell = i; nHell++; }
      const p = f.pixels[hell];
      if (nHell !== 1 || !p || p.R !== e[2] || p.c !== e[3]) fehler++;
    }
    return fehler;
  },
  // Abstand Pixel i -> j im Modell
  abstand: function (fid, i, j) {
    const a = this.f(fid).pixels[i], b = this.f(fid).pixels[j];
    return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
  },
  // Bestands-Panel: Fingerabdruck aus Lage + Groesse aller Meshes
  abdruck: function (fid) {
    const out = [];
    this.f(fid).group.traverse(function (o) {
      if (!o.isMesh) return;
      const p = o.geometry.parameters || {};
      out.push([o.geometry.type, +(p.width || 0).toFixed(6), +(p.height || 0).toFixed(6),
                +o.position.x.toFixed(6), +o.position.y.toFixed(6), +o.position.z.toFixed(6)]);
    });
    return JSON.stringify(out);
  },
};
true
"""


class _SzeneBasis(unittest.TestCase):
    STUFE = "high"

    def setUp(self):
        self.assertTrue(os.path.isfile(_HTML_PATH), f"fehlt: {_HTML_PATH}")
        self._view = QWebEngineView()
        try:
            self._view.page().profile().setHttpCacheType(
                QWebEngineProfile.HttpCacheType.NoCache)
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

    def _eval(self, js, timeout=_POLL_TIMEOUT_S):
        box = []
        self._view.page().runJavaScript(js, box.append)
        ende = time.monotonic() + timeout
        while not box and time.monotonic() < ende:
            _app.processEvents()
            time.sleep(0.005)
        self.assertTrue(box, f"runJavaScript ohne Callback: {js[:120]}")
        return box[0]

    def _zahl(self, js):
        wert = self._eval(js)
        self.assertIsNotNone(wert, f"kein Wert fuer: {js[:160]}")
        return float(wert)

    def _aufbauen(self, nutzlast, letzte_fid):
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}&gputier={self.STUFE}")
        self._view.load(url)
        ende = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._geladen and time.monotonic() < ende:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._geladen and self._geladen[-1], "Page nicht geladen")
        ende = time.monotonic() + _POLL_TIMEOUT_S
        while time.monotonic() < ende and not self._eval("!!window.__lightosAppReady"):
            time.sleep(_POLL_INTERVAL_S)
        text = json.dumps(nutzlast)
        ende = time.monotonic() + 2 * _POLL_TIMEOUT_S
        da = False
        while time.monotonic() < ende:
            self._bridge.allFixtures.emit(text)
            if self._eval(f"typeof window.__lightos.fixtures['{letzte_fid}'] === 'object'"):
                da = True
                break
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(da, "allFixtures kam nie an")
        self._eval(_HELFER)


def _bestand(fid, **kw):
    d = {"fid": fid, "label": f"P{fid}", "type": "matrix", "model": "matrix",
         "nHeads": 48, "pixelOrder": "serpentine", "elementRotation": 0,
         "elementFlip": False, "gridRows": 4, "gridCols": 12,
         "x": 0, "y": 5, "z": 0, "rotX": 0, "rotY": 0, "rotZ": 0,
         "r": 0, "g": 0, "b": 0, "intensity": 0, "pan": 128, "tilt": 128}
    d.update(kw)
    return d


class BauformenSceneTest(_SzeneBasis):

    def test_jede_bauform_masse_nummerierung_und_licht(self):
        nutzlast, letzte = [], None
        angaben = {b: _angaben(b) for b in _BAUFORMEN}
        for b in _BAUFORMEN:
            teile = _teil_nutzlast(angaben[b], _FID0[b])
            nutzlast += teile
            letzte = teile[-1]["fid"]
        nutzlast.append(_bestand(_BESTAND))
        nutzlast.append(_bestand(_BESTAND_PANELFORM,
                                 matrixForm={"bauform": "panel", "pitchW": 0,
                                             "pitchH": 0}))
        self._aufbauen(nutzlast, _BESTAND_PANELFORM)
        v = "window.__v114"

        for b in _BAUFORMEN:
            a = angaben[b]
            f0 = _FID0[b]
            with self.subTest(bauform=b):
                # (1) Modell vorhanden, als Instanzen, mit der richtigen Bauform
                for t in LM.teile(a):
                    fid = f0 + t.index
                    self.assertEqual(self._eval(f"{v}.f({fid}).matrixInstanz.bauform"), b)
                    self.assertEqual(self._zahl(f"{v}.instanzen({fid})"), 1,
                                     "alle Pixel eines Teils = EIN InstancedMesh")
                    self.assertEqual(self._zahl(f"{v}.f({fid}).matrixInstanz.anzahl"),
                                     t.zeilen * a.breite_px)
                    self.assertLessEqual(self._zahl(f"{v}.meshes({fid})"), 3,
                                         "Zeichenaufrufe je Teil bleiben klein")
                # (2) Masse (ganze Matrix, Meter)
                br = self._zahl(f"{v}.f({f0}).matrixInstanz.masse.breite")
                ho = self._zahl(f"{v}.f({f0}).matrixInstanz.masse.hoehe")
                if b in ("panel", "vorhang", "leiste"):
                    self.assertAlmostEqual(br, 1.0, places=6)
                    self.assertAlmostEqual(ho, 0.6, places=6)
                    # Nachbarpixel = Pixelabstand 5 cm (Zeile 0, Spalte 0 -> 1)
                    self.assertAlmostEqual(self._zahl(f"{v}.abstand({f0}, 0, 1)"),
                                           0.05, places=6)
                elif b == "ring":
                    self.assertAlmostEqual(br, 1.0, places=6, msg="Aussendurchmesser")
                    # aeusserste Pixelreihe: Radius D/2 - halbe Bandteilung
                    band = self._zahl(f"{v}.f({f0}).matrixInstanz.masse.band")
                    self.assertAlmostEqual(band, 0.5, places=6,
                                           msg="Band auf den Radius begrenzt")
                    rmax = self._zahl(
                        f"Math.max.apply(null, [{f0}, {f0 + 1}].flatMap(function (fid) {{"
                        f" return {v}.f(fid).pixels.map(function (p) {{"
                        f" return Math.hypot(p.x, p.y); }}); }}))")
                    self.assertAlmostEqual(rmax, 0.5 - 0.5 * 0.5 / 12, places=6)
                else:   # saeule
                    self.assertAlmostEqual(br, 1.0, places=6, msg="Durchmesser")
                    self.assertAlmostEqual(ho, 0.6, places=6)
                    self.assertEqual(self._zahl(
                        f"{v}.f({f0}).pixels.every(function (p) {{"
                        f" return Math.abs(Math.hypot(p.x, p.z) - 0.5) < 1e-9; }}) ? 1 : 0"), 1,
                        "alle Pixel auf dem Mantel")
                # (3) Nummerierung = Python (pixel_platz / Gesamt-Gruppe)
                erw = json.dumps(_erwartete_plaetze(a))
                self.assertEqual(self._zahl(f"{v}.lageFehler({f0}, {erw})"), 0,
                                 "3D-Pixel liegt woanders als in 2D/Gesamt-Gruppe")
                # (4) Pixel leuchten in der richtigen Reihenfolge
                self.assertEqual(self._zahl(f"{v}.leuchtFehler({f0}, {erw}, 7)"), 0)

        # (5) Master-Dimmer = EIN Skalar (wie beim Bestand intNorm*1.6)
        f0 = _FID0["vorhang"]
        self._eval(f"window.__lightos.applyDmx([{{fid: {f0}, r: 0, g: 0, b: 0, "
                   f"intensity: 128, heads: []}}])")
        self.assertAlmostEqual(
            self._zahl(f"{v}.f({f0}).matrixInstanz.hell.material.emissiveIntensity"),
            128 / 255 * 1.6, places=4)

        # (6) Bestands-Panel: alter Bau-Weg, unveraendert
        for fid in (_BESTAND, _BESTAND_PANELFORM):
            self.assertEqual(self._eval(f"{v}.f({fid}).matrixInstanz === null"), True)
            self.assertEqual(self._eval(f"!!{v}.f({fid}).pixels[0].mesh"), True)
            self.assertEqual(self._zahl(f"{v}.meshes({fid})"), 1 + 48)
        self.assertEqual(self._eval(f"{v}.abdruck({_BESTAND})"),
                         self._eval(f"{v}.abdruck({_BESTAND_PANELFORM})"),
                         "Panel ohne Flaeche muss pixelgleich zum Bestand sein")
        # Bestandsmass (VIZ-50a): 12x4 -> 0,5 m breit
        self.assertAlmostEqual(self._zahl(
            f"(function () {{ let w = 0; {v}.f({_BESTAND}).group.traverse(function (o) {{"
            f" if (o.isMesh && o.geometry.type === 'BoxGeometry') w = o.geometry.parameters.width; }});"
            f" return w; }})()"), 0.5, places=6)


# ════════════════════════════════════════════════════════════════════════════
# 3. Stufe Niedrig: 40 x 80-Vorhang, Bildzeit
# ════════════════════════════════════════════════════════════════════════════

_VORHANG0 = 610000

_BILD_JS = """
(function () {
  const L = window.__lightos;
  const c = document.querySelector('canvas');
  const gl = c && (c.getContext('webgl2') || c.getContext('webgl'));
  L.requestRender();
  const t0 = performance.now();
  L.__renderTick();
  gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(4));
  return performance.now() - t0;
})()
"""


def _lauf_js(fids, k):
    """Ein DMX-Stand fuer alle Teile (Lauflicht, je Bild verschoben)."""
    return f"""
(function () {{
  const fids = {json.dumps(fids)};
  const batch = [];
  for (let t = 0; t < fids.length; t++) {{
    const f = window.__lightos.fixtures[String(fids[t])];
    const heads = [];
    const n = f.matrixInstanz ? f.matrixInstanz.anzahl : f.pixels.length;
    for (let i = 0; i < n; i++) {{
      const v = ((i + t * 7 + {k}) % 40) < 8 ? 255 : 0;
      heads.push({{r: v, g: (i * 3) % 256, b: 255 - v}});
    }}
    batch.push({{fid: fids[t], r: 0, g: 0, b: 0, intensity: 255, heads: heads}});
  }}
  const t0 = performance.now();
  window.__lightos.applyDmx(batch);
  return performance.now() - t0;
}})()
"""


class _VorhangMessung(_SzeneBasis):
    """Laeuft NUR im Kindprozess (s. ``VorhangNiedrigMessungTest``)."""
    __test__ = False
    STUFE = "low"

    def runTest(self):
        pass

    def _messen(self, fids, runden=40, aufwaermen=15):
        dmx, bild = [], []
        for k in range(aufwaermen + runden):
            d = float(self._eval(_lauf_js(fids, k)) if fids else 0.0)
            b = float(self._eval(_BILD_JS))
            if k >= aufwaermen:
                dmx.append(d)
                bild.append(b)
            _app.processEvents()
        return dmx, bild

    def messung(self):
        a = LM.MatrixAngaben(breite_px=40, hoehe_px=80, breite_cm=400.0,
                             hoehe_cm=800.0, bauform="vorhang", format="RGB")
        teile = _teil_nutzlast(a, _VORHANG0, y=8.5)
        self.assertEqual(len(teile), 20, "40 breit RGB -> 4 Zeilen je Universum")
        self._view.resize(1280, 720)
        self._view.show()
        self._aufbauen(teile, teile[-1]["fid"])
        if self._eval("document.querySelector('canvas').getContext('webgl2')"
                      " .isContextLost()"):
            return {"kontext_verloren": True}
        fids = [t["fid"] for t in teile]
        v = "window.__v114"
        self.assertEqual(self._eval("window.__lightos.tierSettings.matrixPunktEcken"), 6)
        self.assertEqual(self._zahl(f"{v}.f({fids[0]}).matrixInstanz.mesh.geometry"
                                    f".parameters.segments"), 6,
                         "Stufe Niedrig: runde Pixel mit 6 Ecken")
        self.assertEqual(self._zahl(
            "Object.values(window.__lightos.fixtures).reduce(function (s, f) {"
            " return s + (f.matrixInstanz ? f.matrixInstanz.anzahl : 0); }, 0)"), 3200)
        self._eval("window.__lightos.fitAll && window.__lightos.fitAll()")

        vorher = self._zahl("window.__lightos.renderStats().count")
        dmx, bild = self._messen(fids)
        self.assertGreaterEqual(
            self._zahl("window.__lightos.renderStats().count") - vorher, 55,
            "jedes Messbild muss wirklich gezeichnet worden sein")
        gpu = self._eval(
            "(function () { const c = document.querySelector('canvas');"
            " const gl = c.getContext('webgl2') || c.getContext('webgl');"
            " const e = gl.getExtension('WEBGL_debug_renderer_info');"
            " return e ? gl.getParameter(e.UNMASKED_RENDERER_WEBGL)"
            " : gl.getParameter(gl.RENDERER); })()")
        # Das Bild ist nicht leer: irgendwo leuchten Vorhang-Pixel.
        hell = self._zahl(
            "(function () { const L = window.__lightos; L.requestRender();"
            " L.__renderTick(); const c = document.querySelector('canvas');"
            " const gl = c.getContext('webgl2'); const n = c.width * c.height;"
            " const px = new Uint8Array(4 * n);"
            " gl.readPixels(0, 0, c.width, c.height, gl.RGBA, gl.UNSIGNED_BYTE, px);"
            " let k = 0; for (let i = 0; i < n; i++) if (px[4*i] > 200) k++;"
            " return k; })()")
        verloren = self._eval("document.querySelector('canvas').getContext('webgl2')"
                              " .isContextLost()")
        # Vergleich: dieselbe Szene ohne Vorhang (leere Buehne)
        for fid in fids:
            self._bridge.fixtureRemoved.emit(fid)
        ende = time.monotonic() + _POLL_TIMEOUT_S
        while time.monotonic() < ende and self._zahl(
                "Object.keys(window.__lightos.fixtures).length") > 0:
            for fid in fids:
                self._bridge.fixtureRemoved.emit(fid)
            _pump(0.1)
        _d0, leer = self._messen([])
        # Vorher: dieselben 20 Teile OHNE Bauform-Angabe -> Bestands-Panel
        # (je Pixel ein eigenes Mesh mit eigenem Material).
        alt = [dict(t, matrixForm=None) for t in teile]
        text = json.dumps(alt)
        ende = time.monotonic() + 2 * _POLL_TIMEOUT_S
        while time.monotonic() < ende:
            self._bridge.allFixtures.emit(text)
            if self._eval(f"!!window.__lightos.fixtures['{fids[-1]}']"
                          f" && !window.__lightos.fixtures['{fids[-1]}'].matrixInstanz"):
                break
            _pump(0.1)
        dmx_alt, bild_alt = self._messen(fids)

        def p95(xs):
            return sorted(xs)[int(0.95 * (len(xs) - 1))]
        bericht = {
            "bild_median_ms": round(statistics.median(bild), 2),
            "bild_p95_ms": round(p95(bild), 2),
            "dmx_median_ms": round(statistics.median(dmx), 2),
            "dmx_p95_ms": round(p95(dmx), 2),
            "leer_median_ms": round(statistics.median(leer), 2),
            "leer_p95_ms": round(p95(leer), 2),
            "bestand_bild_median_ms": round(statistics.median(bild_alt), 2),
            "bestand_bild_p95_ms": round(p95(bild_alt), 2),
            "bestand_dmx_median_ms": round(statistics.median(dmx_alt), 2),
            "gpu": gpu,
            "kontext_verloren": bool(verloren),
            "rote_bildpunkte": int(hell),
        }
        return bericht


# ★ Unter QT_QPA_PLATFORM=offscreen verliert die Seite ihren WebGL-Kontext
# meist schon beim Start (Chromium: „SKIA: Failed to begin write access",
# danach isContextLost() = true und readPixels liefert nur Nullen). Jede
# Bildzeit waere dann eine Zeit fuer NICHTS — so sahen die ersten Zahlen dieser
# Messung aus (0,2 ms fuer die leere Buehne). Ohne GPU-Compositing bleibt der
# Kontext stehen und WebGL zeichnet ueber ANGLE auf der echten GPU; der Test
# prueft das (Kontext lebt, rote Bildpunkte im Bild).
_MESS_FLAGS = "--disable-gpu-compositing"


class VorhangNiedrigMessungTest(unittest.TestCase):
    """40 x 80-Vorhang (3200 Pixel in 20 Teilen) auf Stufe Niedrig: Bildzeit
    und DMX-Anwendung je Bild, gegen dieselbe Buehne ohne Vorhang."""

    def test_40x80_vorhang_auf_niedrig(self):
        import subprocess
        import sys
        hier = os.path.dirname(os.path.abspath(__file__))
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                   QTWEBENGINE_CHROMIUM_FLAGS=_MESS_FLAGS,
                   PYTHONPATH=os.pathsep.join([_ROOT, hier]))
        # Geht der Kontext trotzdem verloren, misst der Lauf nichts und wird
        # wiederholt, statt eine Zahl fuer ein leeres Bild zu melden.
        bericht, versuche = None, 0
        for versuche in range(1, 7):
            lauf = subprocess.run(
                [sys.executable, os.path.abspath(__file__), "--messen"],
                cwd=_ROOT, env=env,
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=600)
            zeile = next((z for z in lauf.stdout.splitlines()
                          if z.startswith("VIZ114-MESSUNG ")), None)
            self.assertIsNotNone(zeile, lauf.stdout[-2000:] + lauf.stderr[-2000:])
            bericht = json.loads(zeile.split(" ", 1)[1])
            if bericht.get("ok") and not bericht.get("kontext_verloren"):
                break
        if bericht.get("kontext_verloren"):
            self.skipTest(f"WebGL-Kontext in {versuche} Starts verloren — "
                          "auf diesem Rechner offscreen nicht messbar")
        bericht["versuche"] = versuche
        print("\nVIZ-114 Messung 40x80-Vorhang, Stufe Niedrig "
              "(offscreen, ohne GPU-Compositing):", json.dumps(bericht))
        self.assertTrue(bericht.get("ok"), bericht)
        self.assertFalse(bericht["kontext_verloren"],
                         "ohne lebenden WebGL-Kontext misst die Zeit nichts")
        # Budget auf Niedrig: Push 15 Hz -> 66 ms je Bild. Bild + DMX-Anwendung
        # muessen darunter bleiben.
        self.assertGreater(bericht["rote_bildpunkte"], 100,
                           "das Bild muss den Vorhang wirklich zeigen")
        self.assertLess(bericht["bild_p95_ms"] + bericht["dmx_p95_ms"], 66.0,
                        json.dumps(bericht))


def _messen_im_kindprozess():
    t = _VorhangMessung()
    t.setUp()
    try:
        bericht = t.messung()
        bericht["ok"] = True
    except Exception as e:                               # noqa: BLE001
        bericht = {"ok": False, "fehler": repr(e)}
    finally:
        t.tearDown()
    print("VIZ114-MESSUNG " + json.dumps(bericht), flush=True)


if __name__ == "__main__":
    import sys as _sys
    if "--messen" in _sys.argv:
        _messen_im_kindprozess()
    else:
        unittest.main()
