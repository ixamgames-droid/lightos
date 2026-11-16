"""LAS-27: „bunt" im 3D — mehrfarbige Strahlen (offscreen QtWebEngine).

Vorher: ``payload.laser.bunt`` kam an, ``scene_src/fixtures/laser.js`` wertete
es nicht aus — ein EL-400RGB MK2 auf Farbe „bunt" (Wert 0, auch der Grundwert)
zeichnete alle Strahlen und den Muster-Mantel in EINER Geraetefarbe (weiss).
Nachher: jeder Einzelstrahl und jedes Mantel-Segment bekommt reihum eine Farbe
aus ``LASER_BUNT_PALETTE`` (Rot, Gruen, Blau, Gelb, Cyan, Magenta), fest nach
seinem Index — von Bild zu Bild dieselbe Zuordnung. Ohne „bunt" bleibt es eine
Farbe. Gemessen an Materialfarben und Eckpunkt-Farben der Szene.
"""
import json
from types import SimpleNamespace

import test_viz79_laser_strahlen_scene as v79
from test_viz95_lasermuster_payload import el400, el400_kanaele

from src.ui.visualizer.visualizer_service import _build_fixture_payload

_FID = v79._FID
_FX = SimpleNamespace(fid=_FID, fixture_type="laser")

# Farben der sichtbaren Einzelstrahlen (nach Index) und der Mantel-Segmente
# (Eckpunkt-Farbe x Materialfarbe), gerundet als Hex-Text.
_FARBEN_JS = """
(function(){
  const f = window.__lightos.fixtures['%d'];
  const rig = f.laserRig, k = rig.kegel;
  const hex = c => [c.r, c.g, c.b].map(v => Math.round(Math.min(1, v) * 255)).join(',');
  const strahlen = rig.beams.filter(b => b.visible).map(b => hex(b.material.color));
  const a = k.geometry.getAttribute('color');
  const m = k.material.color;
  const segmente = [];
  for (let s = 0; s < rig.kegelSegmente; s++) {
    const i = s * 3;
    segmente.push(hex({ r: a.getX(i) * m.r, g: a.getY(i) * m.g, b: a.getZ(i) * m.b }));
  }
  return JSON.stringify({ strahlen, segmente, kegel: k.visible,
                          opacity: rig.beams.filter(b => b.visible).map(b => b.material.opacity) });
})()
"""


