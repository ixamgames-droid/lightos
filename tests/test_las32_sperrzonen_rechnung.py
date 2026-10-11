"""LAS-32 (S1): „Kann Laser L die Zone Z erreichen?" — reine Rechnung.

Die Funktion ist die Grundlage einer ANZEIGE, keiner Abschaltung. Geprueft
wird vor allem die sichere Richtung: im Zweifel „erreicht" bzw. „nicht
pruefbar", nie ein falsches „erreicht keine Zone".
"""
import math
import unittest

from src.core.laser import sperrzonen as S
from src.core.laser.sperrzonen import (
    LaserFeld, Sperrzone, SperrzonenDaten, kann_erreichen, pruefe_laser,
)


def _feld(l=10.0, r=10.0, o=10.0, u=10.0, zuschlag=2.0):
    return LaserFeld(links=l, rechts=r, oben=o, unten=u, zuschlag=zuschlag)


def _zone(x=0.0, y=0.0, z=10.0, b=2.0, h=2.0, t=2.0, dreh=0.0, name="Publikum"):
    return Sperrzone(name=name, x=x, y=y, z=z, breite=b, hoehe=h, tiefe=t, dreh_y=dreh)


class ZuschlagTest(unittest.TestCase):
    def test_standard_ist_fuenf_grad(self):
        self.assertEqual(LaserFeld().zuschlag, 5.0)
        self.assertEqual(S.ZUSCHLAG_STANDARD, 5.0)

    def test_nie_unter_zwei_und_nie_null(self):
        for wert in (0, 0.0, -3, 1.99, "0"):
            self.assertEqual(LaserFeld(zuschlag=wert).zuschlag, 2.0, wert)
        self.assertEqual(S.zuschlag_begrenzen(0), 2.0)

    def test_unlesbar_faellt_auf_standard(self):
        for wert in (None, "abc", float("nan"), float("inf")):
            self.assertEqual(S.zuschlag_begrenzen(wert), 5.0, wert)

    def test_ebenen_rechnen_auch_bei_manipuliertem_feld_mit_minimum(self):
        feld = _feld(zuschlag=2.0)
        feld.zuschlag = 0.0     # am Konstruktor vorbei
        # Zonenkante bei x = -2.0 (inkl. Rand 0,1 -> -1,9); bei z = 10 sind
        # 10 Grad 1,76 m, 12 Grad 2,13 m: nur MIT Mindestzuschlag erreicht.
        zone = _zone(x=-3.0, y=-1.0, z=10.0, b=2.0, h=2.0, t=0.2)
        self.assertTrue(kann_erreichen((0, 0, 0), (0, 0, 0), feld, zone))


class GeradeausTest(unittest.TestCase):
    """Laser im Ursprung, ungedreht: strahlt nach +Z."""

    def test_zone_mitten_im_feld(self):
        self.assertTrue(kann_erreichen((0, 0, 0), (0, 0, 0), _feld(), _zone(y=-1.0)))

    def test_zone_weit_daneben(self):
        self.assertFalse(kann_erreichen((0, 0, 0), (0, 0, 0), _feld(),
                                        _zone(x=20.0, y=-1.0)))

    def test_zone_hinter_dem_geraet(self):
        self.assertFalse(kann_erreichen((0, 0, 0), (0, 0, 0), _feld(),
                                        _zone(y=-1.0, z=-10.0)))

    def test_grosse_zone_hinter_dem_geraet_trotz_weitem_feld(self):
        feld = _feld(l=80, r=80, o=80, u=80, zuschlag=5)
        zone = _zone(y=-5.0, z=-6.0, b=40.0, h=10.0, t=10.0)   # endet bei z = -0,9
        self.assertFalse(kann_erreichen((0, 0, 0), (0, 0, 0), feld, zone))

    def test_zone_teils_hinter_dem_geraet_zaehlt_nur_vorn(self):
        # Zone seitlich, reicht von z = -5 bis z = +5. Schmales Feld: der
        # vordere Teil liegt weit ausserhalb -> nicht erreicht (G12: kein
        # Dauer-Alarm, nur weil die Zone am Geraet vorbei nach hinten reicht).
        zone = _zone(x=6.0, y=-1.0, z=0.0, b=2.0, h=2.0, t=10.0)
        self.assertFalse(kann_erreichen((0, 0, 0), (0, 0, 0), _feld(), zone))
        # Weites Feld: der vordere Teil wird getroffen.
        weit = _feld(l=5, r=5, o=5, u=5, zuschlag=2)
        self.assertTrue(kann_erreichen((0, 0, 0), (0, 0, 0),
                                       _feld(l=60, r=60), zone))
        self.assertFalse(kann_erreichen((0, 0, 0), (0, 0, 0), weit, zone))

    def test_geraet_sitzt_in_der_zone(self):
        zone = _zone(x=0.0, y=-1.0, z=0.0, b=2.0, h=2.0, t=2.0)
        self.assertTrue(kann_erreichen((0, 0, 0), (0, 0, 0), _feld(), zone))

    def test_reichweite_ist_unbegrenzt(self):
        self.assertTrue(kann_erreichen((0, 0, 0), (0, 0, 0), _feld(),
                                       _zone(y=-1.0, z=500.0)))

    def test_riesige_zone_umschliesst_das_feld(self):
        # Keine Zonenkante liegt im Feld — die Flaeche schon.
        zone = _zone(y=-50.0, z=20.0, b=100.0, h=100.0, t=2.0)
        self.assertTrue(kann_erreichen((0, 0, 0), (0, 0, 0), _feld(), zone))


