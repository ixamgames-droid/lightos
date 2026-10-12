"""LAS-35: Feld einmessen (Wand und Zollstock) — Rechnung und Schalten.

* Die Rechnung nimmt, was der Nutzer an der Wand abliest (Meter, Zentimeter)
  — nie DMX-Werte.
* Der Assistent schaltet den Laser nie ohne ausdrueckliche Bestaetigung ein.
  Eine Attrappe zaehlt jeden Schreibzugriff auf den Programmer.
* Jedes Ende (Uebernehmen, Abbrechen, STOPP) schaltet wieder aus, falls der
  Assistent eingeschaltet hat. Ein gedrueckter LASER NOT-AUS wird nie geloest.
"""
import datetime
import inspect
import math
import os
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.laser import feld_einmessen as E
from src.core.laser import sperrzonen as S
from src.ui.visualizer import einmess_assistent as A

_app = QApplication.instance() or QApplication([])
_ECHTES_MODUL_HOLEN = E._profilangaben_modul


# ── Rechnung ────────────────────────────────────────────────────────────────

class RechnungTest(unittest.TestCase):
    def test_atan_aus_abstand_und_weg(self):
        self.assertAlmostEqual(E.winkel_grad(4.0, 145.0),
                               math.degrees(math.atan(1.45 / 4.0)), places=12)
        self.assertAlmostEqual(E.winkel_grad(2.0, 200.0), 45.0, places=12)
        self.assertEqual(E.winkel_grad(3.0, 0.0), 0.0)

    def test_vier_raender_getrennt(self):
        w = E.randwinkel(E.Messung(4.0, 145.0, 100.0, 60.0, 250.0))
        self.assertEqual(set(w), set(S.RAENDER))
        for rand, cm in (("links", 145), ("rechts", 100), ("oben", 60), ("unten", 250)):
            self.assertAlmostEqual(w[rand], math.degrees(math.atan(cm / 400.0)),
                                   places=12, msg=rand)

    def test_gegenprobe_nennt_den_rechenweg(self):
        self.assertEqual(E.gegenprobe(4.0, 145.0, "links"),
                         "bei 4,00 m Abstand und 1,45 m nach links: 19,9°")
        self.assertEqual(E.gegenprobe(2.5, 80.0, "oben"),
                         "bei 2,50 m Abstand und 0,80 m nach oben: 17,7°")

    def test_abstand_null_und_negative_werte_werden_nie_zu_einem_winkel(self):
        for abstand, weg in ((0.0, 100.0), (-1.0, 100.0), (4.0, -5.0),
                             (float("nan"), 1.0), (4.0, float("inf")), (None, 1.0)):
            with self.assertRaises(ValueError, msg=(abstand, weg)):
                E.winkel_grad(abstand, weg)

    def test_plausibel_ohne_rueckfrage(self):
        self.assertEqual(E.rueckfragen(E.Messung(4.0, 145, 145, 100, 80)), [])

    def test_rueckfrage_abstand_null_sperrt(self):
        fragen = E.rueckfragen(E.Messung(0.0, 145, 145, 100, 80))
        self.assertEqual(len(fragen), 1)
        self.assertTrue(fragen[0].sperrt)
        self.assertIn("Abstand", fragen[0].text)
        with self.assertRaises(ValueError):
            E.feld_aus_messung(E.Messung(0.0, 145, 145, 100, 80))

    def test_rueckfrage_negativer_wert_sperrt(self):
        fragen = E.rueckfragen(E.Messung(4.0, -145, 145, 100, 80))
        self.assertTrue(any(f.sperrt and "links" in f.text for f in fragen))
        with self.assertRaises(ValueError):
            E.feld_aus_messung(E.Messung(4.0, -145, 145, 100, 80))

    def test_rueckfrage_ueber_60_grad_ist_eine_frage_keine_sperre(self):
        # 2 m Abstand, 4 m nach links = 63,4 Grad
        fragen = E.rueckfragen(E.Messung(2.0, 400, 100, 50, 50))
        self.assertEqual(len(fragen), 1)
        self.assertFalse(fragen[0].sperrt)
        self.assertIn("60°", fragen[0].text)
        self.assertIn("links", fragen[0].text)
        self.assertNotIn("rechts", fragen[0].text)
        # genau 60 Grad und darunter: keine Frage
        knapp = math.tan(math.radians(59.9)) * 200
        self.assertEqual(E.rueckfragen(E.Messung(2.0, knapp, 100, 50, 50)), [])

    def test_mehr_als_der_groesste_eintragbare_winkel_sperrt(self):
        """Kappen waere ein zu KLEINES Feld — also nicht uebernehmen."""
        fragen = E.rueckfragen(E.Messung(0.5, 1000, 100, 50, 50))     # 87 Grad
        self.assertTrue(fragen[0].sperrt)
        with self.assertRaises(ValueError):
            E.feld_aus_messung(E.Messung(0.5, 1000, 100, 50, 50))

    def test_alles_null_und_fehlende_achse_fragen_nach(self):
        self.assertTrue(any("Alle vier" in f.text
                            for f in E.rueckfragen(E.Messung(4.0, 0, 0, 0, 0))))
        fragen = E.rueckfragen(E.Messung(4.0, 100, 100, 0, 0))
        self.assertTrue(any("Oben und unten" in f.text and not f.sperrt for f in fragen))

    def test_feld_traegt_herkunft_datum_und_zuschlag(self):
        feld = E.feld_aus_messung(E.Messung(4.0, 145, 145, 100, 80), zuschlag=5,
                                  geraet="a|b|c", datum=datetime.date(2026, 10, 11))
        self.assertEqual((feld.links, feld.rechts, feld.oben, feld.unten),
                         (19.9, 19.9, 14.0, 11.3))
        self.assertEqual(feld.zuschlag, 5.0)
        self.assertEqual(feld.quelle, S.QUELLE_EINGEMESSEN)
        self.assertEqual(feld.quelle_datum, "2026-10-11")
        self.assertEqual(S.quelle_text(feld), "eingemessen am 11.10.2026")
        self.assertEqual(feld.geraet, "a|b|c")
        # Zuschlag nie unter dem Minimum
        self.assertEqual(E.feld_aus_messung(E.Messung(4.0, 1, 1, 1, 1), zuschlag=0).zuschlag,
                         S.ZUSCHLAG_MIN)

    def test_rechnung_kennt_keine_dmx_werte(self):
        """G11: gerechnet wird mit dem Abgelesenen. Die Rechen-Funktionen
        nehmen weder State noch Geraet noch Kanalwerte entgegen."""
        for fn in (E.winkel_grad, E.randwinkel, E.gegenprobe, E.rueckfragen,
                   E.feld_aus_messung):
            namen = set(inspect.signature(fn).parameters)
            self.assertFalse(namen & {"state", "fid", "dmx", "wert", "kanal", "fx"},
                             fn.__name__)
        self.assertEqual(set(E.Messung.__dataclass_fields__),
                         {"abstand_m", "links_cm", "rechts_cm", "oben_cm", "unten_cm"})


