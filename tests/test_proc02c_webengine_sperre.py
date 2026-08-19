"""PROC-02c — WebEngine-Segmente duerfen sich auch ueber LAEUFE hinweg nicht ueberlappen.

Seit XPLAT-17 hat ``verify_segmented.sh`` eine serielle WebEngine-Spur. Die
serialisiert aber nur INNERHALB eines Laufs. Mit parallel arbeitenden Agenten
laufen mehrere Gates und Dutzende gezielter Einzellaeufe gleichzeitig auf
demselben Rechner — und dann stehen wieder zwei WebGL-Kontexte nebeneinander.

Der bisherige Schutz war ein Warten von bis zu 3 s vor jedem WebEngine-Segment,
mit der Bedingung ``pgrep -u <uid> -x QtWebEngineProc``: rechnerweit, ueber alle
Sitzungen. Das ist genau der Fehler, den die Windows-Fassung schon einmal hatte —
ein einziger fremder Prozess haelt die Bedingung dauerhaft offen, jedes Segment
laeuft stumpf in den Deckel, und das Warten bewirkt nichts.

★ Gemessen 2026-08-18 (41 WebEngine-Dateien, Zuordnung ueber die
Prozessgruppe): die EIGENEN Chromium-Kinder eines Segments sind nach spaetestens
0,037 s weg. Der 3-s-Deckel hat also nie auf eigene Kinder gewartet, sondern
immer nur auf fremde.

Diese Datei prueft die beiden Zusicherungen, die daraus folgen — am **echten
Runner**, nicht am Skripttext:

1. Zwei GLEICHZEITIGE Laeufe fahren nie zwei WebEngine-Segmente nebeneinander.
2. Die Sperre wird je SEGMENT abgegeben — ein Einzellauf kommt dazwischen und
   wartet nicht die ganze Spur ab.
3. Der Rest der Suite bleibt parallel — die Sperre darf nicht auf ihn durchschlagen.
4. Ein GEZIELTER Lauf auf eine WebEngine-Datei nimmt dieselbe Sperre …
5. … ein gezielter Lauf ohne WebEngine-Datei aber nicht.
6. Eine haengende Sperre blockiert das Gate nicht, sie meldet sich.
7. Ein ueberlebendes Kind haelt die Sperre nicht rechnerweit fest.
8. Ein Runner INNERHALB eines Segments wartet nicht auf die Sperre seines
   eigenen Elternlaufs.
9. Der Runner wartet an der richtigen Stelle wirklich auf eigene Kinder —
   und meldet das im Normalfall NICHT.
10. Das Warten erkennt ECHTE QtWebEngineProc-Prozesse der eigenen
    Prozessgruppe und laesst sich von fremden nicht aufhalten.
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEG_RUNNER = REPO / "tools" / "verify_segmented.sh"
LOOP_RUNNER = REPO / "tools" / "verify_loop.sh"
HELFER = REPO / "tools" / "_gate_webengine.sh"

_LAEUFT = (SEG_RUNNER.exists() and os.name != "nt"
           and shutil.which("bash") is not None
           and shutil.which("flock") is not None)
_GRUND = ("Der Segment-Runner IST das Linux-Gate; auf Windows faehrt "
          "run_tests.ps1 -Isolate. Ohne flock gibt es bewusst keine Sperre.")

# Der Runner entscheidet per Textsuche, welche Datei als WebEngine-Segment gilt.
# Ein echter Import wuerde diese Mini-Dateien um Sekunden verlangsamen, ohne
# etwas zusaetzlich zu pruefen — geprueft wird der Runner, nicht Qt.
MARKER = '"""Zaehlt als WebEngine-Segment: QWebEngineView."""'
HARMLOS = '"""Gewoehnliches Segment ohne Szene."""'

VORLAGE = '''{marker}
import time

def test_spur():
    start = time.monotonic()
    time.sleep({schlaf})
    with open({protokoll!r}, "a") as fh:
        fh.write("%s %.4f %.4f\\n" % ({name!r}, start, time.monotonic()))
'''


def _umgebung(**extra):
    """Gate-Umgebung fuer einen Unter-Runner.

    ``LIGHTOS_WEBENGINE_LOCK_HELD`` MUSS raus: diese Datei enthaelt selbst den
    WebEngine-Marker, laeuft im echten Gate also als WebEngine-Segment und haelt
    die Sperre bereits. Der Wiedereintritts-Schutz wuerde die Unter-Runner sonst
    an der Sperre vorbeilassen — der Test waere gruen, ohne etwas zu pruefen.
    """
    env = dict(os.environ)
    env.pop("LIGHTOS_WEBENGINE_LOCK_HELD", None)
    env.update(extra)
    return env


def _ueberlappt(a, b):
    return a[0] < b[1] and b[0] < a[1]


def _halte_sperre(pfad):
    """Ein Fremder, der die Sperre haelt — als Prozess, den man RESTLOS los wird.

    ★ Gemessen 2026-08-19, und es ist genau der Fehler, gegen den die
    Produktionsseite ``8>&-`` einsetzt: ``flock DATEI BEFEHL`` forkt (util-linux,
    ohne ``-F``). ``Popen.kill()`` trifft damit nur den flock-Elternprozess —
    das KIND laeuft weiter und haelt den geerbten Deskriptor. Nachgesehen:
    ``sleep 600``, PID 8903, PPID 1 (an init umgehaengt), Sperre BELEGT, obwohl
    der Test laengst durch war.

    Deshalb: eigene Sitzung beim Start, und abgeraeumt wird die ganze
    Prozessgruppe.
    """
    return subprocess.Popen(["flock", str(pfad), "sleep", "600"],
                            start_new_session=True)


def _halter_abraeumen(halter):
    try:
        os.killpg(halter.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        halter.wait(timeout=60)
    except subprocess.TimeoutExpired:
        pass


def _lebt(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:      # existiert, gehoert nur jemand anderem
        return True
    return True


def _lies_protokoll(pfad):
    zeiten = {}
    for zeile in Path(pfad).read_text(encoding="utf-8").splitlines():
        name, start, ende = zeile.split()
        zeiten[name] = (float(start), float(ende))
    return zeiten


@unittest.skipUnless(_LAEUFT, _GRUND)
class SperreUeberLaeufeHinwegTest(unittest.TestCase):
    """Die Zusicherung, um die es in PROC-02c geht."""

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="proc02c_"))
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)
        self.protokoll = self._tmp / "spuren.txt"
        self.protokoll.write_text("", encoding="utf-8")
        # Eigene Sperrdatei: der Test darf sich nicht mit dem echten Gate um die
        # rechnerweite Sperre streiten (und umgekehrt).
        self.sperre = self._tmp / ".webengine_lock"

    def _dateien(self, praefix, marker, anzahl=3, schlaf=0.5):
        pfade = []
        for i in range(anzahl):
            name = f"{praefix}{i}"
            p = self._tmp / f"test_{name}.py"
            p.write_text(VORLAGE.format(marker=marker, schlaf=schlaf,
                                        protokoll=str(self.protokoll), name=name),
                         encoding="utf-8")
            pfade.append(str(p))
        return pfade

    def _starte_runner(self, dateien, nr):
        env = _umgebung(LIGHTOS_SEG_OUT=str(self._tmp / f"out{nr}"),
                        LIGHTOS_WEBENGINE_LOCKFILE=str(self.sperre))
        return subprocess.Popen(["bash", str(SEG_RUNNER), "-j", "3", *dateien],
                                cwd=str(REPO), env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True)

    def test_zwei_gleichzeitige_laeufe_ueberlappen_nie_im_webengine_segment(self):
        a = self._dateien("weba", MARKER)
        b = self._dateien("webb", MARKER)
        p1 = self._starte_runner(a, 1)
        p2 = self._starte_runner(b, 2)
        aus1 = p1.communicate(timeout=300)[0]
        aus2 = p2.communicate(timeout=300)[0]
        self.assertEqual(0, p1.returncode, aus1)
        self.assertEqual(0, p2.returncode, aus2)

        zeiten = _lies_protokoll(self.protokoll)
        self.assertEqual(6, len(zeiten), f"nicht alle Segmente liefen: {sorted(zeiten)}")
        namen = sorted(zeiten)
        paare = [(x, y) for i, x in enumerate(namen) for y in namen[i + 1:]
                 if _ueberlappt(zeiten[x], zeiten[y])]
        self.assertEqual(
            [], paare,
            "Zwei WebEngine-Segmente liefen gleichzeitig, obwohl sie zu "
            "VERSCHIEDENEN Laeufen gehoeren — genau der Fall, den ein Agent "
            f"auf diesem Rechner Dutzende Male am Tag erzeugt: {paare} / {zeiten}")

    def test_ein_einzellauf_kommt_zwischen_die_segmente_der_vollen_suite(self):
        """★ Die Sperre wird je Segment abgegeben, nicht je Lauf.

        Beides verhindert Ueberlappung — der Unterschied ist die Wartezeit der
        anderen Sitzung. Die WebEngine-Spur der vollen Suite laeuft rund 7
        Minuten (41 Segmente, 2026-08-18 gemessen: 413 s). Wuerde sie die
        Sperre am Stueck halten, wartete jeder gezielte Lauf eines Agenten bis
        zu 7 Minuten auf eine Datei, die in 15 Sekunden durch waere — und die
        Sperre, die Fehlalarme abstellen soll, waere selbst der neue Aerger.

        Geprueft wird deshalb die Verschraenkung: nachdem ein Fremder die
        Sperre bekommen hat, muss noch mindestens ein Segment der Suite
        ANFANGEN.

        ⚠️ Der Mitbewerber ist bewusst ein nacktes ``flock`` und kein zweiter
        Gate-Lauf: ein `verify_loop.sh` braeuchte erst seinen Syntax-Check,
        und wie lange der dauert, haengt an der Maschinenlast. Er wird
        ausserdem erst scharfgeschaltet, wenn das erste Segment nachweislich
        laeuft (die Logdatei existiert). Damit haengt der Test an keiner
        Zeitannahme mehr, sondern nur noch an der Reihenfolge.
        """
        lauf = self._dateien("weblang", MARKER, anzahl=5, schlaf=0.8)
        aus_dir = self._tmp / "out1"
        runner = self._starte_runner(lauf, 1)
        stempel = self._tmp / "mitbewerber.txt"
        mit = None
        try:
            for _ in range(3000):                    # bis 300 s
                if aus_dir.is_dir() and any(aus_dir.glob("*.log")):
                    break
                if runner.poll() is not None:
                    self.fail("Der Runner war fertig, bevor ein Segment lief.")
                time.sleep(0.1)
            code = (f"import time; open({str(stempel)!r},'w')"
                    ".write(repr(time.monotonic()))")
            mit = subprocess.Popen(
                ["flock", str(self.sperre), sys.executable, "-c", code],
                start_new_session=True)
            aus_r = runner.communicate(timeout=300)[0]
        finally:
            if mit is not None:
                try:
                    mit.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    _halter_abraeumen(mit)
        self.assertEqual(0, runner.returncode, aus_r)
        self.assertTrue(stempel.exists(),
                        "Der Mitbewerber hat die Sperre nie bekommen.")
        mit_zeit = float(stempel.read_text(encoding="utf-8"))
        zeiten = _lies_protokoll(self.protokoll)
        danach = [n for n, (s, _) in zeiten.items() if s > mit_zeit]
        self.assertTrue(
            danach,
            "Ein Fremder bekam die Sperre erst, nachdem die ganze Spur durch "
            "war — sie wird pro LAUF gehalten statt pro Segment. Im Gate "
            f"heisst das bis zu 7 Minuten Wartezeit je Einzellauf: {zeiten}")

    def test_gewoehnliche_segmente_warten_nicht_auf_die_webengine_sperre(self):
        """★ Positivkontrolle — ohne sie waere der Test darueber wertlos.

        Eine Sperre, die einfach ALLES serialisiert, bestuende die Pruefung
        oben ebenfalls und machte das Gate dabei um Minuten langsamer. 95 % der
        Suite haben mit WebGL nichts zu tun.

        ⚠️ ZWEI Entwuerfe waren vorher lastabhaengig, und beide sind im vollen
        Gate rot geworden, ohne dass etwas kaputt war: erst die Ueberlappung
        zweier paralleler Laeufe (neben drei fremden Suiten auf vier Kernen
        liefen die Segmente einfach nacheinander), dann der Vergleich „Segment
        startet vor der Freigabe nach 8 s" (der Runner brauchte unter Last
        laenger als 8 s bis zum ersten Segment). Ausgerechnet in DIESEM Item
        ist ein lastabhaengiger Fehlalarm die falsche Antwort.

        Jetzt ohne jede Zeitannahme: die Sperre wird gehalten, die Wartezeit
        auf 1 s gestellt — ein gewoehnlicher Lauf darf sie **gar nicht erst
        anfassen**. Beruehrte er sie, protokollierte der Runner das (er kaeme
        nach 1 s nicht an sie heran), und genau diese Protokolldateien duerfen
        nicht entstehen.
        """
        halter = _halte_sperre(self.sperre)
        try:
            dateien = self._dateien("rest", HARMLOS, anzahl=2, schlaf=0.2)
            aus_dir = self._tmp / "out1"
            env = _umgebung(LIGHTOS_SEG_OUT=str(aus_dir),
                            LIGHTOS_WEBENGINE_LOCKFILE=str(self.sperre),
                            LIGHTOS_WEBENGINE_SPERRE_WARTE="1",
                            # ★ Genau der Zustand, in dem dieser Test im Gate
                            # laeuft: er IST ein WebEngine-Segment. Frueher
                            # markierte die Spur das per `export SEG_WEBENGINE=1`
                            # — der pytest-Prozess erbte es, und ein darin
                            # gestarteter Runner hielt dann JEDE seiner Dateien
                            # fuer ein WebEngine-Segment. Hier wird die Variable
                            # absichtlich gesetzt, damit die Zusicherung auch
                            # ausserhalb des Gates greift.
                            SEG_WEBENGINE="1")
            erg = subprocess.run(["bash", str(SEG_RUNNER), "-j", "3", *dateien],
                                 cwd=str(REPO), env=env, capture_output=True,
                                 text=True, timeout=300)
        finally:
            _halter_abraeumen(halter)
        self.assertEqual(0, erg.returncode, erg.stdout)
        self.assertEqual(2, len(_lies_protokoll(self.protokoll)))
        beruehrt = [n for n in ("sperre_gewartet.txt", "sperre_vergeblich.txt")
                    if (aus_dir / n).exists()]
        self.assertEqual(
            [], beruehrt,
            "Ein Lauf ganz ohne WebEngine-Datei hat die WebEngine-Sperre "
            f"angefasst ({beruehrt}) — sie ist auf die schnelle Spur "
            f"durchgeschlagen:\n{erg.stdout}")


@unittest.skipUnless(_LAEUFT, _GRUND)
class GezielterLaufNimmtDieSperreTest(unittest.TestCase):
    """Vorschlag (b) aus dem Item: die Sperre muss auch Einzellaeufe erfassen.

    Der Befund von PROC-02c war ja genau, dass die bestehende Sperre in
    ``verify_loop.sh`` gezielte Laeufe ausnimmt (``[ "$#" -gt 0 ] && return 0``) —
    und dass Agenten fast nur solche fahren.
    """

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="proc02c_ziel_"))
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)
        self.sperre = self._tmp / ".webengine_lock"
        self.sperre.touch()
        self.freigabe = self._tmp / "freigabe.txt"
        self.protokoll = self._tmp / "spuren.txt"
        self.protokoll.write_text("", encoding="utf-8")

    def _halter(self, sekunden):
        """Eine „andere Sitzung", die die Sperre haelt und ihre Freigabe stempelt.

        Zeitstempel statt Laufzeitmessung: ``time.monotonic()`` ist auf Linux
        prozessuebergreifend dieselbe Uhr, damit ist der Vergleich exakt statt
        an Toleranzen gehaengt.
        """
        code = (f"import time; time.sleep({sekunden}); "
                f"open({str(self.freigabe)!r},'w').write(repr(time.monotonic()))")
        return subprocess.Popen(["flock", str(self.sperre), sys.executable, "-c", code],
                                start_new_session=True)

    def _lauf(self, marker, timeout=200, **extra):
        p = self._tmp / "test_ziel.py"
        p.write_text(VORLAGE.format(marker=marker, schlaf=0.1,
                                    protokoll=str(self.protokoll), name="ziel"),
                     encoding="utf-8")
        env = _umgebung(LIGHTOS_WEBENGINE_LOCKFILE=str(self.sperre),
                        LIGHTOS_SEG_OUT=str(self._tmp / "out"),
                        LIGHTOS_SHOW_DB=str(self._tmp / "kind.db"), **extra)
        return subprocess.run([str(LOOP_RUNNER), str(p)], cwd=str(REPO), env=env,
                              capture_output=True, text=True, timeout=timeout)

    def test_webengine_einzellauf_wartet_auf_die_sperre(self):
        halter = self._halter(6)
        try:
            erg = self._lauf(MARKER)
        finally:
            halter.wait(timeout=60)
        self.assertEqual(0, erg.returncode, erg.stdout[-3000:])
        freigabe = float(self.freigabe.read_text(encoding="utf-8"))
        start = _lies_protokoll(self.protokoll)["ziel"][0]
        self.assertGreater(
            start, freigabe,
            "Der gezielte Lauf hat sein WebEngine-Segment gestartet, waehrend "
            "eine andere Sitzung die Sperre hielt. Genau so entstehen die roten "
            "Segmente, die isoliert gruen sind (PROC-02c).")

    def test_eine_haengende_sperre_blockiert_das_gate_nicht(self):
        """Eine Sperre, die haengt, waere schlimmer als keine.

        Der Halter gibt hier NIE frei (bis der Test ihn abraeumt). Der Lauf muss
        trotzdem zu Ende kommen — mit sichtbarer Warnung, nicht stillschweigend.
        Ohne diese Zusicherung koennte ein einziger haengengebliebener Prozess
        jedes Gate auf dem Rechner fuer 15 Minuten stilllegen.
        """
        halter = self._halter(600)
        try:
            erg = self._lauf(MARKER, timeout=200,
                             LIGHTOS_WEBENGINE_SPERRE_WARTE="2")
        finally:
            _halter_abraeumen(halter)
        self.assertEqual(0, erg.returncode, erg.stdout[-3000:])
        self.assertIn("ungesperrt", erg.stdout.lower(),
                      "Der Lauf lief zwar durch, sagte aber nicht, dass die "
                      f"Sperre nicht griff:\n{erg.stdout[-3000:]}")

    def test_lauf_ohne_webengine_datei_wird_NICHT_gesperrt(self):
        """★ Positivkontrolle. Die allermeisten Einzellaeufe haben mit WebGL
        nichts zu tun; sie hinter einer rechnerweiten Sperre anzustellen waere
        die teuerste Art, nichts zu gewinnen.

        Ohne Zeitannahme: die Sperre wird gehalten, die Wartezeit steht auf
        1 s. Ein Lauf ohne WebEngine-Datei darf sie gar nicht erst anfassen —
        taete er es, meldete er nach 1 s, dass er sie nicht bekommen hat.
        """
        halter = _halte_sperre(self.sperre)
        try:
            erg = self._lauf(HARMLOS, LIGHTOS_WEBENGINE_SPERRE_WARTE="1")
        finally:
            _halter_abraeumen(halter)
        self.assertEqual(0, erg.returncode, erg.stdout[-3000:])
        self.assertEqual(1, len(_lies_protokoll(self.protokoll)))
        for satz in ("WebEngine-Sperre war belegt", "Sperre nicht bekommen"):
            self.assertNotIn(
                satz, erg.stdout,
                "Ein Lauf ohne WebEngine-Datei hat die WebEngine-Sperre "
                f"angefasst — sie greift zu weit:\n{erg.stdout[-3000:]}")

    # ── Nachtrag 2026-08-19: welche ARGUMENTE gelten als WebEngine-Lauf? ─────

    def _verzeichnis(self, marker, name):
        verz = self._tmp / name
        verz.mkdir()
        (verz / "test_drin.py").write_text(
            VORLAGE.format(marker=marker, schlaf=0.1,
                           protokoll=str(self.protokoll), name=name),
            encoding="utf-8")
        return verz

    def _lauf_mit(self, *argumente, timeout=200, **extra):
        env = _umgebung(LIGHTOS_WEBENGINE_LOCKFILE=str(self.sperre),
                        LIGHTOS_SEG_OUT=str(self._tmp / "out"),
                        LIGHTOS_SHOW_DB=str(self._tmp / "kind.db"), **extra)
        return subprocess.run([str(LOOP_RUNNER), *argumente], cwd=str(REPO),
                              env=env, capture_output=True, text=True,
                              timeout=timeout)

    def test_ein_verzeichnis_als_argument_nimmt_die_sperre_auch(self):
        """★★ Der Fall, den die erste Fassung STILL uebersprang.

        Sie fragte ``[ -f "$pfad" ]`` und liess damit ausgerechnet den
        schlimmsten Aufruf durch: ``./tools/verify_loop.sh tests/`` faehrt ALLE
        41 WebEngine-Dateien in EINEM pytest-Prozess — und lief dabei komplett
        an der Sperre vorbei. Gemessen am 19.08.2026 an der damaligen
        Arbeitsfassung: mit Datei-Argument meldete der Runner „Sperre nicht
        bekommen", mit Verzeichnis-Argument gar nichts.

        Ohne Zeitannahme: die Sperre wird gehalten, die Wartezeit steht auf 1 s.
        Ein Lauf, der sie nimmt, kommt nicht an sie heran und sagt das.
        """
        verz = self._verzeichnis(MARKER, "mit_web")
        halter = _halte_sperre(self.sperre)
        try:
            erg = self._lauf_mit(str(verz), LIGHTOS_WEBENGINE_SPERRE_WARTE="1")
        finally:
            _halter_abraeumen(halter)
        self.assertEqual(0, erg.returncode, erg.stdout[-3000:])
        self.assertIn(
            "UNGESPERRT", erg.stdout.upper(),
            "Ein Verzeichnis-Argument hat die WebEngine-Sperre nicht genommen. "
            "Genau dieser Aufruf laedt die meisten WebEngine-Dateien von "
            f"allen:\n{erg.stdout[-3000:]}")

    def test_ein_verzeichnis_OHNE_webengine_datei_nimmt_sie_nicht(self):
        """★ Positivkontrolle zum Test darueber.

        Sonst waere die billigste Loesung „jedes Verzeichnis sperren" — und
        damit saesse die halbe Suite hinter einer rechnerweiten Sperre.
        """
        verz = self._verzeichnis(HARMLOS, "ohne_web")
        halter = _halte_sperre(self.sperre)
        try:
            erg = self._lauf_mit(str(verz), LIGHTOS_WEBENGINE_SPERRE_WARTE="1")
        finally:
            _halter_abraeumen(halter)
        self.assertEqual(0, erg.returncode, erg.stdout[-3000:])
        self.assertEqual(1, len(_lies_protokoll(self.protokoll)))
        for satz in ("WebEngine-Sperre war belegt", "Sperre nicht bekommen"):
            self.assertNotIn(satz, erg.stdout,
                             f"Verzeichnis ohne WebEngine-Datei gesperrt:\n"
                             f"{erg.stdout[-3000:]}")

    def test_auch_der_segment_runner_sieht_in_ein_verzeichnis(self):
        """Dieselbe Erkennung, anderer Runner — sonst driften die beiden.

        Der Segment-Runner bekommt seine Dateien meist aus ``find``, also immer
        einzeln. Ein Verzeichnis als Argument ist aber moeglich, und dann galt
        dieselbe Luecke wie in ``verify_loop.sh``. Zwei Runner mit zwei
        Antworten auf dieselbe Frage waeren genau die Drift, gegen die
        ``tools/_gate_webengine.sh`` ueberhaupt existiert (XPLAT-11).

        Gemessen an den Protokolldateien der Segmentausgabe, nicht am Text:
        ``sperre_vergeblich.txt`` entsteht nur, wenn ein Segment die Sperre
        genommen — und nach 1 s nicht bekommen — hat.
        """
        # ★ Beide Wege des Runners: die Zwei-Spuren-Fassung (-j 2) UND der
        # serielle Notweg (-j 1), der die Spur-Trennung gar nicht erst macht.
        # Die Sperre gilt rechnerweit und darf nicht davon abhaengen, wie DIESER
        # Lauf seine Segmente verteilt.
        faelle = (("seg_mit_parallel", "2", MARKER, True),
                  ("seg_mit_seriell", "1", MARKER, True),
                  ("seg_ohne", "2", HARMLOS, False))
        for name, jobs, marker, erwartet in faelle:
            with self.subTest(verzeichnis=name, jobs=jobs):
                verz = self._verzeichnis(marker, name)
                aus_dir = self._tmp / f"out_{name}"
                halter = _halte_sperre(self.sperre)
                try:
                    env = _umgebung(
                        LIGHTOS_SEG_OUT=str(aus_dir),
                        LIGHTOS_WEBENGINE_LOCKFILE=str(self.sperre),
                        LIGHTOS_WEBENGINE_SPERRE_WARTE="1",
                        LIGHTOS_SHOW_DB=str(self._tmp / f"{name}.db"))
                    erg = subprocess.run(
                        ["bash", str(SEG_RUNNER), "-j", jobs, str(verz)],
                        cwd=str(REPO), env=env, capture_output=True,
                        text=True, timeout=300)
                finally:
                    _halter_abraeumen(halter)
                self.assertEqual(0, erg.returncode, erg.stdout)
                self.assertEqual(
                    erwartet, (aus_dir / "sperre_vergeblich.txt").exists(),
                    "Der Segment-Runner beantwortet die Frage „WebEngine?\" "
                    "fuer ein Verzeichnis anders als verify_loop.sh:\n"
                    f"{erg.stdout}")

    def _entscheidung(self, cwd, *argumente):
        """Ruft die ECHTE Entscheidungsfunktion aus tools/_gate_webengine.sh.

        Der Weg ueber den Runner steht in den beiden Tests darueber; hier geht
        es um den Fall „gar kein Pfad dabei", den man ueber den Runner nur mit
        einem Voll-Suiten-Lauf messen koennte. Aufgerufen wird die
        Produktionsfunktion selbst, kein Nachbau.
        """
        skript = f'. "{HELFER}"; webengine_argumente "$@" && echo JA || echo NEIN'
        erg = subprocess.run(["bash", "-c", skript, "_", *argumente],
                             cwd=str(cwd), capture_output=True, text=True,
                             timeout=60)
        return erg.stdout.strip()

    def test_ohne_pfadargument_zaehlt_die_vorgabe_von_pytest(self):
        """``verify_loop.sh -k viz`` gibt pytest keinen Pfad — dann sammelt es
        die Vorgabe, also die ganze Suite samt WebEngine.

        Beide Richtungen an einem gestellten Arbeitsverzeichnis, damit die
        Aussage nicht davon abhaengt, was gerade in ``tests/`` liegt.
        """
        mit = self._tmp / "wurzel_mit" / "tests"
        ohne = self._tmp / "wurzel_ohne" / "tests"
        for verz, marker in ((mit, MARKER), (ohne, HARMLOS)):
            verz.mkdir(parents=True)
            (verz / "test_x.py").write_text(marker + "\n", encoding="utf-8")
        self.assertEqual("JA", self._entscheidung(mit.parent, "-k", "viz"),
                         "Ein Lauf ohne Pfadargument sammelt tests/ — dort "
                         "liegen WebEngine-Dateien, er muss die Sperre nehmen.")
        self.assertEqual("NEIN", self._entscheidung(ohne.parent, "-k", "viz"),
                         "★ Positivkontrolle: ohne WebEngine-Datei in tests/ "
                         "darf auch ein Lauf ohne Pfadargument frei laufen.")
        # ★ Und die Vorgabe darf nur greifen, wenn WIRKLICH kein Pfad dabei ist:
        # ein genannter harmloser Pfad schlaegt sie, obwohl tests/ hier voller
        # WebEngine-Dateien ist. Ohne diese Zusicherung waere die billigste
        # Loesung „im Zweifel immer sperren" — und die haette den gezielten
        # Einzellauf, um den es in PROC-02c geht, hinter die Sperre gestellt.
        harmlos = mit.parent / "extra_harmlos.py"
        harmlos.write_text(HARMLOS + "\n", encoding="utf-8")
        self.assertEqual("NEIN",
                         self._entscheidung(mit.parent, str(harmlos), "-k", "viz"),
                         "Ein ausdruecklich genannter harmloser Pfad wurde von "
                         "der Vorgabe ueberstimmt — die Erkennung sperrt zu weit.")


@unittest.skipUnless(_LAEUFT, _GRUND)
class SperreGibtSichSelbstFreiTest(unittest.TestCase):
    """Zwei Wege, auf denen sich eine rechnerweite Sperre selbst erledigt."""

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="proc02c_frei_"))
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)
        self.sperre = self._tmp / ".webengine_lock"
        self.sperre.touch()

    def _sperre_frei(self):
        """Bekommt ein Fremder die Sperre sofort? (`flock -n`, ohne Warten.)"""
        return subprocess.run(["flock", "-n", str(self.sperre), "true"]).returncode == 0

    def test_ein_ueberlebender_enkelprozess_haelt_die_sperre_nicht_fest(self):
        """★ Der teuerste denkbare Fehler dieser Sperre.

        `flock` loest erst, wenn die LETZTE Kopie des Deskriptors zu ist. Erbt
        ein Chromium-Kind ihn und ueberlebt den Segmentlauf — Windows hat genau
        so einen Waisen dokumentiert, acht Minuten alt und nie gestorben —,
        dann bliebe die Sperre RECHNERWEIT haengen: jeder kuenftige
        WebEngine-Lauf wartet 15 Minuten und laeuft dann ungesperrt. Deshalb
        schliesst der Runner fd 8 im Kind.

        Das Mini-Segment stellt genau das nach: ein abgekoppeltes Kind, das den
        Lauf ueberlebt, mit ``close_fds=False`` — so, wie Chromium seine
        Hilfsprozesse startet.
        """
        pidfile = self._tmp / "enkel.pid"
        p = self._tmp / "test_enkel.py"
        p.write_text(
            MARKER + f'''
import subprocess

def test_spur():
    k = subprocess.Popen(["sleep", "300"], start_new_session=True, close_fds=False)
    open({str(pidfile)!r}, "w").write(str(k.pid))
''', encoding="utf-8")
        env = _umgebung(LIGHTOS_SEG_OUT=str(self._tmp / "out"),
                        LIGHTOS_WEBENGINE_LOCKFILE=str(self.sperre))
        erg = subprocess.run(["bash", str(SEG_RUNNER), "-j", "2", str(p)],
                             cwd=str(REPO), env=env, capture_output=True,
                             text=True, timeout=300)
        enkel = int(pidfile.read_text(encoding="utf-8")) if pidfile.exists() else 0
        try:
            self.assertEqual(0, erg.returncode, erg.stdout)
            # Lebt der Enkel ueberhaupt noch? Sonst pruefte der Test nichts —
            # eine stille Nicht-Pruefung waere schlimmer als ein rotes Ergebnis.
            self.assertTrue(enkel and _lebt(enkel),
                            "Der ueberlebende Enkel war schon tot — die "
                            "Pruefung waere nichtssagend gewesen.")
            self.assertTrue(
                self._sperre_frei(),
                "Nach dem Lauf haelt noch jemand die WebEngine-Sperre — ein "
                "geerbter Deskriptor in einem ueberlebenden Kind. Ab jetzt "
                "wartet jeder WebEngine-Lauf auf diesem Rechner ins Leere.")
        finally:
            if enkel:
                try:
                    os.kill(enkel, 9)
                except ProcessLookupError:
                    pass

    def test_der_runner_wartet_wirklich_auf_seine_eigenen_kinder(self):
        """Die Einbaustelle, nicht nur die Funktion.

        Der Runner darf die Sperre nicht weiterreichen, solange eigene
        Chromium-Kinder leben. Nachgestellt mit einem Prozess, der den Namen
        traegt, auf den der Runner prueft (``QtWebEngineProc``), und der das
        Segment ueberlebt — er bleibt in dessen Prozessgruppe, weil er NICHT
        abgekoppelt gestartet wird. Genau so verhalten sich Chromiums
        Hilfsprozesse.

        Die Erkennung selbst laeuft an ECHTEN QtWebEngineProc-Prozessen in
        ``WartenAufEigeneKinderTest``; hier geht es darum, dass der Runner sie
        an der richtigen Stelle ueberhaupt aufruft.
        """
        fake = self._tmp / "QtWebEngineProc"      # comm: genau 15 Zeichen
        shutil.copy2("/bin/sleep", fake)
        pidfile = self._tmp / "fake.pid"
        p = self._tmp / "test_langlebig.py"
        # 300 s Lebensdauer, damit der Stellvertreter unter Last sicher noch
        # lebt, wenn der Runner nach dem Segment nachsieht — und danach vom
        # Test selbst abgeraeumt wird. Bliebe er liegen, wuerde er in den
        # naechsten Segmenten als „fremdes Chromium" gemeldet: ein Fehlalarm,
        # den ausgerechnet dieser Test erzeugt haette.
        p.write_text(
            MARKER + f'''
import subprocess

def test_spur():
    k = subprocess.Popen([{str(fake)!r}, "300"])
    open({str(pidfile)!r}, "w").write(str(k.pid))
''', encoding="utf-8")
        env = _umgebung(LIGHTOS_SEG_OUT=str(self._tmp / "out3"),
                        LIGHTOS_WEBENGINE_LOCKFILE=str(self.sperre),
                        LIGHTOS_WEBENGINE_KIND_DECKEL="0.5")
        erg = subprocess.run(["bash", str(SEG_RUNNER), "-j", "2", str(p)],
                             cwd=str(REPO), env=env, capture_output=True,
                             text=True, timeout=300)
        fake_pid = int(pidfile.read_text(encoding="utf-8")) if pidfile.exists() else 0
        try:
            self.assertEqual(0, erg.returncode, erg.stdout)
            self.assertIn(
                "EIGENE Chromium-Kinder", erg.stdout,
                "Der Runner hat die Sperre freigegeben, ohne auf seine eigenen "
                f"Kinder zu sehen:\n{erg.stdout}")
        finally:
            if fake_pid:
                try:
                    os.kill(fake_pid, 9)
                except ProcessLookupError:
                    pass

    def test_ein_gewoehnliches_segment_meldet_keine_uebrigen_kinder(self):
        """★ Positivkontrolle zur Pruefung darueber.

        Gemessen ueber 41 WebEngine-Dateien war die eigene Prozessgruppe beim
        ersten Nachsehen leer (spaetestens 0,037 s). Schlaegt die Meldung im
        Normalfall an, ist die Erkennung zu weit — und das Gate wartet wieder
        bei jedem Segment auf etwas, das es nicht gibt.
        """
        p = self._tmp / "test_normal.py"
        p.write_text(VORLAGE.format(marker=MARKER, schlaf=0.1,
                                    protokoll=str(self._tmp / "spuren2.txt"),
                                    name="normal"), encoding="utf-8")
        env = _umgebung(LIGHTOS_SEG_OUT=str(self._tmp / "out4"),
                        LIGHTOS_WEBENGINE_LOCKFILE=str(self.sperre),
                        LIGHTOS_WEBENGINE_KIND_DECKEL="0.5")
        erg = subprocess.run(["bash", str(SEG_RUNNER), "-j", "2", str(p)],
                             cwd=str(REPO), env=env, capture_output=True,
                             text=True, timeout=300)
        self.assertEqual(0, erg.returncode, erg.stdout)
        self.assertNotIn("EIGENE Chromium-Kinder", erg.stdout, erg.stdout)

    def test_verschachtelter_runner_wartet_nicht_auf_sich_selbst(self):
        """Der Gate-Lauf enthaelt einen Runner, der einen Runner startet.

        ``tests/test_gate_webengine_lane.py`` zaehlt selbst als
        WebEngine-Segment — es laeuft also, waehrend die Sperre gehalten wird,
        und startet den Segment-Runner erneut. Ohne Wiedereintritts-Schutz
        wartete dieser innere Lauf auf die Sperre seines eigenen Elternlaufs,
        bis die Wartezeit ablaeuft: 15 Minuten Stillstand mitten im Gate.

        Nachgestellt mit einem Halter, der nie freigibt (= das aeussere
        Segment), und der Umgebung, die das aeussere Segment vererbt.
        """
        halter = _halte_sperre(self.sperre)
        p = self._tmp / "test_innen.py"
        p.write_text(VORLAGE.format(marker=MARKER, schlaf=0.1,
                                    protokoll=str(self._tmp / "spuren.txt"),
                                    name="innen"), encoding="utf-8")
        try:
            env = dict(os.environ)
            env.update(LIGHTOS_SEG_OUT=str(self._tmp / "out2"),
                       LIGHTOS_WEBENGINE_LOCKFILE=str(self.sperre),
                       LIGHTOS_WEBENGINE_LOCK_HELD="1",
                       LIGHTOS_WEBENGINE_SPERRE_WARTE="5")
            erg = subprocess.run(["bash", str(SEG_RUNNER), "-j", "2", str(p)],
                                 cwd=str(REPO), env=env, capture_output=True,
                                 text=True, timeout=120)
        finally:
            _halter_abraeumen(halter)
        self.assertEqual(0, erg.returncode, erg.stdout)
        self.assertNotIn(
            "bekamen die Sperre nicht", erg.stdout,
            "Der innere Lauf hat auf die Sperre seines eigenen Elternlaufs "
            f"gewartet — im echten Gate steht damit alles still:\n{erg.stdout}")


@unittest.skipUnless(_LAEUFT, _GRUND)
class GezielterLaufGibtDieSperreEbensoFreiTest(unittest.TestCase):
    """★★ Dieselben Zusicherungen wie oben — nur fuer ``verify_loop.sh``.

    Nachtrag 2026-08-19. Die erste Fassung von PROC-02c hat beide
    Selbstbefreiungs-Wege NUR am Segment-Runner gemessen. Das ist die falsche
    Haelfte: der Befund des Items lautet ja gerade, dass **Agenten fast
    ausschliesslich gezielte Einzellaeufe fahren** — der Weg durch
    ``verify_loop.sh`` ist der haeufigere, nicht der seltenere.

    Nachgemessen an der damaligen Arbeitsfassung, beide Mutationen blieben
    GRUEN (19 Tests, 46 s):

      * ``8>&-`` aus der pytest-Zeile entfernt  -> alles gruen
      * ``webengine_warte_auf_kinder`` entfernt -> alles gruen

    Dieselben Mutationen im Segment-Runner sind rot. Die Luecke sass also
    genau dort, wo die Zusage am meisten wiegt.
    """

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="proc02c_loopfrei_"))
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)
        self.sperre = self._tmp / ".webengine_lock"
        self.sperre.touch()

    def _sperre_frei(self):
        return subprocess.run(["flock", "-n", str(self.sperre), "true"]).returncode == 0

    def _starte(self, datei, timeout=200, **extra):
        env = _umgebung(LIGHTOS_WEBENGINE_LOCKFILE=str(self.sperre),
                        LIGHTOS_SHOW_DB=str(self._tmp / "kind.db"), **extra)
        # ★ Eigene Sitzung: damit ist die Prozessgruppe des Laufs genau seine
        # eigene. Ohne das erbte er die Gruppe DIESES pytest-Prozesses, und die
        # Positivkontrolle unten haenge davon ab, was im Gate sonst noch in
        # derselben Gruppe steckt — eine Lastfalle, und ausgerechnet in diesem
        # Item die falsche Antwort.
        return subprocess.run([str(LOOP_RUNNER), str(datei)], cwd=str(REPO),
                              env=env, capture_output=True, text=True,
                              timeout=timeout, start_new_session=True)

    def test_ein_ueberlebender_enkel_haelt_die_sperre_des_einzellaufs_nicht_fest(self):
        """★ Der teuerste denkbare Fehler — hier auf dem Weg, den Agenten fahren.

        ``flock`` loest erst, wenn die LETZTE Kopie des Deskriptors zu ist. Erbt
        ein Chromium-Kind ihn und ueberlebt den Lauf, bliebe die Sperre
        RECHNERWEIT haengen: jeder kuenftige WebEngine-Lauf wartet dann 15
        Minuten und laeuft danach ungesperrt.
        """
        pidfile = self._tmp / "enkel.pid"
        p = self._tmp / "test_enkel.py"
        p.write_text(MARKER + f'''
import subprocess

def test_spur():
    k = subprocess.Popen(["sleep", "300"], start_new_session=True, close_fds=False)
    open({str(pidfile)!r}, "w").write(str(k.pid))
''', encoding="utf-8")
        erg = self._starte(p)
        enkel = int(pidfile.read_text(encoding="utf-8")) if pidfile.exists() else 0
        try:
            self.assertEqual(0, erg.returncode, erg.stdout[-3000:])
            self.assertTrue(enkel and _lebt(enkel),
                            "Der ueberlebende Enkel war schon tot — die "
                            "Pruefung waere nichtssagend gewesen.")
            self.assertTrue(
                self._sperre_frei(),
                "Nach dem gezielten Lauf haelt noch jemand die WebEngine-"
                "Sperre — ein geerbter Deskriptor in einem ueberlebenden Kind. "
                "Ab jetzt wartet jeder WebEngine-Lauf auf diesem Rechner ins "
                "Leere, und zwar rechnerweit.")
        finally:
            if enkel:
                try:
                    os.kill(enkel, 9)
                except ProcessLookupError:
                    pass

    def test_der_einzellauf_wartet_auf_seine_eigenen_kinder(self):
        """Die Einbaustelle: erst warten, dann freigeben.

        Nachgestellt mit einem Prozess, der den Namen traegt, auf den der Runner
        prueft (``QtWebEngineProc``), und der den Lauf ueberlebt — er bleibt in
        dessen Prozessgruppe, weil er NICHT abgekoppelt gestartet wird. Genau so
        verhalten sich Chromiums Hilfsprozesse.
        """
        fake = self._tmp / "QtWebEngineProc"      # comm: genau 15 Zeichen
        shutil.copy2("/bin/sleep", fake)
        pidfile = self._tmp / "fake.pid"
        p = self._tmp / "test_langlebig.py"
        p.write_text(MARKER + f'''
import subprocess

def test_spur():
    k = subprocess.Popen([{str(fake)!r}, "300"])
    open({str(pidfile)!r}, "w").write(str(k.pid))
''', encoding="utf-8")
        erg = self._starte(p, LIGHTOS_WEBENGINE_KIND_DECKEL="0.5")
        fake_pid = int(pidfile.read_text(encoding="utf-8")) if pidfile.exists() else 0
        try:
            self.assertEqual(0, erg.returncode, erg.stdout[-3000:])
            self.assertIn(
                "EIGENE Chromium-Kinder", erg.stdout,
                "Der gezielte Lauf hat die Sperre freigegeben, ohne auf seine "
                f"eigenen Kinder zu sehen:\n{erg.stdout[-3000:]}")
        finally:
            if fake_pid:
                try:
                    os.kill(fake_pid, 9)
                except ProcessLookupError:
                    pass

    def test_ein_gewoehnlicher_einzellauf_meldet_keine_uebrigen_kinder(self):
        """★ Positivkontrolle. Schlaegt die Meldung im Normalfall an, wartet
        jeder gezielte WebEngine-Lauf wieder auf etwas, das es nicht gibt —
        genau der Zustand vor PROC-02c."""
        p = self._tmp / "test_normal.py"
        p.write_text(VORLAGE.format(marker=MARKER, schlaf=0.1,
                                    protokoll=str(self._tmp / "spuren.txt"),
                                    name="normal"), encoding="utf-8")
        erg = self._starte(p, LIGHTOS_WEBENGINE_KIND_DECKEL="0.5")
        self.assertEqual(0, erg.returncode, erg.stdout[-3000:])
        self.assertNotIn("EIGENE Chromium-Kinder", erg.stdout, erg.stdout[-3000:])

    def test_der_gezielte_lauf_behaelt_sein_terminal(self):
        """★★ Was die Sperre fuer ALLES kaputtmacht, was nicht dieses Item ist.

        Die erste Fassung startete pytest mit ``&`` — nur, um ueber ``$!`` an
        die Prozessgruppe zu kommen. Gemessen 2026-08-19: das bringt hier gar
        nichts (ein Hintergrundjob einer nicht-interaktiven Shell BLEIBT in der
        Gruppe des Skripts — Skript 7346, Kind 7346; nur das ``timeout`` des
        Segment-Runners legt eine eigene an, 7356). Es kostet aber die
        Standardeingabe: bei einem asynchronen Befehl legt die Shell fd 0 auf
        /dev/null. Unter echtem Terminal gemessen — mit ``&`` meldete
        ``pytest -s`` fd 0 als ``/dev/null``, ohne als ``/dev/pts/1``.

        Damit waren ``--pdb``, ``breakpoint()`` und ``--trace`` in JEDEM
        gezielten Lauf tot, auch in den 95 % ohne WebEngine. Bewusst mit einer
        HARMLOSEN Datei gemessen: die Zusicherung haengt nicht an der Sperre.
        """
        import pty
        ziel = self._tmp / "fd0.txt"
        p = self._tmp / "test_terminal.py"
        p.write_text(HARMLOS + f'''
import os

def test_spur():
    try:
        wohin = os.readlink("/proc/self/fd/0")
    except OSError:
        wohin = "<kein fd 0>"
    open({str(ziel)!r}, "w").write(wohin)
''', encoding="utf-8")
        env = _umgebung(LIGHTOS_WEBENGINE_LOCKFILE=str(self.sperre),
                        LIGHTOS_SHOW_DB=str(self._tmp / "kind.db"))
        haupt, neben = pty.openpty()
        try:
            proc = subprocess.Popen(
                [str(LOOP_RUNNER), str(p), "-s"], cwd=str(REPO), env=env,
                stdin=neben, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True)
            os.close(neben)
            neben = None
            aus = proc.communicate(timeout=200)[0]
        finally:
            if neben is not None:
                os.close(neben)
            os.close(haupt)
        self.assertEqual(0, proc.returncode, aus[-3000:])
        wohin = ziel.read_text(encoding="utf-8")
        self.assertTrue(
            wohin.startswith("/dev/pts/"),
            "Der gezielte Lauf hat pytest sein Terminal genommen "
            f"(fd 0 -> {wohin!r}). Damit sind --pdb, breakpoint() und --trace "
            "in jedem gezielten Lauf tot — auch in denen ohne WebEngine.")


@unittest.skipUnless(_LAEUFT, _GRUND)
class SperreGiltUeberWorktreeGrenzenTest(unittest.TestCase):
    """★★ Die Zusage, an der die ganze Sache haengt: „rechnerweit, ueber
    Worktrees und Sitzungen hinweg."

    Nachtrag 2026-08-19. Bis hierhin setzte JEDER Test dieser Datei
    ``LIGHTOS_WEBENGINE_LOCKFILE`` — der Zweig, der die Sperrdatei wirklich
    bestimmt (``git rev-parse --git-common-dir``), wurde damit von keiner
    Messung beruehrt. Nachgemessen: ihn auf ``$(pwd)/.webengine_lock``
    umzustellen — also **exakt der Fehler von PROC-02b, eine eigene Sperrdatei
    je Worktree** — liess alle 35 Gate-Tests gruen.

    Der Fehler ist dort teuer: Agenten arbeiten in verschachtelten Worktrees
    unter ``repo/.claude/worktrees/``. Eine Sperre je Worktree greift genau
    dort nicht, wo tatsaechlich parallel gearbeitet wird.

    Gemessen wird zweifach — der gemeldete Pfad UND seine Wirkung. Der Pfad
    allein waere nur eine Zeichenkette; die Wirkung allein sagte nicht, dass
    beide Worktrees dieselbe Datei meinen.

    ⚠️ Und zwar an einem WEGWERF-Repo, nicht am eigenen. Zwei Gruende, beide
    hart:

      * Diese Datei laeuft im Gate selbst als WebEngine-Segment — der
        Segment-Runner HAELT dann die echte rechnerweite Sperre. Ein Test, der
        sie zum Messen selbst nehmen will, bekaeme sie nie und muesste sich
        wegskippen: im Gate waere er also immer stumm.
      * Ein Halter, der die echte Sperrdatei ueberlebt, legt jeden
        WebEngine-Lauf auf diesem Rechner lahm (s. ``_halte_sperre``).

    Das Wegwerf-Repo hat dieselbe Struktur, die es hier braucht — ein
    ``.git``-Verzeichnis mit Worktrees — und ist von nichts anderem beruehrt.
    """

    def setUp(self):
        if not shutil.which("git"):
            self.skipTest("kein git")
        self._tmp = Path(tempfile.mkdtemp(prefix="proc02c_wt_"))
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)
        self.basis = self._tmp / "repo"
        self.basis.mkdir()
        self._git("init", "-q")
        (self.basis / "README").write_text("wegwerf\n", encoding="utf-8")
        self._git("add", "README")
        self._git("-c", "user.email=t@t", "-c", "user.name=T", "commit", "-qm", "start")

    def _git(self, *args):
        erg = subprocess.run(["git", *args], cwd=str(self.basis),
                             capture_output=True, text=True, timeout=120)
        if erg.returncode != 0:
            self.skipTest(f"git {args[0]} ging nicht: {erg.stderr[:200]}")
        return erg

    def _worktree(self, ziel):
        """Ein echter Worktree des Wegwerf-Repos mit den ARBEITSfassungen.

        Kopiert werden die beiden Dateien, die zusammen die Sperre bestimmen —
        ``verify_loop.sh`` und ``_gate_webengine.sh``. Wer nur eine kopiert,
        misst eine Arbeitsfassung gegen einen committeten Helfer: die Paarung
        gibt es nirgends (die Lehre steht schon in test_verify_loop_sperre.py).
        """
        ziel.parent.mkdir(parents=True, exist_ok=True)
        self._git("worktree", "add", "-q", "--detach", str(ziel), "HEAD")
        (ziel / "tools").mkdir(exist_ok=True)
        (ziel / "src").mkdir(exist_ok=True)
        for datei in ("verify_loop.sh", "_gate_webengine.sh"):
            shutil.copy2(REPO / "tools" / datei, ziel / "tools" / datei)
        os.symlink(REPO / "venv", ziel / "venv")
        return ziel

    def _gemeldeter_pfad(self, wurzel, **extra):
        env = _umgebung(LIGHTOS_VERIFY_DRYRUN="1", LIGHTOS_VERIFY_NOLOCK="1")
        env.pop("LIGHTOS_WEBENGINE_LOCKFILE", None)
        env.update(extra)
        r = subprocess.run(["bash", str(wurzel / "tools" / "verify_loop.sh")],
                           cwd=str(wurzel), env=env, capture_output=True,
                           text=True, timeout=300)
        for zeile in r.stdout.splitlines():
            if zeile.startswith("[verify] WebEngine-Sperrdatei:"):
                return zeile.split(":", 1)[1].strip()
        self.fail(f"keine WebEngine-Sperrdatei-Zeile:\n{r.stdout}\n{r.stderr}")

    def _webengine_lauf(self, wurzel, **extra):
        datei = wurzel / "test_wt_web.py"
        datei.write_text(MARKER + "\n\ndef test_spur():\n    assert True\n",
                         encoding="utf-8")
        env = _umgebung(LIGHTOS_SHOW_DB=str(self._tmp / f"{wurzel.name}.db"))
        env.pop("LIGHTOS_WEBENGINE_LOCKFILE", None)
        env.update(extra)
        return subprocess.run([str(wurzel / "tools" / "verify_loop.sh"), str(datei)],
                              cwd=str(wurzel), env=env, capture_output=True,
                              text=True, timeout=300)

    def test_verschachtelter_und_geschwister_worktree_teilen_die_sperre(self):
        # Die beiden Lagen aus PROC-02b: einmal Geschwister von `repo/`, einmal
        # UNTER `repo/.claude/worktrees/` — die Lage, in der Agenten arbeiten.
        geschwister = self._worktree(self._tmp / "wt-geschwister")
        tief = self._worktree(self.basis / ".claude" / "worktrees" / "wf-tief")
        a = self._gemeldeter_pfad(geschwister)
        b = self._gemeldeter_pfad(tief)
        self.assertEqual(
            a, b,
            "Zwei Worktrees desselben Repos melden VERSCHIEDENE "
            "WebEngine-Sperrdateien — dann serialisiert die Sperre genau dort "
            "nicht, wo parallel gearbeitet wird (PROC-02b, dieselbe Falle).")

        # ★ Und der gemeldete Pfad ist auch der, auf dem wirklich gesperrt wird:
        # ein Fremder haelt ihn, ein Lauf im ANDEREN Worktree kommt nicht daran.
        halter = _halte_sperre(a)
        try:
            erg = self._webengine_lauf(tief, LIGHTOS_WEBENGINE_SPERRE_WARTE="1")
        finally:
            _halter_abraeumen(halter)
        self.assertEqual(0, erg.returncode, erg.stdout[-3000:])
        self.assertIn(
            "UNGESPERRT", erg.stdout.upper(),
            "Ein WebEngine-Lauf im verschachtelten Worktree lief los, obwohl "
            "die gemeinsame Sperre gehalten wurde — die gemeldete Datei ist "
            f"nicht die, auf der gesperrt wird:\n{erg.stdout[-3000:]}")

    def test_die_messung_saehe_zwei_verschiedene_sperren_auch(self):
        """★ Positivkontrolle in beide Richtungen.

        (1) Die Pfadmessung darf nicht blind Gleichheit bestaetigen — mit
        gesetzter Sperrdatei muss sie einen Unterschied sehen.
        (2) Die Wirkungsmessung darf nicht blind blockieren — wird eine ANDERE
        Datei gehalten, muss derselbe Lauf durchlaufen. Ohne (2) waere der Test
        oben auch dann gruen, wenn der Lauf aus irgendeinem anderen Grund
        UNGESPERRT meldete.
        """
        wt = self._worktree(self._tmp / "wt-kontrolle")
        eins = self._gemeldeter_pfad(
            wt, LIGHTOS_WEBENGINE_LOCKFILE=str(self._tmp / "eins.lock"))
        zwei = self._gemeldeter_pfad(
            wt, LIGHTOS_WEBENGINE_LOCKFILE=str(self._tmp / "zwei.lock"))
        self.assertNotEqual(eins, zwei,
                            "Die Pfadmessung kann gar nicht unterscheiden.")

        fremd = self._tmp / "fremde.lock"
        fremd.touch()
        halter = _halte_sperre(fremd)
        try:
            erg = self._webengine_lauf(wt, LIGHTOS_WEBENGINE_SPERRE_WARTE="1")
        finally:
            _halter_abraeumen(halter)
        self.assertEqual(0, erg.returncode, erg.stdout[-3000:])
        self.assertNotIn(
            "UNGESPERRT", erg.stdout.upper(),
            "Der Lauf meldete UNGESPERRT, obwohl eine ganz FREMDE Datei "
            f"gehalten wurde:\n{erg.stdout[-3000:]}")

@unittest.skipUnless(_LAEUFT and HELFER.exists(), _GRUND)
class WartenAufEigeneKinderTest(unittest.TestCase):
    """Das Warten muss die EIGENE Prozessgruppe treffen — und nur die.

    Hier laufen ECHTE ``QtWebEngineProc``-Prozesse: ein realer pytest-Lauf auf
    einer realen Szenendatei wird gestartet und waehrend seiner Laufzeit
    befragt. Eine nachgebaute Attrappe wuerde genau die Frage offen lassen, um
    die es geht — ob die Zuordnung ueber die Prozessgruppe an echten
    Chromium-Kindern haelt.
    """

    SZENE = "tests/test_viz14_labels_scene.py"

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="proc02c_kind_"))
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)

    def _frage_helfer(self, pgid, deckel="0.5"):
        """Ruft die ECHTE Funktion aus tools/_gate_webengine.sh auf."""
        skript = (f'. "{HELFER}"; LIGHTOS_WEBENGINE_KIND_DECKEL={deckel} '
                  f'webengine_warte_auf_kinder {pgid}; echo "rc=$?"')
        t0 = time.monotonic()
        erg = subprocess.run(["bash", "-c", skript], cwd=str(REPO),
                             capture_output=True, text=True, timeout=60)
        return erg.stdout.strip(), time.monotonic() - t0

    def test_eigene_kinder_halten_das_warten_auf_fremde_nicht(self):
        py = REPO / "venv" / "bin" / "python"
        if not py.exists():
            self.skipTest("kein venv-Python")
        env = _umgebung(QT_QPA_PLATFORM="offscreen", LIGHTOS_HARDEN_EXIT="1")
        # Eigene Sitzung -> die Prozessgruppe ist deterministisch die PID des
        # Kindes; genau so, wie `timeout` sie im Runner anlegt. Die
        # Chromium-Kinder erben sie und behalten sie auch dann, wenn ihr
        # Elternprozess stirbt und sie an init umgehaengt werden.
        proc = subprocess.Popen(
            ["timeout", "120", str(py), "-m", "pytest", self.SZENE, "-q",
             "--tb=no", "-p", "no:cacheprovider"],
            cwd=str(REPO), env=env, start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pgid = proc.pid
        try:
            # warten, bis echte Kinder da sind
            for _ in range(600):
                r = subprocess.run(["pgrep", "-u", str(os.getuid()), "-g", str(pgid),
                                    "-x", "QtWebEngineProc"], capture_output=True)
                if r.returncode == 0:
                    break
                if proc.poll() is not None:
                    self.skipTest("Segment war fertig, bevor Kinder sichtbar wurden")
                time.sleep(0.1)
            else:
                self.skipTest("keine QtWebEngineProc-Kinder beobachtet")

            # ⚠️ Bewertet wird der Rueckgabewert, nicht die verstrichene Zeit:
            # rc=1 heisst „Deckel erreicht", also wurde gewartet; rc=0 heisst
            # „nichts gefunden". Eine Zeitschwelle waere hier nur eine weitere
            # Lastabhaengigkeit — und Lastabhaengigkeit ist das Thema dieses
            # Items, nicht sein Werkzeug.
            eigen, _ = self._frage_helfer(pgid)
            self.assertIn("rc=1", eigen,
                          "Die eigenen, LEBENDEN Chromium-Kinder wurden nicht "
                          f"erkannt — die Zuordnung greift nicht: {eigen}")

            # ★ Der eigentliche PROC-02c-Befund: ein FREMDER Lauf darf uns nicht
            # aufhalten. Dieselben echten Kinder, nur aus einer anderen
            # Prozessgruppe befragt.
            fremd_pgid = os.getpgid(0)
            fremd, _ = self._frage_helfer(fremd_pgid)
            self.assertIn("rc=0", fremd,
                          "Fremde Chromium-Kinder halten das Warten weiter auf — "
                          "das ist genau der Zustand, in dem 25 von 41 "
                          f"WebEngine-Segmenten in den Deckel liefen: {fremd}")
        finally:
            import signal
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=60)

    def test_ohne_kinder_wird_nicht_gewartet(self):
        """★ Positivkontrolle: im Normalfall kostet das Warten nichts.

        Gemessen ueber 41 WebEngine-Dateien war die eigene Prozessgruppe beim
        ersten Nachsehen bereits leer (spaetestens 0,037 s). Schlaegt diese
        Pruefung an, wartet das Gate 41-mal je Lauf auf etwas, das es gar nicht
        gibt — der Zustand vor PROC-02c.
        """
        leer, dauer = self._frage_helfer(999999, deckel="30.0")
        self.assertIn("rc=0", leer, leer)
        # Grosszuegig: der Deckel steht auf 30 s, gemessen wird der ganze
        # Unterprozess. Wer trotzdem darueber stolpert, wartet wirklich —
        # eine engere Schwelle waere nur eine Lastfalle.
        self.assertLess(dauer, 10.0,
                        f"Ohne eigene Kinder wurde trotzdem gewartet ({dauer:.2f}s).")


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
