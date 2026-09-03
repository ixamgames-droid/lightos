"""XPLAT-26: eine Aufruf-Zeile, die nur auf einem der beiden Rechner funktioniert.

**Herkunft:** Werkzeug-Durchgang PROC-07 (2026-09-01). Von 77 Werkzeugen nannten
**41** in ihrer Aufruf-Zeile nur ``venv/Scripts/python.exe`` und **14** nur
``venv/bin/python`` — **keines** beide. Wer die Kopfzeile liest und tippt,
bekommt auf dem jeweils anderen Rechner „command not found" und sucht den Fehler
im Werkzeug.

Das ist keine Schoenheitsfrage: seit dem 2026-08-06 arbeiten an diesem Repo zwei
Sitzungen auf **zwei verschiedenen Betriebssystemen**. Jede zweite Kopfzeile war
damit fuer die jeweils andere falsch.

★ **Warum der Test die Symmetrie prueft und nicht nur eine Richtung.** Das Item
nennt nur die Windows-lastigen Zeilen — sie waren die Mehrheit. Ein Waechter, der
nur diese Richtung prueft, laesst die 14 Gegenstuecke stehen und waere ausgerechnet
fuer den Rechner blind, auf dem er am haeufigsten laeuft.
"""
from __future__ import annotations

import glob
import io
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")

_BS = chr(92)
#: Beide Schreibweisen des Windows-Pfades — mit "/" (so steht es fast ueberall)
#: und mit "\" (eine Datei schrieb ihn so).
_WINDOWS = ("venv/Scripts/python", "venv" + _BS + "Scripts" + _BS + "python")
_POSIX = "venv/bin/python"


def _werkzeuge():
    for pfad in sorted(glob.glob(os.path.join(TOOLS, "*.py"))):
        with io.open(pfad, encoding="utf-8") as f:
            yield os.path.relpath(pfad, REPO).replace(os.sep, "/"), f.read()


def _nennt_windows(text: str) -> bool:
    return any(w in text for w in _WINDOWS)


class AufrufzeilenNennenBeideWegeTest(unittest.TestCase):

    def test_kein_werkzeug_nennt_nur_einen_der_beiden_wege(self):
        """★ Die eigentliche Zusicherung.

        Geprueft wird die Datei als Ganzes, nicht die einzelne Zeile: manche
        Werkzeuge haben einen ganzen Block Aufruf-Zeilen, und dort genuegt EIN
        Hinweis darunter. Was zaehlt, ist, dass der Leser den anderen Weg
        ueberhaupt findet, ohne ihn zu erraten.
        """
        einseitig = []
        for pfad, text in _werkzeuge():
            windows, posix = _nennt_windows(text), _POSIX in text
            if windows != posix:
                einseitig.append(
                    "%s: nennt nur den %s-Weg" % (pfad, "Windows" if windows else "Linux"))
        self.assertEqual(
            [], einseitig,
            "Diese Werkzeuge nennen nur einen der beiden Wege — auf dem anderen "
            "Rechner ergibt ihre Kopfzeile 'command not found':\n  "
            + "\n  ".join(einseitig))

    def test_es_gibt_ueberhaupt_werkzeuge_mit_aufrufzeile(self):
        """Ohne das waere der Test oben trivial gruen: keine Treffer, keine Luecken.

        Genau diese Falle hat im Haus schon einmal einen Waechter entwertet
        (QA-52: ein Test, der sein eigenes Muster prueft, bleibt gruen, wenn das
        Muster nicht mehr trifft).
        """
        mit_pfad = [p for p, t in _werkzeuge() if _nennt_windows(t) or _POSIX in t]
        self.assertGreater(
            len(mit_pfad), 40,
            "kaum noch Werkzeuge mit Aufruf-Zeile gefunden — vermutlich hat sich "
            "die Schreibweise geaendert und die Erkennung greift nicht mehr")

    def test_die_erkennung_wuerde_eine_einseitige_zeile_auch_finden(self):
        """Positivkontrolle der Erkennung selbst, an einem gebauten Beispiel.

        Der Test oben ist gruen, solange das Repo sauber ist — er sagt damit
        nichts darueber, ob er einen Rueckfall ueberhaupt saehe.
        """
        nur_windows = 'Aufruf:  venv/Scripts/python.exe tools/x.py\n'
        nur_posix = 'Aufruf:  ./venv/bin/python tools/x.py\n'
        beide = nur_windows + "         (Linux/macOS: ./venv/bin/python)\n"
        self.assertNotEqual(_nennt_windows(nur_windows), _POSIX in nur_windows)
        self.assertNotEqual(_nennt_windows(nur_posix), _POSIX in nur_posix)
        self.assertEqual(_nennt_windows(beide), _POSIX in beide)


if __name__ == "__main__":
    unittest.main()
