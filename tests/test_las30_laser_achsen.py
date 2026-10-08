"""LAS-30: Laser-Achsen je gepatchtem Geraet umkehren/tauschen.

Gegenstueck zu invert_pan/invert_tilt/swap_pan_tilt fuer ``laser_x``/
``laser_y`` (Flags ``invert_laser_x``/``invert_laser_y``/``swap_laser_xy``).
Geprueft werden die Achsen-Konvention (Umkehr ist bei Mitte-/Zwei-Richtungs-
Achsen NICHT ``255 - v``), die Ausgabe-Bytes (Programmer-Flush, Render-Plan,
EFX), Speichern/Laden, der 3D-Payload — und dass Shutter/Aus-Werte unberuehrt
bleiben (Laser-Sicherheit).
"""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import src.core.app_state as A
from src.core.app_state import (AppState, apply_pan_tilt_orientation,
                                unapply_pan_tilt_orientation)
from src.core.database import fixture_db
from src.core.dmx.universe import Universe
from src.core.laser.achsen import achsen_plan, profil_beschreibung, spiegel


def _rg(a, b, name="", kind=""):
    return SimpleNamespace(range_from=a, range_to=b, name=name, kind=kind)


def _ch(attr, num, ranges=(), default=0):
    return SimpleNamespace(attribute=attr, channel_number=num,
                           default_value=default, highlight_value=255,
                           ranges=list(ranges), name=attr)


# Laserworld EL-400RGB MK2 (am Geraet gemessen: X 80 = rechts, 200 = links;
# Y 80 = oben, 200 = unten): 0-10 Mitte, 11-127 eine Richtung, 128-255 andere.
_EL400_X = [_rg(0, 10, "Mitte"), _rg(11, 127, "rechts"), _rg(128, 255, "links")]
_EL400_Y = [_rg(0, 10, "Mitte"), _rg(11, 127, "oben"), _rg(128, 255, "unten")]


def _el400_chans():
    return [_ch("shutter", 1, [_rg(0, 0, "Aus", "closed"),
                               _rg(1, 255, "An", "open")]),
            _ch("laser_x", 2, _EL400_X), _ch("laser_y", 3, _EL400_Y)]


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 3
    protocol = "dmx"
    fixture_type = "laser"

    def __init__(self, fid=7, address=1, **flags):
        self.fid = fid
        self.universe = 1
        self.address = address
        self.invert_pan = self.invert_tilt = self.swap_pan_tilt = False
        self.invert_laser_x = flags.get("invert_laser_x", False)
        self.invert_laser_y = flags.get("invert_laser_y", False)
        self.swap_laser_xy = flags.get("swap_laser_xy", False)


# ── Achsen-Konvention ────────────────────────────────────────────────────────

def test_ohne_bereiche_linear():
    assert achsen_plan(_ch("laser_x", 1))[0] == "linear"
    assert spiegel(0, achsen_plan(_ch("laser_x", 1))) == 255
    assert spiegel(200, achsen_plan(_ch("laser_x", 1))) == 55


def test_fb4_ein_bereich_ueber_alles_ist_linear():
    ch = _ch("laser_x", 1, [_rg(0, 255, "-100 bis +100 % (128 = Mitte)")])
    assert achsen_plan(ch)[0] == "linear"
    assert spiegel(30, achsen_plan(ch)) == 225


def test_el400_mitte_bleibt_richtung_wechselt():
    plan = achsen_plan(_ch("laser_x", 1, _EL400_X))
    assert plan[0] == "zwei"
    # Mitte-Bereich unveraendert — 255-v machte daraus fast ganz links.
    for v in (0, 5, 10):
        assert spiegel(v, plan) == v
    # 80 (rechts) -> in den „links"-Bereich, gleiche Auslenkung.
    links = spiegel(80, plan)
    assert 128 <= links <= 255
    assert abs((links - 128) / 127 - (80 - 11) / 116) < 0.01
    rechts = spiegel(200, plan)
    assert 11 <= rechts <= 127
    # Bereichsenden bleiben Enden.
    assert spiegel(11, plan) == 128 and spiegel(127, plan) == 255
    assert spiegel(128, plan) == 11 and spiegel(255, plan) == 127
    # Fast-Involution (+-1 durch ungleich breite Bereiche).
    for v in range(11, 256):
        assert abs(spiegel(spiegel(v, plan), plan) - v) <= 1


def test_mitte_in_der_mitte_seiten_getauscht():
    plan = achsen_plan(_ch("laser_x", 1, [_rg(0, 119, "links"),
                                          _rg(120, 135, "Mitte"),
                                          _rg(136, 255, "rechts")]))
    assert plan[0] == "seiten"
    assert spiegel(0, plan) == 255          # aussen bleibt aussen
    assert spiegel(119, plan) == 136        # innen bleibt innen
    assert spiegel(127, plan) == 128


