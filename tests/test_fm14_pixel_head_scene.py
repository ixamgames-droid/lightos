"""FM-14 — der Ring am Moving Head im 3D, in echter QWebEngine gemessen.

Der Python-Teil (``test_fm14_pixel_head.py``) belegt, dass das Geraet mit
seinem echten Chart in der Bibliothek steht, dass die Routing-Regel kein
Bestandsgeraet umstellt und dass Pixel N auf Kopf N liegt. Hier wird gemessen,
was daraus im BILD wird:

* der Kopf bekommt **19 einzelne Segment-Meshes** — und sonst gar nichts,
* sie liegen als **Ringe** um die Mitte, in der Reihenfolge des Manuals
  (Pixel 1 Mitte, 2-7 Innenring, 8-19 Aussenring, im Uhrzeigersinn),
* jedes zeigt seinen **eigenen** DMX-Wert, nicht den der Hauptlinse,
* der Kopf **schwenkt** wie jeder andere Moving Head,
* und das **2D-Icon** faerbt dieselben Segmente an denselben Stellen.

★ Gemessen ueber den ECHTEN Weg: ``bridge.allFixtures`` -> ``addFixture`` ->
Registry -> ``buildPixelHead``, dazu ``bridge.dmxBatch`` -> ``updateFixture`` ->
``updatePixelHeadDmx``. Ein Test, der die Builder direkt aufruft, haette die
Registry-Zeile nicht abgedeckt — genau so ist VIZ-51 fuer ``pixelOrder``
durchgefallen: Feld vorhanden, Funktion richtig, Nutzlast leer.

★★ Die Positivkontrolle ist hier nicht Beiwerk: MH8/MH16 sind Bestandsgeraete
in echten Shows. Deshalb steht ein gewoehnlicher Moving Head im selben Rig und
wird MIT GEZAEHLT (Mesh-Zahl, Linse, Pan/Tilt) — die Mesh-Zahl faellt auch dann
auf, wenn etwas gebaut, aber nirgends eingetragen wuerde.

★★★ Arrays reisen ueber die QtWebEngine-Bruecke nicht zuverlaessig zurueck.
Jede Messung fragt deshalb einen EINZELNEN Zahlen-/Wahrheitswert ab.
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


# ── Die Geraete der Szene ───────────────────────────────────────────────────
_SPIIDER = 510301   # Robe Spiider, Mode 7: 20 Baenke -> 19 Ring-Segmente
_NORMAL = 510302    # gewoehnlicher Moving Head (Positivkontrolle MH8/MH16)
_WASH = 510303      # DERSELBE Spiider im Wash-Modus: eine Bank, kein Ring
_KLEIN = 510304     # Pixel-Kopf mit nur EINEM Segment (Randfall)


def _payload():
    def p(fid, **kw):
        d = {"fid": fid, "label": f"F{fid}", "type": "moving_head",
             "model": "moving_head", "nHeads": 0,
             "x": 0, "y": 5, "z": 0, "rotX": 0, "rotY": 0, "rotZ": 0,
             "panRange": 540, "tiltRange": 220, "panZero": 128, "tiltZero": 128,
             "r": 0, "g": 0, "b": 0, "intensity": 0, "pan": 128, "tilt": 128}
        d.update(kw)
        return d
    return json.dumps([
        p(_SPIIDER, model="pixel_head", nHeads=20, x=-4),
        p(_NORMAL, x=0),
        p(_WASH, x=4),                       # nHeads 0 -> Modell moving_head
        p(_KLEIN, model="pixel_head", nHeads=2, x=8),
    ])


def _heads(pro_kopf=None):
    """20 Koepfe, wie ``_build_fixture_payload`` sie fuer den Pixel-Modus
    liefert (Kopf 0 = Grundfarbe, Kopf 1..19 = Pixel 1..19)."""
    pro_kopf = pro_kopf or {}
    hs = []
    for j in range(20):
        h = {"r": 0, "g": 0, "b": 0, "cr": 0, "cg": 0, "cb": 0, "cw": 0,
             "pan": 128, "tilt": 128}
        h.update(pro_kopf.get(j, {}))
        hs.append(h)
    return hs


# Grundfarbe ROT (Kopf 0), Pixel 3 GRUEN (Kopf 3). Wer die Segmente aus der
# Geraetefarbe faerbt, macht hier den ganzen Ring rot.
_ROT_MIT_GRUENEM_PIXEL = json.dumps([{
    "fid": _SPIIDER, "r": 255, "g": 0, "b": 0, "intensity": 255,
    "heads": _heads({0: {"r": 255}, 3: {"g": 255}}),
}])

# Nur Kopf 1 (Pixel 1 = Mitte) blau — die Probe auf die Verschiebung um eins.
_NUR_MITTE = json.dumps([{
    "fid": _SPIIDER, "r": 0, "g": 0, "b": 0, "intensity": 255,
    "heads": _heads({1: {"b": 255}}),
}])

# Bewegung: Pan/Tilt weg von der Mitte, fuer beide Koepfe gleich.
_SCHWENK = json.dumps([
    {"fid": _SPIIDER, "r": 0, "g": 0, "b": 0, "intensity": 200,
     "pan": 200, "tilt": 64, "heads": _heads()},
    {"fid": _NORMAL, "r": 0, "g": 0, "b": 0, "intensity": 200,
     "pan": 200, "tilt": 64},
])


_HELFER = """
window.__fm14 = {
  f: function (fid) { return window.__lightos.fixtures[String(fid)]; },
  ring: function (fid) { return this.f(fid).ringPixels || []; },
  seg: function (fid, i) { return this.ring(fid)[i].mesh; },
  meshes: function (fid) {
    let n = 0;
    this.f(fid).group.traverse(function (o) { if (o.isMesh) n++; });
    return n;
  },
  // Abstand eines Segments von der Kopfachse (Radius in der Linsenebene).
  radius: function (fid, i) {
    const p = this.seg(fid, i).position;
    return Math.sqrt(p.x * p.x + p.z * p.z);
  },
  zellen: function (fid) {
    const ic = this.f(fid).icon;
    return (ic && ic.userData && ic.userData.cells) ? ic.userData.cells : [];
  },
};
true
"""


class PixelHeadSceneTest(unittest.TestCase):

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

        nutzlast = _payload()
        ende = time.monotonic() + _POLL_TIMEOUT_S
        da = False
        while time.monotonic() < ende:
            self._bridge.allFixtures.emit(nutzlast)
            if self._eval(f"typeof window.__lightos.fixtures['{_KLEIN}'] "
                          f"=== 'object'"):
                da = True
                break
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(da, "allFixtures kam nie an (addFixture nie gelaufen)")
        self._eval(_HELFER)

    def _dmx(self, batch, pruefung):
        """Batch schicken, bis die Wirkung da ist (WebChannel ist deferred)."""
        ende = time.monotonic() + _POLL_TIMEOUT_S
        while time.monotonic() < ende:
            self._bridge.dmxBatch.emit(batch)
            if self._eval(pruefung):
                return True
            time.sleep(_POLL_INTERVAL_S)
        return False

    # ── (1) Der Ring steht da ───────────────────────────────────────────────

    def test_neunzehn_segmente_am_kopf_und_sonst_nichts(self):
        """★ Die Abnahme als Zahl: 20 Baenke -> 19 Segmente (Bank 0 ist die
        Geraetefarbe). Und die Mesh-Zahl belegt, dass der Kopf selbst
        unveraendert geblieben ist: genau 19 Meshes mehr als der gewoehnliche
        Moving Head, kein einziges anderes."""
        self._aufbauen()
        self.assertEqual(self._zahl(f"window.__fm14.ring({_SPIIDER}).length"), 19)
        normal = self._zahl(f"window.__fm14.meshes({_NORMAL})")
        pixel = self._zahl(f"window.__fm14.meshes({_SPIIDER})")
        self.assertEqual(pixel - normal, 19,
                         "der Pixel-Kopf darf sich vom Moving Head um genau "
                         "die Segmente unterscheiden")

    def test_der_kopf_behaelt_linse_kegel_und_spotlight(self):
        """Ein Pixel-Kopf ist ein Moving Head: er strahlt weiter EINEN Kegel.
        Ohne diese Zusage waere aus dem Geraet ein Direkt-Emitter geworden."""
        self._aufbauen()
        for feld in ("lens", "beam", "spot", "floorSpot", "yoke", "head"):
            self.assertEqual(
                self._zahl(f"window.__fm14.f({_SPIIDER}).{feld} ? 1 : 0"), 1,
                f"{feld} fehlt am Pixel-Kopf")

    def test_die_segmente_haengen_am_kopf_nicht_am_sockel(self):
        """Sie muessen mit Pan UND Tilt mitgehen — sonst blieben sie im Raum
        stehen, waehrend der Kopf schwenkt."""
        self._aufbauen()
        self.assertEqual(
            self._zahl(f"(function(){{ const f = window.__fm14.f({_SPIIDER});"
                       f" let a = window.__fm14.seg({_SPIIDER}, 0).parent;"
                       f" while (a && a !== f.head) a = a.parent;"
                       f" return a === f.head ? 1 : 0; }})()"), 1)

    # ── (2) Die Ringform aus dem Manual ─────────────────────────────────────

    def test_mitte_innenring_aussenring(self):
        """★ Die Anordnung des Manuals (S. 15) als Geometrie: Pixel 1 sitzt in
        der Mitte, 2-7 auf einem Ring, 8-19 auf einem doppelt so grossen. Ein
        Renderer, der die 19 Pixel einfach im Kreis auffaedelt, faellt hier
        durch."""
        self._aufbauen()
        r_mitte = self._zahl(f"window.__fm14.radius({_SPIIDER}, 0)")
        self.assertAlmostEqual(r_mitte, 0.0, places=9,
                               msg="Pixel 1 gehoert in die Mitte")
        r_innen = self._zahl(f"window.__fm14.radius({_SPIIDER}, 1)")
        r_aussen = self._zahl(f"window.__fm14.radius({_SPIIDER}, 7)")
        self.assertGreater(r_innen, 0.0)
        self.assertAlmostEqual(r_aussen / r_innen, 2.0, places=6,
                               msg="der Aussenring hat den doppelten Radius")
        # Jeder Ring ist wirklich ein Ring: gleicher Radius fuer alle Plaetze.
        for i in (2, 3, 4, 5, 6):
            self.assertAlmostEqual(
                self._zahl(f"window.__fm14.radius({_SPIIDER}, {i})"),
                r_innen, places=9, msg=f"Segment {i} faellt aus dem Innenring")
        for i in (12, 18):
            self.assertAlmostEqual(
                self._zahl(f"window.__fm14.radius({_SPIIDER}, {i})"),
                r_aussen, places=9, msg=f"Segment {i} faellt aus dem Aussenring")

    def test_der_ring_passt_in_die_linse(self):
        """Die Segmente sind Teil der Lichtaustrittsflaeche, kein Kranz um das
        Gehaeuse — sonst stuenden sie im Beam-Kegel."""
        self._aufbauen()
        r_aussen = self._zahl(f"window.__fm14.radius({_SPIIDER}, 7)")
        self.assertLess(r_aussen, 0.077,
                        "der Aussenring liegt ausserhalb der Linse")
        # ... und VOR der Hauptlinse, in Richtung Lichtausgang (-Y). Lieferten
        # beide dieselbe Ebene, flimmerten sie gegeneinander; laegen die
        # Segmente dahinter, waeren sie unsichtbar.
        y_seg = self._zahl(f"window.__fm14.seg({_SPIIDER}, 0).position.y")
        y_linse = self._zahl(f"window.__fm14.f({_SPIIDER}).lens.position.y")
        self.assertLess(y_seg, y_linse,
                        "die Segmente gehoeren vor die Hauptlinse")

    def test_die_reihenfolge_laeuft_im_uhrzeigersinn(self):
        """★★ Die Aussage, die ein Chase sichtbar macht — und die Ordnung, die
        NICHT geraten ist: laut Manual liegt Pixel 3 links, Pixel 6 rechts,
        Pixel 2 unten-links und Pixel 4 oben-links (Blick von vorn auf die
        Linse). In der Kopf-Ebene ist „rechts" = -X und „oben" = -Z. Ein
        gespiegelter Ring laesst ein Lauflicht andersherum laufen als am Rig.
        """
        self._aufbauen()
        # Pixel 3 (Index 2) liegt LINKS: +X, und genau auf der Waagerechten.
        x3 = self._zahl(f"window.__fm14.seg({_SPIIDER}, 2).position.x")
        z3 = self._zahl(f"window.__fm14.seg({_SPIIDER}, 2).position.z")
        self.assertGreater(x3, 0.0, "Pixel 3 gehoert nach links")
        self.assertAlmostEqual(z3, 0.0, places=9)
        # Pixel 6 (Index 5) liegt genau gegenueber.
        x6 = self._zahl(f"window.__fm14.seg({_SPIIDER}, 5).position.x")
        self.assertAlmostEqual(x6, -x3, places=9)
        # Pixel 2 (Index 1) unten-links, Pixel 4 (Index 3) oben-links.
        z2 = self._zahl(f"window.__fm14.seg({_SPIIDER}, 1).position.z")
        z4 = self._zahl(f"window.__fm14.seg({_SPIIDER}, 3).position.z")
        self.assertGreater(z2, 0.0, "Pixel 2 gehoert nach unten")
        self.assertLess(z4, 0.0, "Pixel 4 gehoert nach oben")
        self.assertAlmostEqual(z2, -z4, places=9)
        # Aussenring: Pixel 13/14 (Index 12/13) liegen oben, links und rechts
        # der Senkrechten — das pinnt den halben Schritt Versatz.
        x13 = self._zahl(f"window.__fm14.seg({_SPIIDER}, 12).position.x")
        x14 = self._zahl(f"window.__fm14.seg({_SPIIDER}, 13).position.x")
        z13 = self._zahl(f"window.__fm14.seg({_SPIIDER}, 12).position.z")
        self.assertLess(z13, 0.0, "Pixel 13 gehoert nach oben")
        self.assertGreater(x13, 0.0, "Pixel 13 liegt links der Senkrechten")
        self.assertAlmostEqual(x14, -x13, places=9,
                               msg="Pixel 13/14 liegen symmetrisch zur Senkrechten")

    # ── (3) Jedes Segment zeigt seinen EIGENEN Wert ─────────────────────────

    def test_ein_segment_zeigt_nicht_die_farbe_der_hauptlinse(self):
        """★★ Der Fall, der einen naiv gebauten Ring entlarvt: die Geraetefarbe
        ist ROT, nur Pixel 3 ist gruen. Wer die Segmente aus der Geraetefarbe
        faerbt (oder ohne Kopf-Daten darauf zurueckfaellt), macht hier den
        ganzen Ring rot."""
        self._aufbauen()
        ok = self._dmx(_ROT_MIT_GRUENEM_PIXEL,
                       f"window.__fm14.seg({_SPIIDER}, 2).material.color.g > 0.9")
        self.assertTrue(ok, "der DMX-Batch kam nie an")

        # Vorbedingung: die Hauptlinse zeigt die Geraetefarbe.
        self.assertEqual(
            self._zahl(f"window.__fm14.f({_SPIIDER}).lens.material.emissive.r"),
            1.0, "Vorbedingung: die Hauptlinse leuchtet rot")
        # Segment 2 = Pixel 3 = Kopf 3 -> gruen.
        self.assertEqual(
            self._zahl(f"window.__fm14.seg({_SPIIDER}, 2).material.color.g"), 1.0)
        self.assertEqual(
            self._zahl(f"window.__fm14.seg({_SPIIDER}, 2).material.color.r"), 0.0)
        # Alle anderen bleiben DUNKEL — auch das Segment in der Mitte.
        for i in (0, 1, 3, 18):
            self.assertEqual(
                self._zahl(f"window.__fm14.seg({_SPIIDER}, {i})"
                           f".material.color.r"), 0.0,
                f"Segment {i} zeigt die Farbe der Hauptlinse")
            self.assertEqual(
                self._zahl(f"window.__fm14.seg({_SPIIDER}, {i})"
                           f".material.emissive.r"), 0.0)

    def test_kopf_null_ist_die_geraetefarbe_und_kein_segment(self):
        """★ Die Verschiebung um eins, in der schaerfsten Richtung gemessen:
        NUR Kopf 1 (Pixel 1, die Mitte) leuchtet blau. Segment 0 muss es sein,
        Segment 1 darf es nicht sein."""
        self._aufbauen()
        ok = self._dmx(_NUR_MITTE,
                       f"window.__fm14.seg({_SPIIDER}, 0).material.color.b > 0.9")
        self.assertTrue(ok, "der DMX-Batch kam nie an")
        self.assertEqual(
            self._zahl(f"window.__fm14.seg({_SPIIDER}, 0).material.color.b"), 1.0)
        self.assertEqual(
            self._zahl(f"window.__fm14.seg({_SPIIDER}, 1).material.color.b"), 0.0,
            "der Ring ist um eins verschoben")
        self.assertEqual(
            self._zahl(f"window.__fm14.f({_SPIIDER}).lens.material.emissive.b"),
            0.0, "die Hauptlinse gehoert der Grundfarbe, nicht Pixel 1")

    def test_der_master_dimmer_wirkt_auf_die_segmente(self):
        """Ein Ring, der den Dimmer ignoriert, leuchtete im Blackout weiter."""
        self._aufbauen()
        self.assertTrue(self._dmx(
            _ROT_MIT_GRUENEM_PIXEL,
            f"window.__fm14.seg({_SPIIDER}, 2).material.emissiveIntensity > 0.1"))
        dunkel = json.dumps([{
            "fid": _SPIIDER, "r": 255, "g": 0, "b": 0, "intensity": 0,
            "heads": _heads({0: {"r": 255}, 3: {"g": 255}}),
        }])
        self.assertTrue(self._dmx(
            dunkel,
            f"window.__fm14.seg({_SPIIDER}, 2).material.emissiveIntensity === 0"))

    # ── (4) Der Kopf bewegt sich ────────────────────────────────────────────

    def test_der_pixel_kopf_schwenkt_wie_ein_moving_head(self):
        """★ ``f.type`` ist das RENDER-Modell. Ohne 'pixel_head' im Pan/Tilt-
        Guard stuende das Geraet stur geradeaus — und der Bodenfleck laege
        woanders als der Kegel."""
        self._aufbauen()
        ok = self._dmx(_SCHWENK,
                       f"Math.abs(window.__fm14.f({_SPIIDER}).yoke.rotation.y)"
                       f" > 0.01")
        self.assertTrue(ok, "der DMX-Batch kam nie an")
        pan_pix = self._zahl(f"window.__fm14.f({_SPIIDER}).yoke.rotation.y")
        tilt_pix = self._zahl(f"window.__fm14.f({_SPIIDER}).head.rotation.x")
        self.assertNotEqual(pan_pix, 0.0)
        self.assertNotEqual(tilt_pix, 0.0)
        # ★★ Positivkontrolle: der gewoehnliche Moving Head daneben bewegt sich
        # bei denselben Werten und demselben Bereich EXAKT gleich.
        pan_mh = self._zahl(f"window.__fm14.f({_NORMAL}).yoke.rotation.y")
        tilt_mh = self._zahl(f"window.__fm14.f({_NORMAL}).head.rotation.x")
        self.assertAlmostEqual(pan_pix, pan_mh, places=9)
        self.assertAlmostEqual(tilt_pix, tilt_mh, places=9)

    # ── (5) Das 2D-Icon zeigt dieselben Segmente ────────────────────────────

    def test_das_2d_icon_hat_dieselben_neunzehn_zellen(self):
        self._aufbauen()
        self.assertEqual(self._zahl(f"window.__fm14.zellen({_SPIIDER}).length"),
                         19)

    def test_das_2d_icon_faerbt_dasselbe_segment(self):
        """★ 2D und 3D duerfen nicht auseinanderlaufen (Lehre VIZ-51): dieselbe
        Nutzlast, dieselbe Zelle, dieselbe Farbe."""
        self._aufbauen()
        ok = self._dmx(_ROT_MIT_GRUENEM_PIXEL,
                       f"window.__fm14.zellen({_SPIIDER})[2].material.color.g"
                       f" > 0.9")
        self.assertTrue(ok, "der DMX-Batch kam nie an")
        self.assertEqual(
            self._zahl(f"window.__fm14.zellen({_SPIIDER})[2].material.color.r"),
            0.0)
        # Und die Zelle sitzt an derselben Stelle wie das 3D-Segment (gleiche
        # Vorzeichen in x/z — dieselbe Quelle, dieselbe Handedness).
        x_3d = self._zahl(f"window.__fm14.seg({_SPIIDER}, 1).position.x")
        z_3d = self._zahl(f"window.__fm14.seg({_SPIIDER}, 1).position.z")
        x_2d = self._zahl(f"window.__fm14.zellen({_SPIIDER})[1].position.x")
        z_2d = self._zahl(f"window.__fm14.zellen({_SPIIDER})[1].position.z")
        self.assertGreater(x_3d * x_2d, 0.0, "die Zelle liegt gespiegelt")
        self.assertGreater(z_3d * z_2d, 0.0, "die Zelle liegt gespiegelt")

    # ── (6) Positivkontrolle: der Bestand bleibt, wie er war ────────────────

    def test_ein_gewoehnlicher_moving_head_bekommt_keinen_ring(self):
        """★★ MH8/MH16 sind Bestandsgeraete in echten Shows. Kein Ring, keine
        zusaetzlichen Meshes, und die Linse folgt weiter der Geraetefarbe."""
        self._aufbauen()
        self.assertEqual(
            self._zahl(f"window.__fm14.f({_NORMAL}).ringPixels === null ? 1 : 0"),
            1, "ein Moving Head darf keine Segmente bekommen")
        self.assertEqual(
            self._zahl(f"window.__fm14.f({_NORMAL}).isPixelHead ? 1 : 0"), 0)
        self.assertEqual(self._zahl(f"window.__fm14.zellen({_NORMAL}).length"), 0,
                         "auch das 2D-Icon bleibt der einfache Kreis")

        rot = json.dumps([{"fid": _NORMAL, "r": 255, "g": 0, "b": 0,
                           "intensity": 255, "pan": 128, "tilt": 128}])
        self.assertTrue(self._dmx(
            rot,
            f"window.__fm14.f({_NORMAL}).lens.material.emissive.r > 0.9"),
            "die Linse des gewoehnlichen Moving Heads folgt der Farbe nicht mehr")
        self.assertGreater(
            self._zahl(f"window.__fm14.f({_NORMAL}).beam.material.opacity"), 0.0)

    def test_derselbe_spiider_im_wash_modus_hat_keinen_ring(self):
        """★ Der schaerfste Positivfall: dasselbe Geraet, gleiche Mechanik, nur
        eine Farb-Bank. Wer den Ring am Geraet statt an den Kanaelen festmacht,
        baut ihn hier auch."""
        self._aufbauen()
        self.assertEqual(
            self._zahl(f"window.__fm14.f({_WASH}).ringPixels === null ? 1 : 0"), 1)
        self.assertEqual(self._zahl(f"window.__fm14.meshes({_WASH})"),
                         self._zahl(f"window.__fm14.meshes({_NORMAL})"),
                         "der Wash-Modus ist ein gewoehnlicher Moving Head")

    def test_ein_pixel_kopf_mit_einem_einzigen_segment(self):
        """Randfall: zwei Baenke = Grundfarbe + EIN Pixel. Es gehoert in die
        Mitte, und der Handler darf daran nicht scheitern."""
        self._aufbauen()
        self.assertEqual(self._zahl(f"window.__fm14.ring({_KLEIN}).length"), 1)
        self.assertAlmostEqual(self._zahl(f"window.__fm14.radius({_KLEIN}, 0)"),
                               0.0, places=9)
        batch = json.dumps([{
            "fid": _KLEIN, "r": 0, "g": 0, "b": 0, "intensity": 255,
            "heads": [{"r": 0, "g": 0, "b": 0}, {"r": 0, "g": 0, "b": 255}],
        }])
        self.assertTrue(self._dmx(
            batch, f"window.__fm14.seg({_KLEIN}, 0).material.color.b > 0.9"))

    def test_ein_pixel_kopf_ohne_kopf_daten_faellt_nicht_auf_die_nase(self):
        """Ein Batch ohne ``heads`` (Alt-Nutzlast, transienter Zustand) darf den
        Handler nicht anhalten — und darf keine Farben erfinden."""
        self._aufbauen()
        ohne = json.dumps([{"fid": _SPIIDER, "r": 255, "g": 255, "b": 255,
                            "intensity": 255, "pan": 128, "tilt": 128}])
        self.assertTrue(self._dmx(
            ohne,
            f"window.__fm14.f({_SPIIDER}).lens.material.emissiveIntensity > 0.1"),
            "der Batch hat den Pixel-Kopf nicht erreicht")
        self.assertEqual(
            self._zahl(f"window.__fm14.seg({_SPIIDER}, 0).material.color.r"), 0.0,
            "ohne Kopf-Daten darf kein Segment die Geraetefarbe zeigen")


if __name__ == "__main__":
    unittest.main()
