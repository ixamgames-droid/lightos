"""VIZ-84: "Automatisch" stuft eine schnelle Grafikkarte unter Windows nicht
mehr als Niedrig ein.

Testbericht (Windows 11, RX 580): WebGL laeuft dort ueber ANGLE/Direct3D 11,
und das meldet fuer JEDE Grafikkarte ``MAX_TEXTURE_IMAGE_UNITS = 16``. Die alte
Probe (``maxTex <= 16 -> low``) gab damit Pixeldichte 1,25 und kein
Antialiasing — auch auf einer diskreten Karte.

Jetzt (``scene/gpu_tier.js``): erst der Renderer-Name aus
``WEBGL_debug_renderer_info``, dann eine kurze Frame-Zeit-Messung, erst
zuletzt die Texture-Units. ``?gputier`` (manuelle Stufe) bleibt vorrangig.

Zwei Teile: die reine Entscheidung unter Node (viele echte Renderer-Namen), und
die Verdrahtung in der echten Seite (offscreen) mit per Skript injiziertem
Renderer-Namen — dieselbe Seite meldet offscreen sonst nur ihren
Software-Renderer.
"""
import json
import os
import subprocess
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (QWebEngineProfile, QWebEngineScript,
                                     QWebEngineSettings)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

from _qt_lifecycle import destroy_webengine_view, destroy_all_top_level_widgets  # noqa: E402
import pytest

_app = QApplication.instance() or QApplication([])

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCENE = os.path.join(_REPO, "src", "ui", "visualizer", "scene_src")
_MODUL = os.path.join(_SCENE, "scene", "gpu_tier.js")
_HTML_PATH = os.path.join(_REPO, "src", "ui", "visualizer", "stage_scene.html")

RX580_ANGLE = ("ANGLE (AMD, AMD Radeon RX 580 2048SP Direct3D11 vs_5_0 ps_5_0, "
               "D3D11-31.0.21921.1000)")
# VIZ-99: der Renderer-Name, wie ihn der Windows-ARM-PC meldet (Snapdragon X Elite).
X1_85_ANGLE = ("ANGLE (Qualcomm, Qualcomm(R) Adreno(TM) X1-85 GPU (0x36334330) "
               "Direct3D11 vs_5_0 ps_5_0, D3D11)")


@pytest.fixture(autouse=True)
def _keine_fenster_lecks():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _node_verfuegbar() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=10)
        return True
    except Exception:                       # pragma: no cover
        return False


_TREIBER = """
import { classifyRenderer, decideTier } from './tier.mjs';
const FAELLE = %s;
const aus = FAELLE.map(f => {
  let gemessen = false;
  const r = decideTier({ chip: f.chip, maxTex: f.maxTex,
    messen: () => { gemessen = true; return f.ms; } });
  return { chip: f.chip, tier: r.tier, grund: r.grund, gemessen,
           klasse: classifyRenderer(f.chip).tier };
});
console.log(JSON.stringify(aus));
"""


def _entscheide(faelle):
    with open(_MODUL, encoding="utf-8") as fh:
        quelle = fh.read()
    with tempfile.TemporaryDirectory() as verz:
        with open(os.path.join(verz, "tier.mjs"), "w", encoding="utf-8") as fh:
            fh.write(quelle)
        with open(os.path.join(verz, "treiber.mjs"), "w", encoding="utf-8") as fh:
            fh.write(_TREIBER % json.dumps(faelle))
        p = subprocess.run(["node", os.path.join(verz, "treiber.mjs")],
                           capture_output=True, text=True, timeout=60)
        if p.returncode != 0:               # pragma: no cover
            raise AssertionError(p.stderr)
        return json.loads(p.stdout.strip())


