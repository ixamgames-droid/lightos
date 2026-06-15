"""MediaPlayer — Playlist-Logik, Navigation und BPM-Fallback-Kopplung.

Das Audio-Backend (QMediaPlayer) wird hier NICHT angefasst (kein echtes Abspielen):
getestet wird die reine Playlist-/Index-Logik und die Nominal-BPM-Kopplung.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.audio.media_player import (
    MediaPlayer, Track, clean_title, guess_genre_bpm, get_media_player,
)
from src.core.engine.bpm_manager import get_bpm_manager

_app = QApplication.instance() or QApplication([])


class TrackHelpersTest(unittest.TestCase):
    def test_clean_title_strips_kopie_and_index(self):
        self.assertEqual(
            clean_title("X (NOISETIME Remix) - Kopie - Kopie.mp3"),
            "X (NOISETIME Remix)")
        self.assertEqual(clean_title("Song (1).mp3"), "Song")

    def test_guess_genre_bpm(self):
        self.assertEqual(guess_genre_bpm("SWEET ABOUT ME [205] Frenchcore.mp3"), ("Frenchcore", 205.0))
        self.assertEqual(guess_genre_bpm("Any (TBMN Hardstyle Remix).mp3"), ("Hardstyle", 150.0))
        self.assertEqual(guess_genre_bpm("Major Tom (HBz Bounce Remix).mp3"), ("Bounce", 155.0))
        self.assertEqual(guess_genre_bpm("Foo (Hypertechno).mp3"), ("Hypertechno", 150.0))
        self.assertEqual(guess_genre_bpm("Plain Pop Edit.mp3"), ("Dance", 128.0))

    def test_track_autotitle_and_roundtrip(self):
        t = Track(path="C:/m/Foo (1).mp3")
        self.assertEqual(t.title, "Foo")
        d = t.to_dict()
        self.assertEqual(Track.from_dict(d).path, t.path)


class PlaylistNavigationTest(unittest.TestCase):
    def setUp(self):
        self.mp = MediaPlayer()
        self.mp.set_playlist_dicts([
            {"path": "a.mp3", "title": "A", "bpm": 150},
            {"path": "b.mp3", "title": "B", "bpm": 155},
            {"path": "c.mp3", "title": "C", "bpm": 128},
        ])

    def test_initial_index_and_current_next(self):
        self.assertEqual(self.mp.index, 0)
        self.assertEqual(self.mp.current_track.title, "A")
        self.assertEqual(self.mp.next_track.title, "B")

    def test_next_prev_wrap(self):
        self.mp.index = 0
        self.mp.index = (self.mp.index + 1) % 3   # logik ohne Audio-Backend
        self.assertEqual(self.mp.current_track.title, "B")
        # next_track ist zyklisch
        self.mp.index = 2
        self.assertEqual(self.mp.next_track.title, "A")

    def test_empty_playlist(self):
        mp = MediaPlayer()
        self.assertIsNone(mp.current_track)
        self.assertIsNone(mp.next_track)
        self.assertEqual(mp.index, -1)

    def test_load_paths_uses_heuristic(self):
        mp = MediaPlayer()
        mp.load_paths(["X (TBMN Hardstyle Remix).mp3", "Y (HBz Bounce).mp3"])
        self.assertEqual(mp.tracks[0].genre, "Hardstyle")
        self.assertEqual(mp.tracks[0].bpm, 150.0)
        self.assertEqual(mp.tracks[1].genre, "Bounce")

    def test_to_dicts_roundtrip(self):
        dicts = self.mp.to_dicts()
        self.assertEqual(len(dicts), 3)
        mp2 = MediaPlayer()
        mp2.set_playlist_dicts(dicts)
        self.assertEqual([t.title for t in mp2.tracks], ["A", "B", "C"])


class BpmCouplingTest(unittest.TestCase):
    def tearDown(self):
        get_bpm_manager().reset()

    def test_nominal_bpm_set_as_fallback(self):
        mgr = get_bpm_manager()
        mgr.reset()
        mp = MediaPlayer()
        mp.set_playlist_dicts([{"path": "a.mp3", "title": "A", "bpm": 150}])
        mp.couple_bpm = True
        mp._apply_track_bpm()
        self.assertAlmostEqual(mgr.bpm, 150.0, delta=1.0)

    def test_no_coupling_when_disabled(self):
        mgr = get_bpm_manager()
        mgr.reset()
        mp = MediaPlayer()
        mp.set_playlist_dicts([{"path": "a.mp3", "title": "A", "bpm": 150}])
        mp.couple_bpm = False
        mp._apply_track_bpm()
        self.assertEqual(mgr.bpm, 0.0)


class SingletonTest(unittest.TestCase):
    def test_singleton_identity(self):
        self.assertIs(get_media_player(), get_media_player())


if __name__ == "__main__":
    unittest.main()
