"""VIZ-102: Gobo-Muster ueber die Buehnenkante, nichts schwebt — Szenen-Tests.

Rueckmeldung des Projektinhabers nach der Live-Demo von VIZ-96:

1. Die Projektion endete an der Buehnenkante. Jetzt laeuft sie auf dem
   Hallenboden weiter (keine Grenze am Licht, nur noch die Reichweite fuer den
   Abfall in der Ferne), und der Kegel waechst mit dem Ueberhang stufenlos bis
   zur Flaeche darunter.
2. Beim Tetris-Gobo hingen Vierecke vor der Buehne in der Luft: das flache
   Rueckfall-Muster ragte als Scheibe ueber die Kante der getroffenen
   Oberseite. Jetzt wird die Scheibe an der Kante beschnitten (Clipping-Ebenen,
   ab dem Bau am Material — kein Programmwechsel), und der Rest liegt als
   zweite Scheibe auf der Flaeche darunter, ausserhalb des Schattens der
   Oberseite. Gilt auf allen Stufen; ohne Kante ist alles wie vorher.
3. Reine Gobo-DREHUNG zeichnete in jedem Bild alle Shadow-Maps neu (die
   Lichtlage wackelte in den letzten Stellen, weil sie aus der gedrehten
   Kegel-Matrix kommt). Jetzt: Drehung = nur Uniforms, kein Schattendurchlauf.

Gemessen ueber die ECHTE Seite (Produktiv-Push): Zustand, Ebenen, Uniforms.
"""
import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

from test_viz96_gobo_projektion_scene import (         # noqa: E402
    _Basis, _FID, _RING, _payload)


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


_Z_JS = """
(function(){
  const L = window.__lightos, T = window.THREE, f = L.fixtures['%d'];
  const ebenen = (m) => (m.clippingPlanes || []).map(
    p => [p.normal.x, p.normal.y, p.normal.z, p.constant]);
  const a = f.floorSpot, b = f.floorSpot2 || null;
  const pool = L.spotPoolInfo(), g = L.goboProjektionInfo();
  const i = pool.traeger ? pool.traeger.indexOf(%d) : -1;
  const l = i >= 0 ? L.spotPoolLights()[i] : null;
  const p = f.beam.geometry.parameters;
  f.beam.updateWorldMatrix(true, false);
  const apex = f.beam.localToWorld(new T.Vector3(0, p.height / 2, 0));
  let scene = f.group; while (scene.parent) scene = scene.parent;
  let unterInSzene = 0;
  scene.traverse(o => { if (o.userData && o.userData.goboUnterScheibe) unterInSzene += 1; });
  return JSON.stringify({
    laenge: f.baseBeamLength * f.beam.scale.y, grund: f.baseBeamLength,
    durchmesser: 2 * p.radius * f.beam.scale.x, apex: [apex.x, apex.y, apex.z],
    fleckY: a.position.y, ebenen: ebenen(a.material), version: a.material.version,
    deck: a.material.opacity, maske: a.layers.mask, sichtbar: a.visible,
    unter: b ? { sichtbar: b.visible, y: b.matrix.elements[13], ebenen: ebenen(b.material),
                 schnitt: b.material.clipIntersection, deck: b.material.opacity,
                 anteil: (f._goboUntenDeck === undefined) ? null : f._goboUntenDeck,
                 maske: b.layers.mask, gleicheKarte: b.material.map === a.material.map,
                 gleicheFarbe: b.material.color.equals(a.material.color),
                 additiv: b.material.blending === T.AdditiveBlending,
                 fest: b.matrixAutoUpdate === false } : null,
    unterInSzene: unterInSzene,
    fern: (i >= 0 && g.fern) ? g.fern[i] : null,
    fernQ: (f._goboFernQ === undefined) ? null : f._goboFernQ,
    reich: (f._goboReich === undefined) ? null : f._goboReich,
    rand: L.__goboRand ? L.__goboRand() : null,
    weite: l ? l.position.distanceTo(l.target.position) : null,
    hatEbene: 'ebene' in g,
    schatten: L.shadowUpdateStats().neubauten,
  });
})()
"""

_GROSS = (20.0, 1.0, 20.0)     # Buehnenplatte, Oberkante 1,0 m


def _behalten(ebenen, x, y, z):
    """Normale Clipping-Ebenen: behalten, wenn der Punkt vor ALLEN liegt."""
    return all(e[0] * x + e[1] * y + e[2] * z + e[3] >= 0 for e in ebenen)


