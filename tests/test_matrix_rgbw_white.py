"""Cluster B: RGBW-Matrix erzeugt ECHTES Weiss ueber den W-Kanal.

Weiss laeuft rein ueber den weissen Chip (color_w = min(r,g,b)), RGB nur der
Rest (r-w, g-w, b-w) — gleiche Konvention wie color_utils.color_attrs_for_fixture.
Der RGB-Style fasst den W-Kanal nie an. Kein "Weissanteil"-Regler mehr.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.dmx.universe import Universe
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, MatrixStyle


class _Ch:
    def __init__(self, attribute, channel_number):
        self.attribute = attribute
        self.channel_number = channel_number
        self.ranges = []
        self.default_value = 0


class _Fx:
    def __init__(self, fid, universe, address, channels):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.channels = channels


def _rgbw_chans():
    return [_Ch("color_r", 1), _Ch("color_g", 2), _Ch("color_b", 3), _Ch("color_w", 4)]


class MatrixRgbwWhiteTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: fx.channels

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _write(self, color, style):
        m = RgbMatrixInstance(name="t", cols=1, rows=1, fixture_grid=[1],
                              algorithm=RgbAlgorithm.PLAIN, color1=color)
        m.style = style
        m.start()
        fx = _Fx(1, 1, 1, _rgbw_chans())   # r@1, g@2, b@3, w@4
        u = Universe(1)
        m.write({1: u}, [fx], 0.0)
        return u

    def test_rgbw_white_uses_real_white(self):
        u = self._write((255, 255, 255), MatrixStyle.RGBW)
        self.assertEqual(u.get_channel(4), 255, "color_w = min(r,g,b) = 255")
        self.assertEqual(u.get_channel(1), 0, "kein RGB-Weiss")
        self.assertEqual(u.get_channel(2), 0)
        self.assertEqual(u.get_channel(3), 0)

    def test_rgbw_pastel_splits_white_and_residual(self):
        u = self._write((255, 128, 128), MatrixStyle.RGBW)
        self.assertEqual(u.get_channel(4), 128, "w = min(r,g,b)")
        self.assertEqual(u.get_channel(1), 127, "Rest = 255-128")
        self.assertEqual(u.get_channel(2), 0)
        self.assertEqual(u.get_channel(3), 0)

    def test_rgbw_saturated_red_no_white(self):
        u = self._write((255, 0, 0), MatrixStyle.RGBW)
        self.assertEqual(u.get_channel(4), 0, "kein Weissanteil bei gesaettigtem Rot")
        self.assertEqual(u.get_channel(1), 255)

    def test_rgb_style_never_touches_white_channel(self):
        u = self._write((255, 255, 255), MatrixStyle.RGB)
        self.assertEqual(u.get_channel(1), 255, "RGB-Weiss klassisch ueber RGB")
        self.assertEqual(u.get_channel(2), 255)
        self.assertEqual(u.get_channel(3), 255)
        self.assertEqual(u.get_channel(4), 0, "W-Kanal bei RGB-Style unangetastet")


if __name__ == "__main__":
    unittest.main()
