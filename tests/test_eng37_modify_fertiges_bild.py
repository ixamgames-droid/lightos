"""ENG-37: Modify rechnet auf das FERTIGE Bild vor den Mastern.

Regel (ein Ort, src/core/engine/modify.py + AppState._render_frame 4a²b):
ein Modify-Effekt verrechnet sich mit dem fertigen Wert der Schichten darunter
— Effekte, Cuelisten, Programmer/Snaps und automatische Grundhelligkeit — und
VOR Submastern/Fixture-Dimmern, DMX-Eingang, Grand Master, Blackout,
Ziel-Blackout und Laser-NOT-AUS. Wo sein Betrag 0 ist, bleibt alles
unveraendert.

Geprueft wird hier:

1. Snaps und Grundhelligkeit: ein Addieren-Modify schaltet die Lampen
   ausserhalb des Laeufers NICHT mehr aus; Abziehen/Abdunkeln wirken auf
   Snap-Werte und auf die Grundhelligkeit.
2. Master, DMX-Eingang, Blackout, Ziel-Blackout, NOT-AUS behalten das letzte
   Wort.
3. Modify als Kind einer Sammlung / Show: Helligkeit und Huellkurve der
   Sammlung skalieren nur die Staerke, der Untergrund bleibt exakt stehen.
4. Modify als Chaser-Schritt ist gesperrt (der Schritt gibt nichts aus).
"""
from __future__ import annotations

import os
import sys
import threading
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                               # noqa: E402

import src.core.app_state as A                              # noqa: E402
from src.core.app_state import AppState                     # noqa: E402
from src.core.dmx.universe import Universe                  # noqa: E402
from src.core.engine.chaser import ChaserStep               # noqa: E402
from src.core.engine.function_manager import FunctionManager  # noqa: E402
from src.core.engine.modify import MODIFY_MODES, modify_wert  # noqa: E402
from src.core.engine.rgb_matrix import (                    # noqa: E402
    MatrixStyle, RgbAlgorithm, RgbMatrixInstance)
from src.core.engine.show_engine import ShowFunction, ShowTrack  # noqa: E402

N = 8                 # acht Lampen: Dimmer, Rot, Gruen, Blau ab Adresse 1, 5, 9 …
P40 = 102             # 40 % von 255
DT = 0.02
LASER_FID = 20        # ein Laser mit eigenem Dimmer ab Adresse 100


class _Ch:
    def __init__(self, attribute, channel_number, default=0):
        self.attribute = attribute
        self.channel_number = channel_number
        self.default_value = default
        self.ranges = []


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 4
    protocol = ""
    fixture_name = ""

    def __init__(self, fid, address, universe=1, ftype=""):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.fixture_type = ftype


def _adr(i):
    """Dimmer-Adresse der Lampe mit Index ``i`` (0..7)."""
    return 1 + 4 * i


_KANAELE = {fid: [_Ch("intensity", 1), _Ch("color_r", 2),
                  _Ch("color_g", 3), _Ch("color_b", 4)]
            for fid in range(1, N + 1)}
_KANAELE[LASER_FID] = [_Ch("intensity", 1), _Ch("laser_x", 2),
                       _Ch("laser_y", 3), _Ch("shutter", 4)]


def _patch(mit_laser=False):
    p = [_Fx(fid, _adr(fid - 1)) for fid in range(1, N + 1)]
    if mit_laser:
        p.append(_Fx(LASER_FID, 100, ftype="laser"))
    return p


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(A, "get_channels_for_patched",
                        lambda fx: _KANAELE[fx.fid])
    return _patch()


def _matrix(name, algo=RgbAlgorithm.PLAIN, grid=None, **felder):
    grid = list(grid if grid is not None else range(1, N + 1))
    m = RgbMatrixInstance(name, cols=len(grid), rows=1, fixture_grid=grid,
                          algorithm=algo, color1=(255, 255, 255))
    m.style = MatrixStyle.DIMMER
    m.tempo_bus_id = ""
    m.matrix_speed = 1.0
    for k, v in felder.items():
        setattr(m, k, v)
    return m