class Las27BuntSceneTest(v79.Viz79LaserStrahlenSceneTest):
    _kanaele = None

    def _el400(self, seq, **kw):
        if Las27BuntSceneTest._kanaele is None:
            Las27BuntSceneTest._kanaele = el400_kanaele()
        p = _build_fixture_payload(_FX, el400(**kw), Las27BuntSceneTest._kanaele)
        self.assertEqual(self._apply([dict(p, fid=_FID)], seq), 1)
        return json.loads(self._eval(
            "JSON.stringify(window.__lightos.laserInfo(%d))" % _FID))

    def _farben(self):
        return json.loads(self._eval(_FARBEN_JS % _FID))

    def _zwei_bilder(self):
        # Offscreen drosselt rAF — die Bilder selbst treiben (render_loop.js).
        self._eval("window.__lightos.requestRender(); window.__lightos.__renderTick();"
                   " window.__lightos.requestRender(); window.__lightos.__renderTick(); true")

    def _bauen_el400(self):
        self._load_and_wait()
        self._eval("window.__lightos.setViewMode('3D'); true")
        self._bauen(dict(v79._laser(), intensity=255))

    def test_gepunktet_bunt_mehrfarbig_sonst_einfarbig(self):
        self._bauen_el400()
        i = self._el400(1, muster=96, farbe=0)        # gepunkteter Kreis, bunt
        self.assertTrue(i["bunt"])
        f = self._farben()
        self.assertGreaterEqual(len(f["strahlen"]), 6)
        self.assertGreaterEqual(len(set(f["strahlen"])), 3,
                                f"bunt: zu wenige Farben {f['strahlen']}")
        # Nachbarn verschieden (reihum), Helligkeit wie sonst: eine Deckkraft.
        for a, b in zip(f["strahlen"], f["strahlen"][1:]):
            self.assertNotEqual(a, b)
        self.assertEqual(len(set(f["opacity"])), 1)
        # Nach zwei Bildern und einem erneuten DMX-Takt dieselbe Zuordnung.
        self._zwei_bilder()
        self._el400(2, muster=96, farbe=0)
        self._zwei_bilder()
        self.assertEqual(self._farben()["strahlen"], f["strahlen"],
                         "bunt flackert: Zuordnung hat sich geaendert")
        # Ohne bunt (Gruen 120): genau eine Farbe.
        i = self._el400(3, muster=96, farbe=120)
        self.assertFalse(i["bunt"])
        g = self._farben()
        self.assertEqual(len(set(g["strahlen"])), 1, g["strahlen"])
        self.assertEqual(len(g["strahlen"]), len(f["strahlen"]))
        # Zurueck auf bunt: wieder dieselbe Zuordnung wie vorher.
        self._el400(4, muster=96, farbe=0)
        self.assertEqual(self._farben()["strahlen"], f["strahlen"])

    def test_kreis_mantel_bunt_und_zurueck(self):
        """Grundstellung des EL-400: Muster 0 (Kreis, nur Mantel) + Farbe 0
        (bunt) — gerade dieser Fall war weiss."""
        self._bauen_el400()
        self._el400(1, muster=0, farbe=0)
        f = self._farben()
        self.assertTrue(f["kegel"])
        self.assertEqual(len(f["segmente"]), 48)
        self.assertGreaterEqual(len(set(f["segmente"])), 3, f["segmente"][:8])
        self._zwei_bilder()
        self._el400(2, muster=0, farbe=0)
        self.assertEqual(self._farben()["segmente"], f["segmente"])
        self._el400(3, muster=0, farbe=12)            # Rot: eine Farbe
        r = self._farben()
        self.assertEqual(len(set(r["segmente"])), 1, r["segmente"][:8])
        rgb = [int(v) for v in r["segmente"][0].split(",")]
        self.assertGreater(rgb[0], 230)
        self.assertLess(rgb[1], 80)
        # Musterwechsel bei bunt: die neuen Segmente sind wieder bunt.
        self._el400(4, muster=160, farbe=0)           # Quadrat, 4 Segmente
        q = self._farben()
        self.assertEqual(len(q["segmente"]), 4)
        self.assertEqual(len(set(q["segmente"])), 4)

    def test_ohne_laser_block_bleibt_es_einfarbig(self):
        """Alter Payload ohne ``laser``-Block (Grobweg/Faecher): eine Farbe."""
        self._bauen_el400()
        self.assertEqual(self._apply([v79._gruen()], 1), 1)
        f = self._farben()
        self.assertEqual(len(f["strahlen"]), 5)
        self.assertEqual(len(set(f["strahlen"])), 1)

    def test_bunt_aus_bei_blackout(self):
        self._bauen_el400()
        self._el400(1, muster=96, farbe=0)
        p = _build_fixture_payload(_FX, el400(muster=96, farbe=0),
                                   Las27BuntSceneTest._kanaele)
        self._apply([dict(p, fid=_FID, intensity=0)], 2)
        self.assertEqual(self._farben()["strahlen"], [],
                         "Helligkeit 0: bunte Strahlen leuchten weiter")


# Geerbte VIZ-79-Tests laufen in ihrer eigenen Datei, nicht hier noch einmal.
for _name in dir(v79.Viz79LaserStrahlenSceneTest):
    if _name.startswith("test_"):
        setattr(Las27BuntSceneTest, _name, None)


if __name__ == "__main__":
    import unittest
    unittest.main()