class RandUndZuschlagTest(unittest.TestCase):
    """Zone links neben dem Feld (Welt +X ist links aus Sicht des Geraets)."""

    def _zone_bei(self, kante_x):
        # duenne Wand bei z = 10, naechste Kante (inkl. Rand) bei kante_x
        return _zone(x=kante_x + S.ZONEN_RAND_M + 1.0, y=-1.0, z=10.0,
                     b=2.0, h=2.0, t=0.2)

    def test_zuschlag_entscheidet(self):
        # 10 Grad Rand: bei z ~ 10 m sind 12 Grad = 2,13 m, 15 Grad = 2,68 m.
        zone = self._zone_bei(2.4)
        self.assertFalse(kann_erreichen((0, 0, 0), (0, 0, 0), _feld(zuschlag=2), zone))
        self.assertTrue(kann_erreichen((0, 0, 0), (0, 0, 0), _feld(zuschlag=5), zone))

    def test_knapp_drin_knapp_draussen(self):
        grenze = (10.0 + 0.1 + S.ZONEN_RAND_M) * math.tan(math.radians(12.0))
        self.assertTrue(kann_erreichen((0, 0, 0), (0, 0, 0), _feld(),
                                       self._zone_bei(grenze - 0.05)))
        self.assertFalse(kann_erreichen((0, 0, 0), (0, 0, 0), _feld(),
                                        self._zone_bei(grenze + 0.05)))

    def test_rand_der_zone_zaehlt_mit(self):
        grenze = (10.0 + 0.1 + S.ZONEN_RAND_M) * math.tan(math.radians(12.0))
        zone = _zone(x=grenze + 0.05 + 1.0, y=-1.0, z=10.0, b=2.0, h=2.0, t=0.2)
        # Ohne Rand laege die Kante 5 cm ausserhalb, mit 10 cm Rand 5 cm drin.
        self.assertFalse(kann_erreichen((0, 0, 0), (0, 0, 0), _feld(), zone, rand=0.0))
        self.assertTrue(kann_erreichen((0, 0, 0), (0, 0, 0), _feld(), zone))

    def test_ungleiche_raender_links_rechts(self):
        # Welt +X = links, Welt -X = rechts (Blick in Strahlrichtung +Z).
        links_zone = _zone(x=5.0, y=-1.0, z=10.0)      # ~26,6 Grad links
        rechts_zone = _zone(x=-5.0, y=-1.0, z=10.0)
        nur_links = _feld(l=30, r=5)
        self.assertTrue(kann_erreichen((0, 0, 0), (0, 0, 0), nur_links, links_zone))
        self.assertFalse(kann_erreichen((0, 0, 0), (0, 0, 0), nur_links, rechts_zone))
        nur_rechts = _feld(l=5, r=30)
        self.assertFalse(kann_erreichen((0, 0, 0), (0, 0, 0), nur_rechts, links_zone))
        self.assertTrue(kann_erreichen((0, 0, 0), (0, 0, 0), nur_rechts, rechts_zone))

    def test_ungleiche_raender_oben_unten(self):
        oben_zone = _zone(y=4.0, z=10.0)       # 4..6 m ueber der Achse
        unten_zone = _zone(y=-6.0, z=10.0)
        nur_unten = _feld(o=5, u=30)
        self.assertFalse(kann_erreichen((0, 0, 0), (0, 0, 0), nur_unten, oben_zone))
        self.assertTrue(kann_erreichen((0, 0, 0), (0, 0, 0), nur_unten, unten_zone))
        nur_oben = _feld(o=30, u=5)
        self.assertTrue(kann_erreichen((0, 0, 0), (0, 0, 0), nur_oben, oben_zone))
        self.assertFalse(kann_erreichen((0, 0, 0), (0, 0, 0), nur_oben, unten_zone))

    def test_gedrehte_zone(self):
        # Langer, schmaler Quader: laengs zur Strahlrichtung ausserhalb, um
        # 90 Grad gedreht ragt er ins Feld.
        feld = _feld()
        laengs = _zone(x=4.0, y=-1.0, z=10.0, b=0.5, h=2.0, t=8.0)
        quer = _zone(x=4.0, y=-1.0, z=10.0, b=0.5, h=2.0, t=8.0, dreh=90.0)
        self.assertFalse(kann_erreichen((0, 0, 0), (0, 0, 0), feld, laengs))
        self.assertTrue(kann_erreichen((0, 0, 0), (0, 0, 0), feld, quer))

    def test_drehrichtung_der_zone_wie_im_3d(self):
        # three.js rotation.y = +45 Grad dreht die lokale +Z-Kante nach +X.
        zone = _zone(x=0.0, y=0.0, z=0.0, b=0.2, h=1.0, t=10.0, dreh=45.0)
        ecken = S.zonen_ecken(zone, rand=0.0)
        vorn = [e for e in ecken if e[0] > 0 and e[2] > 0]
        self.assertEqual(len(vorn), 4, ecken)