def _pegel(wert=P40):
    return _matrix("unten", intensity_min=wert, intensity_max=wert)


def _lauflicht(mode="add", staerke=100, **params):
    """Modify-Lauflicht: zwei Laeufer (Lampe k und k+4), harte Kante."""
    m = _matrix("modify", RgbAlgorithm.CHASE)
    m.params.update({"runner_count": 2, "after_fade": 0.0,
                     "movement": "normal"})
    m.params.update(params)
    m.modify, m.modify_mode, m.modify_strength = True, mode, staerke
    return _spion(m)


def _spion(m):
    """Merkt sich den Betrag, den ``m`` zuletzt je Lampe ausgerechnet hat."""
    orig = m.write
    m.betrag = None

    def write(universes, patch_cache, dt, reg=None):
        orig(universes, patch_cache, dt, reg)
        roh = universes[1].get_all()
        m.betrag = [roh[_adr(i) - 1] for i in range(N)]
    m.write = write
    return m


def _aktiv(m):
    return [i for i, w in enumerate(m.betrag) if w == 255]


def _fm(*funktionen, start=None):
    fm = FunctionManager()
    for f in funktionen:
        fm.add(f)
    for f in (start if start is not None else funktionen):
        fm.start(f.id)
    return fm


def _zustand(fm, om=None, mit_laser=False):
    """Schlanker AppState mit ECHTEM FunctionManager (und wahlweise echtem
    OutputManager fuer Grand Master/Blackout)."""
    st = AppState.__new__(AppState)
    if om is not None:
        st.universes = {1: om.add_universe(1)}
        st.output_manager = om
    else:
        st.universes = {1: Universe(1)}
        st.output_manager = types.SimpleNamespace(
            set_gm_address_mask=lambda m: None)
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = fm
    st._patch_cache = _patch(mit_laser)
    st._fix_index = {}
    st._default_frame = {}
    st._commit_spans = {}
    st._patched_set = {}
    st._engine_extra_prev = {}
    st.submaster_level = 1.0
    st.fixture_dimmers = {}
    st.selected_fids = []
    st.programmer_focus = None
    st.base_levels = {}
    st.laser_estop_active = False
    st._laser_estop_addrs = {}
    st._laser_fids = frozenset()
    st._suppress_emits = True
    st._prog_lock = threading.RLock()
    st._rebuild_render_plan()
    return st


def _dimmer(st):
    roh = st.universes[1].get_all()
    return [roh[_adr(i) - 1] for i in range(N)]


def _soll(mode, unten, aktiv, s=1.0):
    return [modify_wert(mode, unten, 255, s) if i in aktiv else unten
            for i in range(N)]


# ── (1) Snaps und Grundhelligkeit ────────────────────────────────────────────


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_farb_snap_grundhelligkeit_bleibt_ausserhalb_des_laeufers(rig, mode):
    """Nur ein Farb-Snap (Programmer-Farbe, kein Dimmer): die Lampen leuchten
    ueber die automatische Grundhelligkeit (100 %). Ein Modify-Effekt schaltet
    die Grundhelligkeit NICHT ab — ausserhalb des Laeufers bleibt 100 %,
    darunter wird addiert (bleibt 100 %) bzw. abgezogen/abgedunkelt."""
    mod = _lauflicht(mode)
    st = _zustand(_fm(mod))
    st.programmer = {fid: {"color_r": 255} for fid in range(1, N + 1)}
    st._render_frame(DT)
    aktiv = _aktiv(mod)
    assert len(aktiv) == 2
    assert _dimmer(st) == _soll(mode, 255, aktiv)
    if mode != "add":
        assert sorted(_dimmer(st)) == [0] * 2 + [255] * 6


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_reiner_farb_effekt_grundhelligkeit_bleibt(rig, mode):
    """Reiner Farb-Effekt (Matrix Stil RGB, treibt den Dimmer nicht) + Modify."""
    farbe = RgbMatrixInstance("farbe", cols=N, rows=1,
                              fixture_grid=list(range(1, N + 1)),
                              algorithm=RgbAlgorithm.PLAIN, color1=(255, 0, 0))
    farbe.style = MatrixStyle.RGB
    farbe.tempo_bus_id = ""
    mod = _lauflicht(mode, 50)
    st = _zustand(_fm(farbe, mod))
    st._render_frame(DT)
    aktiv = _aktiv(mod)
    assert len(aktiv) == 2
    assert _dimmer(st) == _soll(mode, 255, aktiv, 0.5)
    # Farbe und Dimmer bleiben getrennt: die Farbkanaele fasst der Modify nicht an
    roh = st.universes[1].get_all()
    assert [roh[_adr(i)] for i in range(N)] == [255] * N


