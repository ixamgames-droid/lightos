"""VCB-42: das Ziel einer Blackout-Taste meint EINE Gruppe — nicht „wer gerade
diese Nummer hat“.

Folge aus dem Review von VCB-36 (#1025). Seit VCB-36 merkt die Taste ihr Ziel
als Gruppen-ID. Zwei Wege fuehrten damit zur FALSCHEN Gruppe:

* **Die Nummer wird wiederverwendet.** SQLite vergibt die hoechste Nummer neu:
  letzte Gruppe loeschen, neue anlegen — die neue Gruppe bekam dieselbe ID und
  erbte das Ziel der Taste.
* **Nummern gelten nur in EINER Show.** „VC Layout speichern/laden“ traegt die
  Tasten in eine andere Show; dort gehoert dieselbe Nummer einer anderen Gruppe.

Deshalb traegt jede Gruppe eine **Kennung** (bleibt beim Umbenennen und
Verschieben, eine neu angelegte Gruppe bekommt eine neue), und die Taste merkt
je ID einen **Steckbrief**: Kennung, Name, Ordner. Ein Ziel gilt nur, wenn die
Gruppe mit dieser ID dieselbe Kennung traegt — oder, falls nicht, denselben
Namen im selben Ordner hat. Sonst ist es **verloren**: die Taste schaltet
nichts, zeigt es an und wird nie zum globalen Blackout.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication             # noqa: E402
from sqlalchemy import create_engine, delete, select, text   # noqa: E402
from sqlalchemy.orm import Session                      # noqa: E402

from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15
import src.core.app_state as A                          # noqa: E402
from src.core import group_ref                          # noqa: E402
from src.core.app_state import get_state                # noqa: E402
from src.core.database.models import (                  # noqa: E402
    FixtureGroup, PatchedFixture, create_all_idempotent, migrate_show_db)
from src.core.show import show_file as SF               # noqa: E402
from src.core.undo import get_undo_stack                # noqa: E402
from src.ui.virtualconsole import target_list_editor as tle   # noqa: E402
from src.ui.virtualconsole.vc_button import ButtonAction, VCButton   # noqa: E402

_app = QApplication.instance() or QApplication([])

_BASIS = {"cols": 1, "rows": 1, "positions_json": "{}", "folder": ""}


def _gruppen_leeren(state):
    with state._session() as s:
        s.execute(delete(FixtureGroup))
        s.commit()


def _gruppe(state, name, folder, fids, gid=None) -> int:
    pos = {f"{i},0": fid for i, fid in enumerate(fids)}
    with state._session() as s:
        g = FixtureGroup(name=name, folder=folder, cols=max(1, len(fids)), rows=1,
                         positions_json=json.dumps(pos))
        if gid is not None:
            g.id = gid
        s.add(g)
        s.commit()
        return int(g.id)


def _loeschen(state, gid):
    # Wie die Gruppen-Ansicht: eine Loesch-Anweisung, kein ORM-Objekt.
    with state._session() as s:
        s.execute(delete(FixtureGroup).where(FixtureGroup.id == gid))
        s.commit()


def _aendern(state, gid, **felder):
    with state._session() as s:
        g = s.get(FixtureGroup, gid)
        for k, v in felder.items():
            setattr(g, k, v)
        s.commit()


def _uids(state) -> dict:
    with state._session() as s:
        return {int(g.id): g.uid for g in s.execute(select(FixtureGroup)).scalars()}


def _alte_version_hat_ziel(d: dict) -> bool:
    """Der Ladepfad VOR VCB-36: er kennt nur ``blackout_fids``/``blackout_groups``."""
    roh = d.get("blackout_groups", None)
    return bool(d.get("blackout_fids") or [g for g in (roh or []) if isinstance(g, str) and g.strip()])


class _MitState(unittest.TestCase):

    def setUp(self):
        self.state = get_state()
        _gruppen_leeren(self.state)
        self.addCleanup(_gruppen_leeren, self.state)
        self.addCleanup(self.state.clear_all_target_blackouts)
        self.addCleanup(destroy_all_top_level_widgets, QApplication.instance())

    def _taste(self, *gids):
        """Eine Blackout-Taste; ``gids`` werden gewaehlt wie im Dialog."""
        b = VCButton("BO")
        b.action = ButtonAction.BLACKOUT
        if gids:
            b.blackout_gruppen_waehlen(list(gids))
        return b

    def _ziele(self, b) -> set:
        slot = object()
        self.state.set_target_blackout(slot, b.blackout_fids, b._blackout_gruppen_ziele())
        return self.state._target_blackout_fids(self.state._ziel_blackout_specs[slot])

    def _nummer_neu_vergeben(self, gid, name="Neu", folder="", fids=(31,)) -> int:
        """Gruppe ``gid`` loeschen und eine neue anlegen, die DIESELBE Nummer
        bekommt (SQLite vergibt die hoechste neu) — der Weg aus dem Review."""
        _loeschen(self.state, gid)
        neu = _gruppe(self.state, name, folder, list(fids))
        self.assertEqual(neu, gid, "VORBEDINGUNG: die Nummer wird wiederverwendet")
        return neu


# ── Die Regel selbst ─────────────────────────────────────────────────────────

class RegelTest(unittest.TestCase):

    def test_dieselbe_kennung_gilt_auch_nach_umbenennen_und_verschieben(self):
        self.assertTrue(group_ref.ziel_gilt(("PARs", "Front", "k1"), ("Hinten", "Back", "k1")))

    def test_andere_kennung_und_anderer_name_ist_verloren(self):
        self.assertFalse(group_ref.ziel_gilt(("PARs", "Front", "k1"), ("Neu", "Front", "k2")))
        self.assertFalse(group_ref.ziel_gilt(("PARs", "Front", "k1"), ("PARs", "Back", "k2")))

    def test_andere_kennung_ist_eine_andere_gruppe_auch_bei_gleichem_namen(self):
        """VCB-44: tragen beide Seiten eine Kennung, entscheidet nur sie —
        geloescht und gleichnamig neu angelegt ist eine NEUE Gruppe."""
        self.assertFalse(group_ref.ziel_gilt(("PARs", "Front", "k1"), ("PARs", "Front", "k2")))

    def test_ohne_kennung_auf_einer_seite_gilt_name_und_ordner(self):
        """Ein Ziel aus einem Layout der Zeit vor den Kennungen."""
        self.assertTrue(group_ref.ziel_gilt(("PARs", "", ""), ("PARs", "", "k2")))
        self.assertTrue(group_ref.ziel_gilt(("PARs", "Front", "k1"), ("PARs", "Front", "")))
        self.assertFalse(group_ref.ziel_gilt(("PARs", "", ""), ("PARs", "Back", "k2")))

    def test_keine_gruppe_mit_dieser_nummer_ist_verloren(self):
        self.assertFalse(group_ref.ziel_gilt(("PARs", "", "k1"), None))
        self.assertFalse(group_ref.ziel_gilt(None, None))

    def test_ohne_steckbrief_gilt_die_nummer(self):
        """Layout aus der Zeit vor VCB-42: mehr als die Nummer steht nicht da."""
        self.assertTrue(group_ref.ziel_gilt(None, ("Egal", "", "k9")))

    def test_leere_kennungen_sind_keine_uebereinstimmung(self):
        self.assertFalse(group_ref.ziel_gilt(("PARs", "", ""), ("Neu", "", "")))

    def test_leerer_name_ist_kein_beleg(self):
        """Zwei namenlose Gruppen sind nicht „dieselbe“ — nur die Kennung zaehlt."""
        self.assertFalse(group_ref.ziel_gilt(("", "", "k1"), ("", "", "k2")))
        self.assertTrue(group_ref.ziel_gilt(("", "", "k1"), ("", "", "k1")))

    def test_unbekannter_name_passt_auf_keine_gruppe(self):
        """Steckbrief einer Gruppe, die es beim Uebernehmen schon nicht mehr gab."""
        self.assertFalse(group_ref.ziel_gilt((None, "", ""), ("", "", "k2")))
        self.assertFalse(group_ref.ziel_gilt((None, "", ""), ("Neu", "", "")))

    def test_kennungen_sind_verschieden_und_lesbar(self):
        a, b = group_ref.neue_uid(), group_ref.neue_uid()
        self.assertNotEqual(a, b)
        self.assertEqual(group_ref.uid_lesbar(a), a)
        for kaputt in (None, 5, "", "  ", "x" * 200, "mit leer", ["a"], True):
            self.assertEqual(group_ref.uid_lesbar(kaputt), "", kaputt)


# ── (a) Die Nummer einer geloeschten Gruppe wird wiederverwendet ────────────

class WiederverwendeteNummerTest(_MitState):

    def setUp(self):
        super().setUp()
        self.front = _gruppe(self.state, "PARs", "Front", [11, 12])
        self.back = _gruppe(self.state, "PARs", "Back", [21, 22])

    def test_neue_gruppe_auf_der_alten_nummer_erbt_das_ziel_nicht(self):
        b = self._taste(self.back)
        self.assertEqual(self._ziele(b), {21, 22}, "VORBEDINGUNG")
        self._nummer_neu_vergeben(self.back)
        self.assertEqual(self._ziele(b), set())

    def test_verlorenes_ziel_ist_kein_globaler_blackout(self):
        b = self._taste(self.back)
        self._nummer_neu_vergeben(self.back)
        self.assertTrue(b.has_blackout_target())
        with mock.patch.object(type(self.state), "set_target_blackout") as ziel, \
                mock.patch.object(self.state.output_manager, "set_blackout") as glob:
            b._trigger_primary(True)
        self.assertEqual(ziel.call_count, 1)
        self.assertEqual(glob.call_count, 0)

    def test_auch_eine_gehaltene_taste_folgt_nicht_der_neuen_gruppe(self):
        b = self._taste(self.back)
        slot = object()
        self.state.set_target_blackout(slot, [], b._blackout_gruppen_ziele())
        spec = lambda: self.state._ziel_blackout_specs[slot]            # noqa: E731
        self.assertEqual(self.state._target_blackout_fids(spec()), {21, 22})
        self._nummer_neu_vergeben(self.back)
        self.state.notify_groups_changed()
        self.assertEqual(self.state._target_blackout_fids(spec()), set())

    def test_umbenennen_und_verschieben_halten_das_ziel(self):
        b = self._taste(self.back)
        _aendern(self.state, self.back, name="Hinten", folder="Buehne/Hinten")
        self.assertEqual(self._ziele(b), {21, 22})
        self.assertEqual(b._blackout_ziele_verloren(), [])

    def test_gehaltene_taste_folgt_der_umbenannten_gruppe(self):
        b = self._taste(self.back)
        slot = object()
        self.state.set_target_blackout(slot, [], b._blackout_gruppen_ziele())
        _aendern(self.state, self.back, name="Hinten", positions_json=json.dumps({"0,0": 23}))
        self.state.notify_groups_changed()
        self.assertEqual(
            self.state._target_blackout_fids(self.state._ziel_blackout_specs[slot]), {23})

    def test_geloescht_und_gleichnamig_neu_angelegt_erbt_das_ziel_nicht(self):
        """VCB-44, der Befund aus QA-96: die neue Gruppe heisst wie die alte und
        liegt im selben Ordner — sie ist trotzdem eine andere (neue Kennung).
        Bis VCB-44 galt sie hier als dieselbe und uebernahm das Ziel."""
        b = self._taste(self.back)
        self._nummer_neu_vergeben(self.back, name="PARs", folder="Back", fids=(41,))
        self.assertEqual(self._ziele(b), set())
        self.assertEqual(len(b._blackout_ziele_verloren()), 1)
        self.assertTrue(b.has_blackout_target(), "verloren ist kein globaler Blackout")

    def test_gleicher_name_in_anderem_ordner_ist_eine_andere_gruppe(self):
        b = self._taste(self.back)
        self._nummer_neu_vergeben(self.back, name="PARs", folder="Seite", fids=(41,))
        self.assertEqual(self._ziele(b), set())

    def test_umbenannt_dann_geloescht_der_alte_name_holt_das_ziel_nicht_zurueck(self):
        """Der Steckbrief zieht nach: nach dem Umbenennen ist „PARs/Back“ nicht
        mehr der Name des Ziels — eine neue Gruppe dieses Namens erbt nichts."""
        b = self._taste(self.back)
        _aendern(self.state, self.back, name="Hinten")
        self.assertEqual(self._ziele(b), {21, 22})          # Druck zieht nach
        self._nummer_neu_vergeben(self.back, name="PARs", folder="Back", fids=(41,))
        self.assertEqual(self._ziele(b), set())

    def test_die_andere_gruppe_bleibt_ein_ziel(self):
        b = self._taste(self.front, self.back)
        self._nummer_neu_vergeben(self.back)
        self.assertEqual(self._ziele(b), {11, 12})
        self.assertEqual(len(b._blackout_ziele_verloren()), 1)

    def test_aeltere_versionen_bekommen_nicht_den_namen_der_fremden_gruppe(self):
        """``blackout_groups`` ist das Feld fuer Versionen, die nur Namen kennen.
        Stuende dort „Neu“, schaltete eine aeltere Version die FREMDE Gruppe."""
        b = self._taste(self.back)
        self._nummer_neu_vergeben(self.back)
        d = json.loads(json.dumps(b.to_dict()))
        self.assertNotIn("Neu", d["blackout_groups"])
        self.assertTrue(_alte_version_hat_ziel(d), d["blackout_groups"])
        for name in d["blackout_groups"]:
            self.assertEqual(self.state.group_cells_by_name(name), [], name)


# ── (b) Nummern gelten nur innerhalb EINER Show ──────────────────────────────

class AndereShowTest(_MitState):

    def _layout_aus_show_eins(self) -> dict:
        _gruppe(self.state, "PARs", "Front", [11, 12])
        back = _gruppe(self.state, "PARs", "Back", [21, 22])
        return json.loads(json.dumps(self._taste(back).to_dict()))

    def test_layout_in_anderer_show_trifft_nicht_die_gruppe_mit_derselben_nummer(self):
        d = self._layout_aus_show_eins()
        _gruppen_leeren(self.state)
        _gruppe(self.state, "Truss", "", [51])
        _gruppe(self.state, "Floor", "", [61, 62])          # dieselbe Nummer wie „Back“
        neu = self._taste()
        neu.apply_dict(d)
        self.assertEqual(self._ziele(neu), set())
        self.assertTrue(neu.has_blackout_target())
        self.assertEqual(len(neu._blackout_ziele_verloren()), 1)
        self.assertIn("PARs", neu._blackout_ziele_verloren()[0])

    def test_layout_in_show_ohne_gruppen(self):
        d = self._layout_aus_show_eins()
        _gruppen_leeren(self.state)
        neu = self._taste()
        neu.apply_dict(d)
        self.assertEqual(self._ziele(neu), set())
        self.assertTrue(neu.has_blackout_target())

    def test_getrennt_angelegte_gruppe_gleichen_namens_ist_eine_andere(self):
        """VCB-44: dieselbe Buehne in zwei Show-Dateien, GETRENNT angelegt — die
        Gruppen tragen verschiedene Kennungen. Das Layout trifft dort nichts und
        sagt es; der Bediener waehlt das Ziel neu. (Eine KOPIE der Show behaelt
        die Kennungen, dort gilt das Ziel weiter.)"""
        d = self._layout_aus_show_eins()
        _gruppen_leeren(self.state)
        _gruppe(self.state, "PARs", "Front", [71])
        _gruppe(self.state, "PARs", "Back", [81, 82])
        neu = self._taste()
        neu.apply_dict(d)
        self.assertEqual(self._ziele(neu), set())
        self.assertEqual(len(neu._blackout_ziele_verloren()), 1)

    def test_kopie_der_show_mit_denselben_kennungen_gilt(self):
        d = self._layout_aus_show_eins()
        kennungen = _uids(self.state)
        _gruppen_leeren(self.state)
        front = _gruppe(self.state, "PARs", "Front", [71])
        back = _gruppe(self.state, "PARs", "Back", [81, 82])
        alt = sorted(kennungen)
        _aendern(self.state, front, uid=kennungen[alt[0]])
        _aendern(self.state, back, uid=kennungen[alt[1]])
        neu = self._taste()
        neu.apply_dict(d)
        self.assertEqual(self._ziele(neu), {81, 82})

    def test_verlorenes_ziel_ueberlebt_speichern_und_laden(self):
        """Verloren heisst nicht vergessen: der Steckbrief bleibt in der Datei —
        zurueck in der ersten Show wirkt die Taste wieder."""
        d = self._layout_aus_show_eins()
        eins = _uids(self.state)
        _gruppen_leeren(self.state)
        _gruppe(self.state, "Truss", "", [51])
        _gruppe(self.state, "Floor", "", [61, 62])
        fremd = self._taste()
        fremd.apply_dict(d)
        self.assertEqual(self._ziele(fremd), set())
        d2 = json.loads(json.dumps(fremd.to_dict()))
        self.assertEqual(d2["blackout_group_refs"], d["blackout_group_refs"])
        # zurueck in Show eins (dieselben Gruppen, dieselben Kennungen)
        _gruppen_leeren(self.state)
        SF._restore_fixture_groups(self.state, [
            dict(_BASIS, id=1, uid=eins[1], name="PARs", folder="Front"),
            dict(_BASIS, id=2, uid=eins[2], name="Hinten", folder="Back",
                 positions_json=json.dumps({"0,0": 21}))])
        wieder = self._taste()
        wieder.apply_dict(d2)
        self.assertEqual(self._ziele(wieder), {21})

    def test_ueber_echte_show_dateien(self):
        tmp = tempfile.mkdtemp()
        _gruppe(self.state, "PARs", "Front", [11, 12])
        back = _gruppe(self.state, "PARs", "Back", [21, 22])
        layout = json.loads(json.dumps(self._taste(back).to_dict()))
        eins = os.path.join(tmp, "eins.lshow")
        SF.save_show(eins)
        _gruppen_leeren(self.state)
        _gruppe(self.state, "Truss", "", [51])
        _gruppe(self.state, "Floor", "", [61, 62])
        zwei = os.path.join(tmp, "zwei.lshow")
        SF.save_show(zwei)

        self.assertTrue(SF.load_show(zwei)[0])
        b = self._taste()
        b.apply_dict(layout)
        self.assertEqual(self._ziele(b), set(), "fremde Show: Ziel verloren")

        self.assertTrue(SF.load_show(eins)[0])
        b = self._taste()
        b.apply_dict(layout)
        self.assertEqual(self._ziele(b), {21, 22}, "eigene Show: Ziel da")


# ── Show-Datei und Show-DB tragen die Kennung ───────────────────────────────

class ShowDateiTest(_MitState):

    def test_neue_gruppe_bekommt_von_selbst_eine_kennung(self):
        a = _gruppe(self.state, "A", "", [1])
        b = _gruppe(self.state, "B", "", [2])
        u = _uids(self.state)
        self.assertTrue(u[a] and u[b])
        self.assertNotEqual(u[a], u[b])

    def test_die_show_datei_traegt_die_kennung(self):
        gid = _gruppe(self.state, "A", "", [1])
        eintrag = SF._collect_fixture_groups(self.state)[0]
        self.assertEqual(eintrag["uid"], _uids(self.state)[gid])

    def test_kennung_ueberlebt_speichern_und_laden(self):
        _gruppe(self.state, "A", "", [1])
        _gruppe(self.state, "B", "", [2])
        vorher = _uids(self.state)
        daten = json.loads(json.dumps(SF._collect_fixture_groups(self.state)))
        _gruppen_leeren(self.state)
        _gruppe(self.state, "Stoerer", "", [9])
        SF._restore_fixture_groups(self.state, daten)
        self.assertEqual(_uids(self.state), vorher)

    def test_alt_show_ohne_kennung_bekommt_eine_je_gruppe(self):
        SF._restore_fixture_groups(self.state, [
            dict(_BASIS, name="A", id=3), dict(_BASIS, name="B"), dict(_BASIS, name="C")])
        u = _uids(self.state)
        self.assertEqual(len(u), 3)
        self.assertTrue(all(u.values()), u)
        self.assertEqual(len(set(u.values())), 3, u)

    def test_doppelte_und_unlesbare_kennungen_kosten_keine_gruppe(self):
        SF._restore_fixture_groups(self.state, [
            dict(_BASIS, name="A", id=1, uid="abcdef0123456789"),
            dict(_BASIS, name="B", id=2, uid="abcdef0123456789"),     # doppelt
            dict(_BASIS, name="C", id=3, uid=17),
            dict(_BASIS, name="D", id=4, uid=""),
            dict(_BASIS, name="E", id=5, uid="x" * 500),
            dict(_BASIS, name="F", id=6, uid=None),
            dict(_BASIS, name="G", id=7, uid=["a"])])
        u = _uids(self.state)
        self.assertEqual(sorted(u), [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(u[1], "abcdef0123456789", "der erste Eintrag behaelt sie")
        self.assertTrue(all(u.values()), u)
        self.assertEqual(len(set(u.values())), 7, u)
        self.assertTrue(all(len(v) <= 64 for v in u.values()), u)

    def test_taste_trifft_nach_umbenennen_speichern_und_laden_dieselbe_gruppe(self):
        _gruppe(self.state, "PARs", "Front", [11, 12])
        back = _gruppe(self.state, "PARs", "Back", [21, 22])
        b = self._taste(back)
        _aendern(self.state, back, name="Hinten")
        taste = json.loads(json.dumps(b.to_dict()))
        self.assertEqual([r["name"] for r in taste["blackout_group_refs"]], ["Hinten"])
        tmp = os.path.join(tempfile.mkdtemp(), "s.lshow")
        SF.save_show(tmp)
        _gruppen_leeren(self.state)
        self.assertTrue(SF.load_show(tmp)[0])
        nach = self._taste()
        nach.apply_dict(taste)
        self.assertEqual(self._ziele(nach), {21, 22})


class MigrationTest(unittest.TestCase):
    """Eine Show-DB von vor VCB-42 hat die Spalte nicht."""

    def _alte_db(self):
        fd, pfad = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        eng = create_engine(f"sqlite:///{pfad}")
        self.addCleanup(eng.dispose)
        with eng.begin() as c:
            c.execute(text(
                "CREATE TABLE fixture_groups (id INTEGER NOT NULL PRIMARY KEY, "
                "name VARCHAR(80), cols INTEGER, rows INTEGER, positions_json TEXT, "
                "folder VARCHAR(200))"))
            c.execute(text(
                "INSERT INTO fixture_groups (id, name, cols, rows, positions_json, folder) "
                "VALUES (1,'A',1,1,'{}',''), (2,'B',1,1,'{}',''), (5,'C',1,1,'{}','X')"))
        return eng

    def _zeilen(self, eng) -> dict:
        with Session(eng) as s:
            return {g.id: (g.name, g.folder, g.uid)
                    for g in s.execute(select(FixtureGroup)).scalars()}

    def test_spalte_wird_ergaenzt_und_jede_gruppe_bekommt_eine_kennung(self):
        eng = self._alte_db()
        migrate_show_db(eng)
        z = self._zeilen(eng)
        self.assertEqual({k: v[:2] for k, v in z.items()},
                         {1: ("A", ""), 2: ("B", ""), 5: ("C", "X")})
        uids = [v[2] for v in z.values()]
        self.assertTrue(all(uids), uids)
        self.assertEqual(len(set(uids)), 3, uids)
        self.assertTrue(all(group_ref.uid_lesbar(u) == u for u in uids), uids)

    def test_zweiter_lauf_aendert_nichts(self):
        eng = self._alte_db()
        migrate_show_db(eng)
        vorher = self._zeilen(eng)
        migrate_show_db(eng)
        self.assertEqual(self._zeilen(eng), vorher)

    def test_zeile_einer_aelteren_version_bekommt_beim_naechsten_start_eine(self):
        """Eine aeltere Programmversion kennt die Spalte nicht und schreibt ''."""
        eng = self._alte_db()
        migrate_show_db(eng)
        with eng.begin() as c:
            c.execute(text(
                "INSERT INTO fixture_groups (id, name, cols, rows, positions_json, folder) "
                "VALUES (9,'Alt',1,1,'{}','')"))
        self.assertFalse(self._zeilen(eng)[9][2])
        migrate_show_db(eng)
        z = self._zeilen(eng)
        self.assertTrue(z[9][2])
        self.assertEqual(len({v[2] for v in z.values()}), 4)

    def test_frisch_angelegte_db_nimmt_eine_zeile_ohne_kennung(self):
        """Eine NEU angelegte Show-DB muss dieselbe Zeile annehmen wie eine
        nachgezogene. Als Pflichtspalte ohne Datenbank-Vorgabe liesse ``uid``
        eine aeltere Programmversion auf dieser DB keine Gruppe mehr anlegen
        („NOT NULL constraint failed“)."""
        fd, pfad = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        eng = create_engine(f"sqlite:///{pfad}")
        self.addCleanup(eng.dispose)
        create_all_idempotent(eng)
        with eng.begin() as c:
            c.execute(text(
                "INSERT INTO fixture_groups (name, cols, rows, positions_json, folder) "
                "VALUES ('Alt',1,1,'{}','')"))
        (zeile,) = self._zeilen(eng).values()
        self.assertEqual(zeile[:2], ("Alt", ""))
        self.assertFalse(zeile[2])
        migrate_show_db(eng)
        (zeile,) = self._zeilen(eng).values()
        self.assertTrue(group_ref.uid_lesbar(zeile[2]))


# ── Die Taste: Steckbrief, Datei, Altbestand ────────────────────────────────

class TasteTest(_MitState):

    def setUp(self):
        super().setUp()
        self.front = _gruppe(self.state, "PARs", "Front", [11, 12])
        self.back = _gruppe(self.state, "PARs", "Back", [21, 22])

    def test_die_wahl_merkt_den_steckbrief(self):
        b = self._taste(self.back)
        self.assertEqual(b.blackout_group_ids, [self.back])
        self.assertEqual(b.blackout_group_refs[self.back],
                         {"uid": _uids(self.state)[self.back], "name": "PARs", "folder": "Back"})

    def test_datei_traegt_den_steckbrief_je_id(self):
        d = self._taste(self.back, self.front).to_dict()
        u = _uids(self.state)
        self.assertEqual(d["blackout_group_ids"], [self.back, self.front])
        self.assertEqual(d["blackout_group_refs"], [
            {"id": self.back, "uid": u[self.back], "name": "PARs", "folder": "Back"},
            {"id": self.front, "uid": u[self.front], "name": "PARs", "folder": "Front"}])

    def test_taste_ohne_gruppen_ziel_schreibt_das_feld_nicht(self):
        for b in (self._taste(), ):
            self.assertNotIn("blackout_group_refs", b.to_dict())
        b = self._taste()
        b.blackout_groups = ["Altname"]
        b.blackout_fids = [3]
        self.assertNotIn("blackout_group_refs", b.to_dict())

    def test_laden_und_speichern_ist_stabil(self):
        d = json.loads(json.dumps(self._taste(self.back, self.front).to_dict()))
        neu = self._taste()
        neu.apply_dict(d)
        self.assertEqual(json.loads(json.dumps(neu.to_dict())), d)

    def test_layout_von_vcb36_ohne_steckbrief_gilt_ueber_die_nummer(self):
        """Zwischenstand VCB-36: nur ``blackout_group_ids``. Mehr als die Nummer
        steht nicht da — sie gilt; der Steckbrief wird beim Laden ergaenzt."""
        b = self._taste()
        b.apply_dict({"caption": "BO", "action": ButtonAction.BLACKOUT.value,
                      "blackout_group_ids": [self.back], "blackout_groups": ["PARs"],
                      "blackout_groups_nur_name": []})
        self.assertEqual(b.blackout_group_refs[self.back]["uid"], _uids(self.state)[self.back])
        self.assertEqual(self._ziele(b), {21, 22})
        # … und ist danach geschuetzt wie jedes andere Ziel.
        self._nummer_neu_vergeben(self.back)
        self.assertEqual(self._ziele(b), set())

    def test_layout_von_vcb36_auf_fehlende_gruppe_bleibt_verloren(self):
        """Gab es die Gruppe beim Laden nicht, darf eine SPAETER angelegte mit
        dieser Nummer das Ziel nicht erben."""
        frei = self.back + 7
        b = self._taste()
        b.apply_dict({"caption": "BO", "action": ButtonAction.BLACKOUT.value,
                      "blackout_group_ids": [frei]})
        self.assertTrue(b.has_blackout_target())
        _gruppe(self.state, "Spaeter", "", [91], gid=frei)
        self.assertEqual(self._ziele(b), set())
        self.assertEqual(len(b._blackout_ziele_verloren()), 1)
        d = json.loads(json.dumps(b.to_dict()))
        nach = self._taste()
        nach.apply_dict(d)
        self.assertEqual(self._ziele(nach), set())
        self.assertTrue(nach.has_blackout_target())

    def test_unlesbare_steckbriefe_kosten_die_taste_nicht(self):
        for roh in ("kaputt", 7, None, [None, 5, "x", {"id": "3"}, {"uid": "a"}],
                    {"id": self.back}, [{"id": self.back, "name": 5, "uid": [], "folder": 2}]):
            b = self._taste()
            b.apply_dict({"caption": "BO", "action": ButtonAction.BLACKOUT.value,
                          "blackout_group_ids": [self.back], "blackout_group_refs": roh})
            self.assertEqual(b.blackout_group_ids, [self.back], roh)
            self.assertTrue(b.has_blackout_target(), roh)
            self.assertEqual(self._ziele(b), {21, 22}, roh)

    def test_steckbrief_fuer_fremde_id_wird_nicht_uebernommen(self):
        b = self._taste()
        b.apply_dict({"caption": "BO", "action": ButtonAction.BLACKOUT.value,
                      "blackout_group_ids": [self.back],
                      "blackout_group_refs": [
                          {"id": self.front, "uid": "zzzzzzzzzzzz", "name": "X", "folder": ""}]})
        self.assertEqual(b.blackout_group_ids, [self.back])
        self.assertNotIn(self.front, b.blackout_group_refs)

    def test_ohne_lesbare_show_db_kein_fehlalarm_und_kein_vergessen(self):
        b = self._taste(self.back)
        vorher = dict(b.blackout_group_refs)
        with mock.patch.object(type(self.state), "gruppen_steckbriefe", return_value=None):
            self.assertEqual(b._blackout_ziele_verloren(), [])
            d = b.to_dict()
        self.assertEqual(b.blackout_group_refs, vorher)
        self.assertEqual(d["blackout_group_ids"], [self.back])
        self.assertTrue(_alte_version_hat_ziel(d))


# ── Sichtbar: Dialog und Taste ───────────────────────────────────────────────

class AnzeigeTest(_MitState):

    def setUp(self):
        super().setUp()
        self.front = _gruppe(self.state, "PARs", "Front", [11, 12])
        self.back = _gruppe(self.state, "PARs", "Back", [21, 22])

    def _editor(self, b):
        ed = tle.BlackoutTargetEditor()
        b._blackout_editor_fuellen(ed)
        return ed

    def _zeilen(self, ed) -> list[tuple[str, str]]:
        return [(r["func"].currentData(), r["func"].currentText()) for r in ed._rows]

    def test_gueltiges_ziel_steht_als_gruppe_im_dialog(self):
        ed = self._editor(self._taste(self.back))
        self.assertEqual([k for k, _t in self._zeilen(ed)], [f"gi:{self.back}"])

    def test_verlorenes_ziel_steht_mit_seinem_namen_da_nicht_als_fremde_gruppe(self):
        b = self._taste(self.back)
        self._nummer_neu_vergeben(self.back)
        (key, text_), = self._zeilen(self._editor(b))
        self.assertEqual(key, f"gx:{self.back}")
        self.assertIn("PARs", text_)
        self.assertIn("Back", text_)
        self.assertIn("verloren", text_)
        self.assertNotIn("Neu", text_)

    def test_ok_ohne_aenderung_haelt_das_verlorene_ziel(self):
        """OK im Dialog darf die Taste weder an die fremde Gruppe binden noch
        zum globalen Blackout machen."""
        b = self._taste(self.back)
        self._nummer_neu_vergeben(self.back)
        vorher = dict(b.blackout_group_refs[self.back])
        b._blackout_ziel_aus_editor(self._editor(b))
        self.assertEqual(b.blackout_group_ids, [self.back])
        self.assertEqual(b.blackout_group_refs[self.back], vorher)
        self.assertTrue(b.has_blackout_target())
        self.assertEqual(self._ziele(b), set())

    def test_neu_gewaehlte_gruppe_ersetzt_das_verlorene_ziel_gleicher_nummer(self):
        b = self._taste(self.back)
        neu = self._nummer_neu_vergeben(self.back)
        ed = self._editor(b)
        ed.set_targets([f"gx:{self.back}", f"gi:{neu}"])
        b._blackout_ziel_aus_editor(ed)
        self.assertEqual(b.blackout_group_ids, [neu])
        self.assertEqual(b.blackout_group_refs[neu]["name"], "Neu")
        self.assertEqual(self._ziele(b), {31})

    def test_zeile_entfernen_gibt_das_ziel_auf(self):
        b = self._taste(self.back)
        self._nummer_neu_vergeben(self.back)
        ed = self._editor(b)
        ed.set_targets([])
        b._blackout_ziel_aus_editor(ed)
        self.assertEqual(b.blackout_group_ids, [])
        self.assertEqual(b.blackout_group_refs, {})
        self.assertFalse(b.has_blackout_target())

    def test_die_auswahl_bietet_ein_verlorenes_ziel_nicht_zum_waehlen_an(self):
        self.assertFalse([k for k, _t in tle._blackout_choices() if k.startswith("gx:")])

    def test_taste_meldet_verlorene_ziele_mit_namen(self):
        b = self._taste(self.front, self.back)
        self.assertEqual(b._blackout_ziele_verloren(), [])
        self._nummer_neu_vergeben(self.back)
        (text_,) = b._blackout_ziele_verloren()
        self.assertIn("PARs", text_)
        self.assertIn("Back", text_)

    def test_andere_aktion_meldet_nichts(self):
        b = self._taste(self.back)
        self._nummer_neu_vergeben(self.back)
        b.action = ButtonAction.FUNCTION_TOGGLE
        self.assertEqual(b._blackout_ziele_verloren(), [])

    def test_taste_zeichnet_die_warnung_und_nimmt_sie_zurueck(self):
        b = self._taste(self.back)
        kennung = _uids(self.state)[self.back]
        b.resize(120, 60)
        b.grab()
        self.assertNotIn("Blackout-Ziel", b.toolTip())
        self._nummer_neu_vergeben(self.back)
        b._blackout_anzeige_veraltet()
        b.grab()
        self.assertIn("Blackout-Ziel", b.toolTip())
        self.assertIn("PARs", b.toolTip())
        # wieder da (die Gruppe traegt ihre Kennung wieder, wie nach einem
        # Rueckgaengig des Loeschens) -> Warnung weg. Gleicher Name allein
        # genuegt seit VCB-44 nicht mehr.
        _aendern(self.state, self.back, name="PARs", folder="Back")
        b._blackout_anzeige_veraltet()
        b.grab()
        self.assertIn("Blackout-Ziel", b.toolTip())
        _aendern(self.state, self.back, uid=kennung)
        b._blackout_anzeige_veraltet()
        b.grab()
        self.assertNotIn("Blackout-Ziel", b.toolTip())

    def test_druck_auf_verlorenes_ziel_sagt_es(self):
        b = self._taste(self.back)
        self._nummer_neu_vergeben(self.back)
        with mock.patch.object(VCButton, "_show_status") as status:
            b._trigger_primary(True)
        self.assertEqual(status.call_count, 1)
        self.assertIn("PARs", status.call_args[0][0])
        # Loslassen meldet nichts.
        with mock.patch.object(VCButton, "_show_status") as status:
            b._trigger_primary(False)
        self.assertEqual(status.call_count, 0)


# ── Undo gibt der Gruppe ihre Kennung zurueck ───────────────────────────────

def _rgbw_baenke(n):
    chans, num = [], 1
    for _h in range(n):
        for attr in ("color_r", "color_g", "color_b", "color_w"):
            chans.append(NS(attribute=attr, channel_number=num, default_value=0))
            num += 1
    return chans


class UndoHaeltDieKennungTest(unittest.TestCase):

    def setUp(self):
        orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _rgbw_baenke(4)
        self.addCleanup(setattr, A, "get_channels_for_patched", orig)
        self.state = A.AppState()
        fd, pfad = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.state.open_show(pfad)
        self.stack = get_undo_stack()
        self.stack.clear()
        self.addCleanup(self.stack.clear)
        for fid, label, addr in ((5, "HydraA", 1), (9, "HydraB", 33)):
            self.state.add_fixture(PatchedFixture(
                fid=fid, label=label, fixture_profile_id=1, mode_name="Standard",
                universe=1, address=addr, channel_count=16,
                fixture_type="moving_head"), undoable=True)

    def _ziel(self, gid, steckbrief) -> set:
        name, folder, uid = steckbrief
        slot = object()
        self.state.set_target_blackout(slot, [], [(gid, name, folder, uid)])
        return self.state._target_blackout_fids(self.state._ziel_blackout_specs[slot])

    def test_undo_gibt_der_gruppe_ihre_kennung_zurueck(self):
        gid = self.state.find_head_matrix_group(9, dedicated=True)
        vorher = self.state.gruppen_steckbriefe()[gid]
        self.assertTrue(vorher[2])
        self.state.remove_fixture(9, undoable=True)
        self.assertNotIn(gid, self.state.gruppen_steckbriefe())
        self.stack.undo()
        self.assertEqual(self.state.gruppen_steckbriefe()[gid], vorher)

    def test_ziel_mit_veraltetem_namen_ueberlebt_loeschen_und_undo(self):
        """Der Steckbrief der Taste kann aelter sein als der Name der Gruppe
        (umbenannt, Taste seither nicht gedrueckt). Dann haelt nur die Kennung."""
        gid = self.state.find_head_matrix_group(9, dedicated=True)
        name, folder, uid = self.state.gruppen_steckbriefe()[gid]
        alt = ("Alter Name", folder, uid)
        self.assertEqual(self._ziel(gid, alt), {9}, "VORBEDINGUNG")
        self.state.remove_fixture(9, undoable=True)
        self.assertEqual(self._ziel(gid, alt), set())
        self.stack.undo()
        self.assertEqual(self._ziel(gid, alt), {9})

    def test_vergebene_kennung_wird_nicht_doppelt(self):
        gid = self.state.find_head_matrix_group(9, dedicated=True)
        uid = self.state.gruppen_steckbriefe()[gid][2]
        self.state.remove_fixture(9, undoable=True)
        with Session(self.state._show_engine) as s:
            s.add(FixtureGroup(name="Fremd", cols=1, rows=1, uid=uid,
                               positions_json=json.dumps({"0,0": 5})))
            s.commit()
        self.stack.undo()
        uids = [u for _n, _f, u in self.state.gruppen_steckbriefe().values()]
        self.assertEqual(len(uids), len(set(uids)), uids)


if __name__ == "__main__":
    unittest.main()
