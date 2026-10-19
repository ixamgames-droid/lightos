"""ENG-35 Schritt 4: „wer gewinnt“ live — der Kern (ohne Qt).

1. Das Protokoll „Adresse -> letzter Schreiber“ laeuft nur, solange es
   angefordert ist (Zaehler); aus = der Takt beruehrt es nicht.
2. Schneller Pfad UND priv-Pfad (Helligkeit < 1) protokollieren.
3. Das Schreib-Protokoll des Renderers bleibt unveraendert (Teil-Protokoll).
4. Auswertung je Geraet: gewinnt auf n / verdeckt auf m von X.
5. Im Renderer: Cueliste, Programmer und Snap liegen darueber; Modify-Effekte
   gelten nicht als Verdecker.
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
from src.core.engine import wer_gewinnt                     # noqa: E402
from src.core.engine.function_manager import FunctionManager  # noqa: E402
from src.core.engine.rgb_matrix import (                    # noqa: E402
    MatrixStyle, RgbAlgorithm, RgbMatrixInstance)

N = 8
DT = 0.02


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
    fixture_type = ""

    def __init__(self, fid, address, universe=1):
        self.fid = fid
        self.universe = universe
        self.address = address


def _adr(i):
    """Dimmer-Adresse der Lampe ``i`` (0..7): Dimmer, R, G, B ab 1, 5, 9 …"""
    return 1 + 4 * i


def _patch():
    return [_Fx(fid, _adr(fid - 1)) for fid in range(1, N + 1)]


_KANAELE = {fid: [_Ch("intensity", 1), _Ch("color_r", 2),
                  _Ch("color_g", 3), _Ch("color_b", 4)]
            for fid in range(1, N + 1)}


class _Schreiber:
    """Minimal-Funktion: schreibt ``wert`` auf die Dimmer der Lampen."""

    def __init__(self, fid, lampen, wert=200, priority=0, name=None,
                 intensity=1.0):
        self.id = fid
        self.name = name or f"F{fid}"
        self.lampen = list(lampen)
        self.wert = wert
        self.priority = priority
        self.is_running = True
        self.intensity = intensity

    def start(self):
        self.is_running = True

    def stop(self):
        self.is_running = False

    def write(self, universes, patch_cache, dt, registry):
        for i in self.lampen:
            universes[1].set_channel(_adr(i), self.wert)


def _fm(*funktionen):
    fm = FunctionManager()
    for f in funktionen:
        fm._functions[f.id] = f
    for f in funktionen:
        fm.start(f.id)
    return fm


# ── (1) nur wenn angefordert ─────────────────────────────────────────────────


class _SpionUniverse(Universe):
    teil = 0

    def teil_log_beginnen(self):
        type(self).teil += 1
        return super().teil_log_beginnen()


def test_aus_beruehrt_der_takt_das_protokoll_nicht():
    _SpionUniverse.teil = 0
    fm = _fm(_Schreiber(1, range(4)), _Schreiber(2, range(2, 4)))
    assert fm.wer_gewinnt_aktiv is False
    fm.tick({1: _SpionUniverse(1)}, _patch(), DT)
    assert _SpionUniverse.teil == 0, "aus: kein Teil-Protokoll im Takt"
    assert fm._wg_protokoll is None
    assert fm.wer_gewinnt(_patch()) == {}


def test_zaehler_mehrere_anzeigen_und_freigeben_schaltet_ab():
    fm = _fm(_Schreiber(1, range(4)))
    fm.wer_gewinnt_anfordern()
    fm.wer_gewinnt_anfordern()
    fm.wer_gewinnt_freigeben()
    assert fm.wer_gewinnt_aktiv, "eine Anzeige will es noch"
    fm.tick({1: Universe(1)}, _patch(), DT)
    assert fm.wer_gewinnt(_patch())
    fm.wer_gewinnt_freigeben()
    assert not fm.wer_gewinnt_aktiv
    assert fm._wg_protokoll is None and fm.wer_gewinnt(_patch()) == {}
    fm.wer_gewinnt_freigeben()                   # zu oft: bleibt bei 0
    assert fm._wg_zaehler == 0
    _SpionUniverse.teil = 0
    fm.tick({1: _SpionUniverse(1)}, _patch(), DT)
    assert _SpionUniverse.teil == 0


# ── (2)+(4) schneller Pfad, priv-Pfad, Auswertung ────────────────────────────


def test_hoehere_stufe_verdeckt_auf_ihren_geraeten():
    unten = _Schreiber(1, range(4), priority=0, name="Grundlicht")
    oben = _Schreiber(2, (2, 3), priority=20, name="Akzent")
    fm = _fm(oben, unten)                         # Start-Reihenfolge egal
    fm.wer_gewinnt_anfordern()
    fm.tick({1: Universe(1)}, _patch(), DT)
    erg = fm.wer_gewinnt(_patch())
    assert (erg[1].gewinnt, erg[1].verdeckt) == (2, 2)
    assert erg[1].von == [("Akzent", 2)]
    assert erg[1].text() == "verdeckt von Akzent auf 2 Geräten"
    assert (erg[2].gewinnt, erg[2].verdeckt) == (2, 0)
    assert erg[2].text() == ""
    assert "gewinnt auf 2 Geräten" in erg[2].tooltip()


def test_priv_pfad_mit_halber_helligkeit_protokolliert_auch():
    unten = _Schreiber(1, range(4), priority=0, name="Grundlicht")
    oben = _Schreiber(2, (3,), priority=20, name="Halb", intensity=0.5)
    fm = _fm(unten, oben)
    fm.wer_gewinnt_anfordern()
    fm.tick({1: Universe(1)}, _patch(), DT)
    erg = fm.wer_gewinnt(_patch())
    assert erg[1].text() == "verdeckt von Halb auf 1 Gerät"
    assert erg[2].gewinnt == 1


def test_verdecker_nach_anzahl_sortiert_und_gekuerzt():
    e = wer_gewinnt.Ergebnis(gewinnt=0, verdeckt=6,
                             von=[("A", 3), ("B", 2), ("C", 1)])
    assert e.text() == "verdeckt von A auf 3 Geräten, B auf 2 Geräten (+1 weitere)"


def test_unverdeckt_und_ungepatcht_bleibt_leer():
    p = wer_gewinnt.SchreibProtokoll()
    p.eintragen(7, 1, {400, 401})                # keine Lampe dort
    assert wer_gewinnt.auswerten(p, None, _patch(), lambda f: "x") == {}
    assert wer_gewinnt.auswerten(None, None, _patch(), lambda f: "x") == {}


# ── (3) das Protokoll des Renderers bleibt gleich ────────────────────────────


@pytest.mark.parametrize("an", [False, True])
def test_aeusseres_schreib_protokoll_unveraendert(an):
    fm = _fm(_Schreiber(1, (0, 1)), _Schreiber(2, (5,), intensity=0.5))
    if an:
        fm.wer_gewinnt_anfordern()
    u = Universe(1)
    u.begin_write_log()
    fm.tick({1: u}, _patch(), DT)
    assert u.end_write_log() == {_adr(0), _adr(1), _adr(5)}


# ── (5) im Renderer ──────────────────────────────────────────────────────────


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(A, "get_channels_for_patched",
                        lambda fx: _KANAELE[fx.fid])
    return _patch()


def _zustand(fm, programmer=None, playback=None):
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.output_manager = types.SimpleNamespace(set_gm_address_mask=lambda m: None)
    st.programmer = programmer or {}
    st.playback_engine = playback
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


def _matrix(name, algo=RgbAlgorithm.PLAIN, **felder):
    m = RgbMatrixInstance(name, cols=N, rows=1, fixture_grid=list(range(1, N + 1)),
                          algorithm=algo, color1=(255, 255, 255))
    m.style = MatrixStyle.DIMMER
    m.tempo_bus_id = ""
    m.matrix_speed = 1.0
    for k, v in felder.items():
        setattr(m, k, v)
    return m


def _echter_fm(*funktionen):
    fm = FunctionManager()
    for f in funktionen:
        fm.add(f)
    for f in funktionen:
        fm.start(f.id)
    return fm


def test_renderer_programmer_und_snap_liegen_darueber(rig):
    unten = _matrix("Pegel", intensity_min=100, intensity_max=100)
    fm = _echter_fm(unten)
    st = _zustand(fm, programmer={1: {"intensity": 255}, 2: {"intensity": 222}})
    st.programmer_focus = "Intensity"
    st.selected_fids = [1]                       # Lampe 1: manuell dimmen
    st.snap_dimmer_override = {2: {"intensity": 222}}   # Lampe 2: Snap-Taste
    fm.wer_gewinnt_anfordern()
    st._render_frame(DT)
    erg = fm.wer_gewinnt(st._patch_cache)[unten.id]
    assert erg.verdeckt == 2 and erg.gewinnt == N - 2
    assert sorted(erg.von) == [("Programmer", 1), ("Snap", 1)]


class _Playback:
    def __init__(self, merged):
        self._m = merged

    def compute_merged(self):
        return self._m


def test_renderer_cueliste_liegt_darueber(rig):
    unten = _matrix("Pegel", intensity_min=100, intensity_max=100)
    fm = _echter_fm(unten)
    st = _zustand(fm, playback=_Playback({3: {"intensity": 10},
                                          4: {"intensity": 10}}))
    fm.wer_gewinnt_anfordern()
    st._render_frame(DT)
    erg = fm.wer_gewinnt(st._patch_cache)[unten.id]
    assert erg.text() == "verdeckt von Cueliste auf 2 Geräten"


def test_renderer_modify_ist_kein_verdecker(rig):
    unten = _matrix("Pegel", intensity_min=100, intensity_max=100)
    lauf = _matrix("Lauf", RgbAlgorithm.CHASE)
    lauf.params.update({"runner_count": 2, "after_fade": 0.0})
    lauf.modify, lauf.modify_mode, lauf.modify_strength = True, "add", 100
    lauf.priority = 60
    fm = _echter_fm(unten, lauf)
    st = _zustand(fm)
    fm.wer_gewinnt_anfordern()
    for _ in range(3):
        st._render_frame(DT)
    erg = fm.wer_gewinnt(st._patch_cache)
    assert erg[unten.id].verdeckt == 0 and erg[unten.id].gewinnt == N
    assert lauf.id not in erg, "Modify schreibt im Durchlauf nichts"
    assert max(st.universes[1].get_all()[_adr(i) - 1] for i in range(N)) > 100, \
        "der Modify-Laeufer wirkt trotzdem"


def test_renderer_aus_meldet_keine_schicht_darueber(rig):
    unten = _matrix("Pegel", intensity_min=100, intensity_max=100)
    fm = _echter_fm(unten)
    st = _zustand(fm, programmer={1: {"intensity": 255}},
                  playback=_Playback({3: {"intensity": 10}}))
    st.programmer_focus = "Intensity"
    st.selected_fids = [1]
    st._render_frame(DT)
    assert fm._wg_oben is None and fm._wg_protokoll is None
    assert fm.wer_gewinnt(st._patch_cache) == {}
