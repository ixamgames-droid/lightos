"""XPLAT-55: ein Zeitlimit des Zeitbomben-Waechters darf das Windows-Gate nicht
gruen lassen.

**Befund (Sitzung D, 11.10. und 18.10.2026, Windows x64).**
``tests/test_zeitbomben_gate.py`` lief im Voll-Gate ins 300-s-Segmentlimit.
``verify_segmented.ps1`` zaehlte das als ZEIT, und nach dem Exit-Vertrag
(XPLAT-28) faerben Zeitlimits nicht rot: das Gate meldete Exit 0, der Waechter
war still nicht ausgewertet. Die Laufzeit ist seit QA-102 wieder unter dem
Limit (Windows im Gate 201-250 s), die stille Toleranz aber war geblieben.

**Warum die Toleranz hier nicht traegt.** XPLAT-28 begruendet sie mit der
60-s-Klammer aus ``pytest.ini``: ein Haenger IM Test stirbt nach 60 s rot, nur
ein Abbau-Haenger NACH den Tests erreicht die Segmentgrenze. Der Waechter setzt
``pytestmark = pytest.mark.timeout(600)`` — fuer ihn gilt die Klammer nicht,
und ein Zeitlimit heisst schlicht: seine Tests liefen nicht zu Ende.

**Regel (Test-ZeitToleranzGedeckt).** Hebt eine Datei ``pytest.mark.timeout``
auf das Segmentlimit oder darueber (oder schaltet ihn mit 0 ab), zaehlt ihr
Zeitlimit ROT (``$fail``). Fuer alle anderen Dateien bleibt die Einzelregel aus
XPLAT-28 unveraendert. Linux (``verify_segmented.sh``) zaehlt ohnehin jeden
``rc != 0`` rot.

Der Verhaltensnachweis braucht PowerShell und laeuft nur unter Windows und nur
im Einzellauf (Gate im Gate, s. XPLAT-27/31). Die statischen Tests laufen
ueberall und halten die Verdrahtung fest.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "tools" / "verify_segmented.ps1"
RUNNER_SH = REPO / "tools" / "verify_segmented.sh"
WAECHTER = REPO / "tests" / "test_zeitbomben_gate.py"

_IST_WINDOWS = sys.platform == "win32"
_IM_SEGMENT = bool(os.environ.get("LIGHTOS_IM_SEGMENT"))


def _quelle() -> str:
    return RUNNER.read_text(encoding="utf-8", errors="replace")


def _funktion(name: str) -> str:
    """Rumpf einer PowerShell-Funktion bis zur naechsten ``function``-Zeile."""
    m = re.search(r"^function\s+" + re.escape(name) + r"\b(.*?)(?=^function\s|\Z)",
                  _quelle(), re.S | re.M)
    if not m:
        raise AssertionError(f"Funktion {name} fehlt in verify_segmented.ps1")
    return m.group(1)


def _gedeckt(text: str, limit: int) -> bool:
    """Wendet das Muster AUS DEM RUNNER (nicht eine Kopie) auf ``text`` an."""
    rumpf = _funktion("Test-ZeitToleranzGedeckt")
    m = re.search(r"\[regex\]::Matches\(\$text,\s*'([^']+)'\)", rumpf)
    if not m:
        raise AssertionError("Test-ZeitToleranzGedeckt sucht kein timeout-Muster mehr")
    for treffer in re.finditer(m.group(1), text):
        sek = int(treffer.group(1))
        if sek == 0 or sek >= limit:
            return False
    return True


class VerdrahtungTest(unittest.TestCase):
    """Statisch — laeuft auf jeder Plattform und in jedem Lauf."""

    def test_der_zeitlimit_zweig_fragt_die_toleranz_ab(self):
        quelle = _quelle()
        zweig = re.search(r"TotalSeconds\s*-gt\s*\$TimeoutSec\)(.*?)\$laufend\.Remove",
                          quelle, re.S)
        self.assertIsNotNone(zweig, "Zeitlimit-Zweig im Runner nicht gefunden")
        self.assertIn("Test-ZeitToleranzGedeckt", zweig.group(1),
                      "ein Zeitlimit wird wieder ungeprueft toleriert — der "
                      "Zeitbomben-Waechter faerbt dann im Limit nichts rot (XPLAT-55)")
        self.assertIn('"zeit-rot"', zweig.group(1))

    def test_zeit_rot_zaehlt_als_failure(self):
        m = re.search(r'"zeit-rot"\s*\{([^}]*)\}', _funktion("Complete-Segment"))
        self.assertIsNotNone(m, 'Complete-Segment kennt "zeit-rot" nicht')
        self.assertIn("$script:fail +=", m.group(1),
                      '"zeit-rot" muss in $fail landen — nur $fail faerbt den Exit rot')
        self.assertNotIn("$script:timeout", m.group(1))

    def test_die_einzelregel_fuer_andere_dateien_bleibt(self):
        """Gegenprobe: kein pauschales Rot fuer jedes Zeitlimit (XPLAT-28)."""
        quelle = _quelle()
        self.assertRegex(quelle, r"if\s*\(\$fail\.Count\)\s*\{\s*exit 1\s*\}")
        self.assertNotRegex(quelle, r"if\s*\(\$fail\.Count\s*-or\s*\$timeout\.Count\)")
        self.assertRegex(quelle, r'Complete-Segment \$rec 124 "zeit"\s*\}')


class MusterTest(unittest.TestCase):
    """Das Muster des Runners, angewandt in Python."""

    def test_der_zeitbomben_waechter_faellt_unter_die_regel(self):
        """★ Der eigentliche Fall: im Voll-Lauf (300 s) wie im Einzellauf (600 s)."""
        text = WAECHTER.read_text(encoding="utf-8", errors="replace")
        self.assertFalse(_gedeckt(text, 300),
                         "ein Zeitlimit des Zeitbomben-Waechters wuerde wieder "
                         "still toleriert")
        self.assertFalse(_gedeckt(text, 600))

    def test_eine_datei_ohne_gehobenes_limit_bleibt_toleriert(self):
        self.assertTrue(_gedeckt("def test_a():\n    pass\n", 300))
        self.assertTrue(_gedeckt("@pytest.mark.timeout(170)\ndef test_a():\n    pass\n", 300))

    def test_grenzfaelle(self):
        self.assertFalse(_gedeckt("pytestmark = pytest.mark.timeout(300)\n", 300))
        self.assertFalse(_gedeckt("@pytest.mark.timeout(0)\n", 300))
        self.assertFalse(_gedeckt("@pytest.mark.timeout(timeout=900)\n", 300))
        self.assertTrue(_gedeckt("@pytest.mark.timeout(299)\n", 300))

    def test_linux_zaehlt_jedes_zeitlimit_ohnehin_rot(self):
        quelle = RUNNER_SH.read_text(encoding="utf-8", errors="replace")
        self.assertIn("BAD=$(awk -F'\\t' '$1!=0'", quelle)
        self.assertRegex(quelle, r'exit "\$BAD"')


@unittest.skipUnless(_IST_WINDOWS, "verify_segmented.ps1 ist das Windows-Gate")
@unittest.skipIf(_IM_SEGMENT, "startet selbst einen Segment-Runner (Gate im Gate, "
                 "QA-53). Gezielt: .\\tools\\verify_loop.ps1 "
                 "tests\\test_xplat55_zeitlimit_waechter_rot.py")
class VerhaltenTest(unittest.TestCase):
    """Echter Runner: ein haengendes Segment mit und ohne gehobenes Limit."""

    GRUEN = "def test_gruen():\n    assert True\n"
    HAENGT = "{kopf}import time\n\n\ndef test_haengt():\n    time.sleep({sek})\n"

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory(prefix="lightos_xplat55_g_") as tmp:
            probe = Path(tmp) / "test_grundlast.py"
            probe.write_text(cls.GRUEN, encoding="utf-8")
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
            start = time.monotonic()
            subprocess.run([sys.executable, "-m", "pytest", str(probe), "-q",
                            "-p", "no:cacheprovider"], cwd=str(REPO), env=env,
                           capture_output=True, timeout=600)
            cls.TIMEOUT = max(25, int((time.monotonic() - start) * 4) + 1)

    def _lauf(self, kopf: str):
        with tempfile.TemporaryDirectory(prefix="lightos_xplat55_") as tmp:
            tmp = Path(tmp)
            a = tmp / "test_a_gruen.py"
            a.write_text(self.GRUEN, encoding="utf-8")
            b = tmp / "test_b_haengt.py"
            b.write_text(self.HAENGT.format(kopf=kopf, sek=self.TIMEOUT * 4),
                         encoding="utf-8")
            env = dict(os.environ)
            for k in ("LIGHTOS_LOCKFILE", "LIGHTOS_VERIFY_DRYRUN",
                      "LIGHTOS_VERIFY_NOLOCK", "LIGHTOS_VERIFY_SINGLE"):
                env.pop(k, None)
            env["LIGHTOS_SEG_OUT"] = str(tmp / "out")
            env["LIGHTOS_SHOW_DB"] = str(tmp / "kind_show.db")
            env["QT_QPA_PLATFORM"] = "offscreen"
            erg = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(RUNNER), "-TimeoutSec", str(self.TIMEOUT), "-j", "1",
                 str(a), str(b)],
                cwd=str(REPO), env=env, capture_output=True, timeout=900)
            return erg.returncode, (erg.stdout + erg.stderr).decode("utf-8", "replace")

    def test_gehobenes_limit_im_zeitlimit_ist_rot(self):
        rc, aus = self._lauf("import pytest\npytestmark = pytest.mark.timeout(600)\n")
        self.assertIn("XPLAT-55", aus, aus[-1200:])
        self.assertNotEqual(0, rc, aus[-1200:])

    def test_ohne_gehobenes_limit_bleibt_die_toleranz(self):
        """Positivkontrolle: die Einzelregel aus XPLAT-28 gilt weiter.

        Der Haenger sitzt hier im Modul-Import (vor jedem Test, von
        ``pytest-timeout`` ungeschuetzt) — sonst beendete die 60-s-Klammer ihn
        rot, bevor das Segmentlimit greift.
        """
        rc, aus = self._lauf(f"import time\ntime.sleep({self.TIMEOUT * 4})\n")
        self.assertRegex(aus, r"ZEIT", aus[-1200:])
        self.assertNotIn("XPLAT-55", aus, aus[-1200:])
        self.assertEqual(0, rc, aus[-1200:])


if __name__ == "__main__":
    unittest.main()
