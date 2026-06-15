"""APC-Probier To-Do #4: PROGRAMMER-Fader an eine FESTE Fixture-Gruppe binden.

scope == "group" + programmer_group lassen den Fader gezielt auf die Geräte
einer Gruppe wirken — unabhängig von der Live-Auswahl (PAR-Dim trifft die PARs,
ohne dass man die Gruppe vorher anklicken muss).
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.core.app_state import get_state

_app = QApplication.instance() or QApplication([])


class _FakeSession:
    def __init__(self, group):
        self._group = group
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def execute(self, _query):
        return SimpleNamespace(scalar_one_or_none=lambda: self._group)


class GroupFidsResolutionTest(unittest.TestCase):
    """`_group_fids` delegiert jetzt an state.group_fids_by_name (zentrale Auflösung)."""
    def test_group_fids_delegates_to_state(self):
        fake_state = SimpleNamespace(group_fids_by_name=lambda name: [2, 4, 7])
        self.assertEqual(VCSlider._group_fids(fake_state, "PARs"), [2, 4, 7])

    def test_group_fids_missing_group_returns_empty(self):
        fake_state = SimpleNamespace(group_fids_by_name=lambda name: [])
        self.assertEqual(VCSlider._group_fids(fake_state, "X"), [])


class ApplyGroupScopeTest(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self.state.programmer.clear()

    def tearDown(self):
        self.state.programmer.clear()

    def test_apply_routes_to_group_fids(self):
        s = VCSlider("PAR-Dim")
        s.mode = SliderMode.PROGRAMMER
        s.programmer_attr = "intensity"
        s.programmer_scope = "group"
        s.programmer_group = "PAR-Reihe"
        with patch.object(VCSlider, "_group_fids", return_value=[2, 4]):
            s.value = 200
        self.assertEqual(self.state.programmer.get(2, {}).get("intensity"), 200)
        self.assertEqual(self.state.programmer.get(4, {}).get("intensity"), 200)
        self.assertNotIn(1, self.state.programmer)   # nicht in der Gruppe

    def test_apply_empty_group_falls_back_to_all(self):
        s = VCSlider("PAR-Dim")
        s.mode = SliderMode.PROGRAMMER
        s.programmer_attr = "intensity"
        s.programmer_scope = "group"
        s.programmer_group = "Leer"
        fakes = [SimpleNamespace(fid=1), SimpleNamespace(fid=2)]
        with patch.object(VCSlider, "_group_fids", return_value=[]), \
             patch.object(type(self.state), "get_patched_fixtures", return_value=fakes):
            s.value = 128
        self.assertEqual(self.state.programmer.get(1, {}).get("intensity"), 128)
        self.assertEqual(self.state.programmer.get(2, {}).get("intensity"), 128)


class SerializationTest(unittest.TestCase):
    def test_roundtrip(self):
        s = VCSlider("X")
        s.mode = SliderMode.PROGRAMMER
        s.programmer_scope = "group"
        s.programmer_group = "Moving Heads"
        s2 = VCSlider("Y")
        s2.apply_dict(s.to_dict())
        self.assertEqual(s2.programmer_scope, "group")
        self.assertEqual(s2.programmer_group, "Moving Heads")


if __name__ == "__main__":
    unittest.main()
