"""MIDI-4: ein Fehler in einer Mapping-Zeile darf die anderen Zeilen derselben
Note nicht abbrechen; der Toggle-Zustand ist gegen parallele Zugriffe
abgesichert."""
from __future__ import annotations

import threading
import unittest

from src.core.midi.midi_manager import MidiMessage
import src.core.midi.midi_mapper as mm


class _FakeMidi:
    def __init__(self):
        self.callbacks = []

    def subscribe(self, cb):
        self.callbacks.append(cb)

    def send_note(self, *a, **k):
        pass

    def send_cc(self, *a, **k):
        pass

    def send_note_to(self, *a, **k):
        return True

    def send_cc_to(self, *a, **k):
        return True


class _Ex:
    def __init__(self, wirft=False):
        self.wirft = wirft
        self.go = 0

    def press_btn(self, btn):
        if self.wirft:
            raise RuntimeError("kaputt")
        self.go += 1

    def release_btn(self, btn):
        pass

    def get_output(self):
        return {}


class _PE:
    current_page = 0

    def __init__(self):
        self.ex = {1: _Ex(wirft=True), 2: _Ex()}

    def get_executor(self, slot):
        return self.ex[slot]


class _OM:
    grand_master = 1.0

    def subscribe_grand_master(self, cb):
        pass


class _State:
    def __init__(self):
        self.playback_engine = _PE()
        self.output_manager = _OM()
        self.function_manager = None

    def get_patched_fixtures(self):
        return []


class MappingIsoliertTests(unittest.TestCase):
    def setUp(self):
        self._alt = mm.get_midi_manager
        fake = _FakeMidi()
        mm.get_midi_manager = lambda: fake
        self.state = _State()
        self.mapper = mm.MidiMapper(self.state)

    def tearDown(self):
        self.mapper.close()
        mm.get_midi_manager = self._alt

    def _go(self, slot):
        return mm.MidiMapping(name=f"GO {slot}", msg_type="note_on", channel=1,
                              data1=7, action=mm.ACTION_EXECUTOR_GO,
                              param=str(slot), button_mode=mm.BUTTON_PRESS)

    def test_erste_zeile_wirft_zweite_laeuft(self):
        self.mapper.add_mapping(self._go(1))
        self.mapper.add_mapping(self._go(2))
        self.mapper._on_midi(MidiMessage("APC", 1, "note_on", 7, 127))
        self.assertEqual(self.state.playback_engine.ex[2].go, 1)

    def test_toggle_states_haben_lock(self):
        self.assertTrue(hasattr(self.mapper, "_toggle_lock"))
        m = mm.MidiMapping(name="T", msg_type="note_on", channel=1, data1=9,
                           action=mm.ACTION_PAGE_NEXT,
                           button_mode=mm.BUTTON_TOGGLE)
        self.mapper.add_mapping(m)
        msg = MidiMessage("APC", 1, "note_on", 9, 127)

        def drueck():
            for _ in range(200):
                self.mapper._on_midi(msg)

        ts = [threading.Thread(target=drueck) for _ in range(4)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        # 800 Druecke -> gerade Anzahl -> wieder AUS.
        self.assertFalse(self.mapper._toggle_states[m.mapping_id])


if __name__ == "__main__":
    unittest.main()
