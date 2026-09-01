"""QA-53 — die Abschlusszahl des Segment-Runners darf nicht luegen.

★ **Der Anlass.** Am 2026-08-06 meldete das Gate „68/69 Segmente gruen",
gefahren wurden 584 Dateien. Notiert wurde damals die Vermutung, ein Zaehler
aus der parallelen Spur erreiche den Elternprozess nicht. **Das war falsch.**

Gemessen am 2026-08-11: `TOT` ist schlicht `wc -l` auf `results.tsv`, und ein
ZWEITER Lauf im selben Repo beginnt mit `rm -rf "$OUTDIR"` — er raeumt die
Zeilen des ersten weg, der zaehlt danach nur noch seinen Rest. Ausgeloest hat
das `tests/test_verify_loop_sperre.py`, das den Runner ohne Argumente startete
(= die volle Suite).

**Warum die Warnung bleibt, obwohl die Ursache behoben ist:** zwei Sitzungen
auf einem Rechner koennen denselben Fall jederzeit wieder erzeugen — genau
dafuer gibt es COORDINATION.md. Und die Zahl ist nicht nur kosmetisch: unter
ihr steht die Liste der roten Segmente, und die kann dann Zeilen eines FREMDEN
Laufs enthalten.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNNER = REPO / "tools" / "verify_segmented.sh"

# Eine Testdatei, die dem Runner mitten im Lauf die Ergebnisliste wegraeumt —
# also genau das tut, was ein zweiter Lauf mit seinem `rm -rf` bewirkt. Das
# macht den Fall DETERMINISTISCH: kein Warten auf ein Zeitfenster, kein Timing.
RAEUMER = """
import os
def test_raeumt_die_ergebnisliste_weg():
    ziel = os.path.join(os.environ["LIGHTOS_SEG_OUT"], "results.tsv")
    open(ziel, "w").close()
"""

HARMLOS = """
def test_harmlos():
    assert True
"""


# ⚠️ QA-69: der Guard war ``os.access(RUNNER, os.X_OK)`` — und der greift auf
# Windows NIE, weil ``os.access(..., X_OK)`` dort fuer jede existierende Datei
# ``True`` liefert (ein Ausfuehrbar-Bit gibt es nicht). Die ``.sh`` ist mit
# eingecheckt, liegt also auch auf einem Windows-Checkout. Der Test lief damit
# los, startete den LINUX-Runner und faerbte sich rot, ohne irgendetwas ueber
# den Zaehler auszusagen.
#
# Dieselbe Falle wurde in ``tests/test_gate_webengine_lane.py`` bereits
# behoben; hier steht bewusst dieselbe Formulierung, damit beide Stellen
# gemeinsam auffallen, wenn sich die Lage aendert.
#
# Der Segment-Runner IST das Linux-Gate: er startet je Segment ein
# ``venv/bin/python``, das es auf einem Windows-Checkout nicht gibt. Auf
# Windows faehrt das Gate ueber ``verify_segmented.ps1`` bzw.
# ``run_tests.ps1 -Isolate``. Dass fuer DIESE Zusicherung („der Zaehler luegt
# nicht") auf der Windows-Seite kein Gegenstueck existiert, ist als
# **XPLAT-23** erfasst — die Luecke wird hier benannt, nicht versteckt.
_RUNNER_LAEUFT = (RUNNER.exists() and os.name != "nt"
                  and shutil.which("bash") is not None)
_RUNNER_GRUND = ("verify_segmented.sh ist das Linux-Gate — auf Windows faehrt "
                 "verify_segmented.ps1 / run_tests.ps1 -Isolate (XPLAT-23), "
                 "und bash fehlt im PATH")


@unittest.skipUnless(_RUNNER_LAEUFT, _RUNNER_GRUND)
class ZaehlerWarntWennErgebnisseFehlenTest(unittest.TestCase):

    def _lauf(self, raeumen: bool):
        with tempfile.TemporaryDirectory(prefix="lightos_qa53_") as tmp:
            tmp = Path(tmp)
            # Alphabetisch sortiert, `-j 1`: a schreibt seine Zeile, der
            # Raeumer in der MITTE loescht sie waehrend seines Laufs, danach
            # haengen b und c ihre eigenen an -> 2 Zeilen bei 3 Dateien.
            # (Erster Versuch hatte den Raeumer vorne — dort loescht er eine
            # noch leere Datei, und `run_one` haengt seine Zeile ERST DANACH an;
            # der Lauf kam auf saubere 3/3 und der Test war gruen ohne Befund.)
            dateien = []
            for name, inhalt in (("a_harmlos", HARMLOS),
                                 ("b_raeumer", RAEUMER if raeumen else HARMLOS),
                                 ("c_harmlos", HARMLOS)):
                p = tmp / f"test_{name}.py"
                p.write_text(inhalt, encoding="utf-8")
                dateien.append(str(p))
            umgebung = dict(os.environ)
            umgebung["LIGHTOS_SEG_OUT"] = str(tmp / "out")
            return subprocess.run(
                ["bash", str(RUNNER), "-j", "1", *dateien],
                cwd=str(REPO), env=umgebung, capture_output=True,
                text=True, timeout=300)

    def test_fehlende_zeilen_werden_gemeldet(self):
        erg = self._lauf(raeumen=True)
        self.assertIn("WARNUNG", erg.stdout,
                      "Der Runner hat eine unvollstaendige Ergebnisliste "
                      f"stillschweigend gezaehlt:\n{erg.stdout}")
        self.assertIn("2 Zeilen", erg.stdout, erg.stdout)
        self.assertIn("3 Dateien", erg.stdout, erg.stdout)

    def test_ein_unvollstaendiger_lauf_meldet_NICHT_gruen(self):
        """★★ Die gefaehrlichere Haelfte des Befunds.

        `BAD` zaehlt die roten Zeilen aus derselben `results.tsv`, die der
        zweite Lauf wegraeumt — mit ihr verschwinden auch die roten Zeilen.
        Der Exit-Code wurde damit 0: **das Gate meldete gruen, obwohl Segmente
        rot waren.** Die falsche Zahl sieht man beim Lesen, das falsche Gruen
        nicht; ein Merge-Kriterium, das im Zweifel Erfolg meldet, ist keins.
        """
        erg = self._lauf(raeumen=True)
        self.assertNotEqual(0, erg.returncode,
                            "Unvollstaendige Ergebnisliste, trotzdem gruen:\n"
                            + erg.stdout)

    def test_positivkontrolle_ein_sauberer_lauf_warnt_NICHT(self):
        """★ Ohne diese Gegenprobe waere der Test oben wertlos: eine Warnung,
        die immer erscheint, ist keine Warnung. Sie wuerde bei jedem Gate-Lauf
        mitlaufen und genau die Gewoehnung erzeugen, gegen die sie gebaut ist.
        """
        erg = self._lauf(raeumen=False)
        self.assertEqual(0, erg.returncode, erg.stdout[-2000:])
        self.assertNotIn("WARNUNG", erg.stdout, erg.stdout)
        self.assertIn("3/3 Segmente gruen", erg.stdout, erg.stdout)


if __name__ == "__main__":
    unittest.main()
