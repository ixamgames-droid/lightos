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
import sys
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUNNER = os.path.join(_REPO, "tools", "verify_loop.sh")


def _hat_flock() -> bool:
    return shutil.which("flock") is not None


# ⚠️ QA-69: hier stand ``os.access(_RUNNER, os.X_OK)`` als einziger Guard. Auf
# Windows liefert das fuer jede vorhandene Datei ``True`` — ein Ausfuehrbar-Bit
# gibt es dort nicht, und die ``.sh`` ist mit eingecheckt. Der Guard hat also
# genau das NICHT getan, wonach er aussieht.
#
# Die Folgen waren je Klasse verschieden und beide irrefuehrend:
#   * ``KeineZweiteSuiteAusEinemTestTest`` startete die ``.sh`` als Prozess und
#     starb mit ``OSError [WinError 193] %1 ist keine zulaessige
#     Win32-Anwendung``;
#   * ``SperreGiltUeberWorktreeGrenzenTest`` hatte gar keinen Guard und starb
#     an ``os.symlink`` mit ``WinError 1314`` (Symlinks brauchen dort Adminrechte
#     oder den Entwicklermodus).
# Beides las sich wie ein kaputtes Gate, war aber nur eine Linux-Annahme.
#
# ``verify_loop.sh`` IST das Linux-Gate — es startet ``venv/bin/python``, das
# auf einem Windows-Checkout nicht existiert, und nimmt eine ``flock``-Sperre,
# die es dort auch nicht gibt. Windows faehrt stattdessen ``verify_loop.ps1``
# bzw. ``run_tests.ps1``. **Dass es fuer die Zusicherungen dieser Datei auf der
# Windows-Seite kein Gegenstueck gibt, ist als XPLAT-23 erfasst** — hier wird
# die Luecke benannt statt stillschweigend uebersprungen.
_RUNNER_LAEUFT = (os.path.exists(_RUNNER) and os.name != "nt"
                  and shutil.which("bash") is not None)
_RUNNER_GRUND = ("verify_loop.sh ist das Linux-Gate — auf Windows faehrt "
                 "verify_loop.ps1 / run_tests.ps1 (XPLAT-23), und bash fehlt "
                 "im PATH")


