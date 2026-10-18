"""LAS-35: Sperrzonen-Planer — Ziehen, Schraffur, Vorlagen, Rueckgaengig, Show.

Die Zeichenflaechen werden offscreen mit echten Maus-Ereignissen bedient
(``QMouseEvent`` an die Flaeche). Die Schraffur „vom Laser erreichbar" muss in
jeder Lage dasselbe sagen wie ``pruefe_laser`` — die Zeichnung darf nie „frei"
zeigen, wenn die Rechnung „erreicht" sagt.
"""
import json
import math
import os
import pathlib
import random
import shutil
import tempfile
import unittest
import zipfile
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel

from src.core.laser import feld_einmessen as E
from src.core.laser import sperrzonen as S
from src.core.laser import sperrzonen_merker as M
from src.core.laser.sperrzonen import LaserFeld, Sperrzone, SperrzonenDaten
from src.ui.visualizer import sperrzonen_planer as P
from src.ui.visualizer import sperrzonen_ui as UI

_app = QApplication.instance() or QApplication([])
_REPO = pathlib.Path(__file__).resolve().parent.parent


class _Fx:
    protocol = ""
    fixture_type = "laser"
    manufacturer_name = "Laserworld"
    fixture_name = "EL-400RGB MK2"
    mode_name = "9ch"

    def __init__(self, fid, label="EL-400"):
        self.fid, self.label = fid, label


class _State:
    def __init__(self, laser=(2,)):
        self.sperrzonen = SperrzonenDaten()
        self._patch = [_Fx(f) for f in laser]
        self.visualizer_positions = {f: (0.0, 1.5, 0.0) for f in laser}
        self.visualizer_rotations = {f: (0.0, 0.0, 0.0) for f in laser}
        self.ereignisse = []
        self.laser_estop_active = False
        self.programmer = {}

    def get_patched_fixtures(self):
        return list(self._patch)

    def _emit(self, event, data=None):
        self.ereignisse.append(event)

    def get_programmer_value(self, fid, attribut, head=None):
        return self.programmer.get((fid, attribut))

    def set_programmer_value(self, fid, attribut, wert, head=None):
        self.programmer[(fid, attribut)] = int(wert)

    def clear_programmer_value(self, fid, attribut):
        self.programmer.pop((fid, attribut), None)


def _feld(**kw):
    werte = dict(links=20, rechts=20, oben=15, unten=15)
    werte.update(kw)
    return LaserFeld(**werte)


def _maus(w, typ, pos, gedrueckt=True):
    pos = QPointF(pos)
    knopf = Qt.MouseButton.LeftButton
    if typ == QEvent.Type.MouseMove:
        ev = QMouseEvent(typ, pos, w.mapToGlobal(pos), Qt.MouseButton.NoButton,
                         knopf, Qt.KeyboardModifier.NoModifier)
    else:
        ev = QMouseEvent(typ, pos, w.mapToGlobal(pos), knopf,
                         knopf if typ == QEvent.Type.MouseButtonPress
                         else Qt.MouseButton.NoButton,
                         Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w, ev)


def _ziehe(w, von, nach, schritte=4):
    """Druecken bei ``von``, in Schritten nach ``nach``, loslassen (Pixel)."""
    von, nach = QPointF(von), QPointF(nach)
    _maus(w, QEvent.Type.MouseButtonPress, von)
    for i in range(1, schritte + 1):
        t = i / schritte
        _maus(w, QEvent.Type.MouseMove,
              QPointF(von.x() + (nach.x() - von.x()) * t,
                      von.y() + (nach.y() - von.y()) * t))
    _maus(w, QEvent.Type.MouseButtonRelease, nach)


class _PlanerFall(unittest.TestCase):
    LASER = (2,)

    def setUp(self):
        M._vergiss_sitzung()
        patch = mock.patch.object(M, "merke_benutzt")
        patch.start()
        self.addCleanup(patch.stop)
        self.st = _State(self.LASER)
        self.zone = Sperrzone(id="z1", name="Publikum", x=0.0, y=0.0, z=6.0,
                              breite=4.0, hoehe=3.0, tiefe=2.0)
        self.st.sperrzonen.zonen.append(self.zone)
        self.dlg = P.SperrzonenPlaner(self.st)
        self.dlg.resize(1500, 850)
        self.dlg.show()
        _app.processEvents()
        self.drauf, self.seite = self.dlg._drauf, self.dlg._seite
        self.st.ereignisse.clear()

    def tearDown(self):
        self.dlg.close()
        self.dlg.deleteLater()
        _app.processEvents()


# ── Geometrie ueber Maus-Ereignisse ─────────────────────────────────────────

