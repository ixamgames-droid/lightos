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
    alt = dict(vars(st))
    yield
    vars(st).clear()
    vars(st).update(alt)


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
    """Wie die echte PlaybackEngine: mehrere Seiten, ``executors`` = aktuelle."""

    def __init__(self):
        self.pages = [[Executor(i + 1) for i in range(10)] for _ in range(3)]
        self.current_page = 0
        for i, ex in enumerate(self.executors):
            ex.stack = _Stack(f"Liste {i + 1}")

    @property
    def executors(self):
        return self.pages[self.current_page]

    def get_executor(self, slot, page=None):
        p = self.current_page if page is None else page
        return self.pages[p][slot - 1]

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
    msc.get_settings().set_layout = msc.SET_STANDARD
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


# ── Codex-Review #990: SET-Belegung, Command-Format, UDP im Monitor ──────────

@pytest.fixture
def meldungen(monkeypatch):
    """Faengt ``melde_still`` ab (die echte Funktion entdoppelt prozessweit)."""
    import src.core.diagnose_log as dl
    got = []
    monkeypatch.setattr(dl, "melde_still",
                        lambda tag, exc=None, text="": got.append((tag, text)))
    return got


def test_set_vorgabe_ist_grandma_und_rohbytes_bleiben():
    assert msc.MscSettings().set_layout == msc.SET_GRANDMA
    s = msc.parse_msc(_sx(0x01, msc.SET, bytes([2, 1, 0, 0x64])))
    assert s.set_data == (2, 1, 0, 0x64)
    assert msc.set_grandma(s.set_data) == (3, 1, 1.0)


def test_set_grandma_executor_und_seite(meldungen):
    """grandMA sendet 'Executor 3 / Seite 1' als 02 01 — das ist NICHT
    Regler 130, sondern Executor 3 auf Executor-Seite 1."""
    m = _mapper()
    pe = m._state.playback_engine
    pe.current_page = 2                     # Seite kommt aus dem Befehl
    assert msc.get_settings().set_layout == msc.SET_GRANDMA
    assert m.handle_msc(msc.parse_msc(_sx(1, msc.SET, bytes([2, 1, 0, 0x32]))))
    assert pe.pages[0][2].fader_value == pytest.approx(0.5)
    assert m.handle_msc(msc.parse_msc(_sx(1, msc.SET, bytes([0, 2, 64, 24]))))
    assert pe.pages[1][0].fader_value == pytest.approx(0.245)
    assert m.handle_msc(msc.parse_msc(_sx(1, msc.SET, bytes([9, 3, 0, 0x64]))))
    assert pe.pages[2][9].fader_value == pytest.approx(1.0)
    assert pe.pages[2][2].fader_value == pytest.approx(1.0)   # unberuehrt
    assert meldungen == []


@pytest.mark.parametrize("daten, wort", [
    (bytes([10, 1, 0, 0x64]), "Executor 11"),   # Platz gibt es nicht
    (bytes([0, 0, 0, 0x64]), "Seite 0"),        # Seiten zaehlen ab 1
    (bytes([0, 4, 0, 0x64]), "Seite 4"),        # nur 3 Seiten
])
def test_set_grandma_ungueltig_wird_gemeldet(meldungen, daten, wort):
    m = _mapper()
    pe = m._state.playback_engine
    vorher = [[ex.fader_value for ex in seite] for seite in pe.pages]
    assert not m.handle_msc(msc.parse_msc(_sx(1, msc.SET, daten)))
    assert [[ex.fader_value for ex in seite] for seite in pe.pages] == vorher
    assert len(meldungen) == 1 and meldungen[0][0] == "midi.msc.set"
    assert wort in meldungen[0][1]


def test_set_standard_14bit_und_ungueltig_gemeldet(meldungen):
    m = _mapper()
    pe = m._state.playback_engine
    pe.current_page = 1
    msc.get_settings().set_layout = msc.SET_STANDARD
    assert m.handle_msc(msc.parse_msc(_sx(1, msc.SET, bytes([3, 0, 0x7F, 0x7F]))))
    assert pe.pages[1][3].fader_value == pytest.approx(1.0)
    assert meldungen == []
    # grandMA-Bytes in der Standard-Lesart: Regler 130 -> gemeldet statt still
    assert not m.handle_msc(msc.parse_msc(_sx(1, msc.SET, bytes([2, 1, 0, 0x64]))))
    assert len(meldungen) == 1 and "Regler 130" in meldungen[0][1]


