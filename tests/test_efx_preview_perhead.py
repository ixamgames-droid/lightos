"""FM-16b Preview-Nachtrag: die EFX-Vorschau zeigt Pro-Kopf-Punkte.

Der Render (`efx.write()`) faehrt seit FM-16b eine echte Pro-Kopf-Pan+Tilt-Welle
ueber Mehrkopf-Mover (MOVBAR4/Hydrabeam). Die kleine XY-Vorschau
(`EfxPreviewWidget`) zeigte aber weiter nur EINEN Punkt pro Geraet. Jetzt zeichnet
sie N phasenversetzte Kopf-Punkte — dieselben Positionen, die ans DMX gehen.

Sichert ab:
- `pan_tilt_head_count` (kanonische EFX-Kopfzahl = max(#pan,#tilt)),
- `EfxInstance.head_phase_points` (state-freie Kopf-Welle: Kopf 0 == Render-Kopf-0
  aus `_values`, Koepfe>=1 == `_head_pan_tilts`),
- `EfxPreviewWidget` nimmt fuer Mehrkopf-Mover den Kopf-Punkt-Pfad und fuer
  Single-Head weiter den Ein-Punkt-Pfad.

Deterministisch (Phase eingefroren) im Stil von test_efx_perhead_pan.py.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

import src.core.app_state as A
from src.core.engine.efx import EfxInstance, EfxFixture, EfxAlgorithm
from src.ui.views.efx_view import EfxPreviewWidget


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0
        self.highlight_value = 255
        self.ranges = []


def _mover(heads):
    """heads Koepfe je pan/pan_fine/tilt/tilt_fine (voller Pan+Tilt-Mover)."""
    chans, num = [], 1
    for _h in range(heads):
        for a in ("pan", "pan_fine", "tilt", "tilt_fine"):
            chans.append(_Ch(a, num)); num += 1
    return chans


def _clampi(v):
    return int(max(0.0, min(255.0, v)))


# ── pan_tilt_head_count ──────────────────────────────────────────────────────
class PanTiltHeadCountTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _count(self, chans):
        A.get_channels_for_patched = lambda fx: chans
        return A.pan_tilt_head_count(object())

    def test_four_head_mover(self):
        self.assertEqual(self._count(_mover(4)), 4)

    def test_single_head_mover(self):
        self.assertEqual(self._count(_mover(1)), 1)

    def test_dual_tilt_spider(self):
        # 2 Tilt-Koepfe, KEIN Pan -> Kopfzahl = max(0 Pan, 2 Tilt) = 2.
        chans = [_Ch("tilt", 1), _Ch("tilt_fine", 2),
                 _Ch("tilt", 3), _Ch("tilt_fine", 4)]
        self.assertEqual(self._count(chans), 2)

    def test_no_pan_tilt_is_one(self):
        # Ein Geraet ohne Pan/Tilt (z. B. Dimmer) -> Minimum 1 (nie 0).
        chans = [_Ch("intensity", 1), _Ch("shutter", 2)]
        self.assertEqual(self._count(chans), 1)

    def test_pan_only_counts(self):
        # asymmetrisch: 3 Pan, 1 Tilt -> max = 3.
        chans = [_Ch("pan", 1), _Ch("pan", 2), _Ch("pan", 3), _Ch("tilt", 4)]
        self.assertEqual(self._count(chans), 3)

    def test_exception_defaults_to_one(self):
        def boom(fx):
            raise RuntimeError("no db")
        A.get_channels_for_patched = boom
        self.assertEqual(A.pan_tilt_head_count(object()), 1)


# ── EfxInstance.head_phase_points ────────────────────────────────────────────
class HeadPhasePointsTest(unittest.TestCase):
    def _build(self, alg=EfxAlgorithm.CIRCLE, n=2, hs=0.7,
               mirror=False, counter=False, mode="fan"):
        e = EfxInstance(name="t")
        e.algorithm = alg
        e.fixtures = [EfxFixture(fid=fid) for fid in range(1, n + 1)]
        e.width = e.height = 200.0
        e.x_offset = e.y_offset = 128.0
        e.head_spread = hs
        e.mirror = mirror
        e.counter_rotate = counter
        e.phase_mode = mode
        e.phase_offset_deg = 45.0
        e.speed_hz = 0.0
        e._phase = 0.05
        e._rand_progress = 0.3
        e._running = True
        return e

    def test_returns_head_count_points(self):
        e = self._build(n=1)
        pts = e.head_phase_points(0, 1, e._phase, e._rand_progress, 4)
        self.assertEqual(len(pts), 4)
        for pan, tilt in pts:
            self.assertTrue(0.0 <= pan <= 255.0 and 0.0 <= tilt <= 255.0)

    def test_head_count_clamped_to_one_minimum(self):
        e = self._build(n=1)
        self.assertEqual(len(e.head_phase_points(0, 1, 0.1, 0.0, 0)), 1)
        self.assertEqual(len(e.head_phase_points(0, 1, 0.1, 0.0, 1)), 1)

    def test_heads_phased_not_identical(self):
        e = self._build(n=1, hs=1.0)
        pans = [p for p, _ in e.head_phase_points(0, 1, e._phase, e._rand_progress, 4)]
        self.assertGreater(len(set(pans)), 1, f"Koepfe nicht phasenversetzt: {pans}")

    def test_head_spread_zero_collapses(self):
        e = self._build(n=1, hs=0.0)
        pts = e.head_phase_points(0, 1, e._phase, e._rand_progress, 4)
        self.assertEqual(len({(round(p, 6), round(t, 6)) for p, t in pts}), 1)

    def test_state_free_phase_argument(self):
        # Nutzt die UEBERGEBENE Phase, NICHT self._phase -> andere Phase, andere Lage.
        e = self._build(n=1, hs=0.0)
        a = e.head_phase_points(0, 1, 0.10, 0.0, 1)[0]
        b = e.head_phase_points(0, 1, 0.40, 0.0, 1)[0]
        self.assertNotEqual(a, b)

    def test_head0_matches_values_render(self):
        # Kopf 0 aus head_phase_points == Render-Kopf-0 aus _values (die DMX-Quelle)
        # ueber alle Kombinationen (Deckung Vorschau<->Render, keine Drift).
        for alg in (EfxAlgorithm.CIRCLE, EfxAlgorithm.EIGHT, EfxAlgorithm.RANDOM):
            for mirror in (False, True):
                for counter in (False, True):
                    for mode in ("fan", "sync", "offset"):
                        e = self._build(alg=alg, n=2, hs=0.7, mirror=mirror,
                                        counter=counter, mode=mode)
                        vals = e._values()
                        for i, fx in enumerate(e.fixtures):
                            pan, tilt = e.head_phase_points(
                                i, len(e.fixtures), e._phase,
                                e._rand_progress, 4)[0]
                            v = vals[fx.fid]
                            self.assertEqual(
                                (_clampi(pan), _clampi(tilt)),
                                (v.get(fx.pan_attr), v.get(fx.tilt_attr)),
                                f"Kopf0 != _values alg={alg.value} mir={mirror} "
                                f"ctr={counter} mode={mode} i={i}")

    def test_heads_ge1_match_head_pan_tilts_render(self):
        # Koepfe >=1 aus head_phase_points == was _head_pan_tilts ans DMX gibt.
        e = self._build(alg=EfxAlgorithm.CIRCLE, n=2, hs=0.6,
                        counter=True, mode="offset")
        pts = e.head_phase_points(0, len(e.fixtures), e._phase,
                                  e._rand_progress, 4)
        for (k, _pa, pval, _ta, tval) in e._head_pan_tilts(fid=1, head_count=4):
            self.assertEqual((pval, tval), pts[k],
                             f"Kopf {k} Vorschau != Render")


# ── EfxPreviewWidget ─────────────────────────────────────────────────────────
class PreviewWidgetTest(unittest.TestCase):
    def _efx(self, fid=1):
        e = EfxInstance(name="t")
        e.algorithm = EfxAlgorithm.CIRCLE
        e.fixtures = [EfxFixture(fid=fid)]
        e.width = e.height = 200.0
        e.x_offset = e.y_offset = 128.0
        e.head_spread = 1.0
        e._phase = 0.05
        return e

    def _spy(self, e):
        """Ersetzt e.head_phase_points durch einen aufzeichnenden Wrapper."""
        calls = []
        orig = e.head_phase_points

        def wrap(i, n, phase, rp, hc):
            calls.append((i, n, hc))
            return orig(i, n, phase, rp, hc)
        e.head_phase_points = wrap
        return calls

    def test_set_head_counts_override_wins(self):
        # Expliziter Override gewinnt vor der Patch-Aufloesung (leerer Snapshot).
        pw = EfxPreviewWidget()
        pw.set_head_counts({1: 4})
        self.assertEqual(pw._head_count_for(1, {}), 4)

    def test_head_count_for_unknown_fid_is_one(self):
        # Kein Override, kein Patch-Eintrag -> sicher Single-Head (1), NICHT gecacht.
        pw = EfxPreviewWidget()
        self.assertEqual(pw._head_count_for(99, {}), 1)
        self.assertEqual(pw._head_counts_override, {})   # Fallback nie gecacht

    def test_set_efx_clears_overrides(self):
        pw = EfxPreviewWidget()
        pw.set_head_counts({1: 4})
        pw.set_efx(self._efx())
        self.assertEqual(pw._head_counts_override, {})

    def test_multihead_takes_head_point_path(self):
        pw = EfxPreviewWidget()
        e = self._efx()
        pw.set_efx(e)
        pw.set_head_counts({1: 4})
        calls = self._spy(e)
        pw.resize(300, 300)
        pw.grab()                      # erzwingt paintEvent
        self.assertTrue(calls, "Mehrkopf-Zweig nicht genommen (kein head_phase_points)")
        self.assertEqual(calls[0][2], 4, "falsche Kopfzahl an head_phase_points")

    def test_single_head_keeps_one_point_path(self):
        pw = EfxPreviewWidget()
        e = self._efx()
        pw.set_efx(e)
        pw.set_head_counts({1: 1})     # Single-Head -> KEIN Kopf-Punkt-Pfad
        calls = self._spy(e)
        pw.resize(300, 300)
        pw.grab()
        self.assertFalse(calls, "Single-Head nahm faelschlich den Mehrkopf-Zweig")

    def test_no_fixture_placeholder_paints(self):
        # Kein Geraet zugewiesen -> Platzhalter-Punkt, kein Absturz, kein Kopf-Pfad.
        pw = EfxPreviewWidget()
        e = self._efx()
        e.fixtures = []
        pw.set_efx(e)
        calls = self._spy(e)
        pw.resize(300, 300)
        pw.grab()
        self.assertFalse(calls)


if __name__ == "__main__":
    unittest.main()
