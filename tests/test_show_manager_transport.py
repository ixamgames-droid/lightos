"""Show-Manager-Transport startet/stoppt die Show wirklich im Engine.

Regression (adversariale UI-Bug-Jagd 2026-07-09): `_toggle_play`/`_stop` steuerten nur
den lokalen Playhead-Timer (`_on_play_tick` bewegt nur `_elapsed`), riefen aber NIE
`function_manager.start()/stop()` -> „Play" bewegte die Zeitleiste, triggerte aber keine
Funktion und gab kein DMX aus. Fix: `_fm.start(show.id)` beim Play, `_fm.stop(show.id)`
beim Pause/Stop.
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.views.show_manager_view import ShowManagerView

_app = QApplication.instance() or QApplication([])


def _fake():
    fm = MagicMock()
    fake = SimpleNamespace(
        _playing=False,
        _play_timer=MagicMock(),
        _btn_play=MagicMock(),
        _current_show=SimpleNamespace(id=42),
        _fm=fm,
        _elapsed=5.0,
        _timeline=MagicMock(),
        _update_time_label=lambda: None,
    )
    return fake, fm


class ShowManagerTransportTest(unittest.TestCase):
    def test_play_starts_engine(self):
        fake, fm = _fake()
        ShowManagerView._toggle_play(fake)
        fm.start.assert_called_once_with(42)
        self.assertTrue(fake._playing)

    def test_pause_stops_engine(self):
        fake, fm = _fake()
        fake._playing = True
        ShowManagerView._toggle_play(fake)
        fm.stop.assert_called_once_with(42)
        self.assertFalse(fake._playing)

    def test_stop_stops_engine_and_resets(self):
        fake, fm = _fake()
        fake._playing = True
        ShowManagerView._stop(fake)
        fm.stop.assert_called_once_with(42)
        self.assertEqual(fake._elapsed, 0.0)

    def test_play_without_show_is_noop(self):
        fake, fm = _fake()
        fake._current_show = None
        ShowManagerView._toggle_play(fake)
        fm.start.assert_not_called()
        self.assertFalse(fake._playing)


if __name__ == "__main__":
    unittest.main()