# ── Attrappen ───────────────────────────────────────────────────────────────

class _Ch:
    def __init__(self, attribute, ranges=()):
        self.attribute, self.name, self.ranges = attribute, attribute, list(ranges)


class _Rg:
    def __init__(self, von, bis, name, kind=""):
        self.range_from, self.range_to, self.name, self.kind = von, bis, name, kind


class _Fx:
    fid = 7


class _State:
    """Zaehlt jeden Schreibzugriff auf den Programmer."""

    def __init__(self):
        self.laser_estop_active = False
        self.programmer = {}
        self.schreiben = []          # (fid, attribut, wert)
        self.geloescht = []          # (fid, attribut)

    def get_patched_fixtures(self):
        return [_Fx()]

    def get_programmer_value(self, fid, attribut, head=None):
        return self.programmer.get((fid, attribut))

    def set_programmer_value(self, fid, attribut, wert, head=None):
        self.schreiben.append((fid, attribut, int(wert)))
        self.programmer[(fid, attribut)] = int(wert)

    def clear_programmer_value(self, fid, attribut):
        self.geloescht.append((fid, attribut))
        self.programmer.pop((fid, attribut), None)


_KANAELE = [_Ch("shutter", [_Rg(0, 9, "Aus", "closed"), _Rg(10, 255, "An", "open")]),
            _Ch("zoom"), _Ch("laser_x")]


