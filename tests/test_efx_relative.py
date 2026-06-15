"""APC-Probier To-Do #7: relative/additive Moving-Head-Bewegung.

Im Relativ-Modus kreist die EFX-Bewegung um die aktuelle Pan/Tilt-Position jedes
Geräts (beim Start aus dem Programmer geschnappt) statt um die feste Mitte
128/128 — „fahr zur Bühne, dann dort die Acht".
"""
import unittest

from src.core.engine.efx import EfxInstance, EfxFixture, EfxAlgorithm
from src.core.app_state import get_state


class EfxRelativeTest(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self.state.programmer.clear()

    def tearDown(self):
        self.state.programmer.clear()

    def _circle_efx(self, relative):
        e = EfxInstance("rel")
        e.algorithm = EfxAlgorithm.CIRCLE
        e.width = e.height = 100.0       # hw = hh = 50
        e.fixtures = [EfxFixture(fid=1)]
        e.relative = relative
        e._phase = 0.0
        return e

    def test_absolute_centers_on_offset(self):
        e = self._circle_efx(relative=False)
        e.start()
        v = e._values()[1]
        # Phase 0, Circle: x = +hw, y = 0  -> pan = 128+50, tilt = 128
        self.assertEqual(v["pan"], 178)
        self.assertEqual(v["tilt"], 128)
        e.stop()

    def test_relative_centers_on_programmer_position(self):
        self.state.programmer[1] = {"pan": 60, "tilt": 200}
        e = self._circle_efx(relative=True)
        e.start()                         # _on_start schnappt (60, 200)
        v = e._values()[1]
        self.assertEqual(v["pan"], 110)   # 60 + 50
        self.assertEqual(v["tilt"], 200)  # 200 + 0
        e.stop()

    def test_relative_without_position_falls_back_to_offset(self):
        e = self._circle_efx(relative=True)
        e.start()                         # kein Programmer-Eintrag -> feste Mitte
        v = e._values()[1]
        self.assertEqual(v["pan"], 178)
        self.assertEqual(v["tilt"], 128)
        e.stop()

    def test_toggle_action_and_param(self):
        e = self._circle_efx(relative=False)
        self.assertTrue(e.do_action("toggle_relative"))
        self.assertTrue(e.relative)
        self.assertTrue(e.set_param("relative", False))
        self.assertFalse(e.relative)
        self.assertFalse(e.get_param("relative"))
        self.assertIn("relative", {s.key for s in e.list_params()})
        self.assertIn("toggle_relative", dict(e.list_actions()))

    def test_serialization_roundtrip(self):
        e = self._circle_efx(relative=True)
        e2 = EfxInstance.from_dict(e.to_dict())
        self.assertTrue(e2.relative)


if __name__ == "__main__":
    unittest.main()
