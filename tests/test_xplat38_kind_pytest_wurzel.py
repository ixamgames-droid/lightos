"""XPLAT-38: Der Kind-pytest darf nicht das halbe Home-Verzeichnis absammeln.

``tools/zeitbomben_gate.lauf`` startet pytest im Kindprozess. Liegen die Ziele
AUSSERHALB des Repos -- die Proben liegen im Temp-Bereich --, dann bestimmt
pytest sein rootdir ueber die ``pytest.ini`` im Repo und baut den Sammelbaum
vom gemeinsamen Vorfahren von rootdir und Ziel aus. Der ist das
Benutzerverzeichnis. pytest laeuft dann `%TEMP%` mit ab, und weil Nachbartests
dort staendig eigene Ordner loeschen, beendet ein ``lstat`` auf einen gerade
verschwundenen Eintrag die Sammlung: ``Interrupted: 1 error during
collection``, Exit 2.

Gemessen am 2026-09-07 (Sitzung B), zwoelf Kindlaeufe je Variante, mit einer
Schleife ueber ``test_qa58_bibliothek_schema_unberuehrt`` als Nachbarn:
**ohne ``--rootdir`` 11 von 12 gescheitert, mit ``--rootdir`` 0 von 12.**
Das erklaert, warum es immer genau dieser Nachbar war (viele kurzlebige
Temp-Ordner) -- und warum die Datei allein nie rot wurde.
"""
import os
import sys
import subprocess
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools.zeitbomben_gate as zg                      # noqa: E402


class WurzelEntscheidungTest(unittest.TestCase):
    """Die Entscheidung selbst -- deterministisch, ohne Kindprozess."""

    def test_ziele_ausserhalb_bekommen_ihren_eigenen_ordner(self):
        ordner = tempfile.mkdtemp(prefix="x38_")
        self.addCleanup(os.rmdir, ordner)
        datei = os.path.join(ordner, "test_x.py")
        self.assertEqual(zg._wurzel_fuer([datei]), ordner)

    def test_ziele_im_repo_bleiben_wie_bisher(self):
        """★ Der echte Gate-Lauf uebergibt Repo-Dateien. Wuerde er hier ein
        rootdir bekommen, aenderte diese Reparatur den Normalbetrieb -- genau
        das soll sie nicht."""
        drin = os.path.join(zg.REPO, "tests", "test_zeitbomben_gate.py")
        self.assertIsNone(zg._wurzel_fuer([drin]))

    def test_gemischt_lieber_nichts_als_etwas_falsches(self):
        """Bei gemischten Zielen waere der gemeinsame Vorfahr wieder das
        Benutzerverzeichnis -- also der Zustand, den wir gerade abstellen."""
        ordner = tempfile.mkdtemp(prefix="x38_")
        self.addCleanup(os.rmdir, ordner)
        drin = os.path.join(zg.REPO, "tests", "test_zeitbomben_gate.py")
        self.assertIsNone(zg._wurzel_fuer([drin, os.path.join(ordner, "test_x.py")]))

    def test_ohne_dateien_keine_entscheidung(self):
        self.assertIsNone(zg._wurzel_fuer([]))

    def test_mehrere_proben_bekommen_den_gemeinsamen_ordner(self):
        ordner = tempfile.mkdtemp(prefix="x38_")
        a = os.path.join(ordner, "a"); b = os.path.join(ordner, "b")
        os.makedirs(a); os.makedirs(b)
        self.addCleanup(lambda: [os.rmdir(a), os.rmdir(b), os.rmdir(ordner)])
        self.assertEqual(zg._wurzel_fuer([os.path.join(a, "test_1.py"),
                                          os.path.join(b, "test_2.py")]), ordner)


class BefehlTraegtDieWurzelTest(unittest.TestCase):
    """Was der Kind-Befehl traegt -- der Regressionsschutz."""

    def test_bei_proben_draussen_steht_rootdir_im_befehl(self):
        ordner = tempfile.mkdtemp(prefix="x38_")
        self.addCleanup(os.rmdir, ordner)
        befehl = zg._befehl_fuer([os.path.join(ordner, "test_x.py")], 0)
        self.assertIn("--rootdir", befehl)
        self.assertEqual(befehl[befehl.index("--rootdir") + 1], ordner)

    def test_bei_repo_dateien_bleibt_der_befehl_unveraendert(self):
        """★ Der echte Gate-Lauf uebergibt Repo-Dateien. Diese Reparatur darf
        den Normalbetrieb nicht anfassen."""
        drin = os.path.join(zg.REPO, "tests", "test_zeitbomben_gate.py")
        self.assertNotIn("--rootdir", zg._befehl_fuer([drin], 0))


class DieFlaggeWirktBeiPytestTest(unittest.TestCase):
    """★★ Dass ``--rootdir`` tut, was wir annehmen -- an echtem pytest gemessen,
    zweiseitig. Der Schaden selbst (ein ``lstat``-Wettlauf beim Aufzaehlen des
    Vorfahren-Verzeichnisses) ist nur statistisch zu zeigen; DASS die Flagge
    die Sammelwurzel verschiebt, ist es nicht.
    """

    def setUp(self):
        self.ordner = tempfile.mkdtemp(prefix="x38_wurzel_")
        self.pfad = os.path.join(self.ordner, "test_x38_gruen.py")
        with open(self.pfad, "w", encoding="utf-8") as f:
            f.write("def test_gruen():" + chr(10) + "    assert True" + chr(10))

    def tearDown(self):
        for weg in (self.pfad, self.ordner):
            try:
                os.remove(weg) if os.path.isfile(weg) else os.rmdir(weg)
            except OSError:
                pass

    def _kopfzeile(self, extra):
        fertig = subprocess.run(
            [sys.executable, "-m", "pytest", "-p", "no:cacheprovider"] + extra
            + [self.pfad],
            cwd=zg.REPO, text=True, capture_output=True, timeout=300)
        for zeile in (fertig.stdout or "").splitlines():
            if zeile.startswith("rootdir:"):
                return zeile.split(":", 1)[1].strip()
        self.fail("pytest hat keine rootdir-Zeile gedruckt: " + (fertig.stdout or "")[:300])

    def test_ohne_flagge_liegt_die_wurzel_ueber_repo_UND_probe(self):
        """★ Die Negativkontrolle -- und zugleich der Beleg fuer den Schaden.
        Ohne Flagge nimmt pytest den gemeinsamen Vorfahren von Aufrufverzeichnis
        und Ziel. Gemessen ist das das Benutzerverzeichnis: eine Wurzel, die
        SOWOHL ueber dem Repo ALS AUCH ueber dem Probenordner liegt -- und damit
        ueber `%TEMP%`. Ohne diese Pruefung belegte der Test unten nur, dass eine
        Zeile existiert, nicht dass sich etwas geaendert hat."""
        ohne = self._kopfzeile([])
        self.assertNotEqual(os.path.normcase(ohne), os.path.normcase(self.ordner))
        for drunter in (self.ordner, zg.REPO):
            self.assertTrue(
                os.path.normcase(drunter).startswith(os.path.normcase(ohne) + os.sep),
                f"{drunter} liegt nicht unter der gemeldeten Wurzel {ohne}")

    def test_mit_flagge_liegt_die_wurzel_im_probenordner(self):
        self.assertEqual(os.path.normcase(self._kopfzeile(["--rootdir", self.ordner])),
                         os.path.normcase(self.ordner))



if __name__ == "__main__":
    unittest.main()
