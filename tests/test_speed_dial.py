"""SPD-01/02/03/04: Speed-Dial-Erweiterungen.

- Multiplikator-Modus (Faktor statt absoluter BPM),
- optionale Invertierung (höher = langsamer),
- mehrere Ziele (function_ids),
- Sync (Phase aller Ziele angleichen),
- Persistenz inkl. Rückwärtskompatibilität.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm
from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget

_app = QApplication.instance() or QApplication([])


class _Base(unittest.TestCase):
    def setUp(self):
        self.fm = get_state().function_manager
        self.fm.stop_all()
        self.m = RgbMatrixInstance(name="A", cols=2, rows=1,
                                   algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2])
        self.fm.add(self.m)
        self.fid = self.m.id

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m.id)

    def _dial(self):
        d = VCSpeedDial()
        d.target_mode = SpeedTarget.FUNCTION
        d.function_id = self.fid
        return d


class SpeedFactorTest(_Base):
    def test_bpm_mode(self):
        d = self._dial()
        d.bpm = 240                       # 240/120 = 2.0
        self.assertAlmostEqual(self.m.matrix_speed, 2.0, places=3)

    def test_multiplier_mode(self):
        d = self._dial()
        d.multiplier_mode = True
        d.mult = 2.0
        self.assertAlmostEqual(self.m.matrix_speed, 2.0, places=3)
        d.mult = 0.5
        self.assertAlmostEqual(self.m.matrix_speed, 0.5, places=3)

    def test_invert_flips_direction(self):
        d = self._dial()
        d.bpm = 200
        s_low = self.m.matrix_speed
        d.bpm = 400
        s_high = self.m.matrix_speed
        self.assertGreater(s_high, s_low)     # normal: höher = schneller
        d.invert = True
        d.bpm = 200
        si_for_low = self.m.matrix_speed
        d.bpm = 400
        si_for_high = self.m.matrix_speed
        self.assertLess(si_for_high, si_for_low)   # invertiert: höher = langsamer


class MultiTargetTest(_Base):
    def test_multiple_targets(self):
        m2 = RgbMatrixInstance(name="B", cols=2, rows=1,
                               algorithm=RgbAlgorithm.CHASE, fixture_grid=[3, 4])
        self.fm.add(m2)
        try:
            d = self._dial()
            d.function_ids = [m2.id]
            d.multiplier_mode = True
            d.mult = 3.0
            self.assertAlmostEqual(self.m.matrix_speed, 3.0, places=3)
            self.assertAlmostEqual(m2.matrix_speed, 3.0, places=3)
        finally:
            self.fm.remove(m2.id)


class SyncTest(_Base):
    def test_sync_resets_phase(self):
        self.m._step = 5.0
        d = self._dial()
        n = d.sync()
        self.assertEqual(n, 1)
        self.assertEqual(self.m._step, 0.0)

    def test_sync_multi_targets(self):
        m2 = RgbMatrixInstance(name="B", cols=2, rows=1,
                               algorithm=RgbAlgorithm.CHASE, fixture_grid=[3, 4])
        self.fm.add(m2)
        try:
            self.m._step = 3.0
            m2._step = 7.0
            d = self._dial()
            d.function_ids = [m2.id]
            self.assertEqual(d.sync(), 2)
            self.assertEqual(self.m._step, 0.0)
            self.assertEqual(m2._step, 0.0)
        finally:
            self.fm.remove(m2.id)


class SerializeTest(_Base):
    def test_round_trip(self):
        d = self._dial()
        d.multiplier_mode = True
        d._mult = 2.5
        d.invert = True
        d.function_ids = [7, 9]
        d2 = VCSpeedDial()
        d2.apply_dict(d.to_dict())
        self.assertTrue(d2.multiplier_mode)
        self.assertTrue(d2.invert)
        self.assertAlmostEqual(d2._mult, 2.5)
        self.assertEqual(d2.function_ids, [7, 9])
        self.assertEqual(d2.target_mode, SpeedTarget.FUNCTION)

    def test_backward_compat(self):
        d = VCSpeedDial()
        d.apply_dict({"bpm": 150})            # alte Show ohne neue Felder
        self.assertFalse(d.multiplier_mode)
        self.assertFalse(d.invert)
        self.assertEqual(d.function_ids, [])


if __name__ == "__main__":
    unittest.main()
