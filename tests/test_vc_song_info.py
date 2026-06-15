"""VCSongInfo — Serialisierungs-Roundtrip, Registry und MediaPlayer-Anbindung."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.virtualconsole.vc_song_info import VCSongInfo
from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY
from src.core.audio.media_player import get_media_player

_app = QApplication.instance() or QApplication([])


class VCSongInfoTest(unittest.TestCase):
    def test_registered_in_registry(self):
        self.assertIn("VCSongInfo", WIDGET_REGISTRY)
        self.assertIs(WIDGET_REGISTRY["VCSongInfo"], VCSongInfo)

    def test_to_dict_type_and_font(self):
        w = VCSongInfo("Musik")
        w._font_size = 17
        d = w.to_dict()
        self.assertEqual(d["type"], "VCSongInfo")
        self.assertEqual(d["font_size"], 17)
        self.assertEqual(d["caption"], "Musik")

    def test_apply_dict_roundtrip(self):
        w = VCSongInfo("A")
        w._font_size = 20
        d = w.to_dict()
        w2 = VCSongInfo()
        w2.apply_dict(d)
        self.assertEqual(w2._font_size, 20)
        self.assertEqual(w2.caption, "A")

    def test_reads_media_player_without_error(self):
        mp = get_media_player()
        mp.set_playlist_dicts([
            {"path": "a.mp3", "title": "Song A", "bpm": 150},
            {"path": "b.mp3", "title": "Song B", "bpm": 128},
        ])
        w = VCSongInfo()
        # paintEvent darf nicht crashen (rendert in ein Pixmap-Backbuffer offscreen)
        w.resize(300, 100)
        w.repaint()
        self.assertEqual(mp.current_track.title, "Song A")
        self.assertEqual(mp.next_track.title, "Song B")


if __name__ == "__main__":
    unittest.main()
