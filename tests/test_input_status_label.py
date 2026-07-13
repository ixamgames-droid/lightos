"""CDX-02: Das Eingangs-Status-Label muss den von NET-07 gesetzten Zaehler
``state.input_unconfigured`` lesen. Ist das Ziel-Universe nicht als Output
gepatcht (Zaehler > 0), darf nicht mehr faelschlich "Aktiv" stehen, sondern
"Aktiv, aber wirkungslos ...".

Die Label-Logik (``_input_status_text``) wird direkt getestet — der Zaehler
wird im Betrieb erst bei echtem Netzempfang hochgezaehlt, hier mit einem
Fake-State injiziert.
"""
import types
import unittest

from src.ui.widgets import output_config
from src.ui.widgets.output_config import OutputConfigDialog


class _FakeState:
    def __init__(self, unconf):
        self.input_unconfigured = unconf


class InputStatusLabelTest(unittest.TestCase):
    def _text(self, unconf, in_u=1, out_u=7, mode="HTP"):
        # self wird in _input_status_text nicht benutzt -> Dummy genuegt.
        dummy = types.SimpleNamespace()
        orig = output_config.get_state
        output_config.get_state = lambda: _FakeState(unconf)
        try:
            return OutputConfigDialog._input_status_text(dummy, in_u, out_u, mode)
        finally:
            output_config.get_state = orig

    def test_unconfigured_shows_wirkungslos(self):
        txt = self._text({7: 3})
        self.assertIn("wirkungslos", txt)
        self.assertIn("U7", txt)
        self.assertNotEqual(txt, "Aktiv: U1 -> U7 (HTP)")

    def test_configured_shows_plain_aktiv(self):
        txt = self._text({})
        self.assertEqual(txt, "Aktiv: U1 -> U7 (HTP)")

    def test_other_universe_unconfigured_does_not_affect(self):
        # Zaehler steht nur fuer ein anderes Universe -> unser out_u ist ok.
        txt = self._text({5: 2}, out_u=7)
        self.assertEqual(txt, "Aktiv: U1 -> U7 (HTP)")

    def test_zero_counter_is_not_wirkungslos(self):
        txt = self._text({7: 0})
        self.assertEqual(txt, "Aktiv: U1 -> U7 (HTP)")

    def test_missing_field_falls_back_to_aktiv(self):
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