@pytest.mark.parametrize("mode", MODIFY_MODES)
@pytest.mark.parametrize("staerke", [100, 50])
def test_dimmer_snap_wird_verrechnet(rig, mode, staerke):
    """Dimmer-Snap auf 40 % (Programmer-Schicht): der Modify wirkt auf den
    Snap-Wert, ausserhalb des Laeufers bleibt er exakt 40 %."""
    mod = _lauflicht(mode, staerke)
    st = _zustand(_fm(mod))
    st.programmer = {fid: {"intensity": P40} for fid in range(1, N + 1)}
    st._render_frame(DT)
    aktiv = _aktiv(mod)
    assert len(aktiv) == 2
    assert _dimmer(st) == _soll(mode, P40, aktiv, staerke / 100.0)


def test_farb_und_dimmer_snap_zusammen(rig):
    """Wie der Betreiber seine Shows baut: Farb-Taste + Dimmer-Taste + Modify."""
    mod = _lauflicht("add")
    st = _zustand(_fm(mod))
    st.programmer = {fid: {"color_b": 200, "intensity": P40}
                     for fid in range(1, N + 1)}
    for _ in range(60):
        st._render_frame(DT)
        aktiv = _aktiv(mod)
        assert _dimmer(st) == [255 if i in aktiv else P40 for i in range(N)]
        roh = st.universes[1].get_all()
        assert [roh[_adr(i) + 2] for i in range(N)] == [200] * N


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_cueliste_wird_verrechnet(rig, mode):
    mod = _lauflicht(mode)
    st = _zustand(_fm(mod))
    st.playback_engine = types.SimpleNamespace(
        compute_merged=lambda: {fid: {"intensity": P40}
                                for fid in range(1, N + 1)})
    st._render_frame(DT)
    assert _dimmer(st) == _soll(mode, P40, _aktiv(mod))


def test_nichts_darunter(rig):
    """Addieren ohne irgendetwas darunter addiert auf 0: es leuchtet, wo der
    Laeufer ist. Abziehen/Abdunkeln bleiben dunkel."""
    for mode in MODIFY_MODES:
        mod = _lauflicht(mode)
        st = _zustand(_fm(mod))
        st._render_frame(DT)
        aktiv = _aktiv(mod)
        assert len(aktiv) == 2
        soll = [255 if (mode == "add" and i in aktiv) else 0 for i in range(N)]
        assert _dimmer(st) == soll


def test_modify_ist_kein_besitzer_des_dimmers(rig):
    """Der Modify-Effekt schreibt im Funktions-Durchlauf nichts — er steht in
    keinem Schreib-Protokoll und hinterlaesst nach dem Verrechnen keinen
    Posten."""
    mod = _lauflicht("add")
    fm = _fm(mod)
    u = Universe(1)
    u.begin_write_log()
    fm.tick({1: u}, rig, DT, modify_spaeter=True)
    assert u.end_write_log() == set()
    assert u.get_all() == bytes(512)
    assert fm.modify_anwenden({1: u}) is True
    assert sorted(u.get_all()[_adr(i) - 1] for i in range(N)) == [0] * 6 + [255] * 2
    assert fm.modify_anwenden({1: u}) is False       # verbraucht