def _ausgespart(ebenen, x, y, z):
    """clipIntersection: verworfen nur, wenn der Punkt hinter ALLEN liegt."""
    return all(e[0] * x + e[1] * y + e[2] * z + e[3] < 0 for e in ebenen)


class _Viz102Basis(_Basis):
    def _z(self):
        return self._json(_Z_JS % (_FID, _FID))

    def _platte(self, z_mitte, rot=0.0):
        self._bridge_obj.addStageObjectData.emit(json.dumps({
            "id": "v102", "type": "platform", "rotation": rot,
            "position": {"x": 0.0, "y": 0.5, "z": z_mitte},
            "size": {"x": _GROSS[0], "y": _GROSS[1], "z": _GROSS[2]},
        }))
        self._poll_until_true("!!window.__lightos.stageObjects['v102']")

    def _schiebe(self, z_mitte):
        self._eval("(function(){ const m = window.__lightos.stageObjects['v102'].mesh;"
                   " m.position.z = %r; m.updateMatrixWorld(true); return 1; })()" % float(z_mitte))

    def _zeige(self, **attrs):
        self._push(_payload(**attrs))
        self._bild()
        return self._z()


class Viz102KanteTest(_Viz102Basis):
    def test_ohne_kante_alles_wie_vorher(self):
        self._load_and_wait()
        z = self._zeige(gobo_wheel=_RING)
        self.assertEqual(len(z["ebenen"]), 4, "vier Ebenen ab dem Bau (Programm bleibt gleich)")
        for x, zz in ((0, 0), (50, -80), (-300, 300)):
            self.assertTrue(_behalten(z["ebenen"], x, 0.01, zz), "Grundstellung schneidet nichts")
        self.assertIsNone(z["unter"])
        self.assertEqual(z["unterInSzene"], 0)
        self.assertFalse(z["hatEbene"], "keine Grenzebene mehr am Licht")
        self.assertAlmostEqual(z["fleckY"], 0.01, places=6)

    def test_mitten_auf_der_platte_keine_zweite_scheibe(self):
        self._load_and_wait()
        self._platte(0.0)
        z = self._zeige(gobo_wheel=_RING)
        self.assertAlmostEqual(z["fleckY"], 1.01, places=6)
        self.assertTrue(_behalten(z["ebenen"], 0, 1.01, 0))
        self.assertFalse(_behalten(z["ebenen"], 0, 1.01, -10.5), "jenseits der Kante beschnitten")
        self.assertTrue(z["unter"] is None or not z["unter"]["sichtbar"])
        # Kegel endet auf der Platte wie bisher.
        self.assertAlmostEqual(z["laenge"], z["apex"][1] - 1.0, delta=0.08)

    def test_an_der_kante_beschnitten_und_rest_am_hallenboden(self):
        self._load_and_wait()
        self._platte(9.7)                    # Kante bei z = -0,3; Strahlmitte bei z = 0
        offen = self._zeige(gobo_wheel=0)
        self.assertGreater(offen["durchmesser"] / 2, 0.5, "Aufbau: der Fleck ragt ueber die Kante")
        version = offen["version"]
        # Offener Strahl: Fleck beschnitten, Kegel endet auf der Platte, keine zweite Scheibe.
        self.assertFalse(_behalten(offen["ebenen"], 0, 1.01, -0.6))
        self.assertTrue(_behalten(offen["ebenen"], 0, 1.01, 0.5))
        self.assertTrue(offen["unter"] is None or not offen["unter"]["sichtbar"])
        self.assertAlmostEqual(offen["laenge"], offen["apex"][1] - 1.0, delta=0.08)

        z = self._zeige(gobo_wheel=_RING)
        # 1) die Scheibe auf der Platte endet an der Kante ...
        self.assertAlmostEqual(z["fleckY"], 1.01, places=6)
        self.assertTrue(_behalten(z["ebenen"], 0, 1.01, 0.5))
        self.assertTrue(_behalten(z["ebenen"], 0, 1.01, -0.29))
        self.assertFalse(_behalten(z["ebenen"], 0, 1.01, -0.31), "Muster haengt vor der Kante in der Luft")
        # 2) ... der Rest liegt am Hallenboden, ausserhalb des Schattens der Platte.
        u = z["unter"]
        self.assertIsNotNone(u, "kein Muster auf dem Hallenboden")
        self.assertTrue(u["sichtbar"] and u["fest"] and u["additiv"])
        self.assertAlmostEqual(u["y"], 0.01, places=6)
        self.assertTrue(u["schnitt"])
        self.assertTrue(u["gleicheKarte"] and u["gleicheFarbe"])
        ay = z["apex"][1]
        schattenkante = -0.3 * ay / (ay - 1.0)      # Kante vom Licht aus auf den Boden gestreckt
        self.assertTrue(_ausgespart(u["ebenen"], 0, 0.01, schattenkante + 0.02),
                        "Licht im Schatten der Platte")
        self.assertTrue(_ausgespart(u["ebenen"], 0, 0.01, 0.5))
        self.assertFalse(_ausgespart(u["ebenen"], 0, 0.01, schattenkante - 0.02))
        self.assertFalse(_ausgespart(u["ebenen"], 0, 0.01, -1.5))
        # Die zweite Scheibe folgt je Bild Deckkraft und Ebenen-Maske der ersten
        # (auf Hoch projiziert das Geraet: beide ausgeblendet) — nie heller als
        # oben: mit dem Ueberhang eingeblendet, mit dem Abstandsquadrat schwaecher.
        self.assertTrue(0 < u["anteil"] <= ((ay - 1.0) / ay) ** 2 + 1e-9, u)
        self.assertAlmostEqual(u["deck"], z["deck"] * u["anteil"], places=9)
        self.assertEqual(u["maske"], z["maske"])
        # 3) der Kegel reicht ueber die Platte hinaus Richtung Boden — und
        #    bleibt dabei gleich weit geoeffnet (laenger hiesse sonst spitzer:
        #    Muster und Projektion schrumpften auf der Platte).
        self.assertGreater(z["laenge"], offen["laenge"] + 0.2)
        self.assertAlmostEqual(z["durchmesser"] / z["laenge"],
                               offen["durchmesser"] / offen["laenge"], delta=0.004)
        self.assertGreater(z["durchmesser"], offen["durchmesser"] * 1.03)
        self.assertLessEqual(z["laenge"], min(z["grund"], ay) + 0.08)
        # 4) nur Werte: kein needsUpdate am Material der ersten Scheibe durch die Kante.
        self.assertEqual(self._zeige(gobo_wheel=_RING, gobo_rotation=40)["version"], z["version"])
        self.assertGreaterEqual(z["version"], version)
        # Dimmer folgt.
        d = self._zeige(gobo_wheel=_RING, intensity=100)
        self.assertAlmostEqual(d["unter"]["deck"], d["deck"] * d["unter"]["anteil"], places=9)
        # Gobo aus: zweite Scheibe weg, erste bleibt beschnitten.
        aus = self._zeige(gobo_wheel=0)
        self.assertFalse(aus["unter"]["sichtbar"])
        self.assertFalse(_behalten(aus["ebenen"], 0, 1.01, -0.6))
        # Platte weg vom Strahl: Ebenen wieder frei.
        self._schiebe(40.0)
        frei = self._zeige(gobo_wheel=_RING)
        self.assertAlmostEqual(frei["durchmesser"], offen["durchmesser"], delta=1e-6,
                               msg="ohne Kante wieder die Weite aus Zoom/Iris allein")
        self.assertAlmostEqual(frei["fleckY"], 0.01, places=6)
        self.assertTrue(_behalten(frei["ebenen"], 0, 0.01, -5))
        self.assertFalse(frei["unter"]["sichtbar"])

    def test_kegel_waechst_stufenlos_ueber_die_kante(self):
        self._load_and_wait()
        self._platte(0.0)
        self._zeige(gobo_wheel=_RING)
        reihe = []
        kante = -10.0
        while kante <= 0.4:
            self._schiebe(kante + 10.0)          # Kante bei z = `kante`
            z = self._zeige(gobo_wheel=_RING)
            reihe.append((round(kante, 2), z["laenge"], z["fleckY"]))
            kante += 0.1 if kante > -4.05 else 3.0
        laengen = [l for _, l, _ in reihe]
        self.assertAlmostEqual(laengen[0], z["apex"][1] - 1.0, delta=0.08, msg="ganz auf der Platte")
        self.assertTrue(all(b >= a - 1e-9 for a, b in zip(laengen, laengen[1:])), reihe)
        # Nach der Kante (Strahlmitte trifft den Boden) dieselbe Laenge wie kurz davor.
        ziel = min(z["grund"], z["apex"][1])
        self.assertAlmostEqual(laengen[-1], ziel, delta=0.08)
        self.assertAlmostEqual(reihe[-1][2], 0.01, places=6)
        self.assertLess(max(b - a for a, b in zip(laengen, laengen[1:])), 0.35,
                        f"Sprung der Kegellaenge an der Kante: {reihe}")

    def test_gedrehte_platte(self):
        self._load_and_wait()
        self._platte(9.7, rot=0.6)
        z = self._zeige(gobo_wheel=_RING)
        # Kante jetzt schraeg: ihr Abstand vom Auftreffpunkt (0, 0) entlang der
        # gedrehten z-Achse bleibt 0,3 m... die Mitte dreht nicht mit — Abstand neu.
        import math
        c, s = math.cos(0.6), math.sin(0.6)
        lz = (0 - 0.0) * s + (0 - 9.7) * c            # lokale z-Koordinate des Auftreffpunkts
        innen = 10.0 - abs(lz)
        self.assertGreater(innen, 0, "Aufbau: Strahlmitte auf der Platte")
        self.assertAlmostEqual(z["fleckY"], 1.01, places=6)
        # Punkt knapp innerhalb/ausserhalb entlang der lokalen z-Achse (Welt: (s, c)).
        for d, soll in ((innen - 0.05, True), (innen + 0.05, False)):
            self.assertEqual(_behalten(z["ebenen"], -d * s, 1.01, -d * c), soll, (d, z["ebenen"]))

    def test_projektion_laeuft_weiter_bis_zur_reichweite_des_kegels(self):
        self._load_and_wait()
        self._platte(9.7)
        z = self._zeige(gobo_wheel=_RING)
        self.assertFalse(z["hatEbene"])
        q, reich = z["fern"]
        # Senkrecht nach unten: ferner Kegelrand auf der Platte = Abstand zur Platte.
        self.assertAlmostEqual(q, z["fernQ"], places=6)
        self.assertAlmostEqual(q, z["weite"], delta=0.25)
        # ... und die Projektion reicht so weit wie der (verlaengerte) Kegel.
        self.assertAlmostEqual(reich, z["laenge"], delta=1e-6)
        self.assertGreater(reich, q + 0.2, "Kegel ragt ueber die Kante: die Projektion geht mit")
        # Mitten auf der Platte: Reichweite = Muster auf seiner Flaeche.
        self._schiebe(0.0)
        m = self._zeige(gobo_wheel=_RING)
        self.assertAlmostEqual(m["fern"][1], m["fern"][0], delta=0.1)
        self._schiebe(9.7)
        aus = self._zeige(gobo_wheel=0)
        self.assertGreaterEqual(aus["fern"][0], 1e6)
        self.assertGreaterEqual(aus["fern"][1], 1e6)

    def test_entfernen_raeumt_die_zweite_scheibe_ab(self):
        self._load_and_wait()
        self._platte(9.7)
        z = self._zeige(gobo_wheel=_RING)
        self.assertEqual(z["unterInSzene"], 1)
        self._eval("(function(){ let s = window.__lightos.fixtures['%d'].group;"
                   " while (s.parent) s = s.parent; window.__s102 = s; return 1; })()" % _FID)
        self._bridge_obj.fixtureRemoved.emit(_FID)
        self._poll_until_true("!window.__lightos.fixtures['%d']" % _FID)
        n = self._eval("""(function(){ let n = 0;
          window.__s102.traverse(o => { if (o.userData && o.userData.goboUnterScheibe) n += 1; });
          return n; })()""")
        self.assertEqual(n, 0)


