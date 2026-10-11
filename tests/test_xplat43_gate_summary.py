"""XPLAT-43: beide Segment-Gates schreiben ``summary.json`` mit gleichen Feldern.

Bisher stand die Bilanz eines Gate-Laufs nur als Text im Terminal. Fuer die
spaetere Toleranzliste (welche Datei stuerzt auf welcher Plattform wie oft ab)
braucht es je Lauf einen maschinenlesbaren Datensatz — und zwar auf Linux und
Windows mit DENSELBEN Feldern, sonst laesst sich nichts nebeneinanderlegen.

Drei Zusicherungen:

* **Verhalten (Linux):** ``verify_segmented.sh`` gegen Mini-Testdateien in
  einem Temp-Verzeichnis — die Datei steht da, die Zaehlung stimmt.
* **Exit-Code unveraendert:** die Datei ist reine Beigabe. Ein Lauf, in dem sie
  sich nicht schreiben laesst, endet mit demselben Code wie vorher; und ein
  Crash bleibt auf Linux rot (bewusste Entscheidung XPLAT-27/29).
* **Paritaet (statisch):** die Feldnamen in ``tools/_gate_summary.py`` (Linux)
  und im ``[ordered]@{...}`` von ``tools/verify_segmented.ps1`` sind gleich und
  gleich geordnet. Die .ps1 laesst sich hier nicht ausfuehren.
"""
from __future__ import annotations

import ast
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SH = REPO / "tools" / "verify_segmented.sh"
PS1 = REPO / "tools" / "verify_segmented.ps1"
HELFER = REPO / "tools" / "_gate_summary.py"

ERWARTET = ("commit", "plattform", "python", "arch", "gruen", "rot", "crash",
            "timeout", "toleriert", "gesamt", "dauer_s", "zeitstempel")

_RUNNER_LAEUFT = (SH.exists() and os.name != "nt"
                  and shutil.which("bash") is not None
                  and shutil.which("timeout") is not None)
_RUNNER_GRUND = ("verify_segmented.sh ist das Linux-Gate; auf Windows faehrt "
                 "verify_segmented.ps1 (dort nur statisch geprueft)")

#: Von einem AEUSSEREN Gate-Lauf gesetzt, darf der innere nicht erben
#: (Muster aus test_xplat27_gate_ueberlebt_timeout.py / QA-53).
_NICHT_ERBEN = ("LIGHTOS_LOCKFILE", "LIGHTOS_VERIFY_DRYRUN",
                "LIGHTOS_VERIFY_NOLOCK", "LIGHTOS_VERIFY_SINGLE")

GRUEN = "def test_gruen():\n    assert True\n"
ROT = "def test_rot():\n    assert False, 'absichtlich rot'\n"
# SIGKILL statt SIGSEGV: gleiche Crash-Familie (128+9 = 137), aber kein Coredump.
CRASH = ("import os, signal\n\n\ndef test_crash():\n"
         "    os.kill(os.getpid(), signal.SIGKILL)\n")
# Legt summary.json als VERZEICHNIS an — dann kann der Helfer die Datei nicht
# schreiben, und der Runner muss trotzdem mit demselben Code enden.
BLOCKIERT = ("import os\n\n\ndef test_blockiert():\n"
             "    os.makedirs(os.path.join(os.environ['LIGHTOS_SEG_OUT'],"
             " 'summary.json'), exist_ok=True)\n")


def _umgebung(out: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _NICHT_ERBEN}
    env["LIGHTOS_SEG_OUT"] = str(out)
    return env


def _git_head() -> str | None:
    try:
        erg = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO),
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if erg.returncode != 0:
        return None
    return erg.stdout.strip() or None


