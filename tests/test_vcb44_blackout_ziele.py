"""VCB-44: Blackout-Ziele — drei Befunde aus dem grossen Bedientest QA-96.

(a) Eine geloeschte und unter demselben Namen neu angelegte Gruppe uebernahm
    das Blackout-Ziel der alten. Die Regel dazu steht in ``group_ref.ziel_gilt``
    und ist in ``test_vcb42_blackout_ziel_wiedererkennen.py`` festgehalten; hier
    der Fall am Druck der Taste.
(c) Im Ziel-Dialog machte eine leer gelassene Zeile die Taste still zum
    GLOBALEN Blackout.
(d) „Show pruefen & reparieren“ meldete „sauber“ trotz verlorenem Ziel — und
    reparierte ohne Rueckfrage, noch bevor der Dialog erschien.

(b) aus demselben Block — die gehaltene Taste hebt einen fremden Blackout auf —
ist VCB-43.
"""
from __future__ import annotations

import json
import os
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox   # noqa: E402

from sqlalchemy import delete                                       # noqa: E402

from _qt_lifecycle import destroy_all_top_level_widgets             # noqa: E402
from src.core import sync                                           # noqa: E402
from src.core.app_state import get_state                            # noqa: E402
from src.core.capability.validate import blackout_ziel_befunde      # noqa: E402
from src.core.database.models import FixtureGroup                   # noqa: E402
from src.ui.virtualconsole import target_list_editor as tle         # noqa: E402
from src.ui.virtualconsole.vc_button import ButtonAction, VCButton  # noqa: E402
from src.ui.widgets.validation_dialog import ValidationDialog       # noqa: E402

_app = QApplication.instance() or QApplication([])


def _gruppen_leeren(state):
    with state._session() as s:
        s.execute(delete(FixtureGroup))
        s.commit()


def _gruppe(state, name, folder, fids) -> int:
    pos = {f"{i},0": fid for i, fid in enumerate(fids)}
    with state._session() as s:
        g = FixtureGroup(name=name, folder=folder, cols=max(1, len(fids)), rows=1,
                         positions_json=json.dumps(pos))
        s.add(g)
        s.commit()
        return int(g.id)


def _loeschen(state, gid):
    with state._session() as s:
        s.execute(delete(FixtureGroup).where(FixtureGroup.id == gid))
        s.commit()


class _MitState(unittest.TestCase):

    def setUp(self):
        self.state = get_state()
        _gruppen_leeren(self.state)
        self.addCleanup(_gruppen_leeren, self.state)
        self.addCleanup(self.state.clear_all_target_blackouts)
        self.addCleanup(destroy_all_top_level_widgets, QApplication.instance())
        self.front = _gruppe(self.state, "PARs", "Front", [11, 12])
        self.back = _gruppe(self.state, "PARs", "Back", [21, 22])

    def _taste(self, *gids):
        b = VCButton("BO")
        b.action = ButtonAction.BLACKOUT
        if gids:
            b.blackout_gruppen_waehlen(list(gids))
        return b


# ══════════════════════════════════════════════════════════════════════════════
# (a) Geloescht und gleichnamig neu angelegt
# ══════════════════════════════════════════════════════════════════════════════

class GleichnamigNeuAngelegtTest(_MitState):

    def test_der_druck_schaltet_die_neue_gruppe_nicht(self):
        b = self._taste(self.back)
        _loeschen(self.state, self.back)
        neu = _gruppe(self.state, "PARs", "Back", [41, 42])
        self.assertEqual(neu, self.back, "VORBEDINGUNG: die Nummer wird wiederverwendet")
        with mock.patch.object(type(self.state), "set_target_blackout") as ziel, \
                mock.patch.object(self.state.output_manager, "set_blackout") as glob, \
                mock.patch.object(VCButton, "_show_status") as status:
            b._trigger_primary(True)
        self.assertEqual(glob.call_count, 0, "nie global")
        self.assertEqual(status.call_count, 1, "und es wird gesagt")
        self.assertIn("PARs", status.call_args[0][0])
        ziele = ziel.call_args[0][2] if ziel.call_count else []
        slot = object()
        self.state.set_target_blackout(slot, [], ziele)
        self.assertEqual(
            self.state._target_blackout_fids(self.state._ziel_blackout_specs[slot]), set(),
            "die neue Gruppe erbt das Ziel der alten nicht")


