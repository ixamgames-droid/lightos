"""VCB-36, Nachtrag aus dem Review: vier Wege, auf denen ein Ziel-Blackout
doch noch sein Ziel verlor — drei davon endeten im GLOBALEN Blackout oder ohne
Gruppen.

* Eine Gruppen-ID jenseits von SQLites 64 Bit liess das Einfuegen scheitern und
  mit ihm die ganze Transaktion: EINE kaputte Zahl kostete ALLE Gruppen.
* Zeigte die Taste auf eine geloeschte oder namenlose Gruppe, blieb das Feld
  ``blackout_groups`` leer — eine aeltere Programmversion (kennt nur dieses
  Feld) machte daraus den globalen Blackout.
* Waren alle ``blackout_group_ids`` unlesbar (etwa als Text gespeichert), fiel
  die Taste auf „kein Ziel“ zurueck, also ebenfalls auf den globalen Blackout.
* Geraet loeschen + Ctrl+Z gab der Kopf-Gruppe eine NEUE ID; die Taste zeigte
  danach ins Leere.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication             # noqa: E402
from sqlalchemy import delete, select                   # noqa: E402
from sqlalchemy.orm import Session                      # noqa: E402

from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15
import src.core.app_state as A                          # noqa: E402
from src.core.app_state import get_state                # noqa: E402
from src.core.database.models import FixtureGroup, PatchedFixture   # noqa: E402
from src.core.show import show_file as SF               # noqa: E402
from src.core.undo import get_undo_stack                # noqa: E402
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


def _stand(state) -> list[tuple[int, str, str]]:
    with state._session() as s:
        return sorted((int(g.id), g.name, g.folder or "")
                      for g in s.execute(select(FixtureGroup)).scalars())


def _alte_version_hat_ziel(d: dict) -> bool:
    """Der Ladepfad VOR VCB-36 (``VCButton.apply_dict`` + ``has_blackout_target``):
    er kennt nur ``blackout_fids`` und ``blackout_groups``."""
    fids = []
    roh = d.get("blackout_fids", None)
    for i in (roh if isinstance(roh, (list, tuple)) else []):
        try:
            fids.append(int(i))
        except (TypeError, ValueError):
            continue
    roh = d.get("blackout_groups", None)
    gruppen = [g for g in (roh if isinstance(roh, (list, tuple)) else [])
               if isinstance(g, str) and g.strip()]
    return bool(fids or gruppen)


class _MitState(unittest.TestCase):

    def setUp(self):
        self.state = get_state()
        _gruppen_leeren(self.state)
        self.addCleanup(_gruppen_leeren, self.state)
        self.addCleanup(self.state.clear_all_target_blackouts)
        self.addCleanup(destroy_all_top_level_widgets, QApplication.instance())

    def _taste(self):
        b = VCButton("BO")
        b.action = ButtonAction.BLACKOUT
        return b

    def _ziele(self, b) -> set:
        slot = object()
        self.state.set_target_blackout(slot, b.blackout_fids, b._blackout_gruppen_ziele())
        return self.state._target_blackout_fids(self.state._ziel_blackout_specs[slot])


class ZuGrosseIdTest(_MitState):

    def test_eine_zu_grosse_id_kostet_nicht_alle_gruppen(self):
        SF._restore_fixture_groups(self.state, [
            dict(_BASIS, name="A", id=5), dict(_BASIS, name="B", id=2**70),
            dict(_BASIS, name="C", id=2**63)])
        stand = _stand(self.state)
        self.assertEqual(sorted(n for _i, n, _f in stand), ["A", "B", "C"], stand)
        self.assertEqual([i for i, n, _f in stand if n == "A"], [5])
        self.assertTrue(all(i <= SF._GRUPPEN_ID_MAX for i, _n, _f in stand), stand)

    def test_die_groesste_erlaubte_id_bleibt(self):
        SF._restore_fixture_groups(self.state, [
            dict(_BASIS, name="A", id=SF._GRUPPEN_ID_MAX)])
        self.assertEqual(_stand(self.state), [(SF._GRUPPEN_ID_MAX, "A", "")])
        # … und eine weitere Gruppe laesst sich danach noch anlegen.
        neu = _gruppe(self.state, "Neu", "", [1])
        self.assertTrue(0 < neu < SF._GRUPPEN_ID_MAX, neu)


class NieGlobalTest(_MitState):
    """Ein Ziel-Blackout darf ins Leere gehen — aber nie zum globalen werden."""

    def test_geloeschte_gruppe_bleibt_fuer_alte_versionen_ein_ziel(self):
        gid = _gruppe(self.state, "PARs", "Back", [21])
        b = self._taste()
        b.blackout_group_ids = [gid]
        with self.state._session() as s:
            s.delete(s.get(FixtureGroup, gid))
            s.commit()
        d = json.loads(json.dumps(b.to_dict()))
        self.assertTrue(_alte_version_hat_ziel(d), d["blackout_groups"])
        # Der Platzhalter ist kein Alt-Name: die neue Version liest ihn nicht.
        neu = self._taste()
        neu.apply_dict(d)
        self.assertEqual(neu.blackout_group_ids, [gid])
        self.assertEqual(neu.blackout_groups, [])
        self.assertEqual(self._ziele(neu), set())

    def test_namenlose_gruppe_bleibt_fuer_alte_versionen_ein_ziel(self):
        gid = _gruppe(self.state, "", "", [21])
        b = self._taste()
        b.blackout_group_ids = [gid]
        d = b.to_dict()
        self.assertTrue(_alte_version_hat_ziel(d), d["blackout_groups"])
        # Der Platzhalter trifft in der alten Version keine Gruppe.
        for name in d["blackout_groups"]:
            self.assertEqual(self.state.group_cells_by_name(name), [])

    def test_benannte_gruppe_steht_weiter_mit_ihrem_namen_da(self):
        gid = _gruppe(self.state, "PARs", "Back", [21])
        b = self._taste()
        b.blackout_group_ids = [gid]
        self.assertEqual(b.to_dict()["blackout_groups"], ["PARs"])

    def test_nur_unlesbare_ids_fallen_auf_die_namen_zurueck(self):
        _gruppe(self.state, "PARs", "Back", [21])
        b = self._taste()
        b.apply_dict({"caption": "BO", "action": ButtonAction.BLACKOUT.value,
                      "blackout_group_ids": ["3", "4"], "blackout_groups": ["PARs"],
                      "blackout_groups_nur_name": []})
        self.assertEqual(b.blackout_group_ids, [])
        self.assertTrue(b.has_blackout_target())
        self.assertEqual(self._ziele(b), {21})

    def test_nur_unlesbares_ist_kein_globaler_blackout(self):
        for roh in (["x"], "3", [None, 2.5], {"a": 1}):
            b = self._taste()
            b.apply_dict({"caption": "BO", "action": ButtonAction.BLACKOUT.value,
                          "blackout_group_ids": roh})
            self.assertTrue(b.has_blackout_target(), roh)
            self.assertEqual(self._ziele(b), set(), roh)

    def test_ohne_ziel_bleibt_die_taste_global(self):
        """Gegenprobe: nichts davon macht aus einer Taste OHNE Ziel eine mit."""
        for d in ({}, {"blackout_group_ids": []}, {"blackout_groups": []},
                  {"blackout_group_ids": None, "blackout_fids": []}):
            b = self._taste()
            b.apply_dict(dict(d, caption="BO", action=ButtonAction.BLACKOUT.value))
            self.assertFalse(b.has_blackout_target(), d)
            self.assertNotIn("blackout_group_ids", b.to_dict())


class AltShowTest(_MitState):

    def test_alt_show_laden_speichern_laden_haelt_ids_und_ziel(self):
        """Der ganze Weg ueber echte Dateien: eine Show OHNE Gruppen-IDs laden,
        speichern, wieder laden — IDs und Ziel der Taste bleiben."""
        _gruppe(self.state, "PARs", "Front", [11, 12], gid=4)
        _gruppe(self.state, "PARs", "Back", [21, 22], gid=9)
        _gruppe(self.state, "Spots", "", [31], gid=12)
        tmp = tempfile.mkdtemp()
        neu = os.path.join(tmp, "neu.lshow")
        SF.save_show(neu)
        with zipfile.ZipFile(neu) as z:
            teile = {n: z.read(n) for n in z.namelist()}
        daten = json.loads(teile["show.json"])
        self.assertEqual([g["id"] for g in daten["fixture_groups"]], [4, 9, 12])
        for g in daten["fixture_groups"]:
            del g["id"]
        teile["show.json"] = json.dumps(daten).encode("utf-8")
        alt = os.path.join(tmp, "alt.lshow")
        with zipfile.ZipFile(alt, "w") as z:
            for n, inhalt in teile.items():
                z.writestr(n, inhalt)

        self.assertTrue(SF.load_show(alt)[0])
        erster = _stand(self.state)
        self.assertEqual(erster, [(1, "PARs", "Front"), (2, "PARs", "Back"),
                                  (3, "Spots", "")])
        b = self._taste()
        b.blackout_group_ids = [2]
        taste = json.loads(json.dumps(b.to_dict()))
        wieder = os.path.join(tmp, "wieder.lshow")
        SF.save_show(wieder)
        _gruppe(self.state, "Stoerer", "", [99])
        self.assertTrue(SF.load_show(wieder)[0])
        self.assertEqual(_stand(self.state), erster)
        nach = self._taste()
        nach.apply_dict(taste)
        self.assertEqual(self._ziele(nach), {21, 22})
        # Eine danach angelegte Gruppe stoert keine gespeicherte ID.
        self.assertEqual(_gruppe(self.state, "Neu", "", [5]), 4)


def _rgbw_baenke(n):
    chans, num = [], 1
    for _h in range(n):
        for attr in ("color_r", "color_g", "color_b", "color_w"):
            chans.append(NS(attribute=attr, channel_number=num, default_value=0))
            num += 1
    return chans


class UndoHaeltDieIdTest(unittest.TestCase):
    """Geraet loeschen + Ctrl+Z: die Kopf-Gruppe kommt mit IHRER ID zurueck."""

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
        for fid, label, addr in ((5, "HydraA", 1), (9, "HydraB", 33), (12, "HydraC", 65)):
            self.state.add_fixture(PatchedFixture(
                fid=fid, label=label, fixture_profile_id=1, mode_name="Standard",
                universe=1, address=addr, channel_count=16,
                fixture_type="moving_head"), undoable=True)

    def _gruppen(self) -> dict:
        with Session(self.state._show_engine) as s:
            return {g.id: g.name for g in s.execute(select(FixtureGroup)).scalars().all()}

    def _ziel(self, gid) -> set:
        slot = object()
        self.state.set_target_blackout(slot, [], [(gid, "")])
        return self.state._target_blackout_fids(self.state._ziel_blackout_specs[slot])

    def test_undo_gibt_der_gruppe_ihre_id_zurueck(self):
        for fid in (9, 12):          # mittlere und hoechste Nummer
            with self.subTest(fid=fid):
                gid = self.state.find_head_matrix_group(fid, dedicated=True)
                self.assertEqual(self._ziel(gid), {fid}, "VORBEDINGUNG")
                vorher = self._gruppen()
                self.state.remove_fixture(fid, undoable=True)
                self.assertEqual(self._ziel(gid), set())
                self.stack.undo()
                self.assertEqual(self._gruppen(), vorher)
                self.assertEqual(self._ziel(gid), {fid})

    def test_redo_und_erneutes_undo_halten_die_id(self):
        gid = self.state.find_head_matrix_group(9, dedicated=True)
        self.state.remove_fixture(9, undoable=True)
        self.stack.undo()
        self.stack.redo()
        self.assertEqual(self._ziel(gid), set())
        self.stack.undo()
        self.assertEqual(self._ziel(gid), {9})

    def test_belegte_id_wird_nicht_ueberschrieben(self):
        gid = self.state.find_head_matrix_group(9, dedicated=True)
        self.state.remove_fixture(9, undoable=True)
        with Session(self.state._show_engine) as s:
            s.add(FixtureGroup(id=gid, name="Fremd", cols=1, rows=1,
                               positions_json=json.dumps({"0,0": 5})))
            s.commit()
        self.stack.undo()
        g = self._gruppen()
        self.assertEqual(g.get(gid), "Fremd")
        self.assertIn("HydraB · Köpfe", g.values())
        self.assertEqual(self.state.group_fids_by_name("HydraB · Köpfe"), [9])


if __name__ == "__main__":
    unittest.main()
