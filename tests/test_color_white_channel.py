"""P6: Weiss-Auswahl nutzt den echten White-Kanal (RGBW-Konvertierung).

Zentrale Logik: src/core/color_utils.adapt_color_payload — Fixtures mit
color_w bekommen den Weissanteil ueber W (RGB reduziert), Fixtures ohne W
weiterhin RGB-Weiss. Dazu Integration ueber den Quick-Color-Anwendepfad
(_ApplyMixin._apply_payload in preset_tile).
"""
from __future__ import annotations
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.color_utils import adapt_color_payload

RGBW = {"color_r", "color_g", "color_b", "color_w", "intensity"}
RGB = {"color_r", "color_g", "color_b", "intensity"}

WHITE = {"color_w": 255, "color_r": 255, "color_g": 255, "color_b": 255}
RED = {"color_r": 255, "color_g": 0, "color_b": 0, "color_w": 0}


def test_white_uses_w_channel_on_rgbw():
    out = adapt_color_payload(RGBW, WHITE)
    assert out == {"color_r": 0, "color_g": 0, "color_b": 0, "color_w": 255}


def test_white_stays_rgb_on_rgb_only():
    out = adapt_color_payload(RGB, WHITE)
    assert out == {"color_r": 255, "color_g": 255, "color_b": 255}
    assert "color_w" not in out          # kein toter W-Wert im Programmer


def test_red_unchanged_and_clears_w():
    out = adapt_color_payload(RGBW, RED)
    assert out == {"color_r": 255, "color_g": 0, "color_b": 0, "color_w": 0}


def test_pastel_extracts_common_white():
    # Rosa (255,128,128): w=128 wandert in den W-Kanal
    out = adapt_color_payload(RGBW, {"color_r": 255, "color_g": 128,
                                     "color_b": 128})
    assert out == {"color_r": 127, "color_g": 0, "color_b": 0, "color_w": 128}


def test_non_color_payload_untouched():
    payload = {"shutter": 255, "gobo_wheel": 32}
    assert adapt_color_payload(RGBW, payload) == payload


def test_extra_keys_pass_through():
    out = adapt_color_payload(RGBW, {"color_r": 0, "color_g": 0, "color_b": 0,
                                     "color_w": 0, "color_a": 0, "color_uv": 0})
    assert out["color_a"] == 0 and out["color_uv"] == 0


class _Ch:
    def __init__(self, attr):
        self.attribute = attr


class _Fx:
    def __init__(self, fid, attrs):
        self.fid = fid
        self._attrs = attrs


class _StateStub:
    def __init__(self):
        self.calls = []

    def set_programmer_value(self, fid, attr, value):
        self.calls.append((fid, attr, value))


def test_apply_payload_adapts_per_fixture(monkeypatch):
    """Integration: Quick-Color 'Weiss' auf gemischte Auswahl (RGBW + RGB)."""
    import src.core.app_state as A
    monkeypatch.setattr(A, "get_channels_for_patched",
                        lambda fx: [_Ch(a) for a in fx._attrs])

    from src.ui.widgets.preset_tile import _ApplyMixin

    class _Bar(_ApplyMixin):
        def __init__(self, fixtures, state):
            self._fixtures = fixtures
            self._state = state

    state = _StateStub()
    bar = _Bar([_Fx(1, RGBW), _Fx(2, RGB)], state)
    bar._apply_payload(dict(WHITE))

    by_fid = {}
    for fid, attr, val in state.calls:
        by_fid.setdefault(fid, {})[attr] = val
    # RGBW-Fixture: nur W leuchtet
    assert by_fid[1] == {"color_r": 0, "color_g": 0, "color_b": 0,
                         "color_w": 255}
    # RGB-Fixture: klassisches RGB-Weiss, kein color_w geschrieben
    assert by_fid[2] == {"color_r": 255, "color_g": 255, "color_b": 255}
