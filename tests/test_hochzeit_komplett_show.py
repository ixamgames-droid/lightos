"""Coverage- + Render-Gate fuer Hochzeit_Komplett_2026.lshow.

Beweist (im CI), dass die Komplett-Demo wirklich ALLES enthaelt und auf dem
14-Fixture-Hochzeits-Rig echtes, sauber maskiertes DMX erzeugt:
  * 14 Fixtures / 137 Kanaele
  * alle 18 RGB-Matrix-Algorithmen + alle 4 Styles (RGB/RGBW/Dimmer/Shutter)
  * alle 10 EFX-Bewegungsfiguren
  * alle 19 VC-Widget-Typen aus dem WIDGET_REGISTRY
  * Render: RGB faerbt ohne Dimmer, RGBW nutzt den W-Chip, Dimmer maskiert Farbe,
    EFX bewegt MH+Spider, Spider-Doppelbank, Shutter-Style.

Setzt voraus, dass tools/build_hochzeit_komplett.py die Show erzeugt hat.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
import pytest

_app = QApplication.instance() or QApplication([])

from src.core.app_state import get_state, get_channels_for_patched
from src.core.dmx.universe import Universe
from src.core.show.show_file import load_show, reset_show
from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, MatrixStyle
from src.core.engine.efx import EfxInstance, EfxAlgorithm
from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY

SHOW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "shows", "Hochzeit_Komplett_2026.lshow")


@pytest.fixture(scope="module")
def show():
    if not os.path.exists(SHOW):
        pytest.skip("Show fehlt — zuerst tools/build_hochzeit_komplett.py laufen lassen")
    ok, msg = load_show(SHOW)
    assert ok, msg
    yield get_state(), get_function_manager()
    reset_show()


def _fx(state, fid):
    return next(f for f in state.get_patched_fixtures() if f.fid == fid)


def _addr(state, fid, attr, occ=0):
    cs = [c for c in get_channels_for_patched(_fx(state, fid))
          if (c.attribute or "").lower() == attr]
    return _fx(state, fid).address + cs[occ].channel_number - 1


def _fn(fm, name):
    return next(f for f in fm.all() if f.name == name)


def _peak(fm, state, name, attrs, frames=40):
    """Maximalwert je (fid, attr, occ) ueber mehrere gerenderte Frames."""
    fn = _fn(fm, name)
    fn.start()
    fxs = state.get_patched_fixtures()
    peak = {k: 0 for k in attrs}
    for _ in range(frames):
        u = Universe(1)
        fn.write({1: u}, fxs, 0.06)
        for k, (fid, attr, occ) in attrs.items():
            peak[k] = max(peak[k], u.get_channel(_addr(state, fid, attr, occ)))
    fn.stop()
    return peak


# ── Struktur / Vollstaendigkeit ─────────────────────────────────────────────────
def test_rig_dichte(show):
    state, _ = show
    fx = state.get_patched_fixtures()
    assert len(fx) == 14
    assert sum(f.channel_count for f in fx) == 137


def test_alle_18_matrix_algorithmen(show):
    _, fm = show
    algos = {m.algorithm for m in fm.all() if isinstance(m, RgbMatrixInstance)}
    assert set(RgbAlgorithm).issubset(algos), \
        [a.name for a in set(RgbAlgorithm) - algos]


def test_alle_4_matrix_styles(show):
    _, fm = show
    styles = {m.style for m in fm.all() if isinstance(m, RgbMatrixInstance)}
    assert set(MatrixStyle).issubset(styles), [s.name for s in set(MatrixStyle) - styles]


def test_alle_10_efx_figuren(show):
    _, fm = show
    figs = {e.algorithm for e in fm.all() if isinstance(e, EfxInstance)}
    assert set(EfxAlgorithm).issubset(figs), [a.name for a in set(EfxAlgorithm) - figs]


def test_alle_19_widget_typen(show):
    state, _ = show
    present = {w["type"] for w in state._vc_layout.get("widgets", [])}
    assert set(WIDGET_REGISTRY).issubset(present), \
        sorted(set(WIDGET_REGISTRY) - present)


# ── Render / echtes DMX auf dem heterogenen Rig ─────────────────────────────────
def test_rgb_faerbt_ohne_dimmer(show):
    state, fm = show
    p = _peak(fm, state, "01 Plain (Vollflaeche)", {
        "zq_r": (6, "color_r", 0), "zq_dim": (6, "intensity", 0),
        "dotz_c1": (1, "color_r", 0), "dotz_c4": (1, "color_r", 3)})
    assert p["zq_r"] > 0 and p["dotz_c1"] > 0 and p["dotz_c4"] > 0, "RGB faerbt nicht (auch Dotz-Zellen)"
    assert p["zq_dim"] == 0, "RGB-Style treibt den Dimmer (Masking kaputt)"


def test_rgbw_nutzt_weiss_chip(show):
    state, fm = show
    p = _peak(fm, state, "RGBW Reines Weiss", {
        "flat_w": (2, "color_w", 0), "flat_r": (2, "color_r", 0)})
    assert p["flat_w"] > 0, "RGBW-Style nutzt den Weiss-Chip nicht"
    assert p["flat_r"] == 0, "RGBW reines Weiss schreibt Rot (rgbw_split kaputt)"


def test_dimmer_maskiert_farbe(show):
    state, fm = show
    p = _peak(fm, state, "Dim Welle", {
        "zq_dim": (6, "intensity", 0), "zq_r": (6, "color_r", 0)})
    assert p["zq_dim"] > 0, "Dimmer-Matrix treibt den Dimmer nicht"
    assert p["zq_r"] == 0, "Dimmer-Style faerbt (sollte nicht)"


def test_efx_bewegt_mh_und_spider(show):
    state, fm = show
    p = _peak(fm, state, "Kreis", {
        "mh_pan": (12, "pan", 0), "mh_tilt": (12, "tilt", 0),
        "sp_tilt": (13, "tilt", 0), "mh_col": (12, "color_wheel", 0)})
    assert p["mh_pan"] > 0 or p["mh_tilt"] > 0, "EFX bewegt den MH nicht"
    assert p["sp_tilt"] > 0, "EFX bewegt die Spider nicht"
    assert p["mh_col"] == 0, "EFX schreibt Farbe (sollte nicht)"


def test_spider_doppelbank_getrennt(show):
    state, fm = show
    p = _peak(fm, state, "Spider Rot/Blau", {
        "bank1_r": (13, "color_r", 0), "bank2_b": (13, "color_b", 1)}, frames=2)
    assert p["bank1_r"] == 255 and p["bank2_b"] == 255, "Spider-Doppelbank nicht getrennt"


def test_shutter_style_treibt_shutter(show):
    state, fm = show
    p = _peak(fm, state, "Shutter Strobe", {
        "zq_shutter": (6, "shutter", 0), "zq_r": (6, "color_r", 0)})
    assert p["zq_shutter"] > 0, "Shutter-Style treibt den Shutter nicht"
    assert p["zq_r"] == 0, "Shutter-Style faerbt (sollte nicht)"
