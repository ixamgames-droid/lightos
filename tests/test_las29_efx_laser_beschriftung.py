"""LAS-29: der EFX-Editor beschriftet Laser-Ziele nicht mehr wie Moving Heads.

Vorher hiessen die Geometrie-Felder bei einem reinen Laser-Ziel (LAS-22,
``pan_attr='laser_x'``) weiter „Breite (Pan-Hub)“ / „Zentrum Pan“, die
16-bit-Option „Pan/Tilt über pan_fine/tilt_fine“ stand da (Laser haben keine
Fine-Kanaele), und die Zielliste zeigte „Fixture #14“ statt des Labels.

Jetzt:
* reine Laser-Ziele -> X/Y-Beschriftung, 16-bit-Zeile ausgeblendet;
* gemischte Ziele (Laser + Moving Head) -> Bestand (Pan/Tilt, 16-bit sichtbar):
  die 16-bit-Ausgabe wirkt dort auf die Moving Heads weiter;
* Zielliste: Label, wenn vorhanden, sonst weiter „Fixture #N“.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

import src.core.app_state as A
from src.core.engine.efx import EfxFixture
from src.ui.views.efx_view import EfxView


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0
        self.highlight_value = 255
        self.ranges = []


_LASER = ["shutter", "gobo_wheel", "laser_x", "laser_y", "laser_scan_rate"]
_MH = ["pan", "tilt", "intensity"]


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 5

    def __init__(self, fid, address, attrs, ftype="", label=""):
        self.fid = fid
        self.label = label
        self.universe = 1
        self.address = address
        self.fixture_type = ftype
        self._chans = [_Ch(a, i + 1) for i, a in enumerate(attrs)]
        self.invert_pan = False
        self.invert_tilt = False
        self.swap_pan_tilt = False


class LaserBeschriftungTest(unittest.TestCase):
    def setUp(self):
        self.mh = _Fx(1, 10, _MH, label="Spot links")
        self.laser = _Fx(14, 101, _LASER, "laser", label="Showlaser")
        self.ohne = _Fx(3, 200, _MH)            # kein Label
        self._all = [self.mh, self.laser, self.ohne]
        self._sel: list[int] = []
        st = A.get_state()
        self._orig = (A.get_channels_for_patched,
                      st.__dict__.get("get_patched_fixtures"),
                      st.__dict__.get("get_selected_fids"))
        A.get_channels_for_patched = lambda fx: getattr(fx, "_chans", [])
        st.get_patched_fixtures = lambda: list(self._all)
        st.get_selected_fids = lambda: list(self._sel)
        self.v = EfxView()
        self._pre_ids = {f.id for f in self.v._instances}

    def tearDown(self):
        st = A.get_state()
        A.get_channels_for_patched = self._orig[0]
        for name, orig in (("get_patched_fixtures", self._orig[1]),
                           ("get_selected_fids", self._orig[2])):
            if orig is None:
                st.__dict__.pop(name, None)
            else:
                setattr(st, name, orig)
        try:
            for inst in list(self.v._instances):
                if inst.id not in self._pre_ids:
                    self.v._fm.remove(inst.id)
        except Exception:
            pass

    def _label(self, feld):
        return self.v._form_box.layout().labelForField(feld).text()

    def _bit16_sichtbar(self) -> bool:
        lbl = self.v._bit16_chk.parentWidget().layout().labelForField(
            self.v._bit16_chk)
        return not self.v._bit16_chk.isHidden() and not lbl.isHidden()

    def _zeilen(self):
        return [self.v._fx_list.item(i).text()
                for i in range(self.v._fx_list.count())]

    def test_reiner_laser_heisst_x_y_und_ohne_16bit(self):
        self._sel = [14]
        self.v._add_efx()
        self.assertEqual([f.pan_attr for f in self.v._current.fixtures],
                         ["laser_x"])
        self.assertEqual(self._label(self.v._width_spin), "Breite (X-Hub):")
        self.assertEqual(self._label(self.v._height_spin), "Höhe (Y-Hub):")
        self.assertEqual(self._label(self.v._xoff_spin), "Zentrum X:")
        self.assertEqual(self._label(self.v._yoff_spin), "Zentrum Y:")
        self.assertNotIn("Pan", self.v._relative_chk.text())
        self.assertNotIn("Pan", self.v._relative_chk.toolTip())
        self.assertFalse(self._bit16_sichtbar())

    def test_gemischte_ziele_bleiben_pan_tilt(self):
        self._sel = [14, 1]
        self.v._add_efx()
        self.assertEqual(self._label(self.v._width_spin), "Breite (Pan-Hub):")
        self.assertEqual(self._label(self.v._xoff_spin), "Zentrum Pan:")
        self.assertTrue(self._bit16_sichtbar())

    def test_wechsel_laser_zu_mover_stellt_bestand_wieder_her(self):
        self._sel = [14]
        self.v._add_efx()
        self.assertEqual(self._label(self.v._width_spin), "Breite (X-Hub):")
        self.v._current.fixtures = [EfxFixture(fid=1)]
        self.v._update_spider_mode()
        self.assertEqual(self._label(self.v._width_spin), "Breite (Pan-Hub):")
        self.assertEqual(self.v._relative_chk.text(),
                         "um aktuelle Pan/Tilt-Position")
        self.assertIn("Zentrum Pan/Tilt", self.v._relative_chk.toolTip())
        self.assertTrue(self._bit16_sichtbar())

    def test_zielliste_zeigt_das_label(self):
        self._sel = [14, 1, 3]
        self.v._add_efx()
        self.assertEqual(self._zeilen(),
                         ["Showlaser", "Spot links", "Fixture #3"])

    def test_zielliste_nach_dem_laden_zeigt_das_label(self):
        self._sel = [14]
        self.v._add_efx()
        self.v._load_to_ui(self.v._current)
        self.assertEqual(len(self._zeilen()), 1)
        self.assertTrue(self._zeilen()[0].startswith("Showlaser"),
                        self._zeilen())

    def test_resync_nach_show_load_behaelt_laser_beschriftung(self):
        self._sel = [14]
        self.v._add_efx()
        cur_id = self.v._current.id
        # Show-Wechsel/Resync: Liste neu aufbauen, Editor neu laden
        self.v._on_show_loaded()
        if self.v._current is None or self.v._current.id != cur_id:
            for i, inst in enumerate(self.v._visible_instances()):
                if inst.id == cur_id:
                    self.v._load_to_ui(inst)
                    break
        self.assertEqual(self._label(self.v._width_spin), "Breite (X-Hub):")
        self.assertFalse(self._bit16_sichtbar())
        self.assertTrue(self._zeilen()[0].startswith("Showlaser"),
                        self._zeilen())

    def test_target_label_ohne_namenskarte_bleibt_bestand(self):
        self.assertEqual(EfxView._target_label(EfxFixture(fid=7)), "Fixture #7")
        self.assertEqual(EfxView._target_label(EfxFixture(fid=7), None,
                                               {7: "Spot"}), "Spot")
        self.assertEqual(EfxView._target_label(EfxFixture(fid=7, head=2), None,
                                               {7: "Spot"}), "Spot · K3")


if __name__ == "__main__":
    unittest.main()
