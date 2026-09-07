"""XPLAT-35: Wenn ein Kindprozess scheitert, muss seine Ausgabe in der Meldung stehen.

``test_zeitbomben_gate.py`` startet pytest in Kindprozessen. Faellt so ein Kind,
stand in der Meldung bisher nur „AssertionError: 2 != 0" — die Ursache lag
ausschliesslich in der Kind-Ausgabe, und die wurde weggeworfen. Gemessen am
2026-09-07 (Sitzung B) in einem Gate-Lauf: beide KanarieTest-Tests rot, Exit 2
des Unter-pytest (= „ERROR collecting test session"), und WELCHE Sammlung
scheiterte war nicht mehr feststellbar.

Der Fallstrick dabei ist nicht „es gab keine Ausgabe", sondern die falsche
Haelfte: pytest schreibt Sammelfehler auf **stdout**, nicht auf stderr. Drei der
vier Pruefstellen reichten genau ``fertig.stderr`` weiter — bei dieser
Fehlerklasse eine leere Meldung.
"""
import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Das MODUL importieren, nicht die Namen: ein ``from ... import`` machte die
# fremden Testklassen zu Attributen hier, und pytest sammelte sie ein zweites
# Mal ein.
import test_zeitbomben_gate as zgt                       # noqa: E402

_QUELLE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "test_zeitbomben_gate.py")


class _Fertig:
    """Wie ``subprocess.CompletedProcess`` — nur die zwei Felder."""

    def __init__(self, stdout="", stderr=""):
        self.stdout, self.stderr = stdout, stderr


class _Ergebnis:
    """Wie ``zg.Ergebnis`` — traegt die Ausgabe in EINEM Feld."""

    def __init__(self, ausgabe):
        self.ausgabe = ausgabe


class KindAusgabeTest(unittest.TestCase):

    def test_stdout_landet_in_der_meldung_auch_ohne_stderr(self):
        """★ Der eigentliche Fall: pytest meldet Sammelfehler auf stdout. Wer
        nur stderr weiterreicht, bekommt hier nichts."""
        text = zgt._kind_ausgabe(_Fertig(stdout="ERROR collecting test session"))
        self.assertIn("ERROR collecting test session", text)

    def test_stderr_geht_auch_nicht_verloren(self):
        text = zgt._kind_ausgabe(_Fertig(stderr="Traceback (most recent call last)"))
        self.assertIn("Traceback", text)

    def test_die_andere_ergebnisform_wird_ebenfalls_verstanden(self):
        """``zg.lauf`` liefert kein CompletedProcess, sondern ein Ergebnis mit
        ``ausgabe`` — eine Stelle im Waechter benutzt genau diese Form."""
        self.assertIn("ERROR collecting", zgt._kind_ausgabe(_Ergebnis("ERROR collecting")))

    def test_ohne_ausgabe_sagt_die_meldung_das_ausdruecklich(self):
        """Sonst sieht 'keine Ausgabe' aus wie 'nicht nachgesehen'."""
        self.assertIn("ohne Ausgabe", zgt._kind_ausgabe(_Fertig()))

    def test_gekuerzt_wird_vorne_denn_der_fehler_steht_hinten(self):
        text = zgt._kind_ausgabe(_Fertig(stdout="\n".join(str(i) for i in range(200))),
                                 zeilen=5)
        self.assertIn("199", text)              # das Ende ist da
        self.assertNotIn("\n0\n", text)         # der Anfang nicht
        self.assertIn("Zeilen davor", text)     # und es sagt, dass gekuerzt wurde


class JedePruefstelleReichtDieAusgabeWeiterTest(unittest.TestCase):
    """★★ Der Regressionsschutz. Eine neue ``assertEqual(x.returncode, 0, "…")``
    ohne Kind-Ausgabe faellt hier auf, statt erst im naechsten undurchsichtig
    roten Gate-Lauf."""

    def _pruefstellen(self):
        baum = ast.parse(open(_QUELLE, encoding="utf-8").read())
        treffer = []
        for k in ast.walk(baum):
            if not (isinstance(k, ast.Call)
                    and isinstance(k.func, ast.Attribute)
                    and k.func.attr == "assertEqual" and len(k.args) >= 2):
                continue
            erst = k.args[0]
            if not (isinstance(erst, ast.Attribute)
                    and erst.attr in ("returncode", "rc")):
                continue
            meldung = k.args[2] if len(k.args) > 2 else None
            reicht_weiter = meldung is not None and any(
                isinstance(u, ast.Call) and isinstance(u.func, ast.Name)
                and u.func.id == "_kind_ausgabe" for u in ast.walk(meldung))
            treffer.append((k.lineno, reicht_weiter))
        return treffer

    def test_der_waechter_findet_ueberhaupt_pruefstellen(self):
        """Positivkontrolle. Ohne sie waere der Test unten gruen, sobald das
        Suchmuster nicht mehr passt — der bequemste Ausfall von allen."""
        self.assertGreaterEqual(len(self._pruefstellen()), 4)

    def test_keine_pruefstelle_verschweigt_die_kind_ausgabe(self):
        stumm = [z for z, ok in self._pruefstellen() if not ok]
        self.assertEqual(stumm, [],
                         f"Rueckgabewert geprueft, Kind-Ausgabe verschwiegen — "
                         f"{_QUELLE} Zeile(n) {stumm}")


if __name__ == "__main__":
    unittest.main()