@unittest.skipUnless(_RUNNER_LAEUFT, _RUNNER_GRUND)
class LinuxRunnerSchreibtSummaryTest(unittest.TestCase):

    def _lauf(self, tmp: Path, inhalte: dict[str, str]):
        dateien = []
        for name, quelle in inhalte.items():
            p = tmp / f"test_{name}.py"
            p.write_text(quelle, encoding="utf-8")
            dateien.append(str(p))
        out = tmp / "out"
        erg = subprocess.run(["bash", str(SH), "-j", "2", *dateien],
                             cwd=str(REPO), env=_umgebung(out),
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        return erg, out

    def test_felder_und_zaehlung(self):
        with tempfile.TemporaryDirectory() as tmp:
            erg, out = self._lauf(Path(tmp), {"a_gruen": GRUEN, "b_rot": ROT,
                                              "c_crash": CRASH})
            ausgabe = f"{erg.stdout}\n{erg.stderr}"
            # Exit-Vertrag der .sh unveraendert: Anzahl roter Segmente, und
            # der Crash zaehlt mit (Linux toleriert nichts, XPLAT-27/29).
            self.assertEqual(erg.returncode, 2, ausgabe)
            ziel = out / "summary.json"
            self.assertTrue(ziel.is_file(), f"summary.json fehlt:\n{ausgabe}")
            roh = ziel.read_bytes()
            self.assertFalse(roh.startswith(b"\xef\xbb\xbf"), "BOM in summary.json")
            daten = json.loads(roh.decode("utf-8"))

        self.assertEqual(tuple(daten), ERWARTET)
        self.assertEqual(daten["plattform"], "linux")
        self.assertEqual((daten["gruen"], daten["rot"], daten["crash"],
                          daten["timeout"]), (1, 1, 1, 0), daten)
        self.assertEqual(daten["gesamt"], 3)
        self.assertEqual(daten["toleriert"], [])
        self.assertEqual(daten["commit"], _git_head())
        self.assertRegex(daten["python"], r"^\d+\.\d+\.\d+")
        self.assertEqual(daten["arch"], platform.machine())
        self.assertIsInstance(daten["dauer_s"], (int, float))
        self.assertGreaterEqual(daten["dauer_s"], 0)
        self.assertRegex(daten["zeitstempel"],
                         r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        datetime.strptime(daten["zeitstempel"], "%Y-%m-%dT%H:%M:%SZ")

    def test_schreibfehler_aendert_den_exitcode_nicht(self):
        with tempfile.TemporaryDirectory() as tmp:
            erg, out = self._lauf(Path(tmp), {"a_gruen": GRUEN,
                                              "b_blockiert": BLOCKIERT})
            ausgabe = f"{erg.stdout}\n{erg.stderr}"
            self.assertTrue((out / "summary.json").is_dir(), ausgabe)
        self.assertEqual(erg.returncode, 0,
                         f"ein nicht schreibbares summary.json hat den "
                         f"Exit-Code veraendert:\n{ausgabe}")
        self.assertIn("XPLAT-43", erg.stdout)


class HelferTest(unittest.TestCase):

    def _helfer(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("_gate_summary", HELFER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_einstufung(self):
        h = self._helfer()
        self.assertEqual(h.einstufen(0), "gruen")
        self.assertEqual(h.einstufen(1), "rot")
        self.assertEqual(h.einstufen(5), "rot")
        self.assertEqual(h.einstufen(124), "timeout")
        self.assertEqual(h.einstufen(137), "crash")
        self.assertEqual(h.einstufen(139), "crash")

    def test_ohne_results_tsv_alles_null(self):
        h = self._helfer()
        with tempfile.TemporaryDirectory() as tmp:
            daten = h.bilanz(tmp, 0, None, str(REPO))
        self.assertEqual(tuple(daten), ERWARTET)
        self.assertEqual((daten["gruen"], daten["rot"], daten["crash"],
                          daten["timeout"], daten["gesamt"]), (0, 0, 0, 0, 0))
        self.assertIsNone(daten["dauer_s"])


def _felder_helfer() -> tuple[str, ...]:
    baum = ast.parse(HELFER.read_text(encoding="utf-8"))
    for knoten in baum.body:
        if (isinstance(knoten, ast.Assign)
                and any(getattr(z, "id", None) == "FELDER" for z in knoten.targets)):
            return tuple(ast.literal_eval(knoten.value))
    raise AssertionError("FELDER nicht in tools/_gate_summary.py gefunden")


def _ps1_funktion() -> str:
    quelle = PS1.read_text(encoding="utf-8")
    m = re.search(r"function Write-GateSummary \{(.*?)\n\}", quelle, re.S)
    if not m:
        raise AssertionError("Write-GateSummary fehlt in verify_segmented.ps1")
    return m.group(1)


def _felder_ps1() -> tuple[str, ...]:
    m = re.search(r"\[ordered\]@\{(.*?)\n\s*\}", _ps1_funktion(), re.S)
    if not m:
        raise AssertionError("[ordered]@{...} fehlt in Write-GateSummary")
    return tuple(re.findall(r"^\s*([a-z_]+)\s*=", m.group(1), re.M))


class ParitaetTest(unittest.TestCase):
    """Statisch: gleiche Feldnamen, gleiche Reihenfolge, beide Seiten."""

    def test_feldnamen_gleich(self):
        self.assertEqual(_felder_helfer(), ERWARTET)
        self.assertEqual(_felder_ps1(), ERWARTET,
                         "verify_segmented.ps1 und tools/_gate_summary.py "
                         "schreiben unterschiedliche Felder in summary.json")

    def test_ps1_schreibt_utf8_ohne_bom_und_json_depth_3(self):
        f = _ps1_funktion()
        self.assertIn("ConvertTo-Json", f)
        self.assertRegex(f, r"ConvertTo-Json\b[^\n]*-Depth 3")
        self.assertRegex(f, r"UTF8Encoding\(\$false\)")
        self.assertIn('"summary.json"', f)
        self.assertIn('plattform   = "windows"', f)

    def test_ps1_summary_steht_vor_dem_exit_vertrag_und_ist_abgesichert(self):
        quelle = PS1.read_text(encoding="utf-8")
        aufruf = quelle.rfind("\nWrite-GateSummary")
        vertrag = quelle.find("if ($fail.Count) { exit 1 }")
        self.assertGreater(vertrag, 0, "Exit-Vertrag der .ps1 veraendert?")
        self.assertGreater(aufruf, 0, "Write-GateSummary wird nie aufgerufen")
        self.assertLess(aufruf, vertrag,
                        "summary.json muss VOR dem ersten exit geschrieben werden")
        f = _ps1_funktion()
        self.assertRegex(f, r'\$ErrorActionPreference\s*=\s*"Continue"')
        self.assertIn("catch", f)
        self.assertNotRegex(f, r"\bexit\b", "die Bilanz darf nie selbst beenden")

    def test_sh_ruft_helfer_vor_dem_exit_und_ignoriert_seinen_code(self):
        quelle = SH.read_text(encoding="utf-8")
        aufruf = quelle.find("tools/_gate_summary.py")
        self.assertGreater(aufruf, 0)
        self.assertLess(aufruf, quelle.rfind('exit "$BAD"'))
        self.assertLess(aufruf, quelle.rfind("exit 1"))
        self.assertRegex(quelle, r'if ! "\$PY" "\$REPO/tools/_gate_summary\.py"')
        self.assertTrue(quelle.rstrip().endswith('exit "$BAD"'),
                        "Exit-Vertrag der .sh veraendert?")


if __name__ == "__main__":
    unittest.main()
