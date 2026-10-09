"""MIDI-5 / NET-14 / MIDI-16: MSC-Parser, Mapper-Zuordnung, GMA-UDP, kurze Nachrichten."""
from __future__ import annotations

import socket
import time

import pytest

from src.core.midi import msc
from src.core.midi.midi_manager import _decode
from src.core.engine.executor import Executor
import src.core.midi.midi_mapper as mm


def _sx(dev, cmd, data=b"", fmt=0x01):
    return [0xF0, 0x7F, dev, 0x02, fmt, cmd, *list(data), 0xF7]


@pytest.fixture(autouse=True)
def _settings_reset():
    st = msc.get_settings()
    alt = (st.enabled, st.device_id, st.udp_enabled, st.udp_host, st.udp_port)
    yield
    st.enabled, st.device_id, st.udp_enabled, st.udp_host, st.udp_port = alt


# ── Parser ───────────────────────────────────────────────────────────────────

def test_go_mit_cue_und_liste():
    c = msc.parse_msc(_sx(0x01, msc.GO, b"1.5\x002\x00"))
    assert c.name == "go" and c.cue == "1.5" and c.cue_list == "2"
    assert c.cue_path == ""


def test_go_ohne_daten():
    c = msc.parse_msc(_sx(0x01, msc.GO))
    assert c.command == msc.GO and c.cue == "" and c.cue_list == ""


def test_set_fire_timed_go():
    s = msc.parse_msc(_sx(0x01, msc.SET, bytes([2, 0, 0x7F, 0x7F])))
    assert s.control == 2 and s.value == 16383
    f = msc.parse_msc(_sx(0x01, msc.FIRE, bytes([5])))
    assert f.macro == 5
    t = msc.parse_msc(_sx(0x01, msc.TIMED_GO, bytes([0, 0, 3, 0, 0]) + b"4"))
    assert t.time == (0, 0, 3, 0, 0) and t.cue == "4"


def test_device_filter():
    assert msc.parse_msc(_sx(0x05, msc.GO), own_device=0x05) is not None
    assert msc.parse_msc(_sx(0x06, msc.GO), own_device=0x05) is None
    assert msc.parse_msc(_sx(0x7F, msc.GO), own_device=0x05) is not None
    assert msc.parse_msc(_sx(0x06, msc.GO), own_device=0x7F) is not None


def test_kein_msc_und_muell():
    assert msc.parse_msc([0xF0, 0x43, 0x10, 0xF7]) is None
    assert msc.parse_msc([0xF0, 0x7F, 0x01, 0x02, 0x01, 0x55, 0xF7]) is None
    assert msc.parse_msc(_sx(0x01, msc.SET, bytes([1]))) is None


def test_decode_liefert_msc_nachricht():
    m = _decode(_sx(0x01, msc.GO, b"3"), "Pult")
    assert m is not None and m.msg_type == "msc" and m.msc.cue == "3"


def test_decode_msc_abschaltbar():
    msc.get_settings().enabled = False
    assert _decode(_sx(0x01, msc.GO, b"3"), "Pult") is None


def test_rtmidi_sysex_freigegeben():
    from src.core.midi import midi_manager

    class _In:
        args = None

        def ignore_types(self, **kw):
            self.args = kw

    m = _In()
    midi_manager._sysex_freigeben(m)
    assert m.args["sysex"] is False


# ── MIDI-16 ──────────────────────────────────────────────────────────────────

def test_kurze_cc_wird_verworfen():
    assert _decode([0xB0, 7], "x") is None
    assert _decode([0x90, 60], "x") is None
    assert _decode([0xB0, 7, 100], "x").data2 == 100


def test_program_change_mit_einem_datenbyte():
    m = _decode([0xC0, 5], "x")
    assert m is not None and m.msg_type == "pc" and m.data1 == 5
    assert _decode([0xC0], "x") is None


# ── Mapper ───────────────────────────────────────────────────────────────────

class _Stack:
    def __init__(self, name):
        self.name = name
        self.log = []

    def go(self):
        self.log.append("go")

    def go_to(self, n):
        self.log.append(("go_to", n))

    def stop(self):
        self.log.append("stop")

    def back(self):
        self.log.append("back")


class _PE:
    def __init__(self):
        self.executors = [Executor(i + 1) for i in range(10)]
        for i, ex in enumerate(self.executors):
            ex.stack = _Stack(f"Liste {i + 1}")

    def get_executor(self, slot):
        return self.executors[slot - 1]

    def stop_all(self):
        for ex in self.executors:
            ex.stack.stop()


