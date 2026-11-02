"""CDX-64: Codex-Befunde zu #1212 (MIDI-Clock), #1215 (Mapping-Generator) und
#1217 (Speed-Dial-Basis).

* MIDI-Clock: ein MTC-only-Eingang darf den Clock-Port nicht beanspruchen
  (subscribe_echtzeit liefert auch Quarter-Frames).
* MIDI-Clock: eine im MANUAL-/Lock-Zustand abgelehnte Messung darf nicht als
  „gemeldet" gelten — sonst reicht eine gleichbleibende Clock ihr Tempo nach
  AUTO/Unlock nie wieder ein.
* Mapping-Generator: ``range`` ist bei Rastern mit Luecken nur die Huelle —
  erzeugt wird aus der expliziten Nummernliste.
* Speed-Dial: die gemerkte Free-Run-Basis haengt an der Effekt-Instanz, nicht
  nur an fid + Werten.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
import pytest

from src.core.midi.midi_clock import MidiClock

_app = QApplication.instance() or QApplication([])

_DT_120 = 60.0 / (120.0 * 24)


# ── #1212: MTC-Eingang beansprucht den Clock-Port nicht ─────────────────────

class _Mgr:
    def __init__(self):
        self.calls = []

    def request_bpm(self, bpm, source):
        self.calls.append((bpm, source))


def test_mtc_quarter_frame_beansprucht_clock_port_nicht():
    mgr = _Mgr()
    c = MidiClock(mgr)
    # MTC-Eingang meldet sich zuerst und sendet dann laufend Quarter-Frames
    # (100/s), verschraenkt mit der 120-BPM-Clock eines anderen Eingangs.
    c._on_echtzeit([0xF1, 0x00], "Timecode", 99.99)
    t_mtc = 99.99
    for i in range(24 * 4):
        t = 100.0 + i * _DT_120
        while t_mtc < t:
            t_mtc += 0.01
            c._on_echtzeit([0xF1, 0x10], "Timecode", t_mtc)
        c._on_echtzeit([0xF8], "Pult", t)
    assert mgr.calls and mgr.calls[-1] == (120.0, "midi_clock"), mgr.calls


# ── #1212: abgelehnte Messung wird nach AUTO/Unlock neu eingereicht ─────────

@pytest.fixture
def bpm_mgr():
    from src.core.engine.bpm_manager import BPMManager, BpmMode
    m = BPMManager()
    m.set_mode(BpmMode.MANUAL)
    yield m


@pytest.mark.parametrize("sperre", ["manual", "lock"])
def test_abgelehnte_messung_wird_nach_freigabe_neu_eingereicht(bpm_mgr, sperre):
    from src.core.engine.bpm_manager import BpmMode
    if sperre == "lock":
        bpm_mgr.set_mode(BpmMode.AUTO)
        bpm_mgr.set_locked(True)
    vorher = bpm_mgr.bpm
    c = MidiClock(bpm_mgr)
    c.einspeisen(0xFA, 99.9)
    t = 100.0
    for _ in range(49):                       # Messung im MANUAL/Lock: abgelehnt
        c.einspeisen(0xF8, t)
        t += _DT_120
    assert bpm_mgr.bpm == vorher
    if sperre == "lock":
        bpm_mgr.set_locked(False)
    else:
        bpm_mgr.set_mode(BpmMode.AUTO)
    for _ in range(48):                       # gleichbleibende Clock laeuft weiter
        c.einspeisen(0xF8, t)
        t += _DT_120
    assert bpm_mgr.bpm == pytest.approx(120.0), \
        "gleichbleibende Clock reicht ihr Tempo nach der Freigabe nicht neu ein"


def test_angenommene_messung_nach_manuell_und_zurueck_auf_auto_neu_eingereicht():
    """Clock laeuft in AUTO (angenommen), Nutzer ueberschreibt per Hand,
    schaltet zurueck auf AUTO: die gleichbleibende Clock muss ihr Tempo
    wieder einreichen (sonst bleibt die Hand-BPM stehen)."""
    from src.core.engine.bpm_manager import BPMManager, BpmMode
    m = BPMManager()
    m.set_mode(BpmMode.AUTO)
    c = MidiClock(m)
    c.einspeisen(0xFA, 99.9)
    t = 100.0
    for _ in range(49):
        c.einspeisen(0xF8, t)
        t += _DT_120
    assert m.bpm == pytest.approx(120.0) and m.current_source == "midi_clock"
    m.set_manual_bpm(100.0)                   # Hand-Override -> MANUAL
    for _ in range(24):
        c.einspeisen(0xF8, t)
        t += _DT_120
    assert m.bpm == pytest.approx(100.0)
    m.set_mode(BpmMode.AUTO)
    for _ in range(24):
        c.einspeisen(0xF8, t)
        t += _DT_120
    assert m.bpm == pytest.approx(120.0), \
        "Clock reicht nach Hand-Override + AUTO ihr Tempo nicht neu ein"
    assert m.current_source == "midi_clock"


def test_gleichbleibende_clock_meldet_nicht_jedes_viertel_neu():
    """Fuehrt der Manager die Clock schon, bleibt es bei einer Meldung."""
    from src.core.engine.bpm_manager import BPMManager, BpmMode

    class _Zaehler(BPMManager):
        n = 0

        def request_bpm(self, bpm, source="audio"):
            type(self).n += 1
            return super().request_bpm(bpm, source)

    m = _Zaehler()
    m.set_mode(BpmMode.AUTO)
    c = MidiClock(m)
    t = 100.0
    for _ in range(24 * 8):
        c.einspeisen(0xF8, t)
        t += _DT_120
    assert _Zaehler.n == 1


def test_request_bpm_meldet_annahme():
    from src.core.engine.bpm_manager import BPMManager, BpmMode
    m = BPMManager()
    m.set_mode(BpmMode.MANUAL)
    assert m.request_bpm(120.0, "midi_clock") is False
    m.set_mode(BpmMode.AUTO)
    assert m.request_bpm(120.0, "midi_clock") is True


# ── #1215: Generator nimmt die explizite Nummernliste ───────────────────────

def _lib():
    from src.core.controllers.controller_library import ControllerLibrary
    lib = ControllerLibrary()
    lib._load_dir(ControllerLibrary.builtin_dir(), builtin=True)
    lib._loaded = True
    return lib


def test_generator_nutzt_explizite_nummern_statt_huelle():
    from src.core.controllers.controller_library import (ControllerControl,
                                                         ControllerProfile)
    from src.core.controllers.mapping_generator import erzeuge_mapping_profil
    d = ControllerControl("Knobs", "cc", 0, [16, 93], "",
                          numbers=[74, 71, 76, 77, 93, 18, 19, 16]).to_dict()
    c = ControllerControl.from_dict(d)          # Rundreise erhaelt die Liste
    assert c.numbers == [74, 71, 76, 77, 93, 18, 19, 16] and c.count == 8
    prof = erzeuge_mapping_profil(ControllerProfile(id="x", model="X", controls=[c]))
    assert [m.data1 for m in prof.mappings] == [74, 71, 76, 77, 93, 18, 19, 16]


def test_minilab_encoder_nur_echte_ccs():
    from src.core.controllers.mapping_generator import erzeuge_mapping_profil
    prof = erzeuge_mapping_profil(_lib().find("arturia_minilab_3"))
    ccs = [m.data1 for m in prof.mappings if m.msg_type == "cc"]
    assert ccs[:8] == [74, 71, 76, 77, 93, 18, 19, 16], ccs
    assert 20 not in ccs and 35 not in ccs


@pytest.mark.parametrize("pid", ["novation_launchpad_pro_mk3",
                                 "novation_launchpad_mini_mk3",
                                 "novation_launchpad_x"])
def test_launchpad_raster_ohne_nicht_existierende_noten(pid):
    from src.core.controllers.mapping_generator import erzeuge_mapping_profil
    prof = erzeuge_mapping_profil(_lib().find(pid))
    noten = [m.data1 for m in prof.mappings if m.msg_type == "note_on"]
    assert noten, pid
    # Raster 10*Zeile+Spalte: Spalte 0/9 gibt es im 8x8-Grid nicht.
    assert 19 not in noten[:8] and 20 not in noten, noten
    assert noten[:10] == [11, 12, 13, 14, 15, 16, 17, 18, 21, 22]


def test_alle_eingebauten_nummernlisten_liegen_in_der_huelle():
    for p in _lib().all():
        for c in p.controls:
            if c.numbers:
                assert min(c.numbers) == c.range[0] and max(c.numbers) == c.range[1], \
                    (p.id, c.name)


# ── #1217: Speed-Dial-Basis haengt an der Effekt-Instanz ────────────────────

@pytest.fixture
def fm():
    from src.core.engine.function_manager import get_function_manager
    manager = get_function_manager()
    manager.stop_all()
    vorher = {f.id: f for f in manager.all()}
    yield manager
    manager.stop_all()
    for f in list(manager.all()):
        if vorher.get(f.id) is not f:
            manager.remove(f.id)
    for fid, f in vorher.items():
        if manager.get(fid) is None:
            manager._functions[fid] = f


def _dial(fids, factors, active):
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    d = VCSpeedDial("x")
    d.target_mode = SpeedTarget.TEMPO_BUS_MULT
    d.function_ids = list(fids)
    d.factor_buttons = list(factors)
    d._active_factor = d._mult = float(active)
    return d


def test_andere_show_mit_gleicher_id_und_werten_erbt_keine_basis(fm):
    from src.core.engine.efx import EfxInstance
    a = fm.new_efx("Show A")
    a.tempo_bus_id = ""
    a.tempo_multiplier = 1.0
    a.speed_hz = 5.0
    d = _dial([a.id], [1.0, 4.0], 1.0)
    d._set_factor(4.0)                       # Basis 5, speed 10 (geklemmt), ×4
    assert abs(a.speed_hz - 10.0) < 1e-9
    # Show B: anderer Effekt, gleiche fid, zufaellig 10 Hz bei ×4.
    b = EfxInstance("Show B")
    b.id = a.id
    b.tempo_bus_id = ""
    b.tempo_multiplier = 4.0
    b.speed_hz = 10.0
    fm._functions[a.id] = b                  # wie from_dict beim Show-Wechsel
    d2 = _dial([b.id], [1.0, 4.0], 4.0)
    d2._set_factor(1.0)
    assert abs(b.speed_hz - 2.5) < 1e-6, f"Basis der alten Show geerbt: {b.speed_hz}"
