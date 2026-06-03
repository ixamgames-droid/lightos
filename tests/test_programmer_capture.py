"""Tests fuer das attribut-gefilterte 'Programmer -> Szene'-Speichern."""
from __future__ import annotations
from src.ui.views import programmer_view as pv


class _Ch:
    def __init__(self, attribute, channel_number):
        self.attribute = attribute
        self.channel_number = channel_number


class _Fx:
    def __init__(self, fid):
        self.fid = fid


def _patch_channels(monkeypatch):
    chans = [_Ch("intensity", 1), _Ch("color_r", 2),
             _Ch("color_g", 3), _Ch("color_b", 4), _Ch("shutter", 5)]
    monkeypatch.setattr(pv, "get_channels_for_patched", lambda fx: chans)
    return chans


def test_scene_values_map_attr_to_channel(monkeypatch):
    _patch_channels(monkeypatch)
    filtered = {1: {"color_r": 255, "color_g": 0, "color_b": 0}}
    out = pv.programmer_to_scene_values(filtered, [_Fx(1)])
    assert sorted(out) == [(1, 2, 255), (1, 3, 0), (1, 4, 0)]
    # intensity/shutter wurden NICHT mitgespeichert (waren rausgefiltert)
    assert all(ch not in (1, 5) for _, ch, _ in out)


def test_scene_values_only_filtered_attributes(monkeypatch):
    _patch_channels(monkeypatch)
    # Nur Dimmer (intensity) -> nur Kanal 1
    filtered = {1: {"intensity": 200}}
    out = pv.programmer_to_scene_values(filtered, [_Fx(1)])
    assert out == [(1, 1, 200)]


def test_scene_values_clamps_and_skips_unpatched(monkeypatch):
    _patch_channels(monkeypatch)
    filtered = {1: {"color_r": 300, "unknown_attr": 50}, 9: {"color_r": 10}}
    out = pv.programmer_to_scene_values(filtered, [_Fx(1)])
    # 300 -> 255 geklemmt, unknown_attr ohne Kanal ignoriert, fid 9 nicht gepatcht
    assert out == [(1, 2, 255)]
