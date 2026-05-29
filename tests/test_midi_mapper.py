"""Unit tests for the bidirectional MIDI mapper."""
from __future__ import annotations

import tempfile
import time
import unittest

from src.core.midi.midi_manager import MidiMessage
import src.core.midi.midi_mapper as mm


class _FakeMidiManager:
    def __init__(self):
        self.callbacks = []
        self.sent: list[tuple[str, int, int, int]] = []
        self.opened_output = ""
        self.open_output_calls = 0

    def subscribe(self, cb):
        self.callbacks.append(cb)

    def send_note(self, channel: int, note: int, velocity: int = 127):
        self.sent.append(("note", channel, note, velocity))

    def send_cc(self, channel: int, cc: int, value: int, virtual: bool = False):
        self.sent.append(("cc", channel, cc, value))

    def open_output(self, port_name: str):
        self.opened_output = port_name
        self.open_output_calls += 1

    def current_output_name(self) -> str:
        return self.opened_output


class _FakeExecutor:
    def __init__(self):
        self.go_count = 0
        self.back_count = 0
        self._flash_active = False
        self.fader_value = 0.0
        self.fader_function = "volume"
        self.stack = object()

    def press_btn(self, btn):
        if btn == 0:
            self.go_count += 1
        elif btn == 1:
            self.back_count += 1
        elif btn == 2:
            self._flash_active = True

    def release_btn(self, btn):
        if btn == 2:
            self._flash_active = False

    def get_output(self):
        return {1: {"intensity": 255}} if self.go_count > 0 else {}


class _FakePlayback:
    def __init__(self):
        self.current_page = 0
        self.executors = [_FakeExecutor() for _ in range(10)]

    def get_executor(self, slot: int):
        return self.executors[slot - 1]

    def set_page(self, idx: int):
        self.current_page = idx


class _FakeOutputManager:
    def __init__(self):
        self.grand_master = 1.0
        self._subs = []

    def set_grand_master(self, value: float):
        self.grand_master = value
        for cb in list(self._subs):
            cb(value)

    def subscribe_grand_master(self, cb):
        self._subs.append(cb)


class _FakeFunctionManager:
    def __init__(self):
        self._running = set()

    def start(self, fid: int):
        self._running.add(fid)

    def stop(self, fid: int):
        self._running.discard(fid)

    def is_running(self, fid: int) -> bool:
        return fid in self._running


class _FakeState:
    def __init__(self):
        self.playback_engine = _FakePlayback()
        self.output_manager = _FakeOutputManager()
        self.function_manager = _FakeFunctionManager()

    def get_patched_fixtures(self):
        return []

    def set_programmer_value(self, *_args, **_kwargs):
        return None


def _msg(msg_type: str, data1: int, data2: int = 127, channel: int = 1, port: str = "APC"):
    return MidiMessage(port_name=port, channel=channel, msg_type=msg_type, data1=data1, data2=data2)


class MidiMapperTests(unittest.TestCase):
    def setUp(self):
        self.fake_midi = _FakeMidiManager()
        self.old_get = mm.get_midi_manager
        mm.get_midi_manager = lambda: self.fake_midi
        self.state = _FakeState()
        self.mapper = mm.MidiMapper(self.state)

    def tearDown(self):
        self.mapper.close()
        mm.get_midi_manager = self.old_get

    def test_toggle_mapping_triggers_inbound_and_feedback(self):
        mapping = mm.MidiMapping(
            name="GO 1",
            msg_type="note_on",
            channel=1,
            data1=0,
            action=mm.ACTION_EXECUTOR_GO,
            param="1",
            button_mode=mm.BUTTON_TOGGLE,
            midi_out=mm.MidiOutFeedback(trigger_id=0, state_off=5, state_on=3),
        )
        self.mapper.add_mapping(mapping)
        self.fake_midi.sent.clear()

        self.mapper._on_midi(_msg("note_on", 0, 127))
        time.sleep(0.05)

        ex = self.state.playback_engine.get_executor(1)
        self.assertEqual(ex.go_count, 1)
        self.assertIn(("note", 1, 0, 3), self.fake_midi.sent)

    def test_continuous_mapping_scales_grand_master(self):
        mapping = mm.MidiMapping(
            name="GM",
            msg_type="cc",
            channel=1,
            data1=56,
            action=mm.ACTION_GRAND_MASTER,
            button_mode=mm.BUTTON_CONTINUOUS,
            midi_out=mm.MidiOutFeedback(message_type="cc", trigger_id=56),
        )
        self.mapper.add_mapping(mapping)
        self.fake_midi.sent.clear()

        self.mapper._on_midi(_msg("cc", 56, 64))
        time.sleep(0.05)

        self.assertTrue(0.49 <= self.state.output_manager.grand_master <= 0.51)
        self.assertTrue(any(kind == "cc" and key == 56 for kind, _ch, key, _val in self.fake_midi.sent))

    def test_config_roundtrip_uses_structured_shape(self):
        mapping = mm.MidiMapping(
            name="Roundtrip",
            msg_type="note_on",
            channel=2,
            data1=11,
            action=mm.ACTION_EXECUTOR_FLASH,
            param="2",
            button_mode=mm.BUTTON_FLASH,
            midi_out=mm.MidiOutFeedback(
                device="APC mini mk2",
                channel=2,
                trigger_id=11,
                message_type="note",
                state_off=1,
                state_on=6,
                brightness=100,
            ),
        )
        payload = mapping.to_config_dict()
        self.assertTrue({"id", "target", "midi_in", "button_mode", "midi_out"}.issubset(payload.keys()))
        self.assertEqual(payload["midi_in"]["trigger_id"], 11)
        self.assertEqual(payload["midi_out"]["state_on"], 6)

        with tempfile.TemporaryDirectory() as td:
            path = f"{td}\\midi.json"
            self.mapper.add_mapping(mapping)
            self.mapper.save(path)
            self.mapper.replace_mappings([])
            self.mapper.load(path)
            loaded = self.mapper.get_mappings()
            self.assertEqual(len(loaded), 1)
            self.assertTrue(loaded[0].target_id.startswith(mm.ACTION_EXECUTOR_FLASH))
            self.assertIsNotNone(loaded[0].midi_out)
            self.assertEqual(loaded[0].midi_out.state_off, 1)

    def test_feedback_stress_reuses_output_port(self):
        mapping = mm.MidiMapping(
            name="Stress Fader",
            msg_type="cc",
            channel=1,
            data1=1,
            action=mm.ACTION_EXECUTOR_FADER,
            param="1",
            button_mode=mm.BUTTON_CONTINUOUS,
            midi_out=mm.MidiOutFeedback(device="APC mini mk2", message_type="cc", trigger_id=1),
        )
        self.mapper.add_mapping(mapping)
        self.fake_midi.sent.clear()

        for val in range(0, 128):
            self.mapper._on_midi(_msg("cc", 1, val))
        time.sleep(0.2)

        self.assertEqual(self.fake_midi.opened_output, "APC mini mk2")
        self.assertLessEqual(self.fake_midi.open_output_calls, 1)


if __name__ == "__main__":
    unittest.main()
