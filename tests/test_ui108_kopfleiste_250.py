"""UI-108: drei Fehler in der Kopfleiste (Sektionsleiste), gemeldet am
01.11.2026 aus der echten App bei 250 % (Windows 11 x64, Startfenster
1400 px breit):

1. **Page-Pfeile leer.** ``<`` und ``>`` sind 22 px breit, das Stylesheet gibt
   jeder Taste aber 10 px Innenabstand links und rechts plus Rahmen — fuer das
   Zeichen blieb 0 px. Das gilt bei jeder Skalierung.
2. **Beat-Punkt eckig.** 26×26 px mit 4 px Rand links/rechts lassen 18×22 px;
   ein Eckenradius von 13 px passt nicht hinein, Qt zeichnet dann ein dunkles
   Viereck statt eines Kreises.
3. **„🔒 LO…“.** Das BPM-Abzeichen wechselt zur Laufzeit zwischen AUTO/MAN/LOCK
   (z. B. beim Freeze). Bis zum naechsten Layout-Durchlauf stand der lange Text
   in der alten, schmalen Breite — und die Tasten daneben (STOP ALL, BLACKOUT)
   sprangen bei jedem Wechsel um gut 20 px.
"""
from __future__ import annotations

import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

import src.ui.main_window as MW  # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


class _StubMgr:
    """BPM-Manager, der einen bestimmten Zustand meldet; alles andere echt."""

    def __init__(self, echt, gesperrt):
        self._echt = echt
        self.is_locked = gesperrt

    def __getattr__(self, name):
        return getattr(self._echt, name)


class KopfleisteTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _app()
        cls.w = MW.MainWindow()
        cls.w._hw_timer.stop()
        cls.w.resize(1400, 870)
        cls.w.show()
        for _ in range(3):
            _app().processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.w.hide()
        cls.w.deleteLater()
        _app().processEvents()

    def _pfeile(self):
        bar = self.w._section_bar
        return [b for b in bar.findChildren(QPushButton)
                if b.toolTip().startswith(("Vorherige Page", "Nächste Page"))]

    def test_page_pfeile_zeigen_ihr_zeichen(self):
        pfeile = self._pfeile()
        self.assertEqual(len(pfeile), 2)
        for b in pfeile:
            self.assertIn(b.text(), ("<", ">"))
            self.assertLessEqual(b.sizeHint().width(), b.width(),
                                 f"{b.text()!r}: braucht {b.sizeHint().width()} px, hat {b.width()}")

    def test_beat_punkt_ist_rund(self):
        ind = self.w._bpm_indicator
        for stil in (self.w._BPM_DOT_IDLE, ind.styleSheet()):
            radius = int(re.search(r"border-radius:\s*(\d+)px", stil).group(1))
            m = re.search(r"margin:\s*(\d+)px(?:\s+(\d+)px)?", stil)
            oben = int(m.group(1))
            seite = int(m.group(2)) if m.group(2) else oben
            innen = min(ind.width() - 2 * seite, ind.height() - 2 * oben)
            self.assertLessEqual(2 * radius, innen, stil)

    def test_bpm_abzeichen_haelt_seine_breite_beim_wechsel(self):
        w = self.w
        lbl = w._lbl_bpm_mode
        echt = w._bpm_mgr
        if echt is None:
            self.skipTest("kein BPM-Manager")
        stopp = next(b for b in w._section_bar.findChildren(QPushButton) if b.text() == "STOP ALL")
        try:
            w._bpm_mgr = _StubMgr(echt, False)
            w._update_bpm_mode_badge()
            for _ in range(3):
                _app().processEvents()
            x_vorher, breite_vorher = stopp.x(), lbl.width()
            w._bpm_mgr = _StubMgr(echt, True)
            w._update_bpm_mode_badge()
            # OHNE Layout-Durchlauf: der lange Text passt schon jetzt
            self.assertIn("LOCK", lbl.text())
            self.assertGreaterEqual(lbl.width(), lbl.sizeHint().width(),
                                    f"„{lbl.text()}“ in {lbl.width()} px")
            for _ in range(3):
                _app().processEvents()
            self.assertEqual(lbl.width(), breite_vorher, "Abzeichen aendert seine Breite")
            self.assertEqual(stopp.x(), x_vorher, "STOP ALL springt beim Wechsel")
        finally:
            w._bpm_mgr = echt
            w._update_bpm_mode_badge()


if __name__ == "__main__":
    unittest.main()
