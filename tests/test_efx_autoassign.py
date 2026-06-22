"""UI-04: Der Standalone-EFX-Tab weist neuen/gestarteten Bewegungen automatisch
Geraete zu, sodass ``▶ Start`` nicht stumm laeuft.

Regression-Hintergrund: Davids Live-Show ("Test 1 2 3") hatte eine Circle-EFX mit
``fixtures=[]`` -> ``EfxInstance.write()`` bricht bei leerer Liste sofort ab ->
null DMX-Output, nichts im Simple Desk, keine Bewegung. Der EFX-Tab legte neue
Bewegungen ohne Geraete an und ``▶ Start`` startete sie kommentarlos.

Fix: ``_add_efx``/``_start_efx`` rufen ``_auto_assign_if_empty`` — erst die
aktuelle Auswahl, sonst alle gepatchten Movingheads (Pan+Tilt bzw. Dual-Tilt);
gibt es gar keine, bleibt die Liste leer (``_start_efx`` warnt dann statt stumm
zu starten).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

import src.core.app_state as A
from src.ui.views.efx_view import EfxView
from src.core.engine.efx import EfxAlgorithm
from src.core.dmx.universe import Universe


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0
        self.highlight_value = 255
        self.ranges = []


def _mh_chans():
    # Moving Head: pan@1, tilt@2, intensity@3
    return [_Ch("pan", 1), _Ch("tilt", 2), _Ch("intensity", 3)]


def _par_chans():
    # PAR ohne Pan/Tilt -> kein Mover
    return [_Ch("intensity", 1), _Ch("color_r", 2),
            _Ch("color_g", 3), _Ch("color_b", 4)]


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 4

    def __init__(self, fid, address, chans, universe=1):
        self.fid = fid
        self.universe = universe
        self.address = address
        self._chans = chans
        self.invert_pan = False
        self.invert_tilt = False
        self.swap_pan_tilt = False


class EfxAutoAssignTest(unittest.TestCase):
    def setUp(self):
        # Fake-Patch: 2 Moving Heads (fid 1,2) + 1 PAR (fid 3, kein Pan/Tilt).
        self.mh1 = _Fx(1, 10, _mh_chans())
        self.mh2 = _Fx(2, 20, _mh_chans())
        self.par = _Fx(3, 30, _par_chans())
        self._all = [self.mh1, self.mh2, self.par]
        self._sel: list[int] = []
        # Modul-Helfer faken (deckt auch is_dual_tilt_fixture ab, das ueber
        # dieselbe Funktion laeuft); in tearDown zuruecksetzen.
        self._orig_gcp = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: getattr(fx, "_chans", [])
        st = A.get_state()
        st.get_patched_fixtures = lambda: list(self._all)
        st.get_selected_fids = lambda: list(self._sel)
        self.v = EfxView()                 # Standalone-Tab (follow=False)
        self._pre_ids = {f.id for f in self.v._instances}

    def tearDown(self):
        A.get_channels_for_patched = self._orig_gcp
        # Nur in DIESEM Test angelegte EFX wieder aus dem globalen Manager nehmen.
        try:
            for inst in list(self.v._instances):
                if inst.id not in self._pre_ids:
                    self.v._fm.remove(inst.id)
        except Exception:
            pass
        # st.get_patched_fixtures / get_selected_fids raeumt die conftest-Fixture
        # _restore_app_state_singleton wieder ab.

    # ── Anlegen ──────────────────────────────────────────────────────────────

    def test_new_efx_gets_all_movers_when_no_selection(self):
        self.v._add_efx()
        cur = self.v._current
        self.assertIsNotNone(cur)
        # nur die beiden Moving Heads, NICHT der PAR
        self.assertEqual([f.fid for f in cur.fixtures], [1, 2])

    def test_new_efx_prefers_current_selection(self):
        self._sel = [2]                    # nur MH #2 ausgewaehlt
        self.v._add_efx()
        self.assertEqual([f.fid for f in self.v._current.fixtures], [2])

    def test_selection_order_is_preserved(self):
        self._sel = [2, 1]                 # Reihenfolge zaehlt fuer Fan/Spread
        self.v._add_efx()
        self.assertEqual([f.fid for f in self.v._current.fixtures], [2, 1])

    def test_existing_fixtures_are_not_overwritten(self):
        self.v._add_efx()
        cur = self.v._current
        self.assertEqual([f.fid for f in cur.fixtures], [1, 2])
        # erneutes Auto-Assign laesst eine bereits befuellte Liste unangetastet
        self._sel = [3]
        self.assertEqual(self.v._auto_assign_if_empty(allow_all=True), 2)
        self.assertEqual([f.fid for f in cur.fixtures], [1, 2])

    # ── Der eigentliche Bug: Output statt Stille ─────────────────────────────

    def test_auto_assigned_efx_writes_pan_tilt(self):
        self.v._add_efx()
        cur = self.v._current
        cur.algorithm = EfxAlgorithm.CIRCLE
        cur._running = True
        uni = Universe(1)
        cur.write({1: uni}, self._all, dt=0.5)
        # MH #1: pan@addr10, tilt@addr11
        moved = uni.get_channel(10) > 0 or uni.get_channel(11) > 0
        self.assertTrue(moved, "EFX bewegt nach Auto-Zuweisung kein Pan/Tilt")

    # ── Fallback/Sicherheit ──────────────────────────────────────────────────

    def test_no_movers_patched_leaves_list_empty(self):
        self._all = [self.par]             # nur PAR -> kein Mover verfuegbar
        self.v._add_efx()
        cur = self.v._current
        self.assertEqual(cur.fixtures, [])
        # Helfer meldet 0 -> _start_efx warnt statt stumm zu starten
        self.assertEqual(self.v._auto_assign_if_empty(allow_all=True), 0)


if __name__ == "__main__":
    unittest.main()
