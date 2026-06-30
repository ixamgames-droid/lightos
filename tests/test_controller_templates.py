"""Tests fuer die Controller-Vorlagen (APC-Pad-Layout als VC-Widgets).

Prueft den reinen Daten-Builder ``controller_template`` — dass Pads/Fader auf die
korrekten MIDI-Notes/CCs gemappt werden. Der fruehere Color-Chase-Baukasten und
das Canvas-Aufzieh-Werkzeug wurden entfernt.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


class ControllerTemplateTest(unittest.TestCase):
    def setUp(self):
        _app()
        from src.ui.virtualconsole import controller_templates as ct
        self.ct = ct

    def test_apc_mini_grid_and_faders(self):
        t = self.ct.controller_template("apc_mini")
        pads = [w for w in t if w["type"] == "VCButton"
                and w.get("midi_data1", -1) in range(64)]
        notes = sorted(w["midi_data1"] for w in pads)
        self.assertEqual(notes, list(range(64)))          # alle 64 Grid-Pads
        faders = [w for w in t if w["type"] == "VCSlider"]
        self.assertEqual([w["midi_cc"] for w in faders], list(range(48, 57)))

    def test_mk2_track_and_scene_notes(self):
        t = self.ct.controller_template("apc_mini_mk2")
        track = sorted(w["midi_data1"] for w in t
                       if w["type"] == "VCButton" and w["caption"].startswith("Trk"))
        self.assertEqual(track, list(range(100, 108)))     # mk2 Track-Tasten


if __name__ == "__main__":
    unittest.main()
