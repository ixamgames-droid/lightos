"""LAS-32 (S1): Sperrzonen und Laser-Feld in der echten 3D-Seite.

Geprueft wird am geladenen ``stage_scene.html``:

* eine Zone erscheint — rot, halbtransparent, an der eingetragenen Stelle —
  und faengt keinen Klick ab,
* das Feld eines Lasers erscheint, folgt dem Geraet und deckt sich mit der
  Rechnung in Python (dieselben Ecken, dieselbe Seitenfestlegung),
* ohne Randwinkel gibt es kein Feld, und Loeschen raeumt die Szene auf.

Die Daten kommen ueber den Poll (Schluessel ``sperrzonen``) — derselbe Weg wie
im Betrieb.
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

from src.core.laser import sperrzonen as S
from src.core.laser.sperrzonen import LaserFeld, Sperrzone

_app = QApplication.instance() or QApplication([])

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HTML_PATH = os.path.join(_REPO, "src", "ui", "visualizer", "stage_scene.html")

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05

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
    attrs = {name: Signal(*types) for name, types in _SIGNAL_SPECS}

    @Slot()
    def requestFixtures(self):
        pass

    @Slot(result=str)
    def pollControl(self):
        return getattr(self, "_poll", "{}")

    attrs["requestFixtures"] = requestFixtures
    attrs["pollControl"] = pollControl
    attrs["requestFullResync"] = Signal()
    return type("MockVisualizerBridgeLas32", (QObject,), attrs)


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


_FID = 320001
_POS = (1.5, 5.0, -3.0)
_ROT = (25.0, 40.0, 170.0)     # gekippt, gedreht, fast kopfueber
_FELD = LaserFeld(links=12, rechts=30, oben=4, unten=22, zuschlag=5)
_ZONE = Sperrzone(id="z1", name="Publikum", x=2.0, y=0.5, z=7.0,
                  breite=8.0, hoehe=3.0, tiefe=5.0, dreh_y=30.0)


def _laser(pos=_POS, rot=_ROT):
    return {"fid": _FID, "type": "laser", "model": "laser",
            "x": pos[0], "y": pos[1], "z": pos[2],
            "rotX": rot[0], "rotY": rot[1], "rotZ": rot[2],
            "r": 0, "g": 0, "b": 0, "intensity": 0, "pan": 128, "tilt": 128}


def _daten(zonen=(_ZONE,), feld=_FELD):
    felder = []
    if feld is not None:
        e = feld.to_dict()
        e["fid"] = _FID
        felder.append(e)
    return json.dumps({"zonen": [z.to_dict() for z in zonen], "felder": felder,
                       "laenge": S.FELD_ANZEIGE_LAENGE_M}, sort_keys=True)


class SperrzonenSceneTest(unittest.TestCase):
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

    def _load_and_wait(self):
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}&gputier=high")
        self._view.load(url)
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded_ok and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded_ok and self._loaded_ok[-1], "Seite nicht geladen")
        self._poll_until_true("!!window.__lightosAppReady")

    def _eval(self, js_expr):
        huelle = ("(function(){try{return JSON.stringify(['ok',(0,eval)("
                  + json.dumps(js_expr) + ")]);}"
                  "catch(e){return JSON.stringify(['err',String(e)]);}})()")
        box = []
        self._view.page().runJavaScript(huelle, lambda result: box.append(result))
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(0.01)
        self.assertTrue(box and box[0], f"runJavaScript ohne Ergebnis: {js_expr}")
        art, wert = json.loads(box[0])
        self.assertNotEqual(art, "err", f"JS warf bei '{js_expr}': {wert}")
        return wert

    def _poll_until_true(self, js_expr, timeout_s=_POLL_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            last = self._eval(js_expr)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout beim Warten auf '{js_expr}' (letzter Wert: {last!r})")

    def _info(self):
        return json.loads(self._eval(
            "JSON.stringify(window.__lightosSperrzonen.info())"))

    def _poll(self, **zustand):
        self._bridge_obj._poll = json.dumps(zustand)

    # ── Alle Checks in EINER Ladung: jede Vollladung kostet mehrere Sekunden ──
    def test_zone_und_feld_erscheinen_und_decken_sich_mit_der_rechnung(self):
        self._load_and_wait()
        self.assertEqual(self._info(), {"zonen": [], "felder": [],
                                        "laenge": S.FELD_ANZEIGE_LAENGE_M})

        # (1) Zone + Feld + Laser ueber den Poll — wie im Betrieb.
        self._poll(fixtures=json.dumps([_laser()]), sperrzonen=_daten())
        self._poll_until_true(
            "(function(){const i=window.__lightosSperrzonen.info();"
            " return i.zonen.length===1 && i.felder.length===1 && i.felder[0].sichtbar;})()")
        info = self._info()

        # (2) Zone: rot, halbtransparent, an der eingetragenen Stelle.
        z = info["zonen"][0]
        self.assertEqual(z["name"], "Publikum")
        self.assertTrue(z["inSzene"] and z["sichtbar"])
        self.assertEqual(z["farbe"], 0xFF2020)
        self.assertTrue(z["transparent"])
        self.assertGreater(z["deckkraft"], 0.05)
        self.assertLess(z["deckkraft"], 0.5)
        self.assertEqual((z["breite"], z["hoehe"], z["tiefe"]), (8.0, 3.0, 5.0))
        self.assertAlmostEqual(z["y"], 0.5 + 1.5, places=5)      # Unterkante + halbe Hoehe
        self.assertAlmostEqual(z["drehY"], 30.0, places=4)
        # … und deckungsgleich mit dem Quader, mit dem Python rechnet.
        soll = S.zonen_ecken(_ZONE, rand=0.0)
        for ist, erwartet in zip(z["weltEcken"], soll):
            for a, b in zip(ist, erwartet):
                self.assertAlmostEqual(a, b, places=4)
        # Eine Zone faengt keine Eingabe: ein Strahl mitten hindurch trifft nichts.
        self.assertEqual(z["raycastTreffer"], 0)
        # Namensschild: traegt den Namen, ist so breit wie sein Text und haelt
        # in der Totale einen festen Anteil der Bildhoehe (sonst unlesbar).
        self.assertEqual(z["schild"]["text"], "Publikum")
        self.assertGreater(z["schild"]["seitenverhaeltnis"], 2.0)
        self.assertAlmostEqual(z["schild"]["breite"] / z["schild"]["hoehe"],
                               z["schild"]["seitenverhaeltnis"], places=4)
        hoehen = self._eval("[0, 5, 30, 60].map(window.__lightosSperrzonen.schildHoehe)")
        self.assertEqual(hoehen[0], 0.45)
        self.assertEqual(hoehen[1], 0.45)            # aus der Naehe nie kleiner
        self.assertAlmostEqual(hoehen[2], 0.036 * 30, places=6)
        self.assertAlmostEqual(hoehen[3], 0.036 * 60, places=6)

        # (3) Feld: sitzt am Geraet, und seine vier Kanten liegen GENAU auf den
        # Ebenen, mit denen Python „kann erreichen?" rechnet.
        f = info["felder"][0]
        self.assertEqual(f["fid"], _FID)
        self.assertTrue(f["inSzene"] and f["sichtbar"])
        # Spitze = Austrittsfenster des Modells, NICHT der Geraete-Ursprung —
        # dieselbe Stelle, ab der Python rechnet (feld_spitze).
        spitze = S.feld_spitze(_POS, _ROT)
        for ist, erwartet in zip((f["x"], f["y"], f["z"]), spitze):
            self.assertAlmostEqual(ist, erwartet, places=5)
        self.assertGreater(sum((spitze[i] - _POS[i]) ** 2 for i in range(3)) ** 0.5, 0.05)
        fenster = self._eval(
            "(function(){const f=window.__lightos.fixtures[%d];"
            " const v=new THREE.Vector3(); f.group.updateMatrixWorld(true);"
            " f.laserRig.pivot.getWorldPosition(v); return [v.x,v.y,v.z];})()" % _FID)
        for ist, erwartet in zip(fenster, spitze):
            self.assertAlmostEqual(ist, erwartet, places=5)
        ebenen = S.feld_ebenen(_ROT, _FELD)      # [hinten, rechts, links, oben, unten]
        vorn, rechts, oben = S.geraete_achsen(_ROT)
        # Ecken-Reihenfolge der Seite: links-oben, rechts-oben, rechts-unten, links-unten
        auf_ebenen = [(2, 3), (1, 3), (1, 4), (2, 4)]
        for ecke, (e1, e2) in zip(f["weltEcken"], auf_ebenen):
            d = [ecke[i] - spitze[i] for i in range(3)]
            laenge = sum(v * v for v in d) ** 0.5
            self.assertGreater(laenge, S.FELD_ANZEIGE_LAENGE_M - 1e-6)
            for e in (e1, e2):
                abstand = sum(ebenen[e][i] * d[i] for i in range(3)) / laenge
                self.assertAlmostEqual(abstand, 0.0, places=4,
                                       msg=f"Ecke {ecke} liegt nicht auf Ebene {e}")
            # vor dem Geraet, nicht dahinter
            self.assertAlmostEqual(sum(vorn[i] * d[i] for i in range(3)),
                                   S.FELD_ANZEIGE_LAENGE_M, places=3)
        # Seitenprobe: die Ecke „rechts-oben" liegt wirklich rechts und oben.
        d = [f["weltEcken"][1][i] - spitze[i] for i in range(3)]
        self.assertGreater(sum(rechts[i] * d[i] for i in range(3)), 0)
        self.assertGreater(sum(oben[i] * d[i] for i in range(3)), 0)

        # (4) Geraet verschoben/gedreht (Neubau ueber die Geraeteliste): das
        # Feld folgt beim naechsten Poll, ohne dass sich die Zonendaten aendern.
        neu_pos, neu_rot = (-4.0, 3.0, 2.0), (0.0, -90.0, 0.0)
        self._poll(fixtures=json.dumps([_laser(neu_pos, neu_rot)]), sperrzonen=_daten())
        neu_spitze = S.feld_spitze(neu_pos, neu_rot)
        self._poll_until_true(
            "Math.abs(window.__lightosSperrzonen.info().felder[0].x - (%r)) < 1e-5"
            % neu_spitze[0])
        f = self._info()["felder"][0]
        ebenen = S.feld_ebenen(neu_rot, _FELD)
        for ecke, (e1, e2) in zip(f["weltEcken"], auf_ebenen):
            d = [ecke[i] - neu_spitze[i] for i in range(3)]
            laenge = sum(v * v for v in d) ** 0.5
            for e in (e1, e2):
                self.assertAlmostEqual(
                    sum(ebenen[e][i] * d[i] for i in range(3)) / laenge, 0.0, places=4)

        # (5) Laser ohne Randwinkel: kein Feld (nichts Geratenes im Bild).
        self._poll(fixtures=json.dumps([_laser(neu_pos, neu_rot)]),
                   sperrzonen=_daten(feld=None))
        self._poll_until_true("window.__lightosSperrzonen.info().felder.length===0")
        self.assertEqual(len(self._info()["zonen"]), 1)

        # (6) Zone umbenannt/verschoben, dann geloescht: Szene ist wieder leer.
        zweite = Sperrzone(id="z1", name="Bar", x=-3.0, y=0.0, z=1.0,
                           breite=2.0, hoehe=2.0, tiefe=2.0)
        self._poll(fixtures=json.dumps([_laser(neu_pos, neu_rot)]),
                   sperrzonen=_daten(zonen=(zweite,), feld=None))
        self._poll_until_true(
            "(function(){const z=window.__lightosSperrzonen.info().zonen;"
            " return z.length===1 && z[0].name==='Bar';})()")
        self.assertAlmostEqual(self._info()["zonen"][0]["x"], -3.0, places=5)
        vorher = self._eval("window.__lightos.renderInfo ? 1 : 0")
        self.assertEqual(vorher, 1)
        self._poll(fixtures=json.dumps([_laser(neu_pos, neu_rot)]),
                   sperrzonen=_daten(zonen=(), feld=None))
        self._poll_until_true("window.__lightosSperrzonen.info().zonen.length===0")
        reste = self._eval(
            "(function(){let n=0; window.__lightosSperrzonen.info();"
            " const THREE=window.THREE; const s=[];"
            " (function such(o){ if(o.userData&&o.userData.sperrzonenAnzeige) n++;"
            "   (o.children||[]).forEach(such); })"
            " (window.__lightos.fixtures[%d].group.parent); return n;})()" % _FID)
        self.assertEqual(reste, 0, "Reste geloeschter Zonen/Felder in der Szene")

        # (7) Der Laser selbst ist unberuehrt: kein fremdes Kind am Geraet.
        fremd = self._eval(
            "(function(){let n=0; window.__lightos.fixtures[%d].group.traverse("
            "o=>{ if(o.userData&&o.userData.sperrzonenAnzeige) n++; }); return n;})()" % _FID)
        self.assertEqual(fremd, 0)


    # ── Darstellungs-Stile des Feldes (alt / a / b / c) ──────────────────────
    def _stil_info(self):
        return json.loads(self._eval(
            "JSON.stringify(window.__lightosSperrzonen.stilInfo())"))

    def _anzeige_objekte(self):
        return self._eval(
            "(function(){let n=0; window.__lightos.fixtures[%d].group.parent.traverse("
            "o=>{ if(o.userData&&o.userData.sperrzonenAnzeige) n++; }); return n;})()" % _FID)

    def test_stile_zeichnen_und_der_schalter_wirkt(self):
        pos, rot = (0.0, 5.6, 2.5), (0.0, 0.0, 0.0)
        feld = LaserFeld(links=20, rechts=20, oben=20, unten=20, zuschlag=5)
        publikum = Sperrzone(id="p", name="Publikum", x=0.0, y=0.0, z=8.5,
                             breite=11.0, hoehe=2.0, tiefe=8.0)
        technik = Sperrzone(id="t", name="Technik", x=8.6, y=0.0, z=0.5,
                            breite=2.4, hoehe=2.5, tiefe=4.0)
        zonen = (publikum, technik)
        namen = {z.id: z.name for z in zonen}

        def setze(p, r):
            self._poll(fixtures=json.dumps([_laser(p, r)]),
                       sperrzonen=_daten(zonen=zonen, feld=feld))
            sp = S.feld_spitze(p, r)
            achse = S.geraete_achsen(r)[0]
            # Lage UND Richtung muessen angekommen sein: die Ecke links-oben
            # liegt, auf die Achse projiziert, genau eine Feldlaenge voraus.
            self._poll_until_true(
                "(function(){const f=window.__lightosSperrzonen.info().felder[0];"
                " if(!f||!f.sichtbar) return false; const s=%s, a=%s, e=f.weltEcken[0];"
                " const d=Math.abs(f.x-s[0])+Math.abs(f.y-s[1])+Math.abs(f.z-s[2]);"
                " const v=(e[0]-s[0])*a[0]+(e[1]-s[1])*a[1]+(e[2]-s[2])*a[2];"
                " return d<1e-4 && Math.abs(v-f.ecken[0][2])<1e-3;})()"
                % (json.dumps(list(sp)), json.dumps(list(achse))))

        self._load_and_wait()
        setze(pos, rot)
        soll = S.pruefe_laser(_FID, "Laser", pos, rot, feld, zonen)
        self.assertEqual(soll.zonen, ["Publikum"])

        # Standard ist die bisherige Pyramide; der Schalter haengt (auch) an
        # window.__lightos, ohne dass app.js davon weiss.
        self.assertEqual(self._eval("window.__lightos.sperrzonenStil()"), "alt")
        self.assertEqual(self._eval("window.__lightosSperrzonen.stile"),
                         ["alt", "a", "b", "c"])
        vorher = self._stil_info()
        self.assertEqual(vorher["fehler"], "")
        self.assertTrue(vorher["felder"][0]["altSichtbar"])
        self.assertFalse(vorher["felder"][0]["extra"])
        self.assertFalse(vorher["lasersicht"]["sichtbar"])
        objekte_alt = self._anzeige_objekte()
        ecken_alt = self._info()["felder"][0]["weltEcken"]

        for stil in ("a", "b", "c"):
            with self.subTest(stil=stil):
                self.assertEqual(
                    self._eval("window.__lightos.sperrzonenStil(%r)" % stil), stil)
                self._eval("window.__lightos.__renderTick && window.__lightos.__renderTick()")
                i = self._stil_info()
                self.assertEqual(i["stil"], stil)
                self.assertEqual(i["fehler"], "", "Stil wirft beim Zeichnen")
                f = i["felder"][0]
                self.assertFalse(f["altSichtbar"], "alte Pyramide noch im Bild")
                self.assertTrue(f["extra"])
                # jedes neue Objekt ist als reine Anzeige gekennzeichnet
                self.assertEqual(f["ohneKennung"], 0)
                self.assertEqual([namen[z] for z in f["erreicht"]], soll.zonen)
                self.assertGreater(self._anzeige_objekte(), objekte_alt)
                z = {e["id"]: e for e in i["zonen"]}
                if stil == "a":
                    self.assertEqual(f["teile"]["ansatz"], 1.5)
                    self.assertGreater(f["teile"]["fuss"], 0)      # Boden
                    self.assertGreater(f["teile"]["schnitt"], 0)   # Publikum
                    self.assertEqual(z["p"]["zustand"], "")
                    self.assertFalse(i["lasersicht"]["sichtbar"])
                else:
                    self.assertGreater(f["teile"]["ansatz"], 1.5)
                    self.assertLess(f["teile"]["ansatz"], 5.0)
                    self.assertEqual(z["p"]["zustand"], "erreicht")
                    self.assertEqual(z["p"]["laser"], [_FID])
                    self.assertTrue(z["p"]["rand"])
                    self.assertIn("Laser %d erreicht diese Zone" % _FID, z["p"]["zusatz"])
                    self.assertGreater(z["p"]["deckkraft"], 0.3)
                    self.assertEqual(z["t"]["zustand"], "frei")
                    self.assertFalse(z["t"]["rand"])
                    self.assertLess(z["t"]["deckkraft"], 0.2)
                    self.assertTrue(z["t"]["schildSichtbar"])
                if stil == "b":
                    # die beiden unteren Feldkanten enden auf der Zone
                    self.assertEqual(f["teile"]["kanten"], 2)
                    self.assertGreater(f["teile"]["umriss"], 0)
                    self.assertFalse(i["lasersicht"]["sichtbar"])
                if stil == "c":
                    ls = i["lasersicht"]
                    self.assertTrue(ls["sichtbar"])
                    self.assertFalse(ls["faengtEingabe"])
                    self.assertGreater(ls["breite"], 100)
                    self.assertEqual(ls["titel"], "Sicht von Laser %d" % _FID)
                    self.assertEqual(ls["zonen"], ["Publikum", "Technik"])
                    self.assertEqual(ls["erreicht"], ["Publikum"])
                    # ein-/ausblendbar
                    self.assertFalse(self._eval("window.__lightosSperrzonen.lasersicht(false)"))
                    self.assertFalse(self._stil_info()["lasersicht"]["sichtbar"])
                    self.assertTrue(self._eval("window.__lightosSperrzonen.lasersicht(true)"))
                    self.assertTrue(self._stil_info()["lasersicht"]["sichtbar"])
                # Zonen bleiben, was sie sind: an ihrer Stelle, ohne Eingabe zu fangen
                info = self._info()
                self.assertEqual([e["raycastTreffer"] for e in info["zonen"]], [0, 0])
                self.assertEqual(info["felder"][0]["weltEcken"], ecken_alt)
                # am Geraet haengt weiterhin nichts
                self.assertEqual(self._eval(
                    "(function(){let n=0; window.__lightos.fixtures[%d].group.traverse("
                    "o=>{ if(o.userData&&o.userData.sperrzonenAnzeige) n++; }); return n;})()"
                    % _FID), 0)

        # Das Bild folgt derselben Vorschrift wie die Rechnung in Python —
        # in jedem Stil, fuer getroffene wie freie Lagen.
        lagen = [((0.0, 5.6, 2.5), (-30.0, 0.0, 0.0)), ((0.0, 5.6, 2.5), (30.0, 0.0, 0.0)),
                 ((0.0, 5.6, 2.5), (10.0, 75.0, 0.0)), ((0.0, 5.6, 2.5), (0.0, 180.0, 0.0)),
                 ((3.0, 4.0, -6.0), (0.0, 0.0, 0.0)), ((8.6, 1.0, 0.5), (-80.0, 0.0, 0.0)),
                 ((0.0, 5.6, 2.5), (0.0, -55.0, 25.0)),
                 # nach unten geneigt, vom Boden aus: nur der OBERE Rand reicht hin
                 ((0.0, 0.2, -10.0), (22.0, 0.0, 0.0))]
        self.assertEqual(S.pruefe_laser(_FID, "Laser", lagen[-1][0], lagen[-1][1],
                                        feld, zonen).zonen, ["Publikum"])
        gesehen = set()
        for stil in ("c", "a", "alt", "b"):
            self._eval("window.__lightos.sperrzonenStil(%r)" % stil)
            for p, r in lagen:
                setze(p, r)
                erwartet = S.pruefe_laser(_FID, "Laser", p, r, feld, zonen).zonen
                i = self._stil_info()
                self.assertEqual(i["fehler"], "")
                self.assertEqual(sorted(namen[z] for z in i["felder"][0]["erreicht"]),
                                 sorted(erwartet), f"Stil {stil}, Lage {p} {r}")
                gesehen.add(tuple(sorted(erwartet)))
        self.assertIn((), gesehen)                      # auch eine freie Lage war dabei
        self.assertGreater(len(gesehen), 2)

        # Unbekannter Stil aendert nichts; zurueck auf 'alt' raeumt restlos auf.
        self.assertEqual(self._eval("window.__lightos.sperrzonenStil('gibtsnicht')"), "b")
        setze(pos, rot)
        self.assertEqual(self._eval("window.__lightos.sperrzonenStil('alt')"), "alt")
        nachher = self._stil_info()
        self.assertEqual(nachher["zonen"], vorher["zonen"])
        self.assertEqual(nachher["felder"], vorher["felder"])
        self.assertFalse(nachher["lasersicht"]["sichtbar"])
        self.assertEqual(self._anzeige_objekte(), objekte_alt)


if __name__ == "__main__":
    unittest.main()
