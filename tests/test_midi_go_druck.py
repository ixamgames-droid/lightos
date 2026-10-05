"""MIDI-2: GO/BACK sind reine Druck-Aktionen.

Frueher war ``toggle`` die Vorgabe fuer ``executor_go``: jeder ZWEITE Druck
schaltete den Toggle aus und ``_execute_binary`` rief dann ``press_btn(1)`` —
also BACK. Im Flash-Modus loeste schon das Loslassen BACK aus. Bei einer Show
sprang die Cueliste damit falsch, unbemerkt, weil die Tests nur den ersten
Druck prueften.
"""
from __future__ import annotations

import json

import pytest

from src.core.midi.midi_manager import MidiMessage
import src.core.midi.midi_mapper as mm


class _FakeMidi:
    def subscribe(self, cb):
        pass

    def send_note(self, *a, **k):
        pass

    def send_cc(self, *a, **k):
        pass

    def send_note_to(self, *a, **k):
        return True

    def send_cc_to(self, *a, **k):
        return True


class _Ex:
    def __init__(self):
        self.go = 0
        self.back = 0
        self.stack = None
        self._flash_active = False
        self.fader_value = 0.0
        self.fader_function = "volume"

    def press_btn(self, btn):
        if btn == 0:
            self.go += 1
        elif btn == 1:
            self.back += 1

    def release_btn(self, btn):
        pass

    def get_output(self):
        return {}


class _PE:
    def __init__(self):
        self.current_page = 0
        self.executors = [_Ex() for _ in range(4)]

    def get_executor(self, slot):
        return self.executors[slot - 1]


class _OM:
    grand_master = 1.0

    def subscribe_grand_master(self, cb):
        pass


class _State:
    def __init__(self):
        self.playback_engine = _PE()
        self.output_manager = _OM()


@pytest.fixture
def mapper(monkeypatch):
    monkeypatch.setattr(mm, "get_midi_manager", lambda: _FakeMidi())
    state = _State()
    m = mm.MidiMapper(state)
    yield m, state
    m.close()


def _druecken(mapper_obj, note, *, cc=False):
    if cc:
        mapper_obj._on_midi(MidiMessage("APC", 1, "cc", note, 127))
        mapper_obj._on_midi(MidiMessage("APC", 1, "cc", note, 0))
    else:
        mapper_obj._on_midi(MidiMessage("APC", 1, "note_on", note, 127))
        mapper_obj._on_midi(MidiMessage("APC", 1, "note_off", note, 0))


def test_go_vorgabe_ist_druck():
    m = mm.MidiMapping(msg_type="note_on", data1=60,
                       action=mm.ACTION_EXECUTOR_GO, param="1")
    assert m.button_mode == mm.BUTTON_PRESS
    b = mm.MidiMapping(msg_type="note_on", data1=61,
                       action=mm.ACTION_EXECUTOR_BACK, param="1")
    assert b.button_mode == mm.BUTTON_PRESS


@pytest.mark.parametrize("modus", ["", "toggle", "flash", "press"])
@pytest.mark.parametrize("cc", [False, True])
def test_vier_mal_go_gibt_vier_mal_go(mapper, modus, cc):
    mp, state = mapper
    mp.add_mapping(mm.MidiMapping(
        msg_type="cc" if cc else "note_on", data1=60,
        action=mm.ACTION_EXECUTOR_GO, param="1", button_mode=modus))
    for _ in range(4):
        _druecken(mp, 60, cc=cc)
    ex = state.playback_engine.get_executor(1)
    assert (ex.go, ex.back) == (4, 0)


@pytest.mark.parametrize("modus", ["", "toggle", "flash", "press"])
def test_vier_mal_back_gibt_vier_mal_back(mapper, modus):
    mp, state = mapper
    mp.add_mapping(mm.MidiMapping(
        msg_type="note_on", data1=61,
        action=mm.ACTION_EXECUTOR_BACK, param="1", button_mode=modus))
    for _ in range(4):
        _druecken(mp, 61)
    ex = state.playback_engine.get_executor(1)
    assert (ex.go, ex.back) == (0, 4)


def test_flash_loslassen_tut_nichts(mapper):
    mp, state = mapper
    mp.add_mapping(mm.MidiMapping(
        msg_type="note_on", data1=60,
        action=mm.ACTION_EXECUTOR_GO, param="1", button_mode="flash"))
    ex = state.playback_engine.get_executor(1)
    mp._on_midi(MidiMessage("APC", 1, "note_on", 60, 127))
    assert (ex.go, ex.back) == (1, 0)
    mp._on_midi(MidiMessage("APC", 1, "note_off", 60, 0))
    mp._on_midi(MidiMessage("APC", 1, "note_on", 60, 0))
    assert (ex.go, ex.back) == (1, 0)


def test_modus_nachtraeglich_auf_toggle_gesetzt_bleibt_druck(mapper):
    """Die Mapping-Tabelle setzt ``button_mode`` als Freitext NACH dem Anlegen."""
    mp, state = mapper
    m = mm.MidiMapping(msg_type="note_on", data1=60,
                       action=mm.ACTION_EXECUTOR_GO, param="1")
    mp.add_mapping(m)
    m.button_mode = "toggle"
    for _ in range(4):
        _druecken(mp, 60)
    ex = state.playback_engine.get_executor(1)
    assert (ex.go, ex.back) == (4, 0)


def test_gespeicherte_toggle_flash_mappings_werden_beim_laden_normalisiert(mapper, tmp_path):
    mp, state = mapper
    alt = [
        {"id": "a", "name": "GO alt", "target": "executor_go:1",
         "midi_in": {"device": "", "channel": 1, "trigger_id": 60, "message_type": "note"},
         "button_mode": "toggle", "midi_out": None},
        {"id": "b", "name": "BACK alt", "target": "executor_back:1",
         "midi_in": {"device": "", "channel": 1, "trigger_id": 61, "message_type": "note"},
         "button_mode": "flash", "midi_out": None},
        {"id": "c", "name": "Flash bleibt", "target": "executor_flash:2",
         "midi_in": {"device": "", "channel": 1, "trigger_id": 62, "message_type": "note"},
         "button_mode": "flash", "midi_out": None},
        {"id": "d", "name": "Funktion bleibt", "target": "function:7",
         "midi_in": {"device": "", "channel": 1, "trigger_id": 63, "message_type": "note"},
         "button_mode": "toggle", "midi_out": None},
    ]
    pfad = tmp_path / "midi_mappings.json"
    pfad.write_text(json.dumps(alt), encoding="utf-8")
    assert mp.load(str(pfad))
    modi = {m.mapping_id: m.button_mode for m in mp.get_mappings()}
    assert modi == {"a": mm.BUTTON_PRESS, "b": mm.BUTTON_PRESS,
                    "c": mm.BUTTON_FLASH, "d": mm.BUTTON_TOGGLE}

    for _ in range(4):
        _druecken(mp, 60)
    ex = state.playback_engine.get_executor(1)
    assert (ex.go, ex.back) == (4, 0)

    # Gespeichert wird die normalisierte Form.
    ziel = tmp_path / "neu.json"
    assert mp.save(str(ziel))
    gespeichert = {d["id"]: d["button_mode"] for d in json.loads(ziel.read_text("utf-8"))}
    assert gespeichert["a"] == "press" and gespeichert["b"] == "press"


def test_legacy_flaches_mapping_wird_normalisiert():
    m = mm.MidiMapping(**{"name": "x", "msg_type": "note_on", "data1": 1,
                          "action": "executor_go", "param": "1",
                          "button_mode": "toggle"})
    assert m.button_mode == mm.BUTTON_PRESS
