"""PROC-02 — zwei gleichzeitige VOLLE Suiten muessen sich serialisieren.

★ Gefunden beim Audit des Koordinationsprozesses (2026-08-06), und zwar als
Korrektur einer eigenen Behauptung: `COORDINATION.md` hatte zunaechst notiert,
parallele Testlaeufe seien „durch `.pytest_lock.json` gefangen". Nachgesehen —
und der Kopf von `verify_loop.sh` sagt das Gegenteil ausdruecklich:

    „Der Lock-Runner serialisiert Davids mehrere gleichzeitige Windows-Sessions;
     auf einem gewoehnlichen Linux-Checkout/CI gibt es diese Parallelitaet nicht"

Diese Annahme stimmt seit dem 2026-08-06 nicht mehr: seitdem laufen zwei
Claude-Sitzungen auf demselben Linux-Rechner. Es gab also **gar nichts**, was
zwei volle Laeufe auseinandergehalten haette.

**Warum das nicht bloss langsam, sondern falsch ist:** XPLAT-17 hat gemessen,
dass schon EIN rechenintensives Nachbar-Segment (~1,3 s CPU) die WebEngine-Spur
in 3 von 3 Laeufen reissen liess. Eine komplette zweite Suite ist ein weit
groesserer Nachbar — beide Sitzungen saehen rote Segmente, die nichts mit ihrem
Code zu tun haben, und wuerden sie deuten.

Der Test faehrt den **echten** Runner gegen eine **echt gehaltene** Sperre. Ein
Quelltext-Test („steht `flock` in der Datei?") waere hier wertlos: er bliebe
gruen, wenn die Sperre auf die falsche Datei zeigt, im falschen Zweig steht oder
nie genommen wird — also bei genau den Fehlern, um die es geht (QA-52-Klasse).
"""
import os
import shutil
import subprocess
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUNNER = os.path.join(_REPO, "tools", "verify_loop.sh")


def _hat_flock() -> bool:
    return shutil.which("flock") is not None


@unittest.skipUnless(_hat_flock(), "ohne flock gibt es bewusst keine Sperre")
@unittest.skipUnless(os.access(_RUNNER, os.X_OK), "verify_loop.sh nicht ausfuehrbar")
class VolleSuiteSerialisiertTest(unittest.TestCase):
    """★ Eigene Sperrdatei je Test (LIGHTOS_LOCKFILE).

    Diese Datei laeuft selbst als Segment INNERHALB der vollen Suite — und die
    haelt die echte Sperre bereits. Gegen sie zu pruefen hiesse, den eigenen
    Gate-Lauf zu messen: die Positivkontrolle waere immer rot, und der
    Warte-Test waere gruen aus dem falschen Grund (er saehe das Warten auf den
    Elternprozess, nicht auf die nachgestellte zweite Sitzung).
    """

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix="lightos_lock_")
        self.lockfile = os.path.join(self._dir, ".pytest_lock")
        self.env = {**os.environ, "LIGHTOS_LOCKFILE": self.lockfile}

    def tearDown(self):
        shutil.rmtree(self._dir, ignore_errors=True)

    def _starte_volle_suite(self, timeout: float):
        """Runner ohne Argumente starten und nach `timeout` abwuergen.

        Rueckgabe: die Ausgabe bis dahin. Es geht nur darum, ob er ueberhaupt
        bis zum ersten Schritt kommt — die Suite selbst laeuft Minuten und wird
        hier nie zu Ende gefahren.
        """
        p = subprocess.Popen([_RUNNER], cwd=_REPO, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True,
                             start_new_session=True, env=self.env)
        try:
            ausgabe, _ = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            import signal
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            ausgabe, _ = p.communicate()
        return ausgabe or ""

    def test_wartet_wenn_eine_andere_sitzung_die_sperre_haelt(self):
        # Eine „andere Sitzung" nachstellen: flock haelt die Datei und schlaeft.
        halter = subprocess.Popen(
            ["flock", self.lockfile, "sleep", "30"], start_new_session=True)
        try:
            ausgabe = self._starte_volle_suite(timeout=12)
            self.assertIn("warte", ausgabe.lower(),
                          "Der Runner haette auf die andere Sitzung warten "
                          f"muessen. Ausgabe war:\n{ausgabe}")
            self.assertNotIn("Syntax-Check", ausgabe,
                             "Er ist trotz gehaltener Sperre losgelaufen — "
                             "genau der Fall, den PROC-02 verhindern soll.")
        finally:
            import signal
            os.killpg(os.getpgid(halter.pid), signal.SIGKILL)
            halter.wait()

    def test_ohne_sperre_laeuft_er_sofort_los(self):
        """★ Positivkontrolle — ohne sie waere der Test oben wertlos.

        Ein Runner, der grundsaetzlich nie startet (kaputter Pfad, Tippfehler),
        wuerde „wartet brav" vortaeuschen. Hier muss er den ersten Schritt
        wirklich erreichen.
        """
        ausgabe = self._starte_volle_suite(timeout=25)
        self.assertIn("Syntax-Check", ausgabe,
                      f"Der Runner kam nicht einmal bis zum ersten Schritt:\n{ausgabe}")

    def test_gezielter_lauf_wird_nicht_gesperrt(self):
        """Einzellaeufe sind kurz — sie zu serialisieren bremst nur.

        Auch hier haelt eine „andere Sitzung" die Sperre; ein gezielter Lauf
        muss trotzdem durchgehen.
        """
        halter = subprocess.Popen(
            ["flock", self.lockfile, "sleep", "30"], start_new_session=True)
        try:
            r = subprocess.run(
                [_RUNNER, "tests/test_keine_privaten_dateien.py"],
                cwd=_REPO, capture_output=True, text=True, timeout=180,
                env=self.env)
            self.assertNotIn("warte", r.stdout.lower())
            self.assertEqual(r.returncode, 0, r.stdout[-2000:])
        finally:
            import signal
            os.killpg(os.getpgid(halter.pid), signal.SIGKILL)
            halter.wait()


if __name__ == "__main__":
    unittest.main()
