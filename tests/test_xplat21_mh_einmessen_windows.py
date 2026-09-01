"""XPLAT-21: das Einmess-Werkzeug (VIZ-60) laeuft jetzt auch auf Windows.

**Der Befund.** ``tools/mh_einmessen.py`` hatte ``import termios`` und
``import tty`` auf Modulebene. Beide gibt es nur auf POSIX — auf Windows starb
schon ``mh_einmessen.py --help`` mit ``ModuleNotFoundError``. Das Werkzeug misst
Moving Heads am Rig ein und war damit ausgerechnet auf dem Rechner nicht
startbar, an dem das Rig haengt. Als Folge riss auch
``tests/test_viz60_einmessen.py`` mit 8 von 10 Tests, weil sein ``setUp`` das
Modul laedt.

Drei weitere POSIX-Annahmen im selben Werkzeug: ein eigener ``/proc``-Scan,
``select.select`` auf ``sys.stdin`` (auf Windows nur fuer Sockets erlaubt) und
``--port`` fest auf ``/dev/ttyUSB0``.

★ **Warum die Tastencodes hier als Tabelle geprueft werden und nicht als
Tastendruck.** Einen echten Tastendruck kann ein Test nicht herstellen — es
gibt kein Terminal. Die UEBERSETZUNG von Code zu Bedeutung ist aber genau die
Stelle, an der die Fehler sitzen, und sie ist eine reine Funktion. Deshalb
liegen die Zuordnungen im Werkzeug als Daten (``WIN_TASTEN``/``POSIX_TASTEN``)
und werden hier einzeln nachgerechnet.

★★ **Die wichtigste Zusicherung ist die Konsistenz der beiden Tabellen.** Die
Hauptschleife leitet die Schrittweite aus ``t.isupper()`` ab (gross = 8x grob).
Lieferte eine der Tabellen eine andere Schreibweise, waere die Grobbewegung auf
der einen Plattform stumm — und das faellt beim Lesen des Codes nicht auf,
sondern erst am Rig.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PFAD = os.path.join(_ROOT, "tools", "mh_einmessen.py")

_PLAT = sys.platform
_IST_WINDOWS = _PLAT == "win32"


def _modul():
    spec = importlib.util.spec_from_file_location("mh_einmessen_xplat21", _PFAD)
    assert spec and spec.loader, "mh_einmessen.py nicht ladbar"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class WerkzeugStartetUeberhauptTest(unittest.TestCase):
    """Die Grundaussage des Items — auf JEDER Plattform."""

    def test_das_modul_laesst_sich_laden(self):
        """Genau das ging auf Windows nicht (ModuleNotFoundError: termios)."""
        self.assertTrue(hasattr(_modul(), "port_halter"))

    def test_keine_posix_only_importe_auf_modulebene(self):
        """★ Statisch, damit der Fehler nicht auf einem Linux-Rechner
        zurueckkommt, wo ihn niemand bemerkt.

        Geprueft wird der Quelltext bis zur ersten Funktion: ``termios``,
        ``tty``, ``msvcrt`` und ``select`` duerfen dort nicht importiert werden,
        auch nicht in einem ``if``. Ein bedingter Import waere zwar lauffaehig,
        macht die Datei aber fuer jeden Leser und Typpruefer zum Sonderfall —
        und genau deshalb stehen sie jetzt in den Methoden.
        """
        quelle = open(_PFAD, encoding="utf-8").read()
        kopf = quelle.split("\ndef ", 1)[0]
        for modul in ("termios", "tty", "msvcrt", "select"):
            with self.subTest(modul=modul):
                self.assertNotIn(f"\nimport {modul}", kopf,
                                 f"{modul} wird auf Modulebene importiert")

    def test_help_laeuft_durch(self):
        """Der Aufruf, an dem es konkret scheiterte."""
        r = subprocess.run([sys.executable, _PFAD, "--help"],
                           capture_output=True, timeout=120, cwd=_ROOT)
        ausgabe = (r.stdout + r.stderr).decode("utf-8", "replace")
        self.assertEqual(0, r.returncode, ausgabe[-800:])
        self.assertNotIn("ModuleNotFoundError", ausgabe)
        self.assertIn("--adressen", ausgabe)


class TastenUebersetzungTest(unittest.TestCase):
    """Code -> Bedeutung, fuer beide Plattformen nachgerechnet."""

    def setUp(self):
        self.m = _modul()

    def test_windows_pfeile(self):
        for code, erwartet in (("H", "hoch"), ("P", "runter"),
                               ("M", "rechts"), ("K", "links")):
            with self.subTest(code=code):
                self.assertEqual(erwartet, self.m.uebersetze_windows(code))

    def test_windows_grosse_schritte_ueber_strg_pfeil(self):
        """Shift+Pfeil gibt es auf Windows nicht — ``msvcrt`` reicht keine
        Modifier durch. Die Grobbewegung liegt deshalb auf Strg+Pfeil."""
        for code, erwartet in (("\x8d", "HOCH"), ("\x91", "RUNTER"),
                               ("s", "LINKS"), ("t", "RECHTS")):
            with self.subTest(code=code):
                self.assertEqual(erwartet, self.m.uebersetze_windows(code))

    def test_windows_zweiter_weg_fuer_grosse_schritte(self):
        """Bild-hoch/-runter und Pos1/Ende als Ausweichweg.

        Manche Konsolen fangen Strg+Pfeil selbst ab. Ohne zweiten Weg waere die
        Grobbewegung dort nicht erreichbar — am Rig unbrauchbar.
        """
        for code, erwartet in (("I", "HOCH"), ("Q", "RUNTER"),
                               ("G", "LINKS"), ("O", "RECHTS")):
            with self.subTest(code=code):
                self.assertEqual(erwartet, self.m.uebersetze_windows(code))

    def test_unbekannter_code_ist_leer_und_nicht_etwa_eine_bewegung(self):
        """POSITIVKONTROLLE: sonst koennte die Tabelle alles auf 'hoch'
        abbilden und alle Tests oben blieben gruen."""
        for code in ("?", "\x00", "Z", ""):
            with self.subTest(code=code):
                self.assertEqual("", self.m.uebersetze_windows(code))

    def test_posix_bleibt_unveraendert(self):
        """Der bestehende Weg darf sich durch die Windows-Ergaenzung nicht
        aendern — sonst repariert man eine Plattform auf Kosten der anderen."""
        for code, erwartet in (("[A", "hoch"), ("[B", "runter"),
                               ("[C", "rechts"), ("[D", "links"),
                               ("[a", "HOCH"), ("[b", "RUNTER"),
                               ("[c", "RECHTS"), ("[d", "LINKS"),
                               ("zz", "")):
            with self.subTest(code=code):
                self.assertEqual(erwartet, self.m.uebersetze_posix(code))

    def test_beide_tabellen_sprechen_dieselbe_sprache(self):
        """★★ Die Zusicherung, an der die Grobbewegung haengt.

        Die Hauptschleife leitet die Schrittweite aus ``t.isupper()`` ab. Beide
        Tabellen muessen deshalb denselben Wortschatz benutzen — sonst ist die
        8x-Bewegung auf einer Plattform stumm, ohne dass es beim Lesen auffaellt.
        """
        self.assertEqual(set(self.m.POSIX_TASTEN.values()),
                         set(self.m.WIN_TASTEN.values()),
                         "die Bedeutungen der beiden Tabellen weichen ab")

    def test_gross_heisst_grober_schritt(self):
        """Die Konvention selbst, damit sie nicht still kippt."""
        for wert in set(self.m.WIN_TASTEN.values()):
            with self.subTest(wert=wert):
                self.assertEqual(wert.isupper(), wert in
                                 ("HOCH", "RUNTER", "LINKS", "RECHTS"))


class StandardPortTest(unittest.TestCase):
    """``--port`` ohne Angabe muss zur Plattform passen."""

    def setUp(self):
        self.m = _modul()

    @unittest.skipIf(_IST_WINDOWS, "POSIX-Vorgabe")
    def test_posix_bleibt_bei_ttyusb0(self):
        self.assertEqual("/dev/ttyUSB0", self.m.standard_port())

    @unittest.skipUnless(_IST_WINDOWS, "Windows-Vorgabe")
    def test_windows_liefert_einen_com_port(self):
        """Kein ``/dev/...`` mehr — das war auf Windows eine Sackgasse.

        Welcher COM-Port herauskommt, haengt am Rechner (angesteckt oder nicht)
        und wird deshalb NICHT festgenagelt; festgenagelt wird die Form.
        """
        port = self.m.standard_port()
        self.assertTrue(port.upper().startswith("COM"), port)
        self.assertNotIn("/dev/", port)


if __name__ == "__main__":
    unittest.main()
