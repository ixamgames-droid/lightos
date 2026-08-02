"""FINALIZE — es gibt genau EINE Quelle für offene Aufgaben.

Beim Abgleich am 2026-08-02 beanspruchten **zwei** Dateien dieselbe Rolle:
``BACKLOG.md`` nennt sich „Single Source of Truth für den autonomen Loop",
``docs/OPEN_POINTS_OVERVIEW.md`` nannte sich „einzige Quelle der Wahrheit für
offene Aufgaben". Zwei Dokumente mit demselben Anspruch driften zwangsläufig —
und das war messbar:

* **46 Einträge** standen in den OFFEN-Abschnitten der Übersicht,
* davon tauchten **4** im Backlog auf,
* und **3** hatten sich dort selbst schon als „✅ umgesetzt" markiert, ohne den
  Abschnitt zu wechseln (gegen den Code nachgeprüft: alle drei wirklich fertig).

Die Übersicht ist seither ausdrücklich das **Reservoir** (Ideen, Langfrist,
bewusst Zurückgestelltes), nicht die Arbeitsliste. Dieses Gate hält die drei
Fehlerarten fest, die tatsächlich aufgetreten sind — es ersetzt keine Sorgfalt,
aber es merkt sich, was schon einmal schiefging.
"""
from __future__ import annotations

import os
import re
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UEBERSICHT = os.path.join(_REPO, "docs", "OPEN_POINTS_OVERVIEW.md")
_BACKLOG = os.path.join(_REPO, "BACKLOG.md")


def _lies(p: str) -> str:
    with open(p, encoding="utf-8") as f:
        return f.read()


def _offen_abschnitt(text: str) -> str:
    """Abschnitte 2–4 — die Teile, die offene Aufgaben auflisten."""
    return text[text.index("## 2. Alle offenen Punkte"):
                text.index("## 5. Erledigt laut Code")]


class QuellenlageTest(unittest.TestCase):

    def test_uebersicht_verweist_auf_den_backlog(self):
        """Wer die Datei oben aufschlägt, muss in den ersten Zeilen erfahren,
        dass die verbindliche Liste woanders steht."""
        kopf = "\n".join(_lies(_UEBERSICHT).splitlines()[:20])
        self.assertIn("BACKLOG.md", kopf,
                      "die Übersicht muss den Backlog als maßgeblich benennen")
        self.assertRegex(
            kopf, r"NICHT die Quelle der Wahrheit",
            "der Vorrang muss ausdrücklich dastehen, nicht nur implizit")

    def test_backlog_bleibt_die_arbeitsliste(self):
        self.assertIn("Single Source of Truth für den autonomen Loop",
                      _lies(_BACKLOG)[:600])

    def test_kein_offener_punkt_ist_in_wahrheit_erledigt(self):
        """Genau die Drift, die vorlag: drei Einträge standen unter „offen" und
        sagten im eigenen Text „✅ umgesetzt"."""
        treffer = []
        for m in re.finditer(r"^- \*\*`([^`]+)`", _offen_abschnitt(_lies(_UEBERSICHT)),
                             re.M):
            block_start = m.start()
            block = _offen_abschnitt(_lies(_UEBERSICHT))[block_start:block_start + 1200]
            block = re.split(r"^- \*\*`", block[1:], flags=re.M)[0]
            if "✅ umgesetzt" in block:
                treffer.append(m.group(1))
        self.assertEqual(
            treffer, [],
            'diese Einträge stehen unter "offen", bezeichnen sich aber selbst '
            'als umgesetzt — gehören nach Abschnitt 5 (mit Beleg gegen den Code)')

    def test_die_zahlen_in_den_ueberschriften_stimmen(self):
        """Eine falsche Zahl in der Überschrift ist die billigste Art, einen
        Eintrag zu übersehen."""
        text = _offen_abschnitt(_lies(_UEBERSICHT))
        for teil in re.split(r"(?=^### )", text, flags=re.M):
            kopf = teil.split("\n")[0]
            m = re.match(r"### (.+?)\s*\((\d+)\)\s*$", kopf)
            if not m:
                continue
            with self.subTest(abschnitt=m.group(1).strip()):
                self.assertEqual(
                    len(re.findall(r"^- \*\*`", teil, re.M)), int(m.group(2)),
                    f"Zähler in '{kopf}' passt nicht zu den Einträgen")


if __name__ == "__main__":
    unittest.main()
