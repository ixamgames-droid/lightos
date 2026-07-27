"""FM-HEADLAYOUT Slice 5 (Variante A, Teil 1): der KOPF als selektierbares Ziel.

Davids Wunsch „Kopf = eigenes Fixture" — Variante A erweitert das Auswahlmodell
selbst, statt nur einen Schreib-Filter danebenzustellen.

Kern-Vertrag:
* ``AppState.selected_cells`` ist die feine Auswahl (``"fid"`` ODER ``"fid:head"``,
  dieselbe Syntax wie Gruppen-Zellen), ``selected_fids`` bleibt die dedup-Basisliste
  und damit der UNVERÄNDERTE Vertrag aller SELECTION_CHANGED-Konsumenten.
* Beide werden ausschliesslich in ``set_selected_cells`` fortgeschrieben —
  ``set_selected_fids`` delegiert dorthin, damit die feine Auswahl nie veraltet
  (die Fehlerklasse „zweites Feld, das ein Schreiber vergisst").
* Im Programmer erzeugt jedes Mehrkopf-Gerät Kopf-Zeilen; ist nur ein Kopf
  gewählt, zeigt der Color-Tab auch nur dessen Regler.
"""
from __future__ import annotations
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.show.show_file import reset_show
from src.core.sync import SyncEvent, get_sync
from src.ui.views.programmer_view import ProgrammerView, AttributeSlider


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one())


class SelectionModelTest(unittest.TestCase):
    """Kern: Zell-Auswahl, Basisliste, Kopf-Abfrage, Emit-Vertrag."""

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()

    def test_whole_device_selection_is_unchanged_contract(self):
        self.state.set_selected_fids([3, 1])
        self.assertEqual(self.state.get_selected_fids(), [3, 1])
        self.assertEqual(self.state.get_selected_cells(), ["3", "1"])
        self.assertIsNone(self.state.selected_heads_for(3),
                          "ganzes Gerät muss 'alle Köpfe' bedeuten")

    def test_head_cells_produce_base_fids_in_order(self):
        self.state.set_selected_cells(["7:1", "7:3", "4"])
        self.assertEqual(self.state.get_selected_fids(), [7, 4])
        self.assertEqual(self.state.selected_heads_for(7), {1, 3})
        self.assertIsNone(self.state.selected_heads_for(4))

    def test_unselected_device_reports_empty_set(self):
        self.state.set_selected_cells(["7:1"])
        self.assertEqual(self.state.selected_heads_for(9), set())

    def test_whole_device_beats_its_own_head_entries(self):
        # Sonst wäre unklar, ob „alle Köpfe" oder „nur diese" gemeint ist.
        self.state.set_selected_cells(["5:0", "5", "5:2"])
        self.assertEqual(self.state.get_selected_cells(), ["5"])
        self.assertIsNone(self.state.selected_heads_for(5))

    def test_duplicates_are_dropped_order_preserved(self):
        self.state.set_selected_cells(["2:0", "2:0", "1", "2:1"])
        self.assertEqual(self.state.get_selected_cells(), ["2:0", "1", "2:1"])
        self.assertEqual(self.state.get_selected_fids(), [2, 1])

    def test_garbage_entries_are_ignored(self):
        self.state.set_selected_cells(["1", "quatsch", None, "2:x", "3:1"])
        self.assertEqual(self.state.get_selected_fids(), [1, 3])

    def test_set_selected_fids_keeps_cells_in_sync(self):
        # Der eigentliche Schutz gegen ein veraltetes Zweitfeld: der Bestandsweg
        # muss die feine Auswahl MITziehen, nicht danebenlaufen lassen.
        self.state.set_selected_cells(["8:2"])
        self.assertEqual(self.state.selected_heads_for(8), {2})
        self.state.set_selected_fids([8])
        self.assertEqual(self.state.get_selected_cells(), ["8"])
        self.assertIsNone(self.state.selected_heads_for(8),
                          "alte Kopf-Einschränkung überlebte set_selected_fids")

    def _record_selection_events(self) -> list:
        """Subscriber, der die SELECTION_CHANGED-Nutzlast mitschreibt.

        ⚠ Die Callback-Signatur ist ``(event, data)``. Nimmt der Callback nur ein
        Argument, wirft er — und ``StateSync.emit`` fängt Subscriber-Fehler
        bewusst ab (ein kaputter Abonnent darf die anderen nicht mitreissen). Das
        Event kommt dann STILL nicht an; ein Test, der nur „kein Absturz" prüft,
        wäre hier falsch-grün."""
        seen: list = []
        cb = lambda _ev, data: seen.append(data)   # noqa: E731
        get_sync().subscribe(SyncEvent.SELECTION_CHANGED, cb)
        self.addCleanup(get_sync().unsubscribe, SyncEvent.SELECTION_CHANGED, cb)
        return seen

    def test_selection_changed_carries_base_fids(self):
        seen = self._record_selection_events()
        self.state.set_selected_cells(["6:0", "6:1", "7"])
        self.assertEqual(seen[-1], [6, 7],
                         "SELECTION_CHANGED muss weiter die fid-Liste tragen")

    def test_no_emit_when_selection_is_unchanged(self):
        self.state.set_selected_cells(["6:0"])
        seen = self._record_selection_events()
        self.state.set_selected_cells(["6:0"])
        self.assertEqual(seen, [], "identische Auswahl darf kein Event feuern")

    def test_head_change_within_same_device_still_emits(self):
        # Basisliste bleibt [6] — trotzdem hat sich die Auswahl geändert.
        self.state.set_selected_cells(["6:0"])
        seen = self._record_selection_events()
        self.state.set_selected_cells(["6:1"])
        self.assertEqual(len(seen), 1, "Kopfwechsel wurde verschluckt")
        self.assertEqual(self.state.selected_heads_for(6), {1})


