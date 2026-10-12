"""VIZ-96 (B3): Uebergaenge der Gobo-Projektion — Szenen-Tests.

Sichtpruefung von B1/B2 am Bildschirm (12 Moving Heads, Stufe Hoch):

1. Mit mehr Gobo-Geraeten als Pool-Lichtern wechselte die Zuordnung in EINEM
   Bild: Projektion weg, flaches Muster da. Jetzt blendet der alte Halter aus
   (sein flaches Muster ein), dann zieht das Licht um und blendet beim neuen
   Halter ein. Ein projizierendes Geraet haelt sein Licht zudem zaeher.
2. Das flache Muster war heller als die Projektion: angeglichen (nur wo die
   Projektion aktiv ist).
3. Die Treffersuche legte die ganze flache Scheibe auf die Oberseite einer
   getroffenen Traverse: mit Gobo rechnet sie durch schmale Koerper hindurch.
4. Der Kegel endete auf der Buehnenplatte, die Projektion lief weiter ueber den
   Hallenboden. B3 schnitt sie dort ab; seit VIZ-102 laeuft sie weiter und der
   Kegel reicht mit (``test_viz102_gobo_hallenboden_scene.py``).

Gemessen wird ueber die ECHTE Seite (Produktiv-Push), mit stellbarer Pool-Uhr:
Zustand, Uniform-Werte und Programmschluessel (offscreen ist der GL-Kontext
je nach Rechner verloren — die Bilder dazu stehen in der Sichtpruefung).
Stufe Niedrig bleibt in allen vier Punkten wie vor B3.
"""
import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

from test_viz96_gobo_projektion_scene import (         # noqa: E402
    _Basis, _FID, _PROGRAMM_JS, _RING, _VIELE, _geraet, _payload)


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


# Pool und Geraete als Zahlen. `anteil` je Slot = Anteil der Projektion des
# TRAEGERS (des Geraets, dessen Werte das Licht gerade zeigt).
_B3_JS = """
(function(){
  const L = window.__lightos, pool = L.spotPoolInfo(), g = L.goboProjektionInfo();
  const lichter = L.spotPoolLights();
  const geraete = {};
  for (const fid in L.fixtures) {
    const f = L.fixtures[fid];
    geraete[fid] = {
      ebene: f.floorSpot.layers.mask, deck: f.floorSpot.material.opacity,
      basis: (f._fleckBasis === undefined) ? null : f._fleckBasis,
      flach: (f._goboFlach === undefined) ? null : f._goboFlach,
      spot: f.spot.intensity, sichtbar: f.floorSpot.visible,
      farbe: [f.floorSpot.material.color.r, f.floorSpot.material.color.g,
              f.floorSpot.material.color.b],
      fleckY: f.floorSpot.position.y,
      laenge: f.baseBeamLength * f.beam.scale.y,
      durchmesser: 2 * f.beam.geometry.parameters.radius * f.beam.scale.x,
    };
  }
  return JSON.stringify({
    halter: pool.halter, traeger: pool.traeger || null, anteil: pool.goboAnteil || null,
    blenden: (pool.goboBlenden === undefined) ? null : pool.goboBlenden,
    projiziert: pool.goboProjiziert, vergaben: pool.vergaben,
    licht: lichter.map(l => l.intensity),
    maske: g.param ? g.param.map(p => p[0]) : null,
    dirty: L.renderStats().dirty, geraete: geraete,
  });
})()
"""

class _B3Basis(_Basis):
    def _pooluhr(self, t):
        self._eval("(function(){ window.__p96 = %r; window.__lightos.__spotPoolUhr("
                   "() => window.__p96); return 1; })()" % float(t))

    def _bild_um(self, t):
        self._eval("(function(){ window.__p96 = %r; const L = window.__lightos;"
                   " L.requestRender(); L.__renderTick(); return 1; })()" % float(t))
        return self._json(_B3_JS)

    def _z(self):
        return self._json(_B3_JS)

    def _stage(self, sid, typ, pos, size):
        self._bridge_obj.addStageObjectData.emit(json.dumps({
            "id": sid, "type": typ,
            "position": {"x": pos[0], "y": pos[1], "z": pos[2]},
            "size": {"x": size[0], "y": size[1], "z": size[2]},
        }))
        self._poll_until_true(f"!!window.__lightos.stageObjects['{sid}']")


