"""PROC-13: das Verfahren gegen Gate-Messfehler steht in WORKFLOW.md.

Zwei Messfehler haben am 05./06.09. beide Sitzungen je Stunden gekostet, und
beide sehen aus wie ein Flake: der Baum aendert sich WAEHREND des Laufs, oder er
war von vornherein der falsche (Zweig vor einem Merge abgezweigt).

★ **Warum ein Test und nicht nur ein Absatz.** Genau das ist die Lehre des
Tages: eine Regel, die nur in Prosa steht, ist nicht durchgesetzt — sie ist eine
Bitte (QA-78). Dieser Waechter haelt fest, dass die Abhilfe UND die zwei Fallen
benannt bleiben; wer den Abschnitt kuerzt, merkt es hier.
"""
from __future__ import annotations

import os
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _workflow() -> str:
    with open(os.path.join(_REPO, "WORKFLOW.md"), encoding="utf-8") as f:
        return f.read()


class DokuTest(unittest.TestCase):
    def test_die_abhilfe_steht_da(self):
        """Der mechanische Weg — ein festgepinnter, eigener Gate-Worktree."""
        text = _workflow()
        self.assertIn("worktree add --detach", text,
                      "WORKFLOW.md nennt den festgepinnten Gate-Worktree nicht "
                      "— dann bleibt 'nicht am Baum arbeiten' reine Disziplin")

    def test_beide_messfehler_sind_benannt(self):
        """Nicht nur 'der Baum aendert sich', sondern auch die veraltete Basis.

        ★ Die zweite ist die unauffaelligere: der Lauf ist in sich konsistent
        und misst trotzdem einen Fehler, den ein Merge laengst behoben hat.
        """
        text = _workflow().lower()
        self.assertIn("waehrend des laufs", text)
        self.assertIn("von vornherein der falsche", text)

    def test_die_zwei_fallen_stehen_da(self):
        text = _workflow()
        # ⚠️ NICHT auf "pgrep" allein pruefen: das Wort steht schon an anderer
        # Stelle in WORKFLOW.md (Zeile 221, "laeuft eine LightOS-Instanz?").
        # Die Mutationsprobe hat genau das gefangen — die Zusicherung war
        # gruen, obwohl der Absatz entfernt war. Geprueft wird deshalb der
        # SATZ, der die Falle beschreibt, nicht das Werkzeug.
        self.assertIn("findet die **eigene** Kommandozeile", text,
                      "die Selbsttreffer-Falle der Warteschleife fehlt")
        self.assertIn("porcelain", text,
                      "die Falle 'leere Ausgabe ist nicht Erfolg' fehlt")

    def test_der_plattform_unterschied_beim_venv_steht_da(self):
        """★ Er ist nachgemessen und nicht symmetrisch.

        `verify_loop.ps1` faellt auf das venv des Haupt-Checkouts zurueck,
        `verify_loop.sh` NICHT. Wer das gleichsetzt, schickt eine Linux-Sitzung
        in einen Abbruch — oder laesst eine Windows-Sitzung unnoetig linken.
        """
        text = _workflow()
        self.assertIn("verify_loop.sh` sucht **nur im Repo**", text,
                      "der Plattform-Unterschied beim venv fehlt")

    def test_das_lastmuster_beim_lesen_steht_da(self):
        """Wandernde Ausfaelle sind Last, kein Regress — gemessen am 05.09."""
        text = _workflow()
        self.assertIn("LIGHTOS_VERIFY_JOBS=2", text,
                      "der gemessene Ausweg bei wandernden Ausfaellen fehlt")


if __name__ == "__main__":
    unittest.main()
