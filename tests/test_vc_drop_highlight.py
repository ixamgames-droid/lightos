"""Drag-Feedback: beim Ziehen eines Effekts ueber die VC wird das Ziel-Widget
gruen (Effekt bindet hier) bzw. rot (Widget nimmt den Effekt nicht an) umrahmt.

Getestet wird die Validitaets-Logik von VCCanvas:
  * ``_effect_fits_widget`` — Capability-Abgleich Effekt<->Widget-Typ,
  * ``_drag_target_valid`` — Typ-Huerde + Capability-Check zusammen,
  * ``_drag_highlight_info`` / ``_vc_widget_under`` — Ziel-Suche unter dem Cursor.
Das Overlay selbst ist reine Anzeige (WA_TransparentForMouseEvents) und wird hier
nicht gerendert.
"""
import os
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint

from src.ui.virtualconsole.vc_canvas import VCCanvas
from src.ui.virtualconsole.vc_effect_meta import Capabilities

_app = QApplication.instance() or QApplication([])


def _spec(kind="int", live_editable=True, mappable=True, key="x"):
    return types.SimpleNamespace(kind=kind, live_editable=live_editable,
                                 mappable=mappable, key=key)


# Synthetische Effekt-Faehigkeiten fuer die einzelnen Faelle.
CAPS_NONE = Capabilities(has_params=False)                       # Szene/Snap
CAPS_SPEED = Capabilities(has_params=True, has_speed=True)
CAPS_INTENSITY = Capabilities(has_params=True, has_intensity=True)
CAPS_COLORS = Capabilities(has_params=True, has_colors=True)
CAPS_MOVEMENT = Capabilities(has_movement=True)                  # EFX
CAPS_INT_PARAM = Capabilities(has_params=True, param_specs=[_spec(kind="int")])


class _CanvasTest(unittest.TestCase):
    """Basis mit sauberem Abbau (sonst bleiben Canvases beim MIDI-Manager haengen)."""

    def setUp(self):
        self._canvases = []

    def tearDown(self):
        for c in self._canvases:
            try:
                c._teardown_midi()
            except Exception:
                pass
            c.setParent(None)
            c.deleteLater()
        self._canvases.clear()
        _app.processEvents()

    def _canvas(self):
        canvas = VCCanvas()
        self._canvases.append(canvas)
        canvas.set_edit_mode(True)
        return canvas

    def _widget(self, canvas, type_name, pos=QPoint(40, 40)):
        return canvas._add_widget(type_name, pos)


