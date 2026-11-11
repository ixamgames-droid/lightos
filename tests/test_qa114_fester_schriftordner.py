"""QA-114: Windows-Offscreen-Tests messen mit festen Schriften, nicht mit dem,
was zufaellig im Schriftordner des Rechners liegt.

Befund (Windows-ARM, 02.11.2026, volles Gate): QA-99 setzte unter
Windows/offscreen ``QT_QPA_FONTDIR`` auf den ganzen Windows-Schriftordner. Liegen
dort zusaetzliche Schriften (z. B. aus Office), nimmt Qt fuer die Standardschrift
die alphabetisch erste Familie („AGA Arabesque“, Text 279 statt 148 px breit), und
QtWebEngine erbt sie als ``sans-serif``. 13 Testdateien wurden davon rot, ohne dass
am Code etwas war. ``tests/conftest.py`` legt deshalb einen festen Ordner im Temp
an, der nur Arial, Segoe UI, Segoe UI Symbol und Consolas enthaelt — dann misst
jeder Windows-Rechner wie die CI.
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import _qt_schriftordner
import conftest


class RegelTest(unittest.TestCase):
    """Die Regel an einem Attrappen-Windows-Ordner — laeuft auf jedem System."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="qa114_")
        self.windows = os.path.join(self._tmp.name, "Windows")
        self.fonts = os.path.join(self.windows, "Fonts")
        self.basis = os.path.join(self._tmp.name, "temp")
        os.makedirs(self.fonts)
        os.makedirs(self.basis)
        # Die fremde Erst-Schrift vom Befund: alphabetisch vor Arial.
        self._schrift("aga_arabesque.ttf", b"AGA")
        self._schrift("Bahnschrift.ttf", b"BAHN")
        self._schrift("arial.ttf", b"ARIAL-REGULAR")
        self._schrift("segoeui.ttf", b"SEGOE")
        self._schrift("consola.ttf", b"CONSOLAS")
        # Die Regel legt ihren Ordner unter tempfile.gettempdir() an — hier
        # in die Attrappe umgelenkt, damit der Test nichts im echten Temp laesst.
        self._temp = mock.patch.object(conftest.tempfile, "gettempdir",
                                       return_value=self.basis)
        self._temp.start()

    def tearDown(self):
        self._temp.stop()
        self._tmp.cleanup()

    def _schrift(self, name, inhalt):
        with open(os.path.join(self.fonts, name), "wb") as f:
            f.write(inhalt)

    def _inhalt_basis(self):
        """Was im Temp liegt — ohne die Sperrdatei (CDX-69), die bewusst bleibt."""
        return sorted(n for n in os.listdir(self.basis)
                      if n != _qt_schriftordner.SPERRDATEI)

    def _regel(self):
        umgebung = {"QT_QPA_PLATFORM": "offscreen", "WINDIR": self.windows}
        ordner = conftest._offscreen_schriftordner(umgebung, plattform="win32")
        self.assertEqual(umgebung.get("QT_QPA_FONTDIR"), ordner)
        return ordner

    def test_fremde_erstschrift_kommt_nicht_in_den_schriftordner(self):
        ordner = self._regel()
        self.assertIsNotNone(ordner)
        self.assertNotEqual(os.path.normcase(ordner), os.path.normcase(self.fonts),
                            "QT_QPA_FONTDIR zeigt auf den ganzen Windows-Schriftordner")
        self.assertEqual(sorted(os.listdir(ordner)),
                         ["arial.ttf", "consola.ttf", "segoeui.ttf"])

    def test_ordner_liegt_im_temp_und_enthaelt_kopien(self):
        ordner = self._regel()
        self.assertEqual(os.path.normcase(os.path.dirname(ordner)),
                         os.path.normcase(self.basis))
        with open(os.path.join(ordner, "arial.ttf"), "rb") as f:
            self.assertEqual(f.read(), b"ARIAL-REGULAR")

    def test_zweiter_lauf_nimmt_denselben_ordner_ohne_reste(self):
        """Parallele Segmente teilen sich den Ordner; es bleibt nichts liegen."""
        erster = self._regel()
        zweiter = self._regel()
        self.assertEqual(erster, zweiter)
        self.assertEqual(self._inhalt_basis(), [os.path.basename(erster)])

    def test_geaenderte_schrift_gibt_neuen_ordner(self):
        """Ein Windows-Update tauscht eine Schrift — der alte Ordner gilt nicht mehr."""
        alt = self._regel()
        self._schrift("arial.ttf", b"ARIAL-NACH-DEM-UPDATE")
        neu = self._regel()
        self.assertNotEqual(alt, neu)
        with open(os.path.join(neu, "arial.ttf"), "rb") as f:
            self.assertEqual(f.read(), b"ARIAL-NACH-DEM-UPDATE")

    def test_beschaedigter_ordner_wird_neu_aufgebaut(self):
        ordner = self._regel()
        os.remove(os.path.join(ordner, "segoeui.ttf"))
        with open(os.path.join(ordner, "fremd.ttf"), "wb") as f:
            f.write(b"X")
        wieder = self._regel()
        self.assertEqual(sorted(os.listdir(wieder)),
                         ["arial.ttf", "consola.ttf", "segoeui.ttf"])

    def test_gleichzeitiger_aufbau_nimmt_den_fertigen_ordner(self):
        """Ein paralleler Prozess war schneller: dessen fertiger Ordner gilt,
        der eigene halbe Aufbau verschwindet."""
        echtes_rename = os.rename

        def anderer_war_schneller(quelle, ziel):
            shutil.copytree(quelle, ziel)
            echtes_rename(quelle, ziel)          # wirft wie unter Windows: Ziel existiert

        with mock.patch.object(conftest.os, "rename", side_effect=anderer_war_schneller):
            ordner = self._regel()
        self.assertEqual(sorted(os.listdir(ordner)),
                         ["arial.ttf", "consola.ttf", "segoeui.ttf"])
        self.assertEqual(self._inhalt_basis(), [os.path.basename(ordner)])

    def test_ohne_eine_der_festen_schriften_bleibt_es_beim_windows_ordner(self):
        """Fehlen alle festen Schriften, ist der ganze Ordner besser als gar
        keiner (QA-99: sonst Ersatzkaestchen)."""
        for name in ("arial.ttf", "segoeui.ttf", "consola.ttf"):
            os.remove(os.path.join(self.fonts, name))
        self.assertEqual(self._regel(), self.fonts)
        self.assertEqual(self._inhalt_basis(), [])