class ZiehenTest(_PlanerFall):
    def test_griffe_sind_fingertauglich(self):
        self.assertGreaterEqual(P.GRIFF_PX, 36)
        griffe = self.drauf.griffe()
        self.assertEqual(set(griffe), {"nw", "n", "no", "w", "o", "sw", "s", "so",
                                       "mitte", "dreh"})
        # 17 Pixel neben der Griffmitte wird noch gegriffen
        m = griffe["so"]
        self.assertEqual(self.drauf._griff_bei(QPointF(m.x() + 12, m.y() + 12)), "so")
        self.assertEqual(set(self.seite.griffe()), {"oben", "unten"})
        for knopf in (self.dlg._btn_neu, self.dlg._btn_loeschen, self.dlg._btn_fertig,
                      *self.dlg._btn_vorlagen.values()):
            self.assertGreaterEqual(knopf.height(), 34, knopf.text())
        for sp in self.dlg._zspins.values():
            self.assertGreaterEqual(sp.height(), 34)

    def test_verschieben_am_mittelgriff_rastet_auf_viertelmeter(self):
        self.assertTrue(self.dlg.einrasten())
        _ziehe(self.drauf, self.drauf.griffe()["mitte"], self.drauf.zu_px(1.1, 6.6))
        self.assertEqual((self.zone.x, self.zone.z), (1.0, 6.5))
        self.assertEqual((self.zone.breite, self.zone.tiefe, self.zone.hoehe),
                         (4.0, 2.0, 3.0))
        self.assertGreaterEqual(self.st.ereignisse.count("sperrzonen_changed"), 4,
                                "das 3D zeichnet waehrend des Zugs mit")
        self.assertEqual(self.dlg._zspins["x"].value(), 1.0, "Massleiste folgt")

    def test_verschieben_durch_ziehen_an_der_flaeche(self):
        start = self.drauf.zu_px(1.0, 6.4)             # in der Zone, kein Griff
        self.assertIsNone(self.drauf._griff_bei(start))
        _ziehe(self.drauf, start, self.drauf.zu_px(3.0, 8.4))
        self.assertEqual((self.zone.x, self.zone.z), (2.0, 8.0))

    def test_einrasten_abschaltbar(self):
        self.dlg._chk_einrasten.setChecked(False)
        _ziehe(self.drauf, self.drauf.griffe()["mitte"], self.drauf.zu_px(1.1, 6.6))
        self.assertAlmostEqual(self.zone.x, 1.1, places=6)
        self.assertAlmostEqual(self.zone.z, 6.6, places=6)

    def test_ecke_aufziehen_gegenecke_bleibt(self):
        _ziehe(self.drauf, self.drauf.griffe()["so"], self.drauf.zu_px(3.1, 8.2))
        z = self.zone
        self.assertEqual((z.breite, z.tiefe), (5.0, 3.25))
        self.assertEqual((z.x, z.z), (0.5, 6.625))
        self.assertEqual((z.x - z.breite / 2, z.z - z.tiefe / 2), (-2.0, 5.0))

    def test_kante_ziehen_aendert_nur_eine_richtung(self):
        _ziehe(self.drauf, self.drauf.griffe()["w"], self.drauf.zu_px(-3.05, 9.0))
        z = self.zone
        self.assertEqual((z.breite, z.x), (5.0, -0.5))
        self.assertEqual((z.tiefe, z.z), (2.0, 6.0))

    def test_kleiner_als_das_raster_geht_nicht(self):
        _ziehe(self.drauf, self.drauf.griffe()["so"], self.drauf.zu_px(-9.0, -9.0))
        self.assertEqual((self.zone.breite, self.zone.tiefe), (0.25, 0.25))
        self.dlg._chk_einrasten.setChecked(False)
        _ziehe(self.drauf, self.drauf.griffe()["so"], self.drauf.zu_px(-9.0, -9.0))
        self.assertGreaterEqual(self.zone.breite, S.ZONE_MIN_M)

    def test_drehen_am_drehgriff(self):
        r = 3.0
        ziel = math.radians(45.0)
        _ziehe(self.drauf, self.drauf.griffe()["dreh"],
               self.drauf.zu_px(-r * math.sin(ziel), 6.0 - r * math.cos(ziel)))
        self.assertEqual(self.zone.dreh_y, 45.0)
        self.assertEqual((self.zone.x, self.zone.z, self.zone.breite), (0.0, 6.0, 4.0))
        # der Griff sitzt jetzt dort, wohin gedreht wurde (gleiche Drehrichtung
        # wie die Rechnung): die buehnenseitige Kante liegt bei lokal z = -1
        kante = self.drauf.griffe()["n"]
        ecken = S.zonen_ecken(self.zone, 0.0)
        mitte = ((ecken[0][0] + ecken[1][0]) / 2, (ecken[0][2] + ecken[1][2]) / 2)
        soll = self.drauf.zu_px(*mitte)
        self.assertAlmostEqual(kante.x(), soll.x(), places=6)
        self.assertAlmostEqual(kante.y(), soll.y(), places=6)

    def test_drehen_rastet_auf_fuenf_grad_und_frei_ohne_raster(self):
        ziel = math.radians(32.0)
        punkt = self.drauf.zu_px(-3 * math.sin(ziel), 6.0 - 3 * math.cos(ziel))
        _ziehe(self.drauf, self.drauf.griffe()["dreh"], punkt)
        self.assertEqual(self.zone.dreh_y, 30.0)
        self.dlg._chk_einrasten.setChecked(False)
        _ziehe(self.drauf, self.drauf.griffe()["dreh"], punkt)
        self.assertAlmostEqual(self.zone.dreh_y, 32.0, places=4)

    def test_gedrehte_zone_aufziehen_laesst_die_gegenkante_stehen(self):
        self.zone.dreh_y = 30.0
        self.dlg.neu_laden()

        def _welt(lx, lz):
            w = math.radians(self.zone.dreh_y)
            return (self.zone.x + math.cos(w) * lx + math.sin(w) * lz,
                    self.zone.z - math.sin(w) * lx + math.cos(w) * lz)

        gegen = _welt(-self.zone.breite / 2, 0.0)
        ziel = _welt(self.zone.breite / 2 + 1.1, 0.0)
        _ziehe(self.drauf, self.drauf.griffe()["o"], self.drauf.zu_px(*ziel))
        self.assertEqual(self.zone.breite, 5.0, "Mass rastet (4 + 1,1 -> 5,0)")
        self.assertEqual(self.zone.tiefe, 2.0)
        neu = _welt(-self.zone.breite / 2, 0.0)
        self.assertAlmostEqual(neu[0], gegen[0], places=9)
        self.assertAlmostEqual(neu[1], gegen[1], places=9)

    def test_neue_zone_durch_aufziehen_auf_freier_flaeche(self):
        _ziehe(self.drauf, self.drauf.zu_px(-5.1, 9.9), self.drauf.zu_px(-2.9, 12.1))
        self.assertEqual(len(self.st.sperrzonen.zonen), 2)
        neu = self.st.sperrzonen.zonen[1]
        self.assertEqual((neu.x, neu.z, neu.breite, neu.tiefe), (-4.0, 11.0, 2.0, 2.0))
        self.assertEqual((neu.y, neu.hoehe, neu.dreh_y), (0.0, 3.0, 0.0))
        self.assertEqual(neu.name, "Zone")
        self.assertIs(self.dlg.gewaehlte_zone(), neu)
        self.assertEqual(self.dlg._liste.count(), 2)
        M.merke_benutzt.assert_called()

    def test_ein_tipp_auf_freie_flaeche_legt_nichts_an(self):
        p = self.drauf.zu_px(-5.0, 10.0)
        _ziehe(self.drauf, p, QPointF(p.x() + 3, p.y() + 3))
        self.assertEqual(len(self.st.sperrzonen.zonen), 1)
        self.assertEqual(self.st.ereignisse, [])

    def test_seitenansicht_oberkante_und_unterkante(self):
        _ziehe(self.seite, self.seite.griffe()["oben"], self.seite.zu_px(6.0, 4.1))
        self.assertEqual((self.zone.y, self.zone.hoehe), (0.0, 4.0))
        _ziehe(self.seite, self.seite.griffe()["unten"], self.seite.zu_px(6.0, 1.05))
        self.assertEqual((self.zone.y, self.zone.hoehe), (1.0, 3.0))
        # Unterkante ueber die Oberkante hinaus: es bleibt ein Rasterschritt
        _ziehe(self.seite, self.seite.griffe()["unten"], self.seite.zu_px(6.0, 9.0))
        self.assertEqual((self.zone.y, self.zone.hoehe), (3.75, 0.25))
        self.assertEqual((self.zone.x, self.zone.z, self.zone.breite), (0.0, 6.0, 4.0))

    def test_antippen_waehlt_die_zone(self):
        zweite = Sperrzone(id="z2", name="Technik", x=6.0, z=2.0, breite=2.0, tiefe=2.0)
        self.st.sperrzonen.zonen.append(zweite)
        self.dlg.neu_laden()
        self.assertIs(self.dlg.gewaehlte_zone(), self.zone)
        p = self.drauf.zu_px(6.3, 2.3)
        _maus(self.drauf, QEvent.Type.MouseButtonPress, p)
        _maus(self.drauf, QEvent.Type.MouseButtonRelease, p)
        self.assertIs(self.dlg.gewaehlte_zone(), zweite)
        self.assertEqual(self.dlg._liste.currentRow(), 1)
        self.assertEqual(self.dlg._name.text(), "Technik")
        self.assertEqual((zweite.x, zweite.z), (6.0, 2.0), "Antippen verschiebt nicht")
        q = self.seite.zu_px(6.0, 1.0)                 # Publikum in der Seitenansicht
        _maus(self.seite, QEvent.Type.MouseButtonPress, q)
        _maus(self.seite, QEvent.Type.MouseButtonRelease, q)
        self.assertIs(self.dlg.gewaehlte_zone(), self.zone)

    def test_massleiste_bleibt_feineingabe(self):
        self.dlg._zspins["breite"].setValue(7.37)
        self.dlg._zspins["y"].setValue(0.4)
        self.dlg._dreh.setValue(12.5)
        self.assertEqual((self.zone.breite, self.zone.y, self.zone.dreh_y),
                         (7.37, 0.4, 12.5))
        # ein Feld schreibt nur sich selbst: der feine Wert daneben bleibt
        self.zone.x = 1.23456
        self.dlg._anzeige()
        self.dlg._zspins["tiefe"].setValue(3.0)
        self.assertEqual(self.zone.x, 1.23456)

    def test_abschnitt_aus_neuerem_stand_laesst_sich_nicht_ziehen(self):
        fremd = {"version": 99, "zonen": [{"x": 1}]}
        self.st.sperrzonen = SperrzonenDaten(fremd=fremd)
        self.dlg.patch_oder_show_geaendert()
        self.assertEqual(self.drauf.griffe(), {})
        _ziehe(self.drauf, self.drauf.zu_px(-5.1, 9.9), self.drauf.zu_px(-2.9, 12.1))
        self.dlg.vorlage_anlegen("publikum")
        self.dlg.rueckgaengig()
        self.assertEqual(self.st.sperrzonen.to_dict(), fremd)
        self.assertIn("neueren Programmstand", self.dlg._hinweis.text())


