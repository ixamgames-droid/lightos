"""ENG-38: Modify-Effekte im Stil FARBE (RGB/RGBW) — Schritt 2 von ENG-37.

Regel (src/core/engine/modify.py, RgbMatrixInstance._farb_modify):

* Ein Farb-Modify verrechnet JEDEN FARBKANAL EINZELN mit dem fertigen Bild
  darunter (Addieren / Abziehen / Abdunkeln, Betrag x Staerke) und kappt jeden
  Kanal fuer sich bei 0..255.
* Der DIMMER wird nie angefasst — weder geschrieben noch aufgezogen. Eine
  dunkle Lampe bleibt dunkel; die automatische Grundhelligkeit („Farbe heisst
  sichtbar") wird durch einen Farb-Modify weder ausgeloest noch veraendert.
* RGBW: der Weissanteil laeuft ueber den W-Kanal.
* Geraete ohne Farbkanaele (nur Farbrad) bleiben unberuehrt.
* Dimmer- und Farb-Modify rechnen nacheinander in ihrer Reihenfolge; Master
  und Blackout behalten das letzte Wort.

Alle Engine-Tests laufen ueber den ECHTEN Renderer (AppState._render_frame)
und den echten FunctionManager, wie tests/test_eng37_modify_fertiges_bild.py.
"""
from __future__ import annotations

import json
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

N = 8                 # acht Lampen: Dimmer, Rot, Gruen, Blau ab Adresse 1, 5, 9 …
P40 = 102             # 40 % von 255
DT = 0.02
FID_RGBW = 11         # Dimmer, R, G, B, W ab Adresse 41
FID_RGB = 12          # nur R, G, B ab Adresse 51 (kein Dimmer)
FID_RAD = 13          # Dimmer + Farbrad ab Adresse 61 (keine Farbkanaele)
FID_SHUTTER = 14      # Shutter + Dimmer ab Adresse 71


class _Ch:
    def __init__(self, attribute, channel_number, default=0):
        self.attribute = attribute
        self.channel_number = channel_number
        self.default_value = default
        self.ranges = []


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 5
    protocol = ""
    fixture_name = ""
    fixture_type = ""

    def __init__(self, fid, address, universe=1):
        self.fid = fid
        self.universe = universe
        self.address = address


def _adr(i):
    """Dimmer-Adresse der Lampe mit Index ``i`` (0..7); Rot/Gruen/Blau +1/+2/+3."""
    return 1 + 4 * i


_KANAELE = {fid: [_Ch("intensity", 1), _Ch("color_r", 2),
                  _Ch("color_g", 3), _Ch("color_b", 4)]
            for fid in range(1, N + 1)}
_KANAELE[FID_RGBW] = [_Ch("intensity", 1), _Ch("color_r", 2), _Ch("color_g", 3),
                      _Ch("color_b", 4), _Ch("color_w", 5)]
_KANAELE[FID_RGB] = [_Ch("color_r", 1), _Ch("color_g", 2), _Ch("color_b", 3)]
_KANAELE[FID_RAD] = [_Ch("intensity", 1), _Ch("color_wheel", 2)]
# Ein echtes Rad mit benannten Slots — ein NORMALER Farb-Effekt waehlt darauf
# den roten Slot (Mitte 109), siehe test_geraet_nur_mit_farbrad_…
_KANAELE[FID_RAD][1].ranges = [
    types.SimpleNamespace(name="Blau", range_from=20, range_to=39, kind="color"),
    types.SimpleNamespace(name="Rot", range_from=100, range_to=119, kind="color")]
_KANAELE[FID_SHUTTER] = [_Ch("shutter", 1), _Ch("intensity", 2)]
_ADRESSE = {FID_RGBW: 41, FID_RGB: 51, FID_RAD: 61, FID_SHUTTER: 71}


def _patch():
    p = [_Fx(fid, _adr(fid - 1)) for fid in range(1, N + 1)]
    p += [_Fx(fid, adr) for fid, adr in _ADRESSE.items()]
    return p


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(A, "get_channels_for_patched",
                        lambda fx: _KANAELE[fx.fid])
    return _patch()


