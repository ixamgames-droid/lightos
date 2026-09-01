"""XPLAT-22: Die Port-Belegt-Warnung (OUT-54) gibt es jetzt auch auf Windows.

**Der Befund.** ``src/core/dmx/port_check.py`` war auf ``/proc`` gebaut. Auf
Windows lieferte ``port_belegt_von`` deshalb **immer** ``[]`` und
``warne_wenn_belegt`` schwieg — ununterscheidbar von „alles in Ordnung".
Gemessen am 31.08.2026: ``port_belegt_von('COM3')`` -> ``[]``,
``warne_wenn_belegt('COM3')`` -> keine Ausgabe.

**Warum das dort MEHR wiegt als auf Linux.** Auf Linux teilen sich mehrere
Sender die Leitung; das Bild ist zerhacktes DMX (das Geraet blinkt, Blackout
funktioniert). Auf Windows vergibt der serielle Treiber **exklusiv**: der
zweite Zugriff scheitert hart, die Ausgabe laeuft gar nicht erst an — und der
Worker kreist still in ``ST_DISABLED``, waehrend ``is_open()`` ``True`` meldet.
Die Warnung ist dort also nicht Komfort, sondern die einzige Spur.

★ **Wie hier ohne serielle Hardware bewiesen wird, und warum das echt ist.**
An diesem Rechner haengt kein COM-Port (``SerialPort::GetPortNames()`` ->
leer). Der Nachweis laeuft deshalb ueber eine **exklusiv gehaltene Datei**:
``CreateFileW`` mit ``dwShareMode = 0`` ist genau das, was ein serieller
Treiber tut, und der Zweitzugriff liefert denselben Fehlercode
(``ERROR_SHARING_VIOLATION``, 32). Gemessen wird also **echtes Win32-Verhalten
im echten Produktionspfad**, nicht eine Nachbildung: es laeuft dieselbe
``_win_oeffnungsversuch``-Funktion, die spaeter auf ``COM3`` zeigt.

⚠️ **Was damit NICHT bewiesen ist** (und als Hardware-Punkt offen bleibt):
welchen der beiden Fehlercodes ein FTDI-Adapter im Belegtfall wirklich liefert.
Deshalb behandelt der Produktionscode **beide** (5 und 32) als „belegt" statt
sich auf einen zu verlassen. Am Geraet zu bestaetigen bleibt: Enttec Pro
anstecken, LightOS starten, zweite Instanz starten -> die Warnung muss kommen.
"""
from __future__ import annotations

import ctypes
import io
import os
import sys
import tempfile
import unittest

# Ueber eine Variable, sonst wertet Pyright den Vergleich statisch aus und
# meldet den jeweils anderen Zweig als toten Code (wie src/core/paths.py).
_PLAT = sys.platform
_IST_WINDOWS = _PLAT == "win32"
_GRUND = ("XPLAT-22 prueft den Windows-Zweig von port_check; auf Linux macht "
          "das der /proc-Weg in tests/test_out54_port_belegt.py")

from src.core.dmx.port_check import (                    # noqa: E402
    _WIN_BELEGT, _WIN_NICHT_DA, warne_wenn_belegt, windows_port_belegt,
    windows_verdaechtige_prozesse)


class FehlercodeAuswertungTest(unittest.TestCase):
    """Die Auswertung der Win32-Codes — ohne jeden Systemaufruf.

    Ueber den ``oeffner``-Parameter, damit jeder Fall geprueft werden kann,
    auch die, die sich an diesem Rechner nicht herstellen lassen.
    """

    def test_null_heisst_frei(self):
        self.assertIs(False, windows_port_belegt("COM7", oeffner=lambda p: 0))

    def test_beide_belegt_codes_zaehlen(self):
        """★ Beide, nicht nur einer.

        Welcher Code kommt, haengt am Treiber: FTDI-Adapter melden ueblicher-
        weise 5 (ACCESS_DENIED), der Windows-eigene serial.sys 32
        (SHARING_VIOLATION). Wer nur einen prueft, meldet die halbe
        Geraetewelt stillschweigend als frei.
        """
        for code in _WIN_BELEGT:
            with self.subTest(code=code):
                self.assertIs(
                    True, windows_port_belegt("COM7", oeffner=lambda p, c=code: c),
                    f"Win32-Fehler {code} muss als belegt gelten")

    def test_nicht_vorhandener_port_ist_KEINE_entwarnung(self):
        """★★ Der Kern des ganzen Items.

        ``None`` heisst „nicht feststellbar" und darf niemals mit ``False``
        („frei") verwechselt werden. Genau diese Verwechslung war der Befund:
        die alte Fassung lieferte auf Windows eine leere Liste, und eine leere
        Liste liest sich wie Entwarnung.
        """
        for code in _WIN_NICHT_DA:
            with self.subTest(code=code):
                self.assertIsNone(
                    windows_port_belegt("COM7", oeffner=lambda p, c=code: c))

    def test_unbekannter_fehler_meldet_nicht_frei(self):
        self.assertIsNone(windows_port_belegt("COM7", oeffner=lambda p: 1167))

    def test_eine_ausnahme_im_oeffner_stuerzt_nicht_ab(self):
        """Ein Diagnose-Helfer darf den Start der Ausgabe nie verhindern."""
        def kaputt(_):
            raise OSError("Treiber weg")
        self.assertIsNone(windows_port_belegt("COM7", oeffner=kaputt))


