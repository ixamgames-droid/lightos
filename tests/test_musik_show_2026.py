"""Musik-Show 2026 — Struktur der generierten shows/Musik_Show_2026.lshow.

Verifiziert das Endprodukt des Generators (tools/build_musik_show_2026.py): Patch,
Playlist, Auto-Show-Kopplung (beat-getriggerter Master + Slots), Beat-Sync-Cuelisten,
relative MH-EFX und die 5 VC-Banks.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.show.show_file import load_show
from src.core.audio.media_player import get_media_player
from src.core.engine.function_manager import get_function_manager
from src.core.engine.chaser import Chaser
from src.core.engine.efx import EfxInstance

_app = QApplication.instance() or QApplication([])

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOW = os.path.join(_ROOT, "shows", "Musik_Show_2026.lshow")


@unittest.skipUnless(os.path.exists(SHOW), "Musik_Show_2026.lshow nicht erzeugt")
class MusikShow2026Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ok, msg = load_show(SHOW)
        assert ok, msg
        cls.state = get_state()
        cls.vc = cls.state._vc_layout.get("widgets", [])
        cls.fm = get_function_manager()

    def test_patch_8_par_2_mh(self):
        fixtures = self.state.get_patched_fixtures()
        self.assertEqual(len(fixtures), 10)
        types = sorted(f.fixture_type for f in fixtures)
        self.assertEqual(types.count("par"), 8)
        self.assertEqual(types.count("moving_head"), 2)

    def test_playlist_10_tracks(self):
        self.assertEqual(len(self.state.playlist), 10)
        for t in self.state.playlist:
            self.assertTrue(t.get("path"))
            self.assertGreater(t.get("bpm", 0), 0)
        self.assertEqual(len(get_media_player().tracks), 10)

    def test_music_autoshow_coupled(self):
        ma = self.state.music_autoshow
        self.assertTrue(ma.get("enabled"))
        ids = ma.get("function_ids")
        self.assertEqual(len(ids), 2)
        fn_ids = {f.id for f in self.fm.all()}
        self.assertTrue(all(fid in fn_ids for fid in ids))
        # Slots decken die Auto-Show-Funktionen ab (sauberes Ablösen durch Pads).
        self.assertEqual({int(k) for k in ma.get("slots", {})}, set(ids))

    def test_master_par_is_beat_triggered(self):
        ids = self.state.music_autoshow["function_ids"]
        master = self.fm.get(ids[0])
        self.assertIsInstance(master, Chaser)
        self.assertTrue(master.audio_triggered)

    def test_two_beat_sync_cuelists(self):
        self.assertEqual(len(self.state.cue_stacks), 4)
        by = {s.name: s for s in self.state.cue_stacks}
        self.assertTrue(by["Drop-Sequenz"].beat_sync)
        self.assertEqual(by["Drop-Sequenz"].beats_per_cue, 4)
        self.assertTrue(by["Farb-Reise"].beat_sync)
        self.assertEqual(by["Farb-Reise"].beats_per_cue, 8)
        self.assertFalse(by["Aufwärmen"].beat_sync)
        self.assertFalse(by["MH-Fahrt"].beat_sync)

    def test_executors_bound_on_page_2(self):
        pe = self.state.playback_engine
        bound = [pe.get_executor(s, page=2).stack for s in (1, 2, 3, 4)]
        self.assertTrue(all(b is not None for b in bound))
        self.assertEqual({b.name for b in bound},
                         {s.name for s in self.state.cue_stacks})

    def test_relative_mh_efx_present(self):
        rel = [f for f in self.fm.all() if isinstance(f, EfxInstance) and f.relative]
        self.assertGreaterEqual(len(rel), 1)

    def test_five_banks_and_widgets(self):
        banks = {w.get("bank") for w in self.vc}
        self.assertTrue({0, 1, 2, 3, 4, -1}.issubset(banks))
        types = [w.get("type") for w in self.vc]
        self.assertEqual(types.count("VCSongInfo"), 2)
        self.assertEqual(types.count("VCCueList"), 4)
        self.assertEqual(types.count("VCXYPad"), 1)
        media = [w for w in self.vc
                 if w.get("action") in ("MediaPlayPause", "MediaNext", "MediaPrev")]
        self.assertEqual(len(media), 6)


if __name__ == "__main__":
    unittest.main()