class MontageTest(unittest.TestCase):
    def test_achsen_ungedreht(self):
        vorn, rechts, oben = S.geraete_achsen((0, 0, 0))
        self.assertEqual([round(v, 6) for v in vorn], [0, 0, 1])
        self.assertEqual([round(v, 6) for v in rechts], [-1, 0, 0])
        self.assertEqual([round(v, 6) for v in oben], [0, 1, 0])

    def test_um_hochachse_gedreht(self):
        zone_x = _zone(x=10.0, y=-1.0, z=0.0)
        self.assertFalse(kann_erreichen((0, 0, 0), (0, 0, 0), _feld(), zone_x))
        self.assertTrue(kann_erreichen((0, 0, 0), (0, 90, 0), _feld(), zone_x))
        self.assertFalse(kann_erreichen((0, 0, 0), (0, -90, 0), _feld(), zone_x))
        # Alt-Format: einzelner Y-Wert
        self.assertTrue(kann_erreichen((0, 0, 0), 90.0, _feld(), zone_x))

    def test_nach_unten_gekippt_von_der_traverse(self):
        # Laser auf 6 m, Zone am Boden (0..2 m) bei z = 6..10.
        boden = _zone(y=0.0, z=8.0, b=4.0, h=2.0, t=4.0)
        self.assertFalse(kann_erreichen((0, 6, 0), (0, 0, 0), _feld(), boden))
        # rx = +30 Grad kippt +Z nach unten (three.js Euler XYZ).
        self.assertTrue(kann_erreichen((0, 6, 0), (30, 0, 0), _feld(), boden))
        self.assertFalse(kann_erreichen((0, 6, 0), (-30, 0, 0), _feld(), boden))

    def test_haengend_vertauscht_oben_und_unten(self):
        # Feld nur nach „unten" offen. Aufrecht trifft es die Zone unter der
        # Achse; kopfueber (rz = 180) zeigt „unten" nach oben.
        nur_unten = _feld(o=2, u=40)
        unten_zone = _zone(y=-6.0, z=10.0)
        oben_zone = _zone(y=4.0, z=10.0)
        self.assertTrue(kann_erreichen((0, 0, 0), (0, 0, 0), nur_unten, unten_zone))
        self.assertFalse(kann_erreichen((0, 0, 0), (0, 0, 0), nur_unten, oben_zone))
        self.assertFalse(kann_erreichen((0, 0, 0), (0, 0, 180), nur_unten, unten_zone))
        self.assertTrue(kann_erreichen((0, 0, 0), (0, 0, 180), nur_unten, oben_zone))

    def test_haengend_vertauscht_links_und_rechts(self):
        nur_links = _feld(l=30, r=2)
        zone_plus_x = _zone(x=5.0, y=-1.0, z=10.0)
        self.assertTrue(kann_erreichen((0, 0, 0), (0, 0, 0), nur_links, zone_plus_x))
        self.assertFalse(kann_erreichen((0, 0, 0), (0, 0, 180), nur_links, zone_plus_x))

    def test_kopfueber_per_rx_180_strahlt_nach_hinten(self):
        zone_vorn = _zone(y=-1.0, z=10.0)
        zone_hinten = _zone(y=-1.0, z=-10.0)
        self.assertFalse(kann_erreichen((0, 0, 0), (180, 0, 0), _feld(), zone_vorn))
        self.assertTrue(kann_erreichen((0, 0, 0), (180, 0, 0), _feld(), zone_hinten))

    def test_position_verschiebt_das_feld(self):
        zone = _zone(x=30.0, y=-1.0, z=10.0)
        self.assertFalse(kann_erreichen((0, 0, 0), (0, 0, 0), _feld(), zone))
        self.assertTrue(kann_erreichen((30, 0, 0), (0, 0, 0), _feld(), zone))

    def test_gegen_strahlen_stichprobe(self):
        """Gegenrechnung auf anderem Weg: Strahlen durch das Feld werfen.

        Trifft ein Strahl innerhalb des Feldes den Quader, MUSS die Funktion
        „erreicht" sagen (nie ein falsches „frei")."""
        import random
        rnd = random.Random(32)
        falsch_frei = 0
        beide = [0, 0]
        for _ in range(300):
            pos = (rnd.uniform(-5, 5), rnd.uniform(0, 6), rnd.uniform(-5, 5))
            rot = (rnd.uniform(-180, 180), rnd.uniform(-180, 180), rnd.uniform(-180, 180))
            feld = LaserFeld(links=rnd.uniform(0, 40), rechts=rnd.uniform(0, 40),
                             oben=rnd.uniform(0, 40), unten=rnd.uniform(0, 40),
                             zuschlag=rnd.uniform(2, 8))
            zone = _zone(x=rnd.uniform(-8, 8), y=rnd.uniform(0, 3), z=rnd.uniform(-8, 8),
                         b=rnd.uniform(0.5, 6), h=rnd.uniform(0.5, 3),
                         t=rnd.uniform(0.5, 6), dreh=rnd.uniform(0, 180))
            ergebnis = kann_erreichen(pos, rot, feld, zone)
            beide[int(ergebnis)] += 1
            if ergebnis:
                continue
            vorn, rechts, oben = S.geraete_achsen(rot)
            z = feld.zuschlag
            for _s in range(60):
                a = math.radians(rnd.uniform(-(feld.links + z), feld.rechts + z))
                b = math.radians(rnd.uniform(-(feld.unten + z), feld.oben + z))
                d = tuple(vorn[i] + math.tan(a) * rechts[i] + math.tan(b) * oben[i]
                          for i in range(3))
                for schritt in range(1, 80):
                    p = tuple(pos[i] + d[i] * schritt * 0.25 for i in range(3))
                    if S.punkt_in_zone(p, zone):
                        falsch_frei += 1
                        break
        self.assertEqual(falsch_frei, 0)
        self.assertGreater(beide[0], 20, beide)    # beide Ergebnisse kommen vor
        self.assertGreater(beide[1], 20, beide)


