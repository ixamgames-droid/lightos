"""Stille No-Op-Fehlerstellen sichtbar machen (fix/efx-vc-silent-noop, 2026-06-24).

David: „VC-Buttons schalten die Moving-Head-Abfahrwege, aber die fahren nicht ab
und im Simple Desk aendert sich kein Kanal." Ursache war eine Kette stiller
No-Ops:

  1. ``FunctionManager.start(fid)`` ignorierte eine nicht existierende ID
     kommentarlos (tote VC-Bindung -> "Button tut nichts" ohne Hinweis).
  2. ``EfxInstance.write()`` ist bei leerer Geraeteliste ein stiller No-Op
     (kein Pan/Tilt-DMX) -> Moving Head bleibt stehen, Simple Desk zeigt nichts.

Dieser Test sichert die neuen Diagnose-/Hinweis-Pfade ab:
  - ``FunctionManager.start_problem(fid)`` benennt das Problem (fuer UI-Hinweise).
  - ``start()`` warnt im Log bei toter ID bzw. EFX ohne Geraete.
  - ``EfxInstance.write()`` bleibt nachweislich ein No-Op (Phase advanced nicht).
  - ``VCButton._binding_unresolved()`` erkennt die tote Bindung (roter Marker).
"""
import io
import os
import unittest
from contextlib import redirect_stdout

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.function_manager import FunctionManager
from src.core.engine.efx import EfxInstance, EfxFixture
from src.core.engine.scene import Scene
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction

_app = QApplication.instance() or QApplication([])


class StartProblemTest(unittest.TestCase):
    def setUp(self):
        self.fm = FunctionManager()

    def test_missing_id_is_a_problem(self):
        self.assertIn("existiert nicht", self.fm.start_problem(424242) or "")

    def test_efx_without_fixtures_is_a_problem(self):
        efx = self.fm.add(EfxInstance("Kreis"))
        prob = self.fm.start_problem(efx.id)
        self.assertIsNotNone(prob)
        self.assertIn("keine Geräte", prob)

    def test_efx_with_fixtures_is_fine(self):
        efx = self.fm.add(EfxInstance("Kreis"))
        efx.fixtures = [EfxFixture(fid=7), EfxFixture(fid=8)]
        self.assertIsNone(self.fm.start_problem(efx.id))

    def test_non_efx_without_fixtures_attr_is_fine(self):
        # Scene hat keine .fixtures-Liste -> darf keinen Fehlalarm ausloesen.
        scene = self.fm.add(Scene("Snap"))
        self.assertIsNone(self.fm.start_problem(scene.id))


class StartWarningTest(unittest.TestCase):
    def setUp(self):
        self.fm = FunctionManager()

    def test_start_missing_id_warns_and_does_not_run(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.fm.start(999999)
        self.assertIn("WARN", buf.getvalue())
        self.assertFalse(self.fm.is_running(999999))

    def test_start_empty_efx_warns(self):
        efx = self.fm.add(EfxInstance("Eight"))
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.fm.start(efx.id)
        out = buf.getvalue()
        self.assertIn("WARN", out)
        self.assertIn("keine Geräte", out)
        # Gestartet ist sie trotzdem (nur wirkungslos) — das spiegelt den Button.
        self.assertTrue(self.fm.is_running(efx.id))

    def test_start_efx_with_fixtures_is_silent(self):
        efx = self.fm.add(EfxInstance("Kreis"))
        efx.fixtures = [EfxFixture(fid=7)]
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.fm.start(efx.id)
        self.assertNotIn("WARN", buf.getvalue())


class EfxWriteNoOpTest(unittest.TestCase):
    """Der eigentliche Wurzelbefund: ohne Geraete schreibt write() nichts —
    nachweisbar daran, dass die Phase nicht fortschreitet (der Guard greift
    VOR _advance)."""

    def test_empty_fixtures_does_not_advance(self):
        efx = EfxInstance("Kreis")
        efx.fixtures = []
        efx.start()
        self.assertEqual(efx._phase, 0.0)
        efx.write({}, [], 0.5)          # 0.5 s — wuerde sonst klar fortschreiten
        self.assertEqual(efx._phase, 0.0, "write() haette ohne Geraete nicht ticken duerfen")

    def test_with_fixtures_advances(self):
        efx = EfxInstance("Kreis")
        efx.fixtures = [EfxFixture(fid=7)]
        efx.start()
        efx.write({}, [], 0.5)          # leere universes -> kein DMX, aber Phase tickt
        self.assertGreater(efx._phase, 0.0, "mit Geraeten muss die Phase fortschreiten")


class ButtonUnresolvedMarkerTest(unittest.TestCase):
    def setUp(self):
        self.fm = FunctionManager()
        self.efx = self.fm.add(EfxInstance("Kreis"))

    def _button(self, action, fid):
        b = VCButton("Pad")
        b.action = action
        b.function_id = fid
        return b

    def test_dangling_id_is_unresolved(self):
        # _binding_unresolved nutzt den globalen State; daher gegen einen echten,
        # garantiert fehlenden ID-Wert testen (sehr hohe Zahl, nie vergeben).
        b = self._button(ButtonAction.FUNCTION_TOGGLE, 987654321)
        self.assertTrue(b._binding_unresolved())

    def test_none_binding_is_not_unresolved(self):
        b = self._button(ButtonAction.FUNCTION_TOGGLE, None)
        self.assertFalse(b._binding_unresolved())

    def test_non_function_action_is_not_unresolved(self):
        b = self._button(ButtonAction.BLACKOUT, 987654321)
        self.assertFalse(b._binding_unresolved())


if __name__ == "__main__":
    unittest.main()