class _FM:
    def __init__(self):
        self.started = []

    def start(self, fid):
        self.started.append(fid)


class _State:
    def __init__(self):
        self.playback_engine = _PE()
        self.function_manager = _FM()


def _mapper():
    m = mm.MidiMapper.__new__(mm.MidiMapper)
    m._state = _State()
    return m


def test_mapper_go_cue_in_liste():
    m = _mapper()
    assert m.handle_msc(msc.parse_msc(_sx(1, msc.GO, b"2.5\x003")))
    assert m._state.playback_engine.executors[2].stack.log == [("go_to", 2.5)]


def test_mapper_go_ohne_cue_und_liste_nach_name():
    m = _mapper()
    assert m.handle_msc(msc.parse_msc(_sx(1, msc.GO, b"\x00liste 4")))
    assert m._state.playback_engine.executors[3].stack.log == ["go"]
    assert m.handle_msc(msc.parse_msc(_sx(1, msc.GO)))
    assert m._state.playback_engine.executors[0].stack.log == ["go"]


def test_mapper_stop_set_fire_alloff():
    m = _mapper()
    pe = m._state.playback_engine
    assert m.handle_msc(msc.parse_msc(_sx(1, msc.STOP, b"\x002")))
    assert pe.executors[1].stack.log == ["stop"]
    assert m.handle_msc(msc.parse_msc(_sx(1, msc.SET, bytes([0, 0, 0, 0x40]))))
    assert pe.executors[0].fader_value == pytest.approx(8192 / 16383)
    assert m.handle_msc(msc.parse_msc(_sx(1, msc.FIRE, bytes([7]))))
    assert m._state.function_manager.started == [7]
    assert m.handle_msc(msc.parse_msc(_sx(1, msc.ALL_OFF)))
    assert pe.executors[5].stack.log == ["stop"]


def test_mapper_unbekannte_liste_tut_nichts():
    m = _mapper()
    assert not m.handle_msc(msc.parse_msc(_sx(1, msc.GO, b"1\x00gibtsnicht")))
    assert not m.handle_msc(msc.parse_msc(_sx(1, msc.GO, b"1\x000")))


def test_on_midi_leitet_msc_weiter():
    m = _mapper()
    m._learn_mode = True
    m._learn_callback = lambda _msg: pytest.fail("MSC darf nicht gelernt werden")
    m._mappings = []
    m._on_midi(_decode(_sx(1, msc.GO, b"1"), "Pult"))
    assert m._state.playback_engine.executors[0].stack.log == [("go_to", 1.0)]


# ── NET-14: GMA-MSC ueber UDP ────────────────────────────────────────────────

def _gma(sysex):
    body = bytes(sysex)
    return b"GMA\x00MSC\x00" + (12 + len(body)).to_bytes(4, "little") + body


def test_parse_gma_udp():
    c = msc.parse_gma_udp(_gma(_sx(1, msc.GO, b"7")))
    assert c is not None and c.cue == "7"
    assert msc.parse_gma_udp(b"XXXX" + _gma(_sx(1, msc.GO))[4:]) is None
    assert msc.parse_gma_udp(b"GMA\x00") is None


def test_gma_udp_empfaenger_loopback():
    got = []
    rx = msc.GmaMscReceiver(got.append, "127.0.0.1", 0)
    assert rx.start()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(b"muell", ("127.0.0.1", rx.port))
        s.sendto(_gma(_sx(1, msc.GO, b"1.5")), ("127.0.0.1", rx.port))
        s.close()
        t0 = time.monotonic()
        while not got and time.monotonic() - t0 < 2.0:
            time.sleep(0.02)
    finally:
        rx.stop()
    assert len(got) == 1 and got[0].cue == "1.5"
    assert not rx.running


def test_mapper_apply_msc_udp_an_aus():
    m = _mapper()
    st = msc.get_settings()
    st.udp_enabled, st.udp_host, st.udp_port = True, "127.0.0.1", 0
    try:
        assert m.apply_msc_udp()
        port = m._msc_udp.port
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(_gma(_sx(1, msc.GO, b"\x002")), ("127.0.0.1", port))
        s.close()
        log = m._state.playback_engine.executors[1].stack.log
        t0 = time.monotonic()
        while not log and time.monotonic() - t0 < 2.0:
            time.sleep(0.02)
        assert log == ["go"]
        st.udp_enabled = False
        assert not m.apply_msc_udp()
        assert m._msc_udp is None
    finally:
        rx = getattr(m, "_msc_udp", None)
        if rx:
            rx.stop()


