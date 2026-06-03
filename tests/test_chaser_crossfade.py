"""EE-01: Der Chaser muss zwischen seinen Schritten weich ueberblenden.

Vor dem Fix sprang der Chaser hart auf die naechste Farbe (step.fade_in wurde
nie an die Scene durchgereicht, und der Per-Frame-Clear machte ein Snapshotten
des Vorgaengerwerts in der Scene unmoeglich). Jetzt steuert der Chaser die
Blende selbst.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx.universe import Universe
from src.core.engine.scene import Scene
from src.core.engine.chaser import Chaser, ChaserStep
from src.core.engine.function import RunOrder


class _Fx:
    """Minimales PatchedFixture-Stand-in (Scene nutzt fid/universe/address)."""
    def __init__(self, fid, universe, address):
        self.fid = fid
        self.universe = universe
        self.address = address


def _scene(value: int) -> Scene:
    s = Scene("s")
    s.set_value(1, 1, value)   # fid=1, Kanal-Offset 1 -> DMX-Adresse 1
    return s


class TestChaserCrossfade(unittest.TestCase):
    def setUp(self):
        self.patch = [_Fx(1, 1, 1)]
        self.uni = {1: Universe(1)}
        self.a = _scene(200)
        self.b = _scene(50)
        self.reg = {self.a.id: self.a, self.b.id: self.b}
        self.ch = Chaser("c")
        self.ch.run_order = RunOrder.Loop
        self.ch.steps = [
            ChaserStep(function_id=self.a.id, fade_in=1.0, hold=1.0, fade_out=0.0),
            ChaserStep(function_id=self.b.id, fade_in=1.0, hold=1.0, fade_out=0.0),
        ]

    def _val(self) -> int:
        return self.uni[1].get_channel(1)

    def _frame(self, dt=0.5):
        self.ch.write(self.uni, self.patch, dt, self.reg)

    def test_fades_in_from_zero(self):
        self.ch.start()
        self._frame()                  # t=0 -> noch 0
        self.assertEqual(self._val(), 0)
        self._frame()                  # t=0.5 -> halb (≈100)
        self.assertAlmostEqual(self._val(), 100, delta=2)

    def test_reaches_full_during_hold(self):
        self.ch.start()
        for _ in range(3):             # t laeuft 0 -> 0.5 -> 1.0
            self._frame()
        self.assertEqual(self._val(), 200)

    def test_crossfades_between_steps_not_hard_cut(self):
        self.ch.start()
        # Schritt A bis voll + Hold abfahren -> Advance auf Schritt B
        # Frames: 0.0, 0.5, 1.0(voll), 1.5(hold), 2.0(advance)
        for _ in range(4):
            self._frame()
        self.assertEqual(self._val(), 200)
        self._frame()                  # advance auf B, t=0 -> noch Ausgangswert 200
        self.assertEqual(self._val(), 200)
        self._frame()                  # t=0.5 -> Mischwert zwischen 200 und 50
        mid = self._val()
        self.assertTrue(50 < mid < 200,
                        f"Erwartete weiche Blende, bekam harten Wert {mid}")
        self.assertAlmostEqual(mid, 125, delta=3)

    def test_zero_fade_is_instant(self):
        # fade_in=0 -> sofortiger Sprung (z. B. fuer Strobe gewollt).
        self.ch.steps = [
            ChaserStep(function_id=self.a.id, fade_in=0.0, hold=1.0, fade_out=0.0),
            ChaserStep(function_id=self.b.id, fade_in=0.0, hold=1.0, fade_out=0.0),
        ]
        self.ch.start()
        self._frame()
        self.assertEqual(self._val(), 200)   # sofort voll, kein Einblenden


if __name__ == "__main__":
    unittest.main()