def test_ohne_modify_kein_posten_und_kein_aufwand(rig):
    unten = _pegel()
    fm = _fm(unten)
    u = Universe(1)
    fm.tick({1: u}, rig, DT, modify_spaeter=True)
    assert fm._modify_posten == []
    assert fm.modify_anwenden({1: u}) is False


def test_haken_bei_anderem_stil_laeuft_normal(rig):
    """Stil Shutter mit gesetztem Haken: kein Modify, kein Posten.
    (Stil RGB/RGBW verrechnet seit ENG-38 — tests/test_eng38_modify_farbe.py.)"""
    m = _matrix("shutter", grid=[LASER_FID])
    m.style = MatrixStyle.SHUTTER
    m.modify = True
    fm = _fm(m)
    u = Universe(1)
    fm.tick({1: u}, _patch(mit_laser=True), DT, modify_spaeter=True)
    assert fm._modify_posten == []
    assert u.get_channel(100 + 3) == 255              # Shutter wurde gesetzt


# ── (2) Master, Eingang, Blackout, NOT-AUS haben das letzte Wort ─────────────


def test_submaster_und_fixture_dimmer_wirken_nach_dem_modify(rig):
    unten = _pegel()
    mod = _lauflicht("add")
    st = _zustand(_fm(unten, mod))
    st.submaster_level = 0.5
    st._render_frame(DT)
    aktiv = _aktiv(mod)
    assert _dimmer(st) == [int(255 * 0.5) if i in aktiv else int(P40 * 0.5)
                           for i in range(N)]

    unten = _pegel()
    mod = _lauflicht("add", runner_count=1)
    st = _zustand(_fm(unten, mod))
    st._render_frame(DT)
    lampe = _aktiv(mod)[0]
    unten = _pegel()
    mod = _lauflicht("add", runner_count=1)
    st = _zustand(_fm(unten, mod))
    st.fixture_dimmers = {lampe + 1: 0.0}             # Fader dieser Lampe zu
    st._render_frame(DT)
    assert _aktiv(mod) == [lampe]
    assert _dimmer(st)[lampe] == 0, "Modify hat einen zugezogenen Fader aufgehellt"


def test_dmx_eingang_gewinnt_ueber_modify(rig):
    mod = _lauflicht("add", runner_count=1)
    st = _zustand(_fm(mod))
    st._render_frame(DT)
    lampe = _aktiv(mod)[0]
    mod = _lauflicht("add", runner_count=1)
    st = _zustand(_fm(mod))
    st.input_layer = {1: {_adr(lampe): 7}}
    st.input_merge_modes = {1: "LTP"}
    st._render_frame(DT)
    assert _dimmer(st)[lampe] == 7


class _Sender:
    last = None

    def send_dmx(self, data):
        self.last = data

    def close(self):
        pass


def _gesendet(sender):
    return [sender.last[_adr(i) - 1] for i in range(N)]


def test_grand_master_und_blackout_nach_dem_modify(rig):
    from src.core.dmx.output_manager import OutputManager
    om = OutputManager()
    unten = _pegel()
    mod = _lauflicht("add")
    st = _zustand(_fm(unten, mod), om=om)
    sender = _Sender()
    om._enttec_outputs[1] = sender
    st._render_frame(DT)
    aktiv = _aktiv(mod)
    om._send_all()
    assert _gesendet(sender) == [255 if i in aktiv else P40 for i in range(N)]

    om.set_grand_master(0.5)
    st._render_frame(DT)
    aktiv = _aktiv(mod)
    om._send_all()
    assert _gesendet(sender) == [128 if i in aktiv else 51 for i in range(N)]

    om.set_grand_master(1.0)
    om.set_blackout(True)
    for _ in range(30):                               # der Laeufer wandert weiter
        st._render_frame(DT * 5)
        om._send_all()
        assert _gesendet(sender) == [0] * N, "Modify hat den Blackout aufgehellt"
    om.set_blackout(False)
    st._render_frame(DT)
    om._send_all()
    assert max(_gesendet(sender)) == 255