# ── Schraffur = pruefe_laser ────────────────────────────────────────────────

def _lagen(anzahl, saat=35):
    """Zufaellige, aber feste Lagen: Laser, Feld, Zone."""
    rnd = random.Random(saat)
    for _ in range(anzahl):
        pos = (rnd.uniform(-6, 6), rnd.uniform(0.3, 6), rnd.uniform(-3, 3))
        rot = (rnd.choice((0, 0, 10, 25, -20, 60)), rnd.choice((0, 0, 30, 90, 180, -45)),
               rnd.choice((0, 0, 0, 180, 15)))
        feld = LaserFeld(links=rnd.uniform(2, 40), rechts=rnd.uniform(2, 40),
                         oben=rnd.uniform(2, 30), unten=rnd.uniform(2, 30),
                         zuschlag=rnd.choice((2, 5, 8)))
        zone = Sperrzone(id="z", name="Z", x=rnd.uniform(-8, 8), y=rnd.uniform(0, 3),
                         z=rnd.uniform(-4, 14), breite=rnd.uniform(0.5, 10),
                         hoehe=rnd.uniform(0.5, 4), tiefe=rnd.uniform(0.5, 8),
                         dreh_y=rnd.choice((0, 0, 30, 45, -70, 90)))
        yield pos, rot, feld, zone


class SchraffurRechnungTest(unittest.TestCase):
    def test_umriss_genau_dann_wenn_die_rechnung_erreicht_sagt(self):
        erreicht = frei = 0
        for pos, rot, feld, zone in _lagen(600):
            status = S.pruefe_laser(1, "L", pos, rot, feld, [zone]).status
            teil = S.erreichter_teil(pos, rot, feld, zone)
            if status == S.STATUS_ERREICHT:
                erreicht += 1
                self.assertIsNotNone(teil, (pos, rot, zone))
                for ansicht in ("drauf", "seite"):
                    self.assertGreaterEqual(len(teil[ansicht]), 3)
                    self.assertGreater(S.flaeche_2d(teil[ansicht]), 0.0)
            else:
                frei += 1
                self.assertEqual(status, S.STATUS_FREI)
                self.assertIsNone(teil, (pos, rot, zone))
        self.assertGreater(erreicht, 80, "Probe taugt nicht: zu wenig Treffer")
        self.assertGreater(frei, 80, "Probe taugt nicht: zu wenig freie Lagen")

    def test_umriss_liegt_in_der_zone_und_im_feld(self):
        for pos, rot, feld, zone in _lagen(300, saat=7):
            teil = S.erreichter_teil(pos, rot, feld, zone)
            if teil is None:
                continue
            ganz = S.zonen_umriss(zone, S.ZONEN_RAND_M)
            for ansicht in ("drauf", "seite"):
                for i in (0, 1):
                    lo = min(p[i] for p in ganz[ansicht]) - 1e-6
                    hi = max(p[i] for p in ganz[ansicht]) + 1e-6
                    for p in teil[ansicht]:
                        self.assertTrue(lo <= p[i] <= hi, (ansicht, p, lo, hi))
                self.assertLessEqual(S.flaeche_2d(teil[ansicht]),
                                     S.flaeche_2d(ganz[ansicht]) + 1e-6)

    def test_gerade_lage_ergibt_das_erwartete_trapez(self):
        """Laser auf 1,5 m, strahlt waagerecht nach vorn, 20° + 5° je Seite:
        in der Draufsicht reicht der Fleck an der hinteren Zonenkante genau
        (Abstand × tan 25°) nach jeder Seite."""
        pos, rot = (0.0, 1.5, 0.0), (0.0, 0.0, 0.0)
        zone = Sperrzone(id="z", name="P", x=0, y=0, z=7.0, breite=12, hoehe=3, tiefe=6)
        teil = S.erreichter_teil(pos, rot, _feld(), zone)
        hinten = zone.z + zone.tiefe / 2 + S.ZONEN_RAND_M
        vorn = zone.z - zone.tiefe / 2 - S.ZONEN_RAND_M
        t = math.tan(math.radians(25.0))
        self.assertAlmostEqual(max(p[0] for p in teil["drauf"]),
                               (hinten - S.AUSTRITT_VORN_M) * t, places=6)
        self.assertAlmostEqual(min(p[0] for p in teil["drauf"]),
                               -(hinten - S.AUSTRITT_VORN_M) * t, places=6)
        self.assertAlmostEqual(min(p[1] for p in teil["drauf"]), vorn, places=6)
        nah = [p[0] for p in teil["drauf"] if abs(p[1] - vorn) < 1e-6]
        self.assertAlmostEqual(max(nah), (vorn - S.AUSTRITT_VORN_M) * t, places=6)
        # Seitenansicht: an der vorderen Kante reicht das Feld (15° + 5°) von
        # der Laserhoehe aus nach oben und unten
        t_hoch = math.tan(math.radians(20.0))
        vorn_y = [p[1] for p in teil["seite"] if abs(p[0] - vorn) < 1e-6]
        self.assertAlmostEqual(max(vorn_y), 1.5 + (vorn - S.AUSTRITT_VORN_M) * t_hoch,
                               places=6)

    def test_geraet_in_der_zone_ganze_zone(self):
        """Mitte in der Zone, Fenster schaut heraus und zeigt weg: die Rechnung
        sagt „erreicht" — die Zeichnung schraffiert dann die ganze Zone."""
        zone = Sperrzone(id="z", name="Eng", x=0.0, y=3.9, z=-0.11,
                         breite=1.0, hoehe=0.2, tiefe=0.1)
        pos, rot = (0.0, 4.0, 0.0), (0, 0, 0)
        self.assertEqual(S.pruefe_laser(1, "L", pos, rot, _feld(), [zone]).status,
                         S.STATUS_ERREICHT)
        self.assertEqual(S.erreichter_teil(pos, rot, _feld(), zone),
                         S.zonen_umriss(zone, S.ZONEN_RAND_M))

    def test_streifschuss_ohne_flaeche_ganze_zone(self):
        """Das Feld beruehrt nur eine Kante: „erreicht", aber kein zeichenbarer
        Fleck — dann lieber die ganze Zone als nichts."""
        feld = LaserFeld(links=20, rechts=20, oben=20, unten=20, zuschlag=5)
        t = math.tan(math.radians(25.0))
        # Zonenkante (mit Rand) genau auf der Feldgrenze bei z = 10
        kante = (10.0 - S.AUSTRITT_VORN_M) * t
        zone = Sperrzone(id="z", name="R", x=kante + S.ZONEN_RAND_M + 0.5, y=-0.5,
                         z=9.9 - 0.025, breite=1.0, hoehe=1.0, tiefe=0.05)
        pos, rot = (0.0, 0.0, 0.0), (0, 0, 0)
        if S.pruefe_laser(1, "L", pos, rot, feld, [zone]).status == S.STATUS_ERREICHT:
            teil = S.erreichter_teil(pos, rot, feld, zone)
            self.assertGreater(S.flaeche_2d(teil["drauf"]), 0.0)
        else:
            self.assertIsNone(S.erreichter_teil(pos, rot, feld, zone))

    def test_kann_erreichen_und_umriss_teilen_die_rechnung(self):
        import inspect
        self.assertIn("_schnitt_polygone(", inspect.getsource(S.kann_erreichen))
        self.assertIn("_schnitt_polygone(", inspect.getsource(S.erreichter_teil))

    def test_fehlende_winkel_werfen(self):
        with self.assertRaises(ValueError):
            S.erreichter_teil((0, 1, 0), (0, 0, 0), LaserFeld(links=5),
                              Sperrzone(id="z"))


