"""LAS-23: ein Laser-EFX verlor beim Speichern seine Achsen.

``EfxInstance.to_dict()`` schrieb je Ziel nur ``fid``/``offset``/``head`` —
``pan_attr``/``tilt_attr`` fielen weg. Ein EFX auf ``laser_x``/``laser_y`` kam
nach dem Laden als ``pan``/``tilt`` zurueck; der Laser hat keinen Pan-Kanal,
also schrieb der Effekt still NICHTS (laser_x/laser_y blieben stehen).

Geprueft wird der echte Weg ``save_show`` -> ``reset_show`` -> ``load_show``
(conftest isoliert Show-DB und Datenordner), danach das Rendern des geladenen
EFX in ein Universum, und der Show-Lint fuer EFX-Ziele ohne passende Achse.
"""
from __future__ import annotations

import json
import os
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import src.core.app_state as A
from src.core.dmx.universe import Universe
from src.core.engine.efx import EfxAlgorithm, EfxFixture, EfxInstance


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0
        self.highlight_value = 255
        self.ranges = []


class _Laser:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 4
    protocol = ""
    fixture_type = "laser"

    def __init__(self, fid=5, universe=1, address=1):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.invert_pan = self.invert_tilt = self.swap_pan_tilt = False


# Laser ohne Pan/Tilt: shutter, Muster, laser_x (CH3), laser_y (CH4).
_LASER_CHANS = [_Ch("shutter", 1), _Ch("laser_bank", 2),
                _Ch("laser_x", 3), _Ch("laser_y", 4)]


def _laser_efx(fid=5) -> EfxInstance:
    e = EfxInstance(name="Laser-Kreis")
    e.algorithm = EfxAlgorithm.CIRCLE
    e.fixtures = [EfxFixture(fid=fid, pan_attr="laser_x", tilt_attr="laser_y")]
    e.width = e.height = 200.0
    e.bit16 = False
    return e


# ── Serialisierung ───────────────────────────────────────────────────────────

def test_to_dict_keeps_laser_axes_and_from_dict_restores_them():
    d = _laser_efx().to_dict()
    assert d["fixtures"] == [{"fid": 5, "offset": 0.0,
                              "pan_attr": "laser_x", "tilt_attr": "laser_y"}]
    back = EfxInstance.from_dict(json.loads(json.dumps(d)))
    assert (back.fixtures[0].pan_attr, back.fixtures[0].tilt_attr) == (
        "laser_x", "laser_y")


def test_default_axes_are_not_written_old_shows_stay_byte_identical():
    e = EfxInstance(name="MH")
    e.fixtures = [EfxFixture(fid=1), EfxFixture(fid=2, head=1)]
    assert e.to_dict()["fixtures"] == [
        {"fid": 1, "offset": 0.0},
        {"fid": 2, "offset": 0.0, "head": 1}]


def test_old_show_without_axes_and_garbage_axes_fall_back_to_pan_tilt():
    e = EfxInstance.from_dict({"motion": True, "fixtures": [
        {"fid": 1, "offset": 0.0},
        {"fid": 2, "offset": 0.0, "pan_attr": "", "tilt_attr": 7}]})
    for t in e.fixtures:
        assert (t.pan_attr, t.tilt_attr) == ("pan", "tilt")


def test_all_persistent_target_fields_roundtrip():
    """Jedes Feld von EfxFixture (ausser Laufzeit) muss den Rundlauf ueberleben."""
    import dataclasses
    t = EfxFixture(fid=9, start_offset=0.25, pan_attr="laser_x",
                   tilt_attr="laser_y", head=2)
    e = EfxInstance(name="x")
    e.fixtures = [t]
    back = EfxInstance.from_dict(e.to_dict()).fixtures[0]
    for f in dataclasses.fields(EfxFixture):
        assert getattr(back, f.name) == getattr(t, f.name), f.name


# ── Echter Show-Rundlauf + DMX nach dem Laden ────────────────────────────────