def test_ziel_blackout_nach_dem_modify(rig):
    from src.core.dmx.output_manager import OutputManager
    om = OutputManager()
    unten = _pegel()
    mod = _lauflicht("add")
    st = _zustand(_fm(unten, mod), om=om)
    sender = _Sender()
    om._enttec_outputs[1] = sender
    ziel = {_adr(i) for i in range(4)}                # Lampe 1–4
    om.set_target_blackout("t", {1: frozenset(ziel)})
    for _ in range(30):
        st._render_frame(DT * 5)
        aktiv = _aktiv(mod)
        om._send_all()
        assert _gesendet(sender) == [0 if i < 4 else (255 if i in aktiv else P40)
                                     for i in range(N)]


def _laser_modify(mode="add"):
    m = _matrix("laser-modify", grid=[LASER_FID])
    m.modify, m.modify_mode, m.modify_strength = True, mode, 100
    return m


def test_laser_not_aus_bleibt_aus(monkeypatch):
    """NOT-AUS aktiv + Addieren-Modify auf dem Laser-Dimmer = bleibt aus —
    im Renderer (4d) und noch einmal im Sendepfad des OutputManagers."""
    from src.core.dmx.output_manager import OutputManager
    monkeypatch.setattr(A, "get_channels_for_patched",
                        lambda fx: _KANAELE[fx.fid])
    om = OutputManager()
    st = _zustand(_fm(_laser_modify()), om=om, mit_laser=True)
    sender = _Sender()
    om._enttec_outputs[1] = sender
    assert LASER_FID in st._laser_fids, "Test-Laser wird nicht als Laser erkannt"

    # ohne NOT-AUS wirkt der Modify auf den Laser-Dimmer wie jeder Dimmer-Effekt
    st._render_frame(DT)
    assert st.universes[1].get_channel(100) == 255

    st.set_laser_estop(True)
    for _ in range(10):
        st._render_frame(DT)
        assert st.universes[1].get_all()[99:103] == bytes(4)
        om._send_all()
        assert sender.last[99:103] == bytes(4), "Modify hat den NOT-AUS aufgehellt"


def test_laser_not_aus_auch_ohne_sendepfad(monkeypatch):
    """Nur der Renderer (Ebene 4d), Flag direkt gesetzt."""
    monkeypatch.setattr(A, "get_channels_for_patched",
                        lambda fx: _KANAELE[fx.fid])
    st = _zustand(_fm(_laser_modify()), mit_laser=True)
    st.laser_estop_active = True
    st._render_frame(DT)
    assert st.universes[1].get_all()[99:103] == bytes(4)


def test_renderer_mit_manager_ohne_modify_schnittstelle(rig):
    """Ein Manager-Ersatz ohne ``modify_anwenden`` (so bauen ihn aeltere Tests)
    wird wie bisher mit drei Argumenten gerufen."""
    aufrufe = []

    class _Alt:
        def tick(self, universes, patch_cache, dt):
            aufrufe.append(dt)

    st = _zustand(FunctionManager())
    st.function_manager = _Alt()
    st._render_frame(DT)
    assert aufrufe == [DT]


def test_renderer_mit_gepatchtem_tick(rig):
    """Aeltere Tests ersetzen ``tick`` am ECHTEN Manager durch eine Funktion
    mit drei Argumenten — der Renderer muss sie weiter so rufen."""
    fm = FunctionManager()
    st = _zustand(fm)

    def _tick(universes, patch_cache, dt):
        universes[1].set_channel(_adr(0), 200)
    fm.tick = _tick
    st._render_frame(DT)
    assert _dimmer(st)[0] == 200
    assert getattr(fm, "_modify_aufschieben", False) is False


def test_tick_allein_nach_einem_renderer_frame_verrechnet_sofort(rig):
    """Das Aufschieben gilt nur fuer den Frame des Renderers."""
    unten = _pegel()
    mod = _lauflicht("add")
    fm = _fm(unten, mod)
    st = _zustand(fm)
    st._render_frame(DT)
    u = Universe(1)
    fm.tick({1: u}, rig, DT)
    aktiv = _aktiv(mod)
    assert [u.get_all()[_adr(i) - 1] for i in range(N)] == [
        255 if i in aktiv else P40 for i in range(N)]