class EffectFitsWidgetTest(_CanvasTest):
    """Capability-Abgleich pro Widget-Typ."""

    def test_button_and_display_accept_anything(self):
        canvas = self._canvas()
        btn = self._widget(canvas, "VCButton")
        disp = self._widget(canvas, "VCEffectDisplay")
        # Auch ein parameterloser Effekt (Szene/Snap) laesst sich togglen/anzeigen.
        self.assertTrue(canvas._effect_fits_widget(btn, CAPS_NONE))
        self.assertTrue(canvas._effect_fits_widget(disp, CAPS_NONE))

    def test_slider_needs_numeric_param(self):
        canvas = self._canvas()
        sld = self._widget(canvas, "VCSlider")
        self.assertFalse(canvas._effect_fits_widget(sld, CAPS_NONE))     # paramlos -> rot
        self.assertTrue(canvas._effect_fits_widget(sld, CAPS_SPEED))     # Speed -> gruen
        self.assertTrue(canvas._effect_fits_widget(sld, CAPS_INT_PARAM)) # int-Param -> gruen

    def test_encoder_and_stepper_need_numeric_param(self):
        canvas = self._canvas()
        enc = self._widget(canvas, "VCEncoder")
        stp = self._widget(canvas, "VCStepper")
        self.assertFalse(canvas._effect_fits_widget(enc, CAPS_NONE))
        self.assertTrue(canvas._effect_fits_widget(enc, CAPS_INTENSITY))
        self.assertFalse(canvas._effect_fits_widget(stp, CAPS_NONE))
        self.assertTrue(canvas._effect_fits_widget(stp, CAPS_INT_PARAM))

    def test_speeddial_needs_speed(self):
        canvas = self._canvas()
        dial = self._widget(canvas, "VCSpeedDial")
        self.assertFalse(canvas._effect_fits_widget(dial, CAPS_NONE))
        self.assertFalse(canvas._effect_fits_widget(dial, CAPS_COLORS))
        self.assertTrue(canvas._effect_fits_widget(dial, CAPS_SPEED))

    def test_color_needs_colors(self):
        canvas = self._canvas()
        col = self._widget(canvas, "VCColor")
        self.assertFalse(canvas._effect_fits_widget(col, CAPS_NONE))
        self.assertFalse(canvas._effect_fits_widget(col, CAPS_SPEED))
        self.assertTrue(canvas._effect_fits_widget(col, CAPS_COLORS))

    def test_xypad_needs_movement(self):
        canvas = self._canvas()
        pad = self._widget(canvas, "VCXYPad")
        self.assertFalse(canvas._effect_fits_widget(pad, CAPS_NONE))
        self.assertFalse(canvas._effect_fits_widget(pad, CAPS_SPEED))
        self.assertTrue(canvas._effect_fits_widget(pad, CAPS_MOVEMENT))

    def test_effect_editor_needs_params(self):
        canvas = self._canvas()
        box = self._widget(canvas, "VCEffectEditor")
        self.assertFalse(canvas._effect_fits_widget(box, CAPS_NONE))
        self.assertTrue(canvas._effect_fits_widget(box, CAPS_INT_PARAM))


class DragTargetValidTest(_CanvasTest):
    """Typ-Huerde + Capability-Check zusammen (mit echtem function_capabilities)."""

    UNKNOWN_FID = 9_999_999     # keine solche Funktion -> leere Capabilities

    def test_non_droppable_widget_is_invalid(self):
        canvas = self._canvas()
        label = self._widget(canvas, "VCLabel")
        # Ein Label nimmt nie einen Effekt-Drop an -> immer rot.
        self.assertFalse(canvas._drag_target_valid(label, self.UNKNOWN_FID))

    def test_button_valid_even_for_unknown_effect(self):
        canvas = self._canvas()
        btn = self._widget(canvas, "VCButton")
        self.assertTrue(canvas._drag_target_valid(btn, self.UNKNOWN_FID))

    def test_slider_invalid_for_paramless_effect(self):
        canvas = self._canvas()
        sld = self._widget(canvas, "VCSlider")
        # Unbekannte Funktion -> keine Params -> Fader rot.
        self.assertFalse(canvas._drag_target_valid(sld, self.UNKNOWN_FID))


class DragHighlightInfoTest(_CanvasTest):
    """Ziel-Suche unter dem Cursor (childAt) + Validitaet als Tupel."""

    UNKNOWN_FID = 9_999_999

    def _shown_canvas(self):
        canvas = self._canvas()
        canvas.resize(800, 600)
        canvas.show()
        _app.processEvents()
        return canvas

    def test_over_widget_returns_widget(self):
        canvas = self._shown_canvas()
        btn = self._widget(canvas, "VCButton", QPoint(100, 100))
        btn.resize(80, 40)
        btn.show()
        _app.processEvents()
        center = btn.geometry().center()
        target, valid = canvas._drag_highlight_info(center, self.UNKNOWN_FID)
        self.assertIs(target, btn)
        self.assertTrue(valid)                 # Button = immer gueltig

    def test_over_empty_canvas_returns_none(self):
        canvas = self._shown_canvas()
        self._widget(canvas, "VCButton", QPoint(100, 100))
        target, valid = canvas._drag_highlight_info(QPoint(600, 500), self.UNKNOWN_FID)
        self.assertIsNone(target)
        self.assertFalse(valid)


if __name__ == "__main__":
    unittest.main()