# ── Punkt 1: Blende + Hysterese ──────────────────────────────────────────────

class Viz96B3BlendeTest(_B3Basis):
    GERAETE = [_geraet(fid, x=-9 + 2 * n, z=(n % 2) * 2) for n, fid in enumerate(_VIELE)]

    def _start(self):
        """10 Gobo-Geraete voll, 8 Lichter. Liefert (Zeit, Opfer, Herausforderer, Slot)."""
        self._load_and_wait()
        self._pooluhr(0)
        self._push(*[_payload(fid, gobo_wheel=_RING) for fid in _VIELE])
        self._bild_um(0)
        z = self._bild_um(20)
        self.assertIsNotNone(z["traeger"], "B3: der Pool kennt den Traeger je Licht")
        self.assertEqual(z["traeger"], z["halter"])
        self.assertEqual(z["anteil"], [1] * 8, "wer gerade erst aufleuchtet, projiziert sofort")
        self.assertEqual(z["blenden"], 0)
        ohne = [fid for fid in _VIELE if fid not in z["halter"]]
        self.assertEqual(len(ohne), 2)
        return 20.0, z["halter"][0], ohne[0], 0

    def _wechsel_ausloesen(self, t, opfer, dimmer):
        """Opfer abdunkeln und die Spitzenwert-Bremse des Pools (8 s) abwarten."""
        self._push(_payload(opfer, gobo_wheel=_RING, intensity=dimmer))
        self._bild_um(t + 20)
        return t + 60000.0

    def test_wechsel_blendet_ueber_statt_zu_springen(self):
        t, opfer, neu, slot = self._start()
        programm = self._json(_PROGRAMM_JS % opfer)
        t = self._wechsel_ausloesen(t, opfer, 120)
        z = self._bild_um(t)
        # Die VERGABE wechselt sofort, das LICHT bleibt noch beim alten Halter.
        self.assertEqual(z["halter"][slot], neu)
        self.assertEqual(z["traeger"][slot], opfer,
                         "der alte Halter behaelt das Licht, bis er ausgeblendet ist")
        o, n = z["geraete"][str(opfer)], z["geraete"][str(neu)]
        self.assertGreater(z["anteil"][slot], 0.85, "erstes Bild der Blende: kleiner Schritt")
        self.assertLess(z["anteil"][slot], 1.0)
        self.assertEqual(o["ebene"], 1, "flaches Muster des alten Halters blendet schon ein")
        self.assertEqual(n["ebene"], 1)
        self.assertEqual(z["blenden"], 1)
        self.assertTrue(z["dirty"], "eine laufende Blende fordert das naechste Bild an")

        # Bild fuer Bild (20 ms) bis zum Ende.
        aus, ein = [z["anteil"][slot]], []
        for k in range(1, 80):
            z = self._bild_um(t + 20 * k)
            o, n = z["geraete"][str(opfer)], z["geraete"][str(neu)]
            if z["traeger"][slot] == opfer:
                a = z["anteil"][slot]
                aus.append(a)
                # Licht und Scheibe teilen sich das Bild des alten Halters.
                self.assertAlmostEqual(z["licht"][slot], o["spot"] * a, places=9)
                self.assertAlmostEqual(o["flach"], 1 - a, places=9)
                self.assertAlmostEqual(o["deck"], o["basis"] * 0.8 * (1 - a), places=9)
                self.assertEqual(z["maske"][slot], 1, "das Licht bleibt voll maskiert")
            else:
                self.assertEqual(z["traeger"][slot], neu)
                a = z["anteil"][slot]
                ein.append(a)
                self.assertAlmostEqual(z["licht"][slot], n["spot"] * a, places=9)
                self.assertEqual(o["ebene"], 1)
                self.assertAlmostEqual(o["deck"], o["basis"] * 0.8, places=9)
                if a < 1:
                    self.assertEqual(n["ebene"], 1)
                    self.assertAlmostEqual(n["deck"], n["basis"] * 0.8 * (1 - a), places=9)
                if a >= 1:
                    break
        self.assertGreater(len(ein), 0, f"Licht nie umgezogen: {aus}")
        self.assertEqual(ein[-1], 1)
        for reihe, richtung in ((aus, -1), (ein, 1)):
            schritte = [b - a for a, b in zip(reihe, reihe[1:])]
            self.assertTrue(all(s * richtung > 0 for s in schritte), reihe)
            self.assertLess(max(abs(s) for s in schritte), 0.2, f"Sprung in der Blende: {reihe}")
            self.assertGreaterEqual(len(reihe) * 20, 150, reihe)
            self.assertLessEqual(len(reihe) * 20, 250, reihe)
        self.assertLess(ein[0], 0.15, "der neue Halter beginnt dunkel")
        # Ende: neuer Halter projiziert allein, Blende vorbei, kein Dauer-Rendern.
        z = self._bild_um(t + 20 * 90)
        self.assertEqual(z["geraete"][str(neu)]["ebene"], 0)
        self.assertEqual(z["blenden"], 0)
        z = self._z()
        self.assertFalse(z["dirty"], "nach der Blende wird kein weiteres Bild angefordert")
        self.assertIn(neu, z["projiziert"])
        self.assertNotIn(opfer, z["projiziert"])
        # Nur Uniform-Werte: Programmschluessel, Material-Versionen, Lichtzahl gleich.
        self.assertEqual(self._json(_PROGRAMM_JS % opfer), programm)

    def test_blackout_des_alten_halters_bricht_die_blende_ab(self):
        t, opfer, neu, slot = self._start()
        t = self._wechsel_ausloesen(t, opfer, 120)
        z = self._bild_um(t)
        self.assertEqual(z["traeger"][slot], opfer)
        self._push(_payload(opfer, gobo_wheel=_RING, intensity=0))
        z = self._bild_um(t + 20)
        self.assertEqual(z["traeger"][slot], neu, "ein dunkler Halter gibt das Licht sofort ab")
        self.assertNotIn(opfer, z["projiziert"])
        self.assertEqual(z["geraete"][str(opfer)]["flach"], 1)

    def test_wird_der_alte_halter_wieder_hell_blendet_er_zurueck(self):
        t, opfer, neu, slot = self._start()
        t = self._wechsel_ausloesen(t, opfer, 120)
        self._bild_um(t)
        z = self._bild_um(t + 40)
        tief = z["anteil"][slot]
        self.assertLess(tief, 0.9)
        self.assertEqual(z["traeger"][slot], opfer)
        # Der neue Halter geht aus: die Vergabe faellt an das Opfer zurueck.
        self._push(_payload(neu, gobo_wheel=_RING, intensity=0),
                   *[_payload(fid, gobo_wheel=_RING, intensity=0)
                     for fid in _VIELE if fid not in z["halter"] and fid != opfer])
        # (erst nach dem Wechselabstand des Pools, 200 ms)
        z = self._bild_um(t + 300)
        self.assertEqual(z["halter"][slot], opfer, z["halter"])
        self.assertEqual(z["traeger"][slot], opfer)
        self.assertGreater(z["anteil"][slot], tief, "Blende kehrt um statt weiter auszublenden")

    def test_projizierender_halter_haelt_sein_licht_zaeher(self):
        t, opfer, neu, slot = self._start()
        # 255 gegen 185: Faktor 1,38 — ueber der Pool-Hysterese (1,25), unter
        # Hysterese x Haltebonus (1,5). Ohne Bonus wechselte das Licht.
        t = self._wechsel_ausloesen(t, opfer, 185)
        z = self._bild_um(t)
        z = self._bild_um(t + 500)
        self.assertEqual(z["halter"][slot], opfer, "knapper Helligkeits-Vorsprung: kein Wechsel")
        self.assertEqual(z["traeger"][slot], opfer)
        self.assertEqual(z["anteil"][slot], 1)
        self.assertEqual(z["blenden"], 0)
        # Deutlicher Vorsprung (255 gegen 120 = 2,1): Wechsel.
        t = self._wechsel_ausloesen(t + 500, opfer, 120)
        z = self._bild_um(t)
        self.assertEqual(z["halter"][slot], neu)

    def test_vergabe_bonus_gilt_nur_dem_halter(self):
        self._load_and_wait()
        r = self._json("""
(function(){
  const V = window.__lightos.__spotPoolVergeben;
  const hell = () => new Map([[1, 150], [2, 255], [3, 200]]);
  const info = { ausstehend: false };
  return JSON.stringify({
    ohne: V([1, 2], hell(), 1.25),
    mit: V([1, 2], hell(), 1.25, { halteBonus: new Map([[1, 1.2]]) }),
    falscher: V([1, 2], hell(), 1.25, { halteBonus: new Map([[2, 1.2], [3, 5]]) }),
    deutlich: V([1, 2], new Map([[1, 150], [2, 255], [3, 230]]), 1.25,
                { halteBonus: new Map([[1, 1.2]]) }),
    aufgeschoben: (V([1, 2], hell(), 1.25,
                     { halteBonus: new Map([[1, 1.2]]), spitze: new Map([[1, 150]]), info }),
                   info.ausstehend),
  });
})()""")
        self.assertEqual(r["ohne"], [3, 2], "200 > 150 x 1,25: ohne Bonus verdraengt")
        self.assertEqual(r["mit"], [1, 2], "200 < 150 x 1,25 x 1,2: der Projizierende bleibt")
        self.assertEqual(r["falscher"], [3, 2], "Bonus eines anderen/Herausforderers zaehlt nicht")
        self.assertEqual(r["deutlich"], [3, 2], "230 > 225: deutlich heller gewinnt weiter")
        self.assertFalse(r["aufgeschoben"], "kein endloses Nachfordern von Bildern")


