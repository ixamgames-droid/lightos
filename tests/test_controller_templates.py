"""Tests fuer die Controller-Vorlagen + den Color-Chase-Baukasten (Editor-Tool).

Prueft die reinen Daten-Builder und dass der VCCanvas die erzeugten Dicts zu
korrekt konfigurierten Widgets aufbaut (Round-Trip).
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

    def test_color_chase_kit_wiring(self):
        kit = self.ct.color_chase_kit(function_id=42)
        colors = [w for w in kit if w["type"] == "VCColor"]
        self.assertTrue(colors)
        self.assertTrue(all(w.get("function_id") == 42 for w in colors))
        self.assertTrue(all(str(w.get("target", "")).startswith("Effekt (Farbe")
                            for w in colors))
        keys = {w.get("effect_action_key") for w in kit
                if w["type"] == "VCButton" and w.get("action") == "EffectAction"}
        self.assertIn("clear_colors", keys)
        modes = {w.get("mode") for w in kit if w["type"] == "VCSlider"}
        self.assertIn("EffectSpeed", modes)
        self.assertIn("EffectParam", modes)

    def test_canvas_ingests_kit(self):
        """VCCanvas baut aus den Kit-Dicts echte Widgets mit korrekten Eigenschaften."""
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
        canvas = VCCanvas()
        canvas.from_dict({"widgets": self.ct.color_chase_kit(function_id=7)})
        colors = canvas.findChildren(VCColor)
        self.assertTrue(colors)
        self.assertTrue(all(c.target == ColorTarget.EFFECT_ADD and c.function_id == 7
                            for c in colors))

    def test_color_chase_kit_in_rect(self):
        """Der aufgezogene Bereich erzeugt ein passend platziertes Color-Chase-Kit."""
        kit = self.ct.color_chase_kit_in_rect(function_id=3, x=100, y=120, w=400, h=300)
        colors = [w for w in kit if w["type"] == "VCColor"]
        self.assertTrue(colors)
        self.assertTrue(all(w.get("function_id") == 3 for w in colors))
        # Alle Elemente beginnen innerhalb des aufgezogenen Rechtecks.
        self.assertTrue(all(w["x"] >= 100 and w["y"] >= 120 for w in kit))

    def test_canvas_area_tool_state(self):
        """Aufzieh-Werkzeug lässt sich armieren und wieder abbrechen."""
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        c = VCCanvas()
        self.assertIsNone(c._area_tool)
        c.arm_area_tool("color_chase")
        self.assertEqual(c._area_tool, "color_chase")
        c.cancel_area_tool()
        self.assertIsNone(c._area_tool)


if __name__ == "__main__":
    unittest.main()