def _render(efx: EfxInstance, phase: float) -> Universe:
    uni = Universe(1)
    efx.speed_hz = 0.0
    efx._phase = phase
    efx._running = True
    efx.write({1: uni}, [_Laser()], dt=0.0)
    return uni


def test_laser_efx_moves_laser_x_after_real_save_load(tmp_path, monkeypatch):
    from src.core.app_state import get_state
    from src.core.show import show_file

    state = get_state()
    show_file.reset_show()
    e = state.function_manager.new_efx("Laser-Kreis")
    e.algorithm = EfxAlgorithm.CIRCLE
    e.fixtures = [EfxFixture(fid=5, pan_attr="laser_x", tilt_attr="laser_y")]
    e.width = e.height = 200.0
    e.bit16 = False
    fn_id = e.id

    path = os.path.join(str(tmp_path), "las23.lshow")
    show_file.save_show(path)
    with zipfile.ZipFile(path) as z:
        data = json.loads(z.read("show.json").decode("utf-8"))
    saved = [f for f in data["functions"]["functions"] if f.get("id") == fn_id]
    assert saved and saved[0]["fixtures"][0]["pan_attr"] == "laser_x"

    show_file.reset_show()
    ok, msg = show_file.load_show(path)
    assert ok, msg
    loaded = state.function_manager.get(fn_id)
    assert isinstance(loaded, EfxInstance)
    assert loaded.fixtures[0].pan_attr == "laser_x"
    assert loaded.fixtures[0].tilt_attr == "laser_y"

    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: _LASER_CHANS)
    a = _render(loaded, 0.0)
    b = _render(loaded, 0.5)
    # laser_x (CH3) bewegt sich; shutter (CH1) und Muster (CH2) bleiben unberuehrt.
    assert a.get_channel(3) != b.get_channel(3)
    assert a.get_channel(1) == b.get_channel(1) == 0
    assert a.get_channel(2) == 0
    show_file.reset_show()


def test_without_axes_the_laser_stays_still_documents_the_bug(monkeypatch):
    """Gegenprobe: mit pan/tilt (= der alte Ladezustand) schreibt der EFX nichts."""
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: _LASER_CHANS)
    e = _laser_efx()
    e.fixtures = [EfxFixture(fid=5)]
    a, b = _render(e, 0.0), _render(e, 0.5)
    assert a.get_channel(3) == b.get_channel(3) == 0


# ── Show-Lint ────────────────────────────────────────────────────────────────

def _show(fixtures):
    return {"patch": [{"fid": 5, "label": "Laser", "fixture_profile_id": 1,
                       "mode_name": "m", "channel_count": 4, "address": 1}],
            "functions": {"functions": [
                {"id": 1, "type": "EFX", "name": "Kreis", "motion": True,
                 "fixtures": fixtures}]}}


def test_lint_warns_when_efx_axes_missing_on_device(monkeypatch):
    from src.core.capability.efx_achsen_check import efx_achsen_befunde
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: _LASER_CHANS)
    befunde = efx_achsen_befunde(_show([{"fid": 5, "offset": 0.0}]))
    assert [b.code for b in befunde] == ["EFX-ACHSE-FEHLT"]
    assert efx_achsen_befunde(_show([{"fid": 5, "offset": 0.0,
                                      "pan_attr": "laser_x",
                                      "tilt_attr": "laser_y"}])) == []


def test_lint_silent_for_unknown_profile_and_spider(monkeypatch):
    from src.core.capability.efx_achsen_check import efx_achsen_befunde
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: [])
    assert efx_achsen_befunde(_show([{"fid": 5, "offset": 0.0}])) == []
    # Spider: nur Tilt -> gewolltes Ziel, keine Warnung.
    monkeypatch.setattr(A, "get_channels_for_patched",
                        lambda fx: [_Ch("tilt", 1), _Ch("tilt", 2)])
    assert efx_achsen_befunde(_show([{"fid": 5, "offset": 0.0}])) == []
