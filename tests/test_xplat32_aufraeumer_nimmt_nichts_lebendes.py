"""XPLAT-32 — der GETEILTE Aufraeumer darf nichts wegnehmen, was noch lebt.

``tests/conftest.py`` laeuft vor JEDER Testdatei und raeumt dabei im
GEMEINSAMEN Ordner ``_TEST_ROOT`` alles weg, dessen Zeitstempel aelter als 24 h
aussieht. Welche Pfade zu einem noch LEBENDEN Lauf gehoerten, wusste bisher nur
der Prozess selbst (seine Umgebungsvariablen). Ein Nachbar sah davon nichts.

GEMESSEN am 2026-09-06 am laufenden Code, VOR dem Fix: ein einziger
``import conftest`` in einem fremden Prozess nahm die als eigen markierte Datei
in 20 von 20 Faellen weg, und
``test_qa58_bibliothek_schema_unberuehrt.py::BibliothekSchemaTest::
test_alte_leichen_werden_weggeraeumt_frische_fremde_nicht`` wurde damit 7 von 12
Runden rot (ohne Nachbarn 0 von 12). NACH dem Fix: 0 von 20 bzw. 0 von 12.

Diese Datei nagelt beide Haelften fest, und zwar an den ECHTEN Funktionen:

* Was LEBT, bleibt liegen — im eigenen Prozess UND wenn ein FREMDER Prozess
  aufraeumt, ueber beide Wege in den Aufraeumer (direkter Aufruf und blosser
  Import).
* Was TOT ist, verschwindet weiter. Ohne diese Gegenproben bestuende jeder Test
  hier auch dann, wenn der Aufraeumer schlicht abgeschaltet waere.

⚠️ Alles hier laeuft im GETEILTEN Ordner, also mitten unter fremden Prozessen.
Wo eine Zusicherung deshalb nicht in einem Anlauf zu haben ist, steht ein
begrenzter Wiederholungs-Anlauf UND eine Vorbedingung, die den Durchgang als
schluessig ausweist — nie ein Test, der bei Nachbarlast einfach durchwinkt.
"""
import os
import subprocess
import sys
import time
import unittest
import uuid

import conftest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(conftest.__file__)))
_TESTS = os.path.join(_REPO, "tests")
# 48 h alt: sicher jenseits von conftest._RESTE_FRIST.
_ALT = 48 * 3600
# Wie oft ein Anlauf wiederholt wird, der an fremder Last scheitern KANN.
_ANLAEUFE = 5

_KIND = """
import os
import sys
{takt_aushebeln}
sys.path.insert(0, {tests!r})
import conftest
{aufraeumen}
print(chr(10).join('EIGEN:' + p for p in sorted(conftest._eigene_testpfade())))
"""


def _fremde_umgebung() -> dict:
    """Umgebung fuer den Nachbarprozess — OHNE jeden geerbten LightOS-Pfad.

    Das ist die halbe Messung: erbte der Nachbar ``LIGHTOS_FIXTURE_DB``, schonte
    er die Datei schon ueber seine EIGENE Umgebung, und der Test bewiese nichts
    ueber die geteilte Auskunft. Die Tests pruefen zusaetzlich nach, dass der
    Pfad in den eigenen Pfaden des Nachbarn wirklich nicht vorkommt.
    """
    umgebung = dict(os.environ)
    for schluessel in ("LIGHTOS_FIXTURE_DB", "LIGHTOS_SHOW_DB",
                       "LIGHTOS_CRASH_LOG", "LIGHTOS_SACN_CID",
                       "LIGHTOS_UNIVERSES_JSON", "APPDATA", "XDG_DATA_HOME"):
        umgebung.pop(schluessel, None)
    umgebung["QT_QPA_PLATFORM"] = "offscreen"
    return umgebung


