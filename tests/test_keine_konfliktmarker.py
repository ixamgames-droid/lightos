"""Kein Merge-Konfliktmarker darf in einer versionierten Datei landen.

★ **Der Anlass, am 2026-08-12 real passiert.** Beim Zusammenfuehren zweier
parallel bearbeiteter Items blieben in `BACKLOG.md` drei Markerzeilen stehen
(`<<<<<<< HEAD`, `=======`, `>>>>>>> origin/main`) — und der Commit ging durch
Review, volles Gate und CI **gruen** nach `main`.

**Warum kein bestehendes Gate es gefangen hat:** der Backlog-Lint prueft
Item-Zeilen (ID-Muster, eindeutige IDs, Status-Vokabeln). Eine Markerzeile
sieht nicht wie ein Item aus, also faellt sie durch jedes dieser Raster. Der
Doku-Link-Pruefer sucht Links. Der Syntax-Check kompiliert Python — und Markdown
hat keine Syntax, an der sich so etwas bricht.

Gefunden hat es am Ende eine adversariale Gegenpruefung, nicht die Suite. Genau
das ist der Grund fuer diese Datei: **ein Fehler, den nur ein Mensch (oder ein
zweiter Agent) sieht, kommt wieder.**

Geprueft werden die von git verwalteten Text-Dateien — nicht das
Arbeitsverzeichnis: waehrend eines laufenden Merges sind Marker voellig normal
und sollen die Suite nicht rot machen.
"""
import os
import subprocess
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Die drei Zeilen, die `git merge` hinterlaesst. Bewusst am ZEILENANFANG
# verankert und mit Laengenbegrenzung: `=======` steht in Markdown auch als
# Unterstreichung einer Ueberschrift, und `>>>` als Zitat- oder Prompt-Zeichen.
_START = "<<<<<<<"
_TRENN = "======="
_ENDE = ">>>>>>>"

# Diese Datei beschreibt die Marker und enthaelt sie deshalb als Zeichenketten.
_AUSNAHMEN = {"tests/test_keine_konfliktmarker.py"}


def _versionierte_textdateien():
    aus = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True,
                         text=True, check=True).stdout.splitlines()
    for rel in aus:
        if rel in _AUSNAHMEN:
            continue
        if rel.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".ico",
                                 ".zip", ".lshow", ".db", ".woff", ".woff2",
                                 ".ttf", ".pdf", ".mp3", ".wav")):
            continue
        yield rel


def marker_in(text: str) -> list:
    """Zeilennummern (1-basiert) mit einem Konfliktmarker."""
    treffer = []
    for nr, zeile in enumerate(text.splitlines(), start=1):
        blank = zeile.rstrip()
        if blank.startswith(_START) and len(blank) < 60:
            treffer.append(nr)
        elif blank == _TRENN:
            treffer.append(nr)
        elif blank.startswith(_ENDE) and len(blank) < 60:
            treffer.append(nr)
    return treffer


class KeineKonfliktmarkerTest(unittest.TestCase):

    def test_keine_versionierte_datei_traegt_marker(self):
        funde = []
        for rel in _versionierte_textdateien():
            pfad = os.path.join(REPO, rel)
            try:
                with open(pfad, "r", encoding="utf-8", errors="strict") as f:
                    text = f.read()
            except (UnicodeDecodeError, OSError):
                continue          # Binaerdatei o. ae. — nicht dieses Gate
            zeilen = marker_in(text)
            if zeilen:
                funde.append(f"{rel}: Zeile(n) {zeilen}")
        self.assertEqual([], funde,
                         "Merge-Konfliktmarker in versionierten Dateien:\n  "
                         + "\n  ".join(funde))

    def test_der_waechter_faengt_den_echten_fall(self):
        """★ Positivkontrolle mit dem TATSAECHLICHEN Vorfall.

        Ohne sie waere nicht zu unterscheiden, ob das Gate nichts findet oder
        nichts mehr prueft — dieselbe Vorsichtsmassnahme wie im Datenschutz-
        und im Bibliotheks-Gate.
        """
        echt = ("| VIZ-51 | P2 | teils | ... |\n"
                "<<<<<<< HEAD\n"
                "| VIZ-52 | P2 | done | ... |\n"
                "=======\n"
                "| QA-57 | P3 | todo | ... |\n"
                ">>>>>>> origin/main\n"
                "| QA-56 | P3 | todo | ... |\n")
        self.assertEqual([2, 4, 6], marker_in(echt))

    def test_gewoehnlicher_text_wird_nicht_beanstandet(self):
        """★ Gegenprobe. Ein Gate, das normale Dokumentation meldet, wird
        abgeschaltet — und `=======` bzw. `>>>` sind in Markdown gebraeuchlich.
        """
        harmlos = ("Ueberschrift\n"
                   "============\n"          # Setext-Unterstreichung: kuerzer
                   "\n"
                   "> Zitat\n"
                   ">>> noch ein Zitat\n"
                   "```\n"
                   ">>> python-prompt\n"
                   "```\n"
                   "Trennlinie:\n"
                   "-----------\n")
        self.assertEqual([], marker_in(harmlos))

    def test_setext_unterstreichung_genau_sieben_zeichen_ist_der_grenzfall(self):
        """Ehrlich benannte Grenze: eine Setext-Unterstreichung aus GENAU
        sieben ``=`` ist von einem Trennmarker nicht zu unterscheiden. Das ist
        der Preis dafuer, den Trenner ueberhaupt zu erkennen — und er ist
        vertretbar, weil eine Ueberschrift mit exakt dieser Breite selten ist
        und der Fehlalarm sofort sichtbar waere.
        """
        self.assertEqual([1], marker_in("=======\n"))


if __name__ == "__main__":
    unittest.main()
