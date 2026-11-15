"""UI-133: Tipp in ein Textfeld zeigt unter Windows 11 die Touch-Tastatur.

**Befund (B, Finger-Probe 15.11.2026, Windows 11).** Ein Tipp in ein TEXTfeld
im Touch-Modus zeigte gar keine Tastatur. ``_show_windows_osk`` fand
``IPTip_Main_Window`` (unter Windows 11 da, aber unsichtbar), schickte
SC_RESTORE + SetForegroundWindow und kehrte zurueck - wirkungslos; TabTip.exe
wurde nie gestartet.

**Jetzt:** erst nachsehen, ob die Tastatur schon zu sehen ist; sonst COM
``ITipInvocation::Toggle`` (per ctypes, keine neue Abhaengigkeit); scheitert
das (TabTip laeuft nicht), der alte Weg - und hat der TabTip.exe gestartet,
einmal nachfassen.

Kein echter Aufruf: alle Systemzugriffe sind hier Attrappen (QA-118).
"""
from __future__ import annotations

import ctypes
import sys
import unittest

from src.ui import touch_keyboard as tk


class _Ablauf:
    """Attrappen fuer ``_tastatur_zeigen``: was wurde aufgerufen?"""

    def __init__(self, sichtbar=False, com=True, alt="tabtip"):
        self.sichtbar_wert, self.com_wert, self.alt_wert = sichtbar, com, alt
        self.aufrufe: list[str] = []
        self.spaeter_liste: list[tuple[int, object]] = []

    def sichtbar(self):
        self.aufrufe.append("sichtbar")
        if isinstance(self.sichtbar_wert, Exception):
            raise self.sichtbar_wert
        return self.sichtbar_wert

    def umschalten(self):
        self.aufrufe.append("com")
        if isinstance(self.com_wert, Exception):
            raise self.com_wert
        return self.com_wert

    def alter_weg(self):
        self.aufrufe.append("alt")
        return self.alt_wert

    def spaeter(self, ms, f):
        self.spaeter_liste.append((ms, f))

    def zeigen(self):
        return tk._tastatur_zeigen(self.sichtbar, self.umschalten, self.alter_weg,
                                   self.spaeter)


class ReihenfolgeTest(unittest.TestCase):

    def test_windows11_iptip_unsichtbar_com_zeigt_die_tastatur(self):
        """★ Der Befund: IPTip_Main_Window da, aber unsichtbar -> COM, nicht
        mehr der wirkungslose SC_RESTORE-Weg."""
        a = _Ablauf(sichtbar=False, com=True)
        self.assertEqual("com", a.zeigen())
        self.assertEqual(["sichtbar", "com"], a.aufrufe)

    def test_schon_sichtbar_wird_nicht_umgeschaltet(self):
        """Toggle SCHALTET UM - eine sichtbare Tastatur wuerde sonst zugehen."""
        a = _Ablauf(sichtbar=True)
        self.assertEqual("schon sichtbar", a.zeigen())
        self.assertEqual(["sichtbar"], a.aufrufe)

    def test_com_scheitert_alter_weg_und_einmal_nachfassen(self):
        a = _Ablauf(sichtbar=False, com=False, alt="tabtip")
        self.assertEqual("tabtip", a.zeigen())
        self.assertEqual(["sichtbar", "com", "alt"], a.aufrufe)
        self.assertEqual(1, len(a.spaeter_liste))
        ms, nachfassen = a.spaeter_liste[0]
        self.assertEqual(tk._NACHFASSEN_MS, ms)
        a.aufrufe.clear()
        a.com_wert = True                       # TabTip laeuft jetzt
        nachfassen()
        self.assertEqual(["sichtbar", "com"], a.aufrufe)

    def test_nachfassen_schaltet_eine_sichtbare_tastatur_nicht_weg(self):
        """Windows 10 zeigt die Tastatur schon beim Start von TabTip.exe."""
        a = _Ablauf(sichtbar=False, com=False, alt="tabtip")
        a.zeigen()
        a.aufrufe.clear()
        a.sichtbar_wert = True
        a.spaeter_liste[0][1]()
        self.assertEqual(["sichtbar"], a.aufrufe)

    def test_ohne_tabtip_start_kein_nachfassen(self):
        for alt in ("iptip", "osk", "nichts"):
            with self.subTest(alter_weg=alt):
                a = _Ablauf(sichtbar=False, com=False, alt=alt)
                self.assertEqual(alt, a.zeigen())
                self.assertEqual([], a.spaeter_liste)

    def test_fehler_in_den_pruefungen_fuehren_zum_alten_weg(self):
        a = _Ablauf(sichtbar=OSError("weg"), com=OSError("kaputt"), alt="osk")
        self.assertEqual("osk", a.zeigen())
        self.assertEqual(["sichtbar", "com", "alt"], a.aufrufe)

    def test_ausserhalb_von_windows_nichts(self):
        if sys.platform == "win32":
            self.skipTest("prueft den Nicht-Windows-Zweig")
        tk._show_windows_osk()                  # darf nichts tun und nicht werfen


# ── Systemzugriffe mit Attrappen ────────────────────────────────────────────

class _User32:
    def __init__(self, fenster: dict, sichtbar: dict, stil: dict | None = None):
        self.fenster, self.sichtbar, self.stil = fenster, sichtbar, stil or {}
        self.desktop_hwnd = 0x10010

    def FindWindowW(self, klasse, titel):  # noqa: N802 (Win32-Name)
        return self.fenster.get((klasse, titel), 0)

    def IsWindowVisible(self, hwnd):  # noqa: N802
        return self.sichtbar.get(hwnd, 0)

    def GetWindowLongW(self, hwnd, index):  # noqa: N802
        return self.stil.get(hwnd, 0)

    def GetDesktopWindow(self):  # noqa: N802
        return self.desktop_hwnd


