"""STAB-12 (Option B): Learn-Konflikt-Warnung im MidiMapper.

Eine Note/CC kann gleichzeitig ein globales MidiMapper-Mapping UND ein
VC-Widget-Binding treffen (beide haengen am selben Bus, keine Konsumierung).
Diese Tests pruefen die NICHT-behaviorale Konflikt-Erkennung: gegeben eine
gelernte Note/CC -> alle bereits belegten Bindungen (global + VC) werden
gemeldet. Das Dispatch-Verhalten bleibt unveraendert (rein additive Warnung).
"""
from __future__ import annotations

import unittest

from src.core.midi.midi_manager import MidiMessage
import src.core.midi.midi_mapper as mm


class _FakeMidiManager:
    def __init__(self):
        self.callbacks = []

    def subscribe(self, cb):
        self.callbacks.append(cb)

    def send_note(self, *a, **k):
        pass

    def send_cc(self, *a, **k):
        pass

    def current_output_name(self):
        return ""


class _FakeOutputManager:
    grand_master = 1.0

    def subscribe_grand_master(self, cb):
        pass


class _FakeState:
    def __init__(self):
        self.playback_engine = None
        self.output_manager = _FakeOutputManager()
        self.function_manager = None


def _msg(msg_type, data1, data2=127, channel=1, port="APC"):
    return MidiMessage(port_name=port, channel=channel, msg_type=msg_type,
                       data1=data1, data2=data2)


class MidiConflictWarnTests(unittest.TestCase):
    def setUp(self):
        self.old_get = mm.get_midi_manager
        self.fake_midi = _FakeMidiManager()
        mm.get_midi_manager = lambda *a, **k: self.fake_midi
        self.mapper = mm.MidiMapper(_FakeState())
        # Sauberer Start: keine Alt-Provider aus anderen Tests.
        mm._vc_binding_providers.clear()
        self._providers = []

    def tearDown(self):
        for p in self._providers:
            mm.unregister_vc_binding_provider(p)
        mm._vc_binding_providers.clear()
        self.mapper.close()
        mm.get_midi_manager = self.old_get

    def _add_global(self, data1, msg_type="note_on", channel=1, name="GO 1"):
        self.mapper.add_mapping(mm.MidiMapping(
            name=name, msg_type=msg_type, channel=channel, data1=data1,
            action=mm.ACTION_EXECUTOR_GO, param="1",
            button_mode=mm.BUTTON_TOGGLE))

    def _add_vc_binding(self, label, msg_type, channel, data1):
        provider = lambda: [(label, msg_type, channel, data1)]
        self._providers.append(provider)
        mm.register_vc_binding_provider(provider)

    # -- Kernfall: Note global + an VC-Widget -> BEIDE gemeldet ----------------

    def test_conflict_reports_both_global_and_vc(self):
        self._add_global(36, name="Executor 1 Go")
        self._add_vc_binding("Play-Button", "note_on", 1, 36)

        conflicts = self.mapper.find_binding_conflicts("note_on", 1, 36)
        sources = sorted(c["source"] for c in conflicts)
        self.assertEqual(sources, ["global", "vc"])
        self.assertEqual(len(conflicts), 2)
        labels = {c["label"] for c in conflicts}
        self.assertIn("Executor 1 Go", labels)
        self.assertIn("Play-Button", labels)

    # -- Unbelegte Note -> kein Konflikt ---------------------------------------

    def test_unbound_note_has_no_conflict(self):
        self._add_global(36)
        self._add_vc_binding("Play-Button", "note_on", 1, 36)

        self.assertEqual(self.mapper.find_binding_conflicts("note_on", 1, 40), [])

    # -- note_on bindet note_off; CC ist eine andere Familie -------------------

    def test_family_and_channel_semantics(self):
        self._add_global(36, msg_type="note_on", channel=1)
        # note_off auf derselben Note trifft die note-Bindung.
        self.assertTrue(self.mapper.find_binding_conflicts("note_off", 1, 36))
        # CC 36 ist eine andere Familie -> kein Konflikt mit der note-Bindung.
        self.assertEqual(self.mapper.find_binding_conflicts("cc", 1, 36), [])
        # Kanal 0 (alle) im VC-Widget ueberlappt mit jedem Kanal.
        self._add_vc_binding("Any-Chan", "note_on", 0, 36)
        self.assertTrue(self.mapper.find_binding_conflicts("note_on", 5, 36))

    # -- Warnung feuert (print + UI-Callback) bei Learn-Abschluss --------------

    def test_learn_completion_emits_warning(self):
        self._add_global(36, name="Executor 1 Go")
        self._add_vc_binding("Play-Button", "note_on", 1, 36)

        seen = []
        self.mapper.subscribe_conflict(lambda payload: seen.append(payload))

        learned = []
        self.mapper.start_learn(lambda m: learned.append(m))
        # Simuliert den RX-Dispatch: dieselbe Note kommt beim Learn herein.
        self.mapper._on_midi(_msg("note_on", 36))

        # Learn-Callback lief -> Bindung wird (UI-seitig) angewendet.
        self.assertEqual(len(learned), 1)
        # Konflikt-Warnung wurde emittiert und meldet beide Ebenen.
        self.assertEqual(len(seen), 1)
        self.assertEqual(len(seen[0]["conflicts"]), 2)

    def test_no_warning_when_note_is_free(self):
        self._add_global(36)
        seen = []
        self.mapper.subscribe_conflict(lambda payload: seen.append(payload))
        self.mapper.start_learn(lambda m: None)
        self.mapper._on_midi(_msg("note_on", 41))  # freie Note
        self.assertEqual(seen, [])


if __name__ == "__main__":
    unittest.main()