@unittest.skipUnless(_IST_WINDOWS, _GRUND)
class EchterWin32Test(unittest.TestCase):
    """Der Nachweis am echten Betriebssystem — ohne serielle Hardware.

    Eine exklusiv gehaltene Datei verhaelt sich beim Zweitzugriff wie ein
    belegter Port, weil es derselbe Mechanismus ist (``dwShareMode = 0``).
    """

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(prefix="lightos_xplat22_")
        self.pfad = os.path.join(self._dir.name, "belegt.bin")
        with open(self.pfad, "wb") as fh:
            fh.write(b"x")
        self.addCleanup(self._dir.cleanup)
        from ctypes import wintypes
        self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._k32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        self._k32.CreateFileW.restype = wintypes.HANDLE
        self._k32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._ungueltig = ctypes.c_void_p(-1).value

    def _exklusiv_halten(self):
        handle = self._k32.CreateFileW(
            "\\\\.\\" + self.pfad, 0x80000000, 0, None, 3, 0, None)
        self.assertNotEqual(self._ungueltig, handle,
                            "die Probe konnte die Datei nicht exklusiv oeffnen "
                            "— dann misst dieser Test nichts")
        self.addCleanup(self._k32.CloseHandle, handle)
        return handle

    def test_unbelegt_wird_als_frei_erkannt(self):
        """POSITIVKONTROLLE: ohne Halter darf nichts gemeldet werden.

        Ohne sie koennte der Test unten auch dann bestehen, wenn die Funktion
        pauschal „belegt" saegte — eine Warnung, die immer kommt, ist keine.
        """
        self.assertIs(False, windows_port_belegt(self.pfad))

    def test_exklusiver_halter_wird_erkannt(self):
        self._exklusiv_halten()
        self.assertIs(True, windows_port_belegt(self.pfad),
                      "ein exklusiv gehaltener Pfad muss als belegt gelten — "
                      "genau so verhaelt sich ein COM-Port unter Windows")

    def test_der_gemessene_fehlercode_steht_in_der_liste(self):
        """Nicht nur „belegt", sondern WELCHER Code — damit die Liste stimmt."""
        from src.core.dmx.port_check import _win_oeffnungsversuch
        self._exklusiv_halten()
        code = _win_oeffnungsversuch(self.pfad)
        self.assertIn(code, _WIN_BELEGT,
                      f"Win32 meldete {code}; wenn das ein echter Belegtfall "
                      "ist, gehoert der Code in _WIN_BELEGT")

    def test_nach_der_freigabe_ist_er_wieder_frei(self):
        """★ Dass der Befund VERSCHWINDET, ist die halbe Aussage.

        Eine Erkennung, die nach dem ersten Treffer haengenbleibt, wuerde bei
        jedem weiteren Start warnen — und genau die Gewoehnung erzeugen, gegen
        die die Warnung gebaut ist.
        """
        handle = self._k32.CreateFileW(
            "\\\\.\\" + self.pfad, 0x80000000, 0, None, 3, 0, None)
        self.assertIs(True, windows_port_belegt(self.pfad))
        self._k32.CloseHandle(handle)
        self.assertIs(False, windows_port_belegt(self.pfad))

    def test_ein_gar_nicht_vorhandener_port_meldet_nicht_belegt(self):
        self.assertIsNone(windows_port_belegt("COM99"))


