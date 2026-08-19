"""VIZ-50b — die Warmweiss-Leiste im 3D, in echter QWebEngine gemessen.

Der Python-Teil (``test_viz50b_weissband.py``) belegt, dass die Zahl der
Weiss-Segmente aus den Kanaelen ABGELEITET wird (kein neues Feld) und dass
Segment j auf Kopf j sitzt. Hier wird gemessen, was daraus im Bild wird:

* acht Segmente, **halb so hoch** wie eine RGB-Zone,
* mittig **zwischen Reihe 2 und 3**, quer ueber die volle Breite,
* je **anderthalb** RGB-Spalten breit (8 auf 12),
* gefaerbt aus den **eigenen** Kanaelen (``heads[j].cw``), nicht aus der Farbe
  der RGB-Zone j.

★ CDX-52: die FORM dieser Leiste ist seit dem Item hinterlegt
(``whiteRows``/``whiteCols`` aus ``FixtureMode.white_rows/white_cols``) und wird
nicht mehr aus der Kanalzahl geschlossen. Die Nutzlast hier traegt sie deshalb
so, wie ``_fixture_to_dict`` sie schickt — und ``_ZWEI_REIHEN`` belegt, dass der
Renderer sie wirklich liest: ein Band aus ZWEI Reihen muss anders aussehen als
dasselbe Band aus einer. Ohne diesen Fall waere das Feld Zierde, und die
hinterlegte Form haette den Renderer nie erreicht (so ist VIZ-51 fuer
``pixelOrder`` durchgefallen).

★ Gemessen ueber den ECHTEN Weg: ``bridge.allFixtures`` -> ``addFixture`` ->
Registry -> ``buildMatrixPanel``, dazu ``bridge.dmxBatch`` -> ``updateFixture``
-> ``updateMatrixPanelDmx``. Ein Test, der die Builder direkt aufruft, haette
die Registry-Zeile (``o.nWhites``) nicht abgedeckt — genau so ist VIZ-51 fuer
``pixelOrder`` durchgefallen: Feld vorhanden, Funktion richtig, Nutzlast leer.

★★ Der Fall, der ein naiv gebautes Band entlarvt, ist ``_ROT_OHNE_WEISS``:
Zone 1 leuchtet rot, Weiss-Segment 1 ist aus. Wer das Band aus
``heads[j].r/g/b`` faerbt, malt es hier rot — und weil ``visual_rgb`` das Weiss
zusaetzlich additiv auf R/G/B legt, saehe die umgekehrte Probe (Weiss an)
sogar richtig aus. Nur diese Richtung trennt die beiden Quellen.

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

# Signal-Liste wie in test_viz50a_panel_koerper_scene.py (bridge.js#tryChannel).
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
_BALKEN = 500201      # ZQ06121: 48 Zonen 4x12 + 8 Weiss-Segmente
_OHNE_WEISS = 500202  # DERSELBE Balken im 144-Kanal-Modus: kein Band
_KACHEL = 500203      # 8x8-Standardpanel: darf sich um nichts aendern
_HOCHKANT = 500204    # ZQ06121 um 90° montiert: das Band muss mitdrehen
_ZWEI_REIHEN = 500205  # CDX-52: dieselben 8 Segmente, aber als 2x4 hinterlegt


def _payload():
    def p(fid, **kw):
        d = {"fid": fid, "label": f"P{fid}", "type": "matrix", "model": "matrix",
             "nHeads": 48, "pixelOrder": "rowwise", "elementRotation": 0,
             "elementFlip": False, "gridRows": 4, "gridCols": 12, "nWhites": 0,
             # CDX-52: hinterlegte Form der Weiss-Leiste (0 = keine).
             "whiteRows": 0, "whiteCols": 0,
             "x": 0, "y": 5, "z": 0, "rotX": 0, "rotY": 0, "rotZ": 0,
             "r": 0, "g": 0, "b": 0, "intensity": 0, "pan": 128, "tilt": 128}
        d.update(kw)
        return d
    return json.dumps([
        # ★ Genau die Nutzlast, die `_fixture_to_dict` fuer Robins Balken baut:
        # acht Segmente (aus den Kanaelen) in EINER Reihe (aus der Bibliothek).
        p(_BALKEN, nWhites=8, whiteRows=1),
        p(_OHNE_WEISS),
        p(_KACHEL, nHeads=64, gridRows=8, gridCols=8),
        p(_HOCHKANT, nWhites=8, whiteRows=1, elementRotation=90),
        p(_ZWEI_REIHEN, nWhites=8, whiteRows=2),
    ])


def _heads(pro_kopf=None):
    """48 Koepfe wie sie ``_build_fixture_payload`` liefert; ``pro_kopf``
    ueberschreibt einzelne (Schluessel = Kopfindex)."""
    pro_kopf = pro_kopf or {}
    hs = []
    for j in range(48):
        h = {"r": 0, "g": 0, "b": 0, "cr": 0, "cg": 0, "cb": 0, "cw": 0,
             "pan": 128, "tilt": 128}
        h.update(pro_kopf.get(j, {}))
        hs.append(h)
    return hs


# Zone 1 ROT, Weiss-Segment 1 AUS. `r/g/b` ist die Zonenfarbe — ein Band, das
# sich daraus faerbt, wird hier rot statt schwarz.
_ROT_OHNE_WEISS = json.dumps([{
    "fid": _BALKEN, "r": 255, "g": 0, "b": 0, "intensity": 255,
    "heads": _heads({0: {"r": 255, "cr": 255}}),
}])

# Weiss-Segment 2 VOLL, seine Zone dunkel. `r/g/b` traegt das Weiss additiv mit
# (visual_rgb) — deshalb belegt DIESE Richtung allein nichts.
_WEISS_AN = json.dumps([{
    "fid": _BALKEN, "r": 0, "g": 0, "b": 0, "intensity": 255,
    "heads": _heads({1: {"r": 255, "g": 255, "b": 255, "cw": 255}}),
}])


_HELFER = """
window.__viz50b = {
  f: function (fid) { return window.__lightos.fixtures[String(fid)]; },
  band: function (fid) { return this.f(fid).whites || []; },
  seg: function (fid, j) { return this.band(fid)[j].mesh; },
  px: function (fid) { return this.f(fid).pixels; },
  // Zellabstand des Farbrasters (Spalte 0 -> 1 bzw. Zeile 0 -> 1).
  gw: function (fid) {
    const p = this.px(fid);
    return p[1].mesh.position.x - p[0].mesh.position.x;
  },
  gh: function (fid) {
    const p = this.px(fid);
    return p[0].mesh.position.y - p[12].mesh.position.y;
  },
  // Wie viele Meshes haengen insgesamt am Modell? (Gehaeuse + Pixel + Band)
  meshes: function (fid) {
    let n = 0;
    this.f(fid).group.traverse(function (o) { if (o.isMesh) n++; });
    return n;
  },
};
true
"""


class WeissbandSceneTest(unittest.TestCase):

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
            if self._eval(f"typeof window.__lightos.fixtures['{_ZWEI_REIHEN}'] "
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

    # ── (1) Das Band steht da, und zwar in der beschriebenen Form ───────────

    def test_acht_segmente_mittig_und_halb_so_hoch(self):
        """★ Die Abnahme des Items als Geometrie: 8 Segmente, halb so hoch wie
        eine RGB-Zone, mittig zwischen Reihe 2 und 3, je anderthalb Spalten
        breit."""
        self._aufbauen()

        self.assertEqual(self._zahl(f"window.__viz50b.band({_BALKEN}).length"), 8)
        # Und sie haengen wirklich am Modell: Gehaeuse + 48 Pixel + 8 Segmente.
        self.assertEqual(self._zahl(f"window.__viz50b.meshes({_BALKEN})"), 57)

        # (a) HALB so hoch wie eine RGB-Zone — beide Quads sind gleich
        # geschrumpft, das Verhaeltnis ist also exakt die Rasteraussage.
        seg_h = self._zahl(f"window.__viz50b.seg({_BALKEN}, 0)"
                           f".geometry.parameters.height")
        px_h = self._zahl(f"window.__viz50b.px({_BALKEN})[0].mesh"
                          f".geometry.parameters.height")
        self.assertAlmostEqual(seg_h / px_h, 0.5, places=6,
                               msg="das Band muss halb so hoch sein wie eine Zone")

        # (b) ANDERTHALB Spalten breit (8 Segmente auf 12 Spalten).
        seg_w = self._zahl(f"window.__viz50b.seg({_BALKEN}, 0)"
                           f".geometry.parameters.width")
        px_w = self._zahl(f"window.__viz50b.px({_BALKEN})[0].mesh"
                          f".geometry.parameters.width")
        self.assertAlmostEqual(seg_w / px_w, 1.5, places=6,
                               msg="8 Segmente muessen 12 Spalten abdecken")

        # (c) MITTIG zwischen Reihe 2 und 3: genau auf halber Rasterhoehe,
        # also gleich weit von Zeile 1 (Pixel 0) wie von Zeile 4 (Pixel 36).
        y_seg = self._zahl(f"window.__viz50b.seg({_BALKEN}, 0).position.y")
        y_oben = self._zahl(f"window.__viz50b.px({_BALKEN})[0].mesh.position.y")
        y_unten = self._zahl(f"window.__viz50b.px({_BALKEN})[36].mesh.position.y")
        self.assertAlmostEqual(y_seg, (y_oben + y_unten) / 2, places=9,
                               msg="das Band liegt nicht mittig")
        gh = self._zahl(f"window.__viz50b.gh({_BALKEN})")
        y_r2 = self._zahl(f"window.__viz50b.px({_BALKEN})[12].mesh.position.y")
        self.assertAlmostEqual(y_seg, y_r2 - gh / 2, places=9,
                               msg="das Band muss auf der Fuge zwischen Reihe 2 "
                                   "und 3 liegen, nicht auf einer Zeile")

        # (d) Es liegt VOR den Pixeln (die Streifen ueberlappen unvermeidlich —
        # ohne Versatz flimmerten beide Flaechen gegeneinander).
        self.assertEqual(
            self._zahl(f"window.__viz50b.seg({_BALKEN}, 0).position.z >"
                       f" window.__viz50b.px({_BALKEN})[0].mesh.position.z"
                       f" ? 1 : 0"), 1)

    def test_die_segmente_decken_die_volle_breite(self):
        """Von links nach rechts, im Abstand von anderthalb Spalten — und das
        letzte Segment endet dort, wo die letzte Spalte endet."""
        self._aufbauen()
        gw = self._zahl(f"window.__viz50b.gw({_BALKEN})")

        x0 = self._zahl(f"window.__viz50b.seg({_BALKEN}, 0).position.x")
        x1 = self._zahl(f"window.__viz50b.seg({_BALKEN}, 1).position.x")
        self.assertAlmostEqual(x1 - x0, 1.5 * gw, places=9,
                               msg="der Segmentabstand ist nicht anderthalb Spalten")

        # Aussenkanten: Segment 0 beginnt an der linken Rasterkante, Segment 7
        # endet an der rechten. Der 0.85-Schrumpf zaehlt fuer beide gleich, also
        # wird er hier herausgerechnet.
        x7 = self._zahl(f"window.__viz50b.seg({_BALKEN}, 7).position.x")
        px_links = self._zahl(f"window.__viz50b.px({_BALKEN})[0].mesh.position.x")
        px_rechts = self._zahl(f"window.__viz50b.px({_BALKEN})[11].mesh.position.x")
        self.assertAlmostEqual(x0 - 0.75 * gw, px_links - 0.5 * gw, places=9)
        self.assertAlmostEqual(x7 + 0.75 * gw, px_rechts + 0.5 * gw, places=9)

    # ── (2) Die Farbe kommt aus den EIGENEN Kanaelen ────────────────────────

    def test_das_band_zeigt_nicht_die_farbe_der_rgb_zonen(self):
        """★★ Der Fall, der ein naiv gebautes Band entlarvt (s. Modul-Kopf):
        Zone 1 rot, Weiss-Segment 1 aus."""
        self._aufbauen()
        ok = self._dmx(_ROT_OHNE_WEISS,
                       f"window.__viz50b.px({_BALKEN})[0].mesh.material"
                       f".color.r > 0.9")
        self.assertTrue(ok, "der DMX-Batch kam nie an")

        self.assertEqual(
            self._zahl(f"window.__viz50b.px({_BALKEN})[0].mesh.material.color.r"),
            1.0, "Vorbedingung: Zone 1 leuchtet rot")
        self.assertEqual(
            self._zahl(f"window.__viz50b.seg({_BALKEN}, 0).material.color.r"),
            0.0, "das Weiss-Segment zeigt die Farbe seiner Nachbarzone")
        self.assertEqual(
            self._zahl(f"window.__viz50b.seg({_BALKEN}, 0).material.emissive.r"),
            0.0, "ein dunkles Segment darf nicht emittieren")

    def test_das_band_leuchtet_aus_seinem_eigenen_kanal(self):
        """Die andere Richtung: Weiss-Segment 2 voll, seine Zone dunkel."""
        self._aufbauen()
        ok = self._dmx(_WEISS_AN,
                       f"window.__viz50b.seg({_BALKEN}, 1).material.color.r"
                       f" > 0.9")
        self.assertTrue(ok, "der DMX-Batch kam nie an")

        for kanal in ("r", "g", "b"):
            self.assertEqual(
                self._zahl(f"window.__viz50b.seg({_BALKEN}, 1)"
                           f".material.emissive.{kanal}"), 1.0,
                "Weiss rechnet LightOS ueberall neutral (visual_rgb, Spider-LED)")
        self.assertGreater(
            self._zahl(f"window.__viz50b.seg({_BALKEN}, 1)"
                       f".material.emissiveIntensity"), 0.0,
            "der Master-Dimmer steht offen, das Segment muss leuchten")
        # Die anderen Segmente bleiben dunkel — ein Band, das sich als Ganzes
        # faerbt, waere hier ueberall hell.
        for j in (0, 2, 7):
            self.assertEqual(
                self._zahl(f"window.__viz50b.seg({_BALKEN}, {j})"
                           f".material.color.r"), 0.0,
                f"Segment {j} gehoert nicht zu diesem Kanal")

    def test_der_master_dimmer_wirkt_auch_auf_das_band(self):
        """Ein Band, das den Dimmer ignoriert, leuchtete im Blackout weiter."""
        self._aufbauen()
        self.assertTrue(self._dmx(
            _WEISS_AN,
            f"window.__viz50b.seg({_BALKEN}, 1).material.color.r > 0.9"))
        hell = self._zahl(f"window.__viz50b.seg({_BALKEN}, 1)"
                          f".material.emissiveIntensity")
        dunkel_batch = json.dumps([{
            "fid": _BALKEN, "r": 0, "g": 0, "b": 0, "intensity": 0,
            "heads": _heads({1: {"r": 255, "g": 255, "b": 255, "cw": 255}}),
        }])
        self.assertTrue(self._dmx(
            dunkel_batch,
            f"window.__viz50b.seg({_BALKEN}, 1).material.emissiveIntensity"
            f" === 0"))
        self.assertGreater(hell, 0.0, "Vorbedingung: vorher war es hell")

    # ── (3) Positivkontrolle: ohne Weiss-Kanaele kein Band ──────────────────

    def test_ohne_weiss_segmente_entsteht_kein_band(self):
        """★ Die Abnahmebedingung, die nicht verhandelbar ist. Der schaerfste
        Fall ist DASSELBE Geraet im 144-Kanal-Modus: gleiche 48 Zonen, gleiche
        4x12-Form, nur ohne Weiss-Kanaele. Wer das Band an der Rasterform oder
        am Geraetetyp festmacht statt an den Kanaelen, baut es hier auch."""
        self._aufbauen()

        self.assertEqual(self._zahl(f"window.__viz50b.band({_OHNE_WEISS}).length"),
                         0, "ein Modus ohne Weiss-Kanaele bekommt kein Band")
        self.assertEqual(
            self._zahl(f"window.__viz50b.f({_OHNE_WEISS}).whites === null"
                       f" ? 1 : 0"), 1)
        # Und das Farbraster ist unveraendert das des Balkens.
        self.assertEqual(self._zahl(f"window.__viz50b.px({_OHNE_WEISS}).length"),
                         48)

    def test_ein_8x8_standardpanel_sieht_aus_wie_bisher(self):
        """★★ Positivkontrolle am Bestand: 64 Pixel, 65 Meshes (Gehaeuse +
        Pixel) — kein einziges zusaetzliches Objekt. Die Mesh-ZAHL ist hier das
        schaerfere Mass als die Bandlaenge: sie faellt auch dann auf, wenn ein
        Band gebaut, aber nicht in ``whites`` eingetragen wuerde."""
        self._aufbauen()

        self.assertEqual(self._zahl(f"window.__viz50b.band({_KACHEL}).length"), 0)
        self.assertEqual(self._zahl(f"window.__viz50b.px({_KACHEL}).length"), 64)
        self.assertEqual(self._zahl(f"window.__viz50b.meshes({_KACHEL})"), 65,
                         "am 8x8-Panel haengt genau ein Mesh je Pixel plus das "
                         "Gehaeuse")

    def test_ein_dmx_batch_ohne_band_faellt_nicht_auf_die_nase(self):
        """Ein Panel ohne Band bekommt dieselben Kopf-Daten (die Nutzlast
        unterscheidet sie nicht) — der Handler darf daran nicht scheitern."""
        self._aufbauen()
        batch = json.dumps([{
            "fid": _OHNE_WEISS, "r": 0, "g": 0, "b": 0, "intensity": 255,
            "heads": _heads({1: {"r": 255, "g": 255, "b": 255, "cw": 255}}),
        }])
        self.assertTrue(self._dmx(
            batch,
            f"window.__viz50b.px({_OHNE_WEISS})[1].mesh.material.color.r > 0.9"),
            "der Batch hat das Panel ohne Band nicht erreicht")
        self.assertEqual(self._zahl(f"window.__viz50b.band({_OHNE_WEISS}).length"),
                         0, "aus einem DMX-Batch darf kein Band entstehen")

    # ── (4) Montage-Drehung: das Band haengt am Panel, nicht am Bildschirm ──

    def test_hochkant_montiert_steht_auch_das_band_hochkant(self):
        """VIZ-52 dreht das Panel mit der Montage. Ein Band, das die Drehung
        nicht mitmacht, laege bei einem hochkant montierten Balken quer ueber
        den Zonen statt laengs zwischen ihnen."""
        self._aufbauen()

        self.assertEqual(self._zahl(f"window.__viz50b.band({_HOCHKANT}).length"), 8)
        # Aus breit-und-flach wird schmal-und-hoch.
        w = self._zahl(f"window.__viz50b.seg({_HOCHKANT}, 0)"
                       f".geometry.parameters.width")
        h = self._zahl(f"window.__viz50b.seg({_HOCHKANT}, 0)"
                       f".geometry.parameters.height")
        self.assertGreater(h, w * 2.9,
                           "das gedrehte Segment muss hochkant stehen")
        # Die Segmente stapeln sich jetzt in Y statt in X.
        y0 = self._zahl(f"window.__viz50b.seg({_HOCHKANT}, 0).position.y")
        y1 = self._zahl(f"window.__viz50b.seg({_HOCHKANT}, 1).position.y")
        x0 = self._zahl(f"window.__viz50b.seg({_HOCHKANT}, 0).position.x")
        x1 = self._zahl(f"window.__viz50b.seg({_HOCHKANT}, 1).position.x")
        self.assertLess(y1, y0, "die Segmente muessen untereinander liegen")
        self.assertAlmostEqual(x0, x1, places=9,
                               msg="hochkant steht das Band in EINER Spalte")
        # Und weiterhin mittig: gleich weit von der linken wie von der rechten
        # Rasterkante (4 Spalten -> Mitte zwischen Spalte 2 und 3). Bei 90°
        # wird aus der QUELL-Zeile die Spalte: Zeile 0 (Pixel 0) landet rechts
        # aussen, Zeile 3 (Pixel 36) links aussen.
        px_rechts = self._zahl(f"window.__viz50b.px({_HOCHKANT})[0].mesh.position.x")
        px_links = self._zahl(f"window.__viz50b.px({_HOCHKANT})[36].mesh.position.x")
        self.assertLess(px_links, px_rechts, "Vorbedingung: 4 Spalten breit")
        self.assertAlmostEqual(x0, (px_links + px_rechts) / 2, places=9,
                               msg="das gedrehte Band liegt nicht mittig")


    # ── (5) CDX-52: die hinterlegte FORM bestimmt die Anordnung ────────────

    def test_zwei_hinterlegte_reihen_ergeben_zwei_reihen(self):
        """★ CDX-52: dieselben acht Segmente wie beim Balken, aber als ZWEI
        Reihen hinterlegt. Der Renderer muss daraus 2x4 machen — sonst liest er
        die Form gar nicht und die Bibliotheksangabe ist Zierde.

        Gemessen wird die ganze Aussage, nicht nur „irgendwas ist anders":
        vier Segmente je Reihe (also drei Spalten breit statt anderthalb), die
        Reihen gleich verteilt ueber die Panelhoehe, und die Segmentnummern
        zeilenweise vergeben (Segment 4 beginnt die zweite Reihe) — daran
        haengt, welcher Weiss-Kanal welches Segment faerbt."""
        self._aufbauen()

        self.assertEqual(
            self._zahl(f"window.__viz50b.band({_ZWEI_REIHEN}).length"), 8,
            "die Segmentzahl kommt weiter aus den Kanaelen")

        # (a) Vier Segmente je Reihe -> je DREI Spalten breit (12 / 4).
        seg_w = self._zahl(f"window.__viz50b.seg({_ZWEI_REIHEN}, 0)"
                           f".geometry.parameters.width")
        px_w = self._zahl(f"window.__viz50b.px({_ZWEI_REIHEN})[0].mesh"
                          f".geometry.parameters.width")
        self.assertAlmostEqual(seg_w / px_w, 3.0, places=6,
                               msg="vier Segmente muessen 12 Spalten abdecken")

        # (b) Segment 0..3 in EINER Hoehe, Segment 4..7 in einer anderen.
        y_oben = self._zahl(f"window.__viz50b.seg({_ZWEI_REIHEN}, 0).position.y")
        y_unten = self._zahl(f"window.__viz50b.seg({_ZWEI_REIHEN}, 4).position.y")
        for j in (1, 2, 3):
            self.assertAlmostEqual(
                self._zahl(f"window.__viz50b.seg({_ZWEI_REIHEN}, {j}).position.y"),
                y_oben, places=9, msg=f"Segment {j} gehoert in die erste Reihe")
        for j in (5, 6, 7):
            self.assertAlmostEqual(
                self._zahl(f"window.__viz50b.seg({_ZWEI_REIHEN}, {j}).position.y"),
                y_unten, places=9, msg=f"Segment {j} gehoert in die zweite Reihe")
        self.assertLess(y_unten, y_oben,
                        "die zweite Reihe muss unter der ersten liegen")

        # (c) Gleich verteilt ueber die Panelhoehe: bei 4 Zeilen liegt Reihe 1
        # auf der Fuge zwischen Pixelzeile 1 und 2, Reihe 2 zwischen 3 und 4.
        y_px = lambda i: self._zahl(                          # noqa: E731
            f"window.__viz50b.px({_ZWEI_REIHEN})[{i}].mesh.position.y")
        self.assertAlmostEqual(y_oben, (y_px(0) + y_px(12)) / 2, places=9)
        self.assertAlmostEqual(y_unten, (y_px(24) + y_px(36)) / 2, places=9)

        # (d) Und die Segmente stehen zeilenweise: 0 links, 3 rechts, dann
        # beginnt 4 wieder links.
        x0 = self._zahl(f"window.__viz50b.seg({_ZWEI_REIHEN}, 0).position.x")
        x3 = self._zahl(f"window.__viz50b.seg({_ZWEI_REIHEN}, 3).position.x")
        x4 = self._zahl(f"window.__viz50b.seg({_ZWEI_REIHEN}, 4).position.x")
        self.assertLess(x0, x3, "Segment 0 liegt links von Segment 3")
        self.assertAlmostEqual(x4, x0, places=9,
                               msg="Segment 4 beginnt die zweite Reihe links")

    def test_die_eine_reihe_des_balkens_bleibt_davon_unberuehrt(self):
        """★★ Die Positivkontrolle zur Form: derselbe Renderer, dieselbe
        Segmentzahl — mit ``whiteRows: 1`` muss der Balken exakt EINE Reihe
        haben. Ein Renderer, der die Form ignoriert und stumpf zwei Reihen
        baute, faellt hier auf."""
        self._aufbauen()
        y0 = self._zahl(f"window.__viz50b.seg({_BALKEN}, 0).position.y")
        for j in range(1, 8):
            self.assertAlmostEqual(
                self._zahl(f"window.__viz50b.seg({_BALKEN}, {j}).position.y"),
                y0, places=9, msg=f"Segment {j} liegt nicht in derselben Reihe")


if __name__ == "__main__":
    unittest.main()
