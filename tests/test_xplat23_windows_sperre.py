"""XPLAT-23: das Windows-Gate serialisiert die volle Suite — am Verhalten geprueft.

**Der Zustand vorher.** Die Serialisierung des Windows-Gates lag ausschliesslich
in ``../run_tests.ps1`` — einer Datei **ausserhalb** des Repos. Fehlte sie, fuhr
``tools/verify_loop.ps1`` die volle Suite mit einer Warnung, aber **ohne jede
Sperre**. Auf Linux steht dieselbe Sperre seit PROC-02 im Repo (``flock`` am
``--git-common-dir``). Ein frischer Windows-Checkout hatte sie also nicht — und
seit dem 2026-08-06 arbeiten hier zwei Sitzungen gleichzeitig.

★ **Warum das nicht bloss langsam ist:** XPLAT-17 hat gemessen, dass schon ein
einziges rechenintensives Nachbar-Segment die WebEngine-Spur in 3 von 3 Laeufen
reissen liess. Beide Sitzungen haetten rote Segmente gesehen, die nichts mit
ihrem Code zu tun haben — und sie gedeutet.

**Was dieser Test anders macht als die vorhandenen.** ``test_gate_runner_parity``
vergleicht die Runner *textlich*: kommen dieselben zwei Umgebungsvariablen darin
vor? Das ist die Messblindheit, die XPLAT-23 benennt — kein Test prueft das
Windows-Gate am **Verhalten**. Hier laufen deshalb zwei echte
``verify_loop.ps1``-Prozesse gegeneinander, und gemessen wird, ob der zweite
wartet.

**Warum dafuer kein voller Testlauf noetig ist.** ``LIGHTOS_VERIFY_DRYRUN``
steigt NACH dem Syntax-Check und NACH der Sperrnahme aus. Der zu pruefende
Mechanismus laeuft damit vollstaendig echt; es entfaellt nur die Nutzlast. Ohne
diesen Ausstieg muesste der Test die volle Suite starten — mitten im laufenden
Gate, und genau das war QA-53 (95 pytest-Prozesse auf einer geteilten
Show-Datenbank).
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "tools" / "verify_loop.ps1"

_IST_WINDOWS = sys.platform == "win32"
_GRUND = ("verify_loop.ps1 ist das Windows-Gate; auf Linux serialisiert "
          "verify_loop.sh per flock, geprueft von test_verify_loop_sperre.py")


def _lauf(argumente=(), umgebung_extra=None, timeout=180):
    """``verify_loop.ps1`` starten und ``(rc, Ausgabe, Dauer)`` liefern."""
    umgebung = dict(os.environ)
    # Nie die Schalter des AEUSSEREN Gate-Laufs erben: sonst misst der Test die
    # Umgebung des Laufs, in dem er selbst steckt.
    for schluessel in ("LIGHTOS_VERIFY_DRYRUN", "LIGHTOS_VERIFY_DRYRUN_HOLD_MS",
                       "LIGHTOS_VERIFY_NOLOCK", "LIGHTOS_LOCKFILE"):
        umgebung.pop(schluessel, None)
    umgebung.update(umgebung_extra or {})
    beginn = time.monotonic()
    erg = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(RUNNER), *argumente],
        cwd=str(REPO), env=umgebung, capture_output=True, timeout=timeout)
    dauer = time.monotonic() - beginn
    return erg.returncode, (erg.stdout + erg.stderr).decode("utf-8", "replace"), dauer


@unittest.skipUnless(_IST_WINDOWS, _GRUND)
class SperrPfadTest(unittest.TestCase):
    """Wo die Sperrdatei liegt — die Angabe, die von aussen nicht nachpruefbar waere.

    ⚠️ Hier wird ``LIGHTOS_VERIFY_NOLOCK`` gesetzt, und das ist kein Detail:
    ohne den Schalter naehme dieser Test die ECHTE Gate-Sperre — und laeuft er
    innerhalb der vollen Suite, wartet er auf den Lauf, in dem er selbst steckt.
    Genau das ist auf Linux am 12.08.2026 passiert. Pfadbestimmung und
    Sperrnahme sind im Skript deshalb getrennt.
    """

    def test_die_sperre_haengt_am_gemeinsamen_git_verzeichnis(self):
        """PROC-02b: ein verschachtelter Worktree muss DIESELBE Datei sehen.

        Gemessen am Skript, nicht an einer nachgebauten Formel: der Runner meldet
        den Pfad selbst, verglichen wird gegen ``git rev-parse --git-common-dir``.
        Haengte die Sperre am Elternordner, bekaeme jeder Worktree eine eigene
        Datei — und die Serialisierung griffe ausgerechnet dort nicht, wo
        parallel gearbeitet wird.
        """
        rc, ausgabe, _ = _lauf(umgebung_extra={"LIGHTOS_VERIFY_DRYRUN": "1",
                                               "LIGHTOS_VERIFY_NOLOCK": "1"})
        self.assertEqual(0, rc, ausgabe[-800:])
        zeilen = [z for z in ausgabe.splitlines() if "Sperrdatei:" in z]
        self.assertTrue(zeilen,
                        f"der Runner meldet den Sperrpfad nicht:\n{ausgabe[-800:]}")
        gemeldet = Path(zeilen[0].split("Sperrdatei:", 1)[1].strip())

        common = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, timeout=30)
        if common.returncode != 0 or not common.stdout.strip():
            self.skipTest("kein Git-Checkout — der gemeinsame Git-Ordner ist "
                          "nicht bestimmbar")
        roh = Path(common.stdout.strip())
        if not roh.is_absolute():
            roh = REPO / roh
        self.assertEqual(
            roh.resolve() / ".pytest_lock", gemeldet.resolve(),
            "die Sperrdatei haengt nicht am gemeinsamen Git-Verzeichnis — ein "
            "verschachtelter Worktree bekaeme damit eine eigene Sperre (PROC-02b)")

    def test_der_dryrun_meldet_ausdruecklich_dass_er_nichts_geprueft_hat(self):
        """★ Ein Schalter, der das Gate zum No-Op macht, muss das SAGEN.

        Sonst liest jemand Exit 0 und haelt einen Lauf ohne einen einzigen
        gefahrenen Test fuer eine bestandene Pruefung.
        """
        rc, ausgabe, _ = _lauf(umgebung_extra={"LIGHTOS_VERIFY_DRYRUN": "1",
                                               "LIGHTOS_VERIFY_NOLOCK": "1"})
        self.assertEqual(0, rc, ausgabe[-400:])
        self.assertIn("KEINE bestandene Pruefung", ausgabe)
        self.assertNotIn("GRUEN - alles bestanden", ausgabe)


@unittest.skipUnless(_IST_WINDOWS, _GRUND)
class SerialisierungTest(unittest.TestCase):
    """Zwei echte Runner gegeneinander — das Verhalten, nicht der Text.

    Alle Laeufe hier setzen ``LIGHTOS_LOCKFILE`` auf eine eigene Datei im
    Temp-Ordner. Die echte Gate-Sperre wird also nie angefasst, auch dann nicht,
    wenn dieser Test innerhalb der vollen Suite laeuft.
    """

    HALT_MS = 5000

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="lightos_xplat23_")
        self.sperre = str(Path(self._tmp.name) / "probe.lock")

    def tearDown(self):
        self._tmp.cleanup()

    def _halter_starten(self):
        """Einen ECHTEN ``verify_loop.ps1`` starten, der die Sperre eine Weile haelt."""
        umgebung = dict(os.environ)
        umgebung.update({"LIGHTOS_VERIFY_DRYRUN": "1",
                         "LIGHTOS_VERIFY_DRYRUN_HOLD_MS": str(self.HALT_MS),
                         "LIGHTOS_LOCKFILE": self.sperre})
        umgebung.pop("LIGHTOS_VERIFY_NOLOCK", None)
        return subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(RUNNER)],
            cwd=str(REPO), env=umgebung,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _warten_bis_sperre_haelt(self, halter, grenze=120.0):
        """Warten, bis der Halter die Sperre wirklich hat.

        Nicht ueber eine feste Schlafzeit: der Halter faehrt vorher einen echten
        Syntax-Check, und dessen Dauer haengt am Rechner. Die Sperrdatei
        existiert erst, wenn ``Enter-Sperre`` sie geoeffnet hat.
        """
        ende = time.monotonic() + grenze
        while time.monotonic() < ende:
            if os.path.exists(self.sperre):
                return True
            if halter.poll() is not None:
                return False
            time.sleep(0.05)
        return False

    def test_der_zweite_lauf_wartet_auf_den_ersten(self):
        """★★ Der eigentliche Nachweis — zwei Gate-Prozesse, echt gemessen."""
        halter = self._halter_starten()
        try:
            self.assertTrue(
                self._warten_bis_sperre_haelt(halter),
                "der Halter hat die Sperre nie genommen — dann prueft dieser "
                "Test nichts")
            rc, ausgabe, dauer = _lauf(
                umgebung_extra={"LIGHTOS_VERIFY_DRYRUN": "1",
                                "LIGHTOS_LOCKFILE": self.sperre})
        finally:
            halter.wait(timeout=120)
        self.assertEqual(0, rc, ausgabe[-800:])
        self.assertIn("warte", ausgabe,
                      "der zweite Lauf hat die belegte Sperre nicht bemerkt:\n"
                      + ausgabe[-800:])
        self.assertIn("Sperre frei, starte.", ausgabe,
                      "der zweite Lauf meldet nicht, dass er die Sperre bekommen "
                      "hat — dann bleibt offen, ob er sie je hatte:\n"
                      + ausgabe[-800:])
        self.assertGreater(
            dauer, 1.0,
            f"der zweite Lauf war nach {dauer:.1f}s durch, obwohl die Sperre "
            "belegt war — er hat sie offenbar nicht genommen")

    def test_ein_gezielter_lauf_wartet_NICHT(self):
        """★ Gegenprobe zur Absicht (gleiche Regel wie auf Linux).

        Ohne sie koennte die Sperre pauschal JEDEN Lauf serialisieren und alle
        Tests oben blieben gruen — aus dem Schutz waere dann eine Bremse fuer die
        gezielten Einzellaeufe geworden, von denen Agenten fast nur leben.
        """
        halter = self._halter_starten()
        try:
            self.assertTrue(self._warten_bis_sperre_haelt(halter))
            # Mit DRYRUN steigt der Runner vor dem Testlauf aus; das Argument
            # entscheidet hier nur, ob ``Enter-Sperre`` es als gezielten Lauf
            # ansieht — gefahren wird die Datei nicht.
            ausgabe = _lauf(
                ["tests/test_xplat23_windows_sperre.py"],
                umgebung_extra={"LIGHTOS_VERIFY_DRYRUN": "1",
                                "LIGHTOS_LOCKFILE": self.sperre},
                timeout=120)[1]
        finally:
            halter.wait(timeout=120)
        self.assertNotIn("warte", ausgabe,
                         "ein gezielter Lauf hat auf die Sperre gewartet — "
                         "gesperrt wird nur die VOLLE Suite:\n" + ausgabe[-800:])

    def test_NOLOCK_hebt_die_sperre_auf(self):
        """Der dokumentierte Notausgang muss wirken — sonst steht er umsonst da."""
        halter = self._halter_starten()
        try:
            self.assertTrue(self._warten_bis_sperre_haelt(halter))
            rc, ausgabe, _ = _lauf(
                umgebung_extra={"LIGHTOS_VERIFY_DRYRUN": "1",
                                "LIGHTOS_VERIFY_NOLOCK": "1",
                                "LIGHTOS_LOCKFILE": self.sperre})
        finally:
            halter.wait(timeout=120)
        self.assertEqual(0, rc, ausgabe[-800:])
        self.assertNotIn("warte", ausgabe,
                         "LIGHTOS_VERIFY_NOLOCK hat die Sperre nicht aufgehoben:\n"
                         + ausgabe[-800:])


if __name__ == "__main__":
    unittest.main()