class ProgrammerHeadRowsTest(unittest.TestCase):
    """Programmer-Geräteliste: Kopf-Zeilen, Auswahl-Publikation, Regler-Filter."""

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        self.state.add_fixture(PatchedFixture(
            fid=1, label="Spider", fixture_profile_id=_pid("SPIDER14"),
            mode_name="14-Kanal", universe=1, address=1, channel_count=14,
            manufacturer_name="U King", fixture_name="Spider 14ch",
            fixture_type="moving_head"), undoable=False)
        self.state.add_fixture(PatchedFixture(
            fid=2, label="PAR", fixture_profile_id=_pid("ZQ01424"),
            mode_name="8-Kanal RGBW", universe=1, address=20, channel_count=8,
            manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
            fixture_type="par"), undoable=False)
        self.view = ProgrammerView()
        self.addCleanup(self.view.deleteLater)
        self._hosts: list = []

    def _rows(self):
        lst = self.view._fixture_list
        return [(i, lst.item(i).data(Qt.ItemDataRole.UserRole))
                for i in range(lst.count())]

    def _select_rows(self, cells):
        lst = self.view._fixture_list
        lst.clearSelection()
        for i in range(lst.count()):
            if lst.item(i).data(Qt.ItemDataRole.UserRole) in cells:
                lst.item(i).setSelected(True)
        self.view._on_fixture_selected()

    def _color_sliders(self, fixtures):
        host = QWidget()
        self._hosts.append(host)          # Qt-GC: Host am Leben halten
        lay = QVBoxLayout(host)
        self.view._add_color_head_sliders(lay, fixtures)
        return [w for w in (lay.itemAt(i).widget() for i in range(lay.count()))
                if isinstance(w, AttributeSlider)]

    def _fx(self, fid):
        return next(f for f in self.state.get_patched_fixtures() if f.fid == fid)

    def test_multihead_device_gets_head_rows_single_head_does_not(self):
        cells = [c for _i, c in self._rows()]
        self.assertIn("1", cells)
        self.assertIn("1:0", cells)
        self.assertIn("1:1", cells)
        self.assertIn("2", cells)
        self.assertNotIn("2:0", cells, "Einzelkopf-PAR bekam Kopf-Zeilen")

    def test_head_mode_single_suppresses_head_rows(self):
        self.state.update_fixture(1, head_mode="single", undoable=False)
        self.view._refresh_fixture_list()
        cells = [c for _i, c in self._rows()]
        self.assertNotIn("1:0", cells,
                         "'Als eine Lampe' darf keine Kopf-Zeilen anbieten")

    def test_selecting_a_head_publishes_cell_selection(self):
        self._select_rows({"1:1"})
        self.assertEqual(self.state.get_selected_cells(), ["1:1"])
        self.assertEqual(self.state.get_selected_fids(), [1])
        self.assertEqual(self.state.selected_heads_for(1), {1})

    def test_selecting_device_row_selects_all_heads(self):
        self._select_rows({"1"})
        self.assertIsNone(self.state.selected_heads_for(1))

    def test_only_selected_head_gets_sliders(self):
        self._select_rows({"1:1"})
        sliders = self._color_sliders([self._fx(1)])
        self.assertTrue(sliders, "keine Regler für den gewählten Kopf")
        self.assertEqual({s._head for s in sliders}, {1},
                         "Regler anderer Köpfe erschienen trotz Kopf-Auswahl")

    def test_head_selection_beats_sync_mode(self):
        # Auch wenn global/pro Gerät „synchron" gilt: die Kopf-Wahl ist eine
        # ausdrückliche Ansage und muss Pro-Kopf-Regler liefern.
        self.view._color_head_mode = "sync"
        self._select_rows({"1:0"})
        sliders = self._color_sliders([self._fx(1)])
        self.assertEqual({s._head for s in sliders}, {0})
        self.assertTrue(all(s._sync_heads == 0 for s in sliders),
                        "Synchron-Regler trotz Kopf-Auswahl")

    def test_writing_via_head_slider_hits_only_that_bank(self):
        self._select_rows({"1:1"})
        sliders = self._color_sliders([self._fx(1)])
        red = next(s for s in sliders if s._channel.attribute == "color_r")
        red._slider.setValue(200)
        self.assertEqual(self.state.get_programmer_value(1, "color_r", head=1), 200)
        self.assertIsNone(self.state.get_programmer_value(1, "color_r", head=0),
                          "Kopf 0 wurde mitgeschrieben")

    def test_group_selection_still_selects_device_rows(self):
        # FM16E-Fehlerklasse: die Zell-Strings dürfen die fid-basierte
        # Gruppen-/Preset-Auswahl nicht ins Leere laufen lassen.
        self.view._select_fids([1, 2])
        self.assertEqual(self.view._selected_fids, [1, 2])
        self.assertEqual(self.state.get_selected_cells(), ["1", "2"])
        sel = {self.view._fixture_list.item(i).data(Qt.ItemDataRole.UserRole)
               for i in range(self.view._fixture_list.count())
               if self.view._fixture_list.item(i).isSelected()}
        self.assertEqual(sel, {"1", "2"},
                         "Gruppenauswahl markierte Kopf-Zeilen oder gar nichts")

    def test_head_selection_pins_the_global_switch(self):
        # „Sichtbarer Zustand != Logikzustand" (Fallenklasse 12): der globale
        # Umschalter darf nicht „Synchron" behaupten, während sichtbar Pro-Kopf-
        # Regler stehen. Er zählt das Gerät mit Kopf-Auswahl nicht mehr mit.
        self._select_rows({"1"})
        self.assertTrue(self.view._has_auto_mode_color_head_fixture())
        self._select_rows({"1:1"})
        self.assertFalse(self.view._has_auto_mode_color_head_fixture(),
                         "Umschalter blieb bedienbar, obwohl die Kopf-Wahl ihn "
                         "überstimmt")

    def test_header_names_the_selected_head(self):
        self._select_rows({"1:1"})
        self.assertIn("K2", self.view._lbl_selection.text(),
                      "Kopfzeile nennt nur das Gerät, obwohl nur ein Kopf gewählt ist")
        self._select_rows({"1"})
        self.assertNotIn("K2", self.view._lbl_selection.text(),
                         "Kopf-Zusatz blieb stehen, obwohl das ganze Gerät gewählt ist")

    def test_external_head_selection_is_mirrored_into_the_list(self):
        self.state.set_selected_cells(["1:0"])
        self.view._sync_follow_selection()
        sel = {self.view._fixture_list.item(i).data(Qt.ItemDataRole.UserRole)
               for i in range(self.view._fixture_list.count())
               if self.view._fixture_list.item(i).isSelected()}
        self.assertEqual(sel, {"1:0"})


if __name__ == "__main__":
    unittest.main()
