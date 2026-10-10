"""LAS-22: der EFX-Editor bewegt Laser ueber ``laser_x``/``laser_y``.

Die Engine konnte das seit LAS-23 (``EfxFixture.pan_attr``/``tilt_attr``), der
Editor nicht: ein ausgewaehlter DMX-Laser (EL-400RGB MK2, SH-LASER3W) fiel aus
der Geraeteliste, weil nur Pan+Tilt-Geraete und Spider zaehlten, und der
Reiter EFX blieb ohne Pan/Tilt in der Auswahl unsichtbar.

Jetzt: ausgewaehlte Laser mit X/Y-Kanaelen werden Ziele mit
``pan_attr='laser_x'``/``tilt_attr='laser_y'``. Der Rueckfall „alle Mover“
(nichts ausgewaehlt) nimmt Laser NICHT mit — ein per Taste gestarteter EFX
darf keinen Laser schwenken, den niemand gewaehlt hat.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

import src.core.app_state as A
from src.core.dmx.universe import Universe
from src.core.engine.efx import EfxAlgorithm
from src.ui.views.efx_view import EfxView, laser_achsen_attrs


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0
        self.highlight_value = 255
        self.ranges = []


# EL-400RGB MK2 (Auszug der Kanalfolge): Betriebsart, Muster, X, Y.
_LASER = ["shutter", "gobo_wheel", "laser_x", "laser_y", "laser_scan_rate"]
_MH = ["pan", "tilt", "intensity"]


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 5
    fixture_type = ""

    def __init__(self, fid, address, attrs, ftype=""):
        self.fid = fid
        self.universe = 1
        self.address = address
        self.fixture_type = ftype
        self._chans = [_Ch(a, i + 1) for i, a in enumerate(attrs)]
        self.invert_pan = False
        self.invert_tilt = False
        self.swap_pan_tilt = False


class AchsenTest(unittest.TestCase):
    def test_laser_mit_xy(self):
        self.assertEqual(laser_achsen_attrs(_LASER), ("laser_x", "laser_y"))

    def test_nur_eine_laser_achse_reicht(self):
        self.assertEqual(laser_achsen_attrs(["shutter", "laser_x"]),
                         ("laser_x", "laser_y"))

    def test_kopf_suffix(self):
        self.assertEqual(laser_achsen_attrs(["laser_x#1", "laser_y#1"]),
                         ("laser_x", "laser_y"))

    def test_moving_head_bleibt_pan_tilt(self):
        self.assertIsNone(laser_achsen_attrs(_MH))
        self.assertIsNone(laser_achsen_attrs(_MH + ["laser_x"]))

    def test_par_ohne_achsen(self):
        self.assertIsNone(laser_achsen_attrs(["intensity", "color_r"]))


class EditorTest(unittest.TestCase):
    def setUp(self):
        self.mh = _Fx(1, 10, _MH)
        self.laser = _Fx(2, 101, _LASER, "laser")
        self._all = [self.mh, self.laser]
        self._sel: list[int] = []
        self._orig_gcp = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: getattr(fx, "_chans", [])
        st = A.get_state()
        st.get_patched_fixtures = lambda: list(self._all)
        st.get_selected_fids = lambda: list(self._sel)
        self.v = EfxView()
        self._pre_ids = {f.id for f in self.v._instances}

    def tearDown(self):
        A.get_channels_for_patched = self._orig_gcp
        try:
            for inst in list(self.v._instances):
                if inst.id not in self._pre_ids:
                    self.v._fm.remove(inst.id)
        except Exception:
            pass

    def _ziele(self):
        return [(f.fid, f.pan_attr, f.tilt_attr)
                for f in self.v._current.fixtures]

    def test_ausgewaehlter_laser_wird_ziel_mit_laser_achsen(self):
        self._sel = [2]
        self.v._add_efx()
        self.assertEqual(self._ziele(), [(2, "laser_x", "laser_y")])

    def test_gemischte_auswahl_behaelt_reihenfolge_und_achsen(self):
        self._sel = [2, 1]
        self.v._add_efx()
        self.assertEqual(self._ziele(), [(2, "laser_x", "laser_y"),
                                         (1, "pan", "tilt")])

    def test_ohne_auswahl_kein_laser_im_rueckfall(self):
        self._sel = []
        self.v._add_efx()
        self.assertEqual(self._ziele(), [(1, "pan", "tilt")])

    def test_folgemodus_nimmt_laser_aus_der_auswahl(self):
        self._sel = [2]
        self.v._add_efx()
        self.v._current.fixtures = []
        self.v._assign_from_selection()
        self.assertEqual(self._ziele(), [(2, "laser_x", "laser_y")])
        self.assertIn("Laser", self.v._fx_box.title())

    def test_efx_schreibt_laser_x_und_y(self):
        self._sel = [2]
        self.v._add_efx()
        cur = self.v._current
        cur.algorithm = EfxAlgorithm.CIRCLE
        cur._running = True
        uni = Universe(1)
        cur.write({1: uni}, self._all, dt=0.37)
        x, y = uni.get_channel(103), uni.get_channel(104)
        self.assertTrue(x > 0 or y > 0, "EFX bewegt den Laser nicht")
        # Betriebsart und Muster fasst ein Bewegungs-EFX nie an.
        self.assertEqual(uni.get_channel(101), 0)
        self.assertEqual(uni.get_channel(102), 0)


if __name__ == "__main__":
    unittest.main()
