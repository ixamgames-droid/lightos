"""UI-134: der Gesten-Dialog sagt unter Windows, warum Drei-Finger-Tippen nicht ankommt.

**Befund (B, Finger-Probe 15.11.2026, Windows 11).** Drei Finger TIPPEN kam
nie in der App an - Windows nutzt es als Systemgeste; drei Finger beim Ziehen
schon. LightOS stellt die Windows-Einstellung nicht selbst um, nennt sie aber.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel                    # noqa: E402

from src.ui.widgets import gesten_dialog                              # noqa: E402

_app = QApplication.instance() or QApplication([])


class WindowsHinweisTest(unittest.TestCase):

    def _dialog(self, windows: bool):
        with mock.patch.object(gesten_dialog, "_ist_windows", return_value=windows):
            d = gesten_dialog.GestenDialog(pfad=os.devnull)
        self.addCleanup(d.deleteLater)
        return d

    def test_unter_windows_nennt_er_die_einstellung(self):
        d = self._dialog(True)
        label = d.findChild(QLabel, "gesten_windows_hinweis")
        self.assertIsNotNone(label)
        text = label.text()
        self.assertIn("Drei- und Vier-Finger-Gesten", text)
        self.assertIn("Windows-Einstellungen", text)
        self.assertIn("nicht selbst", text, "LightOS stellt nichts am System um")

    def test_sonst_kein_hinweis(self):
        d = self._dialog(False)
        self.assertIsNone(d.findChild(QLabel, "gesten_windows_hinweis"))


if __name__ == "__main__":
    unittest.main()
