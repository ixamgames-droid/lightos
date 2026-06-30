"""Frische Codex-Folgebefunde auf den Loop-PRs #100/#101 (Stand 2026-06-30).

Echte Folge-Bugs der dortigen Fixes, gegen aktuellen main verifiziert:

- VCB-32: GROUP_DIMMER/SUBMASTER werden beim Show-Laden nicht re-applied — die
  Direktzuweisung an _value umgeht den @value.setter (der _apply() ruft). Folge:
  Show kommt zu hell hoch, bis der Nutzer den Fader bewegt (Folge von VCB-05, das
  fixture_dimmers bei load/reset leert).
- VCB-33: range_max=0 (gueltige „Mute/Cap"-Konfig) wurde von `or 255` als „fehlt"
  behandelt und auf 255 hochgesetzt -> Ausgabe nach Reload statt stummem Fader.
- VCB-34: Retarget eines GROUP_DIMMER-Faders von Gruppe A auf B liess A als
  Geister-Dimmer stehen (Folge von VCB-19, dessen elif den Retarget-Fall nicht traf).
- UI-14c: Im Aktiv-Effekt-Modus liefern VCColor/VCEffectColors function_id=None;
  refresh_effect_badges(None) lief in den int(None)-Guard -> kein Badge-Repaint
  (Folge von UI-14b). Jetzt loest refresh_effect_badges None auf den aktiven Effekt auf.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint

from src.core.app_state import get_state
from src.core.engine.rgb_matrix import ColorSequence
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_canvas import VCCanvas

_app = QApplication.instance() or QApplication([])


class VCB32ReapplyOnLoad(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self.state.fixture_dimmers.clear()

    def test_group_dimmer_reapplied_on_load(self):
        s = VCSlider("g")
        s._group_fids = lambda st, name: [101]          # Gruppe -> fid 101
        s.apply_dict({"mode": SliderMode.GROUP_DIMMER,
                      "programmer_group": "G", "value": 128})
        self.assertAlmostEqual(self.state.fixture_dimmers.get(101, 1.0),
                               128 / 255.0, places=2,
                               msg="VCB-32: GROUP_DIMMER muss beim Laden re-applied "
                                   "werden (sonst kommt die Show zu hell hoch)")

    def test_submaster_reapplied_on_load(self):
        calls = []
        om = self.state.output_manager
        orig = om.set_submaster
        om.set_submaster = lambda *a, **k: calls.append(a)
        try:
            s = VCSlider("sm")
            s.apply_dict({"mode": SliderMode.SUBMASTER, "value": 128})
        finally:
            om.set_submaster = orig
        self.assertTrue(calls, "VCB-32: SUBMASTER muss beim Laden gesetzt werden")
        self.assertAlmostEqual(calls[0][1], 128 / 255.0, places=2)

    def test_level_not_reapplied_on_load(self):
        # Gegenprobe: LEVEL darf beim Laden NICHT feuern (sonst schriebe jeder
        # geladene LEVEL-Fader sofort DMX). Universe darf nicht angelegt werden.
        s = VCSlider("l")
        s.apply_dict({"mode": SliderMode.LEVEL, "value": 128,
                      "dmx_universe": 97, "dmx_channel": 5})
        self.assertNotIn(97, self.state.universes,
                         "VCB-32: LEVEL-Fader darf beim Laden nicht angewendet werden")


class VCB33ExplicitZeroRangeMax(unittest.TestCase):
    def test_explicit_zero_max_preserved(self):
        s = VCSlider("x")
        s.apply_dict({"range_max": 0})
        self.assertEqual(s.range_max, 0,
                         "VCB-33: explizite range_max=0 (Mute/Cap) muss erhalten bleiben")

    def test_missing_max_defaults_255(self):
        s = VCSlider("x")
        s.apply_dict({})
        self.assertEqual(s.range_max, 255)

    def test_null_max_defaults_255(self):
        s = VCSlider("x")
        s.apply_dict({"range_max": None})       # JSON null
        self.assertEqual(s.range_max, 255)


class VCB34RetargetGroupDimmer(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self.state.fixture_dimmers.clear()

    def _make(self):
        s = VCSlider("g")
        s.mode = SliderMode.GROUP_DIMMER
        s.programmer_group = "B"                 # neues Ziel
        s._value = 128
        s._group_fids = lambda st, name: {"A": [201], "B": [202]}.get(name, [])
        return s

    def test_retarget_resets_old_group(self):
        # Gruppe A war vor dem Retarget gedimmt (Geister-Kandidat).
        self.state.set_group_dimmer([201], 0.4)
        self.assertIn(201, self.state.fixture_dimmers)
        s = self._make()
        s._post_dialog_mode_sync(SliderMode.GROUP_DIMMER, "A")   # A -> B
        self.assertNotIn(201, self.state.fixture_dimmers,
                         "VCB-34: alte Gruppe A muss beim Retarget zurueckgesetzt werden")
        self.assertAlmostEqual(self.state.fixture_dimmers.get(202, 1.0),
                               128 / 255.0, places=2,
                               msg="neue Gruppe B muss gedimmt sein")

    def test_leaving_group_dimmer_still_resets(self):
        # VCB-19-Regression: weg vom GROUP_DIMMER -> alte Gruppe zuruecksetzen.
        self.state.set_group_dimmer([201], 0.4)
        s = self._make()
        s.mode = SliderMode.LEVEL                # raus aus GROUP_DIMMER
        s._post_dialog_mode_sync(SliderMode.GROUP_DIMMER, "A")
        self.assertNotIn(201, self.state.fixture_dimmers,
                         "VCB-19: Verlassen des GROUP_DIMMER muss alte Gruppe loeschen")


class UI14cActiveEffectBadge(unittest.TestCase):
    def setUp(self):
        self.fm = get_state().function_manager
        self.fn = self.fm.new_rgb_matrix("UI14cMatrix")
        self.fm.start(self.fn.id)               # -> aktiver Effekt (resolve_target(None))

    def tearDown(self):
        try:
            self.fm.stop(self.fn.id)
            self.fm.remove(self.fn.id)
        except Exception:
            pass

    def test_refresh_none_resolves_active_effect(self):
        canvas = VCCanvas()
        b = canvas._add_widget("VCButton", QPoint(10, 10))
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = self.fn.id
        self.assertEqual(len(b._color_badge_colors()), 3, "frische Matrix -> 3 Farben")
        self.fn.colors = ColorSequence([(10, 20, 30)])
        canvas.refresh_effect_badges(None)       # Aktiv-Effekt-Modus: function_id=None
        self.assertEqual(len(b._badge_colors), 1,
                         "UI-14c: None muss auf den aktiven Effekt aufgeloest werden "
                         "und das gebundene Badge neu aufloesen")

    def test_refresh_none_without_active_is_safe(self):
        self.fm.stop(self.fn.id)                 # kein laufender Effekt
        canvas = VCCanvas()
        b = canvas._add_widget("VCButton", QPoint(10, 10))
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = self.fn.id
        b._color_badge_colors()
        try:
            canvas.refresh_effect_badges(None)
        except Exception as e:
            self.fail(f"refresh_effect_badges(None) darf nie crashen: {e!r}")
        self.assertEqual(len(b._badge_colors), 3)


if __name__ == "__main__":
    unittest.main()
