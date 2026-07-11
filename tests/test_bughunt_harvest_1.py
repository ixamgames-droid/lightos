"""Bug-Hunt-Harvest 1 (adversariale UI-Bug-Jagd 2026-07-09) — 3 bestätigte Fixes.

- Chaser-Editor `_move_down` ohne Auswahl (currentRow()==-1) vertauschte ersten+letzten
  Schritt (fehlender `row >= 0`-Guard, den `_move_up` hat).
- Show-Manager-Timeline: Linksklick crashte mit TypeError, weil `_sf_at` `y` (float aus
  event.position()) ungecastet als Listenindex `show.tracks[row]` nutzte.
- Output-Konfig: Enttec/Art-Net/sACN-Quick-Apply-Universe-Felder waren auf 1-16 begrenzt
  statt 1-32 (Universen-Manager + „Maximal 32 Universen" nutzen 32).
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.views.chaser_editor import ChaserEditor
from src.ui.views.show_manager_view import TimelineCanvas, RULER_H, TRACK_H

_app = QApplication.instance() or QApplication([])


class ChaserMoveDownGuardTest(unittest.TestCase):
    def _fake(self, current_row):
        steps = [SimpleNamespace(function_id=i) for i in range(3)]
        fake = SimpleNamespace(
            _table=SimpleNamespace(currentRow=lambda: current_row,
                                   selectRow=lambda r: None),
            _chaser=SimpleNamespace(steps=steps),
            _rebuild_table=lambda: None,
        )
        return fake, steps

    def test_move_down_without_selection_is_noop(self):
        fake, steps = self._fake(current_row=-1)   # keine Auswahl
        ChaserEditor._move_down(fake)
        self.assertEqual([s.function_id for s in steps], [0, 1, 2])  # unveraendert

    def test_move_down_with_selection_swaps(self):
        fake, steps = self._fake(current_row=0)
        ChaserEditor._move_down(fake)
        self.assertEqual([s.function_id for s in steps], [1, 0, 2])  # 0<->1

    def test_move_down_on_last_row_is_noop(self):
        fake, steps = self._fake(current_row=2)
        ChaserEditor._move_down(fake)
        self.assertEqual([s.function_id for s in steps], [0, 1, 2])


class TimelineSfAtFloatTest(unittest.TestCase):
    def test_sf_at_tolerates_float_y(self):
        """_sf_at bekommt float-y aus event.position() -> darf show.tracks[row]
        nicht mit float indizieren (TypeError). Row muss int-gecastet sein."""
        track = SimpleNamespace(show_functions=[])
        show = SimpleNamespace(tracks=[track])
        fake = SimpleNamespace(_show=lambda: show)
        # y in Track 0 (RULER_H + halbe Track-Hoehe), als float
        sf, tr = TimelineCanvas._sf_at(fake, 10.0, float(RULER_H) + TRACK_H / 2.0)
        self.assertIs(tr, track)
        self.assertIsNone(sf)

    def test_sf_at_above_tracks_returns_none(self):
        show = SimpleNamespace(tracks=[])
        fake = SimpleNamespace(_show=lambda: show)
        sf, tr = TimelineCanvas._sf_at(fake, 5.0, float(RULER_H) + 5.0)
        self.assertIsNone(sf)
        self.assertIsNone(tr)


class OutputConfigUniverseRangeTest(unittest.TestCase):
    def test_quick_apply_universe_spinboxes_go_to_32(self):
        """Enttec/Art-Net/sACN-Quick-Apply-Felder muessen bis 32 gehen (wie der
        Universen-Manager), nicht nur bis 16."""
        from src.ui.widgets.output_config import OutputConfigDialog
        dlg = OutputConfigDialog()
        try:
            self.assertEqual(dlg._spin_enttec_univ.maximum(), 32)
            self.assertEqual(dlg._spin_artnet_univ.maximum(), 32)
            self.assertEqual(dlg._spin_sacn_univ.maximum(), 32)
        finally:
            dlg.deleteLater()
            _app.processEvents()


if __name__ == "__main__":
    unittest.main()
