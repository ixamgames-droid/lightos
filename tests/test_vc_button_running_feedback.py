"""VC-Button On-Screen-Rueckmeldung 2026-06-15.

David: „oben rechts zeigt nichts mehr laeuft, aber die Geraete bewegen sich noch."
Ursache: ein FUNCTION_TOGGLE-Pad leuchtete nur waehrend des Drucks (_pressed),
nicht solange seine Funktion lief. Jetzt spiegelt der Button den Laufzustand
(_function_running) — an, solange der Effekt laeuft; aus, sobald er endet (auch
per StopAll/Selbstende).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.core.app_state import get_state

_app = QApplication.instance() or QApplication([])


class ButtonRunningFeedbackTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_state().function_manager
        self.fn = self.fm.new_efx("FeedbackTest")
        self.btn = VCButton("Pad")
        self.btn.action = ButtonAction.FUNCTION_TOGGLE
        self.btn.function_id = self.fn.id

    def tearDown(self):
        self.fm.stop(self.fn.id)
        self.fm.remove(self.fn.id)

    def test_off_when_not_running(self):
        self.assertFalse(self.btn._function_running())

    def test_on_while_running(self):
        self.fm.start(self.fn.id)
        self.assertTrue(self.btn._function_running())

    def test_off_after_stop(self):
        self.fm.start(self.fn.id)
        self.fm.stop(self.fn.id)
        self.assertFalse(self.btn._function_running())

    def test_off_after_stop_all(self):
        self.fm.start(self.fn.id)
        self.fm.stop_all()
        self.assertFalse(self.btn._function_running())

    def test_non_function_action_is_never_lit(self):
        b = VCButton("Blackout")
        b.action = ButtonAction.BLACKOUT
        self.assertFalse(b._function_running())

    def test_no_function_bound(self):
        b = VCButton("Leer")
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = None
        self.assertFalse(b._function_running())

    def test_extra_running_function_lights_group_button(self):
        extra = self.fm.new_efx("FeedbackExtra")
        try:
            self.btn.function_ids = [extra.id]
            self.fm.start(extra.id)
            self.assertTrue(self.btn._function_running())
        finally:
            self.fm.stop(extra.id)
            self.fm.remove(extra.id)

    def test_missing_extra_binding_is_reported(self):
        self.btn.function_ids = [987654321]
        self.assertTrue(self.btn._binding_unresolved())


if __name__ == "__main__":
    unittest.main()
