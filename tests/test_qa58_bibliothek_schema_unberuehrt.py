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
        """Fertig-Kriterium aus QA-58, an der Datei des Nutzers gemessen.

        Der Kindprozess bekommt KEIN ``LIGHTOS_FIXTURE_DB`` mit — er loest die
        Bibliothek genauso auf wie jedes Segment des Gates.
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


if __name__ == "__main__":
    unittest.main()