def _matrix(name, farbe=(255, 255, 255), algo=RgbAlgorithm.PLAIN, grid=None,
            stil=MatrixStyle.RGB, **felder):
    grid = list(grid if grid is not None else range(1, N + 1))
    m = RgbMatrixInstance(name, cols=len(grid), rows=1, fixture_grid=grid,
                          algorithm=algo, color1=farbe)
    m.style = stil
    m.tempo_bus_id = ""
    m.matrix_speed = 1.0
    for k, v in felder.items():
        setattr(m, k, v)
    return m


def _modify(farbe, mode="add", staerke=100, **kw):
    m = _matrix("modify", farbe, **kw)
    m.modify, m.modify_mode, m.modify_strength = True, mode, staerke
    return m


def _lauflicht(farbe, mode="add", staerke=100, **kw):
    """Farb-Modify-Lauflicht: zwei Laeufer (Lampe k und k+4), harte Kante."""
    m = _modify(farbe, mode, staerke, algo=RgbAlgorithm.CHASE, **kw)
    m.params.update({"runner_count": 2, "after_fade": 0.0,
                     "movement": "normal"})
    return m


def _dimmer_matrix(name, pegel=None, **kw):
    m = _matrix(name, stil=MatrixStyle.DIMMER, **kw)
    if pegel is not None:
        m.intensity_min = m.intensity_max = pegel
    return m


def _fm(*funktionen):
    fm = FunctionManager()
    for f in funktionen:
        fm.add(f)
    for f in funktionen:
        fm.start(f.id)
    return fm


def _zustand(fm, om=None):
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
    st._patch_cache = _patch()
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


def _roh(st):
    return list(st.universes[1].get_all())


def _lampe(st, i):
    """(Dimmer, Rot, Gruen, Blau) der Lampe mit Index ``i``."""
    roh = _roh(st)
    a = _adr(i) - 1
    return tuple(roh[a:a + 4])


def _farben(st):
    return [_lampe(st, i)[1:] for i in range(N)]


def _dimmer(st):
    return [_lampe(st, i)[0] for i in range(N)]


def _bild(*funktionen, programmer=None, frames=1):
    st = _zustand(_fm(*funktionen))
    if programmer:
        st.programmer = programmer
    for _ in range(frames):
        st._render_frame(DT)
    return st


def _snap(**attrs):
    return {fid: dict(attrs) for fid in range(1, N + 1)}


# ── (1) Die Rechnung je Farbkanal ────────────────────────────────────────────


@pytest.mark.parametrize("mode", MODIFY_MODES)
@pytest.mark.parametrize("staerke", [100, 50, 0])
def test_jeder_farbkanal_wird_einzeln_verrechnet(rig, mode, staerke):
    """Unten ein normaler Farb-Effekt (100, 150, 200), darueber ein Farb-Modify
    mit dem Betrag (255, 51, 0): je Kanal dieselbe Formel wie beim Dimmer."""
    unten = _matrix("unten", (100, 150, 200))
    mod = _modify((255, 51, 0), mode, staerke)
    st = _bild(unten, mod)
    s = staerke / 100.0
    soll = (modify_wert(mode, 100, 255, s), modify_wert(mode, 150, 51, s),
            200)                              # Betrag 0 auf Blau: unveraendert
    assert _farben(st) == [soll] * N
    if staerke == 0:
        assert soll == (100, 150, 200)
    # Der Dimmer steht ueber die Grundhelligkeit auf voll — vom Modify unberuehrt.
    assert _dimmer(st) == [255] * N


def test_durchgerechnet_wie_in_der_anleitung(rig):
    """Feste Zahlen (dieselben wie in der Anleitung, Abschnitt Farbe)."""
    def farbe(mode, staerke):
        return _farben(_bild(_matrix("unten", (200, 100, 50)),
                             _modify((100, 200, 0), mode, staerke)))[0]
    assert farbe("add", 100) == (255, 255, 50)     # 300 -> 255 gekappt, je Kanal
    assert farbe("sub", 100) == (100, 0, 50)       # 100 - 200 -> 0 gekappt
    assert farbe("dim", 100) == (122, 22, 50)      # 200*(1-100/255), 100*(1-200/255)
    assert farbe("add", 50) == (250, 200, 50)
    assert farbe("sub", 50) == (150, 0, 50)
    assert farbe("dim", 50) == (161, 61, 50)