# Nachbesserung: das Gobo-Bild liegt IM Kegel. Je Stil der groesste Abstand
# (Anteil der Kachel) eines sichtbaren Motiv-Pixels von der Mitte, dazu der
# Oeffnungswinkel des projizierenden Lichts gegen den des sichtbaren Kegels.
_IM_KEGEL_JS = """
(function(){
  const L = window.__lightos, f = L.fixtures['%d'], out = { stile: {} };
  for (const stil of ['ring_slits', 'ovals', 'circle_of_circles', 'tetris', 'dots', 'spiral', 'zebra']) {
    const c = L.__goboTexture(stil).image, g = c.getContext('2d');
    const d = g.getImageData(0, 0, c.width, c.height).data, M = c.width / 2;
    let rmax = 0, voll = 0;
    for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) {
      const a = d[(y * c.width + x) * 4 + 3], r = Math.hypot(x + 0.5 - M, y + 0.5 - M) / M;
      if (a > 12 && d[(y * c.width + x) * 4] > 127 && r > rmax) rmax = r;
      if (a > 242 && r > voll) voll = r;
    }
    out.stile[stil] = [rmax, voll];
  }
  const pool = L.spotPoolInfo(), i = pool.traeger.indexOf(%d);
  const l = L.spotPoolLights()[i], p = f.beam.geometry.parameters;
  const e = f.beam.matrixWorld.elements;
  out.tanKegel = (p.radius * Math.hypot(e[0], e[1], e[2])) / (p.height * Math.hypot(e[4], e[5], e[6]));
  out.tanLicht = Math.tan(l.angle);
  out.karte = [l.shadow.mapSize.width, l.shadow.mapSize.height];
  return JSON.stringify(out);
})()
"""


