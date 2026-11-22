"""FM-20 Teil 2: echte Gruppe in Gruppe.

Eine fertig angeordnete Gruppe (z. B. ein Panel-Raster) steht als EIN Block
``"g:<uid>"`` in einer groesseren Gruppe. Gespeichert wird nur der Verweis;
jeder Leser bekommt ueber ``models.aufgeloeste_positionen`` (Kern:
``group_cells.aufloesen``) die Einzelzellen. Ohne den Fix fallen die Geraete des
Blocks in Programmer/VC/Matrix still weg (``parse_group_cell`` -> None).

Headless; Wegwerf-Show (``reset_show``) auf frischer Bibliothek.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import delete, select

from _fixture_quelle import frische_library
from _qt_lifecycle import destroy_all_top_level_widgets
from src.core.app_state import get_state
from src.core.database.models import (FixtureGroup, aufgeloeste_positionen,
                                      verweise_einbetten)
from src.core.group_cells import (aufloesen, block_ausmass, gruppen_verweis,
                                  parse_gruppen_verweis, waere_zyklus)
from src.core.show import show_file as SF


def _app():
    return QApplication.instance() or QApplication([])


# ── rein: die Aufloesung ─────────────────────────────────────────────────────

_PANEL = (2, 2, {"0,0": 11, "1,0": 12, "0,1": 13, "1,1": 14})


def _lade(tab):
    return lambda u: tab.get(u)


class AufloesungTest(unittest.TestCase):

    def test_ohne_verweis_unveraendert(self):
        pos = {"0,0": 1, "1,0": "5:2"}
        self.assertEqual(aufloesen(pos, _lade({})), pos)

    def test_block_am_anker(self):
        out = aufloesen({"0,0": 1, "1,0": "g:p", "3,0": 2}, _lade({"p": _PANEL}))
        self.assertEqual(out, {"0,0": 1, "1,0": 11, "2,0": 12, "1,1": 13,
                               "2,1": 14, "3,0": 2})

    def test_drehung_90(self):
        out = aufloesen({"0,0": gruppen_verweis("p", 90)}, _lade({"p": _PANEL}))
        # im Uhrzeigersinn: links oben (11) wandert nach rechts oben
        self.assertEqual(out, {"1,0": 11, "1,1": 12, "0,0": 13, "0,1": 14})
        self.assertEqual(block_ausmass(4, 2, 90), (2, 4))

    def test_direkte_zelle_gewinnt(self):
        out = aufloesen({"0,0": "g:p", "1,1": 99}, _lade({"p": _PANEL}))
        self.assertEqual(out["1,1"], 99)

    def test_zyklus_und_fehlende_gruppe_liefern_nichts(self):
        tab = {"a": (1, 1, {"0,0": "g:b"}), "b": (2, 1, {"0,0": "g:a", "1,0": 7})}
        self.assertEqual(aufloesen({"0,0": "g:b"}, _lade(tab), eigene_uid="a"),
                         {"1,0": 7})
        self.assertEqual(aufloesen({"0,0": "g:weg", "1,0": 3}, _lade({})), {"1,0": 3})
        self.assertTrue(waere_zyklus("a", "b", _lade(tab)))
        self.assertTrue(waere_zyklus("a", "a", _lade(tab)))
        self.assertFalse(waere_zyklus("x", "p", _lade({"p": _PANEL})))

    def test_verweis_format(self):
        self.assertEqual(parse_gruppen_verweis("g:ab@270"), ("ab", 270))
        self.assertEqual(parse_gruppen_verweis("g:ab@45"), (None, 0))
        self.assertEqual(parse_gruppen_verweis("5:2"), (None, 0))


# ── mit Show-DB ──────────────────────────────────────────────────────────────

def _leeren(state):
    with state._session() as s:
        s.execute(delete(FixtureGroup))
        s.commit()


def _gruppe(state, name, cols, rows, pos) -> tuple:
    with state._session() as s:
        g = FixtureGroup(name=name, cols=cols, rows=rows, positions_json=json.dumps(pos))
        s.add(g)
        s.commit()
        return int(g.id), g.uid


def _setzen(state, gid, **felder):
    with state._session() as s:
        g = s.get(FixtureGroup, gid)
        for k, v in felder.items():
            setattr(g, k, v)
        s.commit()


class _MitShow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frische_library(cls)

    def setUp(self):
        _app()
        SF.reset_show()
        self.state = get_state()
        _leeren(self.state)
        self.addCleanup(_leeren, self.state)
        self.addCleanup(destroy_all_top_level_widgets, QApplication.instance())
        self.pid, self.puid = _gruppe(self.state, "Panel", 2, 2, _PANEL[2])
        self.oid, self.ouid = _gruppe(self.state, "Buehne", 4, 2,
                                      {"0,0": 1, "1,0": f"g:{self.puid}", "3,0": 2})


class LeserTest(_MitShow):

    def test_programmer_vc_und_browser_sehen_die_blockgeraete(self):
        self.assertEqual(self.state.group_fids_by_name("Buehne"), [1, 11, 12, 2, 13, 14])
        self.assertIn("13", self.state.group_cells_by_name("Buehne"))
        eintrag = [g for g in self.state.list_fixture_groups() if g["name"] == "Buehne"][0]
        self.assertEqual(sorted(eintrag["fids"]), [1, 2, 11, 12, 13, 14])
        from src.ui.views.programmer_view import ProgrammerView
        with self.state._session() as s:
            g = s.get(FixtureGroup, self.oid)
            self.assertEqual(sorted(ProgrammerView._group_fids(g)), [1, 2, 11, 12, 13, 14])

    def test_aenderung_und_umbenennen_der_untergruppe_wirken_nach(self):
        _setzen(self.state, self.pid, name="Panel neu",
                positions_json=json.dumps({"0,0": 11, "1,1": 15}))
        self.assertEqual(self.state.group_fids_by_name("Buehne"), [1, 11, 2, 15])

    def test_speichern_und_laden_behaelt_den_verweis(self):
        tmp = os.path.join(tempfile.mkdtemp(), "s.lshow")
        SF.save_show(tmp)
        _leeren(self.state)
        self.assertTrue(SF.load_show(tmp)[0])
        self.assertEqual(self.state.group_fids_by_name("Buehne"), [1, 11, 12, 2, 13, 14])

    def test_loeschen_bettet_die_zellen_ein(self):
        with self.state._session() as s:
            self.assertEqual(verweise_einbetten(s, self.puid), 1)
            s.execute(delete(FixtureGroup).where(FixtureGroup.id == self.pid))
            s.commit()
            g = s.get(FixtureGroup, self.oid)
            self.assertEqual(json.loads(g.positions_json),
                             {"0,0": 1, "3,0": 2, "1,0": 11, "2,0": 12, "1,1": 13, "2,1": 14})
            self.assertEqual(aufgeloeste_positionen(g, s), json.loads(g.positions_json))

    def test_zusammenlegen_als_bloecke_traegt_die_herkunft(self):
        zid, zuid = _gruppe(self.state, "Zweit", 2, 1, {"0,0": 21, "1,0": 22})
        neu = self.state.merge_head_matrix_groups([self.pid, zid], "Zus", als_bloecke=True)
        with self.state._session() as s:
            g = s.get(FixtureGroup, neu)
            self.assertEqual(json.loads(g.positions_json),
                             {"0,0": f"g:{self.puid}", "0,2": f"g:{zuid}"})
            self.assertEqual((g.cols, g.rows), (2, 3))
        self.assertEqual(self.state.group_fids_by_name("Zus"), [11, 12, 13, 14, 21, 22])
        # Standard bleibt das Kopieren
        alt = self.state.merge_head_matrix_groups([self.pid, zid], "Kopie")
        with self.state._session() as s:
            self.assertNotIn("g:", s.get(FixtureGroup, alt).positions_json)

    def test_matrix_raster_aus_der_aufgeloesten_form(self):
        from src.core.engine.rgb_matrix import grids_from_positions
        with self.state._session() as s:
            g = s.get(FixtureGroup, self.oid)
            grid, _h = grids_from_positions(aufgeloeste_positionen(g, s), g.cols, g.rows)
        self.assertEqual(grid, [1, 11, 12, 2, None, 13, 14, None])

    def test_wachsende_untergruppe_kommt_in_der_matrix_an(self):
        # Pruefung: Panel waechst um eine Zeile, die Buehne (4x2) wurde nicht
        # angepasst. Programmer/VC zaehlen Geraet 15 mit — die Matrix verwarf es
        # vorher still (Zelle ausserhalb von cols x rows).
        _setzen(self.state, self.pid, rows=3, positions_json=json.dumps(
            {"0,0": 11, "1,0": 12, "0,1": 13, "1,1": 14, "0,2": 15}))
        self.assertIn(15, self.state.group_fids_by_name("Buehne"))
        from src.ui.views.rgb_matrix_view import RgbMatrixView
        self.state.set_selected_group_id(self.oid)
        self.addCleanup(self.state.set_selected_group_id, None)
        v = RgbMatrixView()
        raster, _text = v._auswahl_raster()
        self.assertEqual((raster["cols"], raster["rows"]), (4, 3))
        self.assertIn(15, raster["fixture_grid"])
        from src.core.database.models import aufgeloestes_raster
        with self.state._session() as s:       # ohne Verweis: wie gespeichert
            p = s.get(FixtureGroup, self.pid)
            self.assertEqual(aufgeloestes_raster(p, s)[:2], (2, 3))


class AltShowTest(_MitShow):

    def test_alt_show_ohne_uid_bekommt_eine_und_bleibt_gleich(self):
        _leeren(self.state)
        alt = [{"name": "A", "cols": 2, "rows": 1, "folder": "",
                "positions_json": json.dumps({"0,0": 1, "1,0": "2:0"})},
               {"name": "B", "cols": 1, "rows": 1, "folder": "",
                "positions_json": json.dumps({"0,0": 3})}]
        SF._restore_fixture_groups(self.state, alt)
        with self.state._session() as s:
            gs = s.execute(select(FixtureGroup)).scalars().all()
            self.assertTrue(all(g.uid for g in gs))
            self.assertEqual(len({g.uid for g in gs}), 2)
            a = [g for g in gs if g.name == "A"][0]
            self.assertEqual(aufgeloeste_positionen(a, s), {"0,0": 1, "1,0": "2:0"})


def test_alt_show_db_migration_idempotent_und_verlustfrei():
    """Pruefung: eine Show-DB OHNE uid-Spalte — zweimal migriert, gleiche uids,
    Zellen byte-gleich."""
    import sqlite3
    from sqlalchemy import create_engine
    from src.core.database.models import migrate_show_db
    pfad = os.path.join(tempfile.mkdtemp(), "alt.db")
    roh = '{"0,0": 1, "1,0": "2:0"}'
    c = sqlite3.connect(pfad)
    c.execute("CREATE TABLE fixture_groups (id INTEGER PRIMARY KEY, name VARCHAR, "
              "cols INT, rows INT, positions_json TEXT)")
    c.execute("INSERT INTO fixture_groups VALUES (1,'A',2,1,?)", (roh,))
    c.execute("INSERT INTO fixture_groups VALUES (2,'B',1,1,'{\"0,0\": 3}')")
    c.commit()
    c.close()
    eng = create_engine(f"sqlite:///{pfad}")
    q = "select id, name, cols, rows, positions_json, uid from fixture_groups order by id"
    migrate_show_db(eng)
    erst = sqlite3.connect(pfad).execute(q).fetchall()
    migrate_show_db(eng)
    zweit = sqlite3.connect(pfad).execute(q).fetchall()
    eng.dispose()
    assert erst == zweit
    assert erst[0][4] == roh and len({r[5] for r in erst}) == 2
    assert all(len(r[5]) == 32 for r in erst)


class EditorTest(_MitShow):

    def _view(self):
        from src.ui.views.fixture_group_view import FixtureGroupView
        v = FixtureGroupView()
        with self.state._session() as s:
            g = s.get(FixtureGroup, self.oid)
            s.expunge(g)
        v._current_group = g
        v._load_group(g)
        return v

    def _texte(self, menu):
        out = []
        for a in menu.actions():
            out.append(a.text())
            if a.menu():
                out += ["  " + t for t in self._texte(a.menu())]
        return out

    def test_einsetzen_drehen_aufteilen(self):
        neu_id, neu_uid = _gruppe(self.state, "Leiste", 3, 1, {"0,0": 31, "1,0": 32, "2,0": 33})
        v = self._view()
        gw = v._grid_widget
        texte = self._texte(v._build_cell_menu(0, 1))
        self.assertIn("Gruppe als Block einsetzen", texte)
        self.assertIn("  Leiste", texte)
        self.assertNotIn("  Buehne", texte, "die Gruppe selbst ist kein Block-Kandidat")
        self.assertIn("▣ Panel", gw.zell_beschriftung(gw.positions[(1, 0)]))
        self.assertTrue(v._block_einsetzen(neu_uid, 0, 1))
        self.assertEqual(gw.positions[(0, 1)], f"g:{neu_uid}")
        v._block_drehen(0, 1)
        self.assertEqual(gw.positions[(0, 1)], f"g:{neu_uid}@90")
        self.assertGreaterEqual(v._spin_rows.value(), 4, "Raster waechst mit dem Block")
        self.assertIn("Block in Einzelzellen aufteilen", self._texte(v._build_cell_menu(0, 1)))
        v._block_aufteilen(0, 1)
        self.assertEqual({k: gw.positions[k] for k in [(0, 1), (0, 2), (0, 3)]},
                         {(0, 1): 31, (0, 2): 32, (0, 3): 33})
        gw.grab()   # malt Bloecke ohne Fehler

    def test_zyklus_wird_nicht_eingesetzt(self):
        v = self._view()
        # Panel enthaelt jetzt Buehne -> Buehne darf Panel nicht nochmal ... und
        # umgekehrt: Panel kann Buehne nicht aufnehmen.
        with self.state._session() as s:
            p = s.get(FixtureGroup, self.pid)
            s.expunge(p)
        v._current_group = p
        v._load_group(p)
        self.assertFalse(v._block_einsetzen(self.ouid, 0, 0))
        self.assertNotIn((0, 0), [k for k, w in v._grid_widget.positions.items()
                                  if str(w).startswith("g:")])


if __name__ == "__main__":
    unittest.main()