def test_kappung_je_kanal_farbton_darf_kippen(rig):
    """Orange + Rot -> Rot voll, Gruen bleibt: es wird je Kanal gekappt, der
    Farbton wird NICHT gehalten (Entscheidung im Konzept, Frage 6)."""
    st = _bild(_matrix("orange", (255, 128, 0)), _modify((255, 0, 0), "add"))
    assert _farben(st) == [(255, 128, 0)] * N
    st = _bild(_matrix("orange", (200, 128, 0)), _modify((255, 255, 255), "add"))
    assert _farben(st) == [(255, 255, 255)] * N
    st = _bild(_matrix("orange", (200, 128, 0)), _modify((255, 255, 255), "sub"))
    assert _farben(st) == [(0, 0, 0)] * N


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_nur_die_lampen_unter_dem_laeufer_aendern_sich(rig, mode):
    """Blauer Farb-Snap auf allen Lampen, rotes/blaues Modify-Lauflicht: nur die
    zwei Lampen unter dem Laeufer werden verrechnet, alle anderen bleiben
    Byte fuer Byte wie ohne den Modify-Effekt."""
    snap = _snap(color_r=40, color_b=200)
    ohne = _roh(_bild(programmer=snap))
    mod = _lauflicht((255, 0, 255), mode)
    st = _zustand(_fm(mod))
    st.programmer = snap
    gesehen = set()
    for _ in range(80):
        st._render_frame(DT * 3)
        roh = _roh(st)
        dran = [i for i in range(N) if _lampe(st, i)[1:] != (40, 0, 200)]
        assert len(dran) == 2 and dran[1] - dran[0] == 4
        gesehen.update(dran)
        for i in range(N):
            a = _adr(i) - 1
            if i in dran:
                assert tuple(roh[a + 1:a + 4]) == (
                    modify_wert(mode, 40, 255, 1.0), 0,
                    modify_wert(mode, 200, 255, 1.0))
            else:
                assert roh[a:a + 4] == ohne[a:a + 4]
        # Dimmer: Grundhelligkeit, ueberall und immer gleich
        assert _dimmer(st) == [255] * N
    assert gesehen == set(range(N)), "der Laeufer ist nicht ueber alle Lampen gewandert"


def test_nichts_darunter(rig):
    """Addieren rechnet auf 0 (die Farbe steht in den Farbkanaelen), Abziehen
    und Abdunkeln tun nichts."""
    assert _farben(_bild(_modify((10, 20, 30), "add"))) == [(10, 20, 30)] * N
    for mode in ("sub", "dim"):
        st = _bild(_modify((10, 20, 30), mode))
        assert _roh(st) == [0] * 512


# ── (2) Der Dimmer wird NIE angefasst ────────────────────────────────────────


@pytest.mark.parametrize("mode", MODIFY_MODES)
@pytest.mark.parametrize("drive", [False, True])
def test_dunkle_lampe_bleibt_dunkel(rig, mode, drive):
    """Nichts darunter, Farb-Modify laeuft: der Dimmer bleibt 0 — die
    Grundhelligkeit wird durch einen Farb-Modify NICHT ausgeloest, und ein
    (in Alt-Shows gesetztes) „Dimmer mitziehen" zaehlt im Modify-Betrieb nicht."""
    mod = _modify((255, 255, 255), mode, drive_intensity=drive,
                  grid=list(range(1, N + 1)) + [FID_RGBW])
    st = _zustand(_fm(mod))
    assert getattr(st, "implicit_brightness", True) is True
    for _ in range(5):
        st._render_frame(DT)
        assert _dimmer(st) == [0] * N
        assert _roh(st)[_ADRESSE[FID_RGBW] - 1] == 0
    if mode == "add":
        assert _farben(st) == [(255, 255, 255)] * N


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_grundhelligkeit_wird_nicht_veraendert(rig, mode):
    """Roter Farb-Snap -> Grundhelligkeit zieht den Dimmer auf voll. Ein
    Farb-Modify, der das Rot komplett wegnimmt, nimmt die Grundhelligkeit NICHT
    zurueck (sie ist vor dem Modify entschieden) — und zwar in jedem Frame."""
    mod = _modify((255, 0, 0), mode)
    st = _zustand(_fm(mod))
    st.programmer = _snap(color_r=200)
    for _ in range(6):
        st._render_frame(DT)
        assert _dimmer(st) == [255] * N
        assert _farben(st) == [(modify_wert(mode, 200, 255, 1.0), 0, 0)] * N