def test_l2600_nur_positionsbereich_gespiegelt_eigenbewegung_bleibt():
    chans = _kanaele_l2600()
    x = next(c for c in chans if c.attribute == "laser_x")
    plan = achsen_plan(x)
    assert plan == ("statisch", 0, 127)
    assert spiegel(0, plan) == 127 and spiegel(64, plan) == 63
    assert spiegel(200, plan) == 200        # „Lauf links" bleibt ein Programm


def _kanaele_l2600():
    for name, chans in fixture_db._l2600_modes_data():
        if name == "34-Kanal (Professional DMX)":
            return [SimpleNamespace(
                name=c[0], attribute=c[1],
                ranges=[_rg(a, b, n, k) for a, b, n, k in (c[4] if len(c) > 4 else [])])
                for c in chans]
    raise AssertionError("L2600-Modus fehlt")


def test_profil_beschreibung_nennt_lineare_umkehr_ohne_bereiche():
    t = profil_beschreibung([_ch("laser_x", 1), _ch("laser_y", 2)])
    assert "linear" in t and "255" in t
    assert "Mitte bleibt" in profil_beschreibung(_el400_chans())


# ── Ausgabe-Stufe ────────────────────────────────────────────────────────────

def test_ohne_flags_original_unveraendert():
    attrs = {"laser_x": 80, "laser_y": 80}
    assert apply_pan_tilt_orientation(_Fx(), attrs) is attrs


def test_umkehr_und_tausch_je_kopf(monkeypatch):
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: [
        _ch("laser_x", 1), _ch("laser_y", 2), _ch("laser_x", 3), _ch("laser_y", 4)])
    fx = _Fx(invert_laser_x=True)
    out = apply_pan_tilt_orientation(
        fx, {"laser_x": 10, "laser_y": 20, "laser_x#1": 10, "shutter": 0})
    assert out == {"laser_x": 245, "laser_y": 20, "laser_x#1": 245, "shutter": 0}
    fx = _Fx(swap_laser_xy=True, invert_laser_y=True)
    out = apply_pan_tilt_orientation(fx, {"laser_x": 10, "laser_y": 20})
    # erst Tausch (x->y), dann Umkehr der Y-Achse.
    assert out == {"laser_x": 20, "laser_y": 245}
    assert unapply_pan_tilt_orientation(fx, out) == {"laser_x": 10, "laser_y": 20}


def _bare_state(patch):
    st = AppState.__new__(AppState)
    st._patch_cache = list(patch)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.output_manager = SimpleNamespace(set_gm_address_mask=lambda m: None)
    return st


@pytest.mark.parametrize("weg", ["flush", "render_plan"])
def test_ausgabe_bytes_el400_und_shutter_unberuehrt(monkeypatch, weg):
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: _el400_chans())
    werte = {"shutter": 0, "laser_x": 80, "laser_y": 5}

    def _bytes(fx):
        st = _bare_state([fx])
        if weg == "flush":
            st.programmer = {fx.fid: dict(werte)}
            st._flush_programmer_to_dmx(fx.fid)
            u = st.universes[1]
        else:
            st._rebuild_render_plan()
            u = Universe(1)
            st._apply_fixture_map({1: u}, {fx.fid: dict(werte)})
        return [u.get_channel(i) for i in (1, 2, 3)]

    assert _bytes(_Fx()) == [0, 80, 5]
    sh, x, y = _bytes(_Fx(invert_laser_x=True, invert_laser_y=True))
    assert sh == 0                      # Aus-Wert bleibt aus (Laser-Sicherheit)
    assert 128 <= x <= 255 and x != 255 - 80   # Richtung gewechselt, nicht 255-v
    assert y == 5                       # Mitte bleibt Mitte


def test_efx_auf_laser_achsen_wird_umgekehrt(monkeypatch):
    from src.core.engine.efx import EfxAlgorithm, EfxFixture, EfxInstance
    chans = [_ch("shutter", 1), _ch("laser_x", 2), _ch("laser_y", 3)]
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: chans)

    def _render(fx):
        e = EfxInstance(name="Laser-Kreis")
        e.algorithm = EfxAlgorithm.CIRCLE
        e.fixtures = [EfxFixture(fid=fx.fid, pan_attr="laser_x", tilt_attr="laser_y")]
        e.width = e.height = 200.0
        e.bit16 = False
        e.speed_hz = 0.0
        e._phase = 0.1
        e._running = True
        u = Universe(1)
        e.write({1: u}, [fx], dt=0.0)
        return [u.get_channel(i) for i in (1, 2, 3)]

    sh0, x0, y0 = _render(_Fx())
    sh1, x1, y1 = _render(_Fx(invert_laser_x=True))
    assert x0 != 127 and x1 == 255 - x0 and y1 == y0
    assert sh0 == sh1 == 0


