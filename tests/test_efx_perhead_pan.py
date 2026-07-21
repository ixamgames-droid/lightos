"""FM-16b: EFX faehrt bei Mehrkopf-Movern eine pro-Kopf-PAN+TILT-Welle.

Vor FM-16b bekam nur ein Dual-Tilt-Spider (>=2 Tilt, 0 Pan) eine pro-Kopf-Welle
(tilt-only, `_head_pan_tilts` hiess frueher `_spider_head_tilts`); ein Voll-Mover
mit pro-Kopf-Pan+Tilt (Hydrabeam/MOVBAR4) bekam nur Kopf-0-Pan/Tilt, alle weiteren
Koepfe spiegelten Kopf 0 (via `resolve_attr_channels`-Fallback) -> alle 4 Koepfe
bewegten sich identisch. Jetzt fahren die N Koepfe die Figur phasenversetzt
(``(k/head_count)*head_spread``) -> echter Pan+Tilt-Chase ueber die Koepfe.

Deterministisch (Phase eingefroren, ``speed_hz=0``) im Stil von test_efx_16bit.
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
    channel_count = 16

    def __init__(self, fid=1, universe=1, address=1, **flags):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.invert_pan = flags.get("invert_pan", False)
        self.invert_tilt = flags.get("invert_tilt", False)
        self.swap_pan_tilt = flags.get("swap_pan_tilt", False)


# 4-Kopf-Mover: je Kopf pan/pan_fine/tilt/tilt_fine (16 Kanaele). Vorkommens-Keys:
# Kopf0 = pan/tilt (bare, CH1/CH3), Kopf k = pan#k/tilt#k (CH 5/7, 9/11, 13/15).
def _mover4():
    chans, num = [], 1
    for _h in range(4):
        for a in ("pan", "pan_fine", "tilt", "tilt_fine"):
            chans.append(_Ch(a, num)); num += 1
    return chans


MOVER4 = _mover4()
# DMX-Kanaele je Kopf (1-basiert): (pan, tilt) coarse
HEAD_PAN = (1, 5, 9, 13)
HEAD_TILT = (3, 7, 11, 15)
HEAD_PAN_FINE = (2, 6, 10, 14)
HEAD_TILT_FINE = (4, 8, 12, 16)


def _clampi(v):
    return int(max(0.0, min(255.0, v)))


class _MoverBase(unittest.TestCase):
    CHANS = MOVER4

    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: self.CHANS

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _build(self, head_spread=1.0, bit16=True):
        efx = EfxInstance(name="t")
        efx.algorithm = EfxAlgorithm.CIRCLE
        efx.fixtures = [EfxFixture(fid=1)]
        efx.width = efx.height = 200.0
        efx.x_offset = efx.y_offset = 128.0
        efx.head_spread = head_spread
        efx.bit16 = bit16
        efx.speed_hz = 0.0     # Phase einfrieren -> deterministisch
        efx._phase = 0.05      # Position mit Nachkommaanteil
        efx._running = True
        return efx

    def _write(self, efx, **flags):
        uni = Universe(1)
        efx.write({1: uni}, [_Fx(address=1, **flags)], dt=0.1)
        return uni


class PerHeadPanWaveTest(_MoverBase):
    def test_heads_phased_not_identical(self):
        uni = self._write(self._build(head_spread=1.0))
        pans = [uni.get_channel(c) for c in HEAD_PAN]
        tilts = [uni.get_channel(c) for c in HEAD_TILT]
        self.assertGreater(len(set(pans)), 1,
                           f"Pan-Koepfe alle gleich (keine Welle): {pans}")
        self.assertGreater(len(set(tilts)), 1,
                           f"Tilt-Koepfe alle gleich: {tilts}")

    def test_head1_pan_matches_phase_offset(self):
        # Kopf 1 faehrt exakt die Figur bei phase = base + (1/4)*head_spread.
        efx = self._build(head_spread=1.0)
        uni = self._write(efx)
        base = 0.05                          # _fixture_phase(0,1,fx) = _phase
        exp_pan, exp_tilt = efx._calc((base + 0.25) % 1.0, efx.x_offset, efx.y_offset)
        self.assertEqual(uni.get_channel(5), _clampi(exp_pan))   # pan#1 coarse
        self.assertEqual(uni.get_channel(7), _clampi(exp_tilt))  # tilt#1 coarse

    def test_head_spread_zero_all_heads_identical(self):
        # head_spread=0 kollabiert die Welle -> alle Koepfe = Kopf 0 (Back-Compat).
        uni = self._write(self._build(head_spread=0.0))
        self.assertEqual(len({uni.get_channel(c) for c in HEAD_PAN}), 1)
        self.assertEqual(len({uni.get_channel(c) for c in HEAD_TILT}), 1)
        # ... und identisch mit Kopf 0.
        self.assertEqual(uni.get_channel(5), uni.get_channel(1))
        self.assertEqual(uni.get_channel(7), uni.get_channel(3))

    def test_random_heads_decorrelate_pan(self):
        efx = self._build(head_spread=1.0)
        efx.algorithm = EfxAlgorithm.RANDOM
        efx._rand_progress = 0.3
        uni = self._write(efx)
        pans = [uni.get_channel(c) for c in HEAD_PAN]
        self.assertGreater(len(set(pans)), 1,
                           f"RANDOM-Koepfe pan-korreliert: {pans}")

    def test_random_counter_head_spread_zero_synchronized(self):
        # Review-Fund (MEDIUM): RANDOM + counter_rotate + head_spread=0 -> alle
        # Koepfe synchron. Gegenlauf ist GERAETE-weit (i%2), nicht pro Kopf (k%2);
        # frueher kippte k=1 (ungerade) die Bahn -> Koepfe liefen bei hs=0 ausein-
        # ander. Ein Fixture (i=0) -> kein Geraete-Gegenlauf -> alle identisch.
        efx = self._build(head_spread=0.0)
        efx.algorithm = EfxAlgorithm.RANDOM
        efx.counter_rotate = True
        efx._rand_progress = 5.0
        uni = self._write(efx)
        self.assertEqual(len({uni.get_channel(c) for c in HEAD_PAN}), 1,
                         "RANDOM+counter+hs=0: Pan-Koepfe nicht synchron")
        self.assertEqual(len({uni.get_channel(c) for c in HEAD_TILT}), 1,
                         "RANDOM+counter+hs=0: Tilt-Koepfe nicht synchron")

    def test_swap_exchanges_perhead_axes(self):
        # swap_pan_tilt auf Voll-Mover: pan#k-Kanal bekommt den Tilt-Wert, tilt#k
        # den Pan-Wert (symmetrisch, exakt wie Kopf 0). bit16=False fuer klaren
        # Byte-Vergleich. Kopf 1: pan#1=CH5, tilt#1=CH7.
        plain = self._write(self._build(head_spread=1.0, bit16=False))
        swapped = self._write(self._build(head_spread=1.0, bit16=False),
                              swap_pan_tilt=True)
        self.assertEqual(swapped.get_channel(5), plain.get_channel(7))  # pan#1 <- tilt
        self.assertEqual(swapped.get_channel(7), plain.get_channel(5))  # tilt#1 <- pan


class PerHeadBit16Test(_MoverBase):
    def test_fine_written_per_head_when_bit16(self):
        efx = self._build(head_spread=1.0, bit16=True)
        uni = self._write(efx)
        # Kopf 1 rekonstruiert 16-bit-Pan exakt aus (coarse<<8)|fine.
        exp_pan, _ = efx._calc((0.05 + 0.25) % 1.0, efx.x_offset, efx.y_offset)
        combined = (uni.get_channel(5) << 8) | uni.get_channel(6)
        self.assertEqual(combined, int(max(0.0, min(255.0, exp_pan)) * 256.0))

    def test_fine_zero_per_head_when_bit16_off(self):
        uni = self._write(self._build(head_spread=1.0, bit16=False))
        for c in HEAD_PAN_FINE + HEAD_TILT_FINE:
            self.assertEqual(uni.get_channel(c), 0, f"Fine CH{c} != 0 bei bit16=off")

    def test_invert_pan_couples_perhead_16bit(self):
        plain = self._write(self._build(head_spread=1.0, bit16=True))
        inv = self._write(self._build(head_spread=1.0, bit16=True), invert_pan=True)
        # Kopf 1 (CH5/CH6): invert koppelt das ganze 16-bit-Paar, nicht nur Kopf 0.
        v_plain = (plain.get_channel(5) << 8) | plain.get_channel(6)
        v_inv = (inv.get_channel(5) << 8) | inv.get_channel(6)
        self.assertEqual(v_inv, 65535 - v_plain)


class SpiderRegressionTest(_MoverBase):
    # Dual-Tilt-Spider: 2 Tilt-Koepfe, KEIN Pan -> muss tilt-only bleiben.
    CHANS = [_Ch("tilt", 1), _Ch("tilt_fine", 2), _Ch("tilt", 3), _Ch("tilt_fine", 4)]

    def test_spider_tilt_heads_still_phased(self):
        uni = self._write(self._build(head_spread=1.0))
        t0, t1 = uni.get_channel(1), uni.get_channel(3)
        self.assertNotEqual(t0, t1, "Spider-Tilt-Koepfe nicht mehr phasenversetzt")

    def test_spider_tilt_wave_matches_calc(self):
        # Kopf 1 (CH3) = Tilt-Komponente bei phase + 0.5*head_spread (unveraendert).
        efx = self._build(head_spread=1.0)
        uni = self._write(efx)
        _p, exp_t1 = efx._calc((0.05 + 0.5) % 1.0, efx.x_offset, efx.y_offset)
        self.assertEqual(uni.get_channel(3), _clampi(exp_t1))

    def test_swap_pan_tilt_does_not_collapse_wave(self):
        # Review-Fund (HIGH): swap_pan_tilt=True auf einem reinen Dual-Tilt-Spider
        # (0 Pan) darf die pro-Kopf-Welle NICHT abreissen. Frueher schob der Swap
        # auf dem tilt-only Teil-Dict den Tilt-Wert in einen (nicht existenten)
        # pan#k-Key und LOESCHTE tilt#k -> Kopf k fiel auf Kopf 0 zurueck. Jetzt
        # werden beide Achsen gepackt -> swap ist symmetrisch, tilt#k ueberlebt.
        uni = self._write(self._build(head_spread=1.0), swap_pan_tilt=True)
        t0, t1 = uni.get_channel(1), uni.get_channel(3)
        self.assertNotEqual(t0, t1, "swap_pan_tilt liess die Kopf-Welle kollabieren")


class PerHeadPersistenceTest(_MoverBase):
    def test_roundtrip_reproduces_perhead_output(self):
        efx = self._build(head_spread=0.5, bit16=True)
        efx.phase_mode = "offset"
        efx.counter_rotate = True
        before = self._write(efx)
        efx2 = EfxInstance.from_dict(efx.to_dict())
        efx2._phase = 0.05          # Laufzeit-Phase ist nicht serialisiert
        efx2._running = True
        after = Universe(1)
        efx2.write({1: after}, [_Fx(address=1)], dt=0.1)
        for c in range(1, 17):
            self.assertEqual(before.get_channel(c), after.get_channel(c),
                             f"CH{c} weicht nach to_dict/from_dict ab")


if __name__ == "__main__":
    unittest.main()