# ══════════════════════════════════════════════════════════════════════════════
# (c) Leere Zeile im Ziel-Dialog
# ══════════════════════════════════════════════════════════════════════════════

class LeereZeileTest(_MitState):

    def _einstellungen(self, b):
        """Die Einstellungs-Struktur des Tasten-Dialogs (ohne ihn zu zeigen)."""
        self.dlg = QDialog()
        return b._build_settings(self.dlg, live=False)

    def _frage(self, antwort):
        self.fragen = []

        def frage(_parent, titel, text, *a, **k):
            self.fragen.append(f"{titel}\n{text}")
            return antwort
        return mock.patch.object(QMessageBox, "question", staticmethod(frage))

    def test_editor_erkennt_nur_leere_zeilen(self):
        ed = tle.BlackoutTargetEditor()
        self.assertFalse(ed.nur_leere_zeilen(), "ganz ohne Zeilen = ausdruecklich global")
        ed._add_row(None, "")
        self.assertTrue(ed.nur_leere_zeilen())
        ed._add_row(f"gi:{self.back}", "")
        self.assertFalse(ed.nur_leere_zeilen())

    def test_leere_zeile_macht_ein_ziel_nicht_still_global(self):
        """Der Fall aus dem Befund: die Taste hat ein Ziel, die Zeile wird auf
        „(leer)“ gestellt, OK."""
        b = self._taste(self.back)
        S = self._einstellungen(b)
        ed = S["blackout_editor"]
        ed._rows[0]["func"].setCurrentIndex(0)             # „(leer)“
        self.assertTrue(ed.nur_leere_zeilen(), "VORBEDINGUNG")
        with mock.patch.object(VCButton, "_show_status") as status:
            S["apply"]()
        self.assertEqual(b.blackout_group_ids, [self.back], "das Ziel bleibt")
        self.assertTrue(b.has_blackout_target())
        self.assertEqual(status.call_count, 1)
        self.assertIn("leere Zeile", status.call_args[0][0])

    def test_ok_fragt_und_nein_laesst_den_dialog_offen(self):
        b = self._taste(self.back)
        S = self._einstellungen(b)
        S["blackout_editor"]._rows[0]["func"].setCurrentIndex(0)
        with self._frage(QMessageBox.StandardButton.No):
            self.assertFalse(b._blackout_leer_bestaetigt(S, self.dlg))
        self.assertEqual(len(self.fragen), 1)
        self.assertIn("ALLES dunkel", self.fragen[0])
        self.assertIn("globaler Blackout", self.fragen[0])

    def test_ja_macht_sie_ausdruecklich_global(self):
        b = self._taste(self.back)
        S = self._einstellungen(b)
        S["blackout_editor"]._rows[0]["func"].setCurrentIndex(0)
        with self._frage(QMessageBox.StandardButton.Yes):
            self.assertTrue(b._blackout_leer_bestaetigt(S, self.dlg))
        S["apply"]()
        self.assertFalse(b.has_blackout_target(), "ausdruecklich bestaetigt")
        self.assertEqual(b.blackout_group_ids, [])

    def test_neue_taste_mit_leerer_zeile_wird_ebenfalls_gefragt(self):
        b = self._taste()
        S = self._einstellungen(b)
        S["blackout_editor"]._add_row(None, "")
        with self._frage(QMessageBox.StandardButton.No):
            self.assertFalse(b._blackout_leer_bestaetigt(S, self.dlg))
        self.assertEqual(len(self.fragen), 1)

    def test_gewaehltes_ziel_und_keine_zeile_fragen_nicht(self):
        with self._frage(QMessageBox.StandardButton.No):
            mit_ziel = self._taste(self.back)
            self.assertTrue(mit_ziel._blackout_leer_bestaetigt(
                self._einstellungen(mit_ziel), None))
            ohne = self._taste()
            self.assertTrue(ohne._blackout_leer_bestaetigt(self._einstellungen(ohne), None))
        self.assertEqual(self.fragen, [])

    def test_alle_zeilen_entfernt_bleibt_der_ausdrueckliche_globale_blackout(self):
        b = self._taste(self.back)
        S = self._einstellungen(b)
        ed = S["blackout_editor"]
        ed._remove_row(ed._rows[0])
        self.assertFalse(ed.nur_leere_zeilen())
        S["apply"]()
        self.assertFalse(b.has_blackout_target())

    def test_andere_aktion_wird_nicht_gefragt(self):
        b = self._taste(self.back)
        S = self._einstellungen(b)
        S["blackout_editor"]._rows[0]["func"].setCurrentIndex(0)
        combo = S["action_combo"]
        combo.setCurrentIndex(combo.findData(ButtonAction.TOGGLE.value))
        with self._frage(QMessageBox.StandardButton.No):
            self.assertTrue(b._blackout_leer_bestaetigt(S, self.dlg))
        self.assertEqual(self.fragen, [])

    def test_die_vorgabe_der_frage_ist_nein(self):
        import inspect
        quelle = inspect.getsource(VCButton._blackout_leer_bestaetigt)
        self.assertIn("QMessageBox.StandardButton.No)", quelle)


