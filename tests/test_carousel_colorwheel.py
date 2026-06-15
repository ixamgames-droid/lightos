"""Carousel: paint_color faerbt auch Farbrad-Geraete (ueber color_attrs_for_fixture).

Mit paint_color=True schreibt das Carousel seine Eigenfarbe. RGB-Geraete
bekommen wie bisher color_r/g/b; Farbrad-Geraete (Kanal attribute=="color")
bekommen den passenden Slot statt gar nichts.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.dmx.universe import Universe
from src.core.engine.carousel import Carousel, CarouselPattern


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


class _Fx:
    def __init__(self, fid, universe, address):
        self.fid = fid
        self.universe = universe
        self.address = address


def _colorwheel_chans():
    return [
        _Ch("intensity", 1),
        _Ch("color", 2, ranges=[
            _Range("Rot", 0, 9),
            _Range("Gruen", 10, 19),
            _Range("Blau", 20, 29),
        ]),
    ]


_RGB_CHANS = [_Ch("intensity", 1), _Ch("color_r", 2),
              _Ch("color_g", 3), _Ch("color_b", 4)]


class CarouselColorwheelTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        self._map = {}
        A.get_channels_for_patched = lambda fx: self._map[fx.fid]
        self.u = Universe(1)

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _run(self, c, fx, frames=3, dt=0.25):
        c.fixture_ids = [fx.fid]
        c.sync_to_beat = False
        c.speed = 1.0
        c._running = True
        c._elapsed = 0.0
        for _ in range(frames):
            c.write({1: self.u}, [fx], dt)

    def test_colorwheel_gets_blue_slot(self):
        """Farbrad-Geraet mit paint_color=Blau -> color-Kanal = Blau-Slot (20..29 -> 24)."""
        fx = _Fx(1, 1, 10)                 # intensity@10, color@11
        self._map = {1: _colorwheel_chans()}
        c = Carousel("Pulse"); c.pattern = CarouselPattern.PULSE
        c.paint_color = True
        c.color_r, c.color_g, c.color_b = 0, 0, 255   # blau
        self._run(c, fx)
        self.assertEqual(self.u.get_channel(11), 24, "color-Kanal = Blau-Slot-Mittelwert")

    def test_rgb_fixture_still_writes_rgb(self):
        """RGB-Geraet mit paint_color=Blau -> color_r/g/b wie bisher."""
        fx = _Fx(2, 1, 10)                 # intensity@10, r@11, g@12, b@13
        self._map = {2: _RGB_CHANS}
        c = Carousel("Pulse"); c.pattern = CarouselPattern.PULSE
        c.paint_color = True
        c.color_r, c.color_g, c.color_b = 0, 0, 255   # blau
        self._run(c, fx)
        self.assertEqual(self.u.get_channel(13), 255)  # blau auf color_b
        self.assertEqual(self.u.get_channel(11), 0)
        self.assertEqual(self.u.get_channel(12), 0)

    def test_colorwheel_without_paint_color_untouched(self):
        """Ohne paint_color bleibt der Farbrad-Kanal unberuehrt (kombinierbar)."""
        fx = _Fx(1, 1, 10)
        self._map = {1: _colorwheel_chans()}
        self.u.set_channel(11, 14)         # vorab Gruen-Slot (z. B. aus Programmer)
        c = Carousel("Pulse"); c.pattern = CarouselPattern.PULSE
        c.paint_color = False
        c.color_r, c.color_g, c.color_b = 255, 0, 0
        self._run(c, fx)
        self.assertEqual(self.u.get_channel(11), 14, "Farbrad bleibt unberuehrt")


if __name__ == "__main__":
    unittest.main()
