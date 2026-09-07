"""FM-38: Geraet loeschen + Undo darf die Kopf-Matrix-Gruppe nicht auf den
WERKSSTAND zuruecksetzen.

Gemessen am laufenden Code (nicht nachgerechnet): das Geraet wird ueber
``AppState.add_fixture`` gepatcht, die dabei automatisch erzeugte Kopf-Matrix-
Gruppe wird UMBENANNT und ihr RASTER geaendert, dann geht das Geraet ueber
``AppState.remove_fixture`` weg und der ECHTE Undo-Stack macht das rueckgaengig.

Vor dem Fix erzeugte das Undo die Gruppe NEU statt sie wiederherzustellen:
Name, cols, rows, positions_json fielen auf den Werksstand zurueck (``"<Label> ·
Köpfe"``, 1×N) UND die Gruppe bekam eine NEUE id. Die neue id ist bereits der
Schaden: eine RGB-Matrix-Instanz bindet ueber ``s.get(FixtureGroup, gid)``
(``rgb_matrix_view``), die Bindung zeigt danach ins Leere.

★ Der Alltagsfall hat MEHRERE Geraete mit je eigener Kopf-Gruppe, und geloescht
wird eines in der MITTE — nur dann ist die alte id beim Undo nicht mehr "zufaellig
wieder frei" (mit EINEM Geraet in frischer DB kaeme die id 1 auch beim Neuanlegen
heraus und der id-Verlust bliebe unsichtbar).
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from types import SimpleNamespace as NS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.database.models import FixtureGroup, PatchedFixture
from src.core.undo import get_undo_stack
from sqlalchemy.orm import Session
from sqlalchemy import select


FELDER = ("id", "name", "cols", "rows", "positions_json", "folder")


def _rgbw_baenke(n):
    """n RGBW-Baenke auf fortlaufenden Kanaelen (Multi-Head-Erkennung zaehlt color_r)."""
    chans, num = [], 1
    for _h in range(n):
        for attr in ("color_r", "color_g", "color_b", "color_w"):
            chans.append(NS(attribute=attr, channel_number=num, default_value=0))
            num += 1
    return chans


class Fm38Basis(unittest.TestCase):
    """Gemeinsamer echter Weg: Show-DB, Patch, Undo-Stack."""

    KOEPFE = 4

    def setUp(self):
        self._orig_chans = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _rgbw_baenke(self.KOEPFE)
        self.state = A.AppState()
        self.state.open_show(tempfile.mktemp(suffix=".db"))
        self.stack = get_undo_stack()
        self.stack.clear()

    def tearDown(self):
        A.get_channels_for_patched = self._orig_chans
        self.stack.clear()

    # ── Helfer ───────────────────────────────────────────────────────────────

    def _patch(self, fid, label, address, **kw):
        f = PatchedFixture(fid=fid, label=label, fixture_profile_id=1,
                           mode_name="Standard", universe=1, address=address,
                           channel_count=16, fixture_type="moving_head", **kw)
        self.state.add_fixture(f, undoable=True)
        return f

    def _snap(self, gid):
        """Zustand einer Gruppe als dict — oder ``None``, wenn es sie nicht gibt."""
        if gid is None:
            return None
        with Session(self.state._show_engine) as s:
            g = s.get(FixtureGroup, gid)
            if g is None:
                return None
            return {k: getattr(g, k) for k in FELDER}

    def _alle_gruppen(self):
        with Session(self.state._show_engine) as s:
            return [{k: getattr(g, k) for k in FELDER}
                    for g in s.execute(select(FixtureGroup)).scalars().all()]

    def _umbenennen_und_raster_aendern(self, gid, name, cols, rows, positions):
        with Session(self.state._show_engine) as s:
            g = s.get(FixtureGroup, gid)
            g.name = name
            g.cols, g.rows = cols, rows
            g.positions_json = json.dumps(positions)
            s.commit()

    def _drei_geraete_mit_kopfgruppen(self):
        """Alltagsfall: drei Multi-Head-Geraete, angefasst wird das MITTLERE."""
        for fid, label, addr in ((5, "HydraA", 1), (9, "HydraB", 33), (12, "HydraC", 65)):
            self._patch(fid, label, addr)
        gid = self.state.find_head_matrix_group(9, dedicated=True)
        self.assertIsNotNone(gid, "VORBEDINGUNG: Auto-Kopf-Gruppe des mittleren Geraets")
        return gid


class UndoStelltGruppeFeldweiseWiederHer(Fm38Basis):

    def test_alle_felder_und_die_gid_kommen_unveraendert_zurueck(self):
        gid = self._drei_geraete_mit_kopfgruppen()
        self._umbenennen_und_raster_aendern(
            gid, "Bühne Links", 2, 2,
            {"0,0": "9:0", "1,0": "9:1", "0,1": "9:2", "1,1": "9:3"})
        vorher = self._snap(gid)
        # Vorbedingung: die Sonde trifft wirklich eine UMBENANNTE 2x2-Gruppe.
        self.assertEqual(vorher["name"], "Bühne Links")
        self.assertEqual((vorher["cols"], vorher["rows"]), (2, 2))

        self.state.remove_fixture(9, undoable=True)
        # Vorbedingung: das Loeschen hat die Gruppe wirklich mitgenommen.
        self.assertIsNone(self._snap(gid), "VORBEDINGUNG: Gruppe war weg")
        self.assertIsNone(self.state.find_head_matrix_group(9, dedicated=True))

        self.assertTrue(self.stack.undo(), "VORBEDINGUNG: Undo lief")

        nachher = self._snap(gid)
        self.assertIsNotNone(
            nachher, "die Gruppe muss unter IHRER id wieder da sein — an der id "
                     "haengt die Matrix-/VC-Bindung")
        for feld in FELDER:
            self.assertEqual(nachher[feld], vorher[feld],
                             f"Feld {feld} kam nicht unveraendert zurueck")

    def test_die_bindung_ueber_die_gid_trifft_wieder_dieselbe_gruppe(self):
        """Der Weg, den die RGB-Matrix nimmt: ``s.get(FixtureGroup, gid)``."""
        gid = self._drei_geraete_mit_kopfgruppen()
        self._umbenennen_und_raster_aendern(
            gid, "Bühne Links", 2, 2,
            {"0,0": "9:0", "1,0": "9:1", "0,1": "9:2", "1,1": "9:3"})
        self.state.remove_fixture(9, undoable=True)
        self.stack.undo()
        # Genau die Auflösung, die rgb_matrix_view macht.
        with Session(self.state._show_engine) as s:
            gebunden = s.get(FixtureGroup, gid)
            self.assertIsNotNone(gebunden, "Bindung zeigt ins Leere")
            self.assertEqual(gebunden.name, "Bühne Links")
            self.assertEqual((gebunden.cols, gebunden.rows), (2, 2))
        self.assertEqual(self.state.find_head_matrix_group(9, dedicated=True), gid)

    def test_undo_legt_keine_zweite_gruppe_an(self):
        """Wiederherstellen statt Neuanlegen: die Gruppenzahl bleibt gleich."""
        gid = self._drei_geraete_mit_kopfgruppen()
        self._umbenennen_und_raster_aendern(
            gid, "Bühne Links", 2, 2, {"0,0": "9:0", "1,0": "9:1"})
        vor_zahl = len(self._alle_gruppen())
        self.state.remove_fixture(9, undoable=True)
        self.assertEqual(len(self._alle_gruppen()), vor_zahl - 1,
                         "VORBEDINGUNG: genau eine Gruppe ging mit")
        self.stack.undo()
        self.assertEqual(len(self._alle_gruppen()), vor_zahl)
        namen = sorted(g["name"] for g in self._alle_gruppen())
        self.assertNotIn("HydraB · Köpfe", namen,
                         "der Werksname darf NICHT wieder auftauchen")

    def test_undo_meldet_die_gruppen_aenderung(self):
        """Ohne die Meldung sieht die Matrix-/Gruppen-Ansicht die zurueckgeholte
        Gruppe nicht — sie steht dann nur in der DB."""
        gid = self._drei_geraete_mit_kopfgruppen()
        self._umbenennen_und_raster_aendern(
            gid, "Bühne Links", 2, 2, {"0,0": "9:0", "1,0": "9:1"})
        self.state.remove_fixture(9, undoable=True)
        ereignisse = []
        self.state.subscribe(lambda ev, data=None: ereignisse.append(ev))
        try:
            self.stack.undo()
        finally:
            self.state._callbacks.clear()
        self.assertIn("group_changed", ereignisse)

    def test_geraet_kommt_mit_zurueck(self):
        """Die Gruppen-Wiederherstellung darf das Geraet nicht verdraengen."""
        gid = self._drei_geraete_mit_kopfgruppen()
        self._umbenennen_und_raster_aendern(
            gid, "Bühne Links", 2, 2, {"0,0": "9:0", "1,0": "9:1"})
        self.state.remove_fixture(9, undoable=True)
        self.assertNotIn(9, [f.fid for f in self.state.get_patched_fixtures()])
        self.stack.undo()
        zurueck = [f for f in self.state.get_patched_fixtures() if f.fid == 9]
        self.assertEqual(len(zurueck), 1)
        self.assertEqual(zurueck[0].label, "HydraB")

    def test_redo_und_nochmal_undo_bleiben_feldtreu(self):
        """Zweiter Weg auf dieselbe Regel: nach Redo muss das naechste Undo
        wieder die GEPFLEGTE Gruppe liefern, nicht den Werksstand."""
        gid = self._drei_geraete_mit_kopfgruppen()
        self._umbenennen_und_raster_aendern(
            gid, "Bühne Links", 2, 2,
            {"0,0": "9:0", "1,0": "9:1", "0,1": "9:2", "1,1": "9:3"})
        vorher = self._snap(gid)
        self.state.remove_fixture(9, undoable=True)
        self.stack.undo()
        self.assertTrue(self.stack.redo(), "VORBEDINGUNG: Redo lief")
        self.assertIsNone(self._snap(gid), "VORBEDINGUNG: Redo hat wieder geloescht")
        self.assertTrue(self.stack.undo(), "VORBEDINGUNG: zweites Undo lief")
        self.assertEqual(self._snap(gid), vorher)

    def test_zwei_geraete_nacheinander_loeschen_und_zurueckholen(self):
        """Mehrere kaputte Eintraege im Alltag: beide Gruppen kommen feldtreu
        zurueck, jede unter IHRER id."""
        self._drei_geraete_mit_kopfgruppen()
        gid_a = self.state.find_head_matrix_group(5, dedicated=True)
        gid_b = self.state.find_head_matrix_group(9, dedicated=True)
        self._umbenennen_und_raster_aendern(gid_a, "Links", 2, 2, {"0,0": "5:0"})
        self._umbenennen_und_raster_aendern(gid_b, "Rechts", 1, 4, {"0,3": "9:3"})
        vor_a, vor_b = self._snap(gid_a), self._snap(gid_b)
        self.state.remove_fixture(5, undoable=True)
        self.state.remove_fixture(9, undoable=True)
        self.stack.undo()          # holt 9 zurueck
        self.stack.undo()          # holt 5 zurueck
        self.assertEqual(self._snap(gid_a), vor_a)
        self.assertEqual(self._snap(gid_b), vor_b)


class Gegenproben(Fm38Basis):
    """Ein Fix, der "gelingt", indem er andere Faelle veraendert, taugt nichts."""

    def test_geraet_ohne_abhaengige_gruppe_verhaelt_sich_unveraendert(self):
        """★ Kern-Gegenprobe: ein Ein-Kopf-Geraet hat keine Kopf-Gruppe —
        Loeschen + Undo darf nichts an den Gruppen aendern."""
        self._drei_geraete_mit_kopfgruppen()          # Nachbarn, die stehenbleiben
        A.get_channels_for_patched = lambda fx: _rgbw_baenke(1)   # -> kein Multi-Head
        self._patch(77, "Par64", 200)
        self.assertIsNone(self.state.find_head_matrix_group(77, dedicated=True),
                          "VORBEDINGUNG: dieses Geraet hat KEINE Kopf-Gruppe")
        vorher = self._alle_gruppen()

        self.state.remove_fixture(77, undoable=True)
        self.assertEqual(self._alle_gruppen(), vorher,
                         "Loeschen ohne eigene Gruppe darf keine fremde anfassen")
        self.stack.undo()
        self.assertEqual(self._alle_gruppen(), vorher,
                         "Undo ohne eigene Gruppe darf keine Gruppe erzeugen")
        self.assertIn(77, [f.fid for f in self.state.get_patched_fixtures()])

    def test_saubere_nachbargruppen_bleiben_unberuehrt(self):
        """Loeschen + Undo eines Geraets laesst die Gruppen der ANDEREN Geraete
        Feld fuer Feld unveraendert."""
        gid = self._drei_geraete_mit_kopfgruppen()
        gid_a = self.state.find_head_matrix_group(5, dedicated=True)
        gid_c = self.state.find_head_matrix_group(12, dedicated=True)
        self._umbenennen_und_raster_aendern(gid_a, "Links", 2, 2, {"0,0": "5:0"})
        vor_a, vor_c = self._snap(gid_a), self._snap(gid_c)
        self.state.remove_fixture(9, undoable=True)
        self.stack.undo()
        self.assertEqual(self._snap(gid_a), vor_a)
        self.assertEqual(self._snap(gid_c), vor_c)
        self.assertIsNotNone(self._snap(gid))

    def test_zusammengelegte_fremd_matrix_bleibt_stehen(self):
        """Eine vom Nutzer zusammengelegte Matrix (MEHRERE fids) ist nicht die
        dedizierte Auto-Gruppe — sie darf weder mitgeloescht noch dupliziert
        werden."""
        self._drei_geraete_mit_kopfgruppen()
        g5 = self.state.find_head_matrix_group(5, dedicated=True)
        g9 = self.state.find_head_matrix_group(9, dedicated=True)
        merged = self.state.merge_head_matrix_groups([g5, g9], name="Grosse Matrix")
        self.assertIsNotNone(merged, "VORBEDINGUNG: Zusammenlegen hat geklappt")
        vor_merged = self._snap(merged)
        vor_zahl = len(self._alle_gruppen())

        self.state.remove_fixture(9, undoable=True)
        self.assertEqual(self._snap(merged), vor_merged,
                         "die Fremd-Matrix darf beim Loeschen nicht mitgehen")
        self.stack.undo()
        self.assertEqual(self._snap(merged), vor_merged)
        self.assertEqual(len(self._alle_gruppen()), vor_zahl)

    def test_gemischte_gruppe_im_multi_head_ordner_gehoert_nicht_einem_fid(self):
        """★ Diese Sonde erreicht die "dediziert"-Regel wirklich.

        ``test_zusammengelegte_fremd_matrix_bleibt_stehen`` tut das NICHT: die
        zusammengelegte Matrix liegt im Ordner "Matrizen" und wird schon vom
        SQL-Filter ausgesiebt — die Zugehoerigkeits-Regel wird fuer sie nie
        gefragt. Hier liegt die gemischte Gruppe IM Ordner "Multi-Head" (der
        Nutzer hat die Auto-Gruppe um die Koepfe eines zweiten Geraets
        erweitert): nur „AUSSCHLIESSLICH Koepfe dieses fid" haelt sie fest.
        """
        gid = self._drei_geraete_mit_kopfgruppen()
        with Session(self.state._show_engine) as s:
            g = s.get(FixtureGroup, gid)
            g.name = "Bühne Links"
            g.cols, g.rows = 3, 1
            g.positions_json = json.dumps({"0,0": "9:0", "1,0": "9:1",
                                           "2,0": "12:0"})   # FREMDER Kopf dabei
            s.commit()
            # Vorbedingung: gemischt UND im gefilterten Ordner -> die Regel wird
            # fuer diese Gruppe tatsaechlich gefragt.
            self.assertEqual(g.folder, "Multi-Head")
        vorher = self._snap(gid)
        vor_zahl = len(self._alle_gruppen())

        self.state.remove_fixture(9, undoable=True)
        self.assertEqual(self._snap(gid), vorher,
                         "eine Gruppe mit FREMDEN Koepfen ist nicht die dedizierte "
                         "Auto-Gruppe und darf nicht mitgeloescht werden")
        self.stack.undo()
        self.assertEqual(self._snap(gid), vorher)
        self.assertEqual(len(self._alle_gruppen()), vor_zahl,
                         "die bestehende Gruppe adressiert fid 9 kopfweise — das "
                         "Wiederpatchen darf keine zweite Kopf-Gruppe anlegen")

    def test_gruppe_aus_GANZEN_fids_ist_keine_kopfgruppe(self):
        """Zellen ohne Kopfindex ("9" statt "9:0") sind ganze Geraete — auch im
        Ordner "Multi-Head" ist das keine Pro-Kopf-Auto-Gruppe."""
        self._drei_geraete_mit_kopfgruppen()
        with Session(self.state._show_engine) as s:
            g = FixtureGroup(name="Ganze Geraete", cols=1, rows=1,
                             positions_json=json.dumps({"0,0": "9"}),
                             folder="Multi-Head")
            s.add(g)
            s.commit()
            ganz = g.id
        vorher = self._snap(ganz)
        self.state.remove_fixture(9, undoable=True)
        self.assertEqual(self._snap(ganz), vorher,
                         "eine Gruppe aus ganzen fids darf nicht mitgeloescht werden")
        self.stack.undo()
        self.assertEqual(self._snap(ganz), vorher)

    def test_leere_gruppe_gehoert_zu_keinem_fid(self):
        """Ein LEERES Raster adressiert kein Geraet — es gehoert damit auch zu
        keinem. Sonst raeumte das Loeschen IRGENDEINES Geraets jede leergeraeumte
        Multi-Head-Gruppe mit weg."""
        self._drei_geraete_mit_kopfgruppen()
        with Session(self.state._show_engine) as s:
            g = FixtureGroup(name="Leergeraeumt", cols=4, rows=1,
                             positions_json="{}", folder="Multi-Head")
            s.add(g)
            s.commit()
            leer = g.id
        vorher = self._snap(leer)
        self.state.remove_fixture(9, undoable=True)
        self.assertEqual(self._snap(leer), vorher,
                         "die leere Gruppe darf nicht mitgeloescht werden")
        self.stack.undo()
        self.assertEqual(self._snap(leer), vorher)

    def test_head_mode_single_bleibt_ohne_gruppe(self):
        """head_mode "single" unterdrueckt die Auto-Gruppe (FM-HEADLAYOUT) —
        das Undo darf sie nicht durch die Hintertuer anlegen."""
        self._patch(21, "AlsEineLampe", 1, head_mode="single")
        self.assertIsNone(self.state.find_head_matrix_group(21, dedicated=True),
                          "VORBEDINGUNG: single legt keine Kopf-Gruppe an")
        self.state.remove_fixture(21, undoable=True)
        self.stack.undo()
        self.assertIsNone(self.state.find_head_matrix_group(21, dedicated=True))
        self.assertEqual(self._alle_gruppen(), [])


class KaputteEintraegeReissenNichtsMit(Fm38Basis):
    """★ Der Alltagsfall hat mehrere Eintraege, von denen EINER kaputt ist."""

    def _kaputte_multihead_gruppe(self, positions_json):
        with Session(self.state._show_engine) as s:
            g = FixtureGroup(name="Kaputt", cols=1, rows=1,
                             positions_json=positions_json, folder="Multi-Head")
            s.add(g)
            s.commit()
            return g.id

    def test_kaputte_nachbargruppe_blockiert_das_aufraeumen_nicht(self):
        gid = self._drei_geraete_mit_kopfgruppen()
        kaputt = self._kaputte_multihead_gruppe("das ist kein JSON")
        self._umbenennen_und_raster_aendern(
            gid, "Bühne Links", 2, 2, {"0,0": "9:0", "1,0": "9:1"})
        vorher = self._snap(gid)
        vor_kaputt = self._snap(kaputt)

        self.state.remove_fixture(9, undoable=True)
        self.assertIsNone(self._snap(gid),
                          "VORBEDINGUNG: trotz kaputter Nachbarin wurde aufgeraeumt")
        self.assertEqual(self._snap(kaputt), vor_kaputt,
                         "eine unlesbare Gruppe gehoert zu KEINEM fid — schon das "
                         "Loeschen darf sie nicht anfassen (sonst faellt es nur "
                         "nicht auf, weil das Undo sie wieder herholt)")
        self.stack.undo()
        self.assertEqual(self._snap(gid), vorher)
        self.assertEqual(self._snap(kaputt), vor_kaputt,
                         "die kaputte Gruppe bleibt, wie sie war")

    def test_positions_json_als_liste_statt_dict(self):
        """Zweiter Weg an derselben Regel vorbei: syntaktisch gueltiges JSON,
        aber kein Raster-Objekt."""
        gid = self._drei_geraete_mit_kopfgruppen()
        kaputt = self._kaputte_multihead_gruppe("[1, 2, 3]")
        self._umbenennen_und_raster_aendern(
            gid, "Bühne Links", 2, 2, {"0,0": "9:0", "1,0": "9:1"})
        vorher = self._snap(gid)
        vor_kaputt = self._snap(kaputt)
        self.state.remove_fixture(9, undoable=True)
        self.assertIsNone(self._snap(gid), "VORBEDINGUNG: aufgeraeumt")
        self.assertEqual(self._snap(kaputt), vor_kaputt,
                         "kein Raster-Objekt heisst: gehoert zu keinem fid")
        self.stack.undo()
        self.assertEqual(self._snap(gid), vorher)
        self.assertEqual(self._snap(kaputt), vor_kaputt)

    def test_ein_kaputter_schnappschuss_reisst_die_anderen_nicht_mit(self):
        """★ Der Alltagsfall: MEHRERE Schnappschuesse, EINER davon unbrauchbar.

        Direkt auf ``_restore_group_dicts``, weil ein kaputter Schnappschuss
        ueber den Loesch-Weg gar nicht entstehen kann — die Absicherung PRO
        EINTRAG (Savepoint) waere sonst von keiner Sonde beruehrt. Ein zu
        weiter ``try`` (oder ein Rollback ueber alles) laesst hier den GESUNDEN
        Eintrag mit verschwinden.
        """
        self._drei_geraete_mit_kopfgruppen()
        vor_zahl = len(self._alle_gruppen())
        kaputt = {"id": 900, "name": "Kaputt", "cols": object(),   # nicht bindbar
                  "rows": 1, "positions_json": "{}", "folder": "Multi-Head"}
        gesund = {"id": 901, "name": "Gesund", "cols": 2, "rows": 2,
                  "positions_json": json.dumps({"0,0": "9:0"}), "folder": "Multi-Head"}

        n = self.state._restore_group_dicts([kaputt, gesund])
        self.assertEqual(n, 1, "genau der gesunde Eintrag kam durch")
        self.assertIsNone(self._snap(900))
        wieder = self._snap(901)
        self.assertIsNotNone(wieder, "der gesunde Eintrag darf nicht mitgerissen werden")
        self.assertEqual(wieder["name"], "Gesund")
        self.assertEqual((wieder["cols"], wieder["rows"]), (2, 2))
        self.assertEqual(len(self._alle_gruppen()), vor_zahl + 1)

    def test_belegte_id_wird_nicht_ueberschrieben(self):
        """Ist die alte id beim Undo inzwischen anderweitig vergeben, gewinnt
        die FREMDE Gruppe — die Felder kommen trotzdem zurueck."""
        gid = self._drei_geraete_mit_kopfgruppen()
        self._umbenennen_und_raster_aendern(
            gid, "Bühne Links", 2, 2, {"0,0": "9:0", "1,0": "9:1"})
        self.state.remove_fixture(9, undoable=True)
        # Zwischendurch belegt jemand genau diese id.
        with Session(self.state._show_engine) as s:
            fremd = FixtureGroup(id=gid, name="Fremde Gruppe", cols=1, rows=1,
                                 positions_json="{}", folder="Sonstiges")
            s.add(fremd)
            s.commit()
        self.assertEqual(self._snap(gid)["name"], "Fremde Gruppe",
                         "VORBEDINGUNG: die id ist belegt")

        self.stack.undo()
        self.assertEqual(self._snap(gid)["name"], "Fremde Gruppe",
                         "die fremde Gruppe darf NICHT ueberschrieben werden")
        neu = self.state.find_head_matrix_group(9, dedicated=True)
        self.assertIsNotNone(neu, "die Gruppe muss trotzdem zurueckkommen")
        wieder = self._snap(neu)
        self.assertEqual(wieder["name"], "Bühne Links")
        self.assertEqual((wieder["cols"], wieder["rows"]), (2, 2))
        self.assertEqual(json.loads(wieder["positions_json"]),
                         {"0,0": "9:0", "1,0": "9:1"})


if __name__ == "__main__":
    unittest.main()