# ══════════════════════════════════════════════════════════════════════════════
# (d) Show-Pruefung
# ══════════════════════════════════════════════════════════════════════════════

class ShowPruefungTest(_MitState):

    def _layout(self, *tasten) -> dict:
        return {"widgets": [json.loads(json.dumps(t.to_dict())) for t in tasten]}

    def _befunde(self, layout):
        return blackout_ziel_befunde(layout["widgets"], self.state.gruppen_steckbriefe())

    def test_gueltiges_ziel_kein_befund(self):
        self.assertEqual(self._befunde(self._layout(self._taste(self.back))), [])

    def test_verlorenes_ziel_wird_gemeldet(self):
        layout = self._layout(self._taste(self.back))
        _loeschen(self.state, self.back)
        befunde = self._befunde(layout)
        self.assertEqual(len(befunde), 1)
        self.assertEqual(befunde[0].code, "VC-BLACKOUT-ZIEL")
        self.assertIn("PARs", befunde[0].message)
        self.assertIn("Back", befunde[0].message)
        self.assertIn("'BO'", befunde[0].where)

    def test_gleichnamig_neu_angelegt_wird_gemeldet(self):
        layout = self._layout(self._taste(self.back))
        _loeschen(self.state, self.back)
        _gruppe(self.state, "PARs", "Back", [41])
        self.assertEqual(len(self._befunde(layout)), 1)

    def test_globale_taste_und_andere_aktionen_kein_befund(self):
        andere = VCButton("X")
        andere.action = ButtonAction.TOGGLE
        self.assertEqual(self._befunde(self._layout(self._taste(), andere)), [])

    def test_taste_in_einem_rahmen_wird_gefunden(self):
        d = json.loads(json.dumps(self._taste(self.back).to_dict()))
        _loeschen(self.state, self.back)
        widgets = [{"type": "VCFrame", "caption": "Licht", "children": [d]}]
        befunde = blackout_ziel_befunde(widgets, self.state.gruppen_steckbriefe())
        self.assertEqual(len(befunde), 1)
        self.assertIn("Licht", befunde[0].where)

    def test_alter_name_ohne_gruppe_und_mehrdeutig(self):
        alt = {"type": "VCButton", "caption": "Alt", "action": "Blackout",
               "blackout_groups": ["Gibt es nicht", "PARs"]}
        texte = [b.message for b in blackout_ziel_befunde(
            [alt], self.state.gruppen_steckbriefe())]
        self.assertEqual(len(texte), 2)
        self.assertIn("gibt es nicht", texte[0])
        self.assertIn("mehrdeutig", texte[1])

    def test_kaputte_eintraege_kosten_die_pruefung_nicht(self):
        kaputt = [None, "x", {"action": "Blackout", "blackout_group_ids": "abc",
                              "blackout_group_refs": [5, {"id": "x"}],
                              "blackout_groups": [3, None, ""]}]
        self.assertEqual(blackout_ziel_befunde(kaputt, {}), [])

    def test_die_show_pruefung_meldet_nicht_mehr_sauber(self):
        """Der Befund: ``validate_and_repair`` lieferte fuer diese Show nichts."""
        layout = self._layout(self._taste(self.back))
        _loeschen(self.state, self.back)
        alt = getattr(self.state, "_vc_layout", None)
        self.state._vc_layout = layout
        self.addCleanup(setattr, self.state, "_vc_layout", alt)
        issues = sync.validate_and_repair(self.state, fix=False)
        treffer = [i for i in issues if "Blackout-Ziel verloren" in i.message]
        self.assertEqual(len(treffer), 1)
        self.assertEqual(treffer[0].severity, "warn")
        self.assertFalse(treffer[0].auto_fixed, "nur melden, nie raten")
        self.assertIsNotNone(sync.banner_zusammenfassung(issues))

    def test_unlesbare_show_db_behauptet_keinen_verlust(self):
        layout = self._layout(self._taste(self.back))
        stub = types.SimpleNamespace(
            _vc_layout=layout, gruppen_steckbriefe=lambda: None,
            get_patched_fixtures=lambda: [], programmer={}, cue_stacks=[])
        issues = sync.validate_and_repair(stub, fix=False)
        self.assertFalse([i for i in issues if "Blackout-Ziel" in i.message])


