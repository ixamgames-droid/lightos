"""LAS-32 (S1), Nachbesserung aus dem Review — vier Punkte, weiter NUR ANZEIGE.

1. Randwinkel haengen am GERAET, nicht an der blossen Nummer: Loeschen nimmt
   sie mit (Rueckgaengig holt sie wieder), und ein anderer Laser auf derselben
   Nummer erbt sie nicht — er ist „nicht pruefbar", nie „erreicht keine Zone".
2. Hauptfenster: gelbe Zeile „Laser gepatcht — keine Sperrzonen angelegt" und
   einmalige Meldung beim Wechsel von einer Show mit Zonen auf eine ohne.
3. Schnellweg „Winkel aus Profil / Datenblatt".
4. Spitze der Feld-Pyramide = Austrittsfenster; die Neigung des Strahlen-
   Schemas im 3D ist benannt und an den Viewer gebunden.
"""
import json
import os
import pathlib
import re
import shutil
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.core.show.show_file as SF
from src.core.database import bibliothek_format as B
from src.core.laser import sperrzonen as S
from src.core.laser import sperrzonen_merker as M
from src.core.laser.sperrzonen import LaserFeld, Sperrzone, SperrzonenDaten
from src.ui.visualizer import sperrzonen_ui as UI

_app = QApplication.instance() or QApplication([])
_REPO = pathlib.Path(__file__).resolve().parent.parent


class _Fx:
    protocol = ""
    mode_name = "9-Kanal"

    def __init__(self, fid, ftype="laser", hersteller="Laserworld",
                 modell="EL-400RGB MK2"):
        self.fid, self.fixture_type = fid, ftype
        self.manufacturer_name, self.fixture_name = hersteller, modell
        self.label = modell


class _State:
    def __init__(self, *patch):
        self.sperrzonen = SperrzonenDaten()
        self._patch = list(patch) or [_Fx(2)]
        self.visualizer_positions = {2: (0.0, 4.0, 0.0)}
        self.visualizer_rotations = {2: (0.0, 180.0, 0.0)}   # strahlt nach -Z
        self.ereignisse = []

    def get_patched_fixtures(self):
        return list(self._patch)

    def _emit(self, event, data=None):
        self.ereignisse.append(event)


def _zone_vorn():
    return Sperrzone(id="z1", name="Publikum", x=0, y=3.0, z=10,
                     breite=4, hoehe=2, tiefe=2)


def _feld(**kw):
    return LaserFeld(links=10, rechts=10, oben=10, unten=10, **kw)


# ── 1. Bindung an das Geraet ────────────────────────────────────────────────

class BindungTest(unittest.TestCase):
    def test_kennung_aus_hersteller_modell_modus(self):
        self.assertEqual(S.geraete_kennung(_Fx(2)), "laserworld|el-400rgb mk2|9-kanal")
        self.assertEqual(S.geraete_kennung(object()), "")

    def test_feld_eines_anderen_geraets_gilt_als_nicht_angegeben(self):
        daten = SperrzonenDaten()
        alt = S.geraete_kennung(_Fx(2))
        daten.setze_feld(2, _feld(geraet=alt))
        self.assertTrue(daten.feld(2, alt).vollstaendig)
        neu = S.geraete_kennung(_Fx(2, modell="Anderer Laser"))
        self.assertFalse(daten.feld(2, neu).vollstaendig)
        # ungebunden (Show aus einem Stand vor der Bindung) passt weiter
        daten.setze_feld(3, _feld())
        self.assertTrue(daten.feld(3, neu).vollstaendig)

    def test_neuer_laser_auf_alter_nummer_meldet_nie_erreicht_keine_zone(self):
        """Der Review-Befund: Laser 2 zeigt von der Zone weg und hat ein Feld
        -> „erreicht keine Zone". Er wird ersetzt; der NEUE Laser auf Nummer 2
        hat nichts eingetragen und darf diese Aussage nicht erben."""
        st = _State()
        st.sperrzonen.zonen.append(_zone_vorn())
        st.sperrzonen.setze_feld(2, _feld(geraet=S.geraete_kennung(st._patch[0])))
        self.assertIn("erreicht keine Zone", UI.hinweis_html(st))
        st._patch = [_Fx(2, modell="Anderer Laser")]
        text = UI.hinweis_html(st)
        self.assertNotIn("erreicht keine Zone", text)
        self.assertIn("Randwinkel fehlen — nicht prüfbar", text)
        self.assertEqual(S.szenen_daten(st)["felder"], [])      # kein Feld im 3D

    def test_bindung_ueberlebt_speichern_und_laden(self):
        daten = SperrzonenDaten()
        daten.setze_feld(2, _feld(geraet="a|b|c"))
        wieder, probleme = S.daten_aus_abschnitt(json.loads(json.dumps(daten.to_dict())))
        self.assertEqual(probleme, [])
        self.assertEqual(wieder.laser_felder[2].geraet, "a|b|c")
        # ein Feld ohne Bindung schreibt den Schluessel gar nicht (Alt-Format)
        self.assertNotIn("geraet", _feld().to_dict())

    def test_dialog_bindet_das_feld_beim_eintragen(self):
        st = _State()
        dlg = UI.SperrzonenDialog(st)
        try:
            dlg._feld_spins[2]["links"].setValue(12.0)
            self.assertEqual(st.sperrzonen.laser_felder[2].geraet,
                             S.geraete_kennung(st._patch[0]))
        finally:
            dlg.deleteLater()