@pytest.mark.parametrize("fmt, ok", [
    (0x01, True), (0x02, True), (0x0F, True), (0x7F, True),
    (0x00, False), (0x10, False), (0x20, False), (0x30, False), (0x60, False),
])
def test_command_format_nur_licht(fmt, ok):
    """Mit Device-ID 0x7F darf ein GO fuer Ton/Maschinerie keine Licht-Cue
    ausloesen."""
    assert msc.get_settings().device_id == msc.ALL_DEVICES
    c = msc.parse_msc(_sx(0x7F, msc.GO, b"1", fmt=fmt))
    assert (c is not None) is ok
    assert (_decode(_sx(0x7F, msc.GO, b"1", fmt=fmt), "Pult") is not None) is ok


def test_command_format_alle_annehmen_und_udp():
    assert msc.MscSettings().all_formats is False
    assert msc.parse_gma_udp(_gma(_sx(0x7F, msc.GO, b"1", fmt=0x10))) is None
    msc.get_settings().all_formats = True
    assert msc.parse_msc(_sx(0x7F, msc.GO, b"1", fmt=0x10)) is not None
    assert msc.parse_gma_udp(_gma(_sx(0x7F, msc.GO, b"1", fmt=0x10))) is not None


def test_ton_go_loest_keine_cue_aus():
    m = _mapper()
    m._learn_mode, m._learn_callback, m._mappings = False, None, []
    msg = _decode(_sx(0x7F, msc.GO, b"1", fmt=0x10), "Pult")
    if msg is not None:
        m._on_midi(msg)
    assert m._state.playback_engine.executors[0].stack.log == []


def test_set_belegung_und_formate_dauerhaft(tmp_path, monkeypatch):
    import json
    import src.core.paths as paths
    monkeypatch.setattr(paths, "app_data_dir", lambda: str(tmp_path))
    st = msc.get_settings()
    st.set_layout, st.all_formats = msc.SET_STANDARD, True
    assert msc.save_settings()
    sek = json.loads((tmp_path / "ui_prefs.json").read_text())["midi_msc"]
    assert sek["set_layout"] == "standard" and sek["all_formats"] is True
    st.set_layout, st.all_formats = msc.SET_GRANDMA, False
    msc.load_settings()
    assert (st.set_layout, st.all_formats) == (msc.SET_STANDARD, True)
    # kaputte Werte aendern nichts
    (tmp_path / "ui_prefs.json").write_text(json.dumps(
        {"midi_msc": {"set_layout": "quatsch", "all_formats": "ja"}}))
    msc.load_settings()
    assert (st.set_layout, st.all_formats) == (msc.SET_STANDARD, True)


def test_udp_befehl_erreicht_monitor_beobachter():
    """Per UDP empfangene Befehle muessen im MIDI-Monitor sichtbar sein
    (Quelle 'MSC/UDP') — sie laufen nicht ueber den MIDI-Manager."""
    m = _mapper()
    gesehen = []
    m.subscribe_msc(gesehen.append)
    st = msc.get_settings()
    st.udp_enabled, st.udp_host, st.udp_port = True, "127.0.0.1", 0
    try:
        assert m.apply_msc_udp()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(_gma(_sx(1, msc.GO, b"\x002")), ("127.0.0.1", m._msc_udp.port))
        s.close()
        t0 = time.monotonic()
        while not gesehen and time.monotonic() - t0 < 2.0:
            time.sleep(0.02)
    finally:
        m._msc_udp.stop()
    assert len(gesehen) == 1
    assert gesehen[0].port_name == "MSC/UDP" and gesehen[0].msg_type == "msc"
    assert gesehen[0].msc.cue_list == "2"
    assert m._state.playback_engine.executors[1].stack.log == ["go"]   # genau einmal
    m.unsubscribe_msc(gesehen.append)
    m._on_msc_udp(msc.parse_msc(_sx(1, msc.GO, b"\x003")))
    assert len(gesehen) == 1


def test_udp_monitor_fehler_stoppt_befehl_nicht(meldungen):
    m = _mapper()

    def kaputt(_msg):
        raise RuntimeError("Monitor weg")

    m.subscribe_msc(kaputt)
    assert m._on_msc_udp(msc.parse_msc(_sx(1, msc.GO, b"\x002")))
    assert m._state.playback_engine.executors[1].stack.log == ["go"]
    assert meldungen and meldungen[0][0] == "midi.msc"
