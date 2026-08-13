"""QA-58 — ein Suite-Lauf veraendert das SCHEMA der echten Bibliothek nicht.

**Der Vorfall, gegen den hier geprueft wird.** ``tests/conftest.py`` pinnte
``LIGHTOS_FIXTURE_DB`` bis 2026-08-12 absichtlich auf die ECHTE
``fixtures.db`` des Nutzers, begruendet mit *„reine LESE-/idempotente
Seed-Last"*. Diese Annahme gilt nicht mehr, sobald eine SCHEMA-Migration
dazukommt: der VIZ-50a-Lauf hat ``grid_rows``/``grid_cols`` per ``ALTER TABLE``
in die Nutzerdatei geschrieben. Der Schaden war additiv — der Mechanismus aber
falsch, und QA-54 faengt ihn nicht: der Waechter dort bewacht Schreib-FUNKTIONEN
(``create_user_profile`` …), die Migration laeuft in ``fixture_db.get_engine()``
vor jedem ersten Zugriff.

**★ Warum der Beleg an der echten Datei allein WERTLOS waere.** Ihr Schema ist
heute auf dem neuesten Stand — es kann sich also gar nicht mehr aendern, egal
wie kaputt die Isolation ist. Ein Test, der nur davor/danach vergleicht, waere
ab dem Tag der Reparatur dauerhaft gruen und wuerde die Rueckkehr des Fehlers
nicht sehen (er wuerde erst bei der NAECHSTEN Modell-Spalte auffallen, also
wieder an der Datei des Nutzers). Deshalb steht daneben ein A/B an einer
STELLVERTRETER-Bibliothek, der die VIZ-50a-Spalten fehlen: gleiches Segment,
gleiche Ausgangsdatei, EIN Unterschied — liegt sie an einem Ort, den die Suite
als Nutzerdatei behandelt, oder ist sie bereits eine Testkopie. Der eine Arm
belegt den Schutz, der andere, dass die Messung eine Aenderung auch saehe.

**Und die Gegenrichtung.** „Die Datei bleibt unberuehrt" waere auch dann erfuellt,
wenn die Suite die vorgesetzte Bibliothek einfach IGNORIERTE und immer die
Standard-Datei kopierte. Deshalb wird zusaetzlich am INHALT der Kopie gemessen,
aus welcher Datei sie stammt (``PRAGMA user_version`` als Marke) — mit
Positivkontrolle, dass diese Messung ohne Vorgabe die echte Bibliothek anzeigt.

★ Die echte Bibliothek wird hier ausschliesslich LESEND (``mode=ro``) angefasst.

★★ **Was in dieser Datei den vollen Lauf abdeckt und was nicht — die Korrektur
aus der zweiten Runde.** Die Tests oben fahren jeweils EIN Segment als
Kindprozess. Das Fertig-Kriterium von QA-58 spricht vom VOLLEN Suite-Lauf; eine
Stichprobe von 1 aus 604 als Aussage ueber alle auszugeben, war die eigentliche
Schwaeche des ersten Anlaufs — daneben der Umstand, dass die Messung „Schema
vorher/nachher" auf einem Rechner mit aktueller Bibliothek gar nicht anschlagen
KANN. Die Zusage haengt seither an einer Pruefung in ``tests/conftest.py``, die
in jedem der 604 Segmente laeuft und am PFAD misst statt am Schema. Belegt wird
sie von ``WaechterDeckungTest`` ganz unten: derselbe echte Segmentlauf einmal
mit und einmal ohne den realistischen Rueckfall, in einem Sandkasten-Datenordner,
damit der Rueckfall-Arm niemals die Datei des Nutzers trifft.
"""
from __future__ import annotations

import glob
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Das Segment, das im Kindprozess laeuft. Bewusst DIESES: ``test_render_probe_
# demo_show`` oeffnet die Bibliothek ueber ``get_all_manufacturers()``, also ueber
# ``fixture_db.engine()`` — und genau dort laeuft ``migrate_fixtures_db()``.
#
# ⚠️ **Was „1 passed" beweist und was NICHT — nachgemessen, weil hier zuerst zu
# viel behauptet stand.** Es beweist, dass das Segment die Bibliothek fehlerfrei
# OEFFNEN konnte: mit einer Bibliothek, der eine Modellspalte fehlt und deren
# Migration gesperrt ist, faellt ``get_all_manufacturers()`` und der Test meldet
# „1 skipped" (am 2026-08-13 so gemessen). Es beweist NICHT, dass es die ECHTE
# Bibliothek war — mit einer frisch geseedeten leeren DB ist dasselbe Segment
# ebenfalls „1 passed". Der Beleg, dass dieses Segment wirklich MIGRIERT, ist
# deshalb nicht der Zaehlerstand, sondern Arm B unten: dieselbe Datei, dasselbe
# Segment, und danach stehen die Spalten drin.
_OPFER = "tests/test_capability_live.py::test_render_probe_demo_show"

# Die VIZ-50a-Spalten — der reale Vorfall. Aus dem Stellvertreter entfernt,
# damit die Migration wieder etwas zu tun hat.
_VIZ50A_SPALTEN = ("grid_rows", "grid_cols")


def _echte_bibliothek() -> str:
    """Pfad der ECHTEN Bibliothek.

    Aus ``conftest`` geholt, das ihn aufloest, BEVOR es ``APPDATA`` ins
    Test-Temp umbiegt — auf Windows liefe ``app_data_dir()`` hier sonst ins
    Test-APPDATA und der Waechter prueft die falsche Datei.
    """
    import conftest
    return conftest._ECHTE_FIXTURE_DB


def _profil_kennzahl(pfad: str):
    """Kennzahl ueber die Profil-IDs: (Anzahl, kleinste, groesste, Summe).

    Trifft genau das, wofuer die Kopie da ist. Eine frisch geseedete Bibliothek
    haette dieselben Tabellen (das Schema saehe also gleich aus), aber ANDERE
    Auto-IDs und nur die 47 Quelltext-Profile statt der 1789 der echten Datei —
    und die committeten shows/*.lshow zeigen auf die IDs.
    """
    con = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
    try:
        return con.execute(
            "SELECT count(*), min(id), max(id), sum(id) FROM fixtures").fetchone()
    finally:
        con.close()