class SchraffurPlanerTest(_PlanerFall):
    def _paare(self):
        return {(e["fid"], e["zid"]) for e in self.dlg.schraffuren()}

    def test_planer_schraffiert_was_die_rechnung_erreicht_nennt(self):
        st = self.st
        st.sperrzonen.zonen.append(Sperrzone(id="z2", name="Technik", x=9.0, z=2.0,
                                             breite=2.0, tiefe=2.0, hoehe=2.5))
        self.dlg.neu_laden()
        self.assertEqual(self._paare(), set(), "ohne Randwinkel keine Schraffur")
        self.assertEqual(self.dlg.ampel_texte(),
                         {"Publikum": "nicht prüfbar (Laser 2)",
                          "Technik": "nicht prüfbar (Laser 2)"})
        st.sperrzonen.setze_feld(2, _feld())
        lagen = [((0.0, 1.5, 0.0), (0, 0, 0)), ((0.0, 1.5, 0.0), (0, 180, 0)),
                 ((0.0, 6.0, 0.0), (0, 0, 0)), ((9.0, 1.0, -3.0), (0, 0, 0)),
                 ((0.0, 4.5, 0.0), (35, 0, 0)), ((-8.0, 1.5, 6.0), (0, 90, 0)),
                 ((8.0, 1.5, 6.0), (0, 90, 0)), ((0.0, 1.5, 6.0), (0, 180, 0)),
                 ((9.0, 1.2, 2.0), (0, 180, 0))]
        gesehen = set()
        for pos, rot in lagen:
            st.visualizer_positions[2], st.visualizer_rotations[2] = pos, rot
            self.dlg._takt()
            soll = {(2, z.id) for z in st.sperrzonen.zonen
                    if S.pruefe_laser(2, "L", pos, rot, st.sperrzonen.feld(2), [z]).status
                    == S.STATUS_ERREICHT}
            self.assertEqual(self._paare(), soll, (pos, rot))
            texte = self.dlg.ampel_texte()
            for z in st.sperrzonen.zonen:
                self.assertEqual(texte[z.name], "erreicht von Laser 2"
                                 if (2, z.id) in soll else "frei", (pos, rot, z.name))
            gesehen.add(frozenset(soll))
        self.assertGreaterEqual(len(gesehen), 3, "Probe deckt zu wenig Faelle ab")

    def test_kaputter_umriss_wird_nie_zu_frei(self):
        """Faellt die Umriss-Rechnung aus, schraffiert der Planer die ganze
        Zone — er verlaesst sich fuer das OB allein auf pruefe_laser."""
        self.st.sperrzonen.setze_feld(2, _feld())
        for kaputt in (mock.Mock(return_value=None),
                       mock.Mock(side_effect=RuntimeError("x"))):
            with mock.patch.object(S, "erreichter_teil", kaputt):
                self.dlg._anzeige()
                eintraege = self.dlg.schraffuren()
            self.assertEqual([(e["fid"], e["zid"]) for e in eintraege], [(2, "z1")])
            self.assertEqual(eintraege[0]["drauf"],
                             S.zonen_umriss(self.zone, S.ZONEN_RAND_M)["drauf"])

    def _orange(self, flaeche):
        bild = flaeche.grab().toImage()
        ecken = [flaeche.zu_px(*p) for p in S.zonen_umriss(self.zone)[flaeche.art]]
        x0, x1 = int(min(p.x() for p in ecken)) + 3, int(max(p.x() for p in ecken)) - 3
        y0, y1 = int(min(p.y() for p in ecken)) + 3, int(max(p.y() for p in ecken)) - 3
        n = 0
        for y in range(y0, y1, 2):
            for x in range(x0, x1, 2):
                c = bild.pixelColor(x, y)
                if c.red() > 200 and 110 < c.green() < 200 and c.blue() < 70:
                    n += 1
        return n

    def test_schraffur_wird_in_beiden_ansichten_gemalt(self):
        self.dlg._gewaehlt = None                      # keine Griffe im Bild
        self.st.sperrzonen.setze_feld(2, _feld())
        self.dlg._anzeige()
        self.assertGreater(self._orange(self.drauf), 40)
        self.assertGreater(self._orange(self.seite), 40)
        self.st.visualizer_rotations[2] = (0.0, 180.0, 0.0)     # Laser weggedreht
        self.dlg._takt()
        self.assertEqual(self.dlg.schraffuren(), [])
        self.assertLess(self._orange(self.drauf), 5)
        self.assertLess(self._orange(self.seite), 5)

    def test_zwei_laser_ampel_nennt_wer_erreicht(self):
        st = _State((1, 3))
        st.sperrzonen.zonen.append(Sperrzone(id="z1", name="Publikum", x=0, y=0, z=6,
                                             breite=4, hoehe=3, tiefe=2))
        st.sperrzonen.setze_feld(1, _feld())
        st.visualizer_rotations[3] = (0.0, 180.0, 0.0)
        dlg = P.SperrzonenPlaner(st)
        self.addCleanup(dlg.deleteLater)
        # Laser 3 ohne Winkel -> erreicht bleibt erreicht
        self.assertEqual(dlg.ampel_texte(), {"Publikum": "erreicht von Laser 1"})
        st.visualizer_rotations[1] = (0.0, 180.0, 0.0)
        dlg._anzeige()
        # jetzt erreicht sie keiner, aber Laser 3 ist nicht pruefbar: nie „frei"
        self.assertEqual(dlg.ampel_texte(), {"Publikum": "nicht prüfbar (Laser 3)"})
        st.sperrzonen.setze_feld(3, _feld())
        dlg._anzeige()
        self.assertEqual(dlg.ampel_texte(), {"Publikum": "frei"})
        st.visualizer_rotations = {1: (0, 0, 0), 3: (0, 0, 0)}
        dlg._anzeige()
        self.assertEqual(dlg.ampel_texte(), {"Publikum": "erreicht von Laser 1, 3"})
        st._patch = []
        dlg.patch_oder_show_geaendert()
        self.assertEqual(dlg.ampel_texte(), {"Publikum": "kein Laser"})

    def test_hinweis_nennt_den_ort(self):
        self.st.sperrzonen.setze_feld(2, _feld())
        self.dlg._anzeige()
        text = self.dlg._hinweis.text()
        self.assertIn("kann Zone „Publikum“ erreichen", text)
        self.assertIn("ab rund 4,9 m", text)           # vordere Kante mit Rand
        self.assertIn("Begrenzt wird am Gerät", text)


