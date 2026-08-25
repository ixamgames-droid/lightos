"""QA-63 — der Waechter gegen Zeitbomben, und der Beweis, dass er taugt.

Eine Zeitbombe ist ein Test mit festem Datum, der gegen eine Schwelle geprueft
wird, die an HEUTE haengt. Er wird irgendwann rot, **ohne dass jemand etwas
aendert** — und der Fehlschlag gehoert zu keinem Commit. Genau das hat am
22.08.2026 ``main`` rot gemacht (QA-62): ein reiner BACKLOG-PR fiel durch wie
ein Feature-PR, und niemand konnte den Fehler seinen eigenen Aenderungen
zuordnen, weil er dort nicht war.

★★ **Die eigentliche Arbeit steckt in der Positivkontrolle.** Neun der 615
Testdateien tragen feste Daten ausserhalb von Docstrings (gemessen 22.08.2026;
mit dieser Datei zehn von 616), und alle sind gesund. Ein Gate, das sie
beanstandet, wird nach dem zweiten Fehlalarm abgeschaltet — und ist dann
schlechter als keines. Diese Datei belegt deshalb BEIDES an fahrenden Laeufen:

* eine frisch gebaute Zeitbombe wird gefunden (``ProbenTest``),
* dieselbe Datei mit demselben festen Datum, nur ohne Kopplung an eine
  gleitende Schwelle, wird NICHT beanstandet — ebenso wenig die echten
  Dateien im Repo (``ProbenTest``, ``RepoTest``).

★ **Und die Frage, an der Waechter hier reihenweise gescheitert sind:** stammt
das, was der Test setzt, im Betrieb aus einer anderen Quelle? Der Uhr-Sprung
kommt hier wie im Betrieb aus ``tools/zeitbomben_gate.sprung_umgebung`` — die
Tests bauen ihn nicht selbst nach. Was sie zusaetzlich pruefen, ist der
gefaehrlichste Ausfall ueberhaupt: ein Vorspann, der still NICHT greift, machte
aus dem Waechter einen Ja-Sager (alles gruen, keine Bomben). ``KanarieTest``
misst, dass der Waechter in dem Fall abbricht statt „gruen" zu melden.
"""
import datetime
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import zeitbomben_gate as zg                    # noqa: E402

# Jeder dieser Tests faehrt echte pytest-Kindprozesse; 60 s (pytest.ini) reichen
# fuer den Repo-Lauf nicht, wenn nebenher drei Segmente laufen.
pytestmark = pytest.mark.timeout(600)

TESTS = os.path.join(REPO, "tests")

_KANDIDATEN_CACHE = []


def _kandidaten():
    """Der Scan ueber 616 Dateien kostet ~3 s — einmal je Prozess reicht."""
    if not _KANDIDATEN_CACHE:
        _KANDIDATEN_CACHE.extend(zg.kandidaten(TESTS))
    return list(_KANDIDATEN_CACHE)


#: Die sechs Dateien, die QA-62 am 22.08.2026 als „feste Daten, aber gesund"
#: gemessen hat. Sie sind hier der Massstab fuer Fehlalarme.
QA62_GESUND = [
    "test_audit_bilder_stand.py", "test_controller_library.py",
    "test_crash_logging.py", "test_doc_removed_ui.py",
    "test_session_claim.py", "test_show_format_upgrade.py",
]