def _profilangaben(mit_zoom=True, steuert=True):
    """Attrappe der Profilangaben (LAS-33): Betriebsart 100-149 = statisch,
    Groesse laeuft umgekehrt (0 = gross)."""
    art = types.SimpleNamespace(art="statisch", name="DMX statisch", steuert=steuert,
                                mitte=124)
    aus = types.SimpleNamespace(art="aus", name="Aus", steuert=False, mitte=4)
    art_kanal = types.SimpleNamespace(attribut="shutter", betriebsart=(aus, art))
    groesse = types.SimpleNamespace(ende_niedrig="gross", ende_hoch="klein",
                                    regler_zu_dmx=lambda anteil: 0 if anteil >= 1 else 255)
    angaben = types.SimpleNamespace(
        betriebsart_kanal=art_kanal,
        richtung=lambda kanal: groesse if (kanal == "zoom" and mit_zoom) else None)
    return types.SimpleNamespace(laser_profilangaben=lambda kanaele: angaben)


def _schalter(state):
    return E.FeldSchalter(state, 7, kanaele_holen=lambda fx: list(_KANAELE))


class SchalterTest(unittest.TestCase):
    def setUp(self):
        self.st = _State()
        patch = mock.patch.object(E, "_profilangaben_modul", lambda: _profilangaben())
        patch.start()
        self.addCleanup(patch.stop)
        self.sch = _schalter(self.st)

    def test_ohne_bestaetigung_kein_einziger_schreibzugriff(self):
        for bestaetigt in (False, None, 0, 1, "ja", [True]):
            self.assertFalse(self.sch.einschalten(bestaetigt), repr(bestaetigt))
        self.assertEqual(self.st.schreiben, [])
        self.assertEqual(self.st.geloescht, [])
        self.assertFalse(self.sch.eingeschaltet)
        # auch plan/kann_einschalten/aus_schritt schreiben nichts
        self.sch.plan(); self.sch.kann_einschalten(); self.sch.aus_schritt()
        self.assertEqual(self.st.schreiben, [])

    def test_mit_bestaetigung_groesse_zuerst_betriebsart_zuletzt(self):
        self.assertTrue(self.sch.einschalten(True))
        self.assertEqual(self.st.schreiben, [(7, "zoom", 0), (7, "shutter", 124)])
        self.assertTrue(self.sch.eingeschaltet)

    def test_beenden_schaltet_aus_und_nimmt_die_groesse_zurueck(self):
        self.st.programmer[(7, "zoom")] = 77          # stand schon im Programmer
        self.sch.einschalten(True)
        self.st.schreiben.clear()
        self.sch.beenden()
        self.assertEqual(self.st.schreiben[0], (7, "shutter", 0), "erst AUS")
        self.assertEqual(self.st.programmer[(7, "shutter")], 0)
        self.assertEqual(self.st.programmer[(7, "zoom")], 77)
        self.assertFalse(self.sch.eingeschaltet)
        self.st.schreiben.clear()
        self.sch.beenden()                             # zweites Ende: nichts mehr
        self.assertEqual(self.st.schreiben, [])

    def test_beenden_ohne_einschalten_sendet_nichts(self):
        """Weg „Ich stelle den Laser selbst ein": LightOS sendet nichts — auch
        am Ende nicht."""
        self.sch.beenden()
        self.assertEqual(self.st.schreiben, [])
        self.assertEqual(self.st.geloescht, [])

    def test_stopp_setzt_die_betriebsart_auf_aus(self):
        self.assertTrue(self.sch.stopp())
        self.assertEqual(self.st.schreiben, [(7, "shutter", 0)])

    def test_notaus_wird_nie_geloest(self):
        """Ein Schreibzugriff auf die Betriebsart loest den LASER NOT-AUS
        (A3D-02). Bei gedruecktem NOT-AUS schreibt der Assistent sie deshalb
        gar nicht: kein Einschalten, und STOPP nimmt den Wert nur heraus."""
        self.st.laser_estop_active = True
        ok, grund = self.sch.kann_einschalten()
        self.assertFalse(ok)
        self.assertIn("NOT-AUS", grund)
        self.assertFalse(self.sch.einschalten(True))
        self.assertEqual(self.st.schreiben, [])
        self.assertTrue(self.sch.stopp())
        self.assertEqual(self.st.schreiben, [])
        self.assertEqual(self.st.geloescht, [(7, "shutter")])

    def test_notaus_waehrend_des_einmessens(self):
        self.sch.einschalten(True)
        self.st.laser_estop_active = True
        self.st.schreiben.clear()
        self.sch.beenden()
        self.assertNotIn("shutter", [a for _f, a, _w in self.st.schreiben])
        self.assertIn((7, "shutter"), self.st.geloescht)
        self.assertNotIn((7, "shutter"), self.st.programmer)

    def test_ohne_profilangaben_nur_der_weg_von_hand(self):
        """Dieser Zweig hat LAS-33 (profilangaben.py) nicht: kein harter
        Import, kein Plan, kein Einschalten."""
        with mock.patch.object(E, "_profilangaben_modul", lambda: None):
            sch = _schalter(self.st)
            self.assertIsNone(sch.plan())
            ok, grund = sch.kann_einschalten()
            self.assertFalse(ok)
            self.assertIn("Geräteprofil", grund)
            self.assertFalse(sch.einschalten(True))
        self.assertEqual(self.st.schreiben, [])

    def test_modul_import_ist_weich(self):
        quelle = inspect.getsource(E)
        self.assertNotIn("from src.core.laser import profilangaben", quelle)
        self.assertNotIn("from src.core.laser.profilangaben", quelle)
        self.assertNotIn("import src.core.laser.profilangaben", quelle)
        vorhanden = os.path.exists(os.path.join(os.path.dirname(E.__file__),
                                                "profilangaben.py"))
        self.assertEqual(_ECHTES_MODUL_HOLEN() is not None, vorhanden)

    def test_profil_ohne_steuerbare_betriebsart_kein_plan(self):
        with mock.patch.object(E, "_profilangaben_modul",
                               lambda: _profilangaben(steuert=False)):
            self.assertIsNone(_schalter(self.st).plan())

    def test_ohne_betriebsart_kanal_wird_nie_eingeschaltet(self):
        """Was LightOS nicht wieder ausschalten koennte, schaltet es nicht ein."""
        sch = E.FeldSchalter(self.st, 7, kanaele_holen=lambda fx: [_Ch("zoom")])
        self.assertIsNone(sch.aus_schritt())
        self.assertFalse(sch.einschalten(True))
        self.assertFalse(sch.stopp())
        self.assertEqual(self.st.schreiben, [])

    def test_modul_fasst_die_ausgabe_nicht_an(self):
        quelle = inspect.getsource(E)
        for wort in ("output_manager", "_send_all", "set_laser_estop",
                     "laser_estop_active =", "blackout"):
            self.assertNotIn(wort, quelle, wort)