# ── Vorlagen ────────────────────────────────────────────────────────────────

class VorlagenTest(_PlanerFall):
    def setUp(self):
        super().setUp()
        self.st.sperrzonen.zonen.clear()
        self.dlg.neu_laden()

    def test_drei_vorlagen_mit_den_namen_aus_dem_entwurf(self):
        self.assertEqual([self.dlg._btn_vorlagen[k].text() for k in
                          ("publikum", "technik", "gang")],
                         ["Publikum bis 3 m Höhe vor der Bühne", "Technik/FOH", "Gang"])

    def test_vorlagen_legen_sinnvoll_platzierte_zonen_an(self):
        with mock.patch.object(P, "buehnen_umrisse", lambda st: [{
                "name": "Bühne", "typ": "platform",
                "drauf": [(-5, -1.5), (5, -1.5), (5, 1.5), (-5, 1.5)],
                "seite": [(-1.5, 0), (1.5, 0), (1.5, 1), (-1.5, 1)]}]):
            self.dlg._anzeige()
            for kennung in ("publikum", "technik", "gang"):
                self.dlg._btn_vorlagen[kennung].click()
        pub, tech, gang = self.st.sperrzonen.zonen
        self.assertEqual([z.name for z in (pub, tech, gang)],
                         ["Publikum", "Technik", "Gang"])
        # Publikum: Boden bis 3 m, mittig, VOR der Buehnenkante (z = 1,5)
        self.assertEqual((pub.x, pub.y, pub.hoehe), (0.0, 0.0, 3.0))
        self.assertEqual(pub.z - pub.tiefe / 2, 2.5)
        # Technik/FOH: mittig hinter dem Publikum, ohne Ueberlappung
        self.assertEqual(tech.x, 0.0)
        self.assertGreaterEqual(tech.z - tech.tiefe / 2, pub.z + pub.tiefe / 2)
        # Gang: neben dem Publikum, gleiche Tiefe
        self.assertEqual(gang.x - gang.breite / 2, pub.x + pub.breite / 2)
        self.assertEqual((gang.z, gang.tiefe), (pub.z, pub.tiefe))
        for z in (pub, tech, gang):
            self.assertEqual((z.y, z.dreh_y), (0.0, 0.0))
            self.assertGreaterEqual(z.hoehe, 2.5)
        self.assertIs(self.dlg.gewaehlte_zone(), gang, "die neue Zone ist gewaehlt")

    def test_ohne_buehne_ein_fester_platz_und_freie_namen(self):
        self.dlg._btn_vorlagen["publikum"].click()
        self.dlg._btn_vorlagen["publikum"].click()
        a, b = self.st.sperrzonen.zonen
        self.assertEqual((a.name, b.name), ("Publikum", "Publikum 2"))
        self.assertEqual(a.z - a.tiefe / 2, 3.0)       # Vorgabe-Kante 2 m + 1 m
        with self.assertRaises(ValueError):
            S.vorlage_zone("gibt-es-nicht", self.st.sperrzonen)

    def test_vorlage_laesst_sich_danach_zurechtziehen(self):
        self.dlg._btn_vorlagen["technik"].click()
        zone = self.st.sperrzonen.zonen[0]
        ziel = self.drauf.zu_px(zone.x + 2.0, zone.z - 1.0)
        _ziehe(self.drauf, self.drauf.griffe()["mitte"], ziel)
        self.assertEqual((zone.x, zone.z), (2.0, 10.0))


# ── Rueckgaengig / Wiederholen ──────────────────────────────────────────────

class UndoTest(_PlanerFall):
    def _stand(self):
        return json.dumps(self.st.sperrzonen.to_dict(), sort_keys=True)

    def test_knoepfe_sind_da_und_anfangs_aus(self):
        self.assertEqual(self.dlg._btn_undo.text(), "Rückgängig")
        self.assertEqual(self.dlg._btn_redo.text(), "Wiederholen")
        self.assertFalse(self.dlg._btn_undo.isEnabled())
        self.assertFalse(self.dlg._btn_redo.isEnabled())

    def test_jede_art_aenderung_ist_ein_schritt(self):
        staende = [self._stand()]
        schritte = [
            lambda: _ziehe(self.drauf, self.drauf.griffe()["mitte"],
                           self.drauf.zu_px(2.0, 8.0)),
            lambda: _ziehe(self.drauf, self.drauf.griffe()["so"],
                           self.drauf.zu_px(6.0, 11.0)),
            lambda: _ziehe(self.drauf, self.drauf.griffe()["dreh"],
                           self.drauf.zu_px(-3.0, 5.0)),
            lambda: _ziehe(self.seite, self.seite.griffe()["oben"],
                           self.seite.zu_px(self.zone.z, 4.5)),
            lambda: self.dlg._btn_vorlagen["gang"].click(),
            lambda: _ziehe(self.drauf, self.drauf.zu_px(-9.0, 12.0),
                           self.drauf.zu_px(-7.0, 14.0)),
            lambda: self.dlg._feld_spins[2]["links"].setValue(17.0),
            lambda: self.dlg._btn_loeschen.click(),
        ]
        for schritt in schritte:
            schritt()
            self.assertNotEqual(self._stand(), staende[-1], "Schritt hat nichts geändert")
            staende.append(self._stand())
            self.dlg._undo_schluessel = None           # naechster Schritt zaehlt eigen
        self.assertEqual(len(self.dlg._undo), len(schritte))
        for i in range(len(schritte) - 1, -1, -1):
            self.dlg._btn_undo.click()
            self.assertEqual(self._stand(), staende[i], f"Rückgängig auf Stand {i}")
        self.assertFalse(self.dlg._btn_undo.isEnabled())
        for i in range(1, len(schritte) + 1):
            self.dlg._btn_redo.click()
            self.assertEqual(self._stand(), staende[i], f"Wiederholen auf Stand {i}")
        self.assertFalse(self.dlg._btn_redo.isEnabled())

    def test_ein_zug_ist_ein_schritt_und_ein_zahlenfeld_buendelt(self):
        _ziehe(self.drauf, self.drauf.griffe()["mitte"], self.drauf.zu_px(3.0, 9.0),
               schritte=12)
        self.assertEqual(len(self.dlg._undo), 1)
        for wert in (5.0, 5.25, 5.5, 5.75):            # Pfeiltaste, viermal
            self.dlg._zspins["breite"].setValue(wert)
        self.assertEqual(len(self.dlg._undo), 2)
        self.dlg._zspins["tiefe"].setValue(4.0)        # anderes Feld: neuer Schritt
        self.assertEqual(len(self.dlg._undo), 3)
        self.dlg.rueckgaengig()
        self.dlg.rueckgaengig()
        self.assertEqual((self.zone_jetzt().breite, self.zone_jetzt().tiefe), (4.0, 2.0))
        self.assertEqual((self.zone_jetzt().x, self.zone_jetzt().z), (3.0, 9.0))

    def zone_jetzt(self):
        return self.st.sperrzonen.zone("z1")

    def test_neue_aenderung_verwirft_wiederholen(self):
        self.dlg._zspins["breite"].setValue(6.0)
        self.dlg.rueckgaengig()
        self.assertTrue(self.dlg._btn_redo.isEnabled())
        self.dlg._zspins["tiefe"].setValue(6.0)
        self.assertFalse(self.dlg._btn_redo.isEnabled())
        self.dlg.wiederholen()                          # wirkungslos
        self.assertEqual(self.zone_jetzt().breite, 4.0)

    def test_rueckgaengig_meldet_dem_3d_und_haelt_die_auswahl(self):
        self.dlg._btn_vorlagen["gang"].click()
        self.st.ereignisse.clear()
        self.dlg.rueckgaengig()
        self.assertIn("sperrzonen_changed", self.st.ereignisse)
        self.assertEqual(self.dlg._liste.count(), 1)
        self.assertIs(self.dlg.gewaehlte_zone(), self.zone_jetzt())
        self.assertEqual(self.dlg._name.text(), "Publikum")

    def test_beim_schliessen_ist_der_stand_in_der_show(self):
        """Der Planer arbeitet direkt im Bestand der Show — kein „Speichern"
        im Fenster, kein Verwerfen beim Schliessen."""
        _ziehe(self.drauf, self.drauf.griffe()["mitte"], self.drauf.zu_px(2.0, 8.0))
        self.dlg._btn_fertig.click()
        _app.processEvents()
        self.assertFalse(self.dlg.isVisible())
        self.assertEqual((self.st.sperrzonen.zone("z1").x,
                          self.st.sperrzonen.zone("z1").z), (2.0, 8.0))

    def test_neue_show_leert_den_stapel(self):
        self.dlg._zspins["breite"].setValue(6.0)
        self.st.sperrzonen = SperrzonenDaten()
        self.dlg._takt()                                # der Planer merkt es selbst
        self.assertEqual(self.dlg._undo, [])
        self.dlg.rueckgaengig()
        self.assertEqual(self.st.sperrzonen.zonen, [])