def test_netzwerk_laser_position_gespiegelt():
    from src.core.laser.laser_output import _laser_xy
    st = SimpleNamespace(get_programmer_value=lambda fid, a: {"laser_x": 255,
                                                               "laser_y": 0}.get(a))
    assert _laser_xy(st, _Fx(), 7) == (1.0, pytest.approx(-128 / 127))
    x, y = _laser_xy(st, _Fx(invert_laser_x=True, swap_laser_xy=True), 7)
    assert x == pytest.approx(1.0) and y == pytest.approx(1.0)


# ── 3D-Payload ───────────────────────────────────────────────────────────────

def test_3d_payload_zeigt_modellrichtung():
    from src.ui.visualizer.visualizer_service import _build_fixture_payload
    chans = _el400_chans()[1:]
    from src.core.laser.achsen import apply_laser_orientation
    draht = apply_laser_orientation(
        _Fx(invert_laser_x=True), {"laser_x": 80, "laser_y": 5}, chans)
    assert draht["laser_x"] >= 128   # Draht ist wirklich umgekehrt
    roh = _build_fixture_payload(_Fx(), {"laser_x": 80, "laser_y": 5}, chans)
    inv = _build_fixture_payload(_Fx(invert_laser_x=True), draht, chans)
    assert inv["laser"]["x"] == pytest.approx(roh["laser"]["x"], abs=0.02)
    assert inv["laser"].get("dx") == roh["laser"].get("dx")


# ── Speichern/Laden ──────────────────────────────────────────────────────────

def test_show_rundlauf_und_alte_show_default_aus():
    from src.core.show.show_file import _fixture_to_dict, _patched_fixture_from_data
    fx = _Fx(invert_laser_x=True, swap_laser_xy=True)
    for k in ("label", "manufacturer_name", "fixture_name"):
        setattr(fx, k, "")
    d = _fixture_to_dict(fx)
    assert (d["invert_laser_x"], d["invert_laser_y"], d["swap_laser_xy"]) == (
        True, False, True)
    back = _patched_fixture_from_data(d, 7)
    assert (back.invert_laser_x, back.invert_laser_y, back.swap_laser_xy) == (
        True, False, True)
    alt = {k: v for k, v in d.items()
           if k not in ("invert_laser_x", "invert_laser_y", "swap_laser_xy")}
    back = _patched_fixture_from_data(alt, 7)
    assert not (back.invert_laser_x or back.invert_laser_y or back.swap_laser_xy)


def test_echte_show_speichern_laden(tmp_path):
    from src.core.app_state import get_state
    from src.core.show import show_file
    state = get_state()
    show_file.reset_show()
    fx = A.PatchedFixture(fid=31, label="Laser", fixture_profile_id=0,
                          mode_name="", universe=1, address=100, channel_count=3,
                          fixture_type="laser", invert_laser_y=True,
                          swap_laser_xy=True)
    state.add_fixture(fx, undoable=False)
    assert any(f.fid == 31 for f in state.get_patched_fixtures())
    path = os.path.join(str(tmp_path), "las30.lshow")
    show_file.save_show(path)
    show_file.reset_show()
    ok, msg = show_file.load_show(path)
    assert ok, msg
    f = next(f for f in state.get_patched_fixtures() if f.fid == 31)
    assert (f.invert_laser_x, f.invert_laser_y, f.swap_laser_xy) == (
        False, True, True)
    show_file.reset_show()


# ── Patch-Dialog ─────────────────────────────────────────────────────────────

def _dialog(fx):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from src.core.app_state import get_state
    from src.ui.views.patch_view import PatchFixtureEditDialog
    return PatchFixtureEditDialog(get_state(), fx)


def test_patch_dialog_nur_fuer_laser_und_uebernimmt_flags():
    def _pf(typ, **kw):
        return A.PatchedFixture(fid=41, label="L", fixture_profile_id=0,
                                mode_name="", universe=1, address=1,
                                channel_count=3, fixture_type=typ, **kw)
    d = _dialog(_pf("moving_head"))
    assert d._chk_inv_lx is None
    d.deleteLater()
    d = _dialog(_pf("laser", invert_laser_y=True))
    assert d._chk_inv_lx is not None and d._chk_inv_ly.isChecked()
    d._chk_inv_lx.setChecked(True)
    d._chk_swap_lxy.setChecked(True)
    d._chk_inv_ly.setChecked(False)
    d._on_accept()
    assert d.result_updates is not None
    assert (d.result_updates["invert_laser_x"], d.result_updates["invert_laser_y"],
            d.result_updates["swap_laser_xy"]) == (True, False, True)
    d.deleteLater()