def test_grundhelligkeit_aus_bleibt_aus(rig):
    """Strikte Trennung (implicit_brightness=False): reine Farbe bleibt dunkel,
    auch mit Farb-Modify."""
    mod = _modify((0, 255, 0), "add")
    st = _zustand(_fm(mod))
    st.implicit_brightness = False
    st.programmer = _snap(color_r=200)
    st._render_frame(DT)
    assert _dimmer(st) == [0] * N
    assert _farben(st) == [(200, 255, 0)] * N


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_dimmer_snap_und_dimmer_effekt_bleiben_exakt(rig, mode):
    """Dimmer ueber Snap (40 %) bzw. ueber einen Dimmer-Effekt: ein Farb-Modify
    laesst den Wert exakt stehen."""
    st = _bild(_lauflicht((255, 255, 255), mode),
               programmer=_snap(intensity=P40, color_g=90))
    assert _dimmer(st) == [P40] * N
    st = _bild(_dimmer_matrix("pegel", 77), _matrix("farbe", (0, 90, 0)),
               _lauflicht((255, 255, 255), mode))
    assert _dimmer(st) == [77] * N
    assert sorted(set(_farben(st))) == sorted({
        (0, 90, 0), (modify_wert(mode, 0, 255, 1.0),
                     modify_wert(mode, 90, 255, 1.0),
                     modify_wert(mode, 0, 255, 1.0))})


@pytest.mark.parametrize("stil", [MatrixStyle.RGB, MatrixStyle.RGBW])
def test_farb_modify_schreibt_nur_farbadressen(rig, stil):
    """Der Posten eines Farb-Modify enthaelt ausschliesslich Farbadressen —
    keinen Dimmer, kein Farbrad, keinen Shutter."""
    mod = _modify((255, 200, 100), "add", drive_intensity=True,
                  grid=list(range(1, N + 1))
                  + [FID_RGBW, FID_RGB, FID_RAD, FID_SHUTTER], stil=stil)
    fm = _fm(mod)
    fm.tick({1: Universe(1)}, rig, DT, modify_spaeter=True)
    (_mode, _s, betraege), = fm._modify_posten
    adressen = {a for a, _w in betraege[1]}
    farbe = {_adr(i) + k for i in range(N) for k in (1, 2, 3)}
    farbe |= {_ADRESSE[FID_RGBW] + k for k in (1, 2, 3)}
    farbe |= {_ADRESSE[FID_RGB] + k for k in (0, 1, 2)}
    w = _ADRESSE[FID_RGBW] + 4
    if stil == MatrixStyle.RGB:
        assert adressen == farbe             # der W-Kanal gehoert nicht dazu
    else:
        # RGBW: Weissanteil 100 auf W, Rest (155, 100, 0) — Betrag 0 (Blau)
        # ist neutral und steht gar nicht erst im Posten.
        assert w in adressen
        assert adressen - {w} == {a for a in farbe
                                  if a not in {_adr(i) + 3 for i in range(N)}
                                  | {_ADRESSE[FID_RGBW] + 3,
                                     _ADRESSE[FID_RGB] + 2}}


# ── (3) RGBW: Weiss ueber den W-Kanal ────────────────────────────────────────


def _rgbw(st):
    a = _ADRESSE[FID_RGBW] - 1
    return tuple(_roh(st)[a:a + 5])          # Dimmer, R, G, B, W


def _rgbw_bild(mod, **snap):
    st = _zustand(_fm(mod))
    st.programmer = {FID_RGBW: snap}
    st._render_frame(DT)
    return st


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_rgbw_weiss_laeuft_ueber_den_w_kanal(rig, mode):
    """Stil RGBW, weisser Modify: verrechnet wird NUR der W-Kanal."""
    mod = _modify((255, 255, 255), mode, 50, grid=[FID_RGBW],
                  stil=MatrixStyle.RGBW)
    st = _rgbw_bild(mod, intensity=P40, color_r=50, color_g=60, color_b=70,
                    color_w=100)
    assert _rgbw(st) == (P40, 50, 60, 70, modify_wert(mode, 100, 255, 0.5))