@unittest.skipUnless(sys.platform == "win32", "nur Windows: dort setzt conftest den Schriftordner")
@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen", "nur im Offscreen-Lauf")
class WirkungTest(unittest.TestCase):
    """Im echten Testprozess: Qt kennt genau die festen Schriften, Standard ist Arial."""

    def setUp(self):
        ordner = os.environ.get("QT_QPA_FONTDIR", "")
        if not ordner or not os.path.isdir(ordner):
            self.skipTest("kein Schriftordner gesetzt")
        windows = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
        if (os.path.normcase(os.path.dirname(os.path.abspath(ordner)))
                not in (os.path.normcase(tempfile.gettempdir()),
                        os.path.normcase(windows))):
            self.skipTest("Schriftordner vom Aufrufer vorgegeben")

    def test_qt_sieht_nur_die_festen_schriften(self):
        from PySide6.QtGui import QFont, QFontDatabase, QFontInfo
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        familien = set(QFontDatabase.families())
        fremd = familien - {"Arial", "Segoe UI", "Segoe UI Symbol", "Consolas"}
        if fremd:
            self.fail(f"{len(fremd)} fremde Schriften im Testlauf, z. B. {sorted(fremd)[:5]}")
        self.assertEqual(QFontInfo(QFont()).family(), "Arial")


if __name__ == "__main__":
    unittest.main()
