"""MIDI-7 (MIDI-Clock -> BPM) und MTC-04 (Timecode als Cue-Ausloeser).

Ohne echte Hardware: Attrappen fuer rtmidi-Eingang, BPM-Manager und Cuelisten.
Beide Plattform-Pfade liefern in dieselbe Empfangsschleife des MidiManager —
python-rtmidi mit der rohen Nachricht (``[0xF8]``), WinMM als kurze Nachricht
mit Fuellbytes (``[0xF8, 0, 0]``); beide Formen werden hier eingespeist.
"""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from src.core.midi import midi_manager as mm
from src.core.midi.midi_clock import MidiClock


# ── Gemeinsamer Empfangspfad ────────────────────────────────────────────────

def test_rtmidi_laesst_clock_und_mtc_durch():
    class _In:
        args = None

        def ignore_types(self, **kw):
            self.args = kw

    m = _In()
    mm._sysex_freigeben(m)
    assert m.args["timing"] is False, "timing=True verwirft 0xF8 UND 0xF1"
    assert m.args["sysex"] is False and m.args["active_sense"] is True


def _warte(bedingung, timeout=2.0):
    ende = time.monotonic() + timeout
    while time.monotonic() < ende:
        if bedingung():
            return True
        time.sleep(0.01)
    return bedingung()


@pytest.fixture
def manager():
    m = mm.MidiManager()
    yield m
    m._rx_running = False
    m._rx_thread.join(1.0)


@pytest.mark.parametrize("roh", [[0xF8], [0xF8, 0, 0], [0xF1, 0x23], [0xF1, 0x23, 0],
                                 [0xFA], [0xFC, 0, 0]])
def test_echtzeit_geht_an_echtzeit_abonnenten_nicht_an_mappings(manager, roh):
    echtzeit, mappings = [], []
    manager.subscribe_echtzeit(lambda raw, port, zeit: echtzeit.append((raw, port)))
    manager.subscribe(mappings.append)
    manager._on_message(roh, "Pult")
    manager._on_message([0x90, 60, 100], "Pult")       # normale Note danach
    assert _warte(lambda: mappings)
    assert echtzeit == [(roh, "Pult")]
    assert [m.msg_type for m in mappings] == ["note_on"]


def test_mtc_vollbild_sysex_geht_an_echtzeit(manager):
    echtzeit = []
    manager.subscribe_echtzeit(lambda raw, port, zeit: echtzeit.append(raw))
    voll = [0xF0, 0x7F, 0x7F, 0x01, 0x01, 0x20 | 1, 2, 3, 4, 0xF7]
    manager._on_message(voll, "Pult")
    assert _warte(lambda: echtzeit)
    assert echtzeit == [voll]


# ── MIDI-7: Clock -> BPM ────────────────────────────────────────────────────

class _Mgr:
    def __init__(self):
        self.calls = []

    def request_bpm(self, bpm, source):
        self.calls.append((bpm, source))


def _ticks(clock, bpm, n, t0=100.0, jitter=None):
    dt = 60.0 / (bpm * 24)
    t = t0
    for i in range(n):
        j = jitter[i % len(jitter)] if jitter else 0.0
        clock.einspeisen(0xF8, t + j)
        t += dt
    return t


def test_clock_meldet_120_bpm():
    mgr = _Mgr()
    c = MidiClock(mgr)
    c.einspeisen(0xFA, 99.9)
    _ticks(c, 120.0, 49)
    assert mgr.calls and mgr.calls[-1] == (120.0, "midi_clock")


def test_clock_glaettet_jitter():
    mgr = _Mgr()
    c = MidiClock(mgr)
    _ticks(c, 128.0, 24 * 8, jitter=[0.0, 0.002, -0.0015, 0.001])
    assert mgr.calls
    assert all(abs(b - 128.0) <= 0.5 for b, _ in mgr.calls)


def test_clock_meldet_hoechstens_einmal_je_viertel_und_nur_bei_aenderung():
    mgr = _Mgr()
    c = MidiClock(mgr)
    _ticks(c, 100.0, 24 * 10)
    assert len(mgr.calls) == 1 and mgr.calls[0][0] == 100.0


