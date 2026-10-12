"""VCB-36: das Ziel einer Blackout-Taste meint EINE Gruppe — auch wenn zwei
Gruppen gleich heissen.

Befund (Codex-Review #838): die Taste speicherte ihr Ziel als ``g:<Name>``.
Zwei Gruppen „PARs“ (etwa in den Ordnern „Front“ und „Back“) fielen in der
Auswahl zu EINEM Eintrag zusammen, und gedrueckt traf die Taste die erste.

„Gruppen-ID verwenden“ setzt voraus, dass die ID haelt. Das tat sie nicht: die
``.lshow`` speicherte Gruppen ohne ``id``, das Laden loeschte alle und legte sie
neu an — die IDs wurden 1..n neu vergeben. Eine gespeicherte ID haette nach
Speichern/Laden auf eine andere oder keine Gruppe gezeigt.

Deshalb zwei Teile:

* Die Show-Datei traegt die Gruppen-ID und stellt sie beim Laden wieder her
  (Alt-Shows ohne ``id`` bekommen wie bisher 1..n).
* Die Taste speichert Gruppen-IDs; die Auswahl fuehrt jede Gruppe einzeln.
  Namen aus alten Layouts bleiben lesbar und wirken wie bisher.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication             # noqa: E402
from sqlalchemy import delete, select                   # noqa: E402

from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15
from src.core.app_state import get_state                # noqa: E402
from src.core.database.models import FixtureGroup       # noqa: E402
from src.core.show import show_file as SF               # noqa: E402
from src.ui.virtualconsole import target_list_editor as tle   # noqa: E402
from src.ui.virtualconsole.vc_button import ButtonAction, VCButton   # noqa: E402

_app = QApplication.instance() or QApplication([])


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


def _ids_und_namen(state) -> list[tuple[int, str, str]]:
    with state._session() as s:
        return sorted((int(g.id), g.name, g.folder or "")
                      for g in s.execute(select(FixtureGroup)).scalars())


class _MitGruppen(unittest.TestCase):

    def setUp(self):
        self.state = get_state()
        _gruppen_leeren(self.state)
        # Zwei gleichnamige Gruppen in verschiedenen Ordnern, dazu eine dritte.
        self.front = _gruppe(self.state, "PARs", "Front", [11, 12])
        self.back = _gruppe(self.state, "PARs", "Back", [21, 22])
        self.spots = _gruppe(self.state, "Spots", "", [31])
        self.addCleanup(_gruppen_leeren, self.state)
        self.addCleanup(self.state.clear_all_target_blackouts)
        self.addCleanup(destroy_all_top_level_widgets, QApplication.instance())


class AuswahlTest(_MitGruppen):

    def test_gleichnamige_gruppen_stehen_einzeln_in_der_auswahl(self):
        wahl = dict(tle._blackout_choices())
        gruppen = {k: v for k, v in wahl.items() if not k.startswith("f:")}
        self.assertEqual(len(gruppen), 3, gruppen)
        self.assertIn(f"gi:{self.front}", gruppen)
        self.assertIn(f"gi:{self.back}", gruppen)
        # … und sind fuer den Bediener unterscheidbar (der Ordner steht dabei).
        self.assertNotEqual(gruppen[f"gi:{self.front}"], gruppen[f"gi:{self.back}"])
        self.assertIn("Front", gruppen[f"gi:{self.front}"])
        self.assertIn("Back", gruppen[f"gi:{self.back}"])

    def test_gleicher_name_im_selben_ordner_bleibt_unterscheidbar(self):
        zwilling = _gruppe(self.state, "PARs", "Front", [41])
        wahl = dict(tle._blackout_choices())
        self.assertNotEqual(wahl[f"gi:{self.front}"], wahl[f"gi:{zwilling}"])

    def test_editor_liefert_ids_und_namen_getrennt(self):
        ed = tle.BlackoutTargetEditor()
        ed.set_targets([f"gi:{self.back}", "g:Altname", "f:7"])
        self.assertEqual(ed.group_ids(), [self.back])
        self.assertEqual(ed.groups(), ["Altname"])
        self.assertEqual(ed.fids(), [7])

    def test_alter_name_wird_zur_id_wenn_er_eindeutig_ist(self):
        keys = tle.blackout_ziel_schluessel([], ["Spots"], [])
        self.assertEqual(keys, [f"gi:{self.spots}"])

    def test_mehrdeutiger_alter_name_bleibt_stehen_und_wird_benannt(self):
        """Welche der beiden „PARs“ gemeint war, weiss niemand — die Taste wirkt
        wie bisher (erste Gruppe), und der Editor sagt, dass neu zu waehlen ist."""
        keys = tle.blackout_ziel_schluessel([], ["PARs"], [])
        self.assertEqual(keys, ["g:PARs"])
        ed = tle.BlackoutTargetEditor()
        self.assertIn("mehrdeutig", ed._fehlt_label("g:PARs"))
        self.assertIn("nicht gefunden", ed._fehlt_label("g:Gibt es nicht"))
        self.assertIn("nicht gefunden", ed._fehlt_label("gi:99999"))

    def test_ids_stehen_vor_namen_und_geraeten(self):
        keys = tle.blackout_ziel_schluessel([7], ["Gibt es nicht"], [self.back])
        self.assertEqual(keys, [f"gi:{self.back}", "g:Gibt es nicht", "f:7"])


class ZielAufloesungTest(_MitGruppen):

    def _ziele(self, **kw):
        slot = object()
        self.state.set_target_blackout(slot, **kw)
        return self.state._target_blackout_ziele(self.state._ziel_blackout_specs[slot])[0]

    def test_id_trifft_genau_die_gewaehlte_gruppe(self):
        self.assertEqual(self._ziele(groups=[(self.back, "PARs")]), {21, 22})
        self.assertEqual(self._ziele(groups=[(self.front, "PARs")]), {11, 12})

    def test_beide_gleichnamigen_gruppen_zusammen(self):
        self.assertEqual(self._ziele(groups=[(self.front, ""), (self.back, "")]),
                         {11, 12, 21, 22})

    def test_name_wirkt_wie_bisher(self):
        self.assertEqual(self._ziele(groups=["Spots"]), {31})

    def test_umbenannte_gruppe_bleibt_das_ziel(self):
        with self.state._session() as s:
            s.get(FixtureGroup, self.back).name = "Hinten"
            s.commit()
        self.assertEqual(self._ziele(groups=[(self.back, "PARs")]), {21, 22})

    def test_geloeschte_gruppe_ist_kein_globaler_blackout(self):
        with self.state._session() as s:
            s.delete(s.get(FixtureGroup, self.back))
            s.commit()
        self.assertEqual(self._ziele(groups=[(self.back, "PARs")]), set())


class TasteTest(_MitGruppen):

    def _taste(self):
        b = VCButton("BO Back")
        b.action = ButtonAction.BLACKOUT
        return b

    def test_taste_mit_gruppen_id_hat_ein_ziel(self):
        b = self._taste()
        self.assertFalse(b.has_blackout_target())
        b.blackout_group_ids = [self.back]
        self.assertTrue(b.has_blackout_target())

    def test_druck_reicht_die_id_an_den_state(self):
        b = self._taste()
        b.blackout_group_ids = [self.back]
        b.blackout_groups = ["Spots"]
        b.blackout_fids = [5]
        with mock.patch.object(type(self.state), "set_target_blackout") as setzen:
            b._trigger_primary(True)
        self.assertEqual(setzen.call_count, 1)
        _slot, fids, gruppen = setzen.call_args[0]
        self.assertEqual(list(fids), [5])
        self.assertEqual([g if isinstance(g, str) else int(g[0]) for g in gruppen],
                         [self.back, "Spots"])

    def test_speichern_und_laden_der_taste(self):
        b = self._taste()
        b.blackout_group_ids = [self.back, self.spots]
        b.blackout_groups = ["Altname"]
        d = b.to_dict()
        self.assertEqual(d["blackout_group_ids"], [self.back, self.spots])
        self.assertEqual(d["blackout_groups_nur_name"], ["Altname"])
        neu = self._taste()
        neu.apply_dict(json.loads(json.dumps(d)))
        self.assertEqual(neu.blackout_group_ids, [self.back, self.spots])
        self.assertEqual(neu.blackout_groups, ["Altname"])

    def test_aeltere_programmversion_sieht_weiter_ein_ziel(self):
        """Eine aeltere Version kennt nur ``blackout_groups``. Bliebe das Feld
        leer, waere die Taste dort ein GLOBALER Blackout — deshalb stehen die
        Namen der ID-Ziele zusaetzlich drin."""
        b = self._taste()
        b.blackout_group_ids = [self.back, self.spots]
        self.assertEqual(sorted(b.to_dict()["blackout_groups"]), ["PARs", "Spots"])

    def test_altes_layout_laedt_wie_bisher(self):
        b = self._taste()
        b.apply_dict({"caption": "BO", "action": ButtonAction.BLACKOUT.value,
                     "blackout_fids": [3], "blackout_groups": ["Spots", "PARs"]})
        self.assertEqual(b.blackout_groups, ["Spots", "PARs"])
        self.assertEqual(b.blackout_group_ids, [])
        self.assertTrue(b.has_blackout_target())

    def test_unlesbare_ids_kosten_die_taste_nicht(self):
        b = self._taste()
        b.apply_dict({"caption": "BO", "action": ButtonAction.BLACKOUT.value,
                     "blackout_group_ids": [self.back, "x", None, self.back, -3, True, 2.5],
                     "blackout_groups": ["PARs"], "blackout_groups_nur_name": "kaputt"})
        self.assertEqual(b.blackout_group_ids, [self.back])
        self.assertEqual(b.blackout_groups, [])


class ShowDateiTest(_MitGruppen):
    """Ohne haltende IDs waere die Taste nach Speichern/Laden falsch verdrahtet."""

    def test_die_show_datei_traegt_die_gruppen_id(self):
        daten = SF._collect_fixture_groups(self.state, [])
        self.assertEqual(sorted(g["id"] for g in daten),
                         sorted([self.front, self.back, self.spots]))

    def test_ids_ueberleben_speichern_und_laden_auch_mit_luecken(self):
        _gruppen_leeren(self.state)
        _gruppe(self.state, "PARs", "Front", [11], gid=3)
        _gruppe(self.state, "PARs", "Back", [21], gid=7)
        daten = json.loads(json.dumps(SF._collect_fixture_groups(self.state, [])))
        _gruppen_leeren(self.state)
        _gruppe(self.state, "Fremd", "", [99])           # belegt die ID 1
        SF._restore_fixture_groups(self.state, daten)
        self.assertEqual(_ids_und_namen(self.state),
                         [(3, "PARs", "Front"), (7, "PARs", "Back")])

    def test_alt_show_ohne_ids_bekommt_wie_bisher_eins_bis_n(self):
        daten = [{"name": "A", "cols": 1, "rows": 1, "positions_json": "{}", "folder": ""},
                 {"name": "B", "cols": 1, "rows": 1, "positions_json": "{}", "folder": ""}]
        SF._restore_fixture_groups(self.state, daten)
        self.assertEqual(_ids_und_namen(self.state), [(1, "A", ""), (2, "B", "")])

    def test_doppelte_und_unlesbare_ids_kosten_keine_gruppe(self):
        """STAB-24 gilt weiter: EIN schlechter Eintrag darf nicht alle kosten —
        auch nicht ueber eine doppelte ID, an der die Transaktion scheitert."""
        basis = {"cols": 1, "rows": 1, "positions_json": "{}", "folder": ""}
        daten = [dict(basis, name="A", id=2), dict(basis, name="B"),
                 dict(basis, name="C", id=2), dict(basis, name="D", id="x"),
                 dict(basis, name="E", id=-5), dict(basis, name="F", id=True)]
        SF._restore_fixture_groups(self.state, daten)
        stand = _ids_und_namen(self.state)
        self.assertEqual(sorted(n for _i, n, _f in stand), list("ABCDEF"))
        self.assertEqual(len({i for i, _n, _f in stand}), 6, stand)
        self.assertEqual([i for i, n, _f in stand if n == "A"], [2])

    def test_taste_trifft_nach_speichern_und_laden_dieselbe_gruppe(self):
        _gruppen_leeren(self.state)
        _gruppe(self.state, "PARs", "Front", [11, 12], gid=4)
        back = _gruppe(self.state, "PARs", "Back", [21, 22], gid=9)
        b = VCButton("BO Back")
        b.action = ButtonAction.BLACKOUT
        b.blackout_group_ids = [back]
        taste = json.loads(json.dumps(b.to_dict()))
        gruppen = json.loads(json.dumps(SF._collect_fixture_groups(self.state, [])))
        # „Laden“: Gruppen neu anlegen, Taste neu aufbauen.
        SF._restore_fixture_groups(self.state, gruppen)
        neu = VCButton("x")
        neu.apply_dict(taste)
        slot = object()
        self.state.set_target_blackout(
            slot, neu.blackout_fids, [(g, "") for g in neu.blackout_group_ids])
        ganz, _koepfe = self.state._target_blackout_ziele(
            self.state._ziel_blackout_specs[slot])
        self.assertEqual(ganz, {21, 22})


if __name__ == "__main__":
    unittest.main()
