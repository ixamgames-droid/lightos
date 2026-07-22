"""FM-HEADLAYOUT Slice 1: Mehrkopf-Programmiermodus pro Fixture (`head_mode`).

David-Wunsch 2026-07-22: die beim Patchen automatisch erzeugte Pro-Kopf-Matrix-
Gruppe („… · Köpfe") liess sich nach dem Löschen nicht wiederherstellen, und der
Automatismus war nirgends einstellbar. Jetzt: per-Fixture-Option `head_mode`
(auto | heads | single) — an derselben Stelle wie Invert/Swap — plus ein
idempotentes „Wiederherstellen".

Kern-Invarianten (Fallenklasse #3 Show-Persistenz + „nicht destruktiv"):
- Alt-Shows OHNE den Key laden unveraendert als "auto" (= Bestandsverhalten).
- Unbekannte/kaputte Werte fallen auf "auto" zurueck (kein Garbage aus der Show).
- `head_mode` ueberlebt save -> load.
- "single" unterdrueckt NUR die automatische Anlage; es LOESCHT nie eine Gruppe.
- `find_head_matrix_group` erkennt genau die Kopf-Gruppen (`fid:head`-Zellen).
"""
import json
import os
import unittest
from types import SimpleNamespace as NS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.show.show_file import _fixture_to_dict, _to_head_mode, HEAD_MODES


# ── Rein: Normalisierung + Persistenz-Schema ─────────────────────────────────
class HeadModeNormalizeTest(unittest.TestCase):
    def test_valid_modes(self):
        self.assertEqual(HEAD_MODES, ("auto", "heads", "single"))
        for m in HEAD_MODES:
            self.assertEqual(_to_head_mode(m), m)

    def test_missing_and_garbage_default_to_auto(self):
        # Alt-Show ohne Key / kaputter Wert -> Bestandsverhalten "auto".
        for bad in (None, "", "  ", "quatsch", 7, [], "HEADS!"):
            self.assertEqual(_to_head_mode(bad), "auto", repr(bad))

    def test_case_and_whitespace_tolerant(self):
        self.assertEqual(_to_head_mode(" Heads "), "heads")
        self.assertEqual(_to_head_mode("SINGLE"), "single")


class FixtureToDictTest(unittest.TestCase):
    def _dict_from_obj(self, **kw):
        pf = NS(fid=1, label="X", fixture_profile_id=1, mode_name="m", universe=1,
                address=1, channel_count=4, manufacturer_name="", fixture_name="",
                fixture_type="moving_head", **kw)
        return _fixture_to_dict(pf)

    def test_object_without_head_mode_serializes_auto(self):
        # Ein Fixture-Objekt aus einer Alt-DB (Spalte fehlt) -> "auto".
        self.assertEqual(self._dict_from_obj()["head_mode"], "auto")

    def test_object_head_mode_roundtrips(self):
        for m in HEAD_MODES:
            self.assertEqual(self._dict_from_obj(head_mode=m)["head_mode"], m)

    def test_dict_input_without_key_defaults_auto(self):
        # _fixture_to_dict akzeptiert auch dicts (Alt-.lshow ohne den Key).
        d = _fixture_to_dict({"fid": 1, "label": "X", "fixture_profile_id": 1,
                              "mode_name": "m", "universe": 1, "address": 1,
                              "channel_count": 4})
        self.assertEqual(d["head_mode"], "auto")

    def test_dict_garbage_sanitized(self):
        d = _fixture_to_dict({"fid": 1, "label": "X", "fixture_profile_id": 1,
                              "mode_name": "m", "universe": 1, "address": 1,
                              "channel_count": 4, "head_mode": "boom"})
        self.assertEqual(d["head_mode"], "auto")