def _nachbar_raeumt_auf(weg: str, beleg: str) -> list:
    """Ein FREMDER Prozess raeumt auf und meldet seine EIGENEN Pfade zurueck.

    ``weg="direkt"``  -> ruft ``_purge_old_test_crash_logs()`` selbst auf.
    ``weg="import"``  -> tut NICHTS ausser ``import conftest`` (der Weg, an dem
    der qa58-Waechter rot wurde).

    ``beleg`` ist eine herrenlose Leiche, die danach WEG sein muss: sie belegt,
    dass der Nachbar den Loeschzweig ueberhaupt betreten hat. Der Import-Weg ist
    getaktet, und der Takt-Stempel ist GETEILT — ein fremder Prozess kann ihn
    zwischendurch frisch setzen. Darum entwertet der Kindprozess ihn selbst, und
    darum gibt es bis zu `_ANLAEUFE` Anlaeufe statt einer stillen Annahme.
    """
    stempel = conftest._AUFRAEUM_STEMPEL
    quelle = _KIND.format(
        tests=_TESTS,
        takt_aushebeln="" if weg == "direkt" else
        f"try:\n    os.remove({stempel!r})\nexcept OSError:\n    pass",
        aufraeumen="conftest._purge_old_test_crash_logs()"
        if weg == "direkt" else "")
    for _anlauf in range(_ANLAEUFE):
        fertig = subprocess.run([sys.executable, "-c", quelle],
                                env=_fremde_umgebung(), cwd=_REPO,
                                capture_output=True, text=True, timeout=300)
        if fertig.returncode != 0:
            raise AssertionError("der Nachbarprozess ist gescheitert: "
                                 f"{fertig.stderr[-2000:]}")
        pfade = [z[len("EIGEN:"):] for z in fertig.stdout.splitlines()
                 if z.startswith("EIGEN:")]
        if not os.path.exists(beleg):
            return pfade
    raise AssertionError(
        f"Vorbedingung verfehlt: der Nachbar ({weg}) hat in {_ANLAEUFE} "
        "Anlaeufen die herrenlose Leiche nicht weggeraeumt — der Loeschzweig "
        "wurde nie betreten, die Messung sagt nichts aus")