# ── Punkt 2: Helligkeit ──────────────────────────────────────────────────────

class Viz96B3HelligkeitTest(_B3Basis):
    GERAETE = Viz96B3BlendeTest.GERAETE

    def test_flaches_muster_angeglichen_farbe_unberuehrt(self):
        self._load_and_wait()
        self._pooluhr(0)
        self._push(*[_payload(fid, gobo_wheel=_RING, intensity=220, color_g=128, color_b=0)
                     for fid in _VIELE])
        self._bild_um(0)
        z = self._bild_um(20)
        dim = 220 / 255
        for fid in _VIELE:
            g = z["geraete"][str(fid)]
            # Basis wie vor B3 (Dimmer x 0,55 x GOBO_FLECK 1,5), gezeigt x 0,8.
            self.assertAlmostEqual(g["basis"], dim * 0.55 * 1.5, places=6)
            self.assertAlmostEqual(g["deck"], dim * 0.55 * 1.5 * 0.8, places=6)
            self.assertLess(g["deck"], 1.0, "nichts brennt aus")
            # Farbe bleibt Farbe: der Faktor sitzt allein an der Deckkraft.
            self.assertAlmostEqual(g["farbe"][0], 1.0, places=6)
            self.assertLess(g["farbe"][1], 0.6)
            self.assertAlmostEqual(g["farbe"][2], 0.0, places=6)
            self.assertTrue(g["sichtbar"])
        # Ohne Gobo: der normale Bodenfleck ist nicht betroffen.
        self._push(_payload(_VIELE[0], gobo_wheel=0, intensity=220))
        z = self._bild_um(40)
        g = z["geraete"][str(_VIELE[0])]
        self.assertIsNone(g["basis"])
        self.assertAlmostEqual(g["deck"], dim * 0.55, places=6)


