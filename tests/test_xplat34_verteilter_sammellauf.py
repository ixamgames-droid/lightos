"""XPLAT-34: der Zeitbomben-Waechter verteilt seinen Sammellauf auf mehrere
Kindprozesse.

Die Dauer von ``tests/test_zeitbomben_gate.py`` war die SUMME der Laufzeiten
aller Kandidaten (fremde Testdateien mit festem Datum) und wuchs mit jeder neuen
davon. Gemessen 2026-10-02 (Linux): 44,6 s der 76 s entfielen auf den einen
Sammellauf in ``pruefe``; auf Windows lag die Datei bei 145–169 s, bei einem
Segment-Limit von 300 s. Entscheidung A: den Sammellauf auf mehrere
Kindprozesse verteilen, Windows-Exit-Vertrag unveraendert.

Verteilt wird nach TESTS, nicht nach Dateien: jedes Kind sammelt alle
Kandidaten und faehrt jeden dritten Test (``tools/_zeitbomben_scheibe``). Nach
Dateien verteilt war das Ergebnis 58 % statt ein Drittel, weil eine Datei allein
~31 s von ~47 s brauchte.

Die ersten Klassen ersetzen ``zg.lauf`` durch eine Attrappe; ``EchteScheiben``
faehrt das Plugin in echten Kindprozessen. Was ein echter Gate-Lauf leistet,
belegen weiter ``tests/test_zeitbomben_gate.py`` (Proben, Kanarie, RepoTest) —
die laufen jetzt durch denselben Weg.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import zeitbomben_gate as zg                    # noqa: E402


class _Kandidaten(unittest.TestCase):
    """Sechs Wegwerf-Testdateien mit festem Datum — fuer ``pruefe`` Kandidaten."""

    def setUp(self):
        self.ordner = tempfile.mkdtemp(prefix="xplat34_")
        self.addCleanup(shutil.rmtree, self.ordner, True)
        self.dateien = []
        for i in range(6):
            pfad = os.path.join(self.ordner, f"test_kandidat_{i}.py")
            with open(pfad, "w", encoding="utf-8") as fh:
                fh.write(f'STEMPEL = "2026-0{i + 1}-15"\n'
                         "def test_x():\n    assert STEMPEL\n")
            self.dateien.append(pfad)
        self.aufrufe = []
        self.sperre = threading.Lock()
        self.gleichzeitig = 0
        self.hoechstens = 0
        alt = zg.lauf
        self.addCleanup(setattr, zg, "lauf", alt)
        zg.lauf = self._falscher_lauf
        self.antwort = lambda dateien, tage, scheibe: zg.Ergebnis(0, zg.MARKE_OK, True)

    def _falscher_lauf(self, dateien, tage, shim=zg.SHIM, zeitlimit=480,
                       uhr=zg.SPRUNG_UHR, scheibe=None):
        with self.sperre:
            self.aufrufe.append((list(dateien), tage, scheibe))
            self.gleichzeitig += 1
            self.hoechstens = max(self.hoechstens, self.gleichzeitig)
        try:
            time.sleep(0.2)
            return self.antwort(dateien, tage, scheibe)
        finally:
            with self.sperre:
                self.gleichzeitig -= 1


class VerteiltAufMehrereKinder(_Kandidaten):

    def test_der_sammellauf_laeuft_in_drei_kindern(self):
        bericht = zg.pruefe(self.ordner, dateien=self.dateien)
        self.assertTrue(bericht.gruen)
        laeufe = [a for a in self.aufrufe if a[1] == zg.SPRUNG_TAGE]
        self.assertEqual(len(laeufe), 3, "der Sammellauf muss auf drei Kinder verteilt sein")
        self.assertEqual(sorted(a[2] for a in laeufe), [(0, 3), (1, 3), (2, 3)],
                         "jedes Kind eine eigene Scheibe")
        for dateien, _tage, _scheibe in laeufe:
            self.assertEqual(sorted(dateien), sorted(self.dateien),
                             "jedes Kind sammelt ALLE Kandidaten")

    def test_die_kinder_laufen_gleichzeitig(self):
        zg.pruefe(self.ordner, dateien=self.dateien)
        self.assertEqual(self.hoechstens, 3, "die Kinder liefen nacheinander, nicht gleichzeitig")

    def test_ein_kind_reicht_als_rueckfall(self):
        zg.pruefe(self.ordner, dateien=self.dateien, kinder=1)
        self.assertEqual(len(self.aufrufe), 1)
        self.assertEqual(sorted(self.aufrufe[0][0]), sorted(self.dateien))
        self.assertIsNone(self.aufrufe[0][2])


class StrengZusammengefasst(_Kandidaten):

    def test_ein_stummes_kind_macht_den_lauf_ungueltig(self):
        self.antwort = lambda dateien, tage, scheibe: zg.Ergebnis(
            0, "ohne Marke", scheibe != (1, 3))
        with self.assertRaises(zg.SprungUnwirksam):
            zg.pruefe(self.ordner, dateien=self.dateien)

    def test_ein_rotes_kind_fuehrt_zu_den_einzellaeufen(self):
        rot = self.dateien[3]
        # Im Sammellauf ist Scheibe 3 rot; die Einzellaeufe danach (ohne
        # Scheibe) sind fuer die Datei ``rot`` mit Sprung rot, ohne gruen.
        self.antwort = lambda dateien, tage, scheibe: zg.Ergebnis(
            1 if (scheibe == (2, 3) or (scheibe is None and rot in dateien and tage))
            else 0, zg.MARKE_OK, True)
        bericht = zg.pruefe(self.ordner, dateien=self.dateien)
        self.assertEqual([os.path.basename(p) for p, _ in bericht.bomben],
                         [os.path.basename(rot)],
                         "rot mit Sprung, gruen ohne -> Zeitbombe, wie vorher")

    def test_ein_zeitlimit_wird_weitergereicht(self):
        def antwort(dateien, tage, scheibe):
            if scheibe == (0, 3):
                raise subprocess.TimeoutExpired(["pytest"], 1)
            return zg.Ergebnis(0, zg.MARKE_OK, True)
        self.antwort = antwort
        with self.assertRaises(subprocess.TimeoutExpired):
            zg.pruefe(self.ordner, dateien=self.dateien)


class EchteScheiben(unittest.TestCase):
    """Das Plugin im echten Kindprozess: jeder Test genau einmal, eine Scheibe
    ohne Tests ist kein Fehler."""

    def setUp(self):
        self.ordner = tempfile.mkdtemp(prefix="xplat34_echt_")
        self.addCleanup(shutil.rmtree, self.ordner, True)

    def _datei(self, name, n):
        pfad = os.path.join(self.ordner, name)
        with open(pfad, "w", encoding="utf-8") as fh:
            fh.write("".join(f"def test_{i}():\n    pass\n" for i in range(n)))
        return pfad

    @staticmethod
    def _bestanden(ausgabe):
        treffer = re.search(r"(\d+) passed", ausgabe)
        return int(treffer.group(1)) if treffer else 0

    def test_jeder_test_genau_einmal(self):
        dateien = [self._datei("test_a.py", 4), self._datei("test_b.py", 3)]
        zahlen = [self._bestanden(zg.lauf(dateien, 0, scheibe=(i, 3)).ausgabe)
                  for i in range(3)]
        self.assertEqual(sum(zahlen), 7)
        self.assertEqual(sorted(zahlen), [2, 2, 3])

    def test_jeder_test_genau_einmal_auch_bei_anderem_hash_seed(self):
        """Review #865: ein ``parametrize`` ueber eine Menge sammelt in jedem
        Kind (eigener Hash-Seed) in anderer Reihenfolge. Verteilt wird deshalb
        nach der Node-ID — jeder Fall genau einmal, egal welcher Seed."""
        pfad = os.path.join(self.ordner, "test_menge.py")
        with open(pfad, "w", encoding="utf-8") as fh:
            fh.write("import pytest\n"
                     "@pytest.mark.parametrize('x', set('abcdefghijkl'))\n"
                     "def test_fall(x):\n    pass\n")
        gesammelt = []
        for i, seed in enumerate(("1", "2", "3")):
            env = dict(os.environ, PYTHONHASHSEED=seed,
                       PYTHONPATH=os.pathsep.join([zg.SCHEIBE_ORDNER,
                                                   os.environ.get("PYTHONPATH", "")]))
            env[zg.SCHEIBE_VAR] = "%d/3" % i
            fertig = subprocess.run(
                [sys.executable, "-m", "pytest", "--collect-only", "-q",
                 "-p", zg.SCHEIBE_PLUGIN, "-p", "no:cacheprovider",
                 "--rootdir", self.ordner, pfad],
                cwd=self.ordner, env=env, text=True, capture_output=True, timeout=120)
            gesammelt += re.findall(r"test_fall\[(\w)\]", fertig.stdout)
        self.assertEqual(sorted(gesammelt), list("abcdefghijkl"),
                         "jeder Fall genau einmal ueber alle drei Kinder")

    def test_scheibe_ohne_tests_ist_kein_fehler(self):
        dateien = [self._datei("test_c.py", 1), self._datei("test_d.py", 1)]
        ergebnis = zg.lauf_verteilt(dateien, zg.SPRUNG_TAGE)
        self.assertTrue(ergebnis.sprung_wirksam, ergebnis.ausgabe[-1500:])
        self.assertEqual(ergebnis.rc, 0, ergebnis.ausgabe[-1500:])
        self.assertEqual(sum(self._bestanden(t) for t in ergebnis.ausgabe.split("── Kind")), 2)


if __name__ == "__main__":
    unittest.main()