class FesteDatenTest(unittest.TestCase):
    """Die statische Vorauswahl — grosszuegig, aber nicht wahllos."""

    def _funde(self, quelle):
        return [f.text for f in zg.feste_daten(quelle)]

    def test_iso_datum_in_einer_zeichenkette_wird_gefunden(self):
        self.assertEqual(self._funde('X = "2026-07-20"'), ["2026-07-20"])

    def test_datum_mit_angehaengter_uhrzeit_wird_gefunden(self):
        """★ Der Fehler der ersten Fassung, an einer echten Datei gemessen.

        Mit ``\\b`` am Musterende blieb ``"2026-05-27T00:00:00"`` unsichtbar —
        zwischen „7" und „T" steht keine Wortgrenze. Genau so steht das Datum
        in ``tests/test_show_format_upgrade.py``; die Datei fiel damit aus der
        Vorauswahl, obwohl QA-62 sie ausdruecklich genannt hatte.
        """
        self.assertEqual(self._funde('X = {"created": "2026-05-27T00:00:00"}'),
                         ["2026-05-27"])

    def test_deutsche_schreibweise_wird_gefunden(self):
        """Kommt im Repo genau einmal vor (``test_audit_bilder_stand.py:72``,
        gemessen 2026-08-22) — die Datei ist ueber ihre ISO-Daten ohnehin
        Kandidat. Die Form kostet heute also nichts und schliesst trotzdem eine
        Luecke, die morgen etwas kosten koennte."""
        self.assertEqual(self._funde('X = "17.07.2026"'), ["17.07.2026"])
        self.assertEqual(self._funde('V = "1.2.2026"'), [],
                         "Versionsnummern sind keine Daten")

    def test_datetime_konstruktor_mit_festen_zahlen_wird_gefunden(self):
        """``datetime(2026, 8, 6, 14, 0)`` ist dasselbe feste Datum in anderer
        Schreibweise — so steht es in ``test_session_claim`` und
        ``test_crash_logging``. Wer nur Zeichenketten kennt, sieht eine Datei
        mit ausschliesslich Konstruktoren gar nicht."""
        self.assertEqual(
            self._funde("import datetime\n"
                        "T = datetime.datetime(2026, 8, 6, 14, 0)"),
            ["datetime(2026, 8, 6)"])
        self.assertEqual(self._funde("from datetime import date\n"
                                     "T = date(2026, 8, 6)"),
                         ["date(2026, 8, 6)"])

    def test_docstring_datum_ist_kein_fund(self):
        """★ Der Unterschied zwischen brauchbar und unbenutzbar, gemessen:
        MIT Docstrings tragen 143 von 615 Testdateien ein Datum, OHNE neun.
        Ein Datum in Prosa kann an keinem Vergleich teilnehmen."""
        quelle = ('"""Modul, Stand 2026-06-30."""\n'
                  'class A:\n'
                  '    """Klasse seit 2026-06-30."""\n'
                  '    def f(self):\n'
                  '        """Entfernt am 2026-06-30."""\n'
                  '        return 1\n')
        self.assertEqual(self._funde(quelle), [])

    def test_kommentar_datum_ist_kein_fund(self):
        self.assertEqual(self._funde("# gemessen 2026-08-22\nX = 1"), [])

    def test_ein_am_lauftag_gerechnetes_datum_ist_kein_fund(self):
        """Das ist die REPARATUR aus QA-62 — der Waechter darf sie nicht
        beanstanden, sonst treibt er zurueck in die Zeitbombe."""
        quelle = ("import datetime as d\n"
                  "ALT = (d.datetime.now() - d.timedelta(days=200))"
                  ".strftime('%Y-%m-%dT%H:%M:%S')\n")
        self.assertEqual(self._funde(quelle), [])

    def test_zeile_und_text_zeigen_auf_den_fund(self):
        funde = zg.feste_daten('A = 1\nB = "2026-07-20"\n')
        self.assertEqual([(f.zeile, f.text) for f in funde],
                         [(2, "2026-07-20")])

    def test_die_vorauswahl_im_repo_ist_klein_und_enthaelt_die_sechs(self):
        """Messung statt Behauptung: die Vorauswahl muss die von QA-62
        genannten Dateien treffen UND darf nicht die halbe Suite umfassen —
        sonst faehrt das Gate die Suite ein zweites Mal."""
        alle = zg.testdateien(TESTS)
        kand = [os.path.basename(p) for p, _ in _kandidaten()]
        fehlend = [n for n in QA62_GESUND if n not in kand]
        self.assertEqual(fehlend, [],
                         "QA-62 hat diese Dateien als traeger fester Daten "
                         "gemessen — die Vorauswahl muss sie sehen")
        self.assertLess(len(kand), len(alle) // 10,
                        f"{len(kand)} von {len(alle)} Testdateien in der "
                        "Vorauswahl — das ist keine Vorauswahl mehr")
        self.assertGreaterEqual(len(alle), 500,
                                "die Suite wurde nicht gefunden — dann sagt "
                                "die Verhaeltniszahl oben nichts")

    def test_der_waechter_nimmt_genau_sich_selbst_aus(self):
        """★ Diese Datei FAEHRT den Waechter. Liefe sie in einem Waechter-Lauf
        mit, startete sie darin den naechsten — unbegrenzt tief; genau die
        Selbstverstrickung, die ``tests/test_session_claim.py`` schon einmal
        erwischt hat („das Gate fand sich selbst").

        Der Test haelt beides fest: dass die Ausnahme noetig ist (die Datei IST
        Kandidat, sie traegt feste Daten als Scanner-Eingabe) und dass sie nicht
        stillschweigend mehr ausnimmt.
        """
        kand = _kandidaten()
        selbst = os.path.abspath(__file__)
        self.assertIn(selbst, [p for p, _ in kand],
                      "diese Datei traegt feste Daten — waere sie kein "
                      "Kandidat, waere die Ausnahme wirkungslos und der Test "
                      "hier bloss Deko")
        gefahren = zg.zu_fahren(kand)
        self.assertNotIn(selbst, gefahren)
        ausgenommen = sorted(set(p for p, _ in kand) - set(gefahren))
        self.assertEqual([os.path.basename(p) for p in ausgenommen],
                         ["test_zeitbomben_gate.py"],
                         "es darf GENAU diese eine Ausnahme geben")