# ── Punkt 3: Traverse, Buehnenplatte ─────────────────────────────────────

_TRAV = ("b3_trav", "truss_h", (0.0, 3.0, -0.125), (2.4, 0.3, 0.3))
_PLATTE = ("b3_platte", "platform", (0.5, 0.5, 0.5), (6.0, 1.0, 4.0))


class Viz96B3FlaechenTest(_B3Basis):
    def _g(self):
        return self._z()["geraete"][str(_FID)]

    def test_flaches_muster_liegt_nicht_auf_der_traverse(self):
        self._load_and_wait()
        self._pooluhr(0)
        self._stage(*_TRAV)
        # Ohne Gobo wie bisher: der Kegel endet an der Traverse.
        self._push(_payload(gobo_wheel=0))
        self._bild_um(0)
        offen = self._g()
        self.assertGreater(offen["fleckY"], 3.0, "Aufbau: der Zentralstrahl trifft die Traverse")
        self.assertGreater(offen["durchmesser"], 0.3)
        # Mit Gobo: durch die Traverse hindurch bis zum Boden.
        self._push(_payload(gobo_wheel=_RING))
        self._bild_um(20)
        gobo = self._g()
        self.assertAlmostEqual(gobo["fleckY"], 0.01, places=6,
                               msg="Muster auf der 0,3 m breiten Traverse statt am Boden")
        self.assertGreater(gobo["laenge"], offen["laenge"] + 1.0, "der Kegel reicht jetzt weiter")
        # Gobo wieder aus: zurueck auf die Traverse (Verhalten ohne Gobo unveraendert).
        self._push(_payload(gobo_wheel=0))
        self._bild_um(40)
        self.assertAlmostEqual(self._g()["fleckY"], offen["fleckY"], places=6)

    def test_buehnenplatte_bleibt_ziel(self):
        self._load_and_wait()
        self._pooluhr(0)
        self._stage(*_PLATTE)
        self._stage(*_TRAV)
        self._push(_payload(gobo_wheel=_RING))
        self._bild_um(0)
        self._bild_um(20)
        # Durch die Traverse hindurch, aber AUF die Platte (Oberkante 1,0 m).
        self.assertAlmostEqual(self._g()["fleckY"], 1.01, places=6)


