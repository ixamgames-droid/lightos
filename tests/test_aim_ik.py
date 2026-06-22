"""IK-Solver fuers Ausrichten (src/core/stage/aim.py).

Kernforderung: zwei Moving Heads an verschiedenen Standorten brauchen
verschiedene Pan/Tilt-Werte, um denselben Punkt zu treffen. Plus Strahl-
Rekonstruktion (gleiche Abbildung wie Visualizer) als echte Korrektheitspruefung.
"""
import math
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.stage.aim import (
    aim_pan_tilt, aim_orientation, _mount_matrix,
)


def _beam_from_pan_tilt(pan, tilt, rot_deg=(0.0, 0.0, 0.0),
                        pan_range=360.0, tilt_range=180.0, pz=128.0, tz=128.0):
    """Welt-Strahlrichtung aus Pan/Tilt-DMX + Montage rekonstruieren
    (identische Abbildung wie Solver/Visualizer; bereichs-/nullpunkt-fähig)."""
    pan_rad = (pan - pz) / 128.0 * (pan_range * math.pi / 360.0)
    tilt_rad = (tilt - tz) / 128.0 * (tilt_range * math.pi / 360.0)
    st, ct = math.sin(tilt_rad), math.cos(tilt_rad)
    sp, cp = math.sin(pan_rad), math.cos(pan_rad)
    local = (-st * sp, -ct, -st * cp)
    R = _mount_matrix(rot_deg[0], rot_deg[1], rot_deg[2])
    wx = R[0][0]*local[0] + R[0][1]*local[1] + R[0][2]*local[2]
    wy = R[1][0]*local[0] + R[1][1]*local[1] + R[1][2]*local[2]
    wz = R[2][0]*local[0] + R[2][1]*local[1] + R[2][2]*local[2]
    return (wx, wy, wz)


def _norm(v):
    L = math.sqrt(sum(c*c for c in v)) or 1.0
    return tuple(c/L for c in v)


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


class AimPanTiltTest(unittest.TestCase):
    def test_straight_down_is_center_tilt(self):
        _, tilt = aim_pan_tilt((0, 5, 0), (0, 0, 0), (0, 0, 0))
        self.assertEqual(tilt, 128)          # Strahl gerade runter = Ruhe-Tilt

    def test_horizontal_front_full_tilt(self):
        pan, tilt = aim_pan_tilt((0, 5, 0), (0, 5, -5), (0, 0, 0))
        self.assertEqual(tilt, 255)          # horizontal = Tilt-Anschlag
        self.assertEqual(pan, 128)           # nach vorne (-Z) = Pan-Mitte

    def test_two_heads_different_pan_same_target(self):
        """Kernforderung: zwei Koepfe links/rechts brauchen verschiedenes Pan."""
        target = (0, 0, 0)
        p_left, _ = aim_pan_tilt((-3, 5, 0), target, (0, 0, 0))
        p_right, _ = aim_pan_tilt((3, 5, 0), target, (0, 0, 0))
        # exakt das Target ist hier (0,0,0); leichte Höhe -> Pan zeigt nach innen
        self.assertNotEqual(p_left, p_right)

    def test_beam_reconstruction_hits_target_downward(self):
        """Fuer Ziele unterhalb des Kopfes muss der rekonstruierte Strahl auf
        das Ziel zeigen (dot > 0.999)."""
        cases = [
            ((0, 6, 0), (2, 0, 1)),
            ((-4, 5, -2), (1, 0, 3)),
            ((3, 8, 3), (-2, 0, -1)),
        ]
        for pos, target in cases:
            pan, tilt = aim_pan_tilt(pos, target, (0, 0, 0))
            beam = _norm(_beam_from_pan_tilt(pan, tilt))
            want = _norm(tuple(t - p for t, p in zip(target, pos)))
            self.assertGreater(_dot(beam, want), 0.999,
                               f"pos={pos} target={target} pan={pan} tilt={tilt}")

    def test_beam_reconstruction_with_mount_rotation(self):
        """Bei verdrehter Montage muss Pan/Tilt das kompensieren."""
        pos, target, rot = (0, 6, 0), (3, 0, 2), (0.0, 45.0, 0.0)
        pan, tilt = aim_pan_tilt(pos, target, rot)
        beam = _norm(_beam_from_pan_tilt(pan, tilt, rot))
        want = _norm(tuple(t - p for t, p in zip(target, pos)))
        self.assertGreater(_dot(beam, want), 0.999)

    def test_ranged_540_270_hits_target(self):
        """Mit echtem Geräte-Bereich (540/270) muss der Strahl bei gleicher
        Abbildung exakt auf das Ziel zeigen."""
        for pos, target in [((0, 6, 0), (2, 0, 1)), ((-3, 5, 1), (1, 0, -2))]:
            pan, tilt = aim_pan_tilt(pos, target, (0, 0, 0),
                                     pan_range_deg=540, tilt_range_deg=270)
            beam = _norm(_beam_from_pan_tilt(pan, tilt, (0, 0, 0),
                                             pan_range=540, tilt_range=270))
            want = _norm(tuple(t - p for t, p in zip(target, pos)))
            self.assertGreater(_dot(beam, want), 0.999,
                               f"pos={pos} target={target} pan={pan} tilt={tilt}")

    def test_zero_offset_respected(self):
        """pos==target gibt den konfigurierten Nullpunkt zurück."""
        self.assertEqual(aim_pan_tilt((0, 0, 0), (0, 0, 0), (0, 0, 0),
                                      pan_zero_dmx=100, tilt_zero_dmx=90), (100, 90))

    def test_invert_pan_flips(self):
        p0, _ = aim_pan_tilt((-3, 5, 0), (0, 0, 0), (0, 0, 0))
        p1, _ = aim_pan_tilt((-3, 5, 0), (0, 0, 0), (0, 0, 0), invert_pan=True)
        self.assertEqual(p1, 255 - p0)

    def test_same_pos_target_is_rest(self):
        self.assertEqual(aim_pan_tilt((1, 1, 1), (1, 1, 1), (0, 0, 0)), (128, 128))


class AimOrientationTest(unittest.TestCase):
    def _beam_after(self, rot_deg):
        R = _mount_matrix(*rot_deg)
        # Ruhe-Strahl (0,-1,0) -> Welt
        return _norm((-R[0][1], -R[1][1], -R[2][1]))

    def test_straight_down_no_rotation(self):
        rot = aim_orientation((0, 5, 0), (0, 0, 0))
        for a in rot:
            self.assertAlmostEqual(a, 0.0, places=4)

    def test_points_up_for_ceiling_target(self):
        """Boden-PAR an die Decke: Strahl muss nach oben (+Y) zeigen."""
        rot = aim_orientation((0, 0, 0), (0, 5, 0))
        beam = self._beam_after(rot)
        self.assertGreater(_dot(beam, (0, 1, 0)), 0.999)

    def test_orientation_roundtrip_hits_target(self):
        cases = [
            ((0, 6, 0), (3, 0, 2)),
            ((0, 1, 0), (4, 6, -2)),     # nach schraeg oben
            ((-2, 5, 1), (2, 0, -3)),
        ]
        for pos, target in cases:
            rot = aim_orientation(pos, target)
            beam = self._beam_after(rot)
            want = _norm(tuple(t - p for t, p in zip(target, pos)))
            self.assertGreater(_dot(beam, want), 0.999,
                               f"pos={pos} target={target} rot={rot}")


if __name__ == "__main__":
    unittest.main()
