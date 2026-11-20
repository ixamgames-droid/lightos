"""UI-134: der Gesten-Dialog sagt unter Windows, warum Drei-Finger-Tippen nicht ankommt.

**Befund (B, Finger-Probe 15.11.2026, Windows 11).** Drei Finger TIPPEN kam
nie in der App an - Windows nutzt es als Systemgeste; drei Finger beim Ziehen
schon. LightOS stellt die Windows-Einstellung nicht selbst um, nennt sie aber.

**Stand 16.11.** Den Hinweis liefert inzwischen UI-136 (4) (``system_gesten``,
eine Zeile oben im Dialog, auch fuer Linux). Der eigene Hinweis von UI-134
unter der Drei-Finger-Auswahl ist deshalb wieder entfernt: zwei Hinweise zum
selben Thema, mit verschieden geschriebenen Namen der Einstellung, waeren
schlechter als einer. Diese Datei haelt fest, dass es bei EINEM bleibt und dass
er das Noetige sagt.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel                    # noqa: E402

from src.ui import system_gesten                                      # noqa: E402
from src.ui.widgets import gesten_dialog                              # noqa: E402

_app = QApplication.instance() or QApplication([])


class WindowsHinweisTest(unittest.TestCase):

    def _dialog(self, zeile: str):
        d = gesten_dialog.GestenDialog(pfad=os.devnull, system_zeile=zeile)
        self.addCleanup(d.deleteLater)
        return d

    def test_unter_windows_genau_ein_hinweis_mit_der_einstellung(self):
        zeile = system_gesten.dialog_zeile("win32", lauf=lambda *a, **k: None)
        self.assertTrue(zeile, "unter Windows gibt es immer einen Hinweis")
        d = self._dialog(zeile)
        treffer = [w.text() for w in d.findChildren(QLabel)
                   if "Drei- und Vier-Finger" in w.text()]
        self.assertEqual(1, len(treffer), treffer)
        self.assertIn("Einstellungen", treffer[0])
        self.assertIn("Tippen", treffer[0])
        self.assertIsNone(d.findChild(QLabel, "gesten_windows_hinweis"),
                          "der zweite Hinweis (UI-134) ist durch UI-136 ersetzt")

    def test_ohne_system_gesten_kein_hinweis(self):
        d = self._dialog("")
        self.assertEqual([], [w.text() for w in d.findChildren(QLabel)
                              if "Drei- und Vier-Finger" in w.text()])


if __name__ == "__main__":
    unittest.main()
