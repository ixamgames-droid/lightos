"""VIZ-13 3c Teil 2: Golden-Parity-Test fuer den updateDmx-Split der
FixtureType-Registry.

Der monolithische ``updateFixture``-DMX-Pfad (scene_src/fixtures/fixtures.js)
wird in pro-Typ-``updateDmx``-Handler der Registry zerlegt — als REINER
Refactor (byte-identisches Verhalten). Dieser Test belegt die Paritaet:

  * Er wurde VOR dem Refactor einmal gegen den unveraenderten Monolithen
    gefahren; dabei sind die Referenzwerte (Material-Farben/Opacities,
    Yoke/Head-Rotationen, Beam-Sichtbarkeiten, Icon-Tints, Multihead-
    Einzelwerte) in ``test_viz13c_updatedmx_golden.json`` eingefroren worden.
  * Nach dem Refactor muss er UNVERAENDERT gruen bleiben.

Geprueft werden Objekt-/Material-Zustaende (kein Pixel-Rendering — laeuft
offscreen ohne GPU): gleicher Harness wie ``test_viz13c1_topdown_polish.py``
(offscreen QWebEngineView + Mock-Bridge + runJavaScript-Polling; Signale
werden wiederholt emittiert, weil der QWebChannel-Connect asynchron aufbaut).

Rig: 14 Fixtures — einer pro Registry-Typ (par, moving_head, scanner, laser,
led_bar, dimmer, strobe, smoke, hazer), die drei Multihead-Modelle (par_bar,
mover_bar, spider), ein UNBEKANNTER Typ (PAR-Fallback-Pfad) und die FM-8
Pixel-Bar-Variante (led_bar mit model par_bar, nHeads>=6). Zwei Batches:
"ON" (nicht-triviale Werte: intensity 180, pan 200, tilt 64, individuelle
Kopf-Farben) und "OFF" (intensity 0 — Unlit-/visible=false-Pfade).

Einfrier-Mechanik: Fehlt die Golden-Datei, schreibt der Lauf sie NEU und
schlaegt trotzdem fehl ("neu erzeugt — pruefen und erneut laufen"), damit
ein geloeschtes Golden niemals still neu einfriert. Sanity-Asserts gegen
Trivialitaet (Beams sichtbar, Rotationen != 0, Koepfe individuell gefaerbt)
laufen in JEDEM Fall vor Schreiben/Vergleich.
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
_GOLDEN_PATH = os.path.join(
    os.path.dirname(__file__), "test_viz13c_updatedmx_golden.json")

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05

# Signal-Liste 1:1 aus visualizer_window.py::VisualizerBridge (bridge.js
# guardet jeden Connect mit ``if (bridge.X)`` — die volle Liste haelt den
# Mock identisch zur Produktiv-Bridge; gleicher Mock wie im 3c-1-Test).
_SIGNAL_SPECS = [
    ("fixtureAdded", (str,)),
    ("fixtureRemoved", (int,)),
    ("dmxBatch", (str,)),
    ("allFixtures", (str,)),
    ("settingsChanged", (str,)),
    ("viewModeChanged", (str,)),
    ("editModeChanged", (str,)),
    ("stageLoaded", (str,)),
    ("addStageObject", (str,)),
    ("removeStageObject", (str,)),
    ("selectStageObject", (str,)),
    ("applyFixtureTransform", (str,)),
    ("alignSelected", (str,)),
    ("distributeSelected", (str,)),
    ("cameraReset", ()),
    ("brightnessSignal", (float,)),
    ("brightnessAutoSignal", ()),
    ("updateStageObject", (str,)),
    ("resizeModeSignal", (bool,)),
    ("pixelRatioSignal", (float,)),
]


def _make_mock_bridge_class():
    attrs = {}
    for name, arg_types in _SIGNAL_SPECS:
        attrs[name] = Signal(*arg_types)

    @Slot()
    def requestFixtures(self):
        self._request_fixtures_calls = getattr(self, "_request_fixtures_calls", 0) + 1

    attrs["requestFixtures"] = requestFixtures
    attrs["requestFullResync"] = Signal()

    return type("MockVisualizerBridge", (QObject,), attrs)


_MockVisualizerBridge = _make_mock_bridge_class()


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


# ── Test-Rig: 14 Fixtures, einer pro Registry-Pfad ───────────────────────────
# fid 32 = absichtlich unbekannter Typ -> REGISTRY-Fallback (PAR-Pfad).
# fid 33 = FM-8 Pixel-Bar (type led_bar + model par_bar + nHeads 8) -> isParBar.
_FIXTURES = [
    {"fid": 20, "type": "par"},
    {"fid": 21, "type": "moving_head", "panRange": 540, "tiltRange": 270},
    {"fid": 22, "type": "scanner"},
    {"fid": 23, "type": "laser"},
    {"fid": 24, "type": "led_bar", "nHeads": 4},
    {"fid": 25, "type": "dimmer"},
    {"fid": 26, "type": "strobe"},
    {"fid": 27, "type": "smoke"},
    {"fid": 28, "type": "hazer"},
    {"fid": 29, "type": "par", "model": "par_bar", "nHeads": 4},
    {"fid": 30, "type": "moving_head", "model": "mover_bar", "nHeads": 4},
    {"fid": 31, "type": "moving_head", "model": "spider"},
    {"fid": 32, "type": "kaffeemaschine"},
    {"fid": 33, "type": "led_bar", "model": "par_bar", "nHeads": 8},
]
for _i, _f in enumerate(_FIXTURES):
    _f.update({"x": _i * 2, "y": 2, "z": 0, "rotX": 0, "rotY": 0, "rotZ": 0,
               "r": 0, "g": 0, "b": 0, "intensity": 0})
_FIXTURES_PAYLOAD = json.dumps(_FIXTURES)

_ALL_FIDS = [str(f["fid"]) for f in _FIXTURES]

# ── DMX-Batches ───────────────────────────────────────────────────────────────
_HEADS_PAR_BAR = [
    {"r": 255, "g": 0, "b": 0}, {"r": 0, "g": 255, "b": 0},
    {"r": 0, "g": 0, "b": 255}, {"r": 120, "g": 130, "b": 140},
]
_HEADS_MOVER_BAR = [
    {"r": 255, "g": 0, "b": 0, "pan": 32, "tilt": 96},
    {"r": 0, "g": 255, "b": 0, "pan": 96, "tilt": 160},
    {"r": 0, "g": 0, "b": 255, "pan": 160, "tilt": 32},
    {"r": 200, "g": 200, "b": 0, "pan": 224, "tilt": 200},
]
_HEADS_SPIDER = [
    {"cr": 255, "cg": 64, "cb": 0, "cw": 32, "tilt": 96},
    {"cr": 0, "cg": 128, "cb": 255, "cw": 0, "tilt": 180},
]
_HEADS_PIXEL_BAR = [
    {"r": 255, "g": 0, "b": 0}, {"r": 255, "g": 128, "b": 0},
    {"r": 255, "g": 255, "b": 0}, {"r": 0, "g": 255, "b": 0},
    {"r": 0, "g": 255, "b": 255}, {"r": 0, "g": 0, "b": 255},
    {"r": 128, "g": 0, "b": 255}, {"r": 255, "g": 0, "b": 255},
]
_MULTI_HEADS = {29: _HEADS_PAR_BAR, 30: _HEADS_MOVER_BAR,
                31: _HEADS_SPIDER, 33: _HEADS_PIXEL_BAR}


def _make_batch(intensity):
    batch = []
    for f in _FIXTURES:
        d = {"fid": f["fid"], "r": 200, "g": 100, "b": 50,
             "intensity": intensity, "pan": 200, "tilt": 64}
        if f["fid"] in _MULTI_HEADS:
            d["heads"] = _MULTI_HEADS[f["fid"]]
        batch.append(d)
    return json.dumps(batch)


_BATCH_ON = _make_batch(180)
_BATCH_OFF = _make_batch(0)

# ── Auslese-JS: kompletter Objekt-Zustand aller 14 Fixtures ──────────────────
# r4 = 4-Nachkommastellen-Rundung JS-seitig (Auflage: keine Float-Schwanz-
# Brueche zwischen Einfrieren und Vergleich). Defensive Navigation: fehlende
# Refs -> null, damit ein JS-Fehler nie den ganzen Dump abbricht.
_DUMP_JS = """
(function() {
    const r4 = v => (v == null || isNaN(v)) ? null : Math.round(v * 10000) / 10000;
    const hx = c => (c && c.getHex) ? c.getHex() : null;
    const mat = o => (o && o.material) ? o.material : null;
    function dump(fid) {
        const f = window.__lightos.fixtures[fid];
        if (!f) return null;
        const bm = mat(f.beam), fm = mat(f.floorSpot);
        const lem = mat(f.lens), lam = mat(f.lamp);
        const out = {
            type: f.type,
            beam: f.beam ? { hex: hx(bm.color), op: r4(bm.opacity), vis: f.beam.visible } : null,
            spot: f.spot ? { hex: hx(f.spot.color), inten: r4(f.spot.intensity) } : null,
            floorSpot: f.floorSpot ? { hex: hx(fm.color), op: r4(fm.opacity),
                                       vis: f.floorSpot.visible,
                                       x: r4(f.floorSpot.position.x),
                                       z: r4(f.floorSpot.position.z) } : null,
            lens: lem ? { emHex: hx(lem.emissive), emInt: r4(lem.emissiveIntensity) } : null,
            lamp: lam ? { emHex: hx(lam.emissive), emInt: r4(lam.emissiveIntensity) } : null,
            laser: (f.laserBeams && f.laserBeams.length) ? {
                n: f.laserBeams.length,
                hex0: hx(mat(f.laserBeams[0]).color),
                op0: r4(mat(f.laserBeams[0]).opacity),
                vis0: f.laserBeams[0].visible } : null,
            yokeRotY: f.yoke ? r4(f.yoke.rotation.y) : null,
            headRotX: f.head ? r4(f.head.rotation.x) : null,
            lastPanRad: (f._lastPanRad !== undefined) ? r4(f._lastPanRad) : null,
            icon: f.icon ? {
                yaw: r4(f.icon.rotation.y),
                bodyHex: hx(f.icon.userData.body.material.color),
                bodyOp: r4(f.icon.userData.body.material.opacity),
                cells: f.icon.userData.cells
                    ? f.icon.userData.cells.map(c => hx(c.material.color)) : null,
                cellOps: f.icon.userData.cells
                    ? f.icon.userData.cells.map(c => r4(c.material.opacity)) : null,
            } : null,
            bars: f.bars ? f.bars.map(bar => ({
                tilt: r4(bar.pivot.rotation.x),
                lensEmHex: bar.lenses.map(l => hx(mat(l).emissive)),
                lensEmInt: bar.lenses.map(l => r4(mat(l).emissiveIntensity)),
                beamHex: bar.beams.map(b => hx(mat(b).color)),
                beamOp: bar.beams.map(b => r4(mat(b).opacity)),
                beamVis: bar.beams.map(b => b.visible),
            })) : null,
            parHeads: f.parHeads ? f.parHeads.map(ph => ({
                lensHex: hx(mat(ph.lens).color),
                emHex: hx(mat(ph.lens).emissive),
                emInt: r4(mat(ph.lens).emissiveIntensity),
                beamHex: ph.beam ? hx(mat(ph.beam).color) : null,
                beamOp: ph.beam ? r4(mat(ph.beam).opacity) : null,
                beamVis: ph.beam ? ph.beam.visible : null,
            })) : null,
            moverHeads: f.moverHeads ? f.moverHeads.map(mh => ({
                yokeRotY: r4(mh.yoke.rotation.y),
                headRotX: r4(mh.head.rotation.x),
                lensHex: hx(mat(mh.lens).color),
                emHex: hx(mat(mh.lens).emissive),
                emInt: r4(mat(mh.lens).emissiveIntensity),
                beamHex: mh.beam ? hx(mat(mh.beam).color) : null,
                beamOp: mh.beam ? r4(mat(mh.beam).opacity) : null,
                beamVis: mh.beam ? mh.beam.visible : null,
            })) : null,
        };
        return out;
    }
    const res = {};
    for (const fid of %s) res[fid] = dump(fid);
    return JSON.stringify(res);
})()
""" % json.dumps(_ALL_FIDS)


class UpdateDmxGoldenParityTest(unittest.TestCase):
    maxDiff = None

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
        self.assertTrue(self._poll_until_true("!!window.__lightosAppReady"))

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
        self.fail(f"Timeout beim Warten auf truthy '{js_expr}' (letzter Wert: {last!r})")

    def _emit_until_true(self, emit_fn, js_expr, timeout_s=_POLL_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            emit_fn()
            last = self._eval(js_expr)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout nach wiederholtem Emit fuer '{js_expr}' (letzter Wert: {last!r})")

    def _dump(self):
        raw = self._eval(_DUMP_JS)
        self.assertTrue(raw, "Dump-JS lieferte kein Ergebnis")
        return json.loads(raw)

    # ── Sanity: eingefrorene Werte duerfen nicht trivial sein ────────────────
    def _sanity_check(self, on, off):
        for fid in _ALL_FIDS:
            self.assertIsNotNone(on.get(fid), f"Fixture {fid} fehlt im ON-Dump")
        # (1) MH-Yoke folgt pan=200 ueber panRange 540 (nicht 0, nicht Default).
        self.assertIsNotNone(on["21"]["yokeRotY"])
        self.assertNotEqual(on["21"]["yokeRotY"], 0)
        # (2) Beam bei intensity 180 sichtbar (3D-Modus, showCones default an).
        self.assertTrue(on["21"]["beam"]["vis"], "MH-Beam unsichtbar trotz DMX an")
        self.assertTrue(on["20"]["beam"]["vis"], "PAR-Beam unsichtbar trotz DMX an")
        # (3) Multihead: die 4 PAR-Bar-Zellen sind individuell gefaerbt.
        cells = on["29"]["icon"]["cells"]
        self.assertEqual(len(cells), 4)
        self.assertEqual(len(set(cells)), 4, f"PAR-Bar-Zellen nicht individuell: {cells}")
        # (4) Mover-Bar: Koepfe haben individuelle Pan-Rotationen.
        mh = on["30"]["moverHeads"]
        self.assertNotEqual(mh[0]["yokeRotY"], mh[1]["yokeRotY"])
        # (5) OFF: Beam unsichtbar, Icon zurueck auf Unlit-Fill.
        self.assertFalse(off["20"]["beam"]["vis"], "PAR-Beam sichtbar trotz intensity 0")
        self.assertEqual(off["20"]["icon"]["bodyHex"], 0x4A4E5E,
                         "PAR-Icon nicht auf ICON_UNLIT_FILL zurueckgefallen")
        # (6) Fallback-Typ (fid 32) laeuft ueber den PAR-Pfad (beam vorhanden).
        self.assertIsNotNone(on["32"]["beam"], "Fallback-Fixture ohne Beam")
        # (7) Spider: zwei Bars mit unterschiedlichem Tilt (96 vs 180).
        bars = on["31"]["bars"]
        self.assertEqual(len(bars), 2)
        self.assertNotEqual(bars[0]["tilt"], bars[1]["tilt"])

    def test_updatedmx_golden_parity(self):
        self._load_and_wait()
        self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(_FIXTURES_PAYLOAD),
            "typeof window.__lightos.fixtures['33'] === 'object'", timeout_s=8.0)

        # ON-Batch anwenden (Wartekriterium: MH-Yoke hat rotiert).
        self._emit_until_true(
            lambda: self._bridge_obj.dmxBatch.emit(_BATCH_ON),
            "window.__lightos.fixtures['21'].yoke.rotation.y !== 0", timeout_s=8.0)
        actual_on = self._dump()

        # OFF-Batch anwenden (Wartekriterium: MH-Beam-Opacity auf 0).
        self._emit_until_true(
            lambda: self._bridge_obj.dmxBatch.emit(_BATCH_OFF),
            "window.__lightos.fixtures['21'].beam.material.opacity === 0", timeout_s=8.0)
        actual_off = self._dump()

        actual = {"on": actual_on, "off": actual_off}
        self._sanity_check(actual_on, actual_off)

        if not os.path.isfile(_GOLDEN_PATH):
            with open(_GOLDEN_PATH, "w", encoding="utf-8") as fh:
                json.dump(actual, fh, indent=1, sort_keys=True)
            self.fail(
                f"Golden-Datei fehlte und wurde NEU erzeugt: {_GOLDEN_PATH}\n"
                "Werte pruefen (Sanity-Asserts sind bereits gruen) und den Test "
                "erneut laufen lassen — er vergleicht dann strikt dagegen.")

        with open(_GOLDEN_PATH, encoding="utf-8") as fh:
            golden = json.load(fh)
        self.assertEqual(golden, actual,
                         "updateFixture-Verhalten weicht vom eingefrorenen Golden ab")


if __name__ == "__main__":
    unittest.main()