def _user_version(pfad: str) -> int:
    """``PRAGMA user_version`` — als MARKE, um zwei Bibliotheken zu unterscheiden.

    Bewusst dieses Feld: es steht im SQLite-Dateikopf, wird von LightOS nirgends
    benutzt (die echte Bibliothek hat 0) und ueberlebt eine Migration
    unveraendert. Eine Markierung ueber eine Tabellenzeile haette dagegen an das
    Datenmodell gekoppelt, das dieses Item gerade erst als beweglich erwiesen hat.
    """
    con = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
    try:
        return con.execute("PRAGMA user_version").fetchone()[0]
    finally:
        con.close()


def _schema(pfad: str):
    """Fingerabdruck des SCHEMAS (Tabellen -> Spalten), nicht des Inhalts.

    Liest READ-ONLY: ``mode=ro`` kann per Konstruktion nicht schreiben, also
    faelscht die Messung ihr eigenes Ergebnis nicht.
    """
    if not os.path.exists(pfad):
        return None
    con = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
    try:
        tabellen = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {t: [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
                for t in tabellen}
    finally:
        con.close()


class BibliothekSchemaTest(unittest.TestCase):

    # ── Werkzeug ────────────────────────────────────────────────────────────
    def _segment(self, fixture_db: str | None, zusatz: dict | None = None):
        """Faehrt EIN echtes Segment als Kindprozess.

        ``fixture_db=None`` heisst: die Variable wird aus der Umgebung ENTFERNT,
        der Kindprozess loest die Bibliothek also selbst auf — das ist der Weg,
        den ein gewoehnlicher Suite-Lauf geht.

        Eigene Show-DB fuer das Kind: sonst arbeiten Eltern- und Kindprozess auf
        derselben Datei (QA-53).
        """
        tmp = tempfile.mkdtemp(prefix="qa58_kind_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        env = dict(os.environ)
        env.pop("LIGHTOS_FIXTURE_DB", None)
        if fixture_db is not None:
            env["LIGHTOS_FIXTURE_DB"] = fixture_db
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["LIGHTOS_SHOW_DB"] = os.path.join(tmp, "show.db")
        env.update(zusatz or {})
        # Popen statt run(): der Aufraeum-Test unten braucht die PID des Kindes,
        # um GENAU dessen Kopie zu suchen (im Gate laufen Nachbarsegmente
        # parallel und legen staendig eigene an).
        p = subprocess.Popen(
            [sys.executable, "-m", "pytest", "-q", _OPFER, "-p", "no:cacheprovider"],
            cwd=_REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env)
        self._letzte_pid = p.pid
        aus, _ = p.communicate(timeout=600)
        # Der Zaehlerstand ist hier eine SANITAETSPRUEFUNG, kein Beweis: er
        # sagt nur, dass das Segment die Bibliothek fehlerfrei oeffnen konnte
        # (bei kaputtem Schema meldet es „1 skipped", s. Kopf der Datei). Dass
        # eine Migration stattgefunden HAETTE, belegt Arm B.
        self.assertIn("1 passed", aus,
                      "das Segment ist uebersprungen/rot — dann sagt die "
                      f"Messung daneben nichts:\n{aus[-2000:]}")
        return aus

    def _konftest_kind(self, vorgabe: str | None):
        """Faehrt NUR den Kopierschritt und meldet, worauf er gelenkt hat.

        Ein Kindprozess importiert das ECHTE ``tests/conftest.py``. Das ist der
        Produktionsweg Zeile fuer Zeile: die Kopie entsteht ausschliesslich beim
        Modul-Import, nicht in einem Testhaken. Kein pytest darum herum, und
        zwar aus einem Grund: ein volles Segment loescht seine Kopie am
        Sitzungsende wieder — dann waere ihr INHALT nicht mehr messbar, und
        genau der ist hier die Frage (aus WELCHER Datei stammt sie?). Die
        Schutzwirkung am vollstaendigen Segment misst Arm A.

        Rueckgabe: (Pfad der Kopie, ``PRAGMA user_version`` der Kopie).
        """
        code = ("import os, sys\n"
                "sys.path.insert(0, os.getcwd())\n"
                "sys.path.insert(0, os.path.join(os.getcwd(), 'tests'))\n"
                "import conftest\n"
                "print('KOPIE=' + str(conftest._FIXTURE_DB_KOPIE))\n"
                "print('APPDATA=' + conftest._TEST_APPDATA)\n")
        tmp = tempfile.mkdtemp(prefix="qa58_konftest_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        env = dict(os.environ)
        env.pop("LIGHTOS_FIXTURE_DB", None)
        if vorgabe is not None:
            env["LIGHTOS_FIXTURE_DB"] = vorgabe
        env["LIGHTOS_SHOW_DB"] = os.path.join(tmp, "show.db")   # QA-53
        fertig = subprocess.run([sys.executable, "-c", code], cwd=_REPO,
                                capture_output=True, text=True, timeout=300,
                                env=env)
        self.assertEqual(0, fertig.returncode,
                         f"conftest liess sich nicht importieren:\n{fertig.stderr[-2000:]}")
        werte = dict(z.split("=", 1) for z in fertig.stdout.splitlines()
                     if "=" in z)
        kopie = werte.get("KOPIE")
        # Das Kind kommt ohne pytest-Sitzung nie zum eigenen Aufraeumen.
        self.addCleanup(shutil.rmtree, werte.get("APPDATA", ""),
                        ignore_errors=True)
        self.addCleanup(lambda: kopie and os.path.exists(kopie)
                        and os.remove(kopie))
        self.assertTrue(kopie and kopie != "None",
                        f"conftest hat gar keine Kopie angelegt: {fertig.stdout}")
        self.assertTrue(os.path.exists(kopie),
                        f"die gemeldete Kopie {kopie} existiert nicht")
        return kopie, _user_version(kopie)

    def _stellvertreter(self, marke: int = 0) -> str:
        """Eine Bibliothek wie die echte, aber OHNE die VIZ-50a-Spalten.

        Kopie der realen Datei (nicht frisch geseedet), damit das Opfer-Segment
        seine Profil-IDs findet und beide Arme wirklich dasselbe tun.

        ``marke`` schreibt zusaetzlich ein ``PRAGMA user_version`` in den
        Dateikopf — daran laesst sich spaeter erkennen, ob eine Kopie WIRKLICH
        aus dieser Datei stammt.
        """
        echt = _echte_bibliothek()
        if not os.path.exists(echt):
            self.skipTest("keine echte Bibliothek auf diesem Rechner")
        tmp = tempfile.mkdtemp(prefix="qa58_stellv_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        ziel = os.path.join(tmp, "fixtures.db")
        shutil.copyfile(echt, ziel)
        con = sqlite3.connect(ziel)
        try:
            for spalte in _VIZ50A_SPALTEN:
                con.execute(f"ALTER TABLE fixture_modes DROP COLUMN {spalte}")
            if marke:
                con.execute(f"PRAGMA user_version = {int(marke)}")
            con.commit()
        finally:
            con.close()
        self.assertEqual(
            [], [s for s in _VIZ50A_SPALTEN
                 if s in _schema(ziel)["fixture_modes"]],
            "der Stellvertreter hat die Spalten noch — das A/B haette keinen "
            "Unterschied zu zeigen")
        return ziel

    # ── Der Beleg an der echten Datei ───────────────────────────────────────
    def test_ein_echter_segmentlauf_laesst_die_echte_bibliothek_unberuehrt(self):
        """Eine STICHPROBE an der Datei des Nutzers — mehr ist es nicht.

        Der Kindprozess bekommt KEIN ``LIGHTOS_FIXTURE_DB`` mit; er loest die
        Bibliothek genauso auf wie jedes Segment des Gates. Das ist ein
        Ende-zu-Ende-Beleg an der echten Datei, und er ist etwas wert, weil hier
        wirklich nichts gestellt ist.

        ⚠️ **Was er NICHT ist: das Fertig-Kriterium von QA-58.** Das spricht vom
        VOLLEN Suite-Lauf — 604 Segmente —, hier laeuft EINES. Genau diese
        Verwechslung (Stichprobe von 1 als Aussage ueber alle) hat das Item im
        ersten Anlauf zurueckgeworfen. Und die Messung selbst ist auf einem
        Rechner mit aktueller Bibliothek stumpf: dort gibt es nichts zu
        migrieren, die Datei bliebe auch bei kaputter Isolation byte-identisch.
        Den vollen Lauf deckt der Waechter in ``tests/conftest.py`` ab
        (``pytest_collection_finish`` + ``_waechter_bibliothek_ist_eine_kopie``),
        belegt in ``WaechterDeckungTest`` weiter unten.
        """
        echt = _echte_bibliothek()
        if not os.path.exists(echt):
            self.skipTest("keine echte Bibliothek auf diesem Rechner")
        vorher = _schema(echt)
        vorher_datei = (os.stat(echt).st_size, os.stat(echt).st_mtime_ns)

        self._segment(None)

        self.assertEqual(vorher, _schema(echt),
                         "ein Suite-Lauf hat das SCHEMA der echten Fixture-"
                         "Bibliothek veraendert (QA-58)")
        self.assertEqual(
            vorher_datei, (os.stat(echt).st_size, os.stat(echt).st_mtime_ns),
            "die echte Bibliothek wurde geschrieben (Groesse/Zeitstempel)")

    # ── Positivkontrolle: sieht die Messung eine Aenderung? ─────────────────
    def test_eine_vorgesetzte_nutzerdatei_wird_kopiert_statt_migriert(self):
        """Arm A des A/B — der Schutz.

        Der Stellvertreter liegt dort, wo eine Nutzerdatei liegt, und wird dem
        Kind ausdruecklich vorgesetzt. Er muss die Migration trotzdem nicht
        abbekommen: die Suite arbeitet auf einer KOPIE.

        ⚠️ Das ist zugleich die Antwort auf „eine Schutzmassnahme, die sich vom
        Zielobjekt abschalten laesst, ist keine" (CDX-49): ein von aussen
        gesetzter Pfad bestimmt die QUELLE der Kopie, nicht das Ziel der
        Schreibzugriffe.
        """
        stellvertreter = self._stellvertreter()

        self._segment(stellvertreter)

        fehlend = [s for s in _VIZ50A_SPALTEN
                   if s not in _schema(stellvertreter)["fixture_modes"]]
        self.assertEqual(
            sorted(_VIZ50A_SPALTEN), sorted(fehlend),
            "die Suite hat die vorgesetzte Bibliothek migriert, statt auf einer "
            "Kopie zu arbeiten — genau der VIZ-50a-Vorfall")

    def test_dieselbe_messung_sieht_die_migration_wenn_sie_stattfindet(self):
        """Arm B des A/B — die Positivkontrolle.

        Gleiches Segment, gleiche Ausgangsdatei, gleicher Umgebungs-Schalter.
        EINZIGER Unterschied: die Datei liegt im Testkopie-Ordner, gilt also
        bereits als isoliert — dort arbeitet die Suite direkt darauf, und die
        Migration schlaegt zu. Ohne diesen Arm waere nicht zu unterscheiden, ob
        Arm A den Schutz belegt oder die Messung nur blind ist.
        """
        stellvertreter = self._stellvertreter()
        # Der Ort, den conftest als „schon eine Testkopie" behandelt. Bewusst
        # aus tempfile abgeleitet und NICHT aus LIGHTOS_FIXTURE_DB: waere die
        # Isolation kaputt, zeigte die Variable in den Datenordner des Nutzers —
        # und diese Kontrolle legte dort eine Datei ab.
        testkopien = os.path.join(tempfile.gettempdir(), "lightos_tests")
        os.makedirs(testkopien, exist_ok=True)
        vorgetaeuschte_kopie = os.path.join(
            testkopien, f"lightos_test_fixtures_qa58probe_{os.getpid()}.db")
        shutil.copyfile(stellvertreter, vorgetaeuschte_kopie)
        self.addCleanup(lambda: os.path.exists(vorgetaeuschte_kopie)
                        and os.remove(vorgetaeuschte_kopie))

        self._segment(vorgetaeuschte_kopie)

        spalten = _schema(vorgetaeuschte_kopie)["fixture_modes"]
        self.assertEqual(
            [], [s for s in _VIZ50A_SPALTEN if s not in spalten],
            "die Messung sieht die Migration NICHT, obwohl sie hier stattfinden "
            "muss — dann belegt der Schwestertest nichts")

    # ── Die Vorgabe bestimmt die QUELLE, nicht das Ziel ─────────────────────
    def test_eine_vorgabe_von_aussen_ist_die_QUELLE_der_kopie(self):
        """Die zweite Haelfte der Aussage von Arm A — und ohne sie waere sie
        unbelegt.

        Arm A zeigt nur, dass die vorgesetzte Datei UNBERUEHRT bleibt. Das
        traefe genauso zu, wenn conftest die Vorgabe schlicht ignorierte und
        immer die Standard-Bibliothek kopierte — die Suite liefe dann still an
        der Bibliothek vorbei, auf die jemand sie ausdruecklich gerichtet hat
        (``tools/verify_stage_reload.py`` tut genau das). Gemessen wird deshalb
        am INHALT der Kopie: sie muss die Marke der Vorgabe tragen.
        """
        marke = 58_000_000 + os.getpid() % 1_000_000
        stellvertreter = self._stellvertreter(marke=marke)
        self.assertEqual(marke, _user_version(stellvertreter),
                         "die Marke steht gar nicht in der Vorgabe")

        kopie, gemessen = self._konftest_kind(stellvertreter)

        self.assertNotEqual(os.path.realpath(stellvertreter),
                            os.path.realpath(kopie),
                            "die Suite arbeitet direkt auf der Vorgabe")
        self.assertEqual(
            marke, gemessen,
            "die Kopie stammt NICHT aus der Vorgabe — eine von aussen gesetzte "
            "LIGHTOS_FIXTURE_DB wird stillschweigend uebergangen")

    def test_ohne_vorgabe_stammt_die_kopie_aus_der_echten_bibliothek(self):
        """Positivkontrolle zur Marken-Messung: sie unterscheidet wirklich.

        Ohne diesen Arm koennte der Test oben auch dann gruen sein, wenn
        ``_user_version`` etwas misst, das gar nicht von der Quelle abhaengt.
        Hier laeuft dasselbe Kind ohne Vorgabe — und die Kopie traegt dann die
        Marke der ECHTEN Bibliothek (0), nicht die des Stellvertreters.
        """
        echt = _echte_bibliothek()
        if not os.path.exists(echt):
            self.skipTest("keine echte Bibliothek auf diesem Rechner")

        kopie, gemessen = self._konftest_kind(None)

        self.assertEqual(_user_version(echt), gemessen,
                         "ohne Vorgabe stammt die Kopie nicht aus der echten "
                         f"Bibliothek: {kopie}")
        if os.stat(echt).st_mtime > os.stat(kopie).st_mtime:
            # Die Bibliothek hat sich NACH dem Kopieren geaendert (laufende
            # App). Dann ist ein Unterschied richtig und kein Befund.
            return
        self.assertEqual(
            _profil_kennzahl(echt), _profil_kennzahl(kopie),
            "die Kopie traegt nicht den Bestand der echten Bibliothek")

    def test_ohne_vorhandene_bibliothek_laeuft_die_suite_trotzdem(self):
        """Frische Installation und CI haben noch gar keine ``fixtures.db``.

        Dann gibt es nichts zu kopieren — und das darf den Lauf nicht
        verhindern, sondern muss in den bisherigen Weg muenden
        (``fixture_db._seed_if_empty()`` legt eine an). Geprueft mit einem
        Datenordner, den es nicht gibt; ``APPDATA`` fuer Windows,
        ``XDG_DATA_HOME`` fuer Linux, damit der Kindprozess auf beiden
        Betriebssystemen ins Leere zeigt.
        """
        leer = tempfile.mkdtemp(prefix="qa58_ohne_bibliothek_")
        self.addCleanup(shutil.rmtree, leer, ignore_errors=True)
        self._segment(None, {"XDG_DATA_HOME": leer, "APPDATA": leer,
                             "HOME": leer})

    # ── Die Kopie darf nicht liegenbleiben ──────────────────────────────────
    def test_ein_segment_laesst_seine_kopie_nicht_liegen(self):
        """Der Preis der Kopie ist nur dann klein, wenn sie wieder verschwindet.

        603 Segmente x 9,6 MiB = 5,8 GiB pro Gate-Lauf, wenn nicht. Gesucht wird
        gezielt die Kopie DIESES Kindprozesses (Name traegt seine PID) — im Gate
        laufen Nachbarsegmente parallel und legen laufend eigene an, ein
        pauschales Zaehlen waere flatterhaft.
        """
        self._segment(None)
        muster = os.path.join(tempfile.gettempdir(), "lightos_tests",
                              f"lightos_test_fixtures_{self._letzte_pid}_*.db*")
        self.assertEqual([], sorted(glob.glob(muster)),
                         "das Segment hat seine Kopie der Bibliothek liegen "
                         "gelassen")

    def test_alte_leichen_werden_weggeraeumt_frische_fremde_nicht(self):
        """Fuer den Fall, dass ein Segment hart abstuerzt und nicht mehr zum
        eigenen Aufraeumen kommt (auf Windows der bekannte 0xC0000005 im nativen
        Qt-Abbau) — dann raeumt der naechste Lauf nach 24 h.

        Mit beiden Gegenproben, denn ein zu eifriger Aufraeumer ist schlimmer
        als keiner: eine FRISCHE fremde Kopie gehoert einem LAUFENDEN
        Nachbarsegment, und die EIGENE (ueber die Umgebung bekannte) darf auch
        alt nicht verschwinden — ein Kindprozess erbt sie vom Elternprozess.
        """
        import conftest

        wurzel = os.path.join(tempfile.gettempdir(), "lightos_tests")
        os.makedirs(wurzel, exist_ok=True)
        alt = time.time() - 48 * 3600

        def lege_an(name, zeitstempel=None):
            p = os.path.join(wurzel, name)
            with open(p, "wb") as f:
                f.write(b"x")
            if zeitstempel:
                os.utime(p, (zeitstempel, zeitstempel))
            self.addCleanup(lambda: os.path.exists(p) and os.remove(p))
            return p

        marke = f"qa58purge_{os.getpid()}"
        leiche = lege_an(f"lightos_test_fixtures_{marke}_alt.db", alt)
        frisch = lege_an(f"lightos_test_fixtures_{marke}_frisch.db")
        eigene = lege_an(f"lightos_test_fixtures_{marke}_eigen.db", alt)

        alte_vorgabe = os.environ.get("LIGHTOS_FIXTURE_DB")
        os.environ["LIGHTOS_FIXTURE_DB"] = eigene
        try:
            conftest._purge_old_test_crash_logs()
        finally:
            if alte_vorgabe is None:
                os.environ.pop("LIGHTOS_FIXTURE_DB", None)
            else:
                os.environ["LIGHTOS_FIXTURE_DB"] = alte_vorgabe

        self.assertFalse(os.path.exists(leiche),
                         "alte Kopien bleiben liegen — pro Lauf 9,6 MiB")
        self.assertTrue(os.path.exists(frisch),
                        "eine FRISCHE fremde Kopie wurde weggeraeumt — die "
                        "gehoert einem laufenden Nachbarsegment")
        self.assertTrue(os.path.exists(eigene),
                        "die EIGENE Kopie wurde weggeraeumt — ein Kindprozess "
                        "haette damit dem Elternprozess die Bibliothek entzogen")

    # ── Billiger Sofort-Waechter im laufenden Prozess ───────────────────────
    def test_die_engine_dieses_prozesses_zeigt_nicht_auf_die_echte_datei(self):
        """Geprueft wird der Pfad, den das ORM TATSAECHLICH benutzt (die URL der
        gebauten Engine), nicht die Absicht einer Umgebungsvariablen.

        Derselbe Zuschnitt wie die Waechter fuer crash.log und sACN-CID in
        ``tests/test_app_data_dir.py``.
        """
        from src.core.database import fixture_db as FDB

        benutzt = os.path.realpath(FDB.engine().url.database or "")
        echt = os.path.realpath(_echte_bibliothek())
        self.assertNotEqual(benutzt, echt,
                            "die Suite arbeitet auf der ECHTEN Fixture-"
                            f"Bibliothek: {benutzt}")

    def test_die_kopie_traegt_die_echten_profil_ids(self):
        """Die andere Haelfte der Entscheidung: eine KOPIE, kein frischer Seed.

        Ohne diesen Test waere „arbeite nicht auf der echten Datei" trivial zu
        erfuellen — mit einer leeren Datei. Dann vergibt ``_seed_if_empty()``
        neue Auto-IDs, und die ``fixture_profile_id``-Werte der committeten Shows
        zeigen ins Leere. Gemessen wird an der Datei, die das ORM WIRKLICH
        benutzt, gegen die echte Bibliothek.
        """
        from src.core.database import fixture_db as FDB

        echt = _echte_bibliothek()
        if not os.path.exists(echt):
            self.skipTest("keine echte Bibliothek auf diesem Rechner")
        benutzt = FDB.engine().url.database or ""
        if os.stat(echt).st_mtime > os.stat(benutzt).st_mtime:
            # Die Bibliothek wurde NACH dem Kopieren veraendert (laufende App).
            # Dann ist ein Unterschied richtig und kein Befund.
            self.skipTest("die echte Bibliothek hat sich nach dem Kopieren "
                          "geaendert")
        self.assertEqual(
            _profil_kennzahl(echt), _profil_kennzahl(benutzt),
            "die Arbeits-Bibliothek ist keine Kopie der echten — damit stimmen "
            "die fixture_profile_id-Werte der committeten Shows nicht mehr")


class WaechterDeckungTest(unittest.TestCase):
    """★ Deckt der Waechter die ganze Zusage ab?

    **Der Mangel, gegen den diese Klasse antritt.** Die Tests oben fahren EIN
    Segment als Kindprozess. Das Fertig-Kriterium von QA-58 spricht aber vom
    VOLLEN Suite-Lauf — 604 Segmente. Eine Stichprobe von 1 als Aussage ueber
    alle auszugeben, ist genau die Sorte zu weit gefasster Zusage, an der das
    Item im ersten Anlauf gescheitert ist.

    **Die Zusage haengt seither an zwei Pruefungen in ``tests/conftest.py``** —
    ``pytest_collection_finish`` fuer ``fixture_db.DB_PATH`` (bricht ab, bevor
    ein Test laeuft) und ``_waechter_bibliothek_ist_eine_kopie`` fuer die
    tatsaechlich gebaute Engine. Beide laufen in JEDEM Segment, weil jedes
    Segment dieses ``conftest.py`` laedt. Hier wird belegt, dass sie das auch
    tun: derselbe echte Segmentlauf einmal MIT und einmal OHNE den realistischen
    Rueckfall, fuer beide Wege getrennt und jeweils mit Positivkontrolle.

    ★ **Warum ein Stellvertreter-Datenordner und nicht die echte Bibliothek.**
    Der Rueckfall-Arm laesst das Segment absichtlich auf ``app_data_dir()/
    fixtures.db`` laufen und dort wird migriert. Das darf niemals die Datei des
    Nutzers sein. Also bekommt der Kindprozess ein eigenes ``XDG_DATA_HOME`` mit
    einer Kopie der Bibliothek: fuer ihn ist DAS die echte Bibliothek — der
    Waechter im ``conftest`` rechnet sich seinen Vergleichspfad aus genau
    derselben Quelle aus. Der gepruefte Weg ist Zeile fuer Zeile derselbe, nur
    der Datenordner ist ein Sandkasten.
    """

    _NUR_SKIPS = "tests/test_color_fx_show_render.py"
    """Ein Segment, dessen Tests sich ALLE ueberspringen (die Show ist nicht
    committet), dessen Modul-Import aber ``app_state`` und damit ``fixture_db``
    laedt. Genau der Fall, den eine Test-Fixture nicht sieht: sie laeuft nie."""

    _FRUEH = "tests/test_dimmer_master.py"
    """Ein Segment, das ``fixture_db`` schon beim MODUL-Import laedt (gemessen:
    beim Kollektionsende ist es in ``sys.modules``) und dessen 7 Tests bestehen.
    An ihm laesst sich belegen, dass der Waechter den Lauf abbricht, BEVOR ein
    Test die Bibliothek anfassen kann."""

    _SPAET = _OPFER
    """Und die Gegenprobe: ``test_capability_live.py`` importiert die Bibliothek
    erst IM Test (gemessen: beim Kollektionsende nicht in ``sys.modules``). Dort
    kann der Kollektions-Waechter per Konstruktion nichts sehen — das faengt die
    Fixture nach dem Test ab. Beide Faelle stehen hier, damit die Zusage nicht
    mehr behauptet als der frueheste Zugriffszeitpunkt hergibt."""

    def setUp(self):
        echt = _echte_bibliothek()
        if not os.path.exists(echt):
            self.skipTest("keine echte Bibliothek auf diesem Rechner")

    def _sandkasten_datenordner(self) -> str:
        """Ein ``XDG_DATA_HOME``, in dem eine Kopie der Bibliothek liegt.

        Kopie und nicht frischer Seed: das Opfer-Segment sucht seine Fixtures
        ueber die ``fixture_profile_id`` der committeten Show. Die echte Datei
        wird dabei ausschliesslich GELESEN.
        """
        tmp = tempfile.mkdtemp(prefix="qa58_sandkasten_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        ordner = os.path.join(tmp, "LightOS")
        os.makedirs(ordner)
        shutil.copyfile(_echte_bibliothek(), os.path.join(ordner, "fixtures.db"))
        return tmp

    def _lauf(self, opfer: str, xdg: str, plugin: str | None = None):
        """Faehrt ``opfer`` als echtes Segment im Sandkasten-Datenordner.

        ``plugin`` laedt eines der beiden Rueckfall-Module dazu
        (``tests/_qa58_rueckfall.py`` = Umlenkung weg, also ``DB_PATH`` auf der
        Bibliothek; ``tests/_qa58_engine_rueckfall.py`` = globale Engine auf der
        Bibliothek). Ohne ``plugin`` laeuft das Segment voellig unveraendert —
        das ist die Positivkontrolle.
        """
        tmp = tempfile.mkdtemp(prefix="qa58_waechter_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        env = dict(os.environ)
        env.pop("LIGHTOS_FIXTURE_DB", None)
        # ★ Alle drei Datenordner-Variablen, nicht nur die von Linux. Sonst
        # haengt dieser Beleg an einer Luecke, die im selben Item als
        # Nebenbefund gemeldet ist: `conftest.py` lenkt heute NUR `APPDATA` um
        # und leitet `_ECHTE_FIXTURE_DB` aus `app_data_dir()` ab. Wuerde es
        # kuenftig auch `XDG_DATA_HOME` umlenken (genau das steht als Item an),
        # rechnete der Kindprozess `_ECHTE_FIXTURE_DB` aus dem Sandkasten,
        # `DB_PATH` aber aus seinem eigenen Testordner — der Vergleich schluege
        # nie an, der Rueckfall bliebe gruen, und die Beweisfuehrung fiele in
        # sich zusammen. Auf Windows ist das nach Codelage schon heute so.
        # Die Schwesterfunktion `test_ohne_vorhandene_bibliothek_laeuft_die_
        # suite_trotzdem` macht es laengst richtig; hier stand nur eine.
        env["XDG_DATA_HOME"] = xdg
        env["APPDATA"] = xdg
        env["HOME"] = xdg
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["LIGHTOS_SHOW_DB"] = os.path.join(tmp, "show.db")       # QA-53
        env["LIGHTOS_CRASH_LOG"] = os.path.join(tmp, "crash.log")
        env["PYTHONPATH"] = os.pathsep.join(
            [os.path.join(_REPO, "tests")] + (
                [env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
        befehl = [sys.executable, "-m", "pytest", "-q", "--tb=short",
                  "-p", "no:cacheprovider"]
        if plugin:
            befehl += ["-p", plugin]
        befehl.append(opfer)
        fertig = subprocess.run(befehl, cwd=_REPO, capture_output=True,
                                text=True, timeout=300, env=env)
        return fertig.returncode, fertig.stdout + fertig.stderr

    # ── Der Abbruch muss AUSSEHEN wie ein Fehlschlag ────────────────────────
    def test_der_abbruch_hinterlaesst_eine_FAILED_zeile(self):
        """Sonst liest sich ein echter Rueckfall wie ein Massen-Teardown-Crash.

        ``tools/verify_segmented.sh`` sammelt am Ende ``grep -h '^FAILED'`` und
        schreibt das Ergebnis unter „Fehlgeschlagene Tests:\". Steht dort
        nichts, deutet sein eigener Kommentar — und ``CLAUDE.md`` gleichlautend
        — rote Segmente als native Abbau-Crashes (QA-24), also als
        Dringlichkeits-**Herabstufung**. Bei einem echten Rueckfall gehen ALLE
        604 Segmente rot; ohne diese Zeile bliebe die Liste komplett leer, und
        wer die QA-58-Meldung finden will, muesste ein Segment-Log oeffnen.

        Genau die Fehldiagnose-Signatur, wegen der ``pytest_unconfigure`` +
        ``os._exit`` verworfen wurde. Sie gilt fuer den Kollektions-Abbruch
        genauso — deshalb steht sie hier unter Test statt unter Vertrauen.
        """
        rc, ausgabe = self._lauf(self._FRUEH, self._sandkasten_datenordner(),
                                 plugin="_qa58_rueckfall")
        self.assertEqual(1, rc, "der Rueckfall muss das Segment rot faerben")
        failed = [z for z in ausgabe.splitlines() if z.startswith("FAILED")]
        self.assertTrue(
            failed,
            "Keine Zeile beginnt mit FAILED — verify_segmented.sh listet dann "
            "nichts unter „Fehlgeschlagene Tests\" und der Lauf liest sich als "
            "nativer Abbau-Crash statt als QA-58-Rueckfall.\n"
            f"Ausgabe:\n{ausgabe[-1500:]}")
        self.assertTrue(
            any("Bibliothek" in z for z in failed),
            f"die FAILED-Zeile muss sagen, worum es geht: {failed}")

    def test_ohne_rueckfall_gibt_es_keine_FAILED_zeile(self):
        """POSITIVKONTROLLE: im Normalfall schweigt der Waechter. Ohne sie waere
        der Test oben auch dann gruen, wenn bei JEDEM Lauf FAILED erschiene."""
        rc, ausgabe = self._lauf(_OPFER, self._sandkasten_datenordner())
        self.assertEqual(0, rc, ausgabe[-800:])
        self.assertEqual(
            [], [z for z in ausgabe.splitlines() if z.startswith("FAILED")],
            "ein normaler Lauf darf keine FAILED-Zeile erzeugen")

    # ── Rueckfall 1: die Umlenkung faellt weg ───────────────────────────────
    def test_ein_rueckfall_bricht_das_segment_ab_bevor_ein_test_laeuft(self):
        """Der Kern der Zusage: faellt die Umlenkung, wird das Segment rot.

        ⚠️ **Und zwar auf JEDEM Rechner.** Die Messung haengt bewusst am PFAD,
        den ``fixture_db`` benutzt, nicht am Schema der Datei: auf einem Rechner
        mit aktueller Bibliothek — dem Normalfall — gaebe es nichts mehr zu
        migrieren, die Datei bliebe auch bei voellig kaputter Isolation
        byte-identisch, und eine Schema-Messung waere gruen. Der Sandkasten hier
        traegt eine vollstaendige, aktuelle Kopie: der Rueckfall wird also unter
        genau der Bedingung rot, unter der die alte Messung blind ist.

        ★ Geprueft wird zusaetzlich, dass **kein Test mehr laeuft**. Der
        Waechter sitzt am Ende der Kollektion — bei einem Segment, das die
        Bibliothek beim Modul-Import laedt, meldet er den Fehler also nicht
        bloss, er kommt dem ersten Zugriff zuvor. Ohne diese Bedingung waere
        der Test auch dann gruen, wenn nur die Fixture nach dem Test anschluege.
        """
        xdg = self._sandkasten_datenordner()

        rc, aus = self._lauf(self._FRUEH, xdg, plugin="_qa58_rueckfall")

        self.assertNotEqual(0, rc,
                            f"der Rueckfall blieb GRUEN:\n{aus[-3000:]}")
        self.assertIn("QA-58", aus,
                      f"rot, aber nicht wegen des Waechters:\n{aus[-3000:]}")
        self.assertNotIn("passed", aus,
                         "das Segment hat seine Tests noch ausgefuehrt — der "
                         "Waechter greift zu spaet, der Zugriff auf die "
                         f"Bibliothek war schon:\n{aus[-3000:]}")

    def test_ohne_rueckfall_bleibt_dieses_segment_gruen(self):
        """Positivkontrolle: der Waechter schlaegt im Normalfall NICHT an.

        Gleiches Segment, gleicher Sandkasten, gleiche Umgebung — einziger
        Unterschied ist das fehlende Rueckfall-Plugin. Ohne diesen Arm koennte
        der Test darueber auch dann gruen sein, wenn der Waechter schlicht
        immer meckert. Der Zaehlerstand steht mit dabei: er belegt, dass hier
        ueberhaupt Tests laufen — sonst waere „kein Test lief" oben trivial.
        """
        xdg = self._sandkasten_datenordner()

        rc, aus = self._lauf(self._FRUEH, xdg)

        self.assertEqual(0, rc, f"das unveraenderte Segment ist rot:\n{aus[-3000:]}")
        self.assertRegex(aus, r"\d+ passed",
                         f"das Segment lief gar nicht:\n{aus[-3000:]}")
        self.assertNotIn("QA-58", aus,
                         f"der Waechter meldet ohne Anlass:\n{aus[-3000:]}")

    # ── … und die ehrliche Grenze: spaet importierende Segmente ─────────────
    def test_ein_spaet_importierendes_segment_wird_nach_dem_test_rot(self):
        """★ Was der Kollektions-Waechter NICHT kann — und wer es auffaengt.

        ``test_capability_live.py`` laedt die Bibliothek erst IM Test (gemessen:
        beim Kollektionsende steht ``src.core.database.fixture_db`` nicht in
        ``sys.modules``). Zur Kollektionszeit gibt es dort also nichts zu sehen,
        und ein Waechter, der nur dort steht, waere fuer solche Segmente blind.

        Aufgefangen wird das von der Fixture nach jedem Test. Der Preis steht
        damit auch fest und ist hier festgehalten statt beschoenigt: bei einem
        spaet importierenden Segment ist der Zugriff bereits passiert, wenn die
        Meldung kommt. Rot wird der Lauf trotzdem — und er nennt den Test.
        """
        xdg = self._sandkasten_datenordner()

        rc, aus = self._lauf(self._SPAET, xdg, plugin="_qa58_rueckfall")

        self.assertNotEqual(0, rc, f"der Rueckfall blieb GRUEN:\n{aus[-3000:]}")
        self.assertIn("QA-58", aus,
                      f"rot, aber nicht wegen des Waechters:\n{aus[-3000:]}")
        self.assertIn("test_render_probe_demo_show", aus,
                      "die Meldung nennt den Test nicht — dann sagt ein rotes "
                      f"Segment im Gate nicht, wo zu suchen ist:\n{aus[-3000:]}")

    def test_ohne_rueckfall_bleibt_dasselbe_segment_gruen(self):
        """Positivkontrolle zum spaet importierenden Segment."""
        xdg = self._sandkasten_datenordner()

        rc, aus = self._lauf(self._SPAET, xdg)

        self.assertEqual(0, rc, f"das unveraenderte Segment ist rot:\n{aus[-3000:]}")
        self.assertIn("1 passed", aus, f"das Segment lief gar nicht:\n{aus[-3000:]}")
        self.assertNotIn("QA-58", aus,
                         f"der Waechter meldet ohne Anlass:\n{aus[-3000:]}")

    # ── Auch ein Segment, in dem KEIN Test laeuft ────────────────────────────
    def test_ein_segment_ohne_laufenden_test_wird_trotzdem_rot(self):
        """Die Luecke, die eine Test-Fixture per Konstruktion nicht schliesst.

        ``test_color_fx_show_render.py`` meldet in jedem Gate-Lauf „5 skipped":
        seine Show ist nicht committet. Der Modul-Import laeuft trotzdem, zieht
        ``app_state`` und damit ``fixture_db`` herein — ``DB_PATH`` steht also
        fest, waehrend keine einzige Test-Fixture je ausgefuehrt wird. Genau
        deshalb sitzt der Waechter an der Kollektion und nicht in einer Fixture.
        """
        xdg = self._sandkasten_datenordner()

        rc, aus = self._lauf(self._NUR_SKIPS, xdg, plugin="_qa58_rueckfall")

        self.assertNotEqual(0, rc,
                            f"ein Segment ohne laufenden Test bleibt gruen:\n{aus[-3000:]}")
        self.assertIn("QA-58", aus, f"rot, aber nicht wegen des Waechters:\n{aus[-3000:]}")

    def test_dasselbe_segment_ohne_rueckfall_ueberspringt_sich_gruen(self):
        """Positivkontrolle dazu — und die Gegenprobe zur Annahme des Tests.

        Ohne Rueckfall muss dasselbe Segment gruen bleiben; und es muss sich
        wirklich ueberspringen. Faengt die Datei eines Tages an, Tests
        auszufuehren, prueft der Test darueber nicht mehr die Luecke, die er
        zu pruefen behauptet — dann faellt es hier auf.
        """
        xdg = self._sandkasten_datenordner()

        rc, aus = self._lauf(self._NUR_SKIPS, xdg)

        self.assertEqual(0, rc, f"das unveraenderte Segment ist rot:\n{aus[-3000:]}")
        self.assertRegex(aus, r"\d+ skipped",
                         "das Opfer-Segment fuehrt entgegen der Annahme Tests "
                         f"aus:\n{aus[-3000:]}")
        self.assertNotIn("passed", aus,
                         "das Opfer-Segment laesst inzwischen Tests laufen — "
                         "dann belegt der Test darueber die Luecke nicht mehr:"
                         f"\n{aus[-3000:]}")
        self.assertNotIn("QA-58", aus,
                         f"der Waechter meldet ohne Anlass:\n{aus[-3000:]}")

    # ── Rueckfall 2: die globale Engine haengt an der Bibliothek ────────────
    def test_eine_umgesetzte_engine_wird_rot(self):
        """``DB_PATH`` in Ordnung, ``_engine`` trotzdem auf der Bibliothek.

        Der zweite Weg zur Datei, den der Kollektions-Waechter per Konstruktion
        nicht sehen kann: ``get_engine(pfad)`` geht an ``DB_PATH`` vorbei, und
        ``fixture_db._engine`` ist ein umsetzbares Modul-Global (``tests/
        _fixture_quelle.frische_library`` macht genau das, dort richtig auf eine
        Wegwerf-Datei). Hier muss die Fixture nach dem Test anschlagen — und
        weil ein Test gelaufen ist, sagt sie auch WELCHER.
        """
        xdg = self._sandkasten_datenordner()

        rc, aus = self._lauf(_OPFER, xdg, plugin="_qa58_engine_rueckfall")

        self.assertNotEqual(0, rc, f"der Rueckfall blieb GRUEN:\n{aus[-3000:]}")
        self.assertIn("QA-58", aus,
                      f"rot, aber nicht wegen des Waechters:\n{aus[-3000:]}")
        self.assertIn("test_render_probe_demo_show", aus,
                      "die Meldung nennt den Test nicht — dann sagt ein rotes "
                      f"Segment im Gate nicht, wo zu suchen ist:\n{aus[-3000:]}")

    # ── Der Sandkasten muss auch wirklich einer sein ─────────────────────────
    def test_der_rueckfall_trifft_den_sandkasten_und_nicht_die_echte_datei(self):
        """★ Ohne diesen Test waere die ganze Klasse hier ein Risiko.

        Der Rueckfall-Arm laesst ein Segment absichtlich auf
        ``app_data_dir()/fixtures.db`` migrieren. Gemessen wird deshalb an
        BEIDEN Dateien: die Kopie im Sandkasten hat danach die VIZ-50a-Spalten
        (der Rueckfall ist also wirklich dort angekommen), die echte Bibliothek
        des Nutzers ist byte-identisch geblieben.

        Der Sandkasten startet dafuer ohne die beiden Spalten — sonst waere
        „sie sind da" schon vorher wahr und belegte nichts.
        """
        xdg = self._sandkasten_datenordner()
        sandkasten_db = os.path.join(xdg, "LightOS", "fixtures.db")
        con = sqlite3.connect(sandkasten_db)
        try:
            for spalte in _VIZ50A_SPALTEN:
                con.execute(f"ALTER TABLE fixture_modes DROP COLUMN {spalte}")
            con.commit()
        finally:
            con.close()
        echt = _echte_bibliothek()
        vorher_echt = (os.stat(echt).st_size, os.stat(echt).st_mtime_ns)

        self._lauf(_OPFER, xdg, plugin="_qa58_engine_rueckfall")

        spalten = _schema(sandkasten_db)["fixture_modes"]
        self.assertEqual(
            [], [s for s in _VIZ50A_SPALTEN if s not in spalten],
            "der Rueckfall hat den Sandkasten NICHT migriert — dann faehrt der "
            "Waechter-Nachweis oben etwas anderes als den echten Vorfall")
        self.assertEqual(
            vorher_echt, (os.stat(echt).st_size, os.stat(echt).st_mtime_ns),
            "der Rueckfall-Arm hat die ECHTE Bibliothek des Nutzers angefasst")


if __name__ == "__main__":
    unittest.main()