@unittest.skipUnless(_node_verfuegbar(), "node fehlt")
class EntscheidungTest(unittest.TestCase):
    def _tier(self, chip, maxTex=16, ms=None):
        (r,) = _entscheide([{"chip": chip, "maxTex": maxTex, "ms": ms}])
        return r

    def test_diskrete_gpu_unter_angle_ist_hoch_trotz_16_units(self):
        for chip in (
            RX580_ANGLE,
            "ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 6GB Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "ANGLE (NVIDIA, NVIDIA RTX A2000 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "ANGLE (NVIDIA, NVIDIA Quadro P2000 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "ANGLE (Intel, Intel(R) Arc(TM) A770 Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "AMD Radeon RX 6600 (radeonsi, navi23, LLVM 15.0.7, DRM 3.49)",
            "AMD Radeon Pro WX 5100",
            "ANGLE (Apple, ANGLE Metal Renderer: Apple M2 Pro, Unspecified Version)",
        ):
            r = self._tier(chip, maxTex=16, ms=99)
            self.assertEqual(r["tier"], "high", chip)
            self.assertFalse(r["gemessen"], f"Name reicht, keine Messung: {chip}")

    def test_schwache_und_software_renderer_sind_niedrig(self):
        for chip in (
            "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "ANGLE (Intel, Intel(R) HD Graphics 520 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "Mesa Intel(R) UHD Graphics 620 (KBL GT2)",
            "ANGLE (Qualcomm, Adreno (TM) 690, OpenGL ES 3.2)",
            "Mali-G78 MP14",
            "Google SwiftShader",
            "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)), SwiftShader driver)",
            "llvmpipe (LLVM 15.0.7, 256 bits)",
            "ANGLE (Microsoft, Microsoft Basic Render Driver Direct3D11 vs_5_0 ps_5_0, D3D11)",
        ):
            r = self._tier(chip, maxTex=32, ms=0.1)
            self.assertEqual(r["tier"], "low", chip)
            self.assertFalse(r["gemessen"], chip)

    def test_unbekannter_name_entscheidet_die_frame_zeit(self):
        for chip in ("", "WebKit WebGL", "ANGLE (Unknown, Unknown Device, D3D11)",
                     "AMD Radeon(TM) Graphics", "Intel(R) Iris(R) Xe Graphics"):
            schnell = self._tier(chip, maxTex=16, ms=1.2)
            self.assertTrue(schnell["gemessen"], chip)
            self.assertEqual(schnell["tier"], "high", chip)
            self.assertIn("Frame-Zeit", schnell["grund"])
            langsam = self._tier(chip, maxTex=32, ms=40)
            self.assertEqual(langsam["tier"], "low", chip)

    def test_einstiegskarten_und_alte_apu_sind_niedrig(self):
        # Review-Befund: GT 710/MX150/920MX und "AMD Radeon R7 Graphics"
        # (Kaveri/Carrizo) fielen ueber "geforce" bzw. "radeon ... r[579]"
        # auf Hoch; unter ANGLE waren sie vorher Niedrig.
        for chip in (
            "ANGLE (NVIDIA, NVIDIA GeForce GT 710 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "ANGLE (NVIDIA, NVIDIA GeForce GT 1030 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "ANGLE (NVIDIA, NVIDIA GeForce MX150 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "ANGLE (NVIDIA, NVIDIA GeForce MX250 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "ANGLE (NVIDIA, NVIDIA GeForce 920MX Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "ANGLE (AMD, AMD Radeon R7 Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "ANGLE (AMD, AMD Radeon(TM) R5 Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
        ):
            r = self._tier(chip, maxTex=32, ms=0.1)
            self.assertEqual(r["tier"], "low", chip)
            self.assertFalse(r["gemessen"], chip)
        # Abgrenzung: echte Karten derselben Familien bleiben Hoch.
        for chip in ("NVIDIA GeForce GTX 1050 Ti", "NVIDIA GeForce RTX 2060",
                     "AMD Radeon R9 290", "AMD Radeon R7 260X"):
            self.assertEqual(self._tier(chip, maxTex=16, ms=99)["tier"], "high", chip)

    def test_warp_ist_software(self):
        r = self._tier("ANGLE (Microsoft, Microsoft Direct3D WARP Direct3D11 "
                       "vs_5_0 ps_5_0, D3D11)", maxTex=32, ms=0.1)
        self.assertEqual(r["tier"], "low")
        self.assertFalse(r["gemessen"])

    def test_adreno_x1_85_ist_hoch_ohne_messung(self):
        """VIZ-99: am Windows-ARM-PC gemessen — die Start-Messung streute dort
        von 6,6 bis 9,0 ms um die Grenze (6 ms), die Automatik waehlte Niedrig,
        obwohl Hoch im Leerlauf 60 und unter Bewegung 51-57 fps haelt."""
        for ms in (6.6, 7.2, 7.8, 9.0, 40.0):
            r = self._tier(X1_85_ANGLE, maxTex=16, ms=ms)
            self.assertEqual(r["tier"], "high", ms)
            self.assertFalse(r["gemessen"], "X1-85 entscheidet der Name, nicht die Messung")
            self.assertEqual(r["grund"], "Snapdragon X (Adreno X1-85)")
        # ohne die Geraete-Kennung in Klammern, wie ihn aeltere Treiber melden
        ohne_id = ("ANGLE (Qualcomm, Qualcomm(R) Adreno(TM) X1-85 GPU Direct3D11 "
                   "vs_5_0 ps_5_0, D3D11)")
        self.assertEqual(self._tier(ohne_id, ms=9.0)["tier"], "high")

    def test_uebrige_adreno_x_reihe_wird_gemessen(self):
        # X1-45 (Snapdragon X Plus mit 8 Kernen) und X2-… sind nicht gemessen:
        # weder pauschal Niedrig noch pauschal Hoch.
        for chip in ("ANGLE (Qualcomm, Qualcomm(R) Adreno(TM) X1-45 GPU Direct3D11 "
                     "vs_5_0 ps_5_0, D3D11)",
                     "ANGLE (Qualcomm, Qualcomm(R) Adreno(TM) X2-90 GPU Direct3D11 "
                     "vs_5_0 ps_5_0, D3D11)"):
            schnell = self._tier(chip, maxTex=16, ms=1.0)
            self.assertTrue(schnell["gemessen"], chip)
            self.assertEqual(schnell["tier"], "high", chip)
            self.assertIn("Snapdragon X, Frame-Zeit", schnell["grund"])
            self.assertEqual(self._tier(chip, maxTex=16, ms=9.0)["tier"], "low", chip)
        # aeltere Adreno bleiben pauschal Niedrig
        r = self._tier("ANGLE (Qualcomm, Adreno (TM) 690, OpenGL ES 3.2)", ms=1.0)
        self.assertEqual(r["tier"], "low")
        self.assertFalse(r["gemessen"])

    def test_ohne_messung_die_alte_texture_unit_regel(self):
        self.assertEqual(self._tier("", maxTex=16, ms=None)["tier"], "low")
        self.assertEqual(self._tier("", maxTex=32, ms=None)["tier"], "high")

    def test_probe_waehlt_nie_maximal(self):
        faelle = [{"chip": c, "maxTex": 32, "ms": 0.01}
                  for c in ("NVIDIA GeForce RTX 4090", "", "Apple M3 Max")]
        self.assertTrue(all(r["tier"] in ("low", "high") for r in _entscheide(faelle)))


# ── Verdrahtung in der echten Seite ──────────────────────────────────────────
_SIGNAL_SPECS = [
    ("fixtureAdded", (str,)), ("fixtureRemoved", (int,)),
    ("allFixtures", (str,)), ("settingsChanged", (str,)),
    ("viewModeChanged", (str,)), ("editModeChanged", (str,)),
    ("stageLoaded", (str,)), ("pixelRatioSignal", (float,)),
]


def _mock_bridge_class():
    attrs = {n: Signal(*t) for n, t in _SIGNAL_SPECS}

    @Slot()
    def requestFixtures(self):
        pass

    @Slot(result=str)
    def pollControl(self):
        return "{}"

    @Slot(str)
    def reportGpuTier(self, tier):
        self.gemeldet = tier

    attrs.update(requestFixtures=requestFixtures, pollControl=pollControl,
                 reportGpuTier=reportGpuTier, requestFullResync=Signal())
    return type("MockBridgeViz84", (QObject,), attrs)


_MockBridge = _mock_bridge_class()


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(0.02)


class ProbeInDerSeiteTest(unittest.TestCase):
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
        self._bridge_obj = _MockBridge()
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._bridge_obj)
        self._view.page().setWebChannel(self._channel)
        self._ok = []
        self._view.loadFinished.connect(self._ok.append)

    def tearDown(self):
        destroy_webengine_view(self._view, _pump)
        self._view = None

    def _eval(self, js):
        box = []
        self._view.page().runJavaScript(js, box.append)
        ende = time.monotonic() + 10
        while not box and time.monotonic() < ende:
            _app.processEvents()
            time.sleep(0.01)
        self.assertTrue(box, js)
        return box[0]

    def _laden(self, chip, bench_ms=None, gputier=None):
        stub = f"window.__lightosGpuRendererStub = {json.dumps(chip)};"
        if bench_ms is not None:
            stub += f" window.__lightosGpuBenchStub = {float(bench_ms)};"
        skript = QWebEngineScript()
        skript.setName("viz84-stub")
        skript.setSourceCode(stub)
        skript.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        skript.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        skript.setRunsOnSubFrames(False)
        skripte = self._view.page().scripts()
        for alt in skripte.find("viz84-stub"):
            skripte.remove(alt)
        skripte.insert(skript)
        url = QUrl.fromLocalFile(_HTML_PATH)
        query = f"v={int(time.time() * 1000)}"
        if gputier:
            query += f"&gputier={gputier}"
        url.setQuery(query)
        self._ok.clear()
        self._view.load(url)
        ende = time.monotonic() + 40
        while not self._ok and time.monotonic() < ende:
            _app.processEvents()
            time.sleep(0.05)
        self.assertTrue(self._ok and self._ok[-1])
        ende = time.monotonic() + 10
        while time.monotonic() < ende and not self._eval("!!window.__lightosAppReady"):
            time.sleep(0.05)
        return json.loads(self._eval(
            "(function(){ const L = window.__lightos; return JSON.stringify({"
            " tier: L.gpuTier, info: L.gpuProbeInfo(), cap: L.pixelRatioCap }); })()"))

    def test_rx580_unter_angle_wird_hoch(self):
        z = self._laden(RX580_ANGLE)
        if z["info"]["grund"] == "kein WebGL-Kontext":
            self.skipTest("offscreen ohne WebGL")
        self.assertEqual(z["tier"], "high", z)
        self.assertEqual(z["info"]["grund"], "diskrete GPU")
        self.assertEqual(z["info"]["chip"], RX580_ANGLE)
        self.assertEqual(z["cap"], 2, "Hoch: Pixeldichte bis 2")

    def test_intel_uhd_bleibt_niedrig_und_override_gewinnt(self):
        z = self._laden("ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)")
        if z["info"]["grund"] == "kein WebGL-Kontext":
            self.skipTest("offscreen ohne WebGL")
        self.assertEqual(z["tier"], "low", z)
        # manuelle Stufe schlaegt jeden Renderer-Namen
        z = self._laden(RX580_ANGLE, gputier="low")
        self.assertEqual(z["tier"], "low")
        self.assertEqual(z["info"]["grund"], "manuell (?gputier)")

    def test_adreno_x1_85_wird_hoch_auch_bei_langsamer_startmessung(self):
        """VIZ-99 in der echten Seite: mit der am Geraet gemessenen Start-Zeit
        (9,0 ms, ueber der Grenze) waehlte die Automatik Niedrig."""
        z = self._laden(X1_85_ANGLE, bench_ms=9.0)
        if z["info"]["grund"] == "kein WebGL-Kontext":
            self.skipTest("offscreen ohne WebGL")
        self.assertEqual(z["tier"], "high", z)
        self.assertEqual(z["info"]["grund"], "Snapdragon X (Adreno X1-85)")
        self.assertIsNone(z["info"]["benchMs"], "per Name entschieden, nicht gemessen")
        self.assertEqual(z["cap"], 2, "Hoch: Pixeldichte bis 2")

    def test_unbekannter_name_frame_zeit_rueckfall(self):
        z = self._laden("ANGLE (Unknown, Unknown Device, D3D11)", bench_ms=1.0)
        if z["info"]["grund"] == "kein WebGL-Kontext":
            self.skipTest("offscreen ohne WebGL")
        self.assertEqual(z["tier"], "high", z)
        self.assertEqual(z["info"]["benchMs"], 1.0)
        z = self._laden("ANGLE (Unknown, Unknown Device, D3D11)", bench_ms=50.0)
        self.assertEqual(z["tier"], "low", z)

    def test_echte_messung_laeuft_und_liefert_eine_zeit(self):
        """Ohne Bench-Stub misst die Seite wirklich (Software-Renderer offscreen:
        Ergebnis egal, es muss nur eine Zahl herauskommen und die Seite starten)."""
        z = self._laden("ANGLE (Unknown, Unknown Device, D3D11)")
        if z["info"]["grund"] == "kein WebGL-Kontext":
            self.skipTest("offscreen ohne WebGL")
        self.assertIn(z["tier"], ("low", "high"))
        ms = z["info"]["benchMs"]
        self.assertIsInstance(ms, (int, float), z)
        self.assertGreaterEqual(ms, 0)
        print(f"[VIZ-84] echte Messung: benchMs={ms:.2f} grund={z['info']['grund']}")


if __name__ == "__main__":
    unittest.main()