# ── WinMM: SysEx-Puffer (ohne Windows nur die Pufferlogik) ───────────────────

def test_winmm_longdata_bytes():
    import ctypes
    from src.core.midi import midi_backend_winmm as w
    assert hasattr(w, "_MIM_LONGDATA") and w._MIM_LONGDATA == 0x3C4
    raw = bytes(_sx(1, msc.GO, b"1"))
    buf = ctypes.create_string_buffer(raw, 64)
    hdr = w._MIDIHDR()
    hdr.lpData = ctypes.cast(buf, ctypes.c_void_p)
    hdr.dwBufferLength = 64
    hdr.dwBytesRecorded = len(raw)
    assert w._longdata_bytes(hdr) == list(raw)
    hdr.dwBytesRecorded = 0
    assert w._longdata_bytes(hdr) == []


def test_abgeschnittene_sysex_wirft_nicht():
    """Review-Fix: F7 vor dem Befehlsbyte warf IndexError — im MIDI-Empfangs-
    thread (_rx_loop ruft _decode ohne try) haette das alle Eingaenge gestoppt."""
    for raw in ([0xF0, 0x7F, 0x01, 0x02, 0x01, 0xF7],
                [0xF0, 0x7F, 0x01, 0x02, 0xF7, 0x00],
                [0xF0, 0x7F, 0x01, 0x02, 0x01]):
        assert msc.parse_msc(raw) is None
        assert _decode(raw, "Pult") is None
    paket = b"GMA\x00MSC\x00\x0e\x00\x00\x00" + bytes([0xF0, 0x7F, 1, 2, 1, 0xF7])
    assert msc.parse_gma_udp(paket) is None


# ── Review-Nachbesserungen ───────────────────────────────────────────────────

@pytest.mark.parametrize("cmd", [msc.STOP, msc.GO_OFF])
def test_stop_ohne_liste_stoppt_alle_listen(cmd):
    """MSC-Spezifikation: STOP/GO_OFF ohne Cue-Liste gilt fuer ALLE laufenden
    Listen, nicht nur fuer Executor 1."""
    m = _mapper()
    pe = m._state.playback_engine
    assert m.handle_msc(msc.parse_msc(_sx(1, cmd)))
    assert all(ex.stack.log == ["stop"] for ex in pe.executors)


def test_stop_mit_liste_stoppt_nur_diese(cmd=msc.STOP):
    m = _mapper()
    pe = m._state.playback_engine
    assert m.handle_msc(msc.parse_msc(_sx(1, cmd, b"\x003")))
    assert pe.executors[2].stack.log == ["stop"]
    assert pe.executors[0].stack.log == []


def test_einstellungen_dauerhaft(tmp_path, monkeypatch):
    """MSC-Einstellungen landen in ui_prefs.json (Sektion ``midi_msc``),
    fremde Sektionen bleiben erhalten, Laden stellt sie wieder her."""
    import json
    import src.core.paths as paths
    monkeypatch.setattr(paths, "app_data_dir", lambda: str(tmp_path))
    (tmp_path / "ui_prefs.json").write_text(json.dumps({"fremd": 1}))
    st = msc.get_settings()
    st.enabled, st.device_id = False, 9
    st.udp_enabled, st.udp_host, st.udp_port = True, "0.0.0.0", 6005
    assert msc.save_settings()
    daten = json.loads((tmp_path / "ui_prefs.json").read_text())
    assert daten["fremd"] == 1 and daten["midi_msc"]["device_id"] == 9
    st.enabled, st.device_id = True, 127
    st.udp_enabled, st.udp_host, st.udp_port = False, "127.0.0.1", 1
    msc.load_settings()
    assert (st.enabled, st.device_id, st.udp_enabled, st.udp_host,
            st.udp_port) == (False, 9, True, "0.0.0.0", 6005)


def test_einstellungen_kaputt_bleiben_default(tmp_path, monkeypatch):
    import json
    import src.core.paths as paths
    monkeypatch.setattr(paths, "app_data_dir", lambda: str(tmp_path))
    (tmp_path / "ui_prefs.json").write_text(json.dumps(
        {"midi_msc": {"device_id": "x", "udp_port": 99999, "enabled": False}}))
    st = msc.get_settings()
    st.device_id, st.udp_port = 127, msc.GMA_PORT
    msc.load_settings()
    assert st.device_id == 127 and st.udp_port == msc.GMA_PORT
    assert st.enabled is False