class Viz102ImKegelTest(_Viz102Basis):
    def test_motiv_liegt_im_kegel_mit_weicher_kante(self):
        self._load_and_wait()
        for zoom_attrs in ({}, {"pan": 110, "tilt": 150}):
            self._zeige(gobo_wheel=_RING, **zoom_attrs)
            z = self._json(_IM_KEGEL_JS % (_FID, _FID))
            # Die Kachel reicht bis 1,0; der Kegelrand liegt bei 0,88. Das Licht
            # oeffnet auf die ganze Kachel, das BILD endet am Kegelrand.
            rand = z["tanKegel"] / z["tanLicht"]
            self.assertAlmostEqual(rand, 0.88, delta=0.005)
            for stil, (rmax, voll) in z["stile"].items():
                # sichtbar hoechstens 5 % ueber den Kegelrand (weiche Kante) ...
                self.assertLessEqual(rmax, rand * 1.05, f"{stil}: Licht ausserhalb des Kegels")
                # ... voll deckend nur innerhalb, und das Motiv reicht bis an den Rand.
                self.assertLessEqual(voll, rand, stil)
                self.assertGreater(rmax, rand * 0.93, f"{stil}: Motiv fuellt den Kegel nicht")
        self.assertEqual(z["karte"], [1024, 1024], "feinere Shadow-Map fuer die Kante im Motiv")


