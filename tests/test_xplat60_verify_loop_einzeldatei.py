"""XPLAT-60: ``tools/verify_loop.ps1`` mit GENAU EINER Testdatei.

**Der Fehler.** Ohne den Lock-Runner ``../run_tests.ps1`` (er liegt ausserhalb
des Repos und fehlt auf jedem frischen Windows-Rechner) faehrt das Skript eine
gezielte Datei direkt mit pytest::

    $target = if ($TestArgs) { $TestArgs } else { @("tests/") }
    & $py -m pytest @target ...

Die Zuweisung eines ``if``-Ausdrucks entrollt in PowerShell ein Array mit nur
einem Element zu seinem Element — ``$target`` ist dann eine Zeichenkette, und
``@target`` reicht davon nur das erste Zeichen weiter. Gemessen am 01.11.2026
unter Windows 11 x64: ``.\\tools\\verify_loop.ps1 tests\\test_x.py`` endete mit
``ERROR: file or directory not found: t`` und Exit 1; mit zwei Dateien lief es.
Genau so stand der Aufruf aber im Auftrag (``verify_loop.ps1 tests\\test_….py``).

**Wie geprueft wird.** Am Verhalten, nicht am Text: der echte Runner bekommt
eine winzige Testdatei in einem eigenen Temp-Ordner (absoluter Pfad, beginnt
also mit dem Laufwerksbuchstaben — ohne Fix kaeme bei pytest nur ``C`` an).
Ist ``../run_tests.ps1`` vorhanden, nimmt das Skript den anderen Zweig; dann
gibt es hier nichts zu pruefen und der Test wird uebersprungen.

**Probe-Ordner begrenzt (CDX-66, Codex-Hinweis zu #1220).** Der Runner startet
pytest im Repo (``Push-Location $repo``) mit dem absoluten Pfad der Probe.
Findet pytest ueber der Probe keine ini-Datei, nimmt es als rootdir den
gemeinsamen Vorfahren von Aufrufordner und Probe — liegt das Repo im
Benutzerprofil, ist das z. B. ``C:/Users/<name>``. Beim Sammeln zaehlt pytest
dann die Ordner auf diesem Weg auf, ``%TEMP%`` eingeschlossen, und vergleicht
unter Windows jeden Eintrag per ``lstat`` (``samefile_nofollow``). Ein
Nachbartest, der dort gerade einen Ordner loescht, beendet die Sammlung mit
``FileNotFoundError`` — derselbe Wettlauf wie in XPLAT-38
(``tools/zeitbomben_gate.py::_wurzel_fuer``) und
``test_harden_exit_keeps_report.py::_run_pytest_in``. Den Aufruf selbst darf
dieser Test nicht aendern (er prueft ja genau EIN Argument); darum bekommt der
Probe-Ordner eine leere ``pytest.ini``: pytest nimmt ihn damit als rootdir,
egal wo Repo und Temp-Ordner liegen. Auf diesem PC (Repo nicht im
Benutzerprofil) war der gemeinsame Vorfahr das Laufwerk — dort griff der
Wettlauf nicht, darum prueft ``ProbeOrdnerBegrenztTest`` die Wurzel in einem
nachgestellten Aufbau, unabhaengig vom Rechner.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "tools" / "verify_loop.ps1"
LOCK_RUNNER = REPO.parent / "run_tests.ps1"

_IST_WINDOWS = sys.platform == "win32"


def _probe_ordner(pfad: Path) -> Path:
    """Ordner fuer Probe-Dateien eines Kind-pytest — die Sammlung bleibt darin.

    Eine leere ``pytest.ini`` genuegt: pytest sucht die ini-Datei zuerst im
    Ordner des Arguments, nimmt diesen Ordner dann als rootdir und zaehlt keine
    Vorfahren mehr auf („pytest.ini files take precedence over other files,
    even when empty“, pytest-Doku)."""
    pfad.mkdir(parents=True, exist_ok=True)
    (pfad / "pytest.ini").write_text("", encoding="utf-8")
    return pfad


def _lauf(*argumente, timeout=300):
    umgebung = dict(os.environ)
    # Schalter des aeusseren Gate-Laufs nicht erben (siehe test_xplat23_windows_sperre).
    for schluessel in ("LIGHTOS_VERIFY_DRYRUN", "LIGHTOS_VERIFY_DRYRUN_HOLD_MS",
                       "LIGHTOS_VERIFY_NOLOCK", "LIGHTOS_LOCKFILE"):
        umgebung.pop(schluessel, None)
    erg = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(RUNNER), *argumente],
        cwd=str(REPO), env=umgebung, capture_output=True, timeout=timeout)
    return erg.returncode, (erg.stdout + erg.stderr).decode("utf-8", "replace")


@unittest.skipUnless(_IST_WINDOWS, "verify_loop.ps1 ist das Windows-Gate")
@unittest.skipIf(LOCK_RUNNER.exists(),
                 "../run_tests.ps1 vorhanden - der Einzeldatei-Weg ohne Lock-Runner "
                 "wird auf diesem Rechner nicht genommen")
class EinzeldateiOhneLockRunnerTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="xplat60_")
        self.ordner = _probe_ordner(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def _datei(self, name, inhalt="def test_ok():\n    assert True\n"):
        p = self.ordner / name
        p.write_text(inhalt, encoding="utf-8")
        return p

    def test_genau_eine_datei_wird_ganz_an_pytest_gereicht(self):
        datei = self._datei("test_xplat60_eine.py")
        rc, aus = _lauf(str(datei))
        self.assertNotIn("file or directory not found", aus, aus[-1500:])
        self.assertIn("1 passed", aus, aus[-1500:])
        self.assertEqual(rc, 0, aus[-1500:])

    def test_eine_rote_datei_bleibt_rot(self):
        """Gegenprobe: der Fix darf aus „nichts gefunden" kein „gruen" machen."""
        datei = self._datei("test_xplat60_rot.py", "def test_rot():\n    assert False\n")
        rc, aus = _lauf(str(datei))
        self.assertIn("1 failed", aus, aus[-1500:])
        self.assertNotEqual(rc, 0, aus[-1500:])

    def test_zwei_dateien_wie_bisher(self):
        a = self._datei("test_xplat60_a.py")
        b = self._datei("test_xplat60_b.py")
        rc, aus = _lauf(str(a), str(b))
        self.assertIn("2 passed", aus, aus[-1500:])
        self.assertEqual(rc, 0, aus[-1500:])


class ProbeOrdnerBegrenztTest(unittest.TestCase):
    """CDX-66: Aufrufordner (steht fuer das Repo) und Probe-Ordner haben einen
    gemeinsamen Vorfahren, der nicht das Laufwerk ist — der Aufbau, in dem der
    Runner auf einem Rechner mit Repo im Benutzerprofil ``%TEMP%`` aufzaehlte.
    Gerechnet wird mit demselben Kind-Befehl wie im Runner; die Probe meldet,
    welches rootdir pytest gewaehlt hat. Laeuft auch unter Linux (die
    rootdir-Regel ist dieselbe, nur der lstat-Wettlauf ist Windows-eigen)."""

    def test_rootdir_ist_der_probe_ordner(self):
        with tempfile.TemporaryDirectory(prefix="xplat60_wurzel_") as d:
            basis = Path(d)
            aufruf = basis / "aufruf"
            aufruf.mkdir()
            ordner = _probe_ordner(basis / "probe")
            datei = ordner / "test_xplat60_wurzel.py"
            datei.write_text(
                "def test_wurzel(request):\n"
                "    print('XPLAT60-WURZEL=' + str(request.config.rootpath))\n",
                encoding="utf-8")
            umgebung = {k: v for k, v in os.environ.items()
                        if k not in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS")}
            r = subprocess.run(
                [sys.executable, "-m", "pytest", str(datei), "-q", "-s",
                 "--tb=short", "-p", "no:cacheprovider", "-o", "addopts="],
                cwd=str(aufruf), env=umgebung, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120)
            aus = r.stdout + r.stderr
            self.assertEqual(r.returncode, 0, aus[-1500:])
            m = re.search(r"XPLAT60-WURZEL=(.+)", aus)
            self.assertIsNotNone(m, aus[-1500:])
            self.assertEqual(
                os.path.normcase(os.path.realpath(m.group(1).strip())),
                os.path.normcase(os.path.realpath(str(ordner))),
                "pytest sammelt ueber den Probe-Ordner hinaus (rootdir = "
                f"{m.group(1).strip()}) — im Repo-Aufruf waere das z. B. der Temp-Ordner")


if __name__ == "__main__":
    unittest.main()