def test_rgbw_mischfarbe_teilt_sich_auf(rig):
    """(255, 128, 128) = Weissanteil 128 auf W, Rest 127 auf Rot."""
    mod = _modify((255, 128, 128), "add", grid=[FID_RGBW], stil=MatrixStyle.RGBW)
    st = _rgbw_bild(mod, intensity=P40, color_r=10, color_g=20, color_b=30,
                    color_w=40)
    assert _rgbw(st) == (P40, 137, 20, 30, 168)


def test_stil_rgb_laesst_den_w_kanal_in_ruhe(rig):
    mod = _modify((255, 255, 255), "sub", grid=[FID_RGBW], stil=MatrixStyle.RGB)
    st = _rgbw_bild(mod, intensity=P40, color_r=50, color_g=60, color_b=70,
                    color_w=100)
    assert _rgbw(st) == (P40, 0, 0, 0, 100)


# ── (4) Geraete ohne Farbkanaele ─────────────────────────────────────────────


@pytest.mark.parametrize("mode", MODIFY_MODES)
@pytest.mark.parametrize("stil", [MatrixStyle.RGB, MatrixStyle.RGBW])
def test_geraet_nur_mit_farbrad_bleibt_unberuehrt(rig, mode, stil):
    """Ein Kopf mit Farbrad und Dimmer: der Farb-Modify fasst weder das Rad
    noch den Dimmer an — das Bild ist Byte fuer Byte wie ohne den Effekt."""
    snap = {FID_RAD: {"intensity": 180, "color_wheel": 33}}
    st0 = _zustand(_fm())
    st0.programmer = snap
    st0._render_frame(DT)
    mod = _modify((255, 0, 0), mode, grid=[FID_RAD], stil=stil,
                  drive_intensity=True)
    st = _zustand(_fm(mod))
    st.programmer = snap
    for _ in range(4):
        st._render_frame(DT)
        assert _roh(st) == _roh(st0)
    a = _ADRESSE[FID_RAD] - 1
    assert _roh(st)[a:a + 2] == [180, 33]
    # Gegenprobe: OHNE Haken stellt derselbe Effekt das Rad auf den roten Slot.
    mod.stop()
    normal = _matrix("normal", (255, 0, 0), grid=[FID_RAD], stil=stil)
    st = _zustand(_fm(normal))
    st._render_frame(DT)
    assert _roh(st)[a + 1] == 109


def test_reines_rgb_geraet_ohne_dimmer(rig):
    """Kein Dimmer-Kanal: die Farbe wird verrechnet, sonst nichts."""
    mod = _modify((0, 100, 255), "add", 50, grid=[FID_RGB])
    st = _zustand(_fm(mod))
    st.programmer = {FID_RGB: {"color_r": 10, "color_g": 20, "color_b": 30}}
    st._render_frame(DT)
    a = _ADRESSE[FID_RGB] - 1
    assert _roh(st)[a:a + 3] == [10, 70, 158]


# ── (5) Staerke, Effekt-Helligkeit, Sammlung ─────────────────────────────────


@pytest.mark.parametrize("drive", [False, True])
def test_effekt_helligkeit_skaliert_nur_die_staerke(rig, drive):
    """Regler „Helligkeit" des Modify-Effekts auf 50 % = Staerke 50 % — genau
    einmal (die Matrix skaliert ihre Farben im Modify-Betrieb nicht selbst,
    sonst waeren es 25 %), und das Darunterliegende wird nicht mitgedimmt."""
    unten = _matrix("unten", (100, 150, 200))
    mod = _modify((200, 0, 0), "add", drive_intensity=drive)
    mod.intensity = 0.5
    st = _bild(unten, mod)
    assert _farben(st) == [(200, 150, 200)] * N
    assert _dimmer(st) == [255] * N


def test_farb_modify_in_einer_sammlung(rig):
    unten = _matrix("unten", (100, 150, 200))
    mod = _modify((100, 0, 0), "sub")
    fm = FunctionManager()
    fm.add(unten)
    fm.add(mod)
    col = fm.new_collection("Sammlung")
    col.function_ids = [mod.id]
    col.intensity = 0.5
    fm.start(unten.id)
    fm.start(col.id)
    st = _zustand(fm)
    st._render_frame(DT)
    assert _farben(st) == [(50, 150, 200)] * N         # 100 - 100*0,5