# ── (3) Modify als Kind einer Sammlung / Show ────────────────────────────────


def _sammlung(fm, mod, helligkeit=1.0, einblenden=0.0):
    col = fm.new_collection("Sammlung")
    col.function_ids = [mod.id]
    col.intensity = helligkeit
    col.env_fade_in = einblenden
    return col


def _lauf_mit_sammlung(rig, mode, helligkeit, einblenden, sammlung_zuerst,
                       frames=45):
    unten = _pegel()
    mod = _lauflicht(mode)
    fm = FunctionManager()
    fm.add(unten)
    fm.add(mod)
    col = _sammlung(fm, mod, helligkeit, einblenden)
    for f in ((col, unten) if sammlung_zuerst else (unten, col)):
        fm.start(f.id)
    bilder = []
    for _ in range(frames):
        u = Universe(1)
        fm.tick({1: u}, rig, DT)
        bild = [u.get_all()[_adr(i) - 1] for i in range(N)]
        aktiv = _aktiv(mod)
        assert len(aktiv) == 2
        for i in range(N):
            if i not in aktiv:
                assert bild[i] == P40, (
                    f"Untergrund mitgedimmt: Lampe {i + 1} = {bild[i]}")
        bilder.append((bild, tuple(aktiv)))
    return bilder


@pytest.mark.parametrize("mode", MODIFY_MODES)
@pytest.mark.parametrize("helligkeit", [1.0, 0.5])
def test_sammlung_helligkeit_skaliert_nur_die_staerke(rig, mode, helligkeit):
    paare = [_lauf_mit_sammlung(rig, mode, helligkeit, 0.0, zuerst)
             for zuerst in (True, False)]
    assert paare[0] == paare[1], "Startreihenfolge aendert das Bild"
    for bild, aktiv in paare[0]:
        assert bild == _soll(mode, P40, aktiv, helligkeit)


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_sammlung_einblendzeit_skaliert_nur_die_staerke(rig, mode):
    """0,5 s Einblendzeit der Sammlung: unter dem Laeufer waechst die Wirkung
    von 0 auf voll, der Untergrund bleibt in JEDEM Frame exakt 40 %."""
    paare = [_lauf_mit_sammlung(rig, mode, 1.0, 0.5, zuerst)
             for zuerst in (True, False)]
    assert paare[0] == paare[1], "Startreihenfolge aendert das Bild"
    wirkung = [abs(bild[aktiv[0]] - P40) for bild, aktiv in paare[0]]
    assert wirkung == sorted(wirkung), "Einblenden laeuft nicht monoton"
    # (Abziehen ist schon bei 40 % Staerke am Anschlag 0 -> danach gleich)
    assert wirkung[0] < wirkung[5] <= wirkung[-1]
    voll = abs(modify_wert(mode, P40, 255, 1.0) - P40)
    assert wirkung[-1] == voll                         # nach 0,9 s voll da
    assert wirkung[0] <= voll * 0.1


def test_sammlung_halbe_helligkeit_mit_einblendzeit(rig):
    for bild, aktiv in _lauf_mit_sammlung(rig, "add", 0.5, 0.5, True)[30:]:
        assert bild == _soll("add", P40, aktiv, 0.5)


def test_sammlung_im_renderer_ueber_dimmer_snap(rig):
    """Sammlung mit Modify-Kind auf 50 % ueber einem Dimmer-Snap."""
    mod = _lauflicht("sub")
    fm = FunctionManager()
    fm.add(mod)
    col = _sammlung(fm, mod, 0.5)
    fm.start(col.id)
    st = _zustand(fm)
    st.programmer = {fid: {"intensity": 200} for fid in range(1, N + 1)}
    st._render_frame(DT)
    assert _dimmer(st) == _soll("sub", 200, _aktiv(mod), 0.5)


