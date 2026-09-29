"""QA-67: Show-Lint und Lade-Reparatur finden Ueberlappungen nach EINER Regel.

Der Lint (``capability.validate._check_patch``) verglich wie frueher die
Reparatur (STAB-26) nur Nachbarn in Adress-Reihenfolge: lag ein kurzes Geraet
zwischen zwei ueberlappenden, sah er die Ueberlappung nicht.
"""
import ast
import pathlib
import unittest

from src.core.capability.validate import _check_patch
from src.core.patch_ueberlappung import ueberlappende_paare

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _lint_paare(patch):
    out = set()
    for f in _check_patch({"patch": patch}):
        if f.code == "PATCH-UEBERLAPPUNG":
            out.add(tuple(sorted(x for x in "ABC" if f"'{x}'" in f.message)))
    return out


def _pf(label, adr, n, u=1):
    return {"label": label, "universe": u, "address": adr, "channel_count": n,
            "mode_name": "m"}


class RegelTest(unittest.TestCase):

    def test_jedes_paar(self):
        e = [(1, 100, "A"), (10, 12, "B"), (20, 22, "C")]
        self.assertEqual({(a[2], b[2]) for a, b in ueberlappende_paare(e)},
                         {("A", "B"), ("A", "C")})

    def test_dicht_an_dicht_ist_keine_ueberlappung(self):
        self.assertEqual(ueberlappende_paare([(1, 8, "A"), (9, 16, "B")]), [])

    def test_null_kanaele_ueberlappen_nichts(self):
        self.assertEqual(ueberlappende_paare([(1, 8, "A"), (5, 4, "B")]), [])


class LintTest(unittest.TestCase):

    def test_kurzes_geraet_verdeckt_nichts_mehr(self):
        """Der Befund: A ueberlappt C, B liegt dazwischen."""
        patch = [_pf("A", 1, 30), _pf("B", 10, 2), _pf("C", 25, 8)]
        self.assertEqual(_lint_paare(patch), {("A", "B"), ("A", "C")})

    def test_sauberer_patch(self):
        patch = [_pf("A", 1, 8), _pf("B", 9, 8), _pf("C", 1, 8, u=2)]
        self.assertEqual(_lint_paare(patch), set())


class EineQuelleTest(unittest.TestCase):
    """Beide Stellen rufen dieselbe Funktion — keine zweite Fassung der Regel."""

    def test_beide_nutzen_ueberlappende_paare(self):
        for rel in ("src/core/sync.py", "src/core/capability/validate.py"):
            baum = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
            aufrufe = [n for n in ast.walk(baum) if isinstance(n, ast.Call)
                       and getattr(n.func, "id", "") == "ueberlappende_paare"]
            self.assertTrue(aufrufe, rel)


if __name__ == "__main__":
    unittest.main()