def test_farb_modify_als_chaser_schritt_gibt_nichts_aus(rig):
    """Die Sperre aus ENG-37 gilt unveraendert auch fuer den Stil Farbe."""
    unten = _matrix("unten", (100, 150, 200))
    mod = _modify((255, 255, 255), "add")
    fm = FunctionManager()
    fm.add(unten)
    fm.add(mod)
    ch = fm.new_chaser("Chaser")
    ch.steps = [ChaserStep(function_id=mod.id, hold=5.0)]
    ch.tempo_bus_id = ""
    fm.start(unten.id)
    fm.start(ch.id)
    st = _zustand(fm)
    for _ in range(5):
        st._render_frame(DT)
        assert _farben(st) == [(100, 150, 200)] * N


# ── (6) Mehrere Modify-Effekte, Dimmer und Farbe gemischt ────────────────────


def test_dimmer_und_farb_modify_gleichzeitig(rig):
    """Jeder rechnet auf seinen Kanaelen: der Dimmer-Modify nur am Dimmer, der
    Farb-Modify nur an der Farbe."""
    pegel = _dimmer_matrix("pegel", P40)
    farbe = _matrix("farbe", (100, 150, 200))
    dmod = _dimmer_matrix("dimmer-modify")
    dmod.modify, dmod.modify_mode, dmod.modify_strength = True, "add", 50
    fmod = _modify((255, 0, 100), "sub")
    for folge in ((pegel, farbe, dmod, fmod), (fmod, dmod, farbe, pegel)):
        for f in folge:
            f.stop() if f.is_running else None
        st = _bild(*folge)
        assert _dimmer(st) == [modify_wert("add", P40, 255, 0.5)] * N   # 230
        assert _farben(st) == [(0, 150, 100)] * N


def test_zwei_farb_modify_wirken_in_start_reihenfolge(rig):
    """Rot unten 102: erst Addieren 50 %, dann Abziehen 100 % -> 0; umgekehrt
    gestartet -> 128. Dieselbe Regel wie beim Dimmer (ENG-37)."""
    def rot(reihenfolge):
        unten = _matrix("unten", (P40, 0, 0))
        add = _modify((255, 0, 0), "add", 50)
        sub = _modify((255, 0, 0), "sub", 100)
        paar = (add, sub) if reihenfolge == "add-sub" else (sub, add)
        return _farben(_bild(unten, *paar))[0][0]
    assert rot("add-sub") == 0
    assert rot("sub-add") == 128


def test_layer_prioritaet_ordnet_dimmer_und_farb_modify(rig):
    """Bei gemischten Modify-Effekten gilt weiter: Layer-Prioritaet, darin
    Start-Reihenfolge."""
    unten = _matrix("unten", (P40, 0, 0))
    add = _modify((255, 0, 0), "add", 50)
    sub = _modify((255, 0, 0), "sub", 100)
    sub.priority = -1                         # rechnet trotz spaeterem Start zuerst
    assert _farben(_bild(unten, add, sub))[0][0] == 128


# ── (7) Master und Blackout danach ───────────────────────────────────────────


class _Sender:
    last = None

    def send_dmx(self, data):
        self.last = data

    def close(self):
        pass


def test_grand_master_und_blackout_nach_dem_farb_modify(rig):
    """Reines RGB-Geraet (die Farbe traegt die Helligkeit): Grand Master und
    Blackout greifen NACH dem Farb-Modify — er kann keinen davon aufhellen."""
    from src.core.dmx.output_manager import OutputManager
    om = OutputManager()
    mod = _modify((0, 100, 255), "add", grid=[FID_RGB])
    st = _zustand(_fm(mod), om=om)
    st.programmer = {FID_RGB: {"color_r": 100}}
    sender = _Sender()
    om._enttec_outputs[1] = sender
    a = _ADRESSE[FID_RGB] - 1

    def gesendet():
        st._render_frame(DT)
        om._send_all()
        return list(sender.last[a:a + 3])

    assert gesendet() == [100, 100, 255]
    om.set_grand_master(0.5)
    assert gesendet() == [50, 50, 128]
    om.set_grand_master(1.0)
    om.set_blackout(True)
    for _ in range(10):
        assert gesendet() == [0, 0, 0], "Farb-Modify hat den Blackout aufgehellt"
    om.set_blackout(False)
    assert gesendet() == [100, 100, 255]