def test_stop_verwirft_fenster_start_misst_neu():
    mgr = _Mgr()
    c = MidiClock(mgr)
    t = _ticks(c, 120.0, 49)
    c.einspeisen(0xFC, t)
    assert c.laeuft is False
    c.einspeisen(0xFA, t + 5)
    assert c.laeuft is True
    _ticks(c, 90.0, 49, t0=t + 5.01)
    assert mgr.calls[-1] == (90.0, "midi_clock")


def test_luecke_beginnt_neu_statt_langsamem_takt():
    mgr = _Mgr()
    c = MidiClock(mgr)
    t = _ticks(c, 120.0, 30)
    _ticks(c, 120.0, 30, t0=t + 3.0)     # 3 s Pause mitten im Fenster
    assert all(b == 120.0 for b, _ in mgr.calls)


def test_clock_haengt_sich_an_manager(manager):
    mgr = _Mgr()
    c = MidiClock(mgr)
    c.aktivieren(manager)
    assert c.aktiv
    c._on_echtzeit([0xF8, 0, 0], "WinMM-Pult", 1.0)          # WinMM-Form
    assert len(c._zeiten) == 1
    c.deaktivieren()
    assert not c.aktiv and c._on_echtzeit not in manager._echtzeit_callbacks


# ── MIDI-7: Quelle im BPM-Umschalter ────────────────────────────────────────

class _Clock:
    def __init__(self):
        self.calls = []

    def aktivieren(self):
        self.calls.append("an")

    def deaktivieren(self):
        self.calls.append("aus")


class _BpmMgr:
    mode = "auto"
    audio_active = False
    current_source = "off"

    def __init__(self):
        self.calls = []

    def use_audio_source(self, on):
        self.calls.append(("use_audio_source", on))

    def set_mode(self, m):
        self.calls.append(("set_mode", m))

    def reset(self):
        self.calls.append(("reset",))


class _Srv:
    def is_running(self):
        return False


class _Cap:
    def is_running(self):
        return False


def test_quelle_midi_clock_schaltet_clock_an_und_wieder_aus(monkeypatch):
    from src.ui import bpm_source_controller as bsc
    monkeypatch.setattr(bsc.SourceController, "_seed_memory", lambda self: None)
    clock, mgr = _Clock(), _BpmMgr()
    ctrl = bsc.SourceController(mgr=mgr, cap=_Cap(), os2l=_Srv(), det=None, clock=clock)
    assert ctrl.apply("midi_clock") is True
    assert clock.calls == ["an"]
    assert ("use_audio_source", False) in mgr.calls
    assert ctrl.apply("midi_clock") is False                 # idempotent
    ctrl.apply("off")
    assert clock.calls == ["an", "aus"]


def test_midi_clock_gespeichert_und_sperrt_titel_takt():
    from src.core.audio import bpm_settings
    from src.ui import bpm_source_controller as bsc
    assert "midi_clock" in bpm_settings.SOURCES
    assert "midi_clock" in bsc.KINDS
    assert "midi_clock" in bsc.FALLBACK_GESPERRT


# ── MTC-04: MTC ueber den gemeinsamen Pfad ──────────────────────────────────

def _qf_satz(h, m, s, f, fps_code=1):
    werte = [f & 0xF, f >> 4, s & 0xF, s >> 4, m & 0xF, m >> 4,
             h & 0xF, ((h >> 4) & 1) | (fps_code << 1)]
    return [[0xF1, (i << 4) | v, 0] for i, v in enumerate(werte)]   # WinMM-Form


def test_mtc_reader_liest_ueber_manager_auch_ohne_rtmidi(manager):
    from src.core.timecode.mtc_reader import MTCReader
    r = MTCReader()
    r.an_manager_haengen(manager)
    r.an_manager_haengen(manager)                   # idempotent
    assert manager._echtzeit_callbacks.count(r._on_manager) == 1
    for raw in _qf_satz(0, 1, 2, 10):
        manager._on_message(raw, "WinMM-Pult")
    assert _warte(lambda: r.time() == (0, 1, 2, 12))   # +2-Frame-Korrektur


def test_mtc_reader_ignoriert_manager_bei_eigenem_port():
    from src.core.timecode.mtc_reader import MTCReader
    r = MTCReader()
    r._midi_input = object()
    for raw in _qf_satz(0, 1, 2, 10):
        r._on_manager(raw)
    assert r.time() == (0, 0, 0, 0)