class LoeschenUndRueckgaengigTest(unittest.TestCase):
    """Am echten ``AppState`` (isolierte Test-Datenbank aus conftest)."""

    def setUp(self):
        from src.core.app_state import get_state
        from src.core.undo import get_undo_stack
        self.st = get_state()
        SF.reset_show()
        self.stack = get_undo_stack()
        self.stack.clear()

    def tearDown(self):
        self.stack.clear()
        SF.reset_show()

    def _laser(self, modell="EL-400RGB MK2"):
        from src.core.database.models import PatchedFixture
        return PatchedFixture(
            fid=self.st.next_fid(), label=modell, fixture_profile_id=0,
            mode_name="9-Kanal", universe=1, address=1, channel_count=9,
            manufacturer_name="Laserworld", fixture_name=modell,
            fixture_type="laser")

    def test_loeschen_nimmt_die_randwinkel_mit_und_undo_holt_sie_wieder(self):
        fid = self.st.add_fixture(self._laser(), undoable=False)
        self.st.sperrzonen.setze_feld(fid, _feld(zuschlag=4))
        self.st.remove_fixture(fid)
        self.assertEqual(self.st.sperrzonen.laser_felder, {},
                         "Randwinkel blieben nach dem Loeschen stehen")
        self.assertTrue(self.stack.undo())
        fids = [f.fid for f in self.st.get_patched_fixtures()]
        self.assertEqual(len(fids), 1)
        f = self.st.sperrzonen.feld(fids[0])
        self.assertEqual((f.links, f.rechts, f.oben, f.unten, f.zuschlag),
                         (10.0, 10.0, 10.0, 10.0, 4.0))
        self.assertTrue(self.stack.redo())                      # wieder geloescht
        self.assertEqual(self.st.sperrzonen.laser_felder, {})
        self.assertTrue(self.stack.undo())                      # … und wieder da
        self.assertTrue(self.st.sperrzonen.feld(
            self.st.get_patched_fixtures()[0].fid).vollstaendig)

    def test_neuer_laser_auf_der_freien_nummer_erbt_nichts(self):
        fid = self.st.add_fixture(self._laser(), undoable=False)
        self.st.sperrzonen.setze_feld(fid, _feld())
        self.st.remove_fixture(fid, undoable=False)
        neu = self._laser("Anderer Laser")
        neu.fid = fid
        self.assertEqual(self.st.add_fixture(neu, undoable=False), fid)
        self.assertFalse(self.st.sperrzonen.feld(fid).vollstaendig)

    def test_rueckgaengig_des_patchens_und_wiederholen(self):
        fid = self.st.add_fixture(self._laser())                # mit Undo-Eintrag
        self.st.sperrzonen.setze_feld(fid, _feld())
        self.assertTrue(self.stack.undo())                      # Geraet weg
        self.assertEqual(self.st.sperrzonen.laser_felder, {})
        self.assertTrue(self.stack.redo())                      # Geraet wieder da
        fid2 = self.st.get_patched_fixtures()[0].fid
        self.assertTrue(self.st.sperrzonen.feld(fid2).vollstaendig)