# ── Laser-Karten, Herkunft der Winkel, Assistent im Planer ──────────────────

class _Rg:
    def __init__(self, von, bis, name, kind=""):
        self.range_from, self.range_to, self.name, self.kind = von, bis, name, kind


class _Ch:
    def __init__(self, attribute, ranges=()):
        self.attribute, self.name, self.ranges = attribute, attribute, list(ranges)


class LaserKartenTest(_PlanerFall):
    def test_karte_zeigt_name_montage_winkel_und_herkunft(self):
        karte = self.dlg._laser_karten[2]
        self.assertIn("Laser 2", karte.lbl_titel.text())
        self.assertIn("EL-400", karte.lbl_titel.text())
        self.assertEqual(karte.lbl_montage.text(),
                         "Montage: 1,50 m hoch · strahlt waagerecht")
        self.assertEqual(karte.lbl_winkel.text(), "Randwinkel fehlen — nicht prüfbar")
        self.assertEqual(karte.lbl_quelle.text(), "Quelle: nicht angegeben")
        self.assertEqual(karte.btn_aendern.text(), "ändern")
        self.assertTrue(karte.editor.isHidden())
        karte.btn_aendern.click()
        self.assertFalse(karte.editor.isHidden())
        self.st.visualizer_rotations[2] = (20.0, 0.0, 0.0)
        self.st.sperrzonen.setze_feld(2, _feld(zuschlag=6, quelle=S.QUELLE_DATENBLATT))
        self.dlg._takt()
        self.assertEqual(karte.lbl_winkel.text(),
                         "links 20° · rechts 20° · oben 15° · unten 15° · Zuschlag 6°")
        self.assertEqual(karte.lbl_quelle.text(), "Quelle: Datenblatt")
        self.assertIn("20° nach", karte.lbl_montage.text())

    def test_herkunft_datenblatt_profil_hand(self):
        with mock.patch.object(S, "winkel_aus_bibliothek", return_value=None), \
                mock.patch.object(self.dlg, "_frage_gesamtwinkel", return_value=(40.0, 30.0)):
            self.dlg._laser_karten[2].btn_datenblatt.click()
        feld = self.st.sperrzonen.laser_felder[2]
        self.assertEqual((feld.quelle, feld.quelle_datum), (S.QUELLE_DATENBLATT, ""))
        self.assertEqual(S.quelle_text(feld), "Datenblatt")
        with mock.patch.object(S, "winkel_aus_bibliothek",
                               return_value=LaserFeld(links=30, rechts=30, oben=20, unten=20)):
            self.dlg._laser_karten[2].btn_datenblatt.click()
        self.assertEqual(S.quelle_text(self.st.sperrzonen.laser_felder[2]), "Geräteprofil")
        # nur der Zuschlag: die Herkunft der Winkel bleibt
        self.dlg._feld_spins[2]["zuschlag"].setValue(8.0)
        self.assertEqual(self.st.sperrzonen.laser_felder[2].quelle, S.QUELLE_PROFIL)
        # ein Winkel von Hand: nicht mehr „aus dem Profil"
        self.dlg._feld_spins[2]["links"].setValue(25.0)
        feld = self.st.sperrzonen.laser_felder[2]
        self.assertEqual((feld.quelle, feld.zuschlag), (S.QUELLE_HAND, 8.0))
        self.assertEqual(self.dlg._laser_karten[2].lbl_quelle.text(),
                         "Quelle: von Hand eingetragen")

    def _mit_attrappen(self):
        kanaele = [_Ch("shutter", [_Rg(0, 9, "Aus", "closed")]), _Ch("zoom")]
        import types
        art = types.SimpleNamespace(art="statisch", name="DMX", steuert=True, mitte=124)
        angaben = types.SimpleNamespace(
            betriebsart_kanal=types.SimpleNamespace(attribut="shutter", betriebsart=(art,)),
            richtung=lambda k: None)
        for ziel, wert in ((("_kanaele"), lambda fx: list(kanaele)),
                           (("_profilangaben_modul"), lambda: types.SimpleNamespace(
                               laser_profilangaben=lambda k: angaben))):
            p = mock.patch.object(E, ziel, wert)
            p.start()
            self.addCleanup(p.stop)

    def test_assistent_sitzt_im_planer_und_traegt_das_feld_ein(self):
        self._mit_attrappen()
        self.dlg._laser_karten[2].btn_einmessen.click()
        ass = self.dlg._assistent
        self.assertIsNotNone(ass)
        self.assertEqual(self.dlg._rechts.currentIndex(), 1)
        self.assertTrue(self.dlg._btn_modus_messen.isChecked())
        self.assertEqual(self.st.programmer, {}, "Öffnen sendet nichts")
        ass._btn_weiter.click()
        ass.btn_selbst.click()
        for rand, cm in zip(S.RAENDER, (145, 145, 100, 80)):
            ass.sp_weg[rand].setValue(cm)
        ass._btn_weiter.click()
        ass._btn_weiter.click()
        self.assertIsNone(self.dlg._assistent)
        self.assertEqual(self.dlg._rechts.currentIndex(), 0)
        feld = self.st.sperrzonen.laser_felder[2]
        self.assertEqual((feld.links, feld.rechts, feld.oben, feld.unten),
                         (19.9, 19.9, 14.0, 11.3))
        self.assertEqual(feld.quelle, S.QUELLE_EINGEMESSEN)
        self.assertEqual(feld.geraet, S.geraete_kennung(self.st._patch[0]))
        self.assertTrue(self.dlg._laser_karten[2].lbl_quelle.text()
                        .startswith("Quelle: eingemessen am "))
        self.assertEqual(self.st.programmer, {}, "Weg von Hand: nie gesendet")
        self.dlg.rueckgaengig()                         # das Eintragen ist ein Schritt
        self.assertNotIn(2, self.st.sperrzonen.laser_felder)

    def test_planer_schliessen_bricht_ab_und_schaltet_aus(self):
        for ende in ("schliessen", "zonen", "show", "neu"):
            self._mit_attrappen()
            self.st.programmer.clear()
            self.dlg.show()
            self.dlg.einmessen_starten(2)
            ass = self.dlg._assistent
            ass._btn_weiter.click()
            ass.chk_bestaetigt.setChecked(True)
            ass.btn_zeigen.click()
            self.assertEqual(self.st.programmer, {(2, "shutter"): 124}, ende)
            if ende == "schliessen":
                self.dlg.close()
            elif ende == "zonen":
                self.dlg._btn_modus_zonen.click()
            elif ende == "show":
                self.dlg.patch_oder_show_geaendert()
            else:
                self.dlg.einmessen_starten(2)           # neuer Assistent
            self.assertEqual(self.st.programmer, {(2, "shutter"): 0}, ende)
            self.assertNotIn(2, self.st.sperrzonen.laser_felder)

    def _einschalten_ueber_den_assistenten(self):
        self._mit_attrappen()
        self.st.programmer.clear()
        self.dlg.show()
        self.dlg.einmessen_starten(2)
        ass = self.dlg._assistent
        ass._btn_weiter.click()
        ass.chk_bestaetigt.setChecked(True)
        ass.btn_zeigen.click()
        self.assertEqual(self.st.programmer, {(2, "shutter"): 124})

    def test_esc_und_verstecken_schalten_aus(self):
        """Esc ruft bei einem QDialog ``reject()`` — das versteckt das Fenster
        OHNE ``closeEvent``. Auch dieser Weg ist ein Abbruch: Laser aus."""
        from PySide6.QtTest import QTest
        for ende in ("esc", "reject", "hide"):
            self._einschalten_ueber_den_assistenten()
            if ende == "esc":
                QTest.keyClick(self.dlg, Qt.Key.Key_Escape)
            elif ende == "reject":
                self.dlg.reject()
            else:
                self.dlg.hide()
            _app.processEvents()
            self.assertFalse(self.dlg.isVisible(), ende)
            self.assertEqual(self.st.programmer, {(2, "shutter"): 0}, ende)
            self.assertIsNone(self.dlg._assistent, ende)
            self.assertNotIn(2, self.st.sperrzonen.laser_felder)

    def test_3d_fenster_schliessen_schaltet_aus(self):
        """Das 3D-Fenster wird beim Schliessen nur versteckt; der Planer
        bekommt davon kein Ereignis. Ein laufendes Einmessen endet trotzdem."""
        import src.ui.visualizer.visualizer_window as VW

        class _Fenster(VW.VisualizerWindow):
            def __init__(self, state, dlg):
                VW.QMainWindow.__init__(self)
                self._state = state
                self._sperrzonen_dlg = dlg

            def _confirm_close_with_unsaved_stage(self):
                return True

            def hideEvent(self, ev):
                VW.QMainWindow.hideEvent(self, ev)

        self._einschalten_ueber_den_assistenten()
        win = _Fenster(self.st, self.dlg)
        self.addCleanup(win.deleteLater)
        win.show()
        _app.processEvents()
        win.close()
        _app.processEvents()
        self.assertEqual(self.st.programmer, {(2, "shutter"): 0})
        self.assertIsNone(self.dlg._assistent)


