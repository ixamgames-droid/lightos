"""B3-UI (headless): MusicView Auto-Show-Spalte/Zuweisung (AUTODJ-a), BPM-aus-Tag-Button
(F-15) und das Spektrum-Widget (AUTODJ-b)."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QMessageBox

from src.core.audio.media_player import Track, get_media_player
from src.ui.views.music_view import MusicView
from src.ui.views.spectrum_bars import SpectrumBars

_app = QApplication.instance() or QApplication([])


class MusicViewAutoDjTest(unittest.TestCase):
    def setUp(self):
        self.mp = get_media_player()
        self.mp.set_tracks([Track(path="a.mp3"), Track(path="b.mp3")])
        self.view = MusicView()

    def tearDown(self):
        self.view.deleteLater()
        self.mp.set_tracks([])

    def test_table_has_autoshow_column(self):
        self.assertEqual(self.view._table.columnCount(), 5)
        self.assertEqual(self.view._table.horizontalHeaderItem(4).text(), "Auto-Show")

    def test_autoshow_label(self):
        self.assertEqual(MusicView._autoshow_label(Track(path="x.mp3")), "—")
        self.assertEqual(
            MusicView._autoshow_label(Track(path="x.mp3", autoshow_function_ids=[1, 2])),
            "2 Funktion(en)")

    def test_assign_autoshow_persists(self):
        self.view._assign_autoshow(0, [5, 6])
        self.assertEqual(self.mp.tracks[0].autoshow_function_ids, [5, 6])
        # Writeback in die SSOT state.playlist
        from src.core.app_state import get_state
        pl = get_state().playlist
        self.assertEqual(pl[0]["autoshow_function_ids"], [5, 6])
        # Tabelle zeigt die Zuweisung
        self.assertEqual(self.view._table.item(0, 4).text(), "2 Funktion(en)")

    def test_assign_autoshow_bad_row_noop(self):
        self.view._assign_autoshow(99, [1])      # darf nicht werfen
        self.assertEqual(self.mp.tracks[0].autoshow_function_ids, [])

    def test_refine_bpm_button(self):
        # untagged Dateien -> 0 geändert; MessageBox unterdrücken (sonst modal/blockt)
        orig = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)
        try:
            self.view._on_refine_bpm()           # darf nicht werfen/blocken
        finally:
            QMessageBox.information = orig


class SpectrumBarsTest(unittest.TestCase):
    def test_read_levels_shape(self):
        sb = SpectrumBars(bands=8)
        levels = sb.read_levels()
        self.assertEqual(len(levels), 8)
        self.assertTrue(all(0.0 <= v <= 1.0 for v in levels))
        sb.deleteLater()


if __name__ == "__main__":
    unittest.main()