class UhrVorspannTest(unittest.TestCase):
    """Der Uhr-Vorspann selbst — am echten Kindprozess, nicht am Quelltext."""

    ABFRAGE = ("import datetime, time;"
               "print(datetime.date.today().isoformat(),"
               "datetime.datetime.now().date().isoformat(),"
               "datetime.date.fromtimestamp(time.time()).isoformat(),"
               "time.strftime('%Y-%m-%d', time.localtime()))")

    def _uhren(self, tage, uhr=zg.SPRUNG_UHR):
        """{Quelle: gesehenes Datum} aus einem echten Kindprozess."""
        env = zg.sprung_umgebung(tage, uhr=uhr)
        fertig = subprocess.run([sys.executable, "-c", self.ABFRAGE],
                                cwd=REPO, env=env, text=True,
                                capture_output=True, timeout=120)
        self.assertEqual(fertig.returncode, 0, fertig.stderr)
        werte = [datetime.date.fromisoformat(w)
                 for w in fertig.stdout.split()]
        return dict(zip(("date.today", "datetime.now", "time.time",
                         "localtime"), werte))

    def _soll(self, tage):
        return zg.echt_heute() + datetime.timedelta(days=tage)

    def test_datum_und_datetime_stehen_um_denselben_betrag_vorn(self):
        """★ Die Falle beim Bauen, gemessen: ``date.today()`` ist in CPython
        NICHT unabhaengig von ``time.time`` — es ruft das ``time``-Modul auf.
        Eine Fassung, die beides um denselben Betrag verschob, lieferte
        ``date.today()`` DOPPELT verschoben (bei +400 Tagen 2028-10-30 statt
        2027-09-26). Eine halb verschobene Uhr macht das Gate unbrauchbar,
        ohne dass es auffaellt — deshalb wird JEDE Quelle einzeln gemessen."""
        soll = self._soll(zg.SPRUNG_TAGE)
        uhren = self._uhren(zg.SPRUNG_TAGE)
        for quelle in ("date.today", "datetime.now"):
            self.assertLessEqual(
                abs((uhren[quelle] - soll).days), 1,
                f"{quelle} zeigt {uhren[quelle]} statt {soll}")

    def test_in_der_vorgabe_bleibt_time_time_echt(self):
        """★★ Die gemessene Entscheidung, keine Bequemlichkeit.

        ``st_mtime`` kommt aus der echten Uhr des Betriebssystems und laesst
        sich nicht mitverschieben. Wer „wie alt ist diese Datei" als
        ``time.time() - st_mtime`` rechnet, sieht mit verschobener ``time.time``
        jede eben geschriebene Datei zehn Jahre alt. Gemessen 2026-08-22 ueber
        die ganze Suite: das macht DREI gesunde Dateien rot
        (``test_vc_asset_gc``, ``test_janitor``, ``test_qa58_bibliothek_...``)
        und bringt NULL zusaetzliche Funde. Drei Fehlalarme gegen null Treffer
        — das Gate faehrt deshalb ``datum``.
        """
        heute = zg.echt_heute()
        uhren = self._uhren(zg.SPRUNG_TAGE, uhr="datum")
        for quelle in ("time.time", "localtime"):
            self.assertLessEqual(
                abs((uhren[quelle] - heute).days), 1,
                f"{quelle} wurde mitverschoben ({uhren[quelle]}) — damit "
                "werden gesunde Dateialter-Tests rot")

    def test_staerke_alle_zieht_time_time_ausdruecklich_mit(self):
        """Die andere Staerke gibt es fuer den bewussten Streifzug
        (``--uhr alle``) — sie muss dann auch wirklich mehr verschieben,
        sonst waere der Schalter eine Attrappe."""
        soll = self._soll(zg.SPRUNG_TAGE)
        uhren = self._uhren(zg.SPRUNG_TAGE, uhr="alle")
        for quelle in ("date.today", "datetime.now", "time.time", "localtime"):
            self.assertLessEqual(
                abs((uhren[quelle] - soll).days), 1,
                f"{quelle} zeigt {uhren[quelle]} statt {soll}")

    def test_ohne_sprung_bleibt_jede_uhr_stehen(self):
        """Die Gegenprobe: derselbe Weg, nur ``tage=0``. Ohne sie bewiesen die
        Tests oben nur, dass IRGENDETWAS ein Datum liefert."""
        heute = zg.echt_heute()
        for quelle, gesehen in self._uhren(0).items():
            self.assertLessEqual(
                abs((gesehen - heute).days), 1,
                f"{quelle}: {gesehen} — ohne Sprung darf sich nichts "
                "verschieben")

    def test_monotonic_wird_in_keiner_staerke_angefasst(self):
        """Zeitspannen-Uhren bleiben echt: ``pytest-timeout``, Qt-Timer und
        jedes ``perf_counter``-Mass haengen daran.

        ★ Gemessen wird der ABSOLUTE Stand, nicht eine Differenz — der erste
        Anlauf verglich ``monotonic()`` vor und nach einem ``sleep`` und blieb
        deshalb auch dann gruen, als die Mutante ``monotonic`` um zehn Jahre
        verschob: ein konstanter Versatz kuerzt sich aus jeder Differenz heraus.
        ``CLOCK_MONOTONIC`` zaehlt seit dem Systemstart und ist damit ueber
        Prozessgrenzen hinweg vergleichbar.
        """
        import time as _t
        for uhr in ("datum", "alle"):
            env = zg.sprung_umgebung(zg.SPRUNG_TAGE, uhr=uhr)
            hier = _t.monotonic()
            fertig = subprocess.run(
                [sys.executable, "-c", "import time;print(time.monotonic())"],
                cwd=REPO, env=env, text=True, capture_output=True, timeout=120)
            self.assertEqual(fertig.returncode, 0, fertig.stderr)
            dort = float(fertig.stdout.strip())
            self.assertLess(abs(dort - hier), 60,
                            f"uhr={uhr}: monotonic steht bei {dort} statt "
                            f"~{hier} — die Zeitspannen-Uhr wurde verschoben")