# ── Der Assistent (Oberflaeche) ─────────────────────────────────────────────

class AssistentTest(unittest.TestCase):
    def setUp(self):
        self.st = _State()
        patch = mock.patch.object(E, "_profilangaben_modul", lambda: _profilangaben())
        patch.start()
        self.addCleanup(patch.stop)
        self.ass = A.EinmessAssistent(
            self.st, 7, "EL-400", S.LaserFeld(links=20, rechts=20, oben=15, unten=15,
                                              zuschlag=6, quelle=S.QUELLE_DATENBLATT),
            schalter=_schalter(self.st), heute=datetime.date(2026, 10, 11))
        self.ergebnis = []
        self.ass.beendet.connect(self.ergebnis.append)
        self.addCleanup(self.ass.deleteLater)

    def _bis_schritt(self, nr):
        while self.ass.schritt() < nr:
            self.assertTrue(self.ass._btn_weiter.isEnabled(), self.ass.schritt())
            self.ass._btn_weiter.click()

    def _messen(self, abstand=4.0, links=145, rechts=145, oben=100, unten=80):
        self.ass.sp_abstand.setValue(abstand)
        for rand, cm in zip(S.RAENDER, (links, rechts, oben, unten)):
            self.ass.sp_weg[rand].setValue(cm)

    def test_vier_schritte_in_der_reihenfolge(self):
        self.assertEqual(A.SCHRITTE,
                         ("Aufstellung", "Größtes Feld", "Ablesen", "Übernehmen"))
        self.assertEqual(self.ass.schritt(), 0)
        self.assertFalse(self.ass._btn_stopp.isVisibleTo(self.ass))
        self._bis_schritt(1)
        self.assertTrue(self.ass._btn_stopp.isVisibleTo(self.ass))
        self.assertGreaterEqual(self.ass._btn_stopp.minimumHeight(), 48)

    def test_durchklicken_ohne_bestaetigung_schreibt_nichts(self):
        """Alle Schritte, alle Zahlenfelder, der Knopf ohne Haken — kein
        einziger Schreibzugriff."""
        self._bis_schritt(1)
        self.assertFalse(self.ass.chk_bestaetigt.isChecked())
        self.assertFalse(self.ass.btn_zeigen.isEnabled())
        self.ass.btn_zeigen.click()                    # gesperrt: wirkungslos
        self.assertFalse(self.ass.feld_zeigen())       # direkt gerufen: auch nichts
        self.ass.btn_selbst.click()
        self.assertEqual(self.ass.schritt(), 2)
        self._messen()
        self._bis_schritt(3)
        self.ass.sp_zuschlag.setValue(7.0)
        self.ass.zurueck(); self.ass.zurueck(); self.ass.zurueck()
        self.assertEqual(self.st.schreiben, [])
        self.assertEqual(self.st.geloescht, [])

    def test_bestaetigung_ist_der_ausdrueckliche_satz(self):
        satz = ("Der Laser wird jetzt eingeschaltet. Ich habe den Bereich "
                "abgesichert.")
        self.assertEqual(E.BESTAETIGUNG, satz)
        self.assertIn(satz, self.ass.lbl_bestaetigt.text())
        self.assertEqual(self.ass.chk_bestaetigt.accessibleName(), satz)
        # der Satz ist die Aussage des NUTZERS — sonst sagt das nirgends jemand
        self.assertEqual(inspect.getsource(E).count("abgesichert"), 1)
        self.assertIn("schaltet den Laser ein", self.ass.btn_zeigen.text())

    def test_einschalten_nur_mit_haken_und_der_haken_gilt_einmal(self):
        self._bis_schritt(1)
        self.ass.chk_bestaetigt.setChecked(True)
        self.assertTrue(self.ass.btn_zeigen.isEnabled())
        self.assertEqual(self.st.schreiben, [], "der Haken allein sendet nichts")
        self.ass.btn_zeigen.click()
        self.assertEqual(self.st.schreiben, [(7, "zoom", 0), (7, "shutter", 124)])
        self.assertFalse(self.ass.chk_bestaetigt.isChecked())
        self.assertFalse(self.ass.btn_zeigen.isEnabled())
        self.assertIn("eingeschaltet", self.ass._lbl_zustand.text())

    def test_haken_faellt_beim_wiederbetreten_des_schritts(self):
        self._bis_schritt(1)
        self.ass.chk_bestaetigt.setChecked(True)
        self.ass.zurueck()
        self._bis_schritt(1)
        self.assertFalse(self.ass.chk_bestaetigt.isChecked())

    def test_stopp_schaltet_aus(self):
        self._bis_schritt(1)
        self.ass.chk_bestaetigt.setChecked(True)
        self.ass.btn_zeigen.click()
        self.st.schreiben.clear()
        self.ass._btn_stopp.click()
        self.assertEqual(self.st.schreiben[0], (7, "shutter", 0))
        self.assertFalse(self.ass.schalter.eingeschaltet)
        self.assertEqual(self.ergebnis, [], "STOPP beendet den Assistenten nicht")

    def test_stopp_behauptet_kein_aus_wenn_das_schreiben_scheitert(self):
        """Scheitert der Schreibzugriff, darf der Dialog nicht „steht auf Aus"
        melden — er verweist auf den LASER NOT-AUS."""
        self._bis_schritt(1)
        self.ass.chk_bestaetigt.setChecked(True)
        self.ass.btn_zeigen.click()
        self.assertTrue(self.ass.schalter.eingeschaltet)

        def _kaputt(*_a, **_k):
            raise RuntimeError("Ausgabe weg")

        self.st.set_programmer_value = _kaputt
        self.ass._btn_stopp.click()
        text = self.ass._lbl_zustand.text()
        self.assertNotIn("steht auf", text)
        self.assertIn("LASER NOT-AUS", text)
        self.assertIs(_schalter(self.st).beenden(), True, "nichts eingeschaltet: nichts zu tun")

    def test_abbruch_schaltet_in_jedem_schritt_aus(self):
        for schritt in (1, 2, 3):
            st = _State()
            ass = A.EinmessAssistent(st, 7, "EL-400", schalter=_schalter(st))
            self.addCleanup(ass.deleteLater)
            ende = []
            ass.beendet.connect(ende.append)
            ass._btn_weiter.click()
            ass.chk_bestaetigt.setChecked(True)
            ass.btn_zeigen.click()
            ass.sp_weg["links"].setValue(100)
            ass.sp_weg["rechts"].setValue(100)
            ass.sp_weg["oben"].setValue(50)
            ass.sp_weg["unten"].setValue(50)
            while ass.schritt() < schritt:
                ass._btn_weiter.click()
            self.assertEqual(ass.schritt(), schritt)
            st.schreiben.clear()
            ass._btn_abbrechen.click()
            self.assertEqual(st.programmer[(7, "shutter")], 0, schritt)
            self.assertEqual(ende, [None], schritt)
            self.assertNotIn((7, "zoom"), st.programmer, "Größe zurückgenommen")

    def test_uebernehmen_traegt_ein_und_schaltet_vorher_aus(self):
        self._bis_schritt(1)
        self.ass.chk_bestaetigt.setChecked(True)
        self.ass.btn_zeigen.click()
        self._bis_schritt(2)
        self._messen()
        self.assertIn("links 19,9°", self.ass._lbl_ergebnis.text())
        self.assertIn("bei 4,00 m Abstand und 1,45 m nach links: 19,9°",
                      self.ass._lbl_ergebnis.text())
        self._bis_schritt(3)
        self.assertEqual(self.ass.sp_zuschlag.value(), 5.0, "Standard 5 Grad")
        self.assertEqual(self.ass.sp_zuschlag.minimum(), 2.0)
        self.assertIn("eingemessen am 11.10.2026", self.ass._lbl_summe.text())
        self.assertIn("Laser aus", self.ass._btn_weiter.text())
        self.st.schreiben.clear()
        self.ass._btn_weiter.click()
        self.assertEqual(self.st.programmer[(7, "shutter")], 0)
        feld = self.ergebnis[0]
        self.assertEqual((feld.links, feld.rechts, feld.oben, feld.unten),
                         (19.9, 19.9, 14.0, 11.3))
        self.assertEqual((feld.quelle, feld.quelle_datum),
                         (S.QUELLE_EINGEMESSEN, "2026-10-11"))
        self.ass._btn_weiter.click()                   # zweiter Klick: nichts
        self.assertEqual(len(self.ergebnis), 1)

    def test_rueckfrage_muss_beantwortet_werden(self):
        self._bis_schritt(2)
        self._messen(abstand=2.0, links=400)           # 63,4 Grad
        self.assertFalse(self.ass._lbl_rueckfrage.isHidden())
        self.assertIn("60°", self.ass._lbl_rueckfrage.text())
        self.assertFalse(self.ass._btn_weiter.isEnabled())
        self.ass.weiter()
        self.assertEqual(self.ass.schritt(), 2)
        self.ass.chk_stimmt.setChecked(True)
        self.assertTrue(self.ass._btn_weiter.isEnabled())
        # neue Zahl -> die Antwort gilt nicht mehr
        self.ass.sp_weg["links"].setValue(410)
        self.assertFalse(self.ass.chk_stimmt.isChecked())
        self.assertFalse(self.ass._btn_weiter.isEnabled())

    def test_abstand_null_laesst_nicht_weiter(self):
        self.ass.sp_abstand.setValue(0.0)
        self.assertFalse(self.ass._btn_weiter.isEnabled())
        self.ass.weiter()
        self.assertEqual(self.ass.schritt(), 0)
        self.assertIsNone(self.ass.feld())

    def test_skizze_zeigt_die_eingetragenen_werte(self):
        self._bis_schritt(2)
        self._messen()
        sk = self.ass._skizze_wand
        self.assertEqual(sk.wege, {"links": 145.0, "rechts": 145.0,
                                   "oben": 100.0, "unten": 80.0})
        self.assertEqual(self.ass._skizze_aufstellung.abstand_m, 4.0)
        self.assertFalse(sk.grab().isNull())

    def test_ohne_profilangaben_nur_von_hand(self):
        with mock.patch.object(E, "_profilangaben_modul", lambda: None):
            st = _State()
            ass = A.EinmessAssistent(st, 7, "EL-400", schalter=_schalter(st))
            self.addCleanup(ass.deleteLater)
            ass._btn_weiter.click()
            self.assertFalse(ass.chk_bestaetigt.isEnabled())
            self.assertFalse(ass.btn_zeigen.isEnabled())
            ass.chk_bestaetigt.setChecked(True)
            self.assertFalse(ass.btn_zeigen.isEnabled())
            self.assertFalse(ass.feld_zeigen())
            self.assertTrue(ass.btn_selbst.isEnabled())
            self.assertEqual(st.schreiben, [])

    def test_notaus_hinweis_steht_im_assistenten(self):
        self._bis_schritt(1)
        self.assertIn("LASER NOT-AUS", self.ass._lbl_notaus.text())
        self.assertIn("jederzeit", self.ass._lbl_notaus.text())
        self.assertTrue(self.ass._lbl_notaus.isVisibleTo(self.ass))


if __name__ == "__main__":
    unittest.main()
