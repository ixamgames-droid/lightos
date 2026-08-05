"""Jedes Builtin gehoert an ZWEI Stellen — Erstbefuellung UND Backfill.

`fixture_db.py` legt Geraeteprofile an zwei Orten an:

* `_seed(s)`            — die Erstbefuellung einer noch leeren `fixtures.db`
* `ensure_builtins()`   — der Backfill fuer bereits befuellte, aeltere Datenbanken

Ein neues Geraet muss in BEIDE. Steht es nur im Backfill, faellt das im Betrieb
nicht auf, weil `engine()` zufaellig erst `_seed_if_empty()` und dann
`ensure_builtins()` ruft — das Profil kommt also trotzdem an. Es faellt aber in
den TESTS auf, und zwar als Blindfleck statt als Fehler: `_fixture_quelle.
frische_library` seedet ueber `_seed`, und was dort fehlt, ist fuer jeden
Profil-Test schlicht nicht vorhanden.

★ Genau so passiert am 2026-08-05 mit dem ZQ06121: das Profil stand nur im
Backfill. Sein Profil-Test fand `None` vor und waere ohne diese Regel gar nicht
erst schreibbar gewesen — ein Geraet ohne wirksamen Test, ohne dass irgendwo
etwas rot wurde.

**Nur diese eine Richtung wird geprueft.** Umgekehrt stehen 16 Profile nur in
`_seed` (BAR12, PAR3-5, MH8/16, DIM1/4 …) — das ist der Urbestand: sie waren von
der ersten Fassung an in der Erstbefuellung, also hat jede jemals geseedete
Datenbank sie ohnehin. Ein Backfill dafuer waere toter Code.

**Statisch, nicht ueber die Datenbank.** Ein echter Seed kostet ~1,5 s CPU, und
diese Testspur laeuft neben den WebEngine-Segmenten, denen genau das den
GPU-Kontext wegnimmt (XPLAT-17, gemessen: mit Seed 3/3 rot, ohne 558/558 gruen).
Zwei Seeds waeren also die teuerste denkbare Bauart fuer eine Frage, die der
Syntaxbaum in Millisekunden beantwortet.
"""
from __future__ import annotations

import ast
import os
import unittest

QUELLE = os.path.join(os.path.dirname(__file__), "..", "src", "core",
                      "database", "fixture_db.py")

# `_add_*`-Funktionen, die KEIN Profil anlegen, sondern Bausteine sind.
HELFER = {"_add_modes", "_add_fixture"}


def _baum():
    with open(os.path.abspath(QUELLE), encoding="utf-8") as f:
        return ast.parse(f.read())


def _profil_aufrufe(funktionsname: str) -> set[str]:
    """Alle `_add_xxx(...)`-Aufrufe innerhalb einer Top-Level-Funktion."""
    for knoten in _baum().body:
        if isinstance(knoten, ast.FunctionDef) and knoten.name == funktionsname:
            return {
                k.func.id
                for k in ast.walk(knoten)
                if isinstance(k, ast.Call)
                and isinstance(k.func, ast.Name)
                and k.func.id.startswith("_add_")
                and k.func.id not in HELFER
            }
    raise AssertionError(f"Funktion {funktionsname} nicht gefunden — umbenannt?")


class SeedBackfillParitaetTest(unittest.TestCase):

    def setUp(self):
        self.seed = _profil_aufrufe("_seed")
        self.backfill = _profil_aufrufe("ensure_builtins")

    def test_jedes_backfill_profil_steht_auch_in_der_erstbefuellung(self):
        fehlend = sorted(self.backfill - self.seed)
        self.assertEqual(fehlend, [], (
            "Diese Profile werden nur nachgeruestet, aber nie erstbefuellt — "
            "sie sind damit in jedem Profil-Test unsichtbar (frische_library "
            f"ruft nur _seed): {fehlend}"))

    def test_beide_listen_sind_nicht_versehentlich_leer(self):
        # Ohne diese Absicherung wuerde der Test oben gruen bleiben, wenn die
        # AST-Suche ins Leere greift (Funktion umbenannt, Aufrufe ueber eine
        # Tabelle statt direkt). Er pruefte dann die leere Menge gegen die
        # leere Menge — die klassische Art, wie ein Struktur-Test verstummt.
        #
        # ★ Die Schwelle liegt bewusst WEIT unter dem Ist-Stand (je 31). Im
        # ersten Wurf stand sie auf 30, also direkt an der Kante — die Probe
        # („eine Zeile aus `_seed` entfernen") machte dadurch auch DIESEN Test
        # rot, obwohl er mit der Frage nichts zu tun hat. Eine Sicherung, die
        # bei jeder normalen Aenderung mitschreit, verwaessert die Diagnose des
        # Tests, den sie absichern soll.
        self.assertGreater(len(self.seed), 15,
                           "Erstbefuellung wirkt zu klein — greift die AST-Suche noch?")
        self.assertGreater(len(self.backfill), 15,
                           "Backfill wirkt zu klein — greift die AST-Suche noch?")

    def test_der_zq06121_ist_an_beiden_stellen(self):
        # Der konkrete Ausloeser, als Regressionsanker.
        self.assertIn("_add_uking_zq06121", self.seed)
        self.assertIn("_add_uking_zq06121", self.backfill)


if __name__ == "__main__":
    unittest.main()
