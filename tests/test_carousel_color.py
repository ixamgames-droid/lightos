"""Regression: Carousel (Pulse/Wave) erzwingt KEINE Farbe mehr.

Frueher schrieb das Carousel bei jedem Pattern color_r/g/b (Default 255 = weiss)
und "besass" damit die Farbkanaele -> die im Programmer gewaehlte Farbe wurde
blockiert ("Pulse macht alles weiss"). Jetzt ist das Faerben opt-in
(``paint_color``, Default aus): Pulse/Wave modulieren nur die Helligkeit, die
Farbkanaele bleiben unberuehrt und kommen aus der Ebene darunter.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.dmx.universe import Universe
from src.core.engine.carousel import Carousel, CarouselPattern


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num


class _Fx:
    def __init__(self, fid, universe, address):
        self.fid = fid
        self.universe = universe
        self.address = address


_CHANS = [_Ch("intensity", 1), _Ch("color_r", 2), _Ch("color_g", 3), _Ch("color_b", 4)]


class CarouselColorTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _CHANS
        self.fx = _Fx(1, 1, 10)            # intensity@10, r@11, g@12, b@13
        self.u = Universe(1)

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _run(self, c, frames=3, dt=0.25):
        c.fixture_ids = [1]
        c.sync_to_beat = False            # frei laufend, keine BPM-Abhaengigkeit
        c.speed = 1.0
        c._running = True
        c._elapsed = 0.0
        for _ in range(frames):
            c.write({1: self.u}, [self.fx], dt)

    def test_pulse_keeps_selected_color(self):
        c = Carousel("Pulse"); c.pattern = CarouselPattern.PULSE
        # "Gewaehlte Farbe" (z. B. aus dem Programmer) = Rot auf den Farbkanaelen.
        self.u.set_channel(11, 255); self.u.set_channel(12, 0); self.u.set_channel(13, 0)
        self._run(c)
        # Carousel hat die Farbe NICHT auf weiss ueberschrieben -> bleibt rot.
        self.assertEqual(self.u.get_channel(11), 255)
        self.assertEqual(self.u.get_channel(12), 0)
        self.assertEqual(self.u.get_channel(13), 0)

    def test_wave_keeps_selected_color(self):
        c = Carousel("Wave"); c.pattern = CarouselPattern.WAVE
        self.u.set_channel(12, 200)       # gewaehltes Gruen
        self._run(c)
        self.assertEqual(self.u.get_channel(12), 200)
        self.assertEqual(self.u.get_channel(11), 0)
        self.assertEqual(self.u.get_channel(13), 0)

    def test_paint_color_opt_in_still_writes_color(self):
        c = Carousel("Pulse"); c.pattern = CarouselPattern.PULSE
        c.paint_color = True              # bewusste Eigenfarbe
        c.color_r, c.color_g, c.color_b = 0, 0, 255   # blau
        self._run(c)
        self.assertEqual(self.u.get_channel(13), 255)  # blau geschrieben
        self.assertEqual(self.u.get_channel(11), 0)

    def test_paint_color_survives_roundtrip(self):
        c = Carousel("Pulse"); c.paint_color = True
        c2 = Carousel.from_dict(c.to_dict())
        self.assertTrue(c2.paint_color)
        self.assertFalse(Carousel.from_dict(Carousel("x").to_dict()).paint_color)


if __name__ == "__main__":
    unittest.main()