class Viz102NiedrigTest(_Viz102Basis):
    TIER = "low"

    def test_niedrig_ohne_kante_unveraendert_mit_kante_beschnitten(self):
        self._load_and_wait()
        z = self._zeige(gobo_wheel=_RING, intensity=220)
        self.assertAlmostEqual(z["deck"], (220 / 255) * 0.55 * 1.5, places=6)
        self.assertEqual(z["maske"], 1)
        self.assertIsNone(z["unter"])
        self.assertTrue(_behalten(z["ebenen"], 7, 0.01, -9))
        self._platte(9.7)
        z = self._zeige(gobo_wheel=_RING, intensity=220)
        self.assertFalse(_behalten(z["ebenen"], 0, 1.01, -0.31), "auch auf Niedrig schwebt nichts")
        u = z["unter"]
        self.assertTrue(u and u["sichtbar"])
        self.assertEqual(u["maske"], 1)
        self.assertAlmostEqual(u["deck"], (220 / 255) * 0.55 * 1.5 * u["anteil"], places=6)
        self.assertTrue(0 < u["anteil"] < 1)
        self.assertAlmostEqual(u["y"], 0.01, places=6)


class Viz102SchattenTest(_Viz102Basis):
    def test_gobo_drehung_loest_keinen_schattendurchlauf_aus(self):
        self._load_and_wait()
        self._uhr(0)
        self._zeige(gobo_wheel=_RING, gobo_rotation=0)
        self._bild(50)
        start = self._z()["schatten"]
        t = 50
        for rot in (7, 23, 51, 88, 131, 170, 201, 240, 13, 99, 180, 255):
            self._push(_payload(gobo_wheel=_RING, gobo_rotation=rot))
            for _ in range(3):
                t += 40
                self._bild(t)
        z = self._z()
        self.assertEqual(z["schatten"] - start, 0,
                         "Gobo-Drehung ist nur ein Uniform — kein Schattendurchlauf")
        # Gegenprobe: eine echte Kopfbewegung erneuert die Shadow-Maps weiter.
        self._push(_payload(gobo_wheel=_RING, gobo_rotation=255, pan=100, tilt=150))
        for _ in range(3):
            t += 40
            self._bild(t)
        self.assertGreater(self._z()["schatten"], z["schatten"])


if __name__ == "__main__":
    unittest.main()