def test_mtc_reader_vollbild_ueber_manager():
    from src.core.timecode.mtc_reader import MTCReader
    r = MTCReader()
    r._on_manager([0xF0, 0x7F, 0x7F, 0x01, 0x01, 0x20 | 1, 2, 3, 4, 0xF7])
    assert r.time() == (1, 2, 3, 4) and r.fps() == 25.0


# ── MTC-04: Cue-Feld ────────────────────────────────────────────────────────

def test_cue_timecode_feld_rundreise_und_altbestand():
    from src.core.engine.cue import Cue
    c = Cue(1.0, timecode="0:1:2.3")
    assert c.timecode == "00:01:02:03"
    assert Cue.from_dict(c.to_dict()).timecode == "00:01:02:03"
    alt = c.to_dict()
    del alt["timecode"]
    assert Cue.from_dict(alt).timecode is None
    assert Cue(2.0, timecode="quatsch").timecode is None
    assert Cue(3.0, timecode="00:61:00:00").timecode is None


# ── MTC-04: Ausloesung ──────────────────────────────────────────────────────

def _liste(*tcs):
    from src.core.engine.cue import Cue
    from src.core.engine.cue_stack import CueStack
    st = CueStack("TC")
    for i, tc in enumerate(tcs):
        st.add_cue(Cue(float(i + 1), fade_in=0.0, timecode=tc))
    return st


def _sprung(a, st, h, m, s, f, fps=25.0):
    a.melden(h, m, s, f, fps)
    return [n for _st, n in a.anwenden([st])]


def test_ausloesung_bei_erreichen_und_ueberschreiten():
    from src.core.timecode.mtc_cues import TimecodeAusloeser
    st = _liste(None, "00:00:10:00", "00:00:20:00")
    a = TimecodeAusloeser()
    assert _sprung(a, st, 0, 0, 5, 0) == []
    assert _sprung(a, st, 0, 0, 9, 24) == []
    assert _sprung(a, st, 0, 0, 10, 2) == [2.0]          # ueberschritten
    assert st.current_cue.number == 2.0
    assert _sprung(a, st, 0, 0, 15, 0) == []             # nichts doppelt
    assert _sprung(a, st, 0, 0, 20, 0) == [3.0]          # genau erreicht


def test_sprung_ueber_mehrere_cues_nur_die_letzte():
    from src.core.timecode.mtc_cues import TimecodeAusloeser
    st = _liste("00:00:01:00", "00:00:02:00", "00:00:03:00")
    a = TimecodeAusloeser()
    _sprung(a, st, 0, 0, 0, 10)
    assert _sprung(a, st, 0, 0, 30, 0) == [3.0]


def test_ruecksprung_loest_nichts_aus_und_macht_wieder_scharf():
    from src.core.timecode.mtc_cues import TimecodeAusloeser
    st = _liste("00:00:10:00", "00:00:20:00")
    a = TimecodeAusloeser()
    _sprung(a, st, 0, 0, 9, 0)
    assert _sprung(a, st, 0, 0, 21, 0) == [2.0]
    assert _sprung(a, st, 0, 0, 5, 0) == []              # Ruecksprung
    assert st.current_cue.number == 2.0
    assert _sprung(a, st, 0, 0, 10, 0) == [1.0]          # wieder erreicht
    assert _sprung(a, st, 0, 0, 20, 0) == [2.0]


def test_cue_am_startpunkt_loest_beim_ersten_timecode_aus():
    from src.core.timecode.mtc_cues import TimecodeAusloeser
    st = _liste("00:00:00:00", "00:00:05:00")
    a = TimecodeAusloeser()
    assert _sprung(a, st, 0, 0, 0, 2) == [1.0]           # erster QF-Satz +2 Frames


def test_erster_timecode_weit_hinter_cue_loest_nicht_aus():
    from src.core.timecode.mtc_cues import TimecodeAusloeser
    st = _liste("00:00:01:00")
    a = TimecodeAusloeser()
    assert _sprung(a, st, 0, 10, 0, 0) == []


