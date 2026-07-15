"""UI-19: rohe select-Options-Tokens app-weit durch deutsche Labels ersetzen.

Sichert:
- die geteilte, Qt-freie `option_label`-Fallback-Kette (vc_effect_meta),
- Persistenz-Sicherheit: die Programmer-Matrix-Combos zeigen das deutsche Label,
  speichern aber weiter den ROHWERT (userData) — kein Bruch von Save/Load,
- VCStepper/VCEncoder zeigen Parameter-Label + Options-Label statt roher Tokens.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])


class TestOptionLabelPure(unittest.TestCase):
    """Reine Fallback-Kette (kein Qt): by_key -> Richtung -> Option -> Prettify."""

    def test_chain(self):
        from src.ui.virtualconsole.vc_effect_meta import option_label, prettify_option
        # kontextabhaengiger Override hat Vorrang
        self.assertEqual(option_label("reverse", "loop_mode"), "Rückwärts leeren")
        # ohne key: Richtungs-Label
        self.assertEqual(option_label("reverse"), "rückwärts")
        self.assertEqual(option_label("forward"), "vorwärts")
        # Option-Label
        self.assertEqual(option_label("normal"), "Normal")
        self.assertEqual(option_label("H"), "Horizontal")
        self.assertEqual(option_label("smooth"), "Weich")
        # unbekannt -> Prettify
        self.assertEqual(option_label("foo_bar"), "Foo bar")
        self.assertEqual(prettify_option("runner_count"), "Runner count")

    def test_vc_multi_delegates_to_shared_source(self):
        # der Live-Editor nutzt jetzt dieselbe geteilte Quelle (kein Duplikat mehr)
        from src.ui.virtualconsole import vc_multi_live_editor as m
        from src.ui.virtualconsole.vc_effect_meta import option_label
        self.assertIs(m._option_label, option_label)
        self.assertEqual(m._option_label("reverse", "loop_mode"), "Rückwärts leeren")


class TestMatrixComboPersistenceSafe(unittest.TestCase):
    """Combos zeigen das deutsche Label, speichern aber den Rohwert (userData)."""

    def test_color_order_combo_label_vs_rawvalue(self):
        from src.ui.views.rgb_matrix_view import RgbMatrixView
        v = RgbMatrixView()
        try:
            combo = v._color_order_combo
            datas = [combo.itemData(i) for i in range(combo.count())]
            texts = [combo.itemText(i) for i in range(combo.count())]
            # Rohwerte bleiben als userData erhalten (Save/Load unveraendert)
            self.assertEqual(datas, ["normal", "random", "pingpong"])
            # angezeigt wird das deutsche Label, NICHT der Rohwert
            self.assertIn("Normal", texts)
            self.assertIn("Zufällig", texts)
            for i in range(combo.count()):
                self.assertNotEqual(combo.itemText(i), combo.itemData(i),
                                    "Label darf nicht der Rohwert sein")
        finally:
            v.deleteLater()


class TestStepperEncoderLabels(unittest.TestCase):
    """VCStepper/VCEncoder: Parameter-Label + select-Options-Label statt Roh-Token."""

    def _mk(self, cls):
        w = cls()
        return w

    def test_stepper_fmt_and_label(self):
        from src.ui.virtualconsole.vc_stepper import VCStepper
        s = self._mk(VCStepper)
        try:
            s.param_key = "loop_mode"
            s._spec = lambda: SimpleNamespace(kind="select", label="Lauf-Modus",
                                              options=("forward", "reverse"))
            s._current_value = lambda: "reverse"
            self.assertEqual(s._fmt_value(), "Rückwärts leeren")   # Options-Label
            self.assertEqual(s._param_label(), "Lauf-Modus")        # ParamSpec.label
            # kein gebundener Effekt -> Fallback auf den rohen Key
            s._spec = lambda: None
            s.param_key = "runner_count"
            self.assertEqual(s._param_label(), "runner_count")
        finally:
            s.deleteLater()

    def test_encoder_fmt_and_label(self):
        from src.ui.virtualconsole.vc_encoder import VCEncoder
        e = self._mk(VCEncoder)
        try:
            e.param_key = "speed"
            e._spec = lambda: SimpleNamespace(kind="select", label="Geschwindigkeit",
                                              options=("normal", "smooth"))
            e._current_value = lambda: "smooth"
            self.assertEqual(e._fmt_value(), "Weich")
            self.assertEqual(e._param_label(), "Geschwindigkeit")
        finally:
            e.deleteLater()


if __name__ == "__main__":
    unittest.main()
