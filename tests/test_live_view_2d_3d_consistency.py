"""Tests fuer die 2D<->3D-Konsistenz der Live-View (Branch fix/liveview-2d-3d-consistency).

Deckt zwei Audit-Befunde ab:
- ``_fixture_color_and_intensity`` muss bei Mehrkopf-Geraeten (Spider, zwei
  ``color_r``-Kanaele) den ERSTEN Satz (Kopf 0) verwenden — genau wie der
  3D-Top-Down-Icon. Frueher gewann der letzte Kanal -> Bank 2 -> 2D/3D-Farbe
  liefen auseinander.
- ``dmx_to_angle_deg`` ist die EINE Winkel-Quelle fuer 2D-Beam-Glyph, Info-Box
  und 3D-Visualizer (Formel ``(dmx-zero)/128 * range/2`` wie aim.py /
  stage_scene.html).
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.ui.views.live_view as live_view
from src.ui.views.live_view import StageCanvas, dmx_to_angle_deg


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class _FakeUniverse:
    def __init__(self, vals: dict[int, int]):
        self._vals = vals

    def get_channel(self, addr: int) -> int:
        return self._vals.get(addr, 0)


def _ch(n: int, attr: str):
    return SimpleNamespace(channel_number=n, attribute=attr)


# ── Spider-Farbe: Kopf 0 (erste Bank) gewinnt, wie im 3D ─────────────────────

def test_spider_color_uses_first_bank(monkeypatch):
    """Spider mit Bank0=ROT, Bank1=BLAU -> 2D-Farbe muss ROT (Kopf 0) sein."""
    _app()
    c = StageCanvas()
    fx = SimpleNamespace(fid=1, universe=1, address=1,
                         label="SPI-1", fixture_type="Spider")

    # Zwei RGBW-Baenke; beide Kanalsaetze tragen dieselben attribute-Namen.
    channels = [
        _ch(1, "color_r"), _ch(2, "color_g"), _ch(3, "color_b"), _ch(4, "color_w"),
        _ch(5, "color_r"), _ch(6, "color_g"), _ch(7, "color_b"), _ch(8, "color_w"),
    ]
    # Bank 0 (addr 1..4) = ROT, Bank 1 (addr 5..8) = BLAU
    vals = {1: 255, 2: 0, 3: 0, 4: 0,
            5: 0,   6: 0, 7: 255, 8: 0}

    monkeypatch.setattr(live_view, "get_channels_for_patched", lambda _f: channels)
    monkeypatch.setattr(c._state, "universes", {1: _FakeUniverse(vals)})

    color, _intensity = c._fixture_color_and_intensity(fx)
    assert (color.red(), color.green(), color.blue()) == (255, 0, 0), \
        "2D muss Bank 0 (Kopf 0 = ROT) zeigen, nicht Bank 1 (BLAU)"


def test_single_head_color_unchanged(monkeypatch):
    """Einkopf-Geraet: Verhalten unveraendert (Weiss wird auf RGB addiert)."""
    _app()
    c = StageCanvas()
    fx = SimpleNamespace(fid=2, universe=1, address=1,
                         label="PAR-1", fixture_type="PAR")
    channels = [_ch(1, "color_r"), _ch(2, "color_g"), _ch(3, "color_b"),
                _ch(4, "color_w"), _ch(5, "intensity")]
    vals = {1: 100, 2: 0, 3: 0, 4: 50, 5: 200}  # rot 100 + weiss 50

    monkeypatch.setattr(live_view, "get_channels_for_patched", lambda _f: channels)
    monkeypatch.setattr(c._state, "universes", {1: _FakeUniverse(vals)})

    color, intensity = c._fixture_color_and_intensity(fx)
    assert (color.red(), color.green(), color.blue()) == (150, 50, 50)
    assert intensity == 200


def test_fixture_without_color_channels_is_white(monkeypatch):
    """Reiner Dimmer-PAR (keine Farbkanaele): die 2D-Ansicht zeigte ihn schwarz,
    weil ``color_r`` fehlt und mit 0 angenommen wurde. Er leuchtet weiss —
    dieselbe Ableitung wie im 3D (``color_utils.visual_rgb``)."""
    _app()
    c = StageCanvas()
    fx = SimpleNamespace(fid=3, universe=1, address=1,
                         label="DIM-1", fixture_type="PAR")
    channels = [_ch(1, "intensity")]
    monkeypatch.setattr(live_view, "get_channels_for_patched", lambda _f: channels)
    monkeypatch.setattr(c._state, "universes", {1: _FakeUniverse({1: 180})})

    color, intensity = c._fixture_color_and_intensity(fx)
    assert (color.red(), color.green(), color.blue()) == (255, 255, 255)
    assert intensity == 180


def test_strobe_without_dimmer_follows_shutter(monkeypatch):
    """Xenon-Strobe ohne Dimmer-Kanal: frueher galt er als konstant voll hell.
    Jetzt entscheidet der Shutter ueber die hinterlegte Range-Semantik."""
    _app()
    c = StageCanvas()
    fx = SimpleNamespace(fid=4, universe=1, address=1,
                         label="STR-1", fixture_type="Strobe")
    shutter = SimpleNamespace(channel_number=1, attribute="shutter", ranges=[
        SimpleNamespace(range_from=0, range_to=5, name="Blackout", kind="closed"),
        SimpleNamespace(range_from=6, range_to=255, name="Blitzrate", kind="strobe"),
    ])
    monkeypatch.setattr(live_view, "get_channels_for_patched", lambda _f: [shutter])

    monkeypatch.setattr(c._state, "universes", {1: _FakeUniverse({1: 0})})
    assert c._fixture_color_and_intensity(fx)[1] == 0

    monkeypatch.setattr(c._state, "universes", {1: _FakeUniverse({1: 200})})
    color, intensity = c._fixture_color_and_intensity(fx)
    assert intensity == 255
    assert (color.red(), color.green(), color.blue()) == (255, 255, 255)


# ── Winkel-Helper: eine Quelle fuer 2D & 3D ──────────────────────────────────

def test_dmx_to_angle_deg_center_is_zero():
    assert dmx_to_angle_deg(128, 128, 540) == 0.0


def test_dmx_to_angle_deg_matches_3d_half_range():
    # (dmx - zero)/128 * (range/2): bei DMX 256 relativ zu 128 -> +volle Haelfte
    assert dmx_to_angle_deg(256, 128, 540) == pytest.approx(270.0)
    assert dmx_to_angle_deg(0, 128, 540) == pytest.approx(-270.0)
    # Tilt-Default 270 -> Halbbereich 135 (wie alte fixe Info-Box-Konstante)
    assert dmx_to_angle_deg(256, 128, 270) == pytest.approx(135.0)


def test_dmx_to_angle_deg_honours_zero_and_range():
    # Nicht-Default-Nullpunkt + -Bereich werden beruecksichtigt
    assert dmx_to_angle_deg(128, 0, 360) == pytest.approx((128 - 0) / 128 * 180)
    assert dmx_to_angle_deg(64, 64, 540) == 0.0
