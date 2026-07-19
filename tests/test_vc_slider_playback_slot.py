"""DQ-2: VCSlider PLAYBACK nutzt ein eigenes playback_slot-Feld statt function_id.

Vorher wurde der Executor-Slot im PLAYBACK-Modus in function_id gespeichert
(Zweckentfremdung — alle anderen Modi nutzen function_id als echte Funktions-ID).
Jetzt gibt es ein dediziertes playback_slot; Alt-Shows migrieren beim Laden den
Slot aus function_id, falls playback_slot fehlt.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode

_app = QApplication.instance() or QApplication([])


class PlaybackSlotSerializationTest(unittest.TestCase):
    def test_roundtrip_new_format(self):
        s = VCSlider("PB")
        s.mode = SliderMode.PLAYBACK
        s.playback_slot = 5
        d = s.to_dict()
        self.assertEqual(d["playback_slot"], 5)

        s2 = VCSlider("PB2")
        s2.apply_dict(d)
        self.assertEqual(s2.playback_slot, 5)

    def test_backcompat_migrates_function_id(self):
        # Alt-Show: der Slot lag in function_id, kein playback_slot-Key vorhanden.
        s = VCSlider("Old")
        s.apply_dict({"mode": SliderMode.PLAYBACK, "function_id": 7})
        self.assertEqual(s.playback_slot, 7)

    def test_backcompat_non_playback_not_polluted(self):
        # Nicht-PLAYBACK: function_id ist eine echte ID, KEINE Slot-Migration.
        s = VCSlider("Lvl")
        s.apply_dict({"mode": SliderMode.LEVEL, "function_id": 2})
        self.assertIsNone(s.playback_slot)

    def test_explicit_playback_slot_wins(self):
        # Neue Show mit beidem -> playback_slot zaehlt, function_id wird ignoriert.
        s = VCSlider("Both")
        s.apply_dict({"mode": SliderMode.PLAYBACK, "function_id": 9, "playback_slot": 3})
        self.assertEqual(s.playback_slot, 3)

    def test_explicit_null_slot_not_migrated_from_function_id(self):
        # A3D-39: eine NEUE Show mit BEWUSST geloestem Slot schreibt playback_slot=None
        # (to_dict schreibt den Key IMMER mit). Beim Laden darf der geloeste Slot NICHT
        # aus der (stale) function_id zurueckmigriert werden -> sonst kaeme der geloeschte
        # Executor als Slot zurueck. Frueher unterschied `d.get() is None` das explizite
        # null nicht von einem fehlenden Key.
        s = VCSlider("Cleared")
        s.mode = SliderMode.PLAYBACK
        s.playback_slot = None
        s.function_id = 9             # stale Rest im function_id-Feld
        d = s.to_dict()
        self.assertIn("playback_slot", d)      # Key IST da (nur null)
        self.assertIsNone(d["playback_slot"])
        s2 = VCSlider("Cleared2")
        s2.apply_dict(d)
        self.assertIsNone(
            s2.playback_slot,
            "bewusst geloester Slot faelschlich aus function_id migriert (A3D-39)")

    def test_missing_key_still_migrates(self):
        # Gegenprobe: fehlt der Key GANZ (echte Alt-Show), migriert function_id weiter.
        s = VCSlider("Legacy")
        s.apply_dict({"mode": SliderMode.PLAYBACK, "function_id": 7})   # kein playback_slot
        self.assertEqual(s.playback_slot, 7)


class PlaybackApplyTest(unittest.TestCase):
    def setUp(self):
        # executors ist eine read-only Property (Executoren der aktiven Page) ->
        # nicht ersetzen, sondern die echten fader_value setzen und zuruecksetzen.
        self.execs = get_state().playback_engine.executors
        self._orig = [e.fader_value for e in self.execs]
        for e in self.execs:
            e.fader_value = -1.0

    def tearDown(self):
        for e, v in zip(self.execs, self._orig):
            e.fader_value = v

    def _slider(self, slot, value=255):
        s = VCSlider("PB")
        s.mode = SliderMode.PLAYBACK
        s.playback_slot = slot
        s._value = value
        return s

    def test_apply_writes_playback_slot_not_function_id(self):
        s = self._slider(2)
        s.function_id = 99            # absichtlich falsch -> darf NICHT genutzt werden
        s._apply()
        self.assertEqual(self.execs[2].fader_value, 1.0)
        self.assertEqual(self.execs[0].fader_value, -1.0)   # andere unberuehrt
        self.assertEqual(self.execs[3].fader_value, -1.0)

    def test_apply_none_slot_is_noop(self):
        s = self._slider(None)
        s._apply()                    # kein Crash, nichts geschrieben
        for e in self.execs:
            self.assertEqual(e.fader_value, -1.0)

    def test_apply_out_of_range_slot_is_safe(self):
        s = self._slider(99)          # > Anzahl Executoren (MAX_EXECUTORS=20)
        s._apply()                    # kein IndexError
        for e in self.execs:
            self.assertEqual(e.fader_value, -1.0)


if __name__ == "__main__":
    unittest.main()
