"""CDX-67: die gemischte Modify-Vorschau (ENG-37) zeigt Amber und UV.

Codex-Befund zu #1247: ``RgbMatrixInstance.zellen_ablesen`` las fuer die
Anzeigefarbe nur Rot/Gruen/Blau/Weiss. Eine RGBA-Lampe, an der der Farb-Modify
nur Amber faehrt (DMX ``[0, 0, 0, 255]``), kam als ``(0, 0, 0)`` heraus — die
Vorschau malte die aktive Lampe schwarz. UV ebenso.

★ Keine neue Umrechnung: die Anzeigefarbe kommt aus ``color_utils.visual_rgb``,
  derselben Regel, mit der 3D und 2D-Plan Amber/UV einfaerben.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                               # noqa: E402

import src.core.app_state as A                              # noqa: E402
from src.core.color_utils import visual_rgb                 # noqa: E402
from src.core.dmx.universe import Universe                  # noqa: E402
from src.core.engine.rgb_matrix import (                    # noqa: E402
    MatrixStyle, RgbAlgorithm, RgbMatrixInstance)


class _Ch:
    def __init__(self, attribute, channel_number, default=0):
        self.attribute = attribute
        self.channel_number = channel_number
        self.default_value = default
        self.ranges = []


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    protocol = ""
    fixture_name = ""
    fixture_type = ""

    def __init__(self, fid, address, channel_count, universe=1):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.channel_count = channel_count


_RGBA = [_Ch("color_r", 1), _Ch("color_g", 2), _Ch("color_b", 3),
         _Ch("color_a", 4)]
_RGBUV = [_Ch("color_r", 1), _Ch("color_g", 2), _Ch("color_b", 3),
          _Ch("color_uv", 4)]
_RGBW = [_Ch("color_r", 1), _Ch("color_g", 2), _Ch("color_b", 3),
         _Ch("color_w", 4)]


def _ablesen(monkeypatch, kanaele, werte, style=MatrixStyle.RGB):
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: kanaele)
    m = RgbMatrixInstance("m", cols=1, rows=1, fixture_grid=[1],
                          algorithm=RgbAlgorithm.PLAIN)
    m.style = style
    uni = Universe(1)
    uni.set_range(1, bytes(werte))
    return m.zellen_ablesen({1: uni}, [_Fx(1, 1, len(kanaele))])[0]


def test_nur_amber_ist_nicht_schwarz_sondern_amber(monkeypatch):
    farbe = _ablesen(monkeypatch, _RGBA, [0, 0, 0, 255])
    assert farbe is not None and farbe != (0, 0, 0)
    assert farbe == visual_rgb({"color_a": 255})
    r, g, b = farbe
    assert r > g > b            # warmes Bernstein


def test_nur_uv_ist_violett(monkeypatch):
    farbe = _ablesen(monkeypatch, _RGBUV, [0, 0, 0, 255])
    assert farbe is not None and farbe != (0, 0, 0)
    assert farbe == visual_rgb({"color_uv": 255})
    r, g, b = farbe
    assert b > g and r > g      # Violett: Blau + etwas Rot, kaum Gruen


def test_amber_wird_zur_rgb_mischung_addiert(monkeypatch):
    farbe = _ablesen(monkeypatch, _RGBA, [0, 0, 200, 128])
    assert farbe == visual_rgb({"color_r": 0, "color_g": 0, "color_b": 200,
                                "color_a": 128})
    assert farbe[0] > 0 and farbe[2] >= 200


def test_rgbw_bleibt_wie_bisher(monkeypatch):
    # Weiss kommt weiter auf alle drei (geklemmt) — byte-gleich zum Stand ENG-37.
    farbe = _ablesen(monkeypatch, _RGBW, [100, 0, 200, 100],
                     style=MatrixStyle.RGBW)
    assert farbe == (200, 100, 255)


@pytest.mark.parametrize("kanaele", [_RGBA, _RGBUV])
def test_dunkle_lampe_bleibt_schwarz(monkeypatch, kanaele):
    assert _ablesen(monkeypatch, kanaele, [0, 0, 0, 0]) == (0, 0, 0)


# ── Ende-zu-Ende: Renderer -> Grundbild -> gemischte Vorschau ────────────────
#
# Der echte Weg aus dem Befund: ein Farb-Modify mit „Wirkt auf“ nur Amber bzw.
# nur UV laeuft ueber einem dunklen Untergrund. Die gemischte Vorschau muss die
# Zellen zeigen, die am Ausgang leuchten — nicht schwarz.

def _zustand(*funktionen):
    import threading
    import types
    from src.core.app_state import AppState
    from src.core.engine.function_manager import FunctionManager
    fm = FunctionManager()
    for f in funktionen:
        fm.add(f)
        fm.start(f.id)
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.output_manager = types.SimpleNamespace(
        set_gm_address_mask=lambda m: None)
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = fm
    st._patch_cache = [_Fx(fid, 1 + 4 * (fid - 1), 4) for fid in (1, 2, 3)]
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


@pytest.mark.parametrize("kanaele, kanal, attr", [
    (_RGBA, "a", "color_a"), (_RGBUV, "uv", "color_uv")])
def test_ende_zu_ende_vorschau_zeigt_was_am_ausgang_leuchtet(
        monkeypatch, kanaele, kanal, attr):
    from PySide6.QtWidgets import QApplication
    from src.ui.views.rgb_matrix_view import MatrixPreview
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: kanaele)

    def _m(name):
        m = RgbMatrixInstance(name, cols=3, rows=1, fixture_grid=[1, 2, 3],
                              algorithm=RgbAlgorithm.PLAIN,
                              color1=(255, 255, 255))
        m.style = MatrixStyle.RGB
        m.tempo_bus_id = ""
        m.matrix_speed = 1.0
        return m

    unten = _m("unten")
    unten.color1 = (0, 0, 0)
    mod = _m("modify")
    mod.modify, mod.modify_mode, mod.modify_strength = True, "add", 100
    mod.modify_channels = (kanal,)
    st = _zustand(unten, mod)
    st.grundbild_anfordern()
    st._render_frame(0.02)
    roh = st.universes[1].get_all()
    ausgang = [dict(zip(("color_r", "color_g", "color_b", attr),
                        roh[4 * i:4 * i + 4])) for i in range(3)]
    assert any(w[attr] > 0 for w in ausgang), "Modify faehrt den Kanal nicht"
    v = MatrixPreview()
    v._timer.stop()
    v.set_matrix(mod)
    v._grundbild_quelle = lambda: ((st.grundbild(), st._patch_cache)
                                   if st.grundbild() else None)
    try:
        zellen = v.gemischte_zellen()
        assert zellen is not None, "keine gemischte Vorschau"
        assert zellen == [visual_rgb(w) for w in ausgang]
        for w, z in zip(ausgang, zellen):
            if w[attr] > 0:
                assert z != (0, 0, 0)
    finally:
        v.deleteLater()