class BefundTest(unittest.TestCase):
    def test_randwinkel_fehlen_ist_nicht_pruefbar(self):
        b = pruefe_laser(2, "EL-400", (0, 0, 0), (0, 0, 0), LaserFeld(), [_zone()])
        self.assertEqual(b.status, S.STATUS_NICHT_PRUEFBAR)
        self.assertIn("Randwinkel fehlen — nicht prüfbar", b.text)
        self.assertNotIn("erreicht keine Zone", b.text)

    def test_ein_fehlender_rand_reicht(self):
        feld = LaserFeld(links=10, rechts=10, oben=10, unten=None)
        self.assertFalse(feld.vollstaendig)
        b = pruefe_laser(2, "", (0, 0, 0), (0, 0, 0), feld, [_zone()])
        self.assertEqual(b.status, S.STATUS_NICHT_PRUEFBAR)
        with self.assertRaises(ValueError):
            kann_erreichen((0, 0, 0), (0, 0, 0), feld, _zone())

    def test_nicht_platziert_ist_nicht_pruefbar(self):
        b = pruefe_laser(2, "", None, None, _feld(), [_zone()])
        self.assertEqual(b.status, S.STATUS_NICHT_PRUEFBAR)
        self.assertIn("nicht platziert", b.text)

    def test_rechenfehler_ist_nicht_pruefbar(self):
        b = pruefe_laser(2, "", ("x", 0, 0), (0, 0, 0), _feld(), [_zone()])
        self.assertEqual(b.status, S.STATUS_NICHT_PRUEFBAR)
        b = pruefe_laser(2, "", (float("nan"), 0, 0), (0, 0, 0), _feld(), [_zone()])
        self.assertEqual(b.status, S.STATUS_NICHT_PRUEFBAR)

    def test_texte(self):
        zonen = [_zone(y=-1.0, name="Publikum"), _zone(x=50.0, name="Bar")]
        b = pruefe_laser(2, "EL-400", (0, 0, 0), (0, 0, 0), _feld(), zonen)
        self.assertEqual(b.status, S.STATUS_ERREICHT)
        self.assertEqual(b.zonen, ["Publikum"])
        self.assertEqual(b.text, "Laser 2 „EL-400“: kann Zone „Publikum“ erreichen")
        b = pruefe_laser(2, "EL-400", (0, 0, 0), (0, 180, 0), _feld(), zonen)
        self.assertEqual(b.text, "Laser 2 „EL-400“: erreicht keine Zone")

    def test_kopfzeile(self):
        leer = SperrzonenDaten()
        self.assertEqual(S.kopfzeile(0, leer), "")
        self.assertEqual(S.kopfzeile(1, leer),
                         "Laser gepatcht, keine Sperrzonen angelegt")
        mit = SperrzonenDaten(zonen=[_zone()])
        self.assertIn("schaltet den Laser NICHT ab", S.kopfzeile(1, mit))
        self.assertIn("noch nicht abgenommen", S.kopfzeile(1, mit))

    def test_kein_text_verspricht_schutz(self):
        texte = [S.HINWEIS_NUR_ANZEIGE, S.kopfzeile(1, SperrzonenDaten()),
                 S.kopfzeile(1, SperrzonenDaten(zonen=[_zone()])),
                 S.kopfzeile(1, SperrzonenDaten(fremd={"version": 9}))]
        for t in texte:
            for wort in ("geschützt", "gesichert", "sicher", "überwacht", "gesperrt"):
                self.assertNotIn(wort, t.lower(), t)


class ProfilVorgabeTest(unittest.TestCase):
    def test_nichts_im_profil(self):
        self.assertIsNone(S.feld_aus_profil(None))
        self.assertIsNone(S.feld_aus_profil({}))
        self.assertIsNone(S.feld_aus_profil(object()))
        self.assertIsNone(S.feld_aus_profil({"laser_abstrahlwinkel": 0}))
        self.assertIsNone(S.feld_aus_profil({"laser_abstrahlwinkel": "viel"}))

    def test_voller_winkel_fuellt_beide_raender_halb(self):
        f = S.feld_aus_profil({"laser_abstrahlwinkel": 40})
        self.assertEqual((f.links, f.rechts, f.oben, f.unten), (20, 20, 20, 20))
        f = S.feld_aus_profil({"laser_abstrahlwinkel": [60, 30]})
        self.assertEqual((f.links, f.rechts, f.oben, f.unten), (30, 30, 15, 15))

    def test_vier_raender(self):
        class P:
            laser_randwinkel = {"links": 5, "rechts": 25, "oben": 3, "unten": 30}
        f = S.feld_aus_profil(P())
        self.assertEqual((f.links, f.rechts, f.oben, f.unten), (5, 25, 3, 30))


if __name__ == "__main__":
    unittest.main()
