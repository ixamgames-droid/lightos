"""PROC-02d — ein ueberlebendes Kind darf die VOLL-SUITEN-Sperre nicht halten.

``tools/verify_loop.sh`` nimmt die Sperre gegen zwei gleichzeitige volle Suiten
mit ``exec 9>"$LOCKFILE"`` und ``flock -n 9``. Ein so geoeffneter Deskriptor ist
**vererbbar** — genau deshalb funktioniert das flock-Idiom ueberhaupt. Er wandert
damit in jeden Nachkommen: Segment-Runner, ``timeout``, Segment-pytest und die
Chromium-Kinder darunter. Und ``flock`` loest erst, wenn die **letzte** Kopie zu
ist.

**Warum das teuer ist:** die Sperrdatei haengt am gemeinsamen Git-Verzeichnis,
gilt also rechnerweit ueber alle Worktrees und Sitzungen (PROC-02b). Ein
einziges ueberlebendes Kind haelt sie damit ueber das Gate-Ende hinaus fest —
und ``_verify_lock`` wartet auf sie **ohne Deckel** (``flock 9``, keine
Wartezeit). Der naechste volle Lauf auf diesem Rechner steht dann einfach, ohne
Meldung und ohne Ende. Waisen dieser Art sind dokumentiert: PROC-02c fand einen
``sleep 600`` mit PPID 1 auf der echten WebEngine-Sperrdatei.

Die WebEngine-Sperre aus PROC-02c hat gegen genau das ``8>&-``. Fuer fd 9 fehlte
das Gegenstueck.

★ **Gemessen wird am ECHTEN Runner in einem WEGWERF-REPO**, nicht mit
``LIGHTOS_LOCKFILE`` an einer untergeschobenen Datei. Beides ist Absicht:

* Ein eigenes Repo ist Pflicht, nicht Bequemlichkeit. Diese Datei laeuft selbst
  als Segment INNERHALB der vollen Suite — die echte Sperre ist dann gehalten.
  Ein Test, der den vollen Lauf auf dem echten Repo nachstellte, wartete auf
  seinen eigenen Gate-Lauf, und die volle Suite im Wegwerf-Repo ist EINE
  Mini-Testdatei statt 500 (QA-53: ein Test, der aus Versehen ein zweites Gate
  startet, ist teurer als der Fehler, den er sucht).
* Ohne ``LIGHTOS_LOCKFILE`` faehrt der Runner seine ECHTE Pfadbestimmung ueber
  ``git rev-parse --git-common-dir``. Bei PROC-02c hatte jeder Test die
  Sperrdatei per Umgebungsvariable gesetzt — der Zweig, der sie wirklich
  bestimmt, wurde von keiner Messung beruehrt. Deshalb ist hier auch die blosse
  EXISTENZ von ``<wegwerf>/.git/.pytest_lock`` nach dem Lauf eine Zusicherung:
  ohne sie waere „Sperre frei" gruen, weil gar nichts gesperrt wurde.

★★ **Warum ein `sleep` als Nachstellung genuegt und kein Chromium noetig ist:**
gemessen wird die Vererbung eines Dateideskriptors ueber ``fork``/``exec``. Die
haengt am Startmodus, nicht am Programm — ``close_fds=False`` plus eigene
Sitzung ist exakt der Modus, in dem Chromium seine Hilfsprozesse startet, und
die Assertion sieht den Deskriptor in ``/proc/<pid>/fd`` direkt.
"""
import os
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"
RUNNER = TOOLS / "verify_loop.sh"

_LAEUFT = (os.name != "nt"
           and RUNNER.exists()
           and shutil.which("bash") is not None
           and shutil.which("flock") is not None
           and shutil.which("git") is not None
           and os.path.isdir("/proc"))
_GRUND = ("Die Sperre ist der Linux-Weg (auf Windows serialisiert "
          "run_tests.ps1). Ohne flock gibt es bewusst keine Sperre; die "
          "Deskriptor-Pruefung liest /proc.")

# Die volle Suite des Wegwerf-Repos: EINE Datei, die ein Kind hinterlaesst,
# das den Lauf ueberlebt. `start_new_session=True` koppelt es ab (es haengt
# danach an init), `close_fds=False` laesst es die Deskriptoren des
# pytest-Prozesses erben — beides zusammen ist der Startmodus von Chromiums
# Hilfsprozessen.
ENKEL_TEST = '''"""Hinterlaesst absichtlich ein Kind, das den Lauf ueberlebt."""
import subprocess


def test_enkel():
    kind = subprocess.Popen(["sleep", "300"],
                            start_new_session=True, close_fds=False)
    with open({pidfile!r}, "w", encoding="utf-8") as fh:
        fh.write(str(kind.pid))
'''

