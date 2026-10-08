"""VIZ-79: Laser schiessen im 3D-Visualizer lange, sichtbare Strahlen.

Ausgangsfrage: In der 3D-Ansicht einer grossen Show mit vielen Lasern waren
keine richtigen Laserstrahlen zu sehen. Gemessen (bis VIZ-79):

  * Der Laser-Faecher bestand aus fuenf Zylindern mit **1,8 m** Laenge und
    5 mm Radius — aus Publikumsentfernung ein kurzer Stummel an der Traverse.
  * Der Faecher zeigte nach lokal **-Z**, also von der Kamera (Publikum bei
    +Z) weg nach hinten in die Rueckwand.
  * Zusaetzlich bekam jeder Laser denselben senkrecht nach unten gerichteten
    PAR-Kegel samt SpotLight und Bodenfleck wie ein Scheinwerfer — der war
    das einzige Grosse, was man sah, und er hing an „Beam Opacity" und
    „Max. Strahllaenge". Ein Laser macht keinen Lichtkegel und keinen
    Bodenfleck.

Der Test baut einen Laser in der ECHTEN Produktiv-Seite (offscreen
QtWebEngine), schickt typische DMX-Werte ueber ``applyDmx`` (derselbe Weg wie
der Service) und misst die Strahlen in Weltkoordinaten.
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

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HTML_PATH = os.path.join(_REPO, "src", "ui", "visualizer", "stage_scene.html")

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05

# Mindestlaenge eines Laserstrahls: ueber die Buehne bis ins Publikum.
_MIN_LAENGE_M = 15.0
# Mindest-Deckkraft: ein additiver Strahl darunter ist auf dunklem Grund kaum
# noch vom Hintergrund zu unterscheiden.
_MIN_OPACITY = 0.5

_SIGNAL_SPECS = [
    ("fixtureAdded", (str,)), ("fixtureRemoved", (int,)),
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
    attrs = {name: Signal(*types) for name, types in _SIGNAL_SPECS}

    @Slot()
    def requestFixtures(self):
        pass

    @Slot(result=str)
    def pollControl(self):
        # Review L1: der Test kann Poll-Zustaende (beamsOff) vorgeben.
        return getattr(self, "_poll", "{}")

    attrs["requestFixtures"] = requestFixtures
    attrs["pollControl"] = pollControl
    attrs["requestFullResync"] = Signal()
    return type("MockVisualizerBridgeViz79", (QObject,), attrs)


_MockBridge = _make_mock_bridge_class()


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


_FID = 790001


def _laser(fid=_FID, **extra):
    """Laser an der hinteren Traverse, wie in den Demo-Shows (hinter den
    Movern, Publikum vorne bei +Z)."""
    d = {"fid": fid, "type": "laser", "model": "laser",
         "x": 0, "y": 5.9, "z": -4.6, "r": 0, "g": 0, "b": 0, "intensity": 0,
         "pan": 128, "tilt": 128}
    d.update(extra)
    return d


def _gruen(fid=_FID, intensity=255, laser=None):
    """Typischer Laser-Payload: Farbrad auf Gruen, Shutter im Muster-Bereich
    (``visual_intensity`` -> 255). ``laser`` = normierter Laser-Block, wie ihn
    ``visualizer_service._laser_payload`` baut."""
    d = {"fid": fid, "r": 0, "g": 255, "b": 0, "intensity": intensity,
         "pan": 128, "tilt": 128}
    if laser is not None:
        d["laser"] = laser
    return d


# Strahlen in Weltkoordinaten vermessen. Die Geometrie wird ueber ihre
# Bounding-Box entlang der lokalen Y-Achse (Zylinderachse) abgegriffen — das
# gilt fuer mittig wie fuer am Fuss verankerte Zylinder.
_MISS_JS = """
(function(){
  const f = window.__lightos.fixtures['%d'];
  if (!f) return 'null';
  f.group.updateMatrixWorld(true);
  const out = { beams: [], cone: !!f.beam, spot: !!f.spot, floor: !!f.floorSpot,
                start: [f.group.position.x, f.group.position.y, f.group.position.z] };
  for (const bm of (f.laserBeams || [])) {
    const g = bm.geometry;
    g.computeBoundingBox();
    const bb = g.boundingBox;
    const a = bm.position.clone().set(0, bb.min.y, 0);
    const b = bm.position.clone().set(0, bb.max.y, 0);
    bm.localToWorld(a); bm.localToWorld(b);
    out.beams.push({ visible: bm.visible, opacity: bm.material.opacity,
                     flaeche: !!bm.userData.flaeche,
                     additive: bm.material.blending === 2,
                     a: [a.x, a.y, a.z], b: [b.x, b.y, b.z],
                     len: a.distanceTo(b) });
  }
  return JSON.stringify(out);
})()
"""


def _fern(beam, start):
    """Der vom Geraet weiter entfernte Endpunkt."""
    def d2(p):
        return sum((p[i] - start[i]) ** 2 for i in range(3))
    return beam["a"] if d2(beam["a"]) > d2(beam["b"]) else beam["b"]


class Viz79LaserStrahlenSceneTest(unittest.TestCase):
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
        self._loaded_ok = []
        self._view.loadFinished.connect(self._loaded_ok.append)

    def tearDown(self):
        destroy_webengine_view(self._view, _pump)
        self._view = None

    # ── Helfer ───────────────────────────────────────────────────────────────
    def _load_and_wait(self):
        url = QUrl.fromLocalFile(_HTML_PATH)
        # QA-86: Stufe fest, sonst waehlt die GPU-Probe des Testrechners
        # (Windows/ANGLE meldet 16 Textur-Einheiten -> 'low', Prisma gedeckelt).
        url.setQuery(f"v={int(time.time() * 1000)}&gputier=high")
        self._view.load(url)
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded_ok and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded_ok and self._loaded_ok[-1], "Seite nicht geladen")
        self._poll_until_true("!!window.__lightosAppReady")

    def _eval(self, js_expr):
        box = []
        self._view.page().runJavaScript(js_expr, lambda result: box.append(result))
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(0.01)
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
        self.fail(f"Timeout beim Warten auf '{js_expr}' (letzter Wert: {last!r})")

    def _emit_until_true(self, emit_fn, js_expr, timeout_s=_POLL_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            emit_fn()
            last = self._eval(js_expr)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout nach wiederholtem Emit: '{js_expr}' (letzter Wert: {last!r})")

    def _apply(self, arr, seq):
        return self._eval("window.__lightos.applyDmx(%s, %s)"
                          % (json.dumps(arr), json.dumps(seq)))

    def _bauen(self, data):
        self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(json.dumps([data])),
            "!!window.__lightos.fixtures['%d']" % data["fid"])

    def _miss(self, fid=_FID):
        res = json.loads(self._eval(_MISS_JS % fid))
        self.assertIsNotNone(res, "Laser wurde nicht gebaut")
        return res

    def _show_einstellungen(self, beam_opacity, max_range):
        """Die Einstellungen einer grossen Show: Kegel-Deckkraft niedrig
        (15 %), globale Strahllaengen-Obergrenze gesetzt."""
        self._eval("(function(){ const s = window.__lightos.settings;"
                   " s.beamOpacity = %r; s.maxBeamRange = %r; s.showCones = true;"
                   " return true; })()" % (beam_opacity, max_range))

    # ── Tests ────────────────────────────────────────────────────────────────
    def test_laser_schiesst_lange_sichtbare_strahlen_ins_publikum(self):
        self._load_and_wait()
        self._show_einstellungen(0.15, 5)
        self._bauen(_laser())
        self.assertEqual(self._apply([_gruen()], 1), 1)
        m = self._miss()

        strahlen = [bm for bm in m["beams"] if bm["visible"] and not bm["flaeche"]]
        self.assertGreaterEqual(len(strahlen), 3, "kein Laser-Faecher sichtbar")
        for i, bm in enumerate(strahlen):
            self.assertTrue(bm["visible"], f"Strahl {i} unsichtbar")
            self.assertTrue(bm["additive"], f"Strahl {i} nicht additiv")
            # Beam Opacity 15 % darf den Laser NICHT mitdimmen.
            self.assertGreaterEqual(
                bm["opacity"], _MIN_OPACITY,
                f"Strahl {i}: Deckkraft {bm['opacity']:.2f} — Laser fast unsichtbar")
            # Max. Strahllaenge 5 m gilt fuer Kegel, nicht fuer Laser.
            self.assertGreaterEqual(
                bm["len"], _MIN_LAENGE_M,
                f"Strahl {i}: nur {bm['len']:.2f} m lang — Stummel statt Laserstrahl")
            fern = _fern(bm, m["start"])
            # Richtung Publikum (+Z), nicht in die Rueckwand.
            self.assertGreater(fern[2], m["start"][2] + 10.0,
                               f"Strahl {i} zeigt nicht ins Publikum: Ende {fern}")
            # Ueber den Koepfen bleiben, nicht in den Boden.
            self.assertGreater(fern[1], 2.0,
                               f"Strahl {i} endet zu tief (Ende {fern})")

    def test_laser_hat_keinen_scheinwerferkegel(self):
        """Ein Laser macht keinen Lichtkegel, kein Raumlicht und keinen
        Bodenfleck — der PAR-Kegel war das Einzige, was man sah, und er hing
        an Beam Opacity und Max. Strahllaenge."""
        self._load_and_wait()
        self._bauen(_laser())
        self._apply([_gruen()], 1)
        m = self._miss()
        self.assertFalse(m["cone"], "Laser bekommt einen PAR-Kegel")
        self.assertFalse(m["spot"], "Laser bekommt ein SpotLight")
        self.assertFalse(m["floor"], "Laser bekommt einen Bodenfleck")

    def test_dunkel_heisst_unsichtbar(self):
        """Gegenprobe: Intensitaet 0 (Shutter zu oder Laser-NOT-AUS — der
        Latch nullt die Kanaele, der Payload traegt dann intensity 0)."""
        self._load_and_wait()
        self._bauen(_laser())
        self._apply([_gruen()], 1)
        self._apply([_gruen(intensity=0)], 2)
        m = self._miss()
        self.assertTrue(m["beams"])
        for bm in m["beams"]:
            self.assertFalse(bm["visible"], "dunkler Laser zeigt Strahlen")

    def test_kegel_aus_schaltet_auch_laser_aus(self):
        """„Kegel anzeigen" bleibt der gemeinsame Schalter fuer alle Strahlen
        (beamsSichtbar) — bewusst, dokumentiert in der Anleitung."""
        self._load_and_wait()
        self._bauen(_laser())
        self._apply([_gruen()], 1)
        self._eval("window.__lightos.settings.showCones = false")
        self._apply([_gruen()], 2)
        m = self._miss()
        for bm in m["beams"]:
            self.assertFalse(bm["visible"])


class Viz79LaserMusterSceneTest(Viz79LaserStrahlenSceneTest):
    """VIZ-79 Teil 2: Position, Groesse, Muster und Eigenbewegung aus DMX."""

    # Die geerbten Tests laufen schon in der Basisklasse.
    test_laser_schiesst_lange_sichtbare_strahlen_ins_publikum = None
    test_laser_hat_keinen_scheinwerferkegel = None
    test_dunkel_heisst_unsichtbar = None
    test_kegel_aus_schaltet_auch_laser_aus = None

    def _setze(self, seq, **laser):
        self.assertEqual(self._apply([_gruen(laser=laser)], seq), 1)
        return self._miss()

    @staticmethod
    def _sichtbar(m):
        return [bm for bm in m["beams"] if bm["visible"] and not bm["flaeche"]]

    def _enden(self, m):
        return [_fern(bm, m["start"]) for bm in self._sichtbar(m)]

    def test_laser_x_schwenkt_den_faecher(self):
        self._load_and_wait()
        self._bauen(_laser())
        mitte = sum(e[0] for e in self._enden(self._setze(1, x=0))) / 5
        links = sum(e[0] for e in self._enden(self._setze(2, x=-1))) / 5
        rechts = sum(e[0] for e in self._enden(self._setze(3, x=1))) / 5
        self.assertAlmostEqual(mitte, 0.0, delta=0.5)
        self.assertGreater(abs(rechts - links), 10.0,
                           "laser_x dreht den Faecher nicht (Enden %.2f / %.2f)" % (links, rechts))
        self.assertLess(links, mitte)
        self.assertGreater(rechts, mitte)

    def test_laser_y_neigt_den_faecher(self):
        self._load_and_wait()
        self._bauen(_laser())
        hoch = sum(e[1] for e in self._enden(self._setze(1, y=-1))) / 5
        tief = sum(e[1] for e in self._enden(self._setze(2, y=1))) / 5
        self.assertGreater(hoch - tief, 5.0, "laser_y neigt den Faecher nicht")

    def test_zoom_aendert_die_faecherbreite(self):
        self._load_and_wait()
        self._bauen(_laser())
        def breite(m):
            xs = [e[0] for e in self._enden(m)]
            return max(xs) - min(xs)
        schmal = breite(self._setze(1, sx=0.2))
        voll = breite(self._setze(2, sx=1.0))
        self.assertGreater(voll, 2.5 * schmal,
                           f"Groesse wirkt nicht (Breite {schmal:.2f} -> {voll:.2f} m)")

    def test_muster_aendert_strahlzahl_und_form(self):
        self._load_and_wait()
        self._bauen(_laser())
        faecher = self._setze(1, form=0)
        self.assertEqual(len(self._sichtbar(faecher)), 5)
        einzel = self._setze(2, form=1)
        self.assertEqual(len(self._sichtbar(einzel)), 1)
        kranz = self._setze(3, form=2)
        self.assertEqual(len(self._sichtbar(kranz)), 8)
        flaeche = self._setze(4, form=3)
        self.assertEqual(len(self._sichtbar(flaeche)), 0)
        self.assertTrue(any(bm["flaeche"] and bm["visible"] for bm in flaeche["beams"]),
                        "Flaeche nicht sichtbar")
        # Zurueck zum Faecher: die Flaeche geht wieder aus.
        zurueck = self._setze(5, form=0)
        self.assertFalse(any(bm["flaeche"] and bm["visible"] for bm in zurueck["beams"]))
        self.assertEqual(len(self._sichtbar(zurueck)), 5)
        # Dunkel: auch Kranz und Flaeche verschwinden.
        self._apply([_gruen(intensity=0, laser={"form": 3})], 6)
        self.assertFalse(any(bm["visible"] for bm in self._miss()["beams"]))

    def _info(self, t=None):
        arg = "" if t is None else ", %r" % t
        return json.loads(self._eval(
            "JSON.stringify(window.__lightos.laserInfo(%d%s))" % (_FID, arg)))

    def test_eigenbewegung_laeuft_zeitgesteuert(self):
        """dx = Bewegung laeuft im Geraet (dynamischer Bereich bzw. Auto-
        Programm mit Tempo): der Faecher schwenkt, ohne neues DMX."""
        self._load_and_wait()
        self._bauen(_laser())
        self._setze(1, x=0, dx=True, tempo=0.2)
        a = self._info(0.0)
        b = self._info(2.0)
        self.assertTrue(a["bewegt"], "bewegter, leuchtender Laser nicht als animiert gemeldet")
        self.assertGreater(abs(a["yaw"] - b["yaw"]), 0.1, "kein Schwenk ueber die Zeit")
        # Ohne Eigenbewegung haengt die Pose nicht an der Zeit.
        self._setze(2, x=0.5)
        c = self._info(0.0)
        d = self._info(2.0)
        self.assertFalse(c["bewegt"])
        self.assertAlmostEqual(c["yaw"], d["yaw"], places=6)
        # Dunkel: keine Animation, der Render-Loop darf schlafen.
        self._apply([_gruen(intensity=0, laser={"dx": True})], 3)
        self.assertFalse(self._info()["bewegt"])

    def test_dmx_updates_bauen_keine_geometrie_neu(self):
        """Leistung: ein DMX-Update setzt nur Drehung/Skalierung/Sichtbarkeit."""
        self._load_and_wait()
        self._bauen(_laser())
        js = ("(function(){ const f = window.__lightos.fixtures['%d']; const ids = [];"
              " f.group.traverse(o => { if (o.geometry) ids.push(o.geometry.uuid);"
              " if (o.material) ids.push(o.material.uuid); });"
              " return ids.sort().join(','); })()" % _FID)
        vorher = self._eval(js)
        seq = 1
        for form in range(4):
            for x in (-1, 0, 1):
                self._apply([_gruen(laser={"form": form, "x": x, "sx": 0.5, "dx": True})], seq)
                seq += 1
        self.assertEqual(vorher, self._eval(js),
                         "DMX-Updates haben Geometrien/Materialien neu angelegt")


class Viz79ReviewSceneTest(Viz79LaserStrahlenSceneTest):
    """Review VIZ-79: Picking (H1), Einpassen (M1), Animation (L1/L2)."""

    test_laser_schiesst_lange_sichtbare_strahlen_ins_publikum = None
    test_laser_hat_keinen_scheinwerferkegel = None
    test_dunkel_heisst_unsichtbar = None
    test_kegel_aus_schaltet_auch_laser_aus = None

    def _info(self):
        return json.loads(self._eval(
            "JSON.stringify(window.__lightos.laserInfo(%d))" % _FID))

    def _pick_boden(self, z):
        """Derselbe Fixture-Pick wie Klick/Hover/Zug, auf einen Bodenpunkt
        (0, 0, z) gezielt. Liefert die getroffene fid oder None."""
        r = self._eval("""
        (function(){
          const L = window.__lightos;
          const f = L.fixtures['%d'];
          f.group.updateMatrixWorld(true);
          L.view.activeCam.updateMatrixWorld();
          const p = f.group.position.clone().set(0, 0, %r).project(L.view.activeCam);
          // Bildschirmpunkt direkt als NDC in die geteilte Maus (offscreen hat
          // das Canvas kein Layout fuer Client-Koordinaten).
          L.__mouse.set(p.x, p.y);
          const fid = L.__pickFixture();
          return (fid === null || fid === undefined) ? 'null' : String(fid);
        })()""" % (_FID, z))
        return None if r == "null" else int(r)

    def test_unsichtbare_strahlen_fangen_keinen_klick(self):
        """H1: three r128 prueft `visible` beim Raycast nicht. Ein Klick 7 m
        vor dem Laser auf den Boden darf ihn nicht auswaehlen."""
        self._load_and_wait()
        self._eval("window.__lightos.setViewMode('3D'); true")
        self._bauen(_laser())
        z = -4.6 + 7.0
        for seq, (inten, form) in enumerate(
                [(0, 0), (0, 3), (255, 0), (255, 3), (255, 2)], start=1):
            self._apply([_gruen(intensity=inten, laser={"form": form})], seq)
            self.assertIsNone(self._pick_boden(z),
                              f"Bodenklick 7 m vor dem Laser waehlt ihn aus "
                              f"(Intensitaet {inten}, Form {form})")
        # Gegenprobe: das Gehaeuse selbst bleibt anklickbar.
        r = self._eval("""
        (function(){
          const L = window.__lightos;
          const f = L.fixtures['%d'];
          f.group.updateMatrixWorld(true);
          L.view.activeCam.updateMatrixWorld();
          const p = f.group.position.clone().project(L.view.activeCam);
          L.__mouse.set(p.x, p.y);
          return String(L.__pickFixture());
        })()""" % _FID)
        self.assertEqual(r, str(_FID), "Gehaeuse nicht mehr anklickbar")

    def test_einpassen_rahmt_das_geraet_nicht_die_strahlen(self):
        """M1: „Auswahl einpassen" auf den Laser rahmt das 20-cm-Geraet."""
        self._load_and_wait()
        self._eval("window.__lightos.setViewMode('3D'); true")
        self._bauen(_laser())
        self._apply([_gruen()], 1)
        self._eval("window.__lightos.view.selectedFids = [%d]; true" % _FID)
        self._eval("window.__lightos.fitSelected(); true")
        radius = float(self._eval("window.__lightos.view.radius"))
        self.assertLess(radius, 6.0,
                        f"Einpassen rahmt die Strahlen mit (Abstand {radius:.1f} m)")

    def test_beamsoff_haelt_render_loop_nicht_wach(self):
        """L1: ein ausgeblendeter (beamsOff) bewegter Laser haelt die Render-
        Schleife nicht wach."""
        self._load_and_wait()
        self._bauen(_laser())
        self._apply([_gruen(laser={"dx": True, "tempo": 0.2})], 1)
        self.assertTrue(self._info()["animationAktiv"])
        self._bridge_obj._poll = json.dumps({"beamsOff": [_FID]})
        self._poll_until_true(
            "!window.__lightos.laserInfo(%d).animationAktiv" % _FID)
        # Auch ein neues DMX-Update weckt ihn nicht wieder.
        self._apply([_gruen(laser={"dx": True, "tempo": 0.2})], 2)
        self.assertFalse(self._info()["animationAktiv"])
        # Wieder einblenden: er laeuft weiter.
        self._bridge_obj._poll = json.dumps({"beamsOff": []})
        self._poll_until_true(
            "window.__lightos.laserInfo(%d).animationAktiv" % _FID)

    def test_bewegung_ueberlebt_2d_3d_und_kegel_schalter(self):
        """L2: kam der Bewegungs-Befehl, waehrend der Laser unsichtbar war
        (2D bzw. Kegel aus), laeuft er nach dem Zurueckschalten — ohne neues DMX."""
        self._load_and_wait()
        self._bauen(_laser())
        self._eval("window.__lightos.setViewMode('2D'); true")
        self._apply([_gruen(laser={"dx": True, "tempo": 0.2})], 1)
        self._eval("window.__lightos.setViewMode('3D'); true")
        i = self._info()
        self.assertTrue(i["bewegt"] and i["animationAktiv"],
                        "nach 2D->3D steht der bewegte Laser still")
        # Kegel aus, DMX, Kegel an (applySettings-Pfad wie das Settings-Panel).
        self._eval("window.__lightos.settings.showCones = false;"
                   " for (const k in window.__lightos.fixtures) {} true")
        self._bridge_obj.settingsChanged.emit(json.dumps({"showCones": False}))
        self._poll_until_true("window.__lightos.settings.showCones === false")
        self._apply([_gruen(laser={"dx": True, "tempo": 0.2})], 2)
        self._bridge_obj.settingsChanged.emit(json.dumps({"showCones": True}))
        self._poll_until_true("window.__lightos.settings.showCones === true")
        i = self._info()
        self.assertTrue(i["bewegt"] and i["animationAktiv"],
                        "nach Kegel aus/an steht der bewegte Laser still")


if __name__ == "__main__":
    unittest.main()
