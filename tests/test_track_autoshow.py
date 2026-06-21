"""AUTODJ-(a): Per-Song-Look.
  * Track.autoshow_function_ids round-trippt (+ Legacy-Default []).
  * MusicShowDirector tauscht beim Trackwechsel den Look aus (nur wenn spielend).
  * Funktionen der GLOBALEN Auto-Show werden beim Handoff NICHT gestoppt.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.engine.function_manager import get_function_manager
from src.core.engine.bpm_manager import get_bpm_manager
from src.core.audio.media_player import Track, get_media_player
from src.core.audio.music_show import MusicShowDirector

_app = QApplication.instance() or QApplication([])


class TrackPersistenceTest(unittest.TestCase):
    def test_roundtrip_autoshow_ids(self):
        t = Track(path="a.mp3", autoshow_function_ids=[3, 7])
        t2 = Track.from_dict(t.to_dict())
        self.assertEqual(t2.autoshow_function_ids, [3, 7])

    def test_legacy_defaults_empty(self):
        t = Track.from_dict({"path": "a.mp3"})
        self.assertEqual(t.autoshow_function_ids, [])

    def test_from_dict_drops_bad_ids(self):
        t = Track.from_dict({"path": "a.mp3", "autoshow_function_ids": [1, "x", 2]})
        self.assertEqual(t.autoshow_function_ids, [1, 2])


class PerSongLookTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.state = get_state()
        self.mp = get_media_player()
        self.a = self.fm.new_scene("LookA")
        self.a.set_value(1, 1, 255)
        self.b = self.fm.new_scene("LookB")
        self.b.set_value(1, 2, 255)
        get_bpm_manager().reset()

    def tearDown(self):
        for f in (self.a, self.b):
            try:
                self.fm.stop(f.id)
            except Exception:
                pass
        self.mp.set_tracks([])
        self.mp._playing = False
        get_bpm_manager().reset()
        self.state.music_autoshow = {"enabled": False, "function_ids": [],
                                     "bank": 0, "slots": {}}

    def _enable(self, function_ids=None, slots=None):
        self.state.music_autoshow = {
            "enabled": True, "function_ids": function_ids or [],
            "bank": 0, "slots": slots or {},
        }

    def test_handoff_on_track_change(self):
        self._enable()
        self.mp.set_tracks([
            Track(path="t0.mp3", autoshow_function_ids=[self.a.id]),
            Track(path="t1.mp3", autoshow_function_ids=[self.b.id]),
        ])
        self.mp._playing = True
        d = MusicShowDirector()
        self.mp.index = 0
        d._on_track_changed(0)
        self.assertTrue(self.fm.is_running(self.a.id))
        self.assertFalse(self.fm.is_running(self.b.id))
        self.mp.index = 1
        d._on_track_changed(1)
        self.assertFalse(self.fm.is_running(self.a.id))   # alter Look gestoppt
        self.assertTrue(self.fm.is_running(self.b.id))    # neuer Look läuft

    def test_paused_is_noop(self):
        self._enable()
        self.mp.set_tracks([Track(path="t0.mp3", autoshow_function_ids=[self.a.id])])
        self.mp._playing = False                          # nicht spielend
        MusicShowDirector()._on_track_changed(0)
        self.assertFalse(self.fm.is_running(self.a.id))

    def test_global_function_not_stopped_on_handoff(self):
        # sc A gehört zur GLOBALEN Auto-Show UND ist Per-Song-Look von Track 0.
        self._enable(function_ids=[self.a.id])
        self.mp.set_tracks([
            Track(path="t0.mp3", autoshow_function_ids=[self.a.id]),
            Track(path="t1.mp3", autoshow_function_ids=[self.b.id]),
        ])
        self.mp._playing = True
        d = MusicShowDirector()
        d.start_show()                                    # global A + Per-Song A
        self.assertTrue(self.fm.is_running(self.a.id))
        self.mp.index = 1
        d._on_track_changed(1)
        self.assertTrue(self.fm.is_running(self.a.id))    # global-owned bleibt!
        self.assertTrue(self.fm.is_running(self.b.id))

    def test_per_track_slot_edit_target(self):
        from src.core.engine import effect_live
        self._enable(slots={self.a.id: "song_look"})
        self.mp.set_tracks([Track(path="t0.mp3", autoshow_function_ids=[self.a.id])])
        self.mp._playing = True
        MusicShowDirector()._on_track_changed(0)
        self.assertEqual(effect_live.get_edit_target("song_look"), self.a.id)


if __name__ == "__main__":
    unittest.main()