class _Dwm:
    def __init__(self, verhuellt: int, rc: int = 0):
        self.verhuellt, self.rc = verhuellt, rc

    def DwmGetWindowAttribute(self, hwnd, attr, ziel, groesse):  # noqa: N802
        assert attr == 14
        ziel._obj.value = self.verhuellt
        return self.rc


_W11 = ("Windows.UI.Core.CoreWindow", "Microsoft Text Input Application")
_W10 = ("IPTip_Main_Window", None)


class SichtbarTest(unittest.TestCase):

    def test_windows11_verhuellt_heisst_zu(self):
        u = _User32({_W11: 7, _W10: 9}, {7: 1, 9: 0})
        self.assertFalse(tk._tip_sichtbar(u, _Dwm(verhuellt=1)))

    def test_windows11_offen(self):
        u = _User32({_W11: 7}, {7: 1})
        self.assertTrue(tk._tip_sichtbar(u, _Dwm(verhuellt=0)))

    def test_windows11_iptip_da_aber_unsichtbar_ist_zu(self):
        """Der Befund: das Fenster des alten Wegs existiert, zeigt aber nichts."""
        u = _User32({_W10: 9}, {9: 0})
        self.assertFalse(tk._tip_sichtbar(u, _Dwm(verhuellt=0)))

    def test_windows10_sichtbar_und_nicht_deaktiviert(self):
        u = _User32({_W10: 9}, {9: 1})
        self.assertTrue(tk._tip_sichtbar(u, _Dwm(verhuellt=0)))
        u.stil[9] = 0x08000000                  # WS_DISABLED: Windows 10 "zu"
        self.assertFalse(tk._tip_sichtbar(u, _Dwm(verhuellt=0)))

    def test_kein_fenster(self):
        self.assertFalse(tk._tip_sichtbar(_User32({}, {}), _Dwm(verhuellt=0)))


@unittest.skipUnless(sys.platform == "win32", "COM-Aufruf per WINFUNCTYPE gibt es nur unter Windows")
class UmschaltenTest(unittest.TestCase):
    """``_tip_umschalten`` gegen ein nachgebautes COM-Objekt (Tabelle mit
    QueryInterface, AddRef, Release, Toggle) - prueft Index und Signatur."""

    def setUp(self):
        self.log: list = []
        typ_ref = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
        typ_toggle = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)
        typ_qi = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_void_p)
        self._rueckrufe = [
            typ_qi(lambda *_: self.log.append("QueryInterface") or 0),
            typ_ref(lambda _s: self.log.append("AddRef") or 1),
            typ_ref(lambda _s: self.log.append("Release") or 0),
            typ_toggle(lambda _s, hwnd: self.log.append(("Toggle", hwnd)) or 0),
        ]
        self._tabelle = (ctypes.c_void_p * 4)(
            *[ctypes.cast(f, ctypes.c_void_p).value for f in self._rueckrufe])
        self._objekt = ctypes.c_void_p(ctypes.addressof(self._tabelle))
        self.user32 = _User32({}, {})

    def _ole32(self, erzeugen_hr=0, init_hr=0):
        test = self

        class Ole32:
            def CLSIDFromString(self, s, ziel):  # noqa: N802
                test.log.append(("CLSID", s))
                return 0

            def IIDFromString(self, s, ziel):  # noqa: N802
                test.log.append(("IID", s))
                return 0

            def CoInitializeEx(self, _r, modus):  # noqa: N802
                test.log.append(("CoInitializeEx", modus))
                return init_hr

            def CoUninitialize(self):  # noqa: N802
                test.log.append("CoUninitialize")

            def CoCreateInstance(self, clsid, aussen, ctx, iid, ziel):  # noqa: N802
                test.log.append(("CoCreateInstance", ctx))
                if erzeugen_hr == 0:
                    ziel._obj.value = ctypes.addressof(test._objekt)
                return erzeugen_hr

        return Ole32()

    def test_toggle_mit_desktop_fenster_dann_release(self):
        self.assertTrue(tk._tip_umschalten(self._ole32(), self.user32))
        self.assertIn(("CLSID", "{4CE576FA-83DC-4F88-951C-9D0782B4E376}"), self.log)
        self.assertIn(("IID", "{37C994E7-432B-4834-A2F7-DCE1F13B834B}"), self.log)
        rest = [e for e in self.log if not (isinstance(e, tuple) and e[0] in ("CLSID", "IID"))]
        self.assertEqual([("CoInitializeEx", 2), ("CoCreateInstance", 5),
                          ("Toggle", self.user32.desktop_hwnd), "Release", "CoUninitialize"],
                         rest)

    def test_tabtip_laeuft_nicht(self):
        """UIHostNoLaunch: ohne laufendes TabTip REGDB_E_CLASSNOTREG (auf dem
        Test-PC gemessen) -> False, kein Toggle, COM sauber abgemeldet."""
        self.assertFalse(tk._tip_umschalten(self._ole32(erzeugen_hr=-2147221164),
                                            self.user32))
        self.assertNotIn("Release", self.log)
        self.assertFalse(any(isinstance(e, tuple) and e[0] == "Toggle" for e in self.log))
        self.assertEqual("CoUninitialize", self.log[-1])

    def test_fremdes_com_modell_wird_nicht_abgemeldet(self):
        """RPC_E_CHANGED_MODE: COM gehoert schon jemand anderem - nicht abmelden."""
        self.assertTrue(tk._tip_umschalten(self._ole32(init_hr=-2147417850), self.user32))
        self.assertNotIn("CoUninitialize", self.log)


if __name__ == "__main__":
    unittest.main()
