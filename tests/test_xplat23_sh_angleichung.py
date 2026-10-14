"""XPLAT-23 (i)/(ii) — die zwei Angleichungen auf der ``.sh``-Seite.

Beim Bau der Windows-Sperre (XPLAT-23 Scheibe 1) wurden zwei Stellen gefunden,
an denen ``verify_loop.ps1`` es besser macht als ``verify_loop.sh``:

(i)  Eine nicht oeffenbare Sperrdatei fuehrte auf Linux STILL zu einem
     ungesperrten Volllauf (``exec 9>… 2>/dev/null || return 0``). Eine Sperre,
     die stillschweigend nicht greift, laesst das Ergebnis vertrauenswuerdig
     aussehen — Windows bricht hier laut mit Exit 2 ab.
(ii) ``LIGHTOS_VERIFY_NOLOCK`` und ``LIGHTOS_LOCKFILE`` wirkten wortlos. Ein
     geerbter Schalter machte einen Volllauf ungesperrt, ohne dass es an
     Exit-Code oder Ausgabe zu sehen war. Windows sagt es an.

Dazu ein Nebenbefund: ``exec … 2>/dev/null`` lenkte stderr fuer den GANZEN
restlichen Gate-Lauf ins Leere, weil ``exec`` jede Umlenkung dauerhaft macht.

Alles am echten Runner, mit ``LIGHTOS_VERIFY_DRYRUN`` (Sperre + Syntax-Check
laufen echt, die Suite entfaellt — QA-53) und einer EIGENEN Sperrdatei je Test:
diese Datei laeuft selbst innerhalb der vollen Suite, die die echte Sperre haelt.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUNNER = os.path.join(_REPO, "tools", "verify_loop.sh")

_RUNNER_LAEUFT = (os.path.exists(_RUNNER) and os.name != "nt"
                  and shutil.which("bash") is not None
                  and shutil.which("flock") is not None)
_RUNNER_GRUND = ("verify_loop.sh ist das Linux-Gate und braucht bash und flock. "
                 "Auf Windows prueft tests/test_xplat23_windows_sperre.py "
                 "dieselben zwei Zusicherungen an verify_loop.ps1 (lauter "
                 "Abbruch bei unbrauchbarer Sperrdatei, Hinweis UNGESPERRT).")

# Schalter, die aus einer umgebenden Sitzung oder dem aeusseren Gate geerbt sein
# koennen und das Ergebnis verfaelschen wuerden.
_NICHT_ERBEN = ("LIGHTOS_LOCKFILE", "LIGHTOS_VERIFY_DRYRUN",
                "LIGHTOS_VERIFY_NOLOCK", "LIGHTOS_VERIFY_SINGLE")


@unittest.skipUnless(_RUNNER_LAEUFT, _RUNNER_GRUND)
class ShAngleichungTest(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix="lightos_xplat23sh_")
        self.addCleanup(shutil.rmtree, self._dir, ignore_errors=True)

    def _lauf(self, *args, bash_x=False, **extra):
        env = {k: v for k, v in os.environ.items() if k not in _NICHT_ERBEN}
        env.update({
            "LIGHTOS_VERIFY_DRYRUN": "1",
            "LIGHTOS_SEG_OUT": os.path.join(self._dir, "segments"),
            "LIGHTOS_SHOW_DB": os.path.join(self._dir, "kind.db"),
            "LIGHTOS_LOCKFILE": os.path.join(self._dir, ".pytest_lock"),
        })
        env.update(extra)
        befehl = ["bash"] + (["-x"] if bash_x else []) + [_RUNNER, *args]
        return subprocess.run(befehl, cwd=_REPO, env=env, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=120)

    # ── (i) unbrauchbare Sperrdatei: laut abbrechen, nicht warten ───────────
    def test_fehlender_ordner_bricht_laut_ab(self):
        pfad = os.path.join(self._dir, "gibt_es_nicht", ".pytest_lock")
        r = self._lauf(LIGHTOS_LOCKFILE=pfad)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("Sperrdatei nicht benutzbar", r.stdout)
        self.assertIn(pfad, r.stdout)
        self.assertNotIn("Syntax-Check", r.stdout,
                         "Er ist trotz unbrauchbarer Sperre losgelaufen — "
                         "genau der stille Rueckfall aus XPLAT-23 (i).")
        self.assertNotIn("andere Sitzung", r.stdout,
                         "Falsche Diagnose: es gibt keine andere Sitzung.")

    def test_sperrpfad_ist_ein_ordner_bricht_laut_ab(self):
        r = self._lauf(LIGHTOS_LOCKFILE=self._dir)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("Sperrdatei nicht benutzbar", r.stdout)
        self.assertNotIn("Syntax-Check", r.stdout)

    def test_gezielter_lauf_bleibt_von_der_sperre_unberuehrt(self):
        """Gegenprobe: gezielte Laeufe nehmen keine Sperre — ein kaputter
        Sperrpfad darf sie also auch nicht abbrechen."""
        pfad = os.path.join(self._dir, "gibt_es_nicht", ".pytest_lock")
        r = self._lauf("tests/test_keine_privaten_dateien.py", LIGHTOS_LOCKFILE=pfad)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("nicht benutzbar", r.stdout)
        self.assertIn("Syntax-Check", r.stdout)

    def test_gesunde_sperrdatei_laeuft_durch(self):
        """★ Positivkontrolle — ohne sie waere aus dem Schutz ein Gate
        geworden, das nie mehr startet."""
        r = self._lauf()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Syntax-Check", r.stdout)
        self.assertNotIn("nicht benutzbar", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self._dir, ".pytest_lock")))

    # ── (ii) die Schalter sagen sich an ─────────────────────────────────────
    def test_nolock_sagt_ungesperrt_an(self):
        r = self._lauf(LIGHTOS_VERIFY_NOLOCK="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("UNGESPERRT", r.stdout)

    def test_umgelenkte_sperrdatei_wird_genannt(self):
        r = self._lauf()
        self.assertIn("per LIGHTOS_LOCKFILE umgelenkt", r.stdout)
        self.assertIn(os.path.join(self._dir, ".pytest_lock"), r.stdout)

    # ── Nebenbefund: stderr bleibt nach der Sperrnahme sichtbar ─────────────
    def test_stderr_bleibt_nach_der_sperrnahme_offen(self):
        """``bash -x`` schreibt seine Spur nach stderr. Steht nach der
        Sperrnahme noch eine Spurzeile des Syntax-Checks dort, ist stderr
        nicht umgelenkt worden. Mit dem alten ``exec 9>… 2>/dev/null`` endete
        die Spur an genau dieser Zeile."""
        r = self._lauf(bash_x=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("flock -n 9", r.stderr)
        self.assertIn("1/2 Syntax-Check", r.stderr,
                      "Nach der Sperrnahme kam nichts mehr auf stderr an — "
                      "die Sperre hat stderr fuer den ganzen Lauf verschluckt.")


if __name__ == "__main__":
    unittest.main()
