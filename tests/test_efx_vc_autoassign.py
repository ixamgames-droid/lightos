"""VC-Auto-Assign (fix/efx-vc-autoassign, 2026-06-24).

Folge-Fix zu #45: Ein per **VC-Button** (FunctionToggle) gestarteter EFX ohne
Geraete lief stumm (``write()`` No-Op). Jetzt weist der VC-Pfad beim Start
automatisch bewegliche Geraete zu — aktuelle Auswahl, sonst alle gepatchten
Movingheads — analog UI-04 im EFX-Tab ([[project_efx_start_autoassign_2026_06_23]]).

Mover-Erkennung liegt in EINER Quelle: ``app_state.is_mover_fixture`` /
``mover_fids`` (genutzt von EfxView._patched_movers UND EfxInstance.assign_movers_auto).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

import src.core.app_state as A
from src.core.engine.efx import EfxInstance, EfxAlgorithm
from src.core.dmx.universe import Universe
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0
        self.highlight_value = 255
        self.ranges = []


def _mh_chans():
    return [_Ch("pan", 1), _Ch("tilt", 2), _Ch("intensity", 3)]


def _par_chans():
    return [_Ch("intensity", 1), _Ch("color_r", 2), _Ch("color_g", 3)]


class _Fx:
    def __init__(self, fid, address, chans, universe=1):
        self.fid = fid
        self.universe = universe
        self.address = address
        self._chans = chans
        self.invert_pan = False
        self.invert_tilt = False
        self.swap_pan_tilt = False


class _MoverFakesMixin:
    def _install_patch(self, all_fx, sel=None):
        self._all = list(all_fx)
        self._sel = list(sel or [])
        self._orig_gcp = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: getattr(fx, "_chans", [])
        st = A.get_state()
        st.get_patched_fixtures = lambda: list(self._all)
        st.get_selected_fids = lambda: list(self._sel)

    def _restore_patch(self):
        A.get_channels_for_patched = self._orig_gcp
        # st.get_* raeumt die conftest-Fixture _restore_app_state_singleton ab.


class MoverHelpersTest(_MoverFakesMixin, unittest.TestCase):
    def setUp(self):
        self.mh1 = _Fx(1, 10, _mh_chans())
        self.mh2 = _Fx(2, 20, _mh_chans())
        self.par = _Fx(3, 30, _par_chans())
        self._install_patch([self.mh1, self.mh2, self.par])

    def tearDown(self):
        self._restore_patch()

    def test_is_mover_fixture(self):
        self.assertTrue(A.is_mover_fixture(self.mh1))
        self.assertFalse(A.is_mover_fixture(self.par))

    def test_mover_fids_all(self):
        self.assertEqual(A.mover_fids(), [1, 2])      # PAR faellt raus

    def test_mover_fids_restrict_preserves_order(self):
        self.assertEqual(A.mover_fids([2, 1]), [2, 1])

    def test_mover_fids_restrict_drops_non_movers(self):
        self.assertEqual(A.mover_fids([3, 1]), [1])


class AssignMoversAutoTest(_MoverFakesMixin, unittest.TestCase):
    def setUp(self):
        self.mh1 = _Fx(1, 10, _mh_chans())
        self.mh2 = _Fx(2, 20, _mh_chans())
        self.par = _Fx(3, 30, _par_chans())
        self._install_patch([self.mh1, self.mh2, self.par])

    def tearDown(self):
        self._restore_patch()

    def test_all_movers_when_no_selection(self):
        efx = EfxInstance("Kreis")
        self.assertEqual(efx.assign_movers_auto(), 2)
        self.assertEqual([f.fid for f in efx.fixtures], [1, 2])

    def test_prefers_selection(self):
        self._sel = [2]
        efx = EfxInstance("Kreis")
        efx.assign_movers_auto()
        self.assertEqual([f.fid for f in efx.fixtures], [2])

    def test_selection_order_preserved(self):
        self._sel = [2, 1]
        efx = EfxInstance("Kreis")
        efx.assign_movers_auto()
        self.assertEqual([f.fid for f in efx.fixtures], [2, 1])

    def test_does_not_overwrite_existing(self):
        from src.core.engine.efx import EfxFixture
        efx = EfxInstance("Kreis")
        efx.fixtures = [EfxFixture(fid=2)]
        self.assertEqual(efx.assign_movers_auto(), 1)
        self.assertEqual([f.fid for f in efx.fixtures], [2])

    def test_no_movers_leaves_empty(self):
        self._all = [self.par]
        efx = EfxInstance("Kreis")
        self.assertEqual(efx.assign_movers_auto(), 0)
        self.assertEqual(efx.fixtures, [])

    def test_allow_all_false_without_selection_stays_empty(self):
        efx = EfxInstance("Kreis")
        self.assertEqual(efx.assign_movers_auto(allow_all=False), 0)


class VcButtonTriggerAutoAssignTest(_MoverFakesMixin, unittest.TestCase):
    def setUp(self):
        self.mh1 = _Fx(1, 10, _mh_chans())
        self.mh2 = _Fx(2, 20, _mh_chans())
        self._install_patch([self.mh1, self.mh2])
        self.fm = A.get_state().function_manager
        self.efx = self.fm.add(EfxInstance("Kreis"))
        self.efx.algorithm = EfxAlgorithm.CIRCLE
        self.btn = VCButton("Kreis")
        self.btn.action = ButtonAction.FUNCTION_TOGGLE
        self.btn.function_id = self.efx.id

    def tearDown(self):
        self.fm.stop(self.efx.id)
        self.fm.remove(self.efx.id)
        self._restore_patch()

    def test_toggle_press_auto_assigns_and_runs(self):
        self.assertEqual(self.efx.fixtures, [])
        self.btn._trigger_primary(True)        # Button gedrueckt (Toggle an)
        self.assertTrue(self.fm.is_running(self.efx.id))
        self.assertEqual([f.fid for f in self.efx.fixtures], [1, 2])

    def test_auto_assigned_efx_writes_pan_tilt(self):
        self.btn._trigger_primary(True)
        uni = Universe(1)
        self.efx.write({1: uni}, [self.mh1, self.mh2], dt=0.5)
        moved = uni.get_channel(10) > 0 or uni.get_channel(11) > 0
        self.assertTrue(moved, "EFX bewegt nach VC-Auto-Zuweisung kein Pan/Tilt")

    def test_toggle_again_stops(self):
        self.btn._trigger_primary(True)
        self.assertTrue(self.fm.is_running(self.efx.id))
        self.btn._trigger_primary(True)        # zweiter Druck -> aus
        self.assertFalse(self.fm.is_running(self.efx.id))


if __name__ == "__main__":
    unittest.main()
