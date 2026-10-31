"""VIZ-95: echte Lasermuster im 3D — Szene (offscreen QtWebEngine).

Vorher (bis VIZ-95): ein EL-400RGB MK2 in „Statische Muster" zeigte fuer
jedes Muster eine der vier Grobformen (``gobo_wheel % 4``) — fuer „Kreis"
(Wert 0) einen Faecher aus fuenf Strahlen. Nachher: der Payload traegt das
Muster aus den Profilangaben (LAS-33), der Viewer zeichnet daraus einen
Strahlenkegel (Kreis-Mantel) bzw. Einzelstrahlen (gepunktet), in der
Profilfarbe, in Groesse und Lage laut Profilrichtung.

Gemessen wird an den Werten der Szene (Pose, Kegel-Eckpunkte in Welt-
koordinaten, Materialfarben) — ``toDataURL`` ist offscreen leer.
"""
import json
import math
from types import SimpleNamespace

import test_viz79_laser_strahlen_scene as v79
from test_viz95_lasermuster_payload import el400, el400_kanaele

from src.ui.visualizer.visualizer_service import _build_fixture_payload

_FID = v79._FID
_FX = SimpleNamespace(fid=_FID, fixture_type="laser")

# Weltpunkte des Kegelmantels: Spitze und Konturpunkte (lokal z = Laenge).
_KEGEL_JS = """
(function(){
  const f = window.__lightos.fixtures['%d'];
  const rig = f.laserRig, k = rig.kegel;
  f.group.updateMatrixWorld(true);
  const a = k.geometry.getAttribute('position');
  const n = k.geometry.drawRange.count;
  const fern = [];
  const v = k.position.clone();
  for (let i = 0; i < n; i++) {
    if (i %% 3 === 0) continue;               // Spitze am Austrittsfenster
    v.set(a.getX(i), a.getY(i), a.getZ(i));
    k.localToWorld(v);
    fern.push([v.x, v.y, v.z]);
  }
  const strahlen = rig.beams.filter(b => b.visible).length;
  const c = (rig.beams[0].material.color);
  return JSON.stringify({ visible: k.visible, fern, strahlen,
                          start: [f.group.position.x, f.group.position.y, f.group.position.z],
                          farbe: [c.r, c.g, c.b], opacity: k.material.opacity,
                          kegelFarbe: [k.material.color.r, k.material.color.g, k.material.color.b] });
})()
"""


