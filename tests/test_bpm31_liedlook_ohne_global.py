"""BPM-31: Lied-Look des ersten Titels startet auch ohne globale Funktionen.

Bis 2026-10-20 kehrte ``MusicShowDirector.start_show`` bei leerer globaler
Funktionsliste sofort zurueck — der Lied-Look („Auto-Show fuer Lied…") des
ersten Titels kam dann erst beim naechsten Trackwechsel. Gegenproben: ohne
eingeschaltete Kopplung startet weiterhin nichts, ohne Lied-Look und ohne
globale Liste bleibt start_show ein No-op, und die globale Liste allein laeuft
wie bisher.
"""
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.engine.function_manager import get_function_manager
from src.core.engine.bpm_manager import get_bpm_manager
from src.core.audio.music_show import MusicShowDirector

_app = QApplication.instance() or QApplication([])

_REPO = Path(__file__).resolve().parents[1]
_ANLEITUNG = _REPO / "docs" / "anleitung_musik_sync" / "ANLEITUNG_MUSIK_SYNC.md"


def _player_mit(ids):
    """Ersatz-Player, dessen aktueller Titel den Lied-Look ``ids`` traegt."""
    track = SimpleNamespace(autoshow_function_ids=list(ids), bpm=0.0, path="a.mp3")
    return SimpleNamespace(current_track=track, is_playing=True)


class LiedLookOhneGlobalTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.state = get_state()
        self.look = self.fm.new_scene("BPM31-Liedlook")
        self.look.set_value(1, 1, 255)
        self.glob = self.fm.new_scene("BPM31-Global")
        self.glob.set_value(1, 2, 255)
        get_bpm_manager().reset()

    def tearDown(self):
        for f in (self.look, self.glob):
            try:
                self.fm.stop(f.id)
            except Exception:
                pass
        get_bpm_manager().reset()
        self.state.music_autoshow = {"enabled": False, "function_ids": [],
                                     "bank": 0, "slots": {}}

    def _start(self, enabled, global_ids, track_ids):
        self.state.music_autoshow = {"enabled": enabled, "function_ids": list(global_ids),
                                     "bank": 0, "slots": {}}
        d = MusicShowDirector()
        with mock.patch("src.core.audio.media_player.get_media_player",
                        return_value=_player_mit(track_ids)):
            d.start_show()
        return d

    def test_liedlook_startet_ohne_globale_liste(self):
        d = self._start(True, [], [self.look.id])
        self.assertTrue(self.fm.is_running(self.look.id),
                        "Lied-Look des ersten Titels muss sofort starten")
        self.assertEqual(d._per_track_ids, [self.look.id])
        # BPM-Takt wird auch fuer den Lied-Look sichergestellt
        self.assertGreater(get_bpm_manager().bpm, 0.0)

    def test_gegenprobe_kopplung_aus_startet_nichts(self):
        self._start(False, [], [self.look.id])
        self.assertFalse(self.fm.is_running(self.look.id))
        self.assertEqual(get_bpm_manager().bpm, 0.0)

    def test_gegenprobe_ohne_alles_noop(self):
        d = self._start(True, [], [])
        self.assertEqual(d._per_track_ids, [])
        self.assertEqual(d._started_ids, [])
        self.assertEqual(get_bpm_manager().bpm, 0.0, "kein BPM-Fallback ohne Funktionen")

    def test_global_allein_wie_bisher(self):
        d = self._start(True, [self.glob.id], [])
        self.assertTrue(self.fm.is_running(self.glob.id))
        self.assertEqual(d._per_track_ids, [])

    def test_global_und_liedlook_zusammen(self):
        d = self._start(True, [self.glob.id], [self.look.id])
        self.assertTrue(self.fm.is_running(self.glob.id))
        self.assertTrue(self.fm.is_running(self.look.id))
        self.assertEqual(d._started_ids, [self.glob.id])
        self.assertEqual(d._per_track_ids, [self.look.id])

    def test_grenze_aus_musik_anleitung_gestrichen(self):
        text = _ANLEITUNG.read_text(encoding="utf-8")
        self.assertNotIn("erst beim nächsten Trackwechsel", text)
        self.assertNotIn("Bekannte Grenze (Stand Oktober 2026)", text)


if __name__ == "__main__":
    unittest.main()