def test_sammlung_normale_kinder_wie_bisher(rig):
    """Ohne Modify-Kind dimmt die Sammlung ihre Kinder wie vorher."""
    a = _pegel(200)
    fm = FunctionManager()
    fm.add(a)
    col = fm.new_collection("Sammlung")
    col.function_ids = [a.id]
    col.intensity = 0.5
    fm.start(col.id)
    u = Universe(1)
    fm.tick({1: u}, rig, DT)
    assert [u.get_all()[_adr(i) - 1] for i in range(N)] == [100] * N


@pytest.mark.parametrize("helligkeit", [1.0, 0.5])
def test_show_zeitleiste_mit_modify_kind(rig, helligkeit):
    unten = _pegel()
    mod = _lauflicht("add")
    fm = FunctionManager()
    fm.add(unten)
    fm.add(mod)
    show = fm.new_show("Show")
    spur = ShowTrack()
    spur.add_function(ShowFunction(mod.id, 0.0, 60.0))
    show.tracks = [spur]
    show.intensity = helligkeit
    fm.start(unten.id)
    fm.start(show.id)
    gesehen = 0
    for _ in range(20):
        u = Universe(1)
        fm.tick({1: u}, rig, DT)
        if mod.betrag is None:
            continue
        gesehen += 1
        bild = [u.get_all()[_adr(i) - 1] for i in range(N)]
        assert bild == _soll("add", P40, _aktiv(mod), helligkeit)
    assert gesehen >= 10, "Die Show hat das Modify-Kind nie gespielt"


# ── (4) Chaser-Schritt: gesperrt ─────────────────────────────────────────────


def test_modify_als_chaser_schritt_gibt_nichts_aus(rig):
    """Gesperrt und dokumentiert: ein Modify-Effekt als Chaser-Schritt setzt
    NICHTS (er wuerde sonst alle Lampen ausserhalb des Laeufers ueberschreiben)
    und verrechnet nichts. Der Untergrund bleibt exakt stehen."""
    unten = _pegel()
    mod = _lauflicht("add")
    fm = FunctionManager()
    fm.add(unten)
    fm.add(mod)
    ch = fm.new_chaser("Chaser")
    ch.steps = [ChaserStep(function_id=mod.id, hold=5.0)]
    ch.tempo_bus_id = ""
    fm.start(unten.id)
    fm.start(ch.id)
    assert ch.is_running
    for _ in range(10):
        u = Universe(1)
        fm.tick({1: u}, rig, DT)
        assert [u.get_all()[_adr(i) - 1] for i in range(N)] == [P40] * N
    assert ch.is_running


def test_sammlung_mit_modify_kind_als_chaser_schritt(rig):
    """Die Sperre gilt auch eine Ebene tiefer: Schritt = Sammlung aus einem
    normalen Effekt und einem Modify-Effekt. Der normale Effekt laeuft, der
    Modify-Anteil gibt nichts aus (auch nicht doppelt ueber die zwei
    Probe-Renderings des Chasers)."""
    fm = FunctionManager()
    a = _pegel(77)
    mod = _lauflicht("add")
    fm.add(a)
    fm.add(mod)
    col = fm.new_collection("Sammlung")
    col.function_ids = [a.id, mod.id]
    ch = fm.new_chaser("Chaser")
    ch.steps = [ChaserStep(function_id=col.id, hold=5.0)]
    ch.tempo_bus_id = ""
    fm.start(ch.id)
    for _ in range(5):
        u = Universe(1)
        fm.tick({1: u}, rig, DT, modify_spaeter=True)
        assert fm._modify_posten == []
        assert [u.get_all()[_adr(i) - 1] for i in range(N)] == [77] * N


def test_normaler_effekt_als_chaser_schritt_wie_bisher(rig):
    fm = FunctionManager()
    a = _pegel(77)
    fm.add(a)
    ch = fm.new_chaser("Chaser")
    ch.steps = [ChaserStep(function_id=a.id, hold=5.0)]
    ch.tempo_bus_id = ""
    fm.start(ch.id)
    u = Universe(1)
    fm.tick({1: u}, rig, DT)
    assert [u.get_all()[_adr(i) - 1] for i in range(N)] == [77] * N
