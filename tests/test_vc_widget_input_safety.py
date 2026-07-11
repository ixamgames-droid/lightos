"""VC-Widget-Input-Safety (adversariale Bug-Jagd Runde 2, 2026-07-09).

- VCButton.apply_dict castet function_id/snapshot_index zu int -> kein `executors[float]`-
  TypeError-Crash bei TOGGLE/FLASH bzw. still-fehlschlagender Snapshot-Button.
- VCEncoder.wheelEvent respektiert den Run-Input-Lock (Display-only/Touch-Lock) -> nicht
  per Mausrad umgehbar.
- VCXYPad._norm/_pos_to_value crasht nicht mit ZeroDivisionError, wenn das Widget so klein
  ist, dass das um 24px eingerueckte Pad 0 breit/hoch wird.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect, QPoint

_app = QApplication.instance() or QApplication([])


class VCButtonApplyDictCastTest(unittest.TestCase):
    """Echter VCButton (apply_dict ruft super().apply_dict -> braucht echte Instanz)."""

    def _button(self):
        from src.ui.virtualconsole.vc_button import VCButton
        btn = VCButton("T")
        self.addCleanup(lambda: (btn.deleteLater(), _app.processEvents()))
        return btn

    def test_function_id_and_snapshot_index_cast_to_int(self):
        btn = self._button()
        btn.apply_dict({"function_id": 3.0, "snapshot_index": 1.0})
        self.assertIsInstance(btn.function_id, int)
        self.assertEqual(btn.function_id, 3)
        self.assertIsInstance(btn.snapshot_index, int)
        self.assertEqual(btn.snapshot_index, 1)

    def test_none_stays_none(self):
        btn = self._button()
        btn.apply_dict({})
        self.assertIsNone(btn.function_id)
        self.assertIsNone(btn.snapshot_index)


class VCEncoderWheelLockTest(unittest.TestCase):
    def _event(self):
        return SimpleNamespace(accept=lambda: None,
                               angleDelta=lambda: SimpleNamespace(y=lambda: 120))

    def test_wheel_blocked_when_input_locked(self):
        from src.ui.virtualconsole.vc_encoder import VCEncoder
        calls = []
        fake = SimpleNamespace(_edit_mode=False, _run_input_blocked=lambda: True,
                               nudge=lambda v: calls.append(v))
        VCEncoder.wheelEvent(fake, self._event())
        self.assertEqual(calls, [])   # gesperrt -> kein nudge

    def test_wheel_works_when_unlocked(self):
        from src.ui.virtualconsole.vc_encoder import VCEncoder
        calls = []
        fake = SimpleNamespace(_edit_mode=False, _run_input_blocked=lambda: False,
                               nudge=lambda v: calls.append(v))
        VCEncoder.wheelEvent(fake, self._event())
        self.assertEqual(calls, [1.0])


class VCXYPadZeroSizeTest(unittest.TestCase):
    def test_norm_no_zerodivision_on_zero_size_pad(self):
        from src.ui.virtualconsole.vc_xypad import VCXYPad
        fake = SimpleNamespace(_pad_rect=lambda: QRect(24, 24, 0, 0))  # width/height 0
        pan, tilt = VCXYPad._norm(fake, QPoint(30, 30))
        self.assertTrue(0.0 <= pan <= 1.0)
        self.assertTrue(0.0 <= tilt <= 1.0)


if __name__ == "__main__":
    unittest.main()
