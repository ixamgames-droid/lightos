"""Matrix: Farbrad-Fallback in RgbMatrixInstance.write().

Ein Color-Matrix-Effekt auf einem Moving Head OHNE RGB, aber MIT Farbrad
(ein Kanal attribute=="color" mit benannten color-Slots), faerbt das Geraet
jetzt ueber den naechstgelegenen Slot. RGB-Geraete bekommen weiterhin EXAKT
color_r/g/b (bit-identisch, keine Regression). Pan/Tilt bleiben unangetastet.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.dmx.universe import Universe
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, MatrixStyle


class _Range:
    def __init__(self, name, range_from, range_to, kind="color"):
        self.name = name
        self.range_from = range_from
        self.range_to = range_to
        self.kind = kind


class _Ch:
    def __init__(self, attribute, channel_number, ranges=None):
        self.attribute = attribute
        self.channel_number = channel_number
        self.ranges = ranges or []
        self.default_value = 0


class _Fx:
    def __init__(self, fid, universe, address, channels):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.channels = channels


# Farbrad-Moving-Head: pan@1, tilt@2, color-Farbrad@3 mit Rot/Gruen/Blau-Slots,
# Dimmer@4. KEINE color_r/g/b-Kanaele.
def _colorwheel_chans():
    return [
        _Ch("pan", 1),
        _Ch("tilt", 2),
        _Ch("color", 3, ranges=[
            _Range("Rot", 0, 9),
            _Range("Gruen", 10, 19),
            _Range("Blau", 20, 29),
        ]),
        _Ch("intensity", 4),
    ]


# Klassisches RGB-Fixture (zur Regressionssicherung).
def _rgb_chans():
    return [_Ch("color_r", 1), _Ch("color_g", 2), _Ch("color_b", 3)]


class _PlainRed(RgbMatrixInstance):
    """PLAIN-Matrix, die immer reines Rot ausgibt (deterministisch)."""


def _red_matrix(fixture_grid):
    m = RgbMatrixInstance(name="t", cols=len(fixture_grid), rows=1,
                          fixture_grid=fixture_grid,
                          algorithm=RgbAlgorithm.PLAIN, color1=(255, 0, 0))
    m.style = MatrixStyle.RGB
    m.start()
    return m


class MatrixColorwheelTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        self._map = {}
        A.get_channels_for_patched = lambda fx: self._map[fx.fid]

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def test_colorwheel_gets_red_slot_and_no_movement(self):
        """Farbrad-Geraet: color-Kanal = Mittelwert des Rot-Slots (0..9 -> 4),
        pan/tilt bleiben 0 (keine Bewegung durch die Color-Matrix)."""
        fx = _Fx(1, 1, 10, _colorwheel_chans())   # pan@10, tilt@11, color@12, dim@13
        self._map = {1: fx.channels}
        u = Universe(1)
        _red_matrix([1]).write({1: u}, [fx], 0.0)
        self.assertEqual(u.get_channel(12), 4, "color-Kanal = Rot-Slot-Mittelwert (0+9)//2")
        self.assertEqual(u.get_channel(10), 0, "pan unangetastet")
        self.assertEqual(u.get_channel(11), 0, "tilt unangetastet")

    def test_rgb_fixture_bit_identical(self):
        """RGB-Geraet bekommt weiterhin exakt color_r/g/b (Regression)."""
        fx = _Fx(2, 1, 20, _rgb_chans())          # r@20, g@21, b@22
        self._map = {2: fx.channels}
        u = Universe(1)
        _red_matrix([2]).write({1: u}, [fx], 0.0)
        self.assertEqual(u.get_channel(20), 255)
        self.assertEqual(u.get_channel(21), 0)
        self.assertEqual(u.get_channel(22), 0)

    def test_colorwheel_picks_nearest_slot(self):
        """Gruene Ziel-Farbe waehlt den Gruen-Slot (10..19 -> 14)."""
        m = RgbMatrixInstance(name="t", cols=1, rows=1, fixture_grid=[1],
                              algorithm=RgbAlgorithm.PLAIN, color1=(0, 255, 0))
        m.style = MatrixStyle.RGB
        m.start()
        fx = _Fx(1, 1, 1, _colorwheel_chans())    # pan@1, tilt@2, color@3, dim@4
        self._map = {1: fx.channels}
        u = Universe(1)
        m.write({1: u}, [fx], 0.0)
        self.assertEqual(u.get_channel(3), 14, "Gruen-Slot-Mittelwert (10+19)//2")

    def test_colorwheel_slot_not_scaled_by_intensity(self):
        """intensity halbiert NICHT den Farbrad-Slot (Slot wuerde sich verschieben).
        Der Slot bleibt der Rot-Mittelwert, egal wie der Per-Effekt-Master steht."""
        m = RgbMatrixInstance(name="t", cols=1, rows=1, fixture_grid=[1],
                              algorithm=RgbAlgorithm.PLAIN, color1=(255, 0, 0))
        m.style = MatrixStyle.RGB
        m.drive_intensity = False
        m.intensity = 0.5
        m.start()
        fx = _Fx(1, 1, 1, _colorwheel_chans())
        self._map = {1: fx.channels}
        u = Universe(1)
        m.write({1: u}, [fx], 0.0)
        self.assertEqual(u.get_channel(3), 4, "Rot-Slot unveraendert (nicht mit intensity skaliert)")

    def test_mixed_grid_both_correct(self):
        """Farbrad + RGB im selben Grid: jeder bekommt seinen passenden Output."""
        fx_wheel = _Fx(1, 1, 1, _colorwheel_chans())   # color@3
        fx_rgb = _Fx(2, 1, 20, _rgb_chans())           # r@20
        self._map = {1: fx_wheel.channels, 2: fx_rgb.channels}
        u = Universe(1)
        _red_matrix([1, 2]).write({1: u}, [fx_wheel, fx_rgb], 0.0)
        self.assertEqual(u.get_channel(3), 4)      # Farbrad: Rot-Slot
        self.assertEqual(u.get_channel(20), 255)   # RGB: voll rot
        self.assertEqual(u.get_channel(21), 0)


if __name__ == "__main__":
    unittest.main()