class Viz95LaserMusterSceneTest(v79.Viz79LaserStrahlenSceneTest):
    test_laser_schiesst_lange_sichtbare_strahlen_ins_publikum = None
    test_laser_hat_keinen_scheinwerferkegel = None
    test_dunkel_heisst_unsichtbar = None
    test_kegel_aus_schaltet_auch_laser_aus = None

    _kanaele = None

    def _el400(self, seq, **kw):
        if Viz95LaserMusterSceneTest._kanaele is None:
            Viz95LaserMusterSceneTest._kanaele = el400_kanaele()
        p = _build_fixture_payload(
            _FX, el400(**kw), Viz95LaserMusterSceneTest._kanaele)
        p = dict(p, fid=_FID)
        self.assertEqual(self._apply([p], seq), 1)
        return json.loads(self._eval(
            "JSON.stringify(window.__lightos.laserInfo(%d))" % _FID))

    def _kegel(self):
        return json.loads(self._eval(_KEGEL_JS % _FID))

    @staticmethod
    def _mitte(punkte):
        n = len(punkte)
        return [sum(p[i] for p in punkte) / n for i in range(3)]

    def _bauen_el400(self):
        self._load_and_wait()
        self._eval("window.__lightos.setViewMode('3D'); true")
        d = dict(v79._laser(), intensity=255)
        self._bauen(d)

    def test_vorher_nachher_kreis_statt_faecher(self):
        self._bauen_el400()
        # Vorher: ohne Muster-Block (wie bis VIZ-95) der Grob-Faecher.
        vorher = json.loads(self._eval(
            "JSON.stringify(window.__lightos.laserInfo(%d))" % _FID))
        self.assertEqual(vorher["form"], "faecher")
        self.assertIsNone(vorher["muster"])
        # Nachher: Statische Muster, Muster 0 = Kreis.
        i = self._el400(1, muster=0)
        self.assertEqual(i["muster"], "Kreis")
        self.assertEqual(i["kegel"], 48, "Kreis-Kegel mit 48 Segmenten erwartet")
        self.assertEqual(i["aktiv"], 0, "Kreis zeigt keine Einzelstrahlen")
        k = self._kegel()
        self.assertTrue(k["visible"], "Kreis-Kegel unsichtbar")
        # Ein Kreis: alle Konturpunkte gleich weit von ihrer Mitte entfernt.
        m = self._mitte(k["fern"])
        r = [math.dist(p, m) for p in k["fern"]]
        self.assertGreater(min(r), 1.0, "Kreis zu klein / entartet")
        self.assertLess(max(r) - min(r), 0.05 * max(r), "Kontur ist kein Kreis")
        # Ins Publikum (+Z), ueber den Koepfen.
        self.assertGreater(m[2], k["start"][2] + 10.0)
        self.assertGreater(m[1], 2.0)

    def test_gemessene_grundmuster(self):
        self._bauen_el400()
        erwartet = {0: ("Kreis", 48, 0), 32: ("vier kleine Kreise", 128, 0),
                    64: ("Strich", 1, 0), 160: ("Quadrat", 4, 0),
                    192: ("Stern", 10, 0), 240: ("pulsierender Kreis", 48, 0)}
        seq = 1
        for wert, (name, kegel, strahlen) in erwartet.items():
            i = self._el400(seq, muster=wert)
            seq += 1
            self.assertEqual((i["muster"], i["kegel"], i["aktiv"]),
                             (name, kegel, strahlen), f"Muster {wert}")
        for wert, name in ((96, "gepunkteter Kreis"), (128, "gepunktetes Dreieck")):
            i = self._el400(seq, muster=wert)
            seq += 1
            self.assertEqual(i["muster"], name)
            self.assertEqual(i["kegel"], 0, f"{name}: kein Mantel")
            self.assertGreaterEqual(i["aktiv"], 6, f"{name}: zu wenige Strahlen")
            self.assertEqual(self._kegel()["strahlen"], i["aktiv"])
        self.assertTrue(self._el400(seq, muster=240)["state"]["dz"],
                        "pulsierender Kreis bewegt sich nicht")

    def test_unbekanntes_muster_neutraler_einzelstrahl(self):
        self._bauen_el400()
        i = self._el400(1, muster=50)
        self.assertEqual(i["muster"], "unbekannt")
        self.assertEqual((i["kegel"], i["aktiv"]), (0, 1))
        self.assertEqual(self._kegel()["strahlen"], 1, "neutrale Form nicht sichtbar")

    def test_farbe_groesse_und_lage(self):
        self._bauen_el400()
        self._el400(1, muster=0, farbe=120)
        k = self._kegel()
        self.assertGreater(k["kegelFarbe"][1], 0.9)
        self.assertLess(k["kegelFarbe"][0], 0.3, "Gruen (120) nicht angekommen")
        self._el400(2, muster=0, farbe=12)
        self.assertGreater(self._kegel()["kegelFarbe"][0], 0.9)
        self.assertLess(self._kegel()["kegelFarbe"][1], 0.3, "Rot (12) nicht angekommen")

        def radius(**kw):
            self._el400(3 + radius.n, muster=0, **kw)
            radius.n += 1
            k = self._kegel()
            m = self._mitte(k["fern"])
            return max(math.dist(p, m) for p in k["fern"]), m
        radius.n = 0
        gross, _ = radius(groesse=0)
        klein, _ = radius(groesse=255)
        self.assertGreater(gross, 3 * klein, "Groesse 0 muss beim EL-400 gross sein")
        _, mitte = radius(x=5, y=5)
        _, rechts = radius(x=80)
        _, links = radius(x=200)
        _, oben = radius(y=80)
        _, unten = radius(y=200)
        self.assertAlmostEqual(mitte[0], 0.0, delta=0.5)
        self.assertGreater(rechts[0], mitte[0] + 2, "X 80 = rechts")
        self.assertLess(links[0], mitte[0] - 2, "X 200 = links")
        self.assertGreater(oben[1], unten[1] + 2, "Y 80 = oben, 200 = unten")

    def test_dunkel_bei_blackout_und_not_aus(self):
        """Laser-NOT-AUS/Blackout schreiben Betriebsart 0 (Laser aus) bzw.
        nullen die Helligkeit — Kegel und Strahlen muessen weg sein."""
        self._bauen_el400()
        self._el400(1, muster=0)
        self.assertTrue(self._kegel()["visible"])
        self._el400(2, muster=0, betrieb=0)               # Betriebsart „Laser aus"
        k = self._kegel()
        self.assertFalse(k["visible"], "NOT-AUS/Blackout: Kegel leuchtet weiter")
        self.assertEqual(k["strahlen"], 0)
        self.assertFalse(any(bm["visible"] for bm in self._miss()["beams"]))
        # Auch gepunktet bei Helligkeit 0.
        self._el400(3, muster=96)
        p = _build_fixture_payload(_FX, el400(muster=96),
                                   Viz95LaserMusterSceneTest._kanaele)
        self._apply([dict(p, fid=_FID, intensity=0)], 4)
        self.assertFalse(any(bm["visible"] for bm in self._miss()["beams"]))

    def test_musterwechsel_baut_keine_geometrie_neu(self):
        self._bauen_el400()
        self._el400(1, muster=0)
        js = ("(function(){ const f = window.__lightos.fixtures['%d']; const ids = [];"
              " f.group.traverse(o => { if (o.geometry) ids.push(o.geometry.uuid);"
              " if (o.material) ids.push(o.material.uuid); });"
              " return ids.sort().join(','); })()" % _FID)
        vorher = self._eval(js)
        seq = 2
        for wert in (0, 32, 64, 96, 128, 160, 192, 240, 50, 0):
            for x in (5, 80):
                self._el400(seq, muster=wert, x=x)
                seq += 1
        self.assertEqual(vorher, self._eval(js),
                         "Musterwechsel legt Geometrien/Materialien neu an")


if __name__ == "__main__":
    import unittest
    unittest.main()
