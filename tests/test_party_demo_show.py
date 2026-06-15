"""Party-Demo-Show — Struktur der generierten shows/Party_Demo_2026.lshow.

Verifiziert das Endprodukt des Generators (tools/build_party_demo_show.py): Patch,
Playlist, BPM-getaktete Playbacks, VC-Banks (VCSongInfo, Media-Pads, Cuelisten).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.show.show_file import load_show
from src.core.audio.media_player import get_media_player

_app = QApplication.instance() or QApplication([])

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOW = os.path.join(_ROOT, "shows", "Party_Demo_2026.lshow")


@unittest.skipUnless(os.path.exists(SHOW), "Party_Demo_2026.lshow nicht erzeugt")
class PartyDemoShowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ok, msg = load_show(SHOW)
        assert ok, msg
        cls.state = get_state()
        cls.vc = cls.state._vc_layout.get("widgets", [])

    def test_patch_8_par_2_mh(self):
        fixtures = self.state.get_patched_fixtures()
        self.assertEqual(len(fixtures), 10)
        types = sorted(f.fixture_type for f in fixtures)
        self.assertEqual(types.count("par"), 8)
        self.assertEqual(types.count("moving_head"), 2)

    def test_playlist_10_tracks_with_bpm(self):
        self.assertEqual(len(self.state.playlist), 10)
        for t in self.state.playlist:
            self.assertTrue(t.get("path"))
            self.assertGreater(t.get("bpm", 0), 0)
        # MediaPlayer wurde beim Laden aus der Show gefüllt
        self.assertEqual(len(get_media_player().tracks), 10)

    def test_four_bpm_playbacks_bound(self):
        names = {s.name for s in self.state.cue_stacks}
        self.assertEqual(names, {"Warmup", "Drop/Peak", "Hands-Up", "MH-Sweep"})
        by = {s.name: s for s in self.state.cue_stacks}
        self.assertEqual(by["Drop/Peak"].mode, "single")
        self.assertEqual(by["Warmup"].mode, "loop")
        self.assertEqual(by["Hands-Up"].mode, "bounce")
        pe = self.state.playback_engine
        bound = [pe.get_executor(s, page=3).stack for s in (1, 2, 3, 4)]
        self.assertTrue(all(b is not None for b in bound))
        self.assertEqual({b.name for b in bound}, names)

    def test_music_widgets_and_media_pads(self):
        types = [w.get("type") for w in self.vc]
        self.assertEqual(types.count("VCSongInfo"), 1)
        self.assertEqual(types.count("VCCueList"), 4)
        media = [w for w in self.vc
                 if w.get("action") in ("MediaPlayPause", "MediaNext", "MediaPrev")]
        self.assertEqual(len(media), 6)

    def test_five_banks(self):
        banks = {w.get("bank") for w in self.vc}
        self.assertTrue({0, 1, 2, 3, 4, -1}.issubset(banks))


if __name__ == "__main__":
    unittest.main()