@unittest.skipUnless(_hat_flock(), "ohne flock gibt es bewusst keine Sperre")
@unittest.skipUnless(_RUNNER_LAEUFT, _RUNNER_GRUND)
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
        # ★★ QA-53 — die drei Zusaetze sind der eigentliche Fix an dieser Datei.
        #
        # Bis zum 2026-08-11 startete `_starte_volle_suite` den Runner ohne
        # Argumente und liess ihn 25 s laufen. Ohne Argumente ist das die VOLLE
        # SUITE: mitten im Gate lief damit ein ZWEITES vollstaendiges Gate mit
        # -j 3. Gemessen wurden 95 gleichzeitig lebende pytest-Prozesse auf
        # EINEM geerbten LIGHTOS_SHOW_DB, die sich die Datenbank beim
        # conftest-Import gegenseitig wegloeschten — plus ein `rm -rf` auf das
        # .pytest_segments des aeusseren Laufs.
        #
        # ★ Bitter daran: dieser Test wurde geschrieben, um zwei gleichzeitige
        # Suiten zu VERHINDERN, und startete dabei selbst eine zweite. Der
        # Kommentar in verify_loop.sh benannte die Verschachtelung sogar — nur
        # die Folge daraus war nicht zu Ende gedacht.
        self.segout = os.path.join(self._dir, "segments")
        self.env = {
            **os.environ,
            "LIGHTOS_LOCKFILE": self.lockfile,
            # (1) Kein Testlauf — nur Sperre + Syntax-Check. Der Mechanismus,
            #     um den es hier geht, laeuft damit vollstaendig echt.
            "LIGHTOS_VERIFY_DRYRUN": "1",
            # (2) Eigenes Ausgabeverzeichnis, falls doch je ein Segmentlauf
            #     entsteht: dann raeumt er nicht dem echten Gate die Ergebnisse ab.
            "LIGHTOS_SEG_OUT": self.segout,
            # (3) Eigene Show-DB. Der Kindprozess erbt sie sonst und faellt
            #     seinem Elternprozess in die Datenbank (conftest schuetzt das
            #     seit QA-53 zusaetzlich — hier steht der Guertel zum Hosentraeger).
            "LIGHTOS_SHOW_DB": os.path.join(self._dir, "kind_show.db"),
        }

    def tearDown(self):
        shutil.rmtree(self._dir, ignore_errors=True)

    def _starte_volle_suite(self, timeout: float):
        """Den Runner auf dem Weg der vollen Suite starten (ohne Argumente).

        Er nimmt dabei wirklich die Sperre und macht wirklich den Syntax-Check;
        nur die Suite selbst entfaellt (``LIGHTOS_VERIFY_DRYRUN``, s. setUp).
        Der `timeout` faengt weiterhin den Fall ab, dass er an der Sperre
        haengenbleibt — das ist im Warte-Test der erwuenschte Ausgang.
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
            # ★ Hier bewusst OHNE DRYRUN: dieser Test lebt davon, dass der
            # gezielte Lauf wirklich bis zum Ende durchgeht (returncode 0).
            # Mit Abkuerzung waere er gruen, ohne noch etwas zu belegen — genau
            # die Attrappen-Falle aus QA-52. Eine Datei ist billig.
            env = {k: v for k, v in self.env.items()
                   if k != "LIGHTOS_VERIFY_DRYRUN"}
            r = subprocess.run(
                [_RUNNER, "tests/test_keine_privaten_dateien.py"],
                cwd=_REPO, capture_output=True, text=True, timeout=180,
                env=env)
            self.assertNotIn("warte", r.stdout.lower())
            self.assertEqual(r.returncode, 0, r.stdout[-2000:])
        finally:
            import signal
            os.killpg(os.getpgid(halter.pid), signal.SIGKILL)
            halter.wait()


@unittest.skipUnless(_RUNNER_LAEUFT, _RUNNER_GRUND)
class KeineZweiteSuiteAusEinemTestTest(unittest.TestCase):
    """★★ QA-53 — die Regression, die diese Datei selbst verursacht hat.

    Ein Test, der den Gate-Runner startet, darf keine zweite volle Suite
    ausloesen. Gemessen am 2026-08-11 (vorher): 95 gleichzeitig lebende
    pytest-Prozesse auf einer geerbten Show-DB, ein ``rm -rf`` auf das
    Ausgabeverzeichnis des laufenden Gates, und in der Folge rote Segmente an
    wechselnden Dateien, die alle isoliert gruen liefen.
    """

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix="lightos_nozweite_")
        self.addCleanup(shutil.rmtree, self._dir, ignore_errors=True)

    def test_der_runner_raeumt_das_ausgabeverzeichnis_des_gates_nicht_ab(self):
        """Das Verzeichnis wird beim Segmentlauf per ``rm -rf`` neu angelegt —
        seine Inode-Nummer ist damit der direkte Beleg. Kein Eingriff in einen
        laufenden Gate-Lauf: der Test schreibt nichts hinein, er sieht nur hin.
        """
        segdir = os.path.join(_REPO, ".pytest_segments")
        vorher = os.stat(segdir).st_ino if os.path.isdir(segdir) else None

        env = {**os.environ,
               "LIGHTOS_LOCKFILE": os.path.join(self._dir, ".lock"),
               "LIGHTOS_VERIFY_DRYRUN": "1",
               "LIGHTOS_SHOW_DB": os.path.join(self._dir, "kind.db")}
        r = subprocess.run([_RUNNER], cwd=_REPO, capture_output=True,
                           text=True, timeout=180, env=env)

        self.assertEqual(0, r.returncode, r.stdout[-2000:])
        self.assertNotIn("segmentiert", r.stdout,
                         "Der Runner hat die volle Suite gestartet:\n" + r.stdout)
        nachher = os.stat(segdir).st_ino if os.path.isdir(segdir) else None
        self.assertEqual(vorher, nachher,
                         "Das Ausgabeverzeichnis wurde neu angelegt — ein "
                         "zweiter Segmentlauf hat dem echten Gate die "
                         "results.tsv abgeraeumt (QA-53).")

    def test_ein_kindprozess_loescht_die_show_db_des_elternprozesses_nicht(self):
        """★ Der conftest-Guard, direkt gemessen.

        Ohne ihn ruft JEDER als Kind gestartete pytest beim blossen Import
        ``_purge_test_dbs()`` — und das ``os.remove`` traf den GEERBTEN Pfad,
        also die Datenbank, an der der Elternprozess gerade arbeitet.
        """
        db = os.path.join(self._dir, "eltern_show.db")
        with open(db, "w", encoding="utf-8") as f:
            f.write("nicht leer")

        env = {**os.environ, "LIGHTOS_SHOW_DB": db}
        # ★ Die Datei MUSS unter tests/ liegen, sonst laedt pytest das
        # tests/conftest.py gar nicht — und genau dessen Import loest den
        # Aufraeumschritt aus (conftest.py:255). Ein erster Versuch legte eine
        # Wegwerfdatei in einen Temp-Ordner: das Kind lief, loeschte nichts,
        # und der Test war gruen, ohne je den Fall gefahren zu haben.
        # `-k` waehlt bewusst keinen einzigen Test aus: gebraucht wird nur der
        # Import, nicht die Laufzeit fremder Tests.
        subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_app_data_dir.py",
             "-k", "diesen_namen_gibt_es_nicht", "-q", "-p", "no:cacheprovider"],
            cwd=_REPO, capture_output=True, text=True, timeout=180, env=env)

        self.assertTrue(os.path.exists(db),
                        "Der Kindprozess hat die Show-DB des Elternprozesses "
                        "geloescht — genau der Isolationsbruch aus QA-53.")


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(_RUNNER_LAEUFT, _RUNNER_GRUND)
class SperreGiltUeberWorktreeGrenzenTest(unittest.TestCase):
    """★★ PROC-02b: Ein VERSCHACHTELTER Worktree bekam eine eigene Sperrdatei.

    Der Sperrpfad wurde als „Elternverzeichnis des Worktrees" bestimmt. Das
    stimmt fuer die dokumentierte Konvention (`~/projects/lightos/wt-<kurz>`,
    alles Geschwister von `repo/`) — aber nicht fuer Agenten-Worktrees, die
    unter `repo/.claude/worktrees/` liegen. Die bekamen ihre eigene Datei, und
    damit lief die volle Suite doppelt.

    **Gemessen am 12.08.2026**, waehrend genau das passierte: 11
    WebEngine-Segmente starteten mit noch laufenden Chromium-Kindprozessen,
    zwei Segmente wurden rot. Der Fehler sah aus wie ein Produktfehler.

    Geprueft wird ueber den DRY-RUN des echten Skripts, nicht durch Nachbau
    seiner Pfadlogik — eine nachgebaute Formel wuerde nur sich selbst pruefen
    (QA-55-Falle).
    """

    def _sperrpfad(self, wurzel: str) -> str:
        """Sperrpfad, den DIESER Worktree meldet.

        ★ Aufgerufen wird das Skript AUS dem jeweiligen Worktree — nicht das
        des Hauptrepos mit fremdem Arbeitsverzeichnis. `verify_loop.sh` macht
        als erstes `cd "$(dirname "$0")/.."`; ein Aufruf der Hauptkopie haette
        also immer denselben Pfad gemeldet, egal von wo. Genau daran ist die
        erste Fassung dieses Tests gescheitert: die Mutation „alte Logik
        zurueck" blieb gruen, weil der Test das Skript des Hauptrepos fuhr.
        """
        umgebung = {k: v for k, v in os.environ.items()
                    if k not in ("LIGHTOS_LOCKFILE",)}
        umgebung["LIGHTOS_VERIFY_DRYRUN"] = "1"
        # ★ NOLOCK ist hier Pflicht, nicht Bequemlichkeit: dieser Test laeuft
        # INNERHALB der vollen Suite, die die echte Sperre haelt. Ohne ihn wartet
        # der Unterprozess auf den eigenen Gate-Lauf, bis das Segment-Timeout
        # zuschlaegt — gemessen am 12.08.2026, genau so. Der Pfad wird trotzdem
        # gemeldet, weil Bestimmung und Belegung getrennt sind.
        umgebung["LIGHTOS_VERIFY_NOLOCK"] = "1"
        r = subprocess.run(["bash", os.path.join(wurzel, "tools", "verify_loop.sh")],
                           cwd=wurzel, env=umgebung, capture_output=True, text=True,
                           timeout=180)
        for zeile in r.stdout.splitlines():
            if zeile.startswith("[verify] Sperrdatei:"):
                return zeile.split(":", 1)[1].strip()
        self.fail(f"keine Sperrdatei-Zeile in der Ausgabe:\n{r.stdout}\n{r.stderr}")

    def test_geschwister_und_verschachtelter_worktree_teilen_die_sperre(self):
        if not shutil.which("git"):
            self.skipTest("kein git")
        with tempfile.TemporaryDirectory() as tmp:
            geschwister = os.path.join(tmp, "wt-geschwister")
            tief = os.path.join(tmp, "a", "b", "c", "wt-tief")
            os.makedirs(os.path.dirname(tief), exist_ok=True)
            angelegt = []
            try:
                for ziel in (geschwister, tief):
                    zweig = "proc02b-probe-" + os.path.basename(ziel)
                    r = subprocess.run(
                        ["git", "worktree", "add", "--detach", ziel, "HEAD"],
                        cwd=_REPO, capture_output=True, text=True, timeout=120)
                    if r.returncode != 0:
                        self.skipTest(f"worktree add ging nicht: {r.stderr[:200]}")
                    angelegt.append(ziel)
                    # Ein frischer Worktree hat kein venv — dann steigt
                    # verify_loop.sh mit exit 2 aus, BEVOR es die Sperrdatei
                    # meldet. Genau so ist es am 12.08. auch von Hand passiert:
                    # das Gate meldete "fertig", ohne einen Test gefahren zu
                    # haben. Hier wird die reale Einrichtung nachgebildet.
                    os.symlink(os.path.join(_REPO, "venv"),
                               os.path.join(ziel, "venv"))
                    # `git worktree add` liefert den COMMITTETEN Stand. Geprueft
                    # werden soll aber die Arbeitsfassung — dieselbe, die jeder
                    # andere Test sieht. Sonst misst dieser Test einen aelteren
                    # Runner als den, der gerade laeuft.
                    # ★ PROC-02c: `_gate_webengine.sh` muss mitkommen.
                    # `verify_loop.sh` sourcet es und steigt sonst mit exit 2
                    # aus — und dann meldet es die Sperrdatei nie. Wer hier nur
                    # den Runner kopiert, testet eine Arbeitsfassung gegen einen
                    # committeten Helfer: genau die Paarung, die es nirgends gibt.
                    for datei in ("verify_loop.sh", "_gate_webengine.sh"):
                        shutil.copy2(os.path.join(_REPO, "tools", datei),
                                     os.path.join(ziel, "tools", datei))
                a = self._sperrpfad(geschwister)
                b = self._sperrpfad(tief)
                self.assertEqual(
                    a, b,
                    "Zwei Worktrees desselben Repos muessen DIESELBE Sperrdatei "
                    "benutzen — sonst faehrt die volle Suite doppelt, und das "
                    "Ergebnis sieht trotzdem vertrauenswuerdig aus.")
            finally:
                for ziel in angelegt:
                    subprocess.run(["git", "worktree", "remove", "--force", ziel],
                                   cwd=_REPO, capture_output=True, timeout=120)

    def test_die_messung_wuerde_einen_unterschied_auch_sehen(self):
        """POSITIVKONTROLLE: mit gesetztem ``LIGHTOS_LOCKFILE`` melden zwei
        Laeufe verschiedene Pfade — die Methode kann also unterscheiden und
        bestaetigt nicht blind Gleichheit."""
        with tempfile.TemporaryDirectory() as tmp:
            pfade = []
            for name in ("eins", "zwei"):
                umgebung = dict(os.environ)
                umgebung["LIGHTOS_VERIFY_DRYRUN"] = "1"
                umgebung["LIGHTOS_LOCKFILE"] = os.path.join(tmp, name + ".lock")
                r = subprocess.run(
                    ["bash", os.path.join(_REPO, "tools", "verify_loop.sh")],
                    cwd=_REPO, env=umgebung, capture_output=True, text=True,
                    timeout=120)
                pfade.append(next(z.split(":", 1)[1].strip()
                                  for z in r.stdout.splitlines()
                                  if z.startswith("[verify] Sperrdatei:")))
            self.assertNotEqual(pfade[0], pfade[1])