# ── Show-DB: Migration + Round-Trip + Gruppen-Erkennung ──────────────────────
class _ShowBase(unittest.TestCase):
    def setUp(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from src.core.database.fixture_db import ensure_builtins
        from src.core.show.show_file import reset_show
        from src.core.app_state import get_state
        ensure_builtins()
        reset_show()
        self.state = get_state()

    def _add_group(self, name, positions):
        from src.core.database.models import FixtureGroup
        with self.state._session() as s:
            g = FixtureGroup(name=name, cols=8, rows=8,
                             positions_json=json.dumps(positions))
            s.add(g)
            s.commit()
            return g.id


class MigrationTest(_ShowBase):
    def test_show_db_has_head_mode_column_default_auto(self):
        # Additive ALTER-TABLE-Migration: Spalte da, Default 'auto' (Alt-Zeilen
        # verhalten sich damit exakt wie bisher).
        from sqlalchemy import text
        eng = self.state._show_engine
        with eng.begin() as conn:
            cols = {row[1]: row for row in
                    conn.execute(text("PRAGMA table_info(patched_fixtures)"))}
        self.assertIn("head_mode", cols)


class FindHeadMatrixGroupTest(_ShowBase):
    def test_finds_head_cells_only(self):
        # Kopf-Gruppe (fid:head) wird gefunden ...
        gid = self._add_group("Hydra · Köpfe",
                              {"0,0": "5:0", "1,0": "5:1", "2,0": "5:2", "3,0": "5:3"})
        self.assertEqual(self.state.find_head_matrix_group(5), gid)

    def test_plain_fid_group_is_not_a_head_group(self):
        # ... eine normale Gruppe mit GANZEN fids aber NICHT (sonst würde
        # „vorhanden" fälschlich gemeldet und das Wiederherstellen unterdrückt).
        self._add_group("Normal", {"0,0": 5, "1,0": 7})
        self.assertIsNone(self.state.find_head_matrix_group(5))

    def test_unknown_fid(self):
        self._add_group("Hydra · Köpfe", {"0,0": "5:0", "1,0": "5:1"})
        self.assertIsNone(self.state.find_head_matrix_group(99))

    def test_merged_matrix_finds_each_base_fid(self):
        gid = self._add_group("Merge · Köpfe",
                              {"0,0": "5:0", "1,0": "5:1", "0,1": "7:0", "1,1": "7:1"})
        self.assertEqual(self.state.find_head_matrix_group(5), gid)
        self.assertEqual(self.state.find_head_matrix_group(7), gid)


class RestoreIsNonDestructiveTest(_ShowBase):
    def test_create_is_idempotent_and_keeps_existing_group(self):
        # Eine bereits (evtl. zusammengelegte/bearbeitete) Kopf-Gruppe darf durch
        # ein erneutes „Wiederherstellen" NICHT verändert oder dupliziert werden.
        from src.core.database.models import FixtureGroup
        gid = self._add_group("Meine bearbeitete Matrix",
                              {"0,0": "5:0", "1,0": "5:1", "0,1": "5:2", "1,1": "5:3"})
        fx = NS(fid=5, label="Hydra", fixture_type="moving_head")
        import src.core.app_state as A
        orig = A.get_channels_for_patched
        # 4 RGBW-Bänke -> color_head_count == 4 (echtes Mehrkopf-Gerät)
        A.get_channels_for_patched = lambda f: [
            NS(attribute=a, channel_number=i + 1)
            for i, a in enumerate(["color_r", "color_g", "color_b", "color_w"] * 4)]
        try:
            again = self.state.create_head_matrix_group(fx)
        finally:
            A.get_channels_for_patched = orig
        self.assertEqual(again, gid, "Wiederherstellen darf kein Duplikat anlegen")
        with self.state._session() as s:
            g = s.get(FixtureGroup, gid)
            self.assertEqual(g.name, "Meine bearbeitete Matrix",
                             "bestehende Gruppe wurde umbenannt/überschrieben")
            self.assertEqual(json.loads(g.positions_json),
                             {"0,0": "5:0", "1,0": "5:1", "0,1": "5:2", "1,1": "5:3"},
                             "bestehendes Raster wurde verändert")


class LegacyDbMigrationTest(unittest.TestCase):
    """Der ECHTE ALTER-TABLE-Zweig: eine Alt-DB OHNE die Spalte + Bestandszeile.
    (Ein Test gegen eine FRISCHE DB erreicht den Zweig nie — Review-Fund.)"""

    def test_alter_table_adds_column_and_keeps_data(self):
        import tempfile
        from sqlalchemy import create_engine, text
        from src.core.database.models import migrate_show_db
        path = tempfile.mktemp(suffix=".db")
        eng = create_engine(f"sqlite:///{path}")
        with eng.begin() as c:
            # Alt-Schema: patched_fixtures OHNE head_mode.
            c.execute(text("CREATE TABLE patched_fixtures ("
                           "id INTEGER PRIMARY KEY, fid INTEGER UNIQUE, "
                           "label VARCHAR, invert_pan BOOLEAN DEFAULT 0)"))
            c.execute(text("INSERT INTO patched_fixtures (fid, label, invert_pan) "
                           "VALUES (7, 'Hydra', 1)"))
        migrate_show_db(eng)
        migrate_show_db(eng)          # idempotent: zweimal darf nicht brechen
        with eng.begin() as c:
            cols = {r[1] for r in c.execute(text("PRAGMA table_info(patched_fixtures)"))}
            row = c.execute(text("SELECT fid, label, invert_pan, head_mode "
                                 "FROM patched_fixtures WHERE fid=7")).fetchone()
        self.assertIn("head_mode", cols)
        # Bestandsdaten unveraendert, neue Spalte auf 'auto' (= Bestandsverhalten).
        self.assertEqual((row[0], row[1], bool(row[2])), (7, "Hydra", True))
        self.assertEqual(row[3], "auto")


class _MultiHeadStateBase(_ShowBase):
    """Basis mit gepatchtem get_channels_for_patched -> 4 RGBW-Baenke
    (color_head_count == 4), damit create_head_matrix_group greift."""

    def setUp(self):
        super().setUp()
        import src.core.app_state as A
        self._A = A
        self._orig_chans = A.get_channels_for_patched
        A.get_channels_for_patched = lambda f: [
            NS(attribute=a, channel_number=i + 1, default_value=0,
               highlight_value=255, ranges=[])
            for i, a in enumerate(["color_r", "color_g", "color_b", "color_w"] * 4)]
        self.addCleanup(setattr, A, "get_channels_for_patched", self._orig_chans)

    def _add(self, fid=1, head_mode="auto"):
        from src.core.database.models import PatchedFixture
        f = PatchedFixture(fid=fid, label="Hydra", fixture_profile_id=1,
                           mode_name="m", universe=1, address=1, channel_count=56,
                           fixture_type="moving_head", head_mode=head_mode)
        self.state.add_fixture(f)
        return fid

    def _mode_of(self, fid):
        f = next((x for x in self.state.get_patched_fixtures() if x.fid == fid), None)
        return None if f is None else getattr(f, "head_mode", None)


class UpdateFixturePersistsHeadModeTest(_MultiHeadStateBase):
    """Review-Fund HIGH: head_mode fehlte in der allowed-Whitelist von
    update_fixture -> die Dialog-Wahl wurde STILL verworfen (Feature tot)."""

    def test_update_fixture_persists_head_mode(self):
        self._add(head_mode="auto")
        self.assertTrue(self.state.update_fixture(1, head_mode="single"))
        self.assertEqual(self._mode_of(1), "single")

    def test_update_fixture_normalizes_garbage(self):
        self._add()
        self.state.update_fixture(1, head_mode="QUATSCH")
        self.assertEqual(self._mode_of(1), "auto")
        self.state.update_fixture(1, head_mode=" Heads ")
        self.assertEqual(self._mode_of(1), "heads")

    def test_realistic_dialog_payload(self):
        # Wie PatchView._on_double_click: label/universe/address/channel_count
        # kommen IMMER mit — head_mode darf dabei nicht untergehen.
        self._add()
        self.state.update_fixture(1, label="Hydra", universe=1, address=1,
                                  channel_count=56, head_mode="single")
        self.assertEqual(self._mode_of(1), "single")


class AddFixtureGateTest(_MultiHeadStateBase):
    def test_auto_and_heads_create_group_single_does_not(self):
        for fid, mode, expect in ((1, "auto", True), (2, "heads", True),
                                  (3, "single", False)):
            self._add(fid=fid, head_mode=mode)
            got = self.state.find_head_matrix_group(fid) is not None
            self.assertEqual(got, expect,
                             f"head_mode={mode}: Gruppe erwartet={expect}")


class UndoPreservesHeadModeTest(_MultiHeadStateBase):
    """Review-Fund: der Undo-Snapshot kannte head_mode nicht -> Loeschen+Undo
    setzte den Modus auf 'auto' UND legte die unterdrueckte Gruppe wieder an."""

    def test_remove_and_undo_keeps_single_and_suppression(self):
        self._add(head_mode="single")
        self.assertIsNone(self.state.find_head_matrix_group(1))
        self.state.remove_fixture(1)
        from src.core.undo import get_undo_stack
        get_undo_stack().undo()
        self.assertEqual(self._mode_of(1), "single",
                         "Undo hat den Mehrkopf-Modus verloren")
        self.assertIsNone(self.state.find_head_matrix_group(1),
                          "Undo hat die per 'single' unterdrückte Gruppe angelegt")


class DedicatedVsCoveredTest(_ShowBase):
    """Status darf nicht luegen: eine vom Nutzer ZUSAMMENGELEGTE Fremd-Matrix ist
    keine dedizierte Auto-Gruppe (sonst waere „Wiederherstellen" ein stiller
    No-Op, obwohl die Auto-Gruppe fehlt)."""

    def _add_group(self, name, positions, folder=""):
        from src.core.database.models import FixtureGroup
        with self.state._session() as s:
            g = FixtureGroup(name=name, cols=8, rows=8, folder=folder,
                             positions_json=json.dumps(positions))
            s.add(g)
            s.commit()
            return g.id

    def test_dedicated_auto_group(self):
        gid = self._add_group("Hydra · Köpfe", {"0,0": "5:0", "1,0": "5:1"},
                              folder="Multi-Head")
        self.assertEqual(self.state.find_head_matrix_group(5, dedicated=True), gid)
        self.assertEqual(self.state.find_head_matrix_group(5), gid)

    def test_merged_foreign_matrix_is_covered_but_not_dedicated(self):
        # Zusammengelegt (zwei fids) + anderer Ordner -> deckt ab, ist aber NICHT
        # die dedizierte Auto-Gruppe.
        self._add_group("Meine große Matrix",
                        {"0,0": "5:0", "1,0": "5:1", "0,1": "7:0", "1,1": "7:1"},
                        folder="Matrizen")
        self.assertIsNone(self.state.find_head_matrix_group(5, dedicated=True))
        self.assertIsNotNone(self.state.find_head_matrix_group(5))


if __name__ == "__main__":
    unittest.main()