# ── 2. Kopfleiste + Wechselmeldung ──────────────────────────────────────────

class KopfleisteRegelTest(unittest.TestCase):
    def test_regel(self):
        leer, mit = SperrzonenDaten(), SperrzonenDaten(zonen=[_zone_vorn()])
        text = "Laser gepatcht — keine Sperrzonen angelegt"
        self.assertEqual(S.kopfleisten_hinweis(1, leer, True), text)
        self.assertEqual(S.kopfleisten_hinweis(0, leer, True), "")   # kein Laser
        self.assertEqual(S.kopfleisten_hinweis(1, leer, False), "")  # nie benutzt
        self.assertEqual(S.kopfleisten_hinweis(1, mit, True), "")    # Zonen da

    def test_merker_in_eigener_datei_und_fremde_abschnitte_bleiben(self):
        tmp = tempfile.mkdtemp(prefix="las32m_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        pfad = os.path.join(tmp, "ui_prefs.json")
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump({"bpm_settings": {"x": 1}}, f)
        M._vergiss_sitzung()
        self.addCleanup(M._vergiss_sitzung)
        self.assertFalse(M.war_benutzt(pfad))
        M.merke_benutzt(pfad)
        M._vergiss_sitzung()
        self.assertTrue(M.war_benutzt(pfad))
        with open(pfad, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["bpm_settings"], {"x": 1})

    def test_unlesbare_datei_wird_nicht_ueberschrieben(self):
        tmp = tempfile.mkdtemp(prefix="las32m_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        pfad = os.path.join(tmp, "ui_prefs.json")
        with open(pfad, "w", encoding="utf-8") as f:
            f.write("{halb")
        M._vergiss_sitzung()
        self.addCleanup(M._vergiss_sitzung)
        M.merke_benutzt(pfad)
        with open(pfad, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{halb")
        self.assertTrue(M.war_benutzt(pfad))        # fuer diese Sitzung trotzdem


class KopfzeileWidgetTest(unittest.TestCase):
    def _zeile(self, st, benutzt):
        p = mock.patch.object(M, "war_benutzt", return_value=benutzt)
        p.start()
        self.addCleanup(p.stop)
        z = UI.SperrzonenKopfzeile(lambda: st)
        self.addCleanup(z.deleteLater)
        z.aktualisieren()
        return z

    def test_gelb_und_sichtbar_wenn_laser_ohne_zonen(self):
        z = self._zeile(_State(), True)
        self.assertFalse(z.isHidden())
        self.assertEqual(z.text(), "Laser gepatcht — keine Sperrzonen angelegt")
        self.assertIn(UI.GELB, z.styleSheet())
        self.assertIn("NICHT ab", z.toolTip())

    def test_verschwindet_mit_der_ersten_zone_und_kommt_wieder(self):
        st = _State()
        z = self._zeile(st, True)
        st.sperrzonen.zonen.append(_zone_vorn())
        z.aktualisieren()
        self.assertTrue(z.isHidden())
        st.sperrzonen.zonen.clear()
        z.aktualisieren()
        self.assertFalse(z.isHidden())

    def test_nervt_nicht_ohne_laser_oder_ohne_frueheren_gebrauch(self):
        self.assertTrue(self._zeile(_State(_Fx(5, "par")), True).isHidden())
        self.assertTrue(self._zeile(_State(), False).isHidden())

    def test_takt_kostet_ohne_gebrauch_weder_patch_noch_platte(self):
        """Die Zeile wird im Takt des NOT-AUS-Knopfs gefragt (gut zweimal je
        Sekunde, UI-Thread): wer die Funktion nie benutzt hat, loest dabei
        keinen Gang durch den Patch aus, und die Einstellungsdatei wird je
        Sitzung nur einmal gelesen."""
        st = _State()
        st.get_patched_fixtures = mock.Mock(side_effect=AssertionError("Patch gelesen"))
        M._vergiss_sitzung()
        self.addCleanup(M._vergiss_sitzung)
        with mock.patch.object(M, "_pfad", return_value="/gibt/es/nicht.json"), \
                mock.patch.object(M, "_lies", return_value={}) as lies:
            z = UI.SperrzonenKopfzeile(lambda: st)
            self.addCleanup(z.deleteLater)
            for _ in range(5):
                z.aktualisieren()
            self.assertTrue(z.isHidden())
            self.assertEqual(lies.call_count, 1)
            # ... und der Merker wirkt trotzdem sofort
            M._sitzung = True
            st.get_patched_fixtures = lambda: [_Fx(2)]
            z.aktualisieren()
            self.assertFalse(z.isHidden())

    def test_neue_zone_im_dialog_setzt_den_merker(self):
        st = _State()
        with mock.patch.object(M, "merke_benutzt") as merke:
            dlg = UI.SperrzonenDialog(st)
            try:
                dlg._zone_neu()
            finally:
                dlg.deleteLater()
        merke.assert_called()

    def test_hauptfenster_baut_die_zeile_neben_den_notaus(self):
        quelle = (_REPO / "src" / "ui" / "main_window.py").read_text(encoding="utf-8")
        self.assertEqual(quelle.count("self._sperrzonen_kopfzeile_bauen(lay)"), 2,
                         "Kopfleiste UND Kiosk-Streifen")
        self.assertIn("self._sync_sperrzonen_kopfzeile()", quelle)
        self.assertIn("self._sperrzonen_wechsel_melden()", quelle)


class WechselMeldungFarbeTest(unittest.TestCase):
    """Das Gelb der einmaligen Meldung gehoert zu genau dieser Meldung: ersetzt
    eine andere sie oder laeuft sie ab, ist die Statuszeile wieder normal."""

    def setUp(self):
        import types
        from PySide6.QtWidgets import QStatusBar
        from src.ui.main_window import MainWindow
        sb = QStatusBar()
        self.addCleanup(sb.deleteLater)

        class _Fenster:
            _state = types.SimpleNamespace(sperrzonen_wechsel_hinweis=True)
            statusBar = staticmethod(lambda: sb)
            _reset_statusbar_style = MainWindow._reset_statusbar_style
            _sperrzonen_wechsel_melden = MainWindow._sperrzonen_wechsel_melden
            _sperrzonen_meldung_gewechselt = MainWindow._sperrzonen_meldung_gewechselt

        self.sb, self.fenster = sb, _Fenster()

    def test_meldung_ist_gelb_und_wird_einmal_gezeigt(self):
        self.fenster._sperrzonen_wechsel_melden()
        self.assertEqual(self.sb.currentMessage(), S.MELDUNG_SHOW_OHNE_ZONEN)
        self.assertIn("#ffcc00", self.sb.styleSheet())
        self.assertFalse(self.fenster._state.sperrzonen_wechsel_hinweis)

    def test_andere_meldung_nimmt_das_gelb_weg(self):
        self.fenster._sperrzonen_wechsel_melden()
        self.sb.showMessage("Show gespeichert", 5000)
        self.assertEqual(self.sb.styleSheet(), "")

    def test_abgelaufene_meldung_nimmt_das_gelb_weg(self):
        self.fenster._sperrzonen_wechsel_melden()
        self.sb.clearMessage()
        self.assertEqual(self.sb.styleSheet(), "")

    def test_spaetere_farbe_einer_anderen_meldung_bleibt(self):
        """Der NOT-AUS-Alarm zeigt erst seine Meldung und faerbt dann rot —
        dieses Rot darf hier nicht wieder weggenommen werden."""
        self.fenster._sperrzonen_wechsel_melden()
        self.sb.showMessage("LASER NOT-AUS", 6000)
        self.sb.setStyleSheet("QStatusBar{background:#b31414;}")
        self.sb.showMessage("noch eine Meldung", 1000)
        self.assertIn("#b31414", self.sb.styleSheet())


class WechselMeldungTest(unittest.TestCase):
    """Echtes ``save_show``/``load_show``: Show A hat Zonen, Show B keine."""

    def setUp(self):
        from src.core.app_state import get_state
        self.st = get_state()
        SF.reset_show()
        self.tmp = tempfile.mkdtemp(prefix="las32w_")
        p = mock.patch.object(M, "merke_benutzt")
        self.merke = p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        SF.reset_show()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _speichere(self, name, *, laser, zonen):
        from src.core.database.models import PatchedFixture
        SF.reset_show()
        if laser:
            self.st.add_fixture(PatchedFixture(
                fid=1, label="L", fixture_profile_id=0, mode_name="9-Kanal",
                universe=1, address=1, channel_count=9,
                manufacturer_name="Laserworld", fixture_name="EL-400RGB MK2",
                fixture_type="laser"), undoable=False)
        if zonen:
            self.st.sperrzonen.zonen.append(_zone_vorn())
        pfad = os.path.join(self.tmp, name)
        SF.save_show(pfad)
        return pfad

    def test_wechsel_auf_show_ohne_zonen_meldet_genau_einmal(self):
        mit = self._speichere("mit.lshow", laser=True, zonen=True)
        ohne = self._speichere("ohne.lshow", laser=True, zonen=False)
        self.assertTrue(SF.load_show(mit)[0])
        self.assertTrue(S.dmx_laser(self.st), "Laser ging beim Laden verloren")
        self.assertFalse(self.st.sperrzonen_wechsel_hinweis)
        self.merke.assert_called()                 # Show mit Zonen = benutzt
        self.assertTrue(SF.load_show(ohne)[0])
        self.assertTrue(self.st.sperrzonen_wechsel_hinweis)
        self.assertTrue(SF.load_show(ohne)[0])     # ohne -> ohne: nichts Neues
        self.assertFalse(self.st.sperrzonen_wechsel_hinweis)

    def test_keine_meldung_ohne_laser(self):
        mit = self._speichere("mit.lshow", laser=True, zonen=True)
        ohne = self._speichere("leer.lshow", laser=False, zonen=False)
        self.assertTrue(SF.load_show(mit)[0])
        self.assertTrue(SF.load_show(ohne)[0])
        self.assertFalse(self.st.sperrzonen_wechsel_hinweis)


# ── 3. Winkel aus Profil / Datenblatt ───────────────────────────────────────

_PROFIL = {
    "format_version": 1, "hersteller": "Testlaser", "modell": "TL 1",
    "kurzname": "TL1", "typ": "laser",
    "quelle": {"titel": "Handbuch", "version": "1", "datum": "2026-01-01", "url": ""},
    "herkunft": {"art": "hersteller-handbuch", "lizenz": "eigen"},
    "autor": "LightOS", "geprueft": {"ok": True, "wie": "Test"},
    "modi": [{"name": "1-Kanal", "kanaele": [
        {"name": "Betriebsart", "attribut": "shutter", "default": 0, "highlight": 0}]}],
}


class DatenblattTest(unittest.TestCase):
    def test_gesamtwinkel_wird_je_zur_haelfte_verteilt(self):
        f = S.feld_aus_gesamtwinkel(40, 30)
        self.assertEqual((f.links, f.rechts, f.oben, f.unten), (20.0, 20.0, 15.0, 15.0))
        self.assertIsNone(S.feld_aus_gesamtwinkel(0, 30))
        self.assertIsNone(S.feld_aus_gesamtwinkel("viel", 30))

    def test_profilformat_kennt_den_winkel_und_prueft_ihn(self):
        gut = dict(_PROFIL, laser_abstrahlwinkel=[60, 40])
        self.assertEqual(B.pruefe(gut), [])
        self.assertEqual(B.pruefe(dict(_PROFIL, laser_abstrahlwinkel=45)), [])
        for schlecht in (0, -5, 400, "40", [40], [40, 30, 20], True):
            self.assertTrue(B.pruefe(dict(_PROFIL, laser_abstrahlwinkel=schlecht)),
                            schlecht)
        self.assertTrue(B.pruefe(dict(_PROFIL, typ="par", laser_abstrahlwinkel=40)))
        self.assertEqual(B.pruefe(dict(_PROFIL, laser_randwinkel={
            "links": 5, "rechts": 25, "oben": 3, "unten": 30})), [])
        self.assertTrue(B.pruefe(dict(_PROFIL, laser_randwinkel={"links": 5})))

    def test_winkel_aus_der_bibliotheksdatei(self):
        tmp = tempfile.mkdtemp(prefix="las32b_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        pfad = os.path.join(tmp, B.dateiname("Testlaser", "TL 1"))
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        B.schreibe(dict(_PROFIL, laser_abstrahlwinkel=[60, 40]), pfad)
        f = S.winkel_aus_bibliothek("Testlaser", "TL 1", tmp)
        self.assertEqual((f.links, f.rechts, f.oben, f.unten), (30.0, 30.0, 20.0, 20.0))
        self.assertIsNone(S.winkel_aus_bibliothek("Testlaser", "Gibt es nicht", tmp))
        self.assertIsNone(S.winkel_aus_bibliothek("", "", tmp))

    def test_el400_traegt_keinen_winkel_solange_keiner_belegt_ist(self):
        """Nicht raten: weder die Profil-Notizen noch die dort ausgewerteten
        Handbuch-Abschnitte nennen einen Abstrahlwinkel. Wer einen eintraegt,
        muss ihn in den Notizen belegen (Wort „Abstrahlwinkel"/„Scanwinkel")."""
        pfad = _REPO / "fixtures" / "bibliothek" / "laserworld" / "el-400rgb-mk2.json"
        daten = json.loads(pfad.read_text(encoding="utf-8"))
        hat = "laser_abstrahlwinkel" in daten or "laser_randwinkel" in daten
        belegt = bool(re.search(r"abstrahlwinkel|scanwinkel|scan angle",
                                daten.get("notizen", ""), re.I))
        self.assertEqual(hat, belegt)
        if not hat:
            self.assertIsNone(S.winkel_aus_bibliothek("Laserworld", "EL-400RGB MK2"))


class DatenblattKnopfTest(unittest.TestCase):
    def setUp(self):
        self.st = _State()
        self.dlg = UI.SperrzonenDialog(self.st)
        self.addCleanup(self.dlg.deleteLater)

    def _werte(self):
        f = self.st.sperrzonen.feld(2)
        return (f.links, f.rechts, f.oben, f.unten)

    def test_knopf_ist_da(self):
        self.assertEqual(self.dlg._btn_datenblatt.text(),
                         "Winkel aus Profil / Datenblatt")
        self.assertTrue(self.dlg._btn_datenblatt.isEnabled())

    def test_profil_mit_winkel_fuellt_ohne_rueckfrage(self):
        feld = LaserFeld(links=30, rechts=30, oben=20, unten=20)
        with mock.patch.object(S, "winkel_aus_bibliothek", return_value=feld) as wb, \
                mock.patch.object(self.dlg, "_frage_gesamtwinkel",
                                  side_effect=AssertionError("unerwartete Frage")):
            self.dlg._btn_datenblatt.click()
        wb.assert_called_once_with("Laserworld", "EL-400RGB MK2")
        self.assertEqual(self._werte(), (30.0, 30.0, 20.0, 20.0))
        self.assertEqual(self.dlg._feld_spins[2]["oben"].value(), 20.0)
        self.assertIn("Geräteprofil", self.dlg._datenblatt_info.text())
        self.assertIn("sperrzonen_changed", self.st.ereignisse)

    def test_profil_ohne_winkel_fragt_nach_dem_gesamtwinkel(self):
        with mock.patch.object(S, "winkel_aus_bibliothek", return_value=None), \
                mock.patch.object(self.dlg, "_frage_gesamtwinkel",
                                  return_value=(40.0, 30.0)) as frage:
            self.dlg._btn_datenblatt.click()
        frage.assert_called_once()
        self.assertEqual(self._werte(), (20.0, 20.0, 15.0, 15.0))
        self.assertIn("Datenblatt 40° × 30°", self.dlg._datenblatt_info.text())
        self.assertIn("Kein Messwert", self.dlg._datenblatt_info.text())

    def test_abbrechen_aendert_nichts_und_zuschlag_bleibt(self):
        self.dlg._feld_spins[2]["zuschlag"].setValue(8.0)
        with mock.patch.object(S, "winkel_aus_bibliothek", return_value=None), \
                mock.patch.object(self.dlg, "_frage_gesamtwinkel", return_value=None):
            self.dlg._btn_datenblatt.click()
        self.assertEqual(self._werte(), (None, None, None, None))
        with mock.patch.object(S, "winkel_aus_bibliothek", return_value=None), \
                mock.patch.object(self.dlg, "_frage_gesamtwinkel",
                                  return_value=(20.0, 20.0)):
            self.dlg._btn_datenblatt.click()
        self.assertEqual(self.st.sperrzonen.feld(2).zuschlag, 8.0)

    def test_eingabe_dialog_hat_beide_felder(self):
        d = UI._GesamtwinkelDialog("EL-400", self.dlg)
        self.addCleanup(d.deleteLater)
        self.assertEqual(d.waagerecht.suffix().strip(), "°")
        self.assertGreaterEqual(d.senkrecht.maximum(), 160.0)


# ── 4. Spitze im Austrittsfenster, Achse des Strahlen-Schemas ───────────────

class SpitzeTest(unittest.TestCase):
    def test_fenster_liegt_vorn_auf_der_strahlachse(self):
        self.assertEqual(S.feld_spitze((1.0, 2.0, 3.0), (0, 0, 0)),
                         (1.0, 2.0, 3.0 + S.AUSTRITT_VORN_M))
        s = S.feld_spitze((0.0, 4.0, 0.0), (0.0, 90.0, 0.0))     # strahlt nach +X
        self.assertAlmostEqual(s[0], S.AUSTRITT_VORN_M, places=6)
        self.assertAlmostEqual(s[2], 0.0, places=6)

    def test_dieselbe_zahl_wie_das_3d_modell(self):
        js = (_REPO / "src" / "ui" / "visualizer" / "scene_src" / "fixtures"
              / "builders.js").read_text(encoding="utf-8")
        m = re.search(r"buildLaserRig\(group,\s*([0-9.]+)\)", js)
        self.assertIsNotNone(m)
        self.assertEqual(float(m.group(1)), S.AUSTRITT_VORN_M)

    def test_befund_rechnet_ab_fenster_nicht_ab_geraetemitte(self):
        """Eine Zonenkante, die nur von der Geraetemitte aus im Feld laege:
        20+5 Grad, Zonen-Hinterkante 10,125 m voraus — ab Mitte reicht das
        Feld dort 4,721 m zur Seite, ab Fenster 4,680 m."""
        feld = LaserFeld(links=20, rechts=20, oben=20, unten=20, zuschlag=5)
        pos, rot = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        zone = Sperrzone(id="z", name="Rand", x=4.70 + 0.1 + 0.5, y=-0.5, z=10.0,
                         breite=1.0, hoehe=1.0, tiefe=0.05)
        # Innenkante der Zone (mit 10 cm Rand) bei x = 4,70, z = 9,875 … 10,125
        self.assertTrue(S.kann_erreichen(pos, rot, feld, zone),
                        "Probe taugt nicht: ab Geraetemitte muss sie treffen")
        self.assertFalse(S.kann_erreichen(S.feld_spitze(pos, rot), rot, feld, zone))
        self.assertEqual(S.pruefe_laser(1, "L", pos, rot, feld, [zone]).status,
                         S.STATUS_FREI)

    def test_geraet_in_der_zone_gilt_weiter_als_erreicht(self):
        """Mitte in der Zone, Fenster schaut gerade heraus und zeigt weg."""
        feld = _feld()
        zone = Sperrzone(id="z", name="Eng", x=0.0, y=3.9, z=-0.11,
                         breite=1.0, hoehe=0.2, tiefe=0.1)
        b = S.pruefe_laser(1, "L", (0.0, 4.0, 0.0), (0, 0, 0), feld, [zone])
        self.assertEqual(b.status, S.STATUS_ERREICHT)

    def test_neigung_des_strahlen_schemas_ist_an_den_viewer_gebunden(self):
        js = (_REPO / "src" / "ui" / "visualizer" / "scene_src" / "fixtures"
              / "laser.js").read_text(encoding="utf-8")
        m = re.search(r"const LASER_PITCH = ([0-9.]+);", js)
        self.assertIsNotNone(m)
        import math
        self.assertAlmostEqual(math.degrees(float(m.group(1))),
                               S.STRAHLBILD_NEIGUNG_GRAD, places=9)
        # Der Unterschied der beiden Achsen liegt im Standard-Zuschlag.
        self.assertLess(S.STRAHLBILD_NEIGUNG_GRAD, S.ZUSCHLAG_STANDARD)

    def test_anleitung_nennt_fenster_und_achsunterschied(self):
        text = " ".join((_REPO / "docs" / "anleitung_laser" / "ANLEITUNG_LASER.md")
                        .read_text(encoding="utf-8").split())
        self.assertIn("Austrittsfenster", text)
        self.assertIn("rund 3,4°", text)
        self.assertIn("Winkel aus Profil / Datenblatt", text)
        self.assertIn(S.KOPFLEISTE_KEINE_ZONEN, text)


if __name__ == "__main__":
    unittest.main()
