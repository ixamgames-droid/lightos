"""Verifikation: EFX CIRCLE fährt einen echten Kreis, EIGHT eine echte Acht —
und BEIDE Moving Heads fahren beim Kreis einen Kreis (kein Head fährt eine Acht).

Hintergrund: David sah auf der VC, dass beim „Kreis" ein Kopf trotzdem eine Acht
fuhr. Dieser Test grenzt ein, ob die Engine-Mathematik daran schuld ist
(Ergebnis: nein — siehe unten), damit die Ursache auf Settings/Leftover-Effekte
eingegrenzt werden kann.
"""
import math
import unittest

from src.core.engine.efx import EfxInstance, EfxFixture, EfxAlgorithm


def _radius(pan, tilt, cx=128, cy=128):
    return math.hypot(pan - cx, tilt - cy)


class CircleShapeTest(unittest.TestCase):
    def _efx(self, algo, **kw):
        e = EfxInstance("e")
        e.algorithm = algo
        e.width = e.height = 100.0      # hw = hh = 50
        e.x_offset = e.y_offset = 128.0
        for k, v in kw.items():
            setattr(e, k, v)
        return e

    def test_circle_is_constant_radius(self):
        e = self._efx(EfxAlgorithm.CIRCLE)
        radii = [_radius(*e._calc(p / 72.0)) for p in range(72)]
        # Kreis: Radius konstant (~50), nur int-Rundung als Abweichung.
        self.assertAlmostEqual(min(radii), 50, delta=2)
        self.assertAlmostEqual(max(radii), 50, delta=2)
        self.assertLess(max(radii) - min(radii), 3.0)

    def test_eight_radius_varies_and_self_intersects(self):
        e = self._efx(EfxAlgorithm.EIGHT)
        radii = [_radius(*e._calc(p / 72.0)) for p in range(72)]
        self.assertGreater(max(radii) - min(radii), 15.0)   # klar keine Kreislinie
        # Acht kreuzt sich im Zentrum: bei Phase 0 und 0.5 ~ Mitte.
        self.assertLess(_radius(*e._calc(0.0)), 3)
        self.assertLess(_radius(*e._calc(0.5)), 3)

    def test_both_heads_trace_circle_even_with_default_spread(self):
        # Zwei Köpfe, Default-spread (1.0 = Fan) UND mit Mirror: trotzdem fährt
        # JEDER Kopf einen Kreis (konstanter Radius) — kein Kopf fährt eine Acht.
        for mirror in (False, True):
            e = self._efx(EfxAlgorithm.CIRCLE, spread=1.0, mirror=mirror)
            e.fixtures = [EfxFixture(fid=5), EfxFixture(fid=6)]
            radii = {5: [], 6: []}
            for k in range(72):
                e._phase = k / 72.0
                vals = e._values()
                for fid in (5, 6):
                    radii[fid].append(_radius(vals[fid]["pan"], vals[fid]["tilt"]))
            for fid in (5, 6):
                self.assertLess(max(radii[fid]) - min(radii[fid]), 4.0,
                                f"Kopf {fid} (mirror={mirror}) fährt keinen sauberen Kreis")


if __name__ == "__main__":
    unittest.main()