class KanarieTest(unittest.TestCase):
    """★ Der Selbstschutz: ein stiller Ausfall darf nicht wie „gruen" aussehen.

    Das ist die Fehlerklasse, an der in diesem Repo mehrere Waechter gescheitert
    sind (PROC-02b: eine Sperre, die stillschweigend nicht griff, liess das
    Ergebnis vertrauenswuerdig aussehen). Hier waere sie besonders billig zu
    uebersehen: ohne wirksamen Vorspann laeuft alles mit der echten Uhr, alles
    ist gruen, und der Waechter meldete „keine Zeitbomben".
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="zeitbomben_test_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.probe = zg.probe_schreiben(self.tmp, "bombe")

    def _halber_vorspann(self, sitecustomize: str = ""):
        """Ein Shim-Ordner MIT Kanarienvogel, aber mit kaputtem (oder ganz
        fehlendem) ``sitecustomize`` — das Plugin laeuft, der Vorspann nicht."""
        halb = tempfile.mkdtemp(prefix="zeitbomben_halb_")
        self.addCleanup(shutil.rmtree, halb, True)
        shutil.copy(os.path.join(zg.SHIM, "zeitsprung_kanarie.py"), halb)
        if sitecustomize:
            with open(os.path.join(halb, "sitecustomize.py"), "w",
                      encoding="utf-8") as fh:
                fh.write(sitecustomize)
        return halb

    def test_ein_wirksamer_sprung_meldet_sich_positiv(self):
        ergebnis = zg.lauf([self.probe], zg.SPRUNG_TAGE)
        self.assertIn(zg.MARKE_OK, ergebnis.ausgabe)
        self.assertTrue(ergebnis.sprung_wirksam)

    def test_ein_ausgefallener_vorspann_wird_bemerkt(self):
        ergebnis = zg.lauf([self.probe], zg.SPRUNG_TAGE,
                           shim=self._halber_vorspann())
        self.assertFalse(ergebnis.sprung_wirksam,
                         "der Vorspann war aus — das Ergebnis beweist nichts")
        self.assertIn(zg.MARKE_FEHLT, ergebnis.ausgabe)

    #: Ein Vorspann, der NUR ``datetime.datetime`` verschiebt und ``date``
    #: stehen laesst — genau die Halbheit, die beim Bauen als Erstes entsteht.
    HALB_VERSCHOBEN = (
        "import datetime as _dt, os\n"
        "_d = _dt.timedelta(days=int(os.environ['LIGHTOS_ZEITSPRUNG_TAGE']))\n"
        "_e = _dt.datetime\n"
        "class _X(_e):\n"
        "    @classmethod\n"
        "    def now(cls, tz=None):\n"
        "        return _e.now(tz) + _d\n"
        "_dt.datetime = _X\n")

    def test_ein_halb_verschobener_vorspann_wird_bemerkt(self):
        """★ Nicht nur „gar nicht" muss auffallen, sondern „nur zur Haelfte".

        ``date.today()`` und ``datetime.now()` haengen in CPython an
        VERSCHIEDENEN Quellen — die eine ueber das ``time``-Modul, die andere am
        C-Systemtakt. Ein Kanarienvogel, der nur eine davon abfragt, laesst die
        haeufigste Baustellen-Halbheit durch, und der Waechter misst dann Tests
        gegen eine Uhr, die teils steht.
        """
        halb = self._halber_vorspann(self.HALB_VERSCHOBEN)
        ergebnis = zg.lauf([self.probe], zg.SPRUNG_TAGE, shim=halb)
        self.assertFalse(ergebnis.sprung_wirksam)
        self.assertIn("date.today()", ergebnis.ausgabe,
                      "die Meldung muss die stehengebliebene Quelle nennen")

    def _stummer_vorspann(self):
        """Vorspann WIRKT, aber der Kanarienvogel schweigt — ein Plugin gleichen
        Namens, das nichts meldet. So sieht ein kaputtes oder verdraengtes
        Plugin von aussen aus."""
        stumm = tempfile.mkdtemp(prefix="zeitbomben_stumm_")
        self.addCleanup(shutil.rmtree, stumm, True)
        shutil.copy(os.path.join(zg.SHIM, "sitecustomize.py"), stumm)
        with open(os.path.join(stumm, "zeitsprung_kanarie.py"), "w",
                  encoding="utf-8") as fh:
            fh.write("def pytest_configure(config):\n    pass\n")
        return stumm

    def test_ein_stummer_kanarienvogel_macht_gruen_nicht_gueltig(self):
        """★★ Der Fall, in dem GENAU diese Pruefung noch traegt: der Lauf ist
        GRUEN, aber die Bestaetigung fehlt. Ein roter Lauf faellt ohnehin auf —
        ein gruener ohne Beleg ist die stille Variante, und die ist teurer.

        Gefahren wird die HARMLOSE Probe: sie bliebe auch mit wirksamem Sprung
        gruen, der Waechter darf daraus trotzdem kein „keine Zeitbombe" machen,
        solange der Beleg fehlt.
        """
        ordner = tempfile.mkdtemp(dir=self.tmp)
        harmlos = zg.probe_schreiben(ordner, "harmlos")
        stumm = self._stummer_vorspann()
        ergebnis = zg.lauf([harmlos], zg.SPRUNG_TAGE, shim=stumm)
        self.assertEqual(ergebnis.rc, 0,
                         "die harmlose Probe muss gruen sein — sonst misst "
                         "dieser Test den falschen Zweig")
        self.assertFalse(ergebnis.sprung_wirksam)
        with self.assertRaises(zg.SprungUnwirksam):
            zg.pruefe(ordner, dateien=[harmlos], shim=stumm)

    def test_ein_geerbter_vorspann_wird_nicht_hintenherum_wirksam(self):
        """★ Gemessen 2026-08-22, und nicht vorsorglich: laeuft der Waechter
        selbst unter dem dokumentierten Streifzug ueber die ganze Suite, steht
        der echte Vorspann bereits im geerbten ``PYTHONPATH``. Ein Kind, dem
        der Waechter absichtlich einen KAPUTTEN Vorspann mitgibt, fand ihn dann
        hintenherum doch — und drei Kanarienvogel-Tests wurden rot, ohne dass
        etwas kaputt war. Wer den Vorspann bestimmt, bestimmt ihn ganz.
        """
        vorher = os.environ.get("PYTHONPATH")
        gesetzt = zg.SHIM if not vorher else zg.SHIM + os.pathsep + vorher
        os.environ["PYTHONPATH"] = gesetzt
        try:
            ergebnis = zg.lauf([self.probe], zg.SPRUNG_TAGE,
                               shim=self._halber_vorspann())
        finally:
            if vorher is None:
                os.environ.pop("PYTHONPATH", None)
            else:
                os.environ["PYTHONPATH"] = vorher
        self.assertFalse(ergebnis.sprung_wirksam,
                         "der geerbte Vorspann hat den kaputten ueberstimmt")

    def test_der_waechter_bricht_ab_statt_gruen_zu_melden(self):
        """★★ Die entscheidende Zusage. Ohne Vorspann ist die Bombe gruen —
        der Waechter darf daraus NICHT „keine Zeitbombe" machen."""
        with self.assertRaises(zg.SprungUnwirksam):
            zg.pruefe(self.tmp, dateien=[self.probe],
                      shim=self._halber_vorspann())

    def test_ohne_kanarienvogel_waere_der_ausfall_gruen(self):
        """Die Messung, die zeigt, dass der Kanarienvogel etwas TUT: derselbe
        ausgefallene Vorspann, aber ohne Plugin — dann laeuft die Bombe durch
        und meldet 1 passed. Genau dieser Anblick waere die Falle."""
        env = zg.sprung_umgebung(zg.SPRUNG_TAGE, shim=tempfile.mkdtemp())
        env["LIGHTOS_SHOW_DB"] = os.path.join(self.tmp, "show.db")
        fertig = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             self.probe],
            cwd=REPO, env=env, text=True, capture_output=True, timeout=300)
        self.assertEqual(fertig.returncode, 0,
                         "ohne Vorspann muss die Bombe gruen sein — sonst "
                         "misst der Test daneben")
        self.assertNotIn(zg.MARKE_OK, fertig.stdout + fertig.stderr)


class ProbenTest(unittest.TestCase):
    """Negativ- und Positivkontrolle an frisch gepraegten Proben.

    Beide Proben tragen DASSELBE feste Datum (Lauftag minus drei Tage), rufen
    DASSELBE Produktionsmodul auf (``tools/collect_crash_report``). Der einzige
    Unterschied ist die Kopplung an ``_cold_before()`` — also genau die
    Verbindung, um die es geht. Damit misst dieses Paar den Waechter und nicht
    das Datum.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="zeitbomben_proben_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _probe(self, art):
        ordner = tempfile.mkdtemp(dir=self.tmp)
        return zg.probe_schreiben(ordner, art), ordner

    def test_die_gebaute_zeitbombe_ist_heute_gruen(self):
        """Ohne diesen Nachweis waere die „Bombe" nur ein kaputter Test — und
        der Fund unten hiesse nichts."""
        pfad, _ = self._probe("bombe")
        self.assertEqual(zg.lauf([pfad], 0).rc, 0)

    def test_die_gebaute_zeitbombe_wird_gefunden(self):
        pfad, ordner = self._probe("bombe")
        bericht = zg.pruefe(ordner, dateien=[pfad])
        self.assertEqual([p for p, _ in bericht.bomben], [pfad])
        self.assertFalse(bericht.gruen)

    def test_dasselbe_datum_ohne_gleitende_schwelle_bleibt_unbeanstandet(self):
        """★★ DIE POSITIVKONTROLLE. Gleiche Datei, gleiches festes Datum,
        gleiches Produktionsmodul — nur ohne Schwelle, die an HEUTE haengt.
        Schlaegt der Waechter hier an, beanstandet er auch die neun gesunden
        Dateien im Repo und wird abgeschaltet."""
        pfad, ordner = self._probe("harmlos")
        with open(pfad, encoding="utf-8") as fh:
            quelle = fh.read()
        self.assertTrue(zg.feste_daten(quelle),
                        "die harmlose Probe muss ein festes Datum tragen — "
                        "sonst prueft sie den Waechter gar nicht")
        bericht = zg.pruefe(ordner, dateien=[pfad])
        self.assertEqual(bericht.bomben, [])
        self.assertTrue(bericht.gruen)

    def test_ein_heute_schon_roter_test_ist_keine_zeitbombe(self):
        """Ein gewoehnlicher Fehlschlag gehoert nicht in diese Spalte. Faende
        der Waechter ihn, schoebe er bei rotem ``main`` fremde Fehler auf
        „Zeitbombe" — und die naechste echte ginge darin unter."""
        pfad, ordner = self._probe("schon_rot")
        bericht = zg.pruefe(ordner, dateien=[pfad])
        self.assertEqual(bericht.bomben, [])
        self.assertEqual([p for p, _ in bericht.schon_rot], [pfad])

    def test_der_waechter_laeuft_auch_unter_vorgerueckter_uhr(self):
        """★★ Verschachtelung — der Fall, der beim Streifzug ueber die ganze
        Suite eintritt und den Waechter im eigenen Lauf rot gemacht haette.

        Laeuft der Waechter SELBST mit vorgerueckter Uhr, darf er den Sollwert
        fuer sein Kind nicht aus seiner eigenen, schon verschobenen Uhr
        rechnen — sonst erwartet er +7306 Tage, sieht +3653 und schlaegt Alarm.
        Gemessen wird das an drei echten Prozessen, nicht an der Formel:
        Waechter (verschoben) -> Waechter-Aufruf -> Testlauf.
        """
        ordner = tempfile.mkdtemp(dir=self.tmp)
        tools = os.path.join(REPO, "tools")
        enkel = os.path.join(ordner, "test_enkel.py")
        with open(enkel, "w", encoding="utf-8") as fh:
            fh.write("def test_trivial():\n    assert True\n")
        # Der Enkel OHNE Sprung muss die ECHTE Uhr sehen: der Beleg des
        # Vorspanns darf sich nicht ueber einen sprungfreien Lauf hinweg
        # vererben, sonst rechnete `echt_heute()` dort einen Sprung heraus,
        # den es gar nicht gibt.
        enkel_echt = os.path.join(ordner, "test_enkel_echt.py")
        with open(enkel_echt, "w", encoding="utf-8") as fh:
            fh.write("import sys, datetime\n"
                     "sys.path.insert(0, %r)\n"
                     "import zeitbomben_gate as zg\n"
                     "ECHT = datetime.date.fromisoformat(%r)\n"
                     "def test_echte_uhr():\n"
                     "    assert abs((zg.echt_heute() - ECHT).days) <= 1, "
                     "zg.echt_heute()\n"
                     % (tools, zg.echt_heute().isoformat()))
        kind = os.path.join(ordner, "test_kind.py")
        with open(kind, "w", encoding="utf-8") as fh:
            fh.write("import sys\n"
                     "sys.path.insert(0, %r)\n"
                     "import zeitbomben_gate as zg\n"
                     "def test_waechter_unter_sprung():\n"
                     "    e = zg.lauf([%r], zg.SPRUNG_TAGE)\n"
                     "    assert e.sprung_wirksam, e.ausgabe[-2000:]\n"
                     "    assert e.rc == 0, e.ausgabe[-2000:]\n"
                     "def test_sprungfreier_lauf_sieht_die_echte_uhr():\n"
                     "    e = zg.lauf([%r], 0)\n"
                     "    assert e.rc == 0, e.ausgabe[-2000:]\n"
                     % (tools, enkel, enkel_echt))
        ergebnis = zg.lauf([kind], zg.SPRUNG_TAGE)
        self.assertEqual(ergebnis.rc, 0, ergebnis.ausgabe[-3000:])

    def test_die_probe_traegt_ein_frisch_gepraegtes_datum(self):
        """Eine EINGECHECKTE Zeitbombe waere selbst eine: ein paar Wochen nach
        dem Merge waere sie auch ohne Sprung rot, und dieser Test kippte ohne
        Codeaenderung. Das Datum muss deshalb am Lauftag haengen."""
        pfad, _ = self._probe("bombe")
        with open(pfad, encoding="utf-8") as fh:
            quelle = fh.read()
        soll = (zg.echt_heute() - datetime.timedelta(days=3)).isoformat()
        self.assertIn(f'STEMPEL = "{soll}T10:00:00"', quelle)


class RepoTest(unittest.TestCase):
    """Der Waechter, scharf geschaltet auf das echte Repo."""

    def test_kein_test_im_repo_ist_eine_zeitbombe(self):
        """★ Faellt dieser Test rot, wird eine Testdatei demnaechst von SELBST
        rot — die Ausgabe unten nennt sie beim Namen. Reparatur: das feste
        Datum am Lauftag ausrechnen (so wie ``RecencyTest`` in
        ``tests/test_crash_intake.py`` seit QA-62), damit der Test die REGEL
        misst statt eines Kalenderstands.
        """
        bericht = zg.pruefe(TESTS)
        self.assertTrue(bericht.kandidaten, "keine Kandidaten gefunden — dann "
                                            "hat dieser Lauf nichts gemessen")
        namen = [os.path.relpath(p, REPO) for p, _ in bericht.bomben]
        self.assertEqual(
            namen, [],
            "Zeitbombe(n) gefunden — diese Dateien werden ohne Codeaenderung "
            "rot:\n" + "\n".join(a for _, a in bericht.bomben)[-4000:])

    def test_die_sechs_von_qa62_ueberstehen_den_sprung(self):
        """★★ Der Fehlalarm-Nachweis an den ECHTEN Dateien, nicht an Proben.
        Sie sind der Grund, warum das Gate die Verbindung messen muss statt des
        Datums: sie tragen alle eines und sind alle gesund."""
        dateien = [os.path.join(TESTS, n) for n in QA62_GESUND]
        for pfad in dateien:
            self.assertTrue(os.path.isfile(pfad), pfad)
        ergebnis = zg.lauf(dateien, zg.SPRUNG_TAGE)
        self.assertTrue(ergebnis.sprung_wirksam,
                        "ohne wirksamen Sprung beweist gruen hier nichts")
        self.assertEqual(ergebnis.rc, 0,
                         "eine der sechs als gesund gemessenen Dateien wurde "
                         "rot:\n" + ergebnis.ausgabe[-3000:])


class ProzessHygieneTest(unittest.TestCase):
    """Der Waechter startet pytest AUS pytest heraus — das ist im Haus teuer
    bezahlt worden."""

    def test_ein_haengendes_kind_wird_abgeraeumt_statt_zu_haengen(self):
        """Der Deckel liegt unter dem des Gate-Tests (600 s): faellt er hier,
        nimmt er den Kindprozess mit. Faellt zuerst der aeussere, bliebe ein
        verwaister pytest samt Qt-Kindern liegen."""
        ordner = tempfile.mkdtemp(prefix="zeitbomben_deckel_")
        self.addCleanup(shutil.rmtree, ordner, True)
        pfad = os.path.join(ordner, "test_haengt.py")
        with open(pfad, "w", encoding="utf-8") as fh:
            fh.write("import time\ndef test_schlaeft():\n    time.sleep(20)\n")
        with self.assertRaises(subprocess.TimeoutExpired):
            zg.lauf([pfad], 0, zeitlimit=3)

    def test_das_kind_bekommt_eine_eigene_show_datenbank(self):
        """★ QA-53: ein Kind-pytest erbte den Pfad der Show-Datenbank und
        loeschte sie dem Elternprozess beim conftest-Import weg — gemessen 95
        Prozesse auf EINER Datei, mit wandernden roten Segmenten und falscher
        Abschlusszahl. Deshalb gibt ``lauf()`` jedem Kind einen eigenen Pfad.

        Gemessen wird das im Kind selbst, nicht an der Umgebung, die der Test
        baut — sonst prueft er seine eigene Kopie der Regel.
        """
        ordner = tempfile.mkdtemp(prefix="zeitbomben_hygiene_")
        self.addCleanup(shutil.rmtree, ordner, True)
        eltern = os.environ.get("LIGHTOS_SHOW_DB", "")
        self.assertTrue(eltern, "conftest.py setzt LIGHTOS_SHOW_DB — ohne den "
                                "Elternwert misst dieser Test nichts")
        pfad = os.path.join(ordner, "test_zeigt_db.py")
        with open(pfad, "w", encoding="utf-8") as fh:
            fh.write("import os\n"
                     "ELTERN = %r\n"
                     "def test_eigene_db():\n"
                     "    assert os.environ['LIGHTOS_SHOW_DB'] != ELTERN\n"
                     % eltern)
        self.assertEqual(zg.lauf([pfad], 0).rc, 0,
                         "das Kind arbeitet auf der Show-Datenbank des Elters")


class BerichtUndCliTest(unittest.TestCase):
    """Der Befund muss lesbar sein — sonst wird ein roter Lauf falsch gedeutet.

    ★ Genau das war das Teure an QA-62: der Fehler gehoerte zu keinem Commit,
    und niemand kam auf die Idee, im Kalender zu suchen. Der Text hier muss die
    Datei nennen UND sagen, was zu tun ist.
    """

    def _bericht(self, bomben=(), schon_rot=()):
        return zg.Bericht([], list(bomben), list(schon_rot), zg.SPRUNG_TAGE, "")

    def test_ohne_fund_meldet_der_text_gruen(self):
        self.assertIn("GRUEN", zg.bericht_text(self._bericht()))

    def test_eine_bombe_wird_beim_namen_genannt_mit_reparaturhinweis(self):
        pfad = os.path.join(TESTS, "test_irgendwas.py")
        text = zg.bericht_text(self._bericht(bomben=[(pfad, "E   assert 0")]))
        self.assertIn("tests/test_irgendwas.py", text)
        self.assertIn("ZEITBOMBE", text)
        self.assertIn("am Lauftag ausrechnen", text)
        self.assertNotIn("GRUEN", text)

    def test_ein_schon_roter_test_wird_als_fremd_ausgewiesen(self):
        pfad = os.path.join(TESTS, "test_kaputt.py")
        text = zg.bericht_text(self._bericht(schon_rot=[(pfad, "")]))
        self.assertIn("schon HEUTE rot", text)
        self.assertIn("GRUEN", text, "ein fremder Fehlschlag macht dieses Gate "
                                     "nicht rot")

    def test_die_kandidatenliste_laeuft_ueber_die_kommandozeile(self):
        """Der billige Weg, den ein Mensch zuerst nimmt — er muss gehen."""
        rc = zg.main(["--nur-kandidaten"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