# ── Stufe Niedrig: alles wie vor B3 ──────────────────────────────────────────

class Viz96B3NiedrigTest(_B3Basis):
    TIER = "low"

    def test_niedrig_unveraendert(self):
        self._load_and_wait()
        self._pooluhr(0)
        self._stage(*_TRAV)
        self._push(_payload(gobo_wheel=0))
        self._bild_um(0)
        offen = self._z()["geraete"][str(_FID)]
        self._push(_payload(gobo_wheel=_RING, intensity=220))
        self._bild_um(20)
        z = self._bild_um(40)
        g = z["geraete"][str(_FID)]
        # Treffersuche wie bisher: die Strahlmitte trifft die Traverse. (Seit
        # VIZ-102 wird die Scheibe dort beschnitten und der Kegel reicht zur
        # Flaeche dahinter — test_viz102_gobo_hallenboden_scene.py.)
        self.assertAlmostEqual(g["fleckY"], offen["fleckY"], places=6)
        # Deckkraft ohne Angleichung, keine Blenden-Felder am Geraet.
        self.assertAlmostEqual(g["deck"], (220 / 255) * 0.55 * 1.5, places=6)
        self.assertIsNone(g["basis"])
        self.assertIsNone(g["flach"])
        self.assertEqual(g["ebene"], 1)
        self.assertEqual(g["spot"], 0, "GOBO_LICHT = 0 wie seit VIZ-92")
        self.assertEqual(z["projiziert"], [])
        self.assertEqual(z["blenden"], 0)
        self.assertEqual(z["traeger"], z["halter"])
        self.assertFalse(z["dirty"])


if __name__ == "__main__":
    unittest.main()
