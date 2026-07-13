"""CDX-02 (+Review CDX-02b): Das Eingangs-Status-Label muss den AKTUELLEN Patch-
Stand ``state.universes`` lesen — genau das, was ``_render_frame`` zum Verwerfen der
gemergten Kanaele nutzt. Ist das Ziel-Universe nicht als Output gepatcht (``out_u
not in state.universes``), darf nicht faelschlich "Aktiv" stehen, sondern "Aktiv,
aber wirkungslos ...".

Bewusst NICHT ueber den ``input_unconfigured``-Zaehler: der wird erst vom RX-Thread
NACH dem ersten empfangenen+gerenderten Frame hochgezaehlt -> beim Klick auf
"Uebernehmen" stuende er noch auf 0 (Warnung verpasst) bzw. bliebe nach nachtraeglichem
Patchen stehen (falsche Warnung). Der direkte ``universes``-Check stimmt sofort.
"""
import types
import unittest

from src.ui.widgets import output_config
from src.ui.widgets.output_config import OutputConfigDialog


class _FakeState:
    def __init__(self, universes):
        # wie AppState.universes: dict {universe_num -> Universe-Objekt}
        self.universes = universes


class InputStatusLabelTest(unittest.TestCase):
    def _text(self, universes, in_u=1, out_u=7, mode="HTP"):
        # self wird in _input_status_text nicht benutzt -> Dummy genuegt.
        dummy = types.SimpleNamespace()
        orig = output_config.get_state
        output_config.get_state = lambda: _FakeState(universes)
        try:
            return OutputConfigDialog._input_status_text(dummy, in_u, out_u, mode)
        finally:
            output_config.get_state = orig

    def test_unpatched_out_shows_wirkungslos(self):
        # out_u=7 NICHT gepatcht -> sofort "wirkungslos" (auch ohne je empfangenen Frame).
        txt = self._text({1: object(), 2: object()})   # 7 fehlt
        self.assertIn("wirkungslos", txt)
        self.assertIn("U7", txt)
        self.assertNotEqual(txt, "Aktiv: U1 -> U7 (HTP)")

    def test_patched_out_shows_plain_aktiv(self):
        # out_u=7 gepatcht -> normales "Aktiv" (unabhaengig von empfangenen Frames).
        txt = self._text({7: object()})
        self.assertEqual(txt, "Aktiv: U1 -> U7 (HTP)")

    def test_other_universe_patched_still_wirkungslos(self):
        # Nur ein ANDERES Universe gepatcht -> unser out_u=7 bleibt wirkungslos.
        txt = self._text({5: object()}, out_u=7)
        self.assertIn("wirkungslos", txt)

    def test_empty_universes_is_wirkungslos(self):
        txt = self._text({}, out_u=9)
        self.assertIn("wirkungslos", txt)

    def test_missing_field_falls_back_to_aktiv(self):
        # Kein universes-Feld am State -> defensiv normales "Aktiv" (kein Crash).
        dummy = types.SimpleNamespace()
        orig = output_config.get_state
        output_config.get_state = lambda: types.SimpleNamespace()  # kein Feld
        try:
            txt = OutputConfigDialog._input_status_text(dummy, 2, 9, "LTP")
        finally:
            output_config.get_state = orig
        self.assertEqual(txt, "Aktiv: U2 -> U9 (LTP)")


if __name__ == "__main__":
    unittest.main()
