"""Coverage- + Render-Gate für Hochzeit_Komplett_2026.lshow.

Beweist (im CI), dass die Komplett-Demo Davids Kompositions-Modell umsetzt:
  * 14 Fixtures / 137 Kanäle, alle 18 RgbAlgorithm, alle 4 MatrixStyle, alle 10 EFX, alle 19 Widgets.
  * FARBE = nur Farbe (RGB-Matrix treibt den Dimmer NICHT), DIMMER = Bewegung (treibt nur den Dimmer).
  * Komposition: feste grüne Farbe + Dimmer-Lauflicht = grünes Lauflicht (Farbe konstant, Dimmer läuft).
  * PRO GRUPPE getrennt: Paarlichter rot + Spider blau gleichzeitig (eigene edit_slots).
  * RGBW nutzt den Weiß-Chip; Spider-Doppelbank getrennt; Shutter-Style treibt den Shutter.

Bus-gekoppelte Effekte (Farbe ×1 / Dimmer ×2 an Bus A) animieren nur, wenn der Bus getaktet wird —
im CI über manuelles ``bus.advance_frame`` (in der App treibt der Render-Thread den Bus).

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
from src.core.engine.tempo_bus import get_tempo_bus_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, MatrixStyle
from src.core.engine.efx import EfxInstance, EfxAlgorithm
from src.core.engine import effect_live
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


def _tick_buses(dt=0.06):
    for b in get_tempo_bus_manager().named_buses():
        try:
            b.advance_frame(dt)
        except Exception:
            pass


def _peak(fm, state, name, attrs, frames=50):
    """Maximalwert je (fid, attr, occ) über mehrere gerenderte Frames (mit Bus-Takt)."""
    fn = _fn(fm, name)
    fn.start()
    fxs = state.get_patched_fixtures()
    peak = {k: 0 for k in attrs}
    for _ in range(frames):
        _tick_buses()
        u = Universe(1)
        fn.write({1: u}, fxs, 0.06)
        for k, (fid, attr, occ) in attrs.items():
            peak[k] = max(peak[k], u.get_channel(_addr(state, fid, attr, occ)))
    fn.stop()
    return peak


# ── Struktur / Vollständigkeit ──────────────────────────────────────────────────
def test_rig_dichte(show):
    state, _ = show
    fx = state.get_patched_fixtures()
    assert len(fx) == 14
    assert sum(f.channel_count for f in fx) == 137


def test_alle_18_matrix_algorithmen(show):
    _, fm = show
    algos = {m.algorithm for m in fm.all() if isinstance(m, RgbMatrixInstance)}
    assert set(RgbAlgorithm).issubset(algos), [a.name for a in set(RgbAlgorithm) - algos]


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
    assert set(WIDGET_REGISTRY).issubset(present), sorted(set(WIDGET_REGISTRY) - present)


def test_pro_gruppe_eigene_slots(show):
    """Farbe + Dimmer je Gruppe in eigener Radio-Gruppe → koexistieren, killen sich nicht."""
    state, _ = show
    slots = {w.get("edit_slot", "") for w in state._vc_layout.get("widgets", [])
             if w["type"] == "VCButton"}
    for need in ("farbe_front", "farbe_spider", "farbe_mh", "dim_front", "dim_spider", "dim_mh"):
        assert need in slots, f"edit_slot '{need}' fehlt"


def test_tempo_kopplung_farbe1_dimmer2(show):
    """Farbe ×1, Dimmer ×2 — selber Takt, doppeltes Tempo, gemeinsame sync_group."""
    _, fm = show
    color = _fn(fm, "Feste Farbe")
    dim = _fn(fm, "Lauflicht")
    assert color.sync_group == dim.sync_group != "", "keine gemeinsame sync_group"
    assert abs(color.tempo_multiplier - 1.0) < 1e-6
    assert abs(dim.tempo_multiplier - 2.0) < 1e-6


# ── Render: Farbe/Dimmer-Trennung + Komposition ─────────────────────────────────
def test_rgb_faerbt_ohne_dimmer(show):
    state, fm = show
    p = _peak(fm, state, "Feste Farbe", {
        "zq_r": (6, "color_r", 0), "zq_dim": (6, "intensity", 0),
        "dotz_c1": (1, "color_r", 0), "dotz_c4": (1, "color_r", 3)})
    assert p["zq_r"] > 0 and p["dotz_c1"] > 0 and p["dotz_c4"] > 0, "RGB färbt nicht (auch Dotz-Zellen)"
    assert p["zq_dim"] == 0, "RGB-Style treibt den Dimmer (Trennung kaputt)"


def test_rgbw_nutzt_weiss_chip(show):
    state, fm = show
    p = _peak(fm, state, "Reines Weiß (RGBW)", {
        "flat_w": (2, "color_w", 0), "flat_r": (2, "color_r", 0)})
    assert p["flat_w"] > 0, "RGBW-Style nutzt den Weiß-Chip nicht"
    assert p["flat_r"] == 0, "RGBW reines Weiß schreibt Rot (rgbw_split kaputt)"


def test_dimmer_maskiert_farbe(show):
    state, fm = show
    p = _peak(fm, state, "Welle", {
        "zq_dim": (6, "intensity", 0), "zq_r": (6, "color_r", 0)})
    assert p["zq_dim"] > 0, "Dimmer-Matrix treibt den Dimmer nicht (Bus getaktet?)"
    assert p["zq_r"] == 0, "Dimmer-Style färbt (sollte nicht)"


def test_gruenes_lauflicht_komposition(show):
    """Kern-Modell: feste grüne Farbe (Farb-Schicht) + Dimmer-Lauflicht (Bewegung) = grünes Lauflicht."""
    state, fm = show
    color = _fn(fm, "Feste Farbe")
    dim = _fn(fm, "Lauflicht")
    fm.start(color.id)
    effect_live.set_selected_color((0, 255, 0))   # Farbe grün auf den aktiven Effekt
    fm.start(dim.id)
    fxs = state.get_patched_fixtures()
    greens, intens = set(), []
    for _ in range(60):
        _tick_buses()
        u = Universe(1)
        color.write({1: u}, fxs, 0.06)   # Farb-Schicht
        dim.write({1: u}, fxs, 0.06)     # Dimmer-Schicht drüber
        greens.add(u.get_channel(_addr(state, 6, "color_g")))
        intens.append(u.get_channel(_addr(state, 6, "intensity")))
    fm.stop_all()
    assert max(greens) > 0, "keine grüne Farbe"
    assert min(intens) == 0 and max(intens) > 0, "Dimmer läuft nicht (kein Lauflicht über den Dimmer)"


def test_pro_gruppe_getrennte_farben(show):
    """Paarlichter ROT + Spider BLAU gleichzeitig — eigene Farb-Effekte je Gruppe."""
    state, fm = show
    fm.stop_all()
    fm.start(_fn(fm, "Feste Farbe").id)
    effect_live.set_selected_color((255, 0, 0))         # Paarlichter rot
    fm.start(_fn(fm, "Spider Feste Farbe").id)
    effect_live.set_selected_color((0, 0, 255))         # Spider blau
    fxs = state.get_patched_fixtures()
    pr = {"par_r": 0, "par_b": 0, "sp_r": 0, "sp_b": 0}
    for _ in range(20):
        _tick_buses()
        u = Universe(1)
        for f in fm.all():
            if getattr(f, "is_running", False):
                try:
                    f.write({1: u}, fxs, 0.06)
                except Exception:
                    pass
        pr["par_r"] = max(pr["par_r"], u.get_channel(_addr(state, 6, "color_r")))
        pr["par_b"] = max(pr["par_b"], u.get_channel(_addr(state, 6, "color_b")))
        pr["sp_r"] = max(pr["sp_r"], u.get_channel(_addr(state, 13, "color_r")))
        pr["sp_b"] = max(pr["sp_b"], u.get_channel(_addr(state, 13, "color_b")))
    fm.stop_all()
    assert pr["par_r"] > 0 and pr["par_b"] == 0, "Paarlichter nicht rot (Gruppen-Trennung)"
    assert pr["sp_b"] > 0 and pr["sp_r"] == 0, "Spider nicht blau (Gruppen-Trennung)"


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
        "bank1_r": (13, "color_r", 0), "bank2_b": (13, "color_b", 1)}, frames=4)
    assert p["bank1_r"] == 255 and p["bank2_b"] == 255, "Spider-Doppelbank nicht getrennt"


def test_shutter_style_treibt_shutter(show):
    state, fm = show
    p = _peak(fm, state, "Strobe (Shutter)", {
        "zq_shutter": (6, "shutter", 0), "zq_r": (6, "color_r", 0)})
    assert p["zq_shutter"] > 0, "Shutter-Style treibt den Shutter nicht"
    assert p["zq_r"] == 0, "Shutter-Style färbt (sollte nicht)"
