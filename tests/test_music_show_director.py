"""MusicShowDirector: koppelt den In-App-Player an die Auto-Lichtshow.

Play (playingChanged True) startet die in state.music_autoshow konfigurierten
Funktionen, Pause/Stop stoppt sie; ohne 'enabled' passiert nichts; ein BPM-Takt
wird sichergestellt; Slots werden als Live-Edit-Ziel gesetzt.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.engine.function_manager import get_function_manager
from src.core.engine.bpm_manager import get_bpm_manager
from src.core.audio.music_show import MusicShowDirector

_app = QApplication.instance() or QApplication([])


class MusicShowDirectorTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.state = get_state()
        self.sc = self.fm.new_scene("AutoTest")
        self.sc.set_value(1, 1, 255)
        get_bpm_manager().reset()

    def tearDown(self):
        try:
            self.fm.stop(self.sc.id)
        except Exception:
            pass
        get_bpm_manager().reset()
        self.state.music_autoshow = {"enabled": False, "function_ids": [], "bank": 0, "slots": {}}

    def _enable(self, slots=None):
        self.state.music_autoshow = {
            "enabled": True, "function_ids": [self.sc.id], "bank": 0,
            "slots": slots or {},
        }

    def test_start_when_enabled(self):
        self._enable()
        MusicShowDirector().start_show()
        self.assertTrue(self.fm.is_running(self.sc.id))

    def test_disabled_starts_nothing(self):
        self.state.music_autoshow = {"enabled": False, "function_ids": [self.sc.id],
                                     "bank": 0, "slots": {}}
        MusicShowDirector().start_show()
        self.assertFalse(self.fm.is_running(self.sc.id))

    def test_ensures_bpm_running(self):
        self._enable()
        self.assertEqual(get_bpm_manager().bpm, 0.0)
        MusicShowDirector().start_show()
        self.assertGreater(get_bpm_manager().bpm, 0.0)

    def test_stop_show(self):
        self._enable()
        d = MusicShowDirector()
        d.start_show()
        self.assertTrue(self.fm.is_running(self.sc.id))
        d.stop_show()
        self.assertFalse(self.fm.is_running(self.sc.id))

    def test_on_playing_toggles(self):
        self._enable()
        d = MusicShowDirector()
        d._on_playing(True)
        self.assertTrue(self.fm.is_running(self.sc.id))
        d._on_playing(False)
        self.assertFalse(self.fm.is_running(self.sc.id))

    def test_slots_set_edit_target(self):
        from src.core.engine import effect_live
        self._enable(slots={self.sc.id: "par_show"})
        MusicShowDirector().start_show()
        self.assertEqual(effect_live.get_edit_target("par_show"), self.sc.id)


if __name__ == "__main__":
    unittest.main()
