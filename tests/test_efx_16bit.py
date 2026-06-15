"""T-9: EFX schreibt Pan/Tilt 16-bit (Fine-Kanaele), wenn das Geraet sie hat.

Die EFX-Engine rechnet Pan/Tilt als Float; bei ``bit16`` (Default an) wandert die
Sub-Step-Praezision in pan_fine/tilt_fine -> geschmeidige Moving-Head-Bewegung.
coarse bleibt bit-identisch zur 8-bit-Ausgabe (Truncation), Geraete ohne
Fine-Kanal ignorieren die zusaetzlichen Werte. Invert/Swap koppeln das 16-bit-Paar.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.dmx.universe import Universe
from src.core.engine.efx import EfxInstance, EfxFixture, EfxAlgorithm


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0
        self.highlight_value = 255
        self.ranges = []


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 4

    def __init__(self, fid=1, universe=1, address=1, **flags):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.invert_pan = flags.get("invert_pan", False)
        self.invert_tilt = flags.get("invert_tilt", False)
        self.swap_pan_tilt = flags.get("swap_pan_tilt", False)


# pan@1, pan_fine@2, tilt@3, tilt_fine@4
MH16 = [_Ch("pan", 1), _Ch("pan_fine", 2), _Ch("tilt", 3), _Ch("tilt_fine", 4)]


class Efx16BitWriteTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: MH16

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _build(self, bit16):
        efx = EfxInstance(name="t")
        efx.algorithm = EfxAlgorithm.CIRCLE
        efx.fixtures = [EfxFixture(fid=1)]
        efx.width = efx.height = 100.0
        efx.x_offset = efx.y_offset = 128.0
        efx.bit16 = bit16
        efx.speed_hz = 0.0     # Phase einfrieren -> deterministisch
        efx._phase = 0.05      # Position mit Nachkommaanteil
        efx._running = True
        return efx

    def _write(self, efx, **flags):
        uni = Universe(1)
        efx.write({1: uni}, [_Fx(address=1, **flags)], dt=0.1)
        return uni

    def test_fine_channels_written_when_bit16(self):
        uni = self._write(self._build(bit16=True))
        self.assertTrue(uni.get_channel(2) > 0 or uni.get_channel(4) > 0,
                        "kein Fine-Wert ausgegeben")

    def test_fine_channels_zero_when_bit16_off(self):
        uni = self._write(self._build(bit16=False))
        self.assertEqual(uni.get_channel(2), 0)
        self.assertEqual(uni.get_channel(4), 0)

    def test_coarse_identical_with_and_without_bit16(self):
        on = self._write(self._build(bit16=True))
        off = self._write(self._build(bit16=False))
        self.assertEqual(on.get_channel(1), off.get_channel(1))   # pan coarse
        self.assertEqual(on.get_channel(3), off.get_channel(3))   # tilt coarse

    def test_invert_pan_couples_16bit_pair(self):
        plain = self._write(self._build(bit16=True))
        inv = self._write(self._build(bit16=True), invert_pan=True)
        v_plain = (plain.get_channel(1) << 8) | plain.get_channel(2)
        v_inv = (inv.get_channel(1) << 8) | inv.get_channel(2)
        self.assertEqual(v_inv, 65535 - v_plain)


class Split16Test(unittest.TestCase):
    def test_known_values(self):
        self.assertEqual(EfxInstance._split16(0.0), (0, 0))
        self.assertEqual(EfxInstance._split16(128.0), (128, 0))
        self.assertEqual(EfxInstance._split16(255.0), (255, 0))
        self.assertEqual(EfxInstance._split16(128.5), (128, 128))  # 0.5*256

    def test_coarse_equals_int_truncation(self):
        for v in (0.0, 1.9, 100.3, 200.999, 254.7, 255.0):
            self.assertEqual(EfxInstance._split16(v)[0], int(v))


class Efx16BitPersistenceTest(unittest.TestCase):
    def test_roundtrip(self):
        e = EfxInstance(name="m")
        e.bit16 = False
        self.assertFalse(EfxInstance.from_dict(e.to_dict()).bit16)

    def test_legacy_dict_defaults_true(self):
        e = EfxInstance.from_dict({"name": "Old", "algorithm": "Circle"})
        self.assertTrue(e.bit16)

    def test_set_param_get_param_action(self):
        e = EfxInstance(name="m")
        self.assertTrue(e.set_param("bit16", False))
        self.assertFalse(e.bit16)
        self.assertEqual(e.get_param("bit16"), False)
        self.assertTrue(e.do_action("toggle_bit16"))
        self.assertTrue(e.bit16)


if __name__ == "__main__":
    unittest.main()