def test_submaster_wirkt_nach_dem_farb_modify(rig):
    """Lampe mit Dimmer: der Submaster dimmt den Dimmer, der vom Farb-Modify nie
    angefasst wurde; reines RGB-Geraet: er dimmt die verrechnete Farbe."""
    def bild(sub):
        mod = _modify((0, 100, 255), "add",
                      grid=list(range(1, N + 1)) + [FID_RGB])
        st = _zustand(_fm(mod))
        st.programmer = _snap(intensity=200, color_r=100)
        st.programmer[FID_RGB] = {"color_r": 100}
        st.submaster_level = sub
        st._render_frame(DT)
        return st
    voll, halb = bild(1.0), bild(0.5)
    a = _ADRESSE[FID_RGB] - 1
    assert _dimmer(voll) == [200] * N and _dimmer(halb) == [100] * N
    assert _farben(voll) == [(100, 100, 255)] * N
    assert _roh(voll)[a:a + 3] == [100, 100, 255]
    assert _roh(halb)[a:a + 3] == [int(v * 0.5) for v in (100, 100, 255)]


def test_fixture_fader_zu_bleibt_zu(rig):
    mod = _modify((255, 255, 255), "add")
    st = _zustand(_fm(mod))
    st.programmer = _snap(intensity=200)
    st.fixture_dimmers = {3: 0.0}
    st._render_frame(DT)
    assert _dimmer(st)[2] == 0, "Farb-Modify hat einen zugezogenen Fader aufgehellt"


# ── (8) Ohne Haken exakt wie bisher ──────────────────────────────────────────


@pytest.mark.parametrize("stil", [MatrixStyle.RGB, MatrixStyle.RGBW])
def test_ohne_haken_schreibt_die_farb_matrix_wie_bisher(rig, stil):
    """Festgenagelte Werte des normalen Farb-Effekts (Stand vor ENG-38): der
    Dimmer wird bei „Dimmer mitziehen" geoeffnet, sonst skaliert die Matrix die
    Farben selbst mit der Effekt-Helligkeit. Gemerkte Modify-Art/-Staerke ohne
    Haken aendern daran nichts."""
    def roh(drive, inten, **modify):
        m = _matrix("m", (200, 100, 50), stil=stil, drive_intensity=drive,
                    grid=[1, FID_RGBW, FID_RGB])
        m.intensity = inten
        for k, v in modify.items():
            setattr(m, k, v)
        m.start()
        u = Universe(1)
        m.write({1: u}, rig, DT)
        g = u.get_all()
        return (list(g[0:4]), list(g[40:45]), list(g[50:53]))

    for extra in ({}, {"modify_mode": "sub", "modify_strength": 30}):
        if stil == MatrixStyle.RGBW:
            # Stil RGBW zieht den Weissanteil (50) aus R/G/B — auch dort, wo
            # es keinen W-Kanal gibt (Bestand, hier nur festgehalten).
            assert roh(True, 1.0, **extra) == (
                [255, 150, 50, 0], [255, 150, 50, 0, 50], [150, 50, 0])
            assert roh(False, 0.5, **extra) == (
                [0, 75, 25, 0], [0, 75, 25, 0, 25], [150, 50, 0])
        else:
            assert roh(True, 1.0, **extra) == (
                [255, 200, 100, 50], [255, 200, 100, 50, 0], [200, 100, 50])
            assert roh(False, 0.5, **extra) == (
                [0, 100, 50, 25], [0, 100, 50, 25, 0], [200, 100, 50])


def test_ohne_modify_kein_posten(rig):
    fm = _fm(_matrix("farbe", (1, 2, 3)), _dimmer_matrix("pegel", 9))
    u = Universe(1)
    fm.tick({1: u}, rig, DT, modify_spaeter=True)
    assert fm._modify_posten == []
    assert fm.modify_anwenden({1: u}) is False


def test_stil_shutter_bleibt_gesperrt(rig):
    m = _modify((255, 255, 255), "add", grid=[FID_SHUTTER],
                stil=MatrixStyle.SHUTTER)
    assert m.modify_wirksam() is False and m._farb_modify() is False
    fm = _fm(m)
    u = Universe(1)
    fm.tick({1: u}, rig, DT, modify_spaeter=True)
    assert fm._modify_posten == []
    assert u.get_channel(_ADRESSE[FID_SHUTTER]) == 255      # setzt wie bisher