# ── Einstieg und alte Funktionen ────────────────────────────────────────────

class EinstiegTest(unittest.TestCase):
    def test_der_zahlenfeld_dialog_ist_weg(self):
        self.assertFalse(hasattr(UI, "SperrzonenDialog"))
        quelle = (_REPO / "src" / "ui" / "visualizer" / "visualizer_window.py") \
            .read_text(encoding="utf-8")
        self.assertNotIn("SperrzonenDialog", quelle)
        self.assertIn("planer_oeffnen(self._state, self)", quelle)

    def test_hinweis_und_3d_knopf_oeffnen_denselben_planer(self):
        import src.ui.visualizer.visualizer_window as VW

        class _Fenster(VW.VisualizerWindow):
            def __init__(self, state):
                VW.QMainWindow.__init__(self)
                self._state = state

        st = _State()
        hinweis = UI.SperrzonenHinweis(st)
        self.addCleanup(hinweis.deleteLater)
        knopf = hinweis.findChild(type(hinweis._btn_planer), "sperrzonenHinweisPlaner")
        self.assertEqual(knopf.text(), "Sperrzonen planen…")
        self.assertGreaterEqual(knopf.minimumHeight(), 36)
        knopf.click()
        dlg = P._offen
        self.assertIsInstance(dlg, P.SperrzonenPlaner)
        self.addCleanup(dlg.deleteLater)
        self.assertTrue(dlg.isVisible())
        self.assertFalse(dlg.isModal())
        win = _Fenster(st)
        self.addCleanup(win.deleteLater)
        VW.VisualizerWindow._on_sperrzonen_dialog(win)
        self.assertIs(win._sperrzonen_dlg, dlg)
        anderer = P.planer_oeffnen(_State())            # andere Show: neuer Planer
        self.addCleanup(anderer.deleteLater)
        self.assertIsNot(anderer, dlg)
        anderer.close()
        dlg.close()

    def test_grenzen_dauernd_sichtbar_in_einer_zeile(self):
        st = _State()
        dlg = P.SperrzonenPlaner(st)
        self.addCleanup(dlg.deleteLater)
        dlg.show()
        _app.processEvents()
        lab = dlg.findChild(QLabel, "sperrzonenGrenzen")
        self.assertEqual(lab.text(), "Nur Anzeige — schaltet den Laser nicht ab. "
                                     "Kein Ersatz für Blende, Abstände, "
                                     "Laserschutzbeauftragten.")
        self.assertTrue(lab.isVisibleTo(dlg))
        self.assertLess(lab.height(), 60)
        dlg.einmessen_starten(2)                        # auch neben dem Assistenten
        _app.processEvents()
        self.assertTrue(lab.isVisibleTo(dlg))
        self.assertEqual(dlg.windowTitle(), "Sperrzonen planen")
        dlg.close()

    def test_funktionen_des_alten_dialogs_sind_im_planer(self):
        dlg = P.SperrzonenPlaner(_State())
        self.addCleanup(dlg.deleteLater)
        self.assertEqual(dlg._chk_lasersicht.text(),
                         "Sicht des Lasers zeigen (Fenster im 3D)")
        self.assertEqual(dlg._laser_karten[2].btn_datenblatt.text(),
                         "Winkel aus Profil / Datenblatt")
        self.assertEqual(set(dlg._zspins), {"x", "y", "z", "breite", "hoehe", "tiefe"})
        self.assertEqual(set(dlg._feld_spins[2]), {*S.RAENDER, "zuschlag"})
        self.assertEqual(dlg._chk_einrasten.text(), "Einrasten auf 0,25 m (beim Ziehen)")

    def test_planer_und_assistent_fassen_die_ausgabe_nicht_an(self):
        for name in ("sperrzonen_planer.py", "einmess_assistent.py", "sperrzonen_ui.py"):
            quelle = (_REPO / "src" / "ui" / "visualizer" / name).read_text(encoding="utf-8")
            for wort in ("output_manager", "_send_all", "set_laser_estop",
                         "set_programmer_value", "universes["):
                self.assertNotIn(wort, quelle, f"{name}: {wort}")
        ausgabe = (_REPO / "src" / "core" / "dmx" / "output_manager.py") \
            .read_text(encoding="utf-8")
        for wort in ("sperrzonen", "feld_einmessen"):
            self.assertNotIn(wort, ausgabe, wort)

    def test_buehnenelemente_kommen_als_umrisse(self):
        from src.core.stage.stage_definition import StageDefinition, StageElement
        buehne = StageDefinition(name="T", elements=[
            StageElement(type="platform", x=0, y=0.5, z=1, w=8, h=1, d=4, name="Bühne"),
            StageElement(type="truss_h", x=0, y=5, z=1, w=10, h=0.3, d=0.3,
                         rotation=math.pi / 2)])
        st = _State()
        self.assertEqual(P.buehnen_umrisse(st), [], "ohne aktive Bühne nichts")
        st.active_stage_name = "t"
        with mock.patch("src.core.stage.stage_definition.resolve_active_stage",
                        return_value=(buehne, "user", "t")):
            umrisse = P.buehnen_umrisse(st)
        self.assertEqual(umrisse[0]["name"], "Bühne")
        self.assertEqual(sorted(umrisse[0]["drauf"]),
                         [(-4.0, -1.0), (-4.0, 3.0), (4.0, -1.0), (4.0, 3.0)])
        self.assertEqual(sorted(umrisse[0]["seite"]),
                         [(-1.0, 0.0), (-1.0, 1.0), (3.0, 0.0), (3.0, 1.0)])
        xs = [p[0] for p in umrisse[1]["drauf"]]         # um 90° gedreht: schmal in x
        zs = [p[1] for p in umrisse[1]["drauf"]]
        self.assertAlmostEqual(max(xs) - min(xs), 0.3, places=6)
        self.assertAlmostEqual(max(zs) - min(zs), 10.0, places=6)
        with mock.patch("src.core.stage.stage_definition.resolve_active_stage",
                        side_effect=RuntimeError("kaputt")):
            self.assertEqual(P.buehnen_umrisse(st), [])


