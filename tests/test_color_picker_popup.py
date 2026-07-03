"""Color-Picker soll ein schwebendes Popup-Fenster sein (nicht unten eingebettet).

Früher hängte der „Color Picker einbetten"-Toggle den Picker unten in den
Color-Tab → abgeschnitten. Jetzt öffnet er ein eigenes, NICHT-modales Fenster.
Getestet wird die Logik von ProgrammerView._toggle_embedded_color /
_on_color_window_closed auf leichten Fakes (ohne die ganze View zu bauen).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget, QPushButton

import src.ui.views.programmer_view as PV

_app = QApplication.instance() or QApplication([])


class _Host(QWidget):
    """Fake-Host (Dialog-Parent statt echter ProgrammerView): leiht sich die
    Fenster-Callbacks als KLASSEN-Attribute. Seit STAB-10 läuft finished über
    den Bound-Slot _on_color_window_finished (sender()-Adapter statt
    self-fangendem Lambda). Instanz-gebundene ``types.MethodType``-Attribute
    wären ein Selbst-Zyklus -> Host stürbe nur in der zyklischen GC (genau
    die getestete AV-Klasse)."""
    _on_color_window_closed = PV.ProgrammerView._on_color_window_closed
    _on_color_window_finished = PV.ProgrammerView._on_color_window_finished


def _host_and_tab():
    host = _Host()                         # dient als Dialog-Parent (statt self)
    tab = QWidget()
    btn = QPushButton(); btn.setCheckable(True); btn.setChecked(True)
    tab._cp_button = btn
    return host, tab, btn


class ColorPickerPopupTest(unittest.TestCase):
    def test_opens_non_modal_window_not_embedded(self):
        host, tab, _btn = _host_and_tab()
        PV.ProgrammerView._toggle_embedded_color(host, tab, True)
        win = getattr(tab, "_cp_window", None)
        self.assertIsNotNone(win)
        self.assertIsInstance(win, PV._ToolDialog)
        self.assertFalse(win.isModal())          # nicht-modal -> Programmer bedienbar
        # NICHT in den Tab eingebettet:
        self.assertFalse(hasattr(tab, "_embedded_cp"))
        # enthält einen ColorPicker
        from src.ui.widgets.color_picker import ColorPicker
        self.assertTrue(win.findChildren(ColorPicker))

    def test_reuses_same_window_on_retoggle(self):
        host, tab, _btn = _host_and_tab()
        PV.ProgrammerView._toggle_embedded_color(host, tab, True)
        win1 = tab._cp_window
        PV.ProgrammerView._toggle_embedded_color(host, tab, True)
        self.assertIs(tab._cp_window, win1)       # kein zweites Fenster

    def test_close_resets_toggle_and_ref(self):
        host, tab, btn = _host_and_tab()
        PV.ProgrammerView._toggle_embedded_color(host, tab, True)
        self.assertIsNotNone(tab._cp_window)
        PV.ProgrammerView._on_color_window_closed(host, tab)
        self.assertIsNone(tab._cp_window)
        self.assertFalse(btn.isChecked())         # Toggle gelöst

    def test_toggle_off_closes(self):
        host, tab, _btn = _host_and_tab()
        PV.ProgrammerView._toggle_embedded_color(host, tab, True)
        self.assertIsNotNone(tab._cp_window)
        PV.ProgrammerView._toggle_embedded_color(host, tab, False)  # schließt -> finished
        self.assertIsNone(getattr(tab, "_cp_window", None))


if __name__ == "__main__":
    unittest.main()