class AufraeumerNimmtNichtsLebendesTest(unittest.TestCase):
    """Alles laeuft gegen die ECHTEN Funktionen aus tests/conftest.py."""

    def setUp(self):
        self.marke = f"xplat32_{os.getpid()}_{uuid.uuid4().hex[:8]}"
        self.zaehler = 0

    # ── Werkzeug ────────────────────────────────────────────────────────────
    def _lege_an(self, endung, alter=0.0):
        """Eine Datei im GETEILTEN Wurzelordner anlegen, Zeitstempel wie gewuenscht."""
        self.zaehler += 1
        pfad = os.path.join(
            conftest._TEST_ROOT,
            f"lightos_test_fixtures_{self.marke}_{self.zaehler}_{endung}.db")
        with open(pfad, "wb") as f:
            f.write(b"x")
        if alter:
            wann = time.time() - alter
            os.utime(pfad, (wann, wann))
        self.addCleanup(self._raeum_weg, pfad)
        return pfad

    def _raeum_weg(self, pfad):
        """Datei UND die eigene Anspruchsmarke dazu wieder abtragen."""
        ort = conftest._anspruch_ort(pfad)
        for opfer in (pfad, os.path.join(ort, conftest._TEST_TOKEN)):
            try:
                os.remove(opfer)
            except OSError:
                pass
        try:
            os.rmdir(ort)
        except OSError:
            pass

    def _als_eigen_anmelden(self, pfad, variable="LIGHTOS_FIXTURE_DB"):
        """Den Pfad so beanspruchen, wie conftest es beim Import tut."""
        self._umgebung_setzen(variable, pfad)
        conftest._anspruch_anmelden()
        # Vorbedingung: ohne liegende Marke misst der Test nichts.
        self.assertTrue(conftest._ist_beansprucht(pfad),
                        "die Anspruchsmarke liegt nicht — der Test wuerde am "
                        "Gegenstand vorbeimessen")

    def _umgebung_setzen(self, variable, wert):
        vorher = os.environ.get(variable)
        self.addCleanup(self._umgebung_zurueck, variable, vorher)
        os.environ[variable] = wert

    def _umgebung_zurueck(self, variable, vorher):
        if vorher is None:
            os.environ.pop(variable, None)
        else:
            os.environ[variable] = vorher

    # ── Der Kern: was lebt, bleibt liegen ───────────────────────────────────
    def test_der_eigene_aufruf_nimmt_die_eigene_alte_datei_nicht_weg(self):
        """Der Aufraeumer im EIGENEN Prozess laesst die eigene Datei liegen —
        auch wenn ihr Zeitstempel 48 h alt ist.

        Die Leiche daneben belegt im selben Durchgang, dass der Loeschzweig
        ueberhaupt betreten wurde.
        """
        eigen = self._lege_an("eigen", alter=_ALT)
        self._als_eigen_anmelden(eigen)
        leiche = self._lege_an("leiche", alter=_ALT)

        conftest._purge_old_test_crash_logs()

        self.assertFalse(os.path.exists(leiche),
                         "Vorbedingung verfehlt: der Loeschzweig wurde nicht "
                         "betreten, die Messung sagt nichts aus")
        self.assertTrue(os.path.exists(eigen),
                        "der Aufraeumer hat die EIGENE Datei weggenommen")

    def test_ein_fremder_prozess_nimmt_die_angemeldete_datei_nicht_weg(self):
        """Der Kern von XPLAT-32: der Aufraeumer laeuft in JEDEM Prozess.

        Der Nachbar erbt den Pfad NICHT — er kann ihn nur ueber die geteilte
        Anspruchsmarke kennen. Genau das wird hier nachgeprueft.
        """
        eigen = self._lege_an("eigen", alter=_ALT)
        self._als_eigen_anmelden(eigen)
        leiche = self._lege_an("leiche", alter=_ALT)

        fremde_pfade = _nachbar_raeumt_auf("direkt", beleg=leiche)

        self.assertNotIn(eigen, fremde_pfade,
                         "der Nachbar haelt den Pfad fuer seinen eigenen — die "
                         "Messung liefe ins Leere")
        self.assertTrue(os.path.exists(eigen),
                        "ein fremder Prozess hat die Datei eines LEBENDEN "
                        "Laufs weggenommen")

    def test_auch_der_blosse_import_nimmt_die_angemeldete_datei_nicht_weg(self):
        """Der zweite Weg in den Aufraeumer — und der, an dem qa58 rot wurde.

        Es braucht keinen zweiten qa58-Lauf und keinen zeitbomben-Test: JEDER
        Prozess, der conftest.py auch nur importiert, raeumt mit auf.
        """
        eigen = self._lege_an("eigen", alter=_ALT)
        self._als_eigen_anmelden(eigen)
        leiche = self._lege_an("leiche", alter=_ALT)

        fremde_pfade = _nachbar_raeumt_auf("import", beleg=leiche)

        self.assertNotIn(eigen, fremde_pfade,
                         "der Nachbar haelt den Pfad fuer seinen eigenen")
        self.assertTrue(os.path.exists(eigen),
                        "ein blosser conftest-Import hat die Datei eines "
                        "LEBENDEN Laufs weggenommen")

    def test_die_seitendateien_der_eigenen_datenbank_sind_ebenfalls_geschuetzt(self):
        """Der ZWEITE WEG an derselben Regel vorbei.

        Das Muster ``lightos_test_show_*.db*`` trifft auch ``-wal`` und
        ``-shm``; die frueher hier stehende Schonliste kannte nur den nackten
        DB-Pfad. Eine offene SQLite-Datenbank ohne ihr WAL ist genauso kaputt
        wie eine geloeschte.
        """
        db = os.path.join(conftest._TEST_ROOT,
                          f"lightos_test_show_{self.marke}.db")
        wal = db + "-wal"
        wann = time.time() - _ALT
        for pfad in (db, wal):
            with open(pfad, "wb") as f:
                f.write(b"x")
            os.utime(pfad, (wann, wann))
            self.addCleanup(self._raeum_weg, pfad)
        self._als_eigen_anmelden(db, variable="LIGHTOS_SHOW_DB")
        self.assertTrue(conftest._ist_beansprucht(wal),
                        "die Seitendatei ist nicht mitangemeldet")
        leiche = self._lege_an("leiche", alter=_ALT)

        _nachbar_raeumt_auf("direkt", beleg=leiche)

        self.assertTrue(os.path.exists(wal),
                        "das WAL der eigenen, LEBENDEN Datenbank wurde "
                        "weggenommen")

    def test_der_aufraeumer_meldet_die_eigenen_pfade_selbst_an(self):
        """Genau die Reihenfolge, die der qa58-Waechter fuehrt: Pfad in die
        Umgebung setzen, dann aufraeumen.

        Die Anmeldung muss der Aufraeumer SELBST erledigen. Verliesse er sich
        darauf, dass sie beim Import laengst passiert ist, waere jeder Pfad, den
        ein Test spaeter setzt, fuer jeden Nachbarn Freiwild.

        Zwischen dem Anlegen und dem Aufruf ist die Datei fuer rund eine
        Millisekunde herrenlos (gemessen 1,1 ms) — nimmt ein Nachbar sie in
        genau diesem Fenster weg, ist der Durchgang unschluessig und wird
        wiederholt. Die eigentliche Zusicherung, dass die Marke danach liegt,
        wird in JEDEM Durchgang geprueft.
        """
        for _anlauf in range(_ANLAEUFE):
            eigen = self._lege_an("eigen", alter=_ALT)
            self._umgebung_setzen("LIGHTOS_FIXTURE_DB", eigen)
            self.assertFalse(conftest._ist_beansprucht(eigen),
                             "Vorbedingung: noch darf keine Marke liegen")

            conftest._purge_old_test_crash_logs()

            self.assertTrue(conftest._ist_beansprucht(eigen),
                            "der Aufraeumer meldet die eigenen Pfade nicht "
                            "selbst an")
            if os.path.exists(eigen):
                return
        self.fail("der Aufraeumer hat die EIGENE Datei weggenommen")

    def test_das_DATENVERZEICHNIS_des_laufenden_prozesses_ist_geschuetzt(self):
        """★★★ Vom Skeptiker gefunden, und es ist der destruktivste Zweig des
        Aufraeumers ueberhaupt.

        ``_eigene_testpfade`` nimmt ausser den Dateien auch ``_TEST_APPDATA``
        auf — das Datenverzeichnis DIESES Laufs, mit ``crash.log``, ``stages/``
        und ``ui_prefs.json`` darin. Der Aufraeumer loescht ein Verzeichnis per
        ``shutil.rmtree``.

        Entfernt man diese eine Zeile, nimmt ein fremder Prozess das
        Verzeichnis eines LEBENDEN Laufs **8 von 8 Mal** weg (gemessen; unmutiert
        0 von 8) — und **kein Test hielt das fest**. Alle uebrigen Tests dieser
        Datei arbeiten mit einzelnen DATEIEN; das Verzeichnis war unbeobachtet.
        """
        pfade = conftest._eigene_testpfade()
        self.assertIn(conftest._TEST_APPDATA, pfade,
                      "das Datenverzeichnis dieses Laufs steht nicht unter "
                      "Schutz — ein Nachbar darf es per rmtree entfernen")

    def test_das_datenverzeichnis_ueberlebt_einen_fremden_hausputz(self):
        """Die Verhaltensprobe zur Zeile darueber: nicht nur „steht in der
        Menge", sondern „ist danach noch da". Ein Test, der nur die Menge
        prueft, faellt nicht auf, wenn die Menge spaeter jemand anders liest."""
        marke = os.path.join(conftest._TEST_APPDATA, "LightOS", "ui_prefs.json")
        os.makedirs(os.path.dirname(marke), exist_ok=True)
        with open(marke, "w", encoding="utf-8") as f:
            f.write("{}")
        alt = time.time() - _ALT
        os.utime(conftest._TEST_APPDATA, (alt, alt))
        os.utime(marke, (alt, alt))
        self.assertTrue(os.path.exists(marke), "Vorbedingung: die Datei liegt")

        leiche = self._lege_an("leiche", alter=_ALT)
        _nachbar_raeumt_auf("direkt", beleg=leiche)

        self.assertTrue(os.path.isdir(conftest._TEST_APPDATA),
                        "ein fremder Prozess hat das Datenverzeichnis des "
                        "laufenden Laufs geloescht")
        self.assertTrue(os.path.exists(marke),
                        "der Inhalt des Datenverzeichnisses ist weg")

    def test_die_anspruchsfrage_steht_an_der_entscheidungsstelle(self):
        """Die Frage „gehoert das noch jemandem" muss UNMITTELBAR vor dem
        Loeschen stehen, nicht als Momentaufnahme am Anfang des Durchgangs.

        Ein Durchgang durchsucht den geteilten Ordner und dauert dabei GEMESSEN
        80,8 ms (12319 Eintraege) — lange genug, dass ein Nachbar in derselben
        Zeit seine Datei anlegt und anmeldet. Mit Momentaufnahme am Anfang war
        der qa58-Waechter unter Last 16 von 24 Runden rot, mit der Frage an der
        Entscheidungsstelle 0 von 24.

        Hier ohne Zeitspiel gemessen: die Anmeldung passiert nachweislich erst,
        WAEHREND der echte Durchgang schon laeuft. Der angemeldete Koeder sorgt
        dafuer, dass der Durchgang die Frage garantiert stellt — sonst koennte
        ein Nachbar dem Test alle Kandidaten wegnehmen und er liefe leer.
        """
        koeder = self._lege_an("koeder", alter=_ALT)
        self._als_eigen_anmelden(koeder)
        echte_frage = conftest._ist_beansprucht
        self.addCleanup(setattr, conftest, "_ist_beansprucht", echte_frage)

        for _anlauf in range(_ANLAEUFE):
            spaet = self._lege_an("spaet", alter=_ALT)
            self.assertFalse(echte_frage(spaet),
                             "Vorbedingung: vor dem Durchgang gehoert der Pfad "
                             "niemandem")
            aufrufe = []

            def erst_waehrend_des_durchgangs(pfad, _spaet=spaet,
                                             _aufrufe=aufrufe):
                if not _aufrufe:
                    os.environ["LIGHTOS_FIXTURE_DB"] = _spaet
                    conftest._anspruch_anmelden()
                _aufrufe.append(pfad)
                return echte_frage(pfad)

            # Die Umgebung stellt der Aufraeumcode des Koeders zurueck
            # (addCleanup laeuft LIFO, der aelteste Eintrag zuletzt).
            conftest._ist_beansprucht = erst_waehrend_des_durchgangs
            try:
                conftest._purge_old_test_crash_logs()
            finally:
                conftest._ist_beansprucht = echte_frage

            self.assertTrue(aufrufe,
                            "Vorbedingung verfehlt: der Aufraeumer hat die "
                            "Frage kein einziges Mal gestellt")
            if os.path.exists(spaet):
                return
            # Nicht gefragt heisst: ein Nachbar war schneller als der eigene
            # Durchgang -> unschluessig, neuer Anlauf. Gefragt und trotzdem
            # weg heisst: dieser Aufraeumer hat aus einer Momentaufnahme
            # entschieden.
            self.assertNotIn(spaet, aufrufe,
                             "der Aufraeumer entscheidet aus einer "
                             "Momentaufnahme vom Anfang des Durchgangs")
        self.fail(f"in {_ANLAEUFE} Anlaeufen kein schluessiger Durchgang — "
                  "fremde Prozesse haben die Probe jedes Mal vorher geholt")

    # ── Gegenproben: was tot ist, verschwindet weiter ───────────────────────
    def test_echte_alte_leichen_werden_weiter_geloescht(self):
        """Gegenprobe (a) aus dem Item: ein Fix, der einfach nichts mehr
        loescht, bestuende jeden Test darueber."""
        leiche = self._lege_an("leiche", alter=_ALT)
        self.assertFalse(conftest._ist_beansprucht(leiche),
                         "Vorbedingung: die Leiche darf niemandem gehoeren")

        conftest._purge_old_test_crash_logs()

        self.assertFalse(os.path.exists(leiche),
                         "eine echte alte Leiche bleibt liegen — pro Lauf "
                         "9,6 MiB")

    def test_frische_fremde_dateien_bleiben_liegen(self):
        """Die zweite Haelfte der alten Regel bleibt gueltig: frisch heisst
        „ein Nachbar arbeitet gerade daran"."""
        frisch = self._lege_an("frisch")
        leiche = self._lege_an("leiche", alter=_ALT)

        conftest._purge_old_test_crash_logs()

        self.assertFalse(os.path.exists(leiche),
                         "Vorbedingung verfehlt: der Loeschzweig wurde nicht "
                         "betreten")
        self.assertTrue(os.path.exists(frisch),
                        "eine FRISCHE fremde Datei wurde weggeraeumt")

    def test_eine_abgelaufene_marke_schuetzt_nicht_mehr(self):
        """Gegenprobe gegen die andere Richtung: eine Marke, die ein hart
        abgestuerzter Lauf hinterlassen hat, darf ihre Reste nicht ewig
        schuetzen — sonst waechst der Temp-Ordner unbegrenzt."""
        leiche = self._lege_an("leiche", alter=_ALT)
        ort = conftest._anspruch_ort(leiche)
        os.makedirs(ort, exist_ok=True)
        marke = os.path.join(ort, "toter_lauf_1234_deadbeef")
        with open(marke, "w", encoding="utf-8") as f:
            f.write(leiche)
        self.assertTrue(conftest._ist_beansprucht(leiche),
                        "Vorbedingung: die frische Marke muss zuerst schuetzen")
        wann = time.time() - _ALT
        os.utime(marke, (wann, wann))

        conftest._purge_old_test_crash_logs()

        self.assertFalse(os.path.exists(leiche),
                         "eine laengst abgelaufene Marke schuetzt ihre Reste "
                         "immer noch")
        self.assertFalse(os.path.exists(marke),
                         "die abgelaufene Marke selbst bleibt liegen")

    # ── Der getaktete Import-Weg darf keine Luecke aufreissen ───────────────
    def _eigener_takt_stempel(self):
        """Den Takt-Stempel fuer diesen Test auf einen PRIVATEN Pfad legen.

        Der echte Stempel ist GETEILT: an ihm haengt der Hausputz aller
        gleichzeitig startenden Prozesse. Wer ihn in einem Test entwertet,
        wuerde erstens die Nachbarn stoeren und zweitens ein Wettrennen gegen
        sie fuehren (gemessen: 2 von 8 Runden rot unter vier hammernden
        Nachbarn). Umgelenkt wird nur der ORT — gefahren wird die echte
        `_aufraeumen_beim_import`.
        """
        stempel = os.path.join(conftest._TEST_ROOT,
                               f".takt_probe_{self.marke}")
        self.addCleanup(setattr, conftest, "_AUFRAEUM_STEMPEL",
                        conftest._AUFRAEUM_STEMPEL)
        self.addCleanup(self._loesche, stempel)
        conftest._AUFRAEUM_STEMPEL = stempel
        self.assertFalse(os.path.exists(stempel),
                         "Vorbedingung: der private Stempel muss fehlen")
        return stempel

    def _loesche(self, pfad):
        try:
            os.remove(pfad)
        except OSError:
            pass

    def test_der_takt_meldet_den_anspruch_auch_ohne_hausputz_an(self):
        """Ueberspringt ein Prozess den Hausputz, muss er trotzdem seine Pfade
        anmelden — sonst waeren sie fuer den Prozess, der gerade aufraeumt,
        unsichtbar und damit Freiwild."""
        stempel = self._eigener_takt_stempel()
        eigen = self._lege_an("eigen", alter=_ALT)
        self._umgebung_setzen("LIGHTOS_FIXTURE_DB", eigen)
        self.assertFalse(conftest._ist_beansprucht(eigen),
                         "Vorbedingung: der Pfad darf noch nicht angemeldet sein")
        with open(stempel, "w", encoding="utf-8") as f:
            f.write(str(int(time.time())))   # frisch -> der Takt sperrt

        gelaufen = conftest._aufraeumen_beim_import()

        self.assertFalse(gelaufen,
                         "Vorbedingung verfehlt: der Takt hat nicht gesperrt")
        self.assertTrue(conftest._ist_beansprucht(eigen),
                        "ein Prozess, der den Hausputz ueberspringt, meldet "
                        "seine Pfade nicht an")

    def test_der_takt_schaltet_den_hausputz_nicht_ab(self):
        """Gegenprobe zum Takt: er darf den Hausputz nur SELTENER machen, nicht
        abschalten. Ohne Stempel raeumt er auf, unmittelbar danach nicht mehr."""
        self._eigener_takt_stempel()
        leiche = self._lege_an("leiche", alter=_ALT)

        self.assertTrue(conftest._aufraeumen_beim_import(),
                        "ohne Stempel muss der Hausputz laufen")

        self.assertFalse(os.path.exists(leiche),
                         "der getaktete Weg hat nicht aufgeraeumt")
        self.assertFalse(conftest._aufraeumen_beim_import(),
                         "der Takt greift gar nicht — jeder der ~600 Prozesse "
                         "durchsucht weiter den ganzen Ordner")


if __name__ == "__main__":
    unittest.main()
