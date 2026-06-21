"""Render-Harness fuer Farb_FX_VC_Show.lshow — beweist die Kanal-Trennung:
  * Farb-Matrix (Seite 1) schreibt NUR Farbe, NICHT Dimmer/Shutter (Masking).
  * Dimmer-Matrix (Seite 2) schreibt NUR Dimmer, NICHT Farbe.
  * Bewegungs-EFX (Seite 3) schreibt Pan/Tilt, NICHT Farbe.
  * Farbe + Dimmer auf denselben Geraeten ueberlagern sich sauber.

Setzt voraus, dass tools/build_farb_fx_vc_show.py die Show erzeugt hat.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
import pytest

_app = QApplication.instance() or QApplication([])

from src.core.app_state import get_state, get_channels_for_patched
from src.core.dmx.universe import Universe
from src.core.show.show_file import load_show
from src.core.engine.function_manager import get_function_manager

SHOW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "shows", "Farb_FX_VC_Show.lshow")
_DIM_ATTRS = {"intensity", "dimmer", "master"}


@pytest.fixture(scope="module")
def show():
    if not os.path.exists(SHOW):
        pytest.skip("Show fehlt — zuerst tools/build_farb_fx_vc_show.py laufen lassen")
    ok, msg = load_show(SHOW)
    assert ok, msg
    yield get_state(), get_function_manager()
    # Test-Isolation: load_show ersetzt fm/state global -> nach dem Modul leeren,
    # damit nachfolgende Module (z. B. test_matrix_dirty_save) sauber starten.
    from src.core.show.show_file import reset_show
    reset_show()


def _fx(state, fid):
    return next(f for f in state.get_patched_fixtures() if f.fid == fid)


def _addr(state, fid, attr):
    fx = _fx(state, fid)
    ch = {c.attribute: c.channel_number for c in get_channels_for_patched(fx)}
    return fx.address + ch[attr] - 1


def _dim_addr(state, fid):
    fx = _fx(state, fid)
    for c in get_channels_for_patched(fx):
        if (c.attribute or "").lower() in _DIM_ATTRS:
            return fx.address + c.channel_number - 1
    raise AssertionError(f"kein Dimmer-Kanal an fid {fid}")


def _fn(fm, name):
    return next(f for f in fm.all() if f.name == name)


def _render(fn, fxs, into=None):
    u = into or Universe(1)
    fn.start()
    fn.write({1: u}, fxs, 0.0)
    return u


def test_par_color_matrix_drives_only_color(show):
    state, fm = show
    fxs = state.get_patched_fixtures()
    u = _render(_fn(fm, "PAR Solid"), fxs)
    assert u.get_channel(_addr(state, 1, "color_r")) > 0, "PAR Solid faerbt nicht rot"
    assert u.get_channel(_dim_addr(state, 1)) == 0, "Farb-Matrix treibt den Dimmer (kein Masking!)"


def test_par_dimmer_matrix_drives_only_intensity(show):
    state, fm = show
    fxs = state.get_patched_fixtures()
    u = _render(_fn(fm, "PAR Dim-Blink"), fxs)
    assert u.get_channel(_dim_addr(state, 1)) > 0, "Dimmer-Matrix treibt den Dimmer nicht"
    assert u.get_channel(_addr(state, 1, "color_r")) == 0, "Dimmer-Matrix faerbt (sollte nicht)"


def test_mh_efx_drives_pan_tilt_not_color(show):
    state, fm = show
    fxs = state.get_patched_fixtures()
    u = _render(_fn(fm, "MH Kreis"), fxs)
    # Pan/Tilt werden geschrieben (Bewegung)
    pan = u.get_channel(_addr(state, 9, "pan"))
    tilt = u.get_channel(_addr(state, 9, "tilt"))
    assert pan > 0 or tilt > 0, "EFX bewegt den MH nicht"
    # Farbrad bleibt unangetastet (EFX schreibt keine Farbe)
    assert u.get_channel(_addr(state, 9, "color_wheel")) == 0, "EFX schreibt Farbe (sollte nicht)"


def test_color_and_dimmer_layer_cleanly(show):
    state, fm = show
    fxs = state.get_patched_fixtures()
    u = Universe(1)
    _render(_fn(fm, "PAR Solid"), fxs, into=u)        # Farbe
    _render(_fn(fm, "PAR Dim-Blink"), fxs, into=u)    # Dimmer drueber
    assert u.get_channel(_addr(state, 1, "color_r")) > 0, "Farbe verloren"
    assert u.get_channel(_dim_addr(state, 1)) > 0, "Dimmer verloren"


def test_checker_alternates_across_pars(show):
    state, fm = show
    fxs = state.get_patched_fixtures()
    u = _render(_fn(fm, "PAR Wechsel"), fxs)
    # Schachbrett rot/blau: PAR1 rot, PAR2 blau (benachbart unterschiedlich)
    r1 = u.get_channel(_addr(state, 1, "color_r"))
    b1 = u.get_channel(_addr(state, 1, "color_b"))
    r2 = u.get_channel(_addr(state, 2, "color_r"))
    b2 = u.get_channel(_addr(state, 2, "color_b"))
    assert (r1, b1) != (r2, b2), "Schachbrett: benachbarte PARs gleich gefaerbt"
