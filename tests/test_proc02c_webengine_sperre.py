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
                    mit.kill()
                    mit.wait(timeout=60)
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
        halter = subprocess.Popen(
            ["flock", str(self.sperre), "sleep", "600"], start_new_session=True)
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
            halter.kill()
            halter.wait(timeout=60)
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
            halter.kill()
            halter.wait(timeout=60)
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
        halter = subprocess.Popen(
            ["flock", str(self.sperre), "sleep", "600"], start_new_session=True)
        try:
            erg = self._lauf(HARMLOS, LIGHTOS_WEBENGINE_SPERRE_WARTE="1")
        finally:
            halter.kill()
            halter.wait(timeout=60)
        self.assertEqual(0, erg.returncode, erg.stdout[-3000:])
        self.assertEqual(1, len(_lies_protokoll(self.protokoll)))
        for satz in ("WebEngine-Sperre war belegt", "Sperre nicht bekommen"):
            self.assertNotIn(
                satz, erg.stdout,
                "Ein Lauf ohne WebEngine-Datei hat die WebEngine-Sperre "
                f"angefasst — sie greift zu weit:\n{erg.stdout[-3000:]}")


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
        halter = subprocess.Popen(
            ["flock", str(self.sperre), "sleep", "600"], start_new_session=True)
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
            halter.kill()
            halter.wait(timeout=60)
        self.assertEqual(0, erg.returncode, erg.stdout)
        self.assertNotIn(
            "bekamen die Sperre nicht", erg.stdout,
            "Der innere Lauf hat auf die Sperre seines eigenen Elternlaufs "
            f"gewartet — im echten Gate steht damit alles still:\n{erg.stdout}")


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