# ── Speichern / Laden ───────────────────────────────────────────────────────

class AbschnittTest(unittest.TestCase):
    def test_version_bleibt_eins(self):
        self.assertEqual(S.SPERRZONEN_VERSION, 1)

    def test_herkunft_datum_und_drehung_ueberleben(self):
        daten = SperrzonenDaten()
        daten.zonen.append(Sperrzone(id="z", name="Gang", dreh_y=35.0))
        daten.setze_feld(2, LaserFeld(links=19.9, rechts=19.9, oben=14, unten=11.3,
                                      zuschlag=5, geraet="a|b|c",
                                      quelle=S.QUELLE_EINGEMESSEN,
                                      quelle_datum="2026-10-11"))
        daten.setze_feld(3, _feld(quelle=S.QUELLE_DATENBLATT))
        roh = json.loads(json.dumps(daten.to_dict()))
        self.assertEqual(roh["version"], 1)
        self.assertEqual(roh["zonen"][0]["dreh_y"], 35.0)
        self.assertEqual(roh["laser_felder"]["2"]["quelle"], "eingemessen")
        self.assertEqual(roh["laser_felder"]["2"]["quelle_datum"], "2026-10-11")
        self.assertNotIn("quelle_datum", roh["laser_felder"]["3"])
        wieder, probleme = S.daten_aus_abschnitt(roh)
        self.assertEqual(probleme, [])
        self.assertEqual(wieder.to_dict(), daten.to_dict())
        self.assertEqual(S.quelle_text(wieder.laser_felder[2]), "eingemessen am 11.10.2026")
        self.assertEqual(S.quelle_text(wieder.laser_felder[3]), "Datenblatt")

    def test_alt_abschnitt_laedt_und_speichert_unveraendert(self):
        alt = {"version": 1,
               "zonen": [{"id": "z1", "name": "Publikum", "x": 1.0, "y": 0.0, "z": 6.5,
                          "breite": 8.0, "hoehe": 3.0, "tiefe": 5.0, "dreh_y": 15.0}],
               "laser_felder": {"7": {"links": 12.0, "rechts": 20.0, "oben": 5.0,
                                      "unten": 25.0, "zuschlag": 4.0}}}
        daten, probleme = S.daten_aus_abschnitt(json.loads(json.dumps(alt)))
        self.assertEqual(probleme, [])
        self.assertEqual(daten.to_dict(), alt, "kein neuer Schluessel im Alt-Abschnitt")
        feld = daten.laser_felder[7]
        self.assertEqual((feld.quelle, feld.quelle_datum), ("", ""))
        self.assertEqual(S.quelle_text(feld), "Herkunft nicht vermerkt")
        self.assertEqual(S.quelle_text(LaserFeld()), "nicht angegeben")

    def test_unlesbare_herkunft_wird_nicht_geglaubt(self):
        for roh in ({"quelle": "TÜV"}, {"quelle": 5}, {"quelle": "eingemessen",
                                                       "quelle_datum": "gestern"},
                    {"quelle_datum": "2026-10-11"}, {"quelle": "eingemessen",
                                                     "quelle_datum": 20261011}):
            feld = LaserFeld.from_dict({"links": 1, "rechts": 1, "oben": 1, "unten": 1,
                                        **roh})
            self.assertTrue(feld.vollstaendig)
            self.assertIn(feld.quelle, ("", S.QUELLE_EINGEMESSEN))
            self.assertEqual(feld.quelle_datum, "")
            self.assertNotIn("am ", S.quelle_text(feld))

    def test_neuerer_abschnitt_bleibt_bewahrt(self):
        neu = {"version": 2, "zonen": [{"form": "zylinder"}], "extra": [1, 2]}
        daten, probleme = S.daten_aus_abschnitt(json.loads(json.dumps(neu)))
        self.assertEqual(len(probleme), 1)
        self.assertEqual(daten.to_dict(), neu)
        self.assertEqual(daten.zonen, [])


class ShowDateiTest(unittest.TestCase):
    """Am echten ``save_show``/``load_show`` (isolierte Test-Daten aus conftest)."""

    def setUp(self):
        import src.core.show.show_file as SF
        from src.core.app_state import get_state
        self.SF, self.st = SF, get_state()
        SF.reset_show()
        self.tmp = tempfile.mkdtemp(prefix="las35_")
        self.pfad = os.path.join(self.tmp, "t.lshow")

    def tearDown(self):
        self.SF.reset_show()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_planer_stand_durch_die_show_datei(self):
        dlg = P.SperrzonenPlaner(self.st)
        self.addCleanup(dlg.deleteLater)
        with mock.patch.object(M, "merke_benutzt"):
            dlg.vorlage_anlegen("gang")
        dlg._dreh.setValue(40.0)
        self.st.sperrzonen.setze_feld(7, LaserFeld(
            links=19.9, rechts=19.9, oben=14, unten=11.3,
            quelle=S.QUELLE_EINGEMESSEN, quelle_datum="2026-10-11"))
        vorher = json.loads(json.dumps(self.st.sperrzonen.to_dict()))
        dlg.close()
        self.SF.save_show(self.pfad)
        with zipfile.ZipFile(self.pfad, "r") as zf:
            abschnitt = json.loads(zf.read("show.json").decode("utf-8"))["sperrzonen"]
        self.assertEqual(abschnitt, vorher)
        self.assertEqual(abschnitt["version"], 1)
        self.assertEqual(abschnitt["zonen"][0]["dreh_y"], 40.0)
        self.SF.reset_show()
        self.assertTrue(self.st.sperrzonen.ist_leer())
        with mock.patch.object(M, "merke_benutzt"):
            self.SF.load_show(self.pfad)
        self.assertEqual(self.st.sperrzonen.to_dict(), vorher)
        self.assertEqual(S.quelle_text(self.st.sperrzonen.laser_felder[7]),
                         "eingemessen am 11.10.2026")


if __name__ == "__main__":
    unittest.main()
