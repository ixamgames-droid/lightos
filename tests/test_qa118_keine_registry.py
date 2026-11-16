"""QA-118 (d): die Testsuite aendert die Registry des Rechners nicht.

**Der Befund (15.11.2026, Windows x64).** ``touch_keyboard.install(app,
touch=True)`` schreibt ueber ``_enable_tabtip_autoinvoke``
``HKCU\\Software\\Microsoft\\TabletTip\\1.7\\EnableDesktopModeAutoInvoke = 1``.
Drei Testdateien rufen ``install`` mit ``touch=True`` - damit setzte jedes
volle Windows-Gate diesen Wert, auf jedem Rechner und in der CI. Belegt ueber
die Schreibzeit des Schluessels: 17:43:04, waehrend ``test_ui111`` und
``test_ui112`` im Gate liefen; vorher war der Wert nicht gesetzt.

``tests/conftest.py`` hat dafuer zwei Riegel: die beiden System-Funktionen von
``touch_keyboard`` sind Attrappen, und jede schreibende winreg-Funktion wirft
und macht den Test rot, der sie gerufen hat. Diese Datei belegt beides, ohne
selbst je in die Registry zu schreiben: fehlt ein Riegel, endet jeder Test
hier an der Pruefung VOR dem Aufruf.
"""
from __future__ import annotations

import sys
import unittest

import conftest
from src.ui import touch_keyboard as tk

_WINDOWS = sys.platform == "win32"


class SystemTastaturIstAttrappeTest(unittest.TestCase):

    def test_registry_und_tabtip_sind_attrappen(self):
        for name in ("_enable_tabtip_autoinvoke", "_show_windows_osk"):
            with self.subTest(funktion=name):
                self.assertTrue(
                    getattr(getattr(tk, name), "qa118_attrappe", False),
                    f"touch_keyboard.{name} ist im Test die echte Funktion - sie "
                    "schreibt in die Registry bzw. startet TabTip auf dem Desktop")

    def test_touch_install_merkt_sich_den_aufruf_statt_zu_schreiben(self):
        """Derselbe Weg wie in test_ui111/ui112/ui119."""
        self.assertTrue(getattr(tk._enable_tabtip_autoinvoke, "qa118_attrappe", False))
        vorher = len(conftest.SYSTEM_TASTATUR_AUFRUFE)
        tk._enable_tabtip_autoinvoke()
        tk._show_windows_osk()
        self.assertEqual(["registry", "system_tastatur"],
                         conftest.SYSTEM_TASTATUR_AUFRUFE[vorher:])


@unittest.skipUnless(_WINDOWS, "Registry gibt es nur unter Windows")
class RegistryRiegelTest(unittest.TestCase):

    def setUp(self):
        import winreg
        self.winreg = winreg
        for name in conftest._REGISTRY_SCHREIBER:
            fn = getattr(winreg, name, None)
            if fn is not None:
                self.assertTrue(getattr(fn, "qa118_riegel", False),
                                f"winreg.{name} ist im Test nicht gesperrt")

    def tearDown(self):
        # Die Versuche hier sind gewollt - der Waechter nach dem Test soll
        # nur echte Ausreisser melden.
        conftest._REGISTRY_VERSUCHE.clear()

    def test_schreiben_wirft(self):
        with self.assertRaises(PermissionError):
            self.winreg.CreateKey(self.winreg.HKEY_CURRENT_USER, r"Software\LightOS-QA118-Probe")
        self.assertEqual(["CreateKey"], conftest._REGISTRY_VERSUCHE)

    def test_geschluckter_versuch_wird_trotzdem_gemerkt(self):
        """Wie in _enable_tabtip_autoinvoke: ``except Exception: pass``."""
        try:
            self.winreg.SetValueEx(None, "x", 0, self.winreg.REG_DWORD, 1)
        except Exception:
            pass
        self.assertEqual(["SetValueEx"], conftest._REGISTRY_VERSUCHE)

    def test_lesen_bleibt_erlaubt(self):
        with self.winreg.OpenKey(self.winreg.HKEY_CURRENT_USER, "Software") as k:
            self.assertIsNotNone(k)
        self.assertEqual([], conftest._REGISTRY_VERSUCHE)


if __name__ == "__main__":
    unittest.main()