def test_ausloesung_im_render_takt_compute_merged(monkeypatch):
    """ENG-33: ``melden`` schaltet nichts; erst der Render-Tick loest aus."""
    from src.core.engine.executor import PlaybackEngine
    from src.core.timecode import mtc_cues
    a = mtc_cues.TimecodeAusloeser()
    monkeypatch.setattr(mtc_cues, "_ausloeser", a)
    pe = PlaybackEngine(None)
    st = _liste("00:00:10:00")
    pe.pages[3][5].stack = st                          # andere Page
    a.melden(0, 0, 9, 0, 25.0)
    pe.compute_merged()
    a.melden(0, 0, 10, 0, 25.0)
    assert st.current_cue is None                      # noch nicht geschaltet
    pe.compute_merged()
    assert st.current_cue is not None and st.current_cue.number == 1.0


def test_verdrahten_reicht_mtc_bis_zum_ausloeser(manager, monkeypatch):
    from src.core.timecode import mtc_cues, mtc_reader
    monkeypatch.setattr(mtc_cues, "_ausloeser", None)
    monkeypatch.setattr(mtc_reader, "_reader", None)
    a = mtc_cues.verdrahten(manager)
    assert mtc_cues.verdrahten(manager) is a
    st = _liste("00:00:01:00")
    for raw in _qf_satz(0, 0, 0, 20):
        manager._on_message(raw, "Pult")
    assert _warte(lambda: a._neu is not None)
    a.anwenden([st])
    for raw in _qf_satz(0, 0, 1, 0):
        manager._on_message(raw, "Pult")
    assert _warte(lambda: a._neu is not None)
    assert [n for _s, n in a.anwenden([st])] == [1.0]


# ── Review: Zeitstempel beim Empfang, Clock nur von EINEM Port ──────────────

def test_clock_zeitstempel_beim_empfang_nicht_beim_verteilen(manager, monkeypatch):
    """Haengt die Verteilschleife (langsamer Mapping-Abnehmer), stauen sich die
    Ticks in der Warteschlange. Gestempelt beim Verteilen kaemen sie dann alle
    im selben Augenblick an (Tempo-Spitze); gestempelt beim Empfang behalten sie
    ihren echten Abstand."""
    import threading
    import types
    manager._rx_running = False
    manager._rx_thread.join(1.0)
    uhr = {"t": 10.0}
    echt = mm.time
    attrs = {n: getattr(echt, n) for n in dir(echt) if not n.startswith("__")}
    attrs["perf_counter"] = lambda: uhr["t"]
    monkeypatch.setattr(mm, "time", types.SimpleNamespace(**attrs))
    zeiten = []
    manager.subscribe_echtzeit(lambda raw, port, zeit: zeiten.append(zeit))
    for i in range(3):
        uhr["t"] = 10.0 + i * 0.02
        manager._on_message([0xF8], "Pult")
    uhr["t"] = 99.0                       # Verteilen erst viel spaeter
    manager._rx_running = True
    manager._rx_thread = threading.Thread(target=manager._rx_loop, daemon=True)
    manager._rx_thread.start()
    assert _warte(lambda: len(zeiten) == 3)
    assert zeiten == pytest.approx([10.0, 10.02, 10.04])


def test_clock_von_zweitem_port_verdoppelt_takt_nicht():
    """Zwei Eingaenge mit Clock (Pult + DAW, oder Geraet + Durchleitung) duerfen
    sich nicht zu doppeltem Tempo mischen: gezaehlt wird der zuerst gehoerte Port."""
    mgr = _Mgr()
    c = MidiClock(mgr)
    dt = 60.0 / (120.0 * 24)
    for i in range(24 * 4):
        t = 100.0 + i * dt
        c._on_echtzeit([0xF8], "Pult", t)
        c._on_echtzeit([0xF8], "DAW", t + dt / 2)
    assert mgr.calls and all(b == 120.0 for b, _ in mgr.calls)


def test_clock_wechselt_port_nach_luecke():
    mgr = _Mgr()
    c = MidiClock(mgr)
    dt = 60.0 / (100.0 * 24)
    for i in range(49):
        c._on_echtzeit([0xF8], "Pult", 100.0 + i * dt)
    for i in range(49):                    # Pult schweigt, DAW uebernimmt
        c._on_echtzeit([0xF8], "DAW", 110.0 + i * dt * 100 / 140)
    assert mgr.calls[-1] == (140.0, "midi_clock")