# ── (9) Speichern / Laden ────────────────────────────────────────────────────


def test_show_ohne_modify_bleibt_byte_gleich():
    fm = FunctionManager()
    for stil in MatrixStyle:
        m = fm.new_rgb_matrix(f"Matrix {stil.value}")
        m.style = stil
        m.fixture_grid = [1, 2, None, 4]
        m.cols, m.rows = 4, 1
    vorher = json.dumps(fm.to_dict(), ensure_ascii=False, indent=1)
    assert "modify" not in vorher
    fm2 = FunctionManager()
    fm2.from_dict(json.loads(vorher))
    assert all(not f.modify_wirksam() for f in fm2.all())
    assert json.dumps(fm2.to_dict(), ensure_ascii=False,
                      indent=1).encode("utf-8") == vorher.encode("utf-8")


@pytest.mark.parametrize("stil", [MatrixStyle.RGB, MatrixStyle.RGBW])
def test_rundlauf_farb_modify(rig, stil):
    """Speichern -> laden -> speichern ist gleich, und die geladene Show
    liefert dasselbe DMX."""
    fm = FunctionManager()
    unten = fm.new_rgb_matrix("unten")
    mod = fm.new_rgb_matrix("Farb-Modify")
    for m, farbe in ((unten, (100, 150, 200)), (mod, (255, 60, 60))):
        m.style = stil
        m.cols, m.rows = N, 1
        m.fixture_grid = list(range(1, N + 1))
        m.algorithm = RgbAlgorithm.PLAIN
        m.color1 = farbe
        m.tempo_bus_id = ""
    unten.style = MatrixStyle.RGB
    mod.modify, mod.modify_mode, mod.modify_strength = True, "dim", 65
    text = json.dumps(fm.to_dict())
    fm2 = FunctionManager()
    fm2.from_dict(json.loads(text))
    assert json.dumps(fm2.to_dict()) == text
    m2 = [f for f in fm2.all() if f.name == "Farb-Modify"][0]
    assert (m2.modify, m2.modify_mode, m2.modify_strength, m2.style) == (
        True, "dim", 65, stil)
    assert m2.modify_wirksam() and m2._farb_modify()

    bilder = []
    for manager in (fm, fm2):
        for f in manager.all():
            manager.start(f.id)
        st = _zustand(manager)
        st._render_frame(DT)
        bilder.append(_roh(st))
    assert bilder[0] == bilder[1]
    assert bilder[0][:4] != [255, 100, 150, 200]            # es wurde verrechnet


def test_entwurf_behaelt_die_kennzeichnung():
    """Editor-Entwurf = from_dict(to_dict())."""
    m = _modify((1, 2, 3), "sub", 40, stil=MatrixStyle.RGBW)
    e = RgbMatrixInstance.from_dict(m.to_dict())
    assert (e.modify, e.modify_mode, e.modify_strength, e.style) == (
        True, "sub", 40, MatrixStyle.RGBW)
    assert e._farb_modify()


# ── (10) Konsole: Regler-Parameter ───────────────────────────────────────────


@pytest.mark.parametrize("stil", [MatrixStyle.RGB, MatrixStyle.RGBW])
def test_konsolen_parameter_auch_im_stil_farbe(stil):
    m = _matrix("m", algo=RgbAlgorithm.CHASE, stil=stil)
    ohne = [s.key for s in m.list_params()]
    assert not [k for k in ohne if k.startswith("modify")]
    m.modify = True
    mit = [s.key for s in m.list_params()]
    assert [k for k in mit if not k.startswith("modify")] == ohne
    assert [k for k in mit if k.startswith("modify")] == [
        "modify_strength", "modify_mode"]
    assert m.set_param("modify_strength", 42) and m.modify_strength == 42
    assert m.set_param("modify_mode", "dim") and m.modify_mode == "dim"


def test_modify_staerke_regler_wirkt_auf_die_farbe(rig):
    unten = _matrix("unten", (100, 0, 0))
    mod = _modify((100, 0, 0), "add")
    st = _zustand(_fm(unten, mod))
    for staerke, soll in ((100, 200), (50, 150), (0, 100)):
        mod.set_param("modify_strength", staerke)
        st._render_frame(DT)
        assert _farben(st)[0][0] == soll
