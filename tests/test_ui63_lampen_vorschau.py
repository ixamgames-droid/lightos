"""UI-63: Die Lampen-Vorschau zeigt, was das Geraet wirklich ausgibt.

Frueher zeichnete ``_TileGrid._tile_color`` jedes Geraet mit Dimmer > 0 und
R=G=B=0 als Weiss („Dimmer-only -> Weiss"), auch einen RGB-PAR — der echte PAR
bleibt dabei dunkel. Die Tests bauen echte ``FixtureChannel``-/``ChannelRange``-
Objekte, setzen Werte ueber den echten ``AppState.set_programmer_value`` und
pruefen die Kachel gegen das, was ``_flush_programmer_to_dmx`` ins Universum
schreibt.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

import src.core.app_state as A
import src.ui.widgets.fixture_tile_preview as ftp
from src.core.database.models import ChannelRange, FixtureChannel
from src.core.dmx.universe import Universe


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _ch(nr, attr, default=0, ranges=()):
    ch = FixtureChannel(channel_number=nr, name=attr, attribute=attr,
                        default_value=default)
    for lo, hi, name in ranges:
        ch.ranges.append(ChannelRange(range_from=lo, range_to=hi, name=name))
    return ch


GERAETE = {
    1: [_ch(1, "intensity"), _ch(2, "color_r"), _ch(3, "color_g"), _ch(4, "color_b")],
    2: [_ch(1, "intensity"), _ch(2, "color_r"), _ch(3, "color_g"),
        _ch(4, "color_b"), _ch(5, "color_w")],
    3: [_ch(1, "intensity")],
    4: [_ch(1, "intensity"),
        _ch(2, "color_wheel", ranges=((0, 9, "Open"), (10, 19, "Red"),
                                       (20, 29, "Blue")))],
    # Weiss-Segment-Geraet: nur Weiss-LEDs, kein R/G/B.
    5: [_ch(1, "intensity"), _ch(2, "color_w")],
}


@pytest.fixture
def state(monkeypatch):
    _app()
    st = A.AppState()
    st.universes[1] = Universe(1)
    st._patch_cache = [NS(fid=fid, universe=1, address=1 + (fid - 1) * 10,
                          label=f"Lampe {fid}", fixture_type="par")
                       for fid in GERAETE]
    monkeypatch.setattr(A, "get_channels_for_patched",
                        lambda fx: GERAETE[int(fx.fid)])
    monkeypatch.setattr(ftp, "get_state", lambda: st)
    return st


def _kachel(fid) -> tuple[int, int, int]:
    c = ftp._TileGrid()._tile_color(fid)
    return (c.red(), c.green(), c.blue())


def _dmx(st, fid) -> dict[str, int]:
    """Was der echte Programmer-Flush fuer dieses Geraet ins Universum schreibt."""
    st._flush_programmer_to_dmx(fid)
    fx = next(f for f in st._patch_cache if f.fid == fid)
    uni = st.universes[1]
    return {ch.attribute: uni.get_channel(fx.address + ch.channel_number - 1)
            for ch in GERAETE[fid]}


def test_rgb_par_nur_dimmer_bleibt_dunkel(state):
    """Kern von UI-63: Dimmer voll, keine Farbe -> der PAR gibt Schwarz aus."""
    state.set_programmer_value(1, "intensity", 255)
    out = _dmx(state, 1)
    assert (out["color_r"], out["color_g"], out["color_b"]) == (0, 0, 0)
    assert _kachel(1) == (0, 0, 0)


def test_rgbw_par_nur_dimmer_bleibt_dunkel(state):
    state.set_programmer_value(2, "intensity", 255)
    assert _kachel(2) == (0, 0, 0)


def test_rgbw_par_weiss_leuchtet_weiss(state):
    state.set_programmer_value(2, "intensity", 255)
    state.set_programmer_value(2, "color_w", 255)
    assert _kachel(2) == (255, 255, 255)


def test_rgb_par_farbe_mal_dimmer(state):
    state.set_programmer_value(1, "intensity", 128)
    state.set_programmer_value(1, "color_r", 255)
    r, g, b = _kachel(1)
    assert (g, b) == (0, 0)
    assert 120 <= r <= 130


def test_reiner_dimmer_bleibt_weiss(state):
    """Geraet OHNE Farbkanal leuchtet in Lampenfarbe — weiter weiss/hell."""
    state.set_programmer_value(3, "intensity", 255)
    assert _kachel(3) == (255, 255, 255)
    state.set_programmer_value(3, "intensity", 0)
    assert _kachel(3) == (0, 0, 0)


def test_farbrad_mover_zeigt_slot(state):
    state.set_programmer_value(4, "intensity", 255)
    assert _kachel(4) == (255, 255, 255)        # Rad auf Default = Open
    state.set_programmer_value(4, "color_wheel", 15)
    r, g, b = _kachel(4)
    assert r > 200 and g < 80 and b < 80        # roter Slot


def test_weiss_segment_geraet(state):
    state.set_programmer_value(5, "intensity", 255)
    assert _kachel(5) == (0, 0, 0)              # Weiss-LED aus -> dunkel
    state.set_programmer_value(5, "color_w", 200)
    assert _kachel(5) == (200, 200, 200)


def test_dimmer_default_aus_kanal_wie_der_flush(state):
    """Nur Farbe gesetzt, Dimmer steht auf default 0 -> Ausgabe dunkel."""
    state.set_programmer_value(1, "color_r", 255)
    assert _dmx(state, 1)["intensity"] == 0
    assert _kachel(1) == (0, 0, 0)


def test_leerer_programmer_ist_schwarz(state):
    assert _kachel(1) == (0, 0, 0)


def test_namen_auf_hellen_kacheln_lesbar():
    _app()
    hell = ftp._TileGrid._label_color(QColor(255, 255, 255))
    dunkel = ftp._TileGrid._label_color(QColor(0, 0, 0))
    gelb = ftp._TileGrid._label_color(QColor(255, 255, 0))
    blau = ftp._TileGrid._label_color(QColor(0, 0, 255))
    assert hell.lightness() < 60 and gelb.lightness() < 60
    assert dunkel.lightness() > 150 and blau.lightness() > 150


def test_paint_mit_heller_kachel_wirft_nicht(state):
    state.set_programmer_value(3, "intensity", 255)
    grid = ftp._TileGrid()
    grid.resize(200, 120)
    grid.set_fixtures([1, 3], {1: "PAR", 3: "Dimmer"})
    grid.grab()   # echter paintEvent offscreen
