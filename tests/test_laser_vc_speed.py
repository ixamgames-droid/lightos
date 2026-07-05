"""LAS-Speed: PROGRAMMER-Fader mit Wert-Teilband (0..100% → [min,max]).

Für Laser ohne echten Speed-Kanal (z. B. L2600): der Fader hält den Kanal im
gewählten Dynamik-Bereich (z. B. gobo_rotation 192..223) und regelt darin das
Tempo. Default 0/255 = altes Verhalten (identisch).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.core.app_state as app_state
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode


def _app():
    return QApplication.instance() or QApplication([])


def _find_attr_combo(dlg):
    """Die editierbare Attribut-Combo im Slider-Dialog: eindeutig daran, dass
    sie einen Eintrag mit itemData == 'gobo_rotation' trägt (UXT-01)."""
    from PySide6.QtWidgets import QComboBox
    for cb in dlg.findChildren(QComboBox):
        for i in range(cb.count()):
            if cb.itemData(i) == "gobo_rotation":
                return cb
    return None


class ProgrammerRangeMapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def _sl(self, lo=0, hi=255):
        s = VCSlider()
        s.programmer_min = lo
        s.programmer_max = hi
        return s

    def test_default_is_identity(self):
        s = self._sl(0, 255)
        self.assertEqual(s._programmer_mapped(0), 0)
        self.assertEqual(s._programmer_mapped(255), 255)
        self.assertEqual(s._programmer_mapped(128), 128)

    def test_subrange_maps_endpoints(self):
        s = self._sl(192, 223)
        self.assertEqual(s._programmer_mapped(0), 192)      # 0 % = Bereichsanfang
        self.assertEqual(s._programmer_mapped(255), 223)    # 100 % = Bereichsende
        mid = s._programmer_mapped(128)
        self.assertTrue(192 <= mid <= 223)

    def test_reversed_min_max_normalized(self):
        s = self._sl(223, 192)                              # vertauscht
        self.assertEqual(s._programmer_mapped(0), 192)
        self.assertEqual(s._programmer_mapped(255), 223)

    def test_values_clamped_to_dmx(self):
        s = self._sl(-50, 400)
        self.assertTrue(0 <= s._programmer_mapped(0) <= 255)
        self.assertTrue(0 <= s._programmer_mapped(255) <= 255)

    def test_persistence_roundtrip(self):
        s = self._sl(192, 223)
        s.mode = SliderMode.PROGRAMMER
        s.programmer_attr = "gobo_rotation"
        s2 = VCSlider()
        s2.apply_dict(s.to_dict())
        self.assertEqual(s2.programmer_min, 192)
        self.assertEqual(s2.programmer_max, 223)

    def test_backward_compat_missing_keys(self):
        s = VCSlider()
        s.apply_dict({})                                    # alte Show ohne Keys
        self.assertEqual((s.programmer_min, s.programmer_max), (0, 255))

    def test_apply_writes_mapped_value(self):
        class _S:
            def __init__(s):
                s.calls = []

            def get_patched_fixtures(s):
                return [type("F", (), {"fid": 7})()]

            def get_selected_fids(s):
                return []

            def set_programmer_value(s, fid, attr, v, **k):
                s.calls.append((fid, attr, v))

        st = _S()
        orig = app_state.get_state
        app_state.get_state = lambda: st
        try:
            s = self._sl(192, 223)
            s.mode = SliderMode.PROGRAMMER
            s.programmer_attr = "gobo_rotation"
            s.programmer_scope = "all"
            s._effective_value = lambda: 255               # Fader ganz oben
            s._apply()
            self.assertIn((7, "gobo_rotation", 223), st.calls)
        finally:
            app_state.get_state = orig


class ProgrammerAttrFieldTest(unittest.TestCase):
    """UXT-01: der Slider-Dialog exponiert das Ziel-Attribut. Ohne dieses Feld
    blieb der PROGRAMMER-Modus faktisch auf 'intensity' (Laser-Speed-Fader auf
    gobo_rotation per GUI unbaubar)."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def _open_and(self, slider, action):
        """Öffnet _open_properties mit gepatchtem exec: ``action(dlg)`` läuft im
        offenen Dialog, dann Accepted zurückgeben."""
        from PySide6.QtWidgets import QDialog
        orig = QDialog.exec

        def fake_exec(dlg):
            action(dlg)
            return QDialog.DialogCode.Accepted

        QDialog.exec = fake_exec
        try:
            slider._open_properties()
        finally:
            QDialog.exec = orig

    def test_field_present_and_prefilled(self):
        s = VCSlider()
        s.mode = SliderMode.PROGRAMMER
        s.programmer_attr = "gobo_rotation"
        seen = {}

        def check(dlg):
            cb = _find_attr_combo(dlg)
            seen["combo"] = cb
            if cb is not None:
                seen["current"] = cb.itemData(cb.currentIndex())

        self._open_and(s, check)
        self.assertIsNotNone(seen.get("combo"), "Attribut-Feld fehlt im Dialog")
        self.assertEqual(seen.get("current"), "gobo_rotation")

    def test_choosing_attr_writes_back(self):
        s = VCSlider()
        s.mode = SliderMode.PROGRAMMER
        s.programmer_attr = "intensity"

        def choose(dlg):
            cb = _find_attr_combo(dlg)
            idx = next(i for i in range(cb.count())
                       if cb.itemData(i) == "gobo_rotation")
            cb.setCurrentIndex(idx)

        self._open_and(s, choose)
        self.assertEqual(s.programmer_attr, "gobo_rotation")

    def test_freetext_attr_survives(self):
        s = VCSlider()
        s.mode = SliderMode.PROGRAMMER

        def typ(dlg):
            _find_attr_combo(dlg).setCurrentText("laser_scan_rate")

        self._open_and(s, typ)
        self.assertEqual(s.programmer_attr, "laser_scan_rate")


if __name__ == "__main__":
    unittest.main()