HARMLOS = '''"""Gewoehnliches Segment ohne Nachlass."""


def test_harmlos():
    assert True
'''


def _lebt(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:      # existiert, gehoert nur jemand anderem
        return True
    return True


def _fds(pid: int):
    """Wohin zeigen die offenen Deskriptoren eines Prozesses? {nr: ziel}"""
    ziele = {}
    try:
        namen = os.listdir(f"/proc/{pid}/fd")
    except OSError:
        return ziele
    for name in namen:
        try:
            ziele[int(name)] = os.readlink(f"/proc/{pid}/fd/{name}")
        except (OSError, ValueError):
            pass
    return ziele


class _WegwerfRepo:
    """Ein echtes, winziges git-Repo mit den ARBEITSFASSUNGEN der Gate-Runner.

    ★ Arbeitsfassung, nicht ``git worktree add``: der committete Stand waere ein
    anderer Runner als der, der gerade geprueft werden soll. Genau daran ist die
    erste Fassung des PROC-02b-Tests gescheitert.

    ``_gate_webengine.sh`` muss mit — ``verify_loop.sh`` sourcet es und steigt
    sonst mit exit 2 aus, bevor es die Sperre auch nur nimmt.
    """

    SKRIPTE = ("verify_loop.sh", "verify_segmented.sh", "_gate_webengine.sh")

    def __init__(self, praefix="proc02d_"):
        self.pfad = Path(tempfile.mkdtemp(prefix=praefix))
        for unter in ("tools", "tests", "src"):
            (self.pfad / unter).mkdir()
        for name in self.SKRIPTE:
            ziel = self.pfad / "tools" / name
            shutil.copy2(TOOLS / name, ziel)
            ziel.chmod(0o755)
        # Ohne venv steigt verify_loop.sh mit exit 2 aus, OHNE einen Test zu
        # fahren — und ohne die Sperre je genommen zu haben.
        (self.pfad / "venv").symlink_to(REPO / "venv")
        # `compileall -q src tools` braucht ein src-Verzeichnis.
        (self.pfad / "src" / "platzhalter.py").write_text("WERT = 1\n",
                                                          encoding="utf-8")
        subprocess.run(["git", "init", "-q", "."], cwd=str(self.pfad),
                       check=True, capture_output=True, timeout=60)
        self.pidfile = self.pfad / "enkel.pid"
        (self.pfad / "tests" / "test_enkel.py").write_text(
            ENKEL_TEST.format(pidfile=str(self.pidfile)), encoding="utf-8")

    @property
    def sperre(self) -> Path:
        """Der Pfad, den der Runner selbst ueber --git-common-dir bestimmt."""
        return self.pfad / ".git" / ".pytest_lock"

    def entferne_fd9_schluss(self) -> int:
        """Die Produktionsaenderung in den KOPIERTEN Runnern rueckgaengig machen.

        ★ **Beide** Dateien, nicht nur `verify_loop.sh`. Die Zusicherung sitzt
        seit der Nachbesserung an zwei Stellen, und zwar aus einem Grund:
        `9>&-` an der Delegation an `verify_segmented.sh` haette dem
        Segment-Runner die Sperre KOMPLETT genommen (stirbt die oberste Shell,
        laeuft ein zweiter voller Lauf neben dem ersten — PROC-02b, QA-53).
        Deshalb steht sie fuer den segmentierten Weg am **Blatt**, genau wie
        die WebEngine-Sperre ihr `8>&-`.

        Fasste diese Methode weiterhin nur `verify_loop.sh` an, bliebe die
        Beschaedigung fuer den segmentierten Lauf wirkungslos — die
        Positivkontrolle wuerde „kein Leck" messen und daraus faelschlich
        schliessen, ihre Messung sei blind.
        """
        anzahl = 0
        for name in ("verify_loop.sh", "verify_segmented.sh"):
            datei = self.pfad / "tools" / name
            if not datei.exists():
                continue
            alt = datei.read_text(encoding="utf-8")
            anzahl += alt.count(" 9>&-")
            datei.write_text(alt.replace(" 9>&-", ""), encoding="utf-8")
        return anzahl

    def starte_volle_suite(self, single=False, timeout=300):
        umgebung = dict(os.environ)
        # Der Runner soll seine Sperrdatei SELBST bestimmen; DRYRUN/NOLOCK
        # wuerden den gemessenen Mechanismus abkuerzen.
        for schluessel in ("LIGHTOS_LOCKFILE", "LIGHTOS_VERIFY_DRYRUN",
                           "LIGHTOS_VERIFY_NOLOCK", "LIGHTOS_VERIFY_SINGLE"):
            umgebung.pop(schluessel, None)
        # Eigenes Ausgabeverzeichnis und eigene Show-DB, damit ein geerbter
        # Wert nie auf das echte Gate zurueckschlaegt (QA-53).
        umgebung["LIGHTOS_SEG_OUT"] = str(self.pfad / "segout")
        umgebung["LIGHTOS_SHOW_DB"] = str(self.pfad / "kind_show.db")
        if single:
            umgebung["LIGHTOS_VERIFY_SINGLE"] = "1"
        return subprocess.run(
            ["bash", str(self.pfad / "tools" / "verify_loop.sh")],
            cwd=str(self.pfad), env=umgebung, capture_output=True, text=True,
            timeout=timeout, start_new_session=True)

    def _umgebung(self, single=False) -> dict:
        """Die Umgebung eines Wegwerf-Laufs — einmal, statt zweimal gepflegt."""
        umgebung = dict(os.environ)
        for schluessel in ("LIGHTOS_LOCKFILE", "LIGHTOS_VERIFY_DRYRUN",
                           "LIGHTOS_VERIFY_NOLOCK", "LIGHTOS_VERIFY_SINGLE"):
            umgebung.pop(schluessel, None)
        umgebung["LIGHTOS_SEG_OUT"] = str(self.pfad / "segout")
        umgebung["LIGHTOS_SHOW_DB"] = str(self.pfad / "kind_show.db")
        if single:
            umgebung["LIGHTOS_VERIFY_SINGLE"] = "1"
        return umgebung

    def starte_volle_suite_async(self, single=False):
        """Wie ``starte_volle_suite``, aber ohne zu warten — fuer die Messung
        WAEHREND des Laufs. Eigene Sitzung, damit das Abraeumen die ganze
        Gruppe trifft und kein Enkel ueberlebt."""
        return subprocess.Popen(
            ["bash", str(self.pfad / "tools" / "verify_loop.sh")],
            cwd=str(self.pfad), env=self._umgebung(single),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True)

    @staticmethod
    def beende_async(proc):
        """Die ganze Prozessgruppe abraeumen, nicht nur den Elternprozess.

        ★ `Popen.kill()` allein traefe nur die oberste Shell — genau der
        Fehler, durch den bei PROC-02c ein `sleep 600` mit PPID 1 auf der
        ECHTEN rechnerweiten Sperrdatei liegenblieb und jeden weiteren Lauf
        blockiert haette."""
        if proc.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            proc.wait(timeout=10)

    def enkel_pid(self) -> int:
        try:
            return int(self.pidfile.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return 0

    def aufraeumen(self):
        shutil.rmtree(self.pfad, ignore_errors=True)


@unittest.skipUnless(_LAEUFT, _GRUND)
class UeberlebendesKindHaeltDieSperreNichtTest(unittest.TestCase):
    """Beide Wege der vollen Suite, je einmal mit einem Waisen gemessen."""

    def setUp(self):
        self.repo = _WegwerfRepo()
        self.addCleanup(self.repo.aufraeumen)
        self._enkel = 0
        self.addCleanup(self._enkel_nachweislich_abraeumen)

    def _enkel_nachweislich_abraeumen(self):
        """★★ Der Fehler, in den PROC-02c gelaufen ist, hier nicht wiederholen.

        Dort blieb ein ``sleep 600`` mit PPID 1 auf der ECHTEN rechnerweiten
        Sperrdatei zurueck, weil ``Popen.kill()`` nur den forkenden
        flock-Elternprozess traf. Hier haelt der Waise zwar nur die Sperre des
        Wegwerf-Repos — liegenbleiben darf er trotzdem nicht, und ob er weg ist,
        wird geprueft statt angenommen.
        """
        pid = self._enkel
        if not pid:
            return
        try:
            os.killpg(pid, signal.SIGKILL)    # eigene Sitzung -> pgid == pid
        except (ProcessLookupError, PermissionError):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        ende = time.monotonic() + 10
        while time.monotonic() < ende:
            if not _lebt(pid):
                return
            time.sleep(0.05)
        self.fail(f"Der Waise {pid} liess sich nicht abraeumen — er wuerde die "
                  "Sperre des Wegwerf-Repos weiterhalten.")

    def _sperre_frei(self) -> bool:
        """Bekaeme ein Fremder die Sperre sofort? (``flock -n``, ohne Warten.)"""
        return subprocess.run(
            ["flock", "-n", str(self.repo.sperre), "true"]).returncode == 0

    def _lauf_und_waise(self, single=False, erwarte_rc=0):
        erg = self.repo.starte_volle_suite(single=single)
        self._enkel = self.repo.enkel_pid()
        self.assertEqual(erwarte_rc, erg.returncode,
                         "Der Wegwerf-Lauf selbst ist schiefgegangen:\n"
                         + erg.stdout[-3000:] + erg.stderr[-2000:])
        # Ohne diese beiden Zusicherungen pruefte der Test nichts:
        # (1) Die Sperre muss ueberhaupt genommen worden sein — sonst legt
        #     `flock -n` die Datei selbst an und meldet froehlich „frei".
        self.assertTrue(
            self.repo.sperre.exists(),
            "Der volle Lauf hat gar keine Sperrdatei angelegt — dann sagt "
            "„Sperre frei\" nichts ueber den Deskriptor aus. Erwartet am "
            f"selbst bestimmten Pfad {self.repo.sperre}:\n{erg.stdout[-2000:]}")
        # (2) Der Waise muss den Lauf wirklich ueberlebt haben.
        self.assertTrue(
            self._enkel and _lebt(self._enkel),
            "Das ueberlebende Kind war schon tot — die Messung waere "
            f"nichtssagend gewesen (pid={self._enkel}).")
        return erg

    def _pruefe_keine_sperre_im_waisen(self):
        offen = _fds(self._enkel)
        # ★ Ohne diese Zeile waere eine unlesbare /proc-Liste eine STILLE
        # Nicht-Pruefung: `traeger` bliebe leer und der Test gruen, ohne je
        # hingesehen zu haben. Ein lebender Prozess hat immer 0, 1 und 2.
        self.assertTrue(
            {0, 1, 2} <= set(offen),
            f"Die Deskriptoren von {self._enkel} waren nicht lesbar ({offen}) "
            "— dann prueft dieser Test nichts.")
        ziel = str(self.repo.sperre)
        traeger = sorted(nr for nr, wohin in offen.items() if wohin == ziel)
        self.assertEqual(
            [], traeger,
            "Der ueberlebende Waise hat die Sperrdatei noch offen "
            f"(fd {traeger}) — sie loest erst, wenn die LETZTE Kopie zu ist. "
            f"Alle Deskriptoren: {offen}")
        self.assertTrue(
            self._sperre_frei(),
            "Nach dem vollen Lauf haelt noch jemand die Voll-Suiten-Sperre. "
            "Auf der echten Sperrdatei heisst das: der naechste volle Lauf auf "
            "diesem Rechner wartet in `flock 9` ohne Deckel — also fuer immer.")

    def test_segmentierter_lauf_hinterlaesst_die_sperre_frei(self):
        """Der Normalweg: ``verify_loop.sh`` ohne Argumente -> Segment-Runner.

        Gemessen vor der Aenderung (2026-08-19): im Waisen stand
        ``9 -> <wegwerf>/.git/.pytest_lock``, und ``flock -n`` bekam die Sperre
        nicht. Der Deskriptor lief dabei durch vier Ebenen — verify_loop.sh,
        verify_segmented.sh, timeout, pytest — bis ins Enkelkind.
        """
        self._lauf_und_waise()
        self._pruefe_keine_sperre_im_waisen()

    def test_ein_prozess_lauf_hinterlaesst_die_sperre_ebenso_frei(self):
        """``LIGHTOS_VERIFY_SINGLE=1`` — der zweite Weg, der fd 9 haelt.

        ★ Das Item nannte „die beiden pytest-Aufrufe"; gemessen sind es dieser
        und die Delegation an den Segment-Runner. Der GEZIELTE Lauf gehoert
        nicht dazu: dort steigt ``_verify_lock`` bei Argumenten aus, bevor
        ``exec 9>`` laeuft (s. ``test_gezielter_lauf_nimmt_die_sperre_gar_nicht``).
        Dieser Zweig wird selten gefahren, haelt die Sperre dafuer 7 Minuten am
        Stueck — ein Waise daraus ist der teuerste von allen.
        """
        self._lauf_und_waise(single=True)
        self._pruefe_keine_sperre_im_waisen()

    # ── Die ANDERE Haelfte der Zusage ───────────────────────────────────
    def test_waehrend_des_laufs_ist_die_sperre_belegt(self):
        """★★ Ohne diesen Test war nur die halbe Zusage gemessen.

        Belegt war bisher: „kein Nachkomme haelt die Sperre NACH dem Lauf".
        Die andere Haelfte — „waehrend des Laufs wird sie ueberhaupt noch
        gehalten" — pruefte **kein Test im Repo**, und ausgerechnet dieser Fix
        gefaehrdet sie neu: er fuehrt `9>&-` ueberhaupt erst ein. Ein global
        gesetztes `exec 9>&-` (statt je Befehl) waere die Freigabe der Sperre
        selbst; die rechnerweite Serialisierung aus PROC-02/02b/02c waere dann
        **vollstaendig und still weg**, waehrend das Gate „GRUEN — alles
        bestanden" meldet.

        Genau diesen Fehlermodus benennt `verify_loop.sh` drei Zeilen ueber der
        Sperrnahme als den schlimmsten: *„Eine Sperre, die stillschweigend
        nicht greift, ist schlimmer als keine: sie laesst das Ergebnis
        vertrauenswuerdig aussehen."* Ein Kommentar davor genuegt dafuer nicht.
        """
        proc = self.repo.starte_volle_suite_async()
        self.addCleanup(self.repo.beende_async, proc)
        # Warten, bis der Lauf die Sperre wirklich genommen hat — nicht raten.
        for _ in range(200):                      # bis 20 s
            if self.repo.sperre.exists() and not self._sperre_frei():
                break
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        self.assertTrue(
            self.repo.sperre.exists(),
            "Der Lauf hat keine Sperrdatei angelegt — dann sagt die Messung "
            "unten nichts aus.")
        self.assertFalse(
            self._sperre_frei(),
            "WAEHREND des vollen Laufs ist die Sperre frei — die rechnerweite "
            "Serialisierung greift nicht mehr. Ein zweiter voller Lauf koennte "
            "jetzt danebenlaufen (PROC-02b: 11 kollidierende WebEngine-"
            "Segmente; QA-53: der zweite Lauf raeumt das .pytest_segments des "
            "ersten ab).")

    def test_nach_dem_lauf_ist_sie_wieder_frei(self):
        """POSITIVKONTROLLE zur Messung oben: haelt der Test die Sperre fuer
        belegt, obwohl sie es nie war, waere er wertlos. Nach dem Ende **muss**
        sie frei sein — sonst misst `_sperre_frei` gar nicht den Zustand,
        sondern etwas Konstantes."""
        proc = self.repo.starte_volle_suite_async()
        proc.wait(timeout=120)
        self.assertTrue(
            self._sperre_frei(),
            "Nach dem Lauf ist die Sperre noch belegt — dann unterscheidet "
            "die Messung oben nicht zwischen „laeuft\" und „fertig\".")

    def test_die_messung_wuerde_das_leck_auch_sehen(self):
        """★ POSITIVKONTROLLE zur Empfindlichkeit — die wichtigste hier.

        Beide Pruefungen oben bestehen auch dann, wenn die Messung schlicht
        blind ist: ein Waise ohne geerbten Deskriptor, eine Sperre, die nie
        genommen wurde, ein ``flock -n``, das immer 0 liefert. Deshalb dieselbe
        Messung noch einmal an einer absichtlich beschaedigten KOPIE des
        Runners, aus der ``9>&-`` entfernt ist — sie MUSS das Leck sehen.

        Das haelt die Mutation dauerhaft fest, statt sie einmal von Hand
        gefahren zu haben: verschwindet ``9>&-`` aus der Produktionsdatei, wird
        hier die Entfernung wirkungslos, die Sperre bleibt frei — und dieser
        Test wird rot.
        """
        entfernt = self.repo.entferne_fd9_schluss()
        self.assertGreaterEqual(
            entfernt, 1,
            "In der Arbeitsfassung von verify_loop.sh steht kein ` 9>&-` mehr "
            "— dann misst diese Kontrolle nichts. Entweder ist die Zusicherung "
            "verlorengegangen oder sie ist umformuliert worden.")
        self._lauf_und_waise()
        offen = _fds(self._enkel)
        self.assertIn(
            str(self.repo.sperre), offen.values(),
            "Selbst OHNE `9>&-` hat der Waise die Sperrdatei nicht geerbt — "
            "dann belegt diese Datei den Fehlerfall nicht mehr und die Tests "
            f"darueber sind wertlos. Deskriptoren: {offen}")
        self.assertFalse(
            self._sperre_frei(),
            "Ohne `9>&-` muesste der Waise die Sperre halten. Tut er es nicht, "
            "misst `flock -n` hier nicht, was es zu messen vorgibt.")

    def test_ein_lauf_ohne_waisen_laesst_die_sperre_frei(self):
        """★ POSITIVKONTROLLE zum Normalfall: die Pruefung beanstandet nichts,
        wo nichts zu beanstanden ist.

        Ohne sie koennte ``flock -n`` aus einem ganz anderen Grund scheitern
        (Rechte, Dateisystem, ein Nachbar auf derselben Datei) und die Tests
        oben waeren aus dem falschen Grund gruen — bzw. rot, ohne dass es an
        einem Deskriptor laege.
        """
        (self.repo.pfad / "tests" / "test_enkel.py").write_text(
            '"""Gewoehnliches Segment ohne Nachlass."""\n\n\n'
            "def test_harmlos():\n    assert True\n", encoding="utf-8")
        erg = self.repo.starte_volle_suite()
        self.assertEqual(0, erg.returncode, erg.stdout[-3000:])
        self.assertTrue(self.repo.sperre.exists(), erg.stdout[-2000:])
        self.assertTrue(
            self._sperre_frei(),
            "Ein voller Lauf ohne ueberlebende Kinder muss die Sperre "
            f"freigeben:\n{erg.stdout[-2000:]}")


@unittest.skipUnless(_LAEUFT, _GRUND)
class GezielterLaufNimmtDieSperreGarNichtTest(unittest.TestCase):
    """Warum am gezielten pytest-Aufruf KEIN ``9>&-`` steht.

    Das Item verlangte es „an den beiden pytest-Aufrufen". Nachgemessen ist der
    gezielte Lauf nicht darunter: ``_verify_lock`` steigt bei Argumenten aus,
    bevor ``exec 9>`` laeuft. Ein ``9>&-`` waere dort nicht pruefbar (die
    Mutation bliebe zwangslaeufig gruen) und schloesse nur einen fremden,
    vom Aufrufer geerbten Deskriptor.

    Dieser Test haelt die BEGRUENDUNG fest, nicht nur die Entscheidung: wer
    dem gezielten Lauf eine Voll-Suiten-Sperre gibt, wird hier rot — und dann
    braucht die Zeile ihr ``9>&-``.
    """

    def setUp(self):
        self.repo = _WegwerfRepo(praefix="proc02d_ziel_")
        self.addCleanup(self.repo.aufraeumen)

    def test_gezielter_lauf_legt_keine_sperrdatei_an(self):
        umgebung = dict(os.environ)
        for schluessel in ("LIGHTOS_LOCKFILE", "LIGHTOS_VERIFY_DRYRUN",
                           "LIGHTOS_VERIFY_NOLOCK", "LIGHTOS_VERIFY_SINGLE"):
            umgebung.pop(schluessel, None)
        umgebung["LIGHTOS_SHOW_DB"] = str(self.repo.pfad / "kind_show.db")
        (self.repo.pfad / "tests" / "test_enkel.py").write_text(
            HARMLOS, encoding="utf-8")
        erg = subprocess.run(
            ["bash", str(self.repo.pfad / "tools" / "verify_loop.sh"),
             "tests/test_enkel.py"],
            cwd=str(self.repo.pfad), env=umgebung, capture_output=True,
            text=True, timeout=300, start_new_session=True)
        self.assertEqual(0, erg.returncode, erg.stdout[-3000:])
        self.assertFalse(
            self.repo.sperre.exists(),
            "Der gezielte Lauf hat die Voll-Suiten-Sperre genommen. Dann "
            "erbt sein pytest-Kind fd 9 — und die pytest-Zeile im gezielten "
            "Zweig braucht dasselbe `9>&-` wie die beiden Wege der vollen "
            "Suite (PROC-02d).")


if __name__ == "__main__":
    unittest.main()
