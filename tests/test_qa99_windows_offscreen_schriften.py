"""QA-99: der Windows-Offscreen-Lauf bekommt Schriften.

Unter Windows bringt die Qt-Plattform „offscreen“ keine Schriftquelle mit. Ohne
QT_QPA_FONTDIR kennt sie keine einzige Schrift, jeder Text wird mit
Ersatzkaestchen vermessen, und Layout-Tests werden rot, ohne dass am Code etwas
ist (gemessen 18.10.2026 auf main: 9 Dateien im Windows-Gate). ``tests/conftest.py``
setzt deshalb unter Windows den Systemschriftordner, wenn die Plattform
„offscreen“ ist und der Aufrufer keinen Schriftordner vorgibt. Linux und macOS
bleiben unberuehrt.
"""
import os
import subprocess
import sys
import tempfile
import unittest

import conftest

_HIER = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HIER)


class RegelTest(unittest.TestCase):
    """Die Regel selbst, an einer nachgebauten Umgebung — laeuft auf jedem System."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="qa99_")
        self.windows = self._tmp.name
        os.makedirs(os.path.join(self.windows, "Fonts"))

    def tearDown(self):
        self._tmp.cleanup()

    def _umgebung(self, **mehr):
        umgebung = {"QT_QPA_PLATFORM": "offscreen", "WINDIR": self.windows}
        umgebung.update(mehr)
        return umgebung

    def test_windows_offscreen_ohne_vorgabe_bekommt_den_schriftordner(self):
        umgebung = self._umgebung()
        ordner = conftest._offscreen_schriftordner(umgebung, plattform="win32")
        self.assertEqual(ordner, os.path.join(self.windows, "Fonts"))
        self.assertEqual(umgebung["QT_QPA_FONTDIR"], ordner)

    def test_systemroot_wenn_windir_fehlt(self):
        umgebung = {"QT_QPA_PLATFORM": "offscreen", "SystemRoot": self.windows}
        conftest._offscreen_schriftordner(umgebung, plattform="win32")
        self.assertEqual(umgebung.get("QT_QPA_FONTDIR"), os.path.join(self.windows, "Fonts"))

    def test_vorgabe_des_aufrufers_gewinnt(self):
        umgebung = self._umgebung(QT_QPA_FONTDIR="VORGABE")
        self.assertIsNone(conftest._offscreen_schriftordner(umgebung, plattform="win32"))
        self.assertEqual(umgebung["QT_QPA_FONTDIR"], "VORGABE")

    def test_andere_plattform_als_offscreen_bleibt_unberuehrt(self):
        for qpa in ("windows", "minimal", ""):
            with self.subTest(qpa=qpa):
                umgebung = self._umgebung(QT_QPA_PLATFORM=qpa)
                self.assertIsNone(conftest._offscreen_schriftordner(umgebung, plattform="win32"))
                self.assertNotIn("QT_QPA_FONTDIR", umgebung)

    def test_linux_und_macos_bleiben_unberuehrt(self):
        for plattform in ("linux", "darwin"):
            with self.subTest(plattform=plattform):
                umgebung = self._umgebung()
                vorher = dict(umgebung)
                self.assertIsNone(conftest._offscreen_schriftordner(umgebung, plattform=plattform))
                self.assertEqual(umgebung, vorher)

    def test_fehlender_schriftordner_setzt_nichts(self):
        umgebung = self._umgebung(WINDIR=os.path.join(self.windows, "gibt_es_nicht"))
        self.assertIsNone(conftest._offscreen_schriftordner(umgebung, plattform="win32"))
        self.assertNotIn("QT_QPA_FONTDIR", umgebung)


@unittest.skipUnless(sys.platform == "win32", "nur Windows: dort fehlt offscreen die Schriftquelle")
@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen", "nur im Offscreen-Lauf")
class WirkungTest(unittest.TestCase):
    """Im echten Testprozess: Qt kennt Schriften, Text wird mit echten Glyphen vermessen."""

    def test_qt_kennt_schriften(self):
        from PySide6.QtGui import QFont, QFontDatabase, QFontInfo
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        self.assertGreater(len(QFontDatabase.families()), 0,
                           "offscreen ohne Schriften — QT_QPA_FONTDIR fehlt")
        self.assertTrue(QFontInfo(QFont()).family(), "Standardschrift loest auf keine Familie auf")

    def test_ein_frischer_lauf_ohne_vorgabe_bekommt_schriften(self):
        """Der Aufrufer setzt KEINEN Schriftordner — conftest muss es tun."""
        umgebung = {k: v for k, v in os.environ.items()
                    if k not in ("QT_QPA_FONTDIR", "LIGHTOS_HARDEN_EXIT_ALL", "LIGHTOS_HARDEN_EXIT")}
        umgebung["QT_QPA_PLATFORM"] = "offscreen"
        ziel = os.path.relpath(os.path.abspath(__file__), _REPO) + "::WirkungTest::test_qt_kennt_schriften"
        lauf = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", ziel],
            cwd=_REPO, env=umgebung, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=240,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(lauf.returncode, 0, lauf.stdout[-2000:] + lauf.stderr[-1000:])
        self.assertIn("1 passed", lauf.stdout)


if __name__ == "__main__":
    unittest.main()
