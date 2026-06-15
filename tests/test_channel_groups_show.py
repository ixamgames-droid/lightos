"""SDK-02: Channel Groups — Serialisierung + Show-Integration der View."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.views.channel_groups_view import ChannelGroup, ChannelGroupsView

_app = QApplication.instance() or QApplication([])


class ModelTest(unittest.TestCase):
    def test_round_trip(self):
        g = ChannelGroup(name="Front", universe=2, channels=[1, 2, 5], value=180)
        g2 = ChannelGroup.from_dict(g.to_dict())
        self.assertEqual(g2.name, "Front")
        self.assertEqual(g2.universe, 2)
        self.assertEqual(g2.channels, [1, 2, 5])
        self.assertEqual(g2.value, 180)


class ViewShowIOTest(unittest.TestCase):
    def test_to_dict_and_load_data(self):
        view = ChannelGroupsView()
        payload = [
            {"name": "G1", "universe": 1, "channels": [1, 2, 3], "value": 100},
            {"name": "G2", "universe": 2, "channels": [10, 11], "value": 50},
        ]
        view.load_data(payload)
        out = view.to_dict()
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["name"], "G1")
        self.assertEqual(out[0]["channels"], [1, 2, 3])
        self.assertEqual(out[1]["universe"], 2)

    def test_load_empty_resets(self):
        view = ChannelGroupsView()
        view.load_data([{"name": "X", "universe": 1, "channels": [1], "value": 5}])
        self.assertEqual(len(view.to_dict()), 1)
        view.load_data([])
        self.assertEqual(view.to_dict(), [])


if __name__ == "__main__":
    unittest.main()