@unittest.skipUnless(_IST_WINDOWS, _GRUND)
class VerdaechtigeProzesseTest(unittest.TestCase):
    """Die Heuristik — ausdruecklich als Verdacht, nicht als Feststellung."""

    def test_findet_wenigstens_den_laufenden_python(self):
        """Der Test selbst laeuft in Python; ein Elternprozess muss auftauchen.

        Geprueft wird mit einer FREMDEN eigenen PID, damit nicht der einzige
        Treffer der eigene Prozess ist — sonst bewiese der Test nur, dass die
        Liste nicht leer ist.
        """
        gefunden = windows_verdaechtige_prozesse(eigene_pid=-1)
        self.assertTrue(gefunden, "kein einziger Python-Prozess gefunden — "
                                  "die Prozess-Enumeration greift nicht")
        for pid, name in gefunden:
            self.assertIsInstance(pid, int)
            self.assertTrue(name.lower().startswith("python"), name)

    def test_der_eigene_prozess_wird_ausgelassen(self):
        pids = [p for p, _ in windows_verdaechtige_prozesse()]
        self.assertNotIn(os.getpid(), pids,
                         "der eigene Prozess darf nicht als Verdaechtiger "
                         "auftauchen — sonst warnt jeder Start vor sich selbst")


@unittest.skipUnless(_IST_WINDOWS, _GRUND)
class WarnungTest(unittest.TestCase):
    """Was der Mensch am Ende liest."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(prefix="lightos_xplat22w_")
        self.pfad = os.path.join(self._dir.name, "belegt.bin")
        with open(self.pfad, "wb") as fh:
            fh.write(b"x")
        self.addCleanup(self._dir.cleanup)
        from ctypes import wintypes
        self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._k32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        self._k32.CreateFileW.restype = wintypes.HANDLE
        self._k32.CloseHandle.argtypes = [wintypes.HANDLE]

    def test_die_warnung_sagt_was_passieren_wird(self):
        handle = self._k32.CreateFileW(
            "\\\\.\\" + self.pfad, 0x80000000, 0, None, 3, 0, None)
        self.addCleanup(self._k32.CloseHandle, handle)
        puffer = io.StringIO()
        warne_wenn_belegt(self.pfad, ausgabe=puffer)
        text = puffer.getvalue()
        self.assertIn("WARNUNG", text)
        self.assertIn(self.pfad, text, "der Port muss benannt sein")
        self.assertIn("exklusiv", text,
                      "die Meldung muss den Windows-Grund nennen, nicht den "
                      "Linux-Grund (zerhacktes DMX gibt es hier nicht)")
        self.assertIn("NICHT anlaufen", text,
                      "die Folge gehoert in die Meldung: die Ausgabe startet "
                      "nicht, und zwar ohne Fehlerbild im Programm")

    def test_die_warnung_gibt_den_verdacht_als_verdacht_aus(self):
        """★ Kein Halterschaft-Anspruch, den Windows nicht hergibt.

        Die PIDs sind eine Heuristik. Sie als Tatsache zu drucken, wuerde bei
        der Fehlersuche auf die falsche Faehrte fuehren — deshalb muss das Wort
        im Text stehen.
        """
        handle = self._k32.CreateFileW(
            "\\\\.\\" + self.pfad, 0x80000000, 0, None, 3, 0, None)
        self.addCleanup(self._k32.CloseHandle, handle)
        puffer = io.StringIO()
        warne_wenn_belegt(self.pfad, ausgabe=puffer)
        text = puffer.getvalue()
        self.assertTrue("Verdacht" in text or "verdaechtig" in text.lower(),
                        f"die Meldung tut so, als kenne sie den Halter:\n{text}")

    def test_ein_freier_port_schweigt(self):
        """POSITIVKONTROLLE — sonst waere die Warnung Dauerrauschen."""
        puffer = io.StringIO()
        ergebnis = warne_wenn_belegt(self.pfad, ausgabe=puffer)
        self.assertEqual("", puffer.getvalue())
        self.assertEqual([], ergebnis)

    def test_ein_unbekannter_port_schweigt_ebenfalls(self):
        """``None`` darf keine Warnung ausloesen — sonst warnt jeder Start mit
        abgezogenem Adapter, und das ist der Normalfall am Schreibtisch."""
        puffer = io.StringIO()
        warne_wenn_belegt("COM99", ausgabe=puffer)
        self.assertEqual("", puffer.getvalue())


if __name__ == "__main__":
    unittest.main()
