"""UI-111: EIN Touch-Zustand — ``touch_keyboard`` wird eingerichtet.

Befund Touch-Audit 11.11.2026 (C-01/A-03): ``touch_keyboard.install()`` hatte
keinen Aufrufer, ``is_touch_mode()`` war deshalb immer False — auch mit
``--touch``. Die groesseren Programmer-Regler (M2.5), die Laser-Bausteine und
der VC-Effekt-Editor fragten genau das ab und blieben klein.
"""
from __future__ import annotations

import os
import pathlib
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication            # noqa: E402

from src.ui import touch_keyboard as tk                # noqa: E402

_app = QApplication.instance() or QApplication([])
_WURZEL = pathlib.Path(__file__).resolve().parents[1]


class _Ch:
    def __init__(self, attr="dimmer", default=0, name="Dimmer"):
        self.attribute = attr
        self.default_value = default
        self.name = name


class _StateStub:
    def get_programmer_value(self, fid, attr, head=0):
        return None

    def set_programmer_value(self, fid, attr, value, undoable=False, head=0):
        pass


def _regler():
    from src.ui.views.programmer_view import AttributeSlider
    return AttributeSlider(_Ch(), [], _StateStub())


class TouchZustandTest(unittest.TestCase):

    def setUp(self):
        alt = tk.is_touch_mode()
        self.addCleanup(tk.setze_touch_modus, alt)

    def test_setze_touch_modus(self):
        tk.setze_touch_modus(True)
        self.assertTrue(tk.is_touch_mode())
        tk.setze_touch_modus(False)
        self.assertFalse(tk.is_touch_mode())

    def test_programmer_regler_im_touch_modus_groesser(self):
        tk.setze_touch_modus(False)
        klein = _regler()
        tk.setze_touch_modus(True)
        gross = _regler()
        self.assertGreaterEqual(gross.minimumHeight(), 44)
        self.assertGreaterEqual(gross._slider.minimumHeight(), 30)
        self.assertLess(klein.minimumHeight(), 44)

    def test_install_nur_ein_filter(self):
        tk.install(_app, touch=False)
        f1 = getattr(_app, "_touch_keyboard_filter")
        tk.install(_app, touch=False)
        self.assertIs(getattr(_app, "_touch_keyboard_filter"), f1)
        self.assertFalse(tk.is_touch_mode())

    def test_main_richtet_ein_und_nur_mit_touch_an(self):
        quelle = (_WURZEL / "main.py").read_text(encoding="utf-8")
        self.assertIn("_touch_keyboard.install(app, touch=bool(getattr(args, \"touch\", False)))",
                      quelle, "main.py richtet die Touch-Tastatur ein, ohne Auto-Erkennung")
        self.assertLess(quelle.index("_touch_keyboard.install("),
                        quelle.index("window = MainWindow("), "vor dem Hauptfenster")

    def test_hauptfenster_setzt_den_zustand_vor_den_ansichten(self):
        from src.ui.main_window import MainWindow
        tk.setze_touch_modus(False)
        gelesen = []
        import src.ui.views.programmer_view as pv
        alt = pv.ProgrammerView._is_touch
        pv.ProgrammerView._is_touch = lambda self: gelesen.append(tk.is_touch_mode()) or alt(self)
        self.addCleanup(setattr, pv.ProgrammerView, "_is_touch", alt)
        w = MainWindow(touch=True)
        self.addCleanup(w.deleteLater)
        self.assertTrue(tk.is_touch_mode())
        if gelesen:
            self.assertTrue(all(gelesen), "Programmer las schon beim Bau den Touch-Zustand")
        w2 = MainWindow(touch=False)
        self.addCleanup(w2.deleteLater)
        self.assertFalse(tk.is_touch_mode())


if __name__ == "__main__":
    unittest.main()