class ErstPruefenDannReparierenTest(unittest.TestCase):
    """„Show pruefen & reparieren“ veraenderte die Show, bevor der Dialog
    erschien. Jetzt: pruefen, zeigen, und nur auf „Reparieren“ aendern."""

    def setUp(self):
        self.addCleanup(destroy_all_top_level_widgets, QApplication.instance())

    def _state(self):
        return types.SimpleNamespace(
            get_patched_fixtures=lambda: [], programmer={7: {"intensity": 255}},
            cue_stacks=[], _vc_layout=None)

    def test_pruefen_allein_aendert_nichts_und_sagt_was_reparierbar_waere(self):
        st = self._state()
        issues = sync.validate_and_repair(st, fix=False)
        self.assertEqual(st.programmer, {7: {"intensity": 255}})
        offen = [i for i in issues if getattr(i, "reparierbar", False)]
        self.assertEqual(len(offen), 1)
        self.assertIn("verwaiste fids", offen[0].message)
        self.assertFalse(offen[0].auto_fixed)

    def test_reparieren_meldet_behoben_und_nicht_mehr_reparierbar(self):
        st = self._state()
        issues = sync.validate_and_repair(st, fix=True)
        self.assertEqual(st.programmer, {})
        self.assertTrue(all(not getattr(i, "reparierbar", False) for i in issues))
        self.assertTrue(any(i.auto_fixed for i in issues))

    def test_dialog_bietet_reparieren_an_und_fuehrt_es_erst_auf_klick_aus(self):
        st = self._state()
        gerufen = []

        def reparieren():
            gerufen.append(1)
            return sync.validate_and_repair(st, fix=True)

        dlg = ValidationDialog(sync.validate_and_repair(st, fix=False), None,
                               reparieren=reparieren)
        self.assertIsNotNone(dlg._btn_reparieren)
        self.assertIn("Reparieren (1)", dlg._btn_reparieren.text())
        self.assertEqual(gerufen, [], "der Dialog allein repariert nichts")
        self.assertEqual(st.programmer, {7: {"intensity": 255}})
        dlg._btn_reparieren.click()
        self.assertEqual(gerufen, [1])
        self.assertEqual(st.programmer, {})
        self.assertTrue(dlg.repariert)
        self.assertIsNone(dlg._btn_reparieren, "danach gibt es nichts mehr zu reparieren")

    def test_ohne_reparierbares_kein_knopf(self):
        st = types.SimpleNamespace(get_patched_fixtures=lambda: [], programmer={},
                                   cue_stacks=[], _vc_layout=None)
        dlg = ValidationDialog(sync.validate_and_repair(st, fix=False), None,
                               reparieren=lambda: [])
        self.assertIsNone(dlg._btn_reparieren)

    def test_dialog_ohne_reparatur_funktion_wie_bisher(self):
        dlg = ValidationDialog([sync.ValidationIssue("warn", "X", "y", reparierbar=True)])
        self.assertIsNone(dlg._btn_reparieren)

    def test_das_menue_prueft_erst(self):
        import inspect
        from src.ui import main_window
        quelle = inspect.getsource(main_window.MainWindow._validate_show)
        erst = quelle.index("validate_and_repair(self._state, fix=False)")
        dann = quelle.index("validate_and_repair(self._state, fix=True)")
        self.assertLess(erst, dann)
        self.assertIn("reparieren=lambda", quelle)


if __name__ == "__main__":
    unittest.main()
