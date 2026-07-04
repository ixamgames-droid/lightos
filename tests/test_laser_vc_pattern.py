"""LAS-18: VC-Button „Laser-Muster abrufen" (LASER_PATTERN) — ruft eine
gespeicherte PaletteType.LASER-Palette in den Programmer (wirkt auf DMX-Lasern
wie dem L2600 direkt über die normale Ausgabe)."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.core.app_state as app_state
from src.ui.virtualconsole.vc_button import (VCButton, ButtonAction,
                                             BUTTON_ACTION_LABELS)


def _app():
    return QApplication.instance() or QApplication([])


class _FakeProgState:
    """Minimaler Programmer-State: apply_to_programmer schreibt hierher."""

    def __init__(self):
        self.programmer: dict = {}

    def get_patched_fixtures(self):
        return []

    def get_selected_fids(self):
        return []

    def set_programmer_value(self, fid, attr, value, undoable=False, head=0):
        key = attr if head == 0 else f"{attr}#{head}"
        self.programmer.setdefault(fid, {})[key] = int(value)


class VcLaserPatternTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self._orig = app_state.get_state
        self.state = _FakeProgState()
        app_state.get_state = lambda: self.state

    def tearDown(self):
        app_state.get_state = self._orig

    def _laser_palette(self, name, values):
        from src.core.engine.palette import (Palette, PaletteType,
                                             get_palette_manager)
        mgr = get_palette_manager()
        p = Palette(name=name, type=PaletteType.LASER)
        p.fixture_values = values
        mgr.add(p)
        return mgr, p

    def _btn(self, palette_name):
        b = VCButton()
        b.action = ButtonAction.LASER_PATTERN
        b.laser_palette = palette_name
        b.function_id = None
        return b

    def test_recall_applies_palette(self):
        mgr, p = self._laser_palette(
            "VC Test Muster", {7: {"gobo_wheel": 42, "laser_color": 100}})
        try:
            self._btn("VC Test Muster")._trigger_primary(True)
            self.assertEqual(self.state.programmer.get(7, {}).get("gobo_wheel"), 42)
            self.assertEqual(self.state.programmer.get(7, {}).get("laser_color"), 100)
        finally:
            mgr.remove(p)

    def test_release_is_ignored(self):
        mgr, p = self._laser_palette("VC Rel Muster", {7: {"gobo_wheel": 42}})
        try:
            self._btn("VC Rel Muster")._trigger_primary(False)   # nur Loslassen
            self.assertEqual(self.state.programmer, {})
        finally:
            mgr.remove(p)

    def test_unknown_palette_is_noop(self):
        # Nicht existierendes Muster → kein Crash, keine Programmer-Werte.
        self._btn("gibt es nicht")._trigger_primary(True)
        self.assertEqual(self.state.programmer, {})

    def test_empty_name_is_noop(self):
        self._btn("")._trigger_primary(True)
        self.assertEqual(self.state.programmer, {})

    def test_guard_skips_empty_and_targets_recorded_fids(self):
        # Sicherheit: leere fixture_values → apply_to_programmer wird NICHT
        # gerufen (kein Streuen auf alle Fixtures); befüllt → exakt diese fids.
        from src.core.engine import palette as palmod
        calls = []
        orig = palmod.Palette.apply_to_programmer
        palmod.Palette.apply_to_programmer = \
            lambda self, ids=None: calls.append(ids)
        mgr, pe = self._laser_palette("Leer2", {})
        _, pf = self._laser_palette("Voll2", {5: {"gobo_wheel": 1}})
        try:
            self._btn("Leer2")._trigger_primary(True)
            self.assertEqual(calls, [])                # leer → nie gerufen
            self._btn("Voll2")._trigger_primary(True)
            self.assertEqual(calls, [[5]])             # exakt die aufgenommenen
        finally:
            palmod.Palette.apply_to_programmer = orig
            mgr.remove(pe)
            mgr.remove(pf)

    def test_action_in_dropdown_labels(self):
        actions = {a for a, _ in BUTTON_ACTION_LABELS}
        self.assertIn(ButtonAction.LASER_PATTERN, actions)

    def test_laser_palette_survives_roundtrip(self):
        b = self._btn("Mein Kreis")
        b2 = VCButton()
        b2.apply_dict(b.to_dict())
        self.assertEqual(b2.action, ButtonAction.LASER_PATTERN)
        self.assertEqual(b2.laser_palette, "Mein Kreis")


if __name__ == "__main__":
    unittest.main()
