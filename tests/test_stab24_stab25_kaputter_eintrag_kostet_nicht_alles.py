"""STAB-24/STAB-25: EIN kaputter Eintrag darf nicht ALLES kosten - und nie still.

Zwei Stellen im Lade-Pfad, dieselbe Fehlerklasse:

* ``_restore_fixture_groups`` loeschte ERST alle Gruppen (``delete(FixtureGroup)``)
  und legte sie danach einzeln neu an - alles in EINEM ``try``. Ein unlesbares
  Feld (``cols`` als Text) riss den ganzen Block ab; die Transaktion rollte
  zurueck, uebrig blieb die vom Reset geleerte Tabelle. Vier Gruppen in der
  Datei, null in der DB - wegen EINER.
* Der ``patch``-Block wurde still verworfen, wenn er keine Liste ist
  (``if isinstance(patch_entries, list)`` ohne ``else``), und einzelne
  Nicht-Objekt-Eintraege verschwanden mit einem stummen ``continue``. Kein
  Ladeproblem, kein Warndialog - die Geraete waren einfach weg.

**Die Schadensrichtung ist das Entscheidende:** der Verlust entsteht nicht beim
Laden, sondern beim naechsten SPEICHERN. Ein Hinweis danach ist wertlos. Darum
laufen beide Meldungen ueber den Weg, den das Haus schon hat - ``_lenient`` ->
``letzte_ladeprobleme()`` -> Warndialog in ``main_window._open_show_path`` -
und nicht ueber einen zweiten, neu erfundenen Kanal (Hausregel 6).

Gemessen wird am ECHTEN Weg: eine per ``save_show`` erzeugte Datei, deren
``show.json`` an GENAU EINER Stelle beschaedigt wird, danach ``load_show`` und
gezaehlt, was in der Show-DB steht.
"""
import contextlib
import json
import os
import tempfile
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import delete, select

from src.core.database.models import FixtureGroup, PatchedFixture
from src.core.show import show_file as SF


class _Basis(unittest.TestCase):
    """Gemeinsamer Aufbau: echte Show-Datei bauen, gezielt EINEN Eintrag
    beschaedigen, ueber ``load_show`` laden, das Ergebnis in der DB zaehlen."""

    def setUp(self):
        from src.core.app_state import get_state
        self.st = get_state()
        SF.reset_show()
        self.pfad = os.path.join(tempfile.gettempdir(),
                                 f"stab2425_{os.getpid()}_{id(self)}.lshow")

    def tearDown(self):
        SF.reset_show()
        with contextlib.suppress(OSError):
            os.remove(self.pfad)

    # ── Aufbau ───────────────────────────────────────────────────────────────

    def _gruppen_anlegen(self, namen):
        """Gruppen in die Show-DB schreiben - die Quelle, aus der save_show sammelt."""
        with self.st._session() as s:
            s.execute(delete(FixtureGroup))
            for i, name in enumerate(namen, start=1):
                s.add(FixtureGroup(name=name, cols=i + 1, rows=2,
                                   positions_json='{"0,0": %d}' % i,
                                   folder="Front"))
            s.commit()

    def _gruppen_in_db(self):
        with self.st._session() as s:
            return sorted(g.name for g in s.execute(select(FixtureGroup)).scalars().all())

    def _geraete_patchen(self, labels):
        for i, name in enumerate(labels, start=1):
            self.st.add_fixture(PatchedFixture(
                fid=i, label=name, fixture_profile_id=1, mode_name="m",
                universe=1, address=i * 10, channel_count=8,
                fixture_type="par"), undoable=False)

    def _geraete_in_db(self):
        return sorted(f.label for f in self.st.get_patched_fixtures())

    def _speichern(self):
        SF.save_show(self.pfad)

    def _show_json_aendern(self, aendern):
        """``show.json`` IN der gespeicherten Datei umschreiben, Rest unveraendert.

        Bewusst kein von Hand zusammengebautes ZIP: die Datei bleibt eine echte
        save_show-Ausgabe, nur eben mit einem beschaedigten Feld - so wie sie
        nach einem Absturz oder einer Handbearbeitung auf der Platte liegt."""
        with zipfile.ZipFile(self.pfad, "r") as zf:
            inhalt = [(i.filename, zf.read(i.filename)) for i in zf.infolist()]
        data = json.loads(dict(inhalt)["show.json"].decode("utf-8"))
        aendern(data)
        with zipfile.ZipFile(self.pfad, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, roh in inhalt:
                if name == "show.json":
                    zf.writestr(name, json.dumps(data, ensure_ascii=False))
                else:
                    zf.writestr(name, roh)
        return data

    def _show_json_lesen(self):
        with zipfile.ZipFile(self.pfad, "r") as zf:
            return json.loads(zf.read("show.json").decode("utf-8"))


# ══ STAB-24: Fixture-Gruppen ═════════════════════════════════════════════════

class GruppenTest(_Basis):

    NAMEN = ["Front-Wash", "Back-Spots", "Truss-Bars", "Floor-Pars"]

    def _datei_mit_vier_gruppen(self, beschaedigen=None):
        self._gruppen_anlegen(self.NAMEN)
        self._speichern()
        if beschaedigen is not None:
            self._show_json_aendern(beschaedigen)
        # ★ Vorbedingung: die Datei enthaelt WIRKLICH vier Gruppen-Eintraege.
        data = self._show_json_lesen()
        self.assertEqual(4, len(data["fixture_groups"]),
                         "Die Sonde misst nicht, was sie messen will: die Datei "
                         "haelt gar keine vier Gruppen.")
        SF.reset_show()
        self.assertEqual([], self._gruppen_in_db(),
                         "Ausgangslage nicht leer - die Zaehlung danach waere wertlos.")
        return data

    def test_ein_unlesbares_feld_kostet_nur_seine_eigene_gruppe(self):
        """``cols`` als Text im DRITTEN von vier Eintraegen (Hausregel 4: nicht
        der bequeme Ein-Eintrag-Fall, sondern der Alltagsfall mit mehreren)."""
        def kaputt(data):
            data["fixture_groups"][2]["cols"] = "acht"
        self._datei_mit_vier_gruppen(kaputt)

        ok, msg = SF.load_show(self.pfad)
        uebrig = self._gruppen_in_db()
        print(f"[MESSUNG STAB-24] Datei: 4 Gruppen (1 unlesbar) -> DB: {len(uebrig)} {uebrig}")

        self.assertTrue(ok, msg)
        self.assertEqual(["Back-Spots", "Floor-Pars", "Front-Wash"], uebrig,
                         "Ein einziger unlesbarer Eintrag hat die uebrigen Gruppen "
                         "mitgerissen.")
        self.assertTrue(
            any("Truss-Bars" in p for p in SF.letzte_ladeprobleme()),
            f"Die uebersprungene Gruppe wird nicht gemeldet: {SF.letzte_ladeprobleme()}")
        self.assertIn("konnten nicht gelesen werden", msg,
                      f"load_show meldet glatten Erfolg: {msg!r}")

    def test_eintrag_der_kein_objekt_ist_wird_gemeldet_statt_verschluckt(self):
        """Bisher ein stummes ``continue`` - die Gruppe war weg, ohne ein Wort."""
        def kaputt(data):
            data["fixture_groups"][1] = "Back-Spots"
        self._datei_mit_vier_gruppen(kaputt)

        SF.load_show(self.pfad)
        uebrig = self._gruppen_in_db()
        print(f"[MESSUNG STAB-24b] Datei: 4 Gruppen (1 kein Objekt) -> DB: {len(uebrig)} {uebrig}")

        self.assertEqual(["Floor-Pars", "Front-Wash", "Truss-Bars"], uebrig)
        self.assertEqual(1, len(SF.letzte_ladeprobleme()),
                         "Ein verworfener Gruppen-Eintrag bleibt still - der Nutzer "
                         "erfaehrt es erst, wenn das Speichern es festgeschrieben hat.")
        self.assertIn("Fixture-Gruppe 2", SF.letzte_ladeprobleme()[0],
                      "Die Meldung sagt nicht, WELCHER Eintrag fehlt.")

    def test_gruppen_block_der_keine_liste_ist_wird_gemeldet(self):
        """Der Block ist da, aber unlesbar (Objekt statt Liste) - EINE klare
        Meldung, nicht eine unverstaendliche pro Schluessel."""
        def kaputt(data):
            data["fixture_groups"] = {g["name"]: g for g in data["fixture_groups"]}
        self._gruppen_anlegen(self.NAMEN)
        self._speichern()
        data = self._show_json_aendern(kaputt)
        self.assertNotIsInstance(data["fixture_groups"], list)
        SF.reset_show()

        ok, msg = SF.load_show(self.pfad)
        print(f"[MESSUNG STAB-24d] Gruppen-Block kein Liste -> DB: "
              f"{len(self._gruppen_in_db())}, Ladeprobleme: {SF.letzte_ladeprobleme()}")
        self.assertTrue(ok, msg)
        self.assertEqual(1, len(SF.letzte_ladeprobleme()),
                         f"Erwartet EINE Meldung: {SF.letzte_ladeprobleme()}")
        self.assertIn("Gruppen-Block", SF.letzte_ladeprobleme()[0])

    def test_feld_das_erst_beim_commit_scheitert_kostet_nur_seine_gruppe(self):
        """★ Der zweite Weg um die Regel herum (Hausregel 8): ein Wert, den erst
        SQLite nicht binden kann (``name`` als Liste), wird beim Uebersetzen noch
        nicht bemerkt — er reisst dann die GEMEINSAME Transaktion und damit alle
        uebrigen Gruppen mit, obwohl jeder Eintrag einzeln gebaut wurde."""
        def kaputt(data):
            data["fixture_groups"][2]["name"] = ["Truss-Bars"]
        self._datei_mit_vier_gruppen(kaputt)

        SF.load_show(self.pfad)
        uebrig = self._gruppen_in_db()
        print(f"[MESSUNG STAB-24e] Datei: 4 Gruppen (1 unbindbarer name) -> DB: "
              f"{len(uebrig)} {uebrig}")

        self.assertEqual(["Back-Spots", "Floor-Pars", "Front-Wash"], uebrig,
                         "Ein Feld, das erst beim Commit scheitert, kostet "
                         "weiterhin alle Gruppen.")
        self.assertEqual(1, len(SF.letzte_ladeprobleme()),
                         f"Genau EIN Ausfall erwartet: {SF.letzte_ladeprobleme()}")
        self.assertIn("Fixture-Gruppe 3", SF.letzte_ladeprobleme()[0])

    def test_positions_json_als_objekt_kostet_nur_seine_gruppe(self):
        """Zweite Auspraegung derselben Falle an einem ANDEREN Feld — damit die
        Haertung nicht nur fuer ``name`` gilt."""
        def kaputt(data):
            data["fixture_groups"][0]["positions_json"] = {"0,0": 1}
        self._datei_mit_vier_gruppen(kaputt)

        SF.load_show(self.pfad)
        uebrig = self._gruppen_in_db()
        print(f"[MESSUNG STAB-24f] Datei: 4 Gruppen (1 positions_json als Objekt) "
              f"-> DB: {len(uebrig)} {uebrig}")

        self.assertEqual(["Back-Spots", "Floor-Pars", "Truss-Bars"], uebrig)
        self.assertEqual(1, len(SF.letzte_ladeprobleme()),
                         f"Genau EIN Ausfall erwartet: {SF.letzte_ladeprobleme()}")
        self.assertIn("Front-Wash", SF.letzte_ladeprobleme()[0],
                      "Die Meldung sagt nicht, WELCHE Gruppe fehlt.")

    def test_zwei_kaputte_von_vier_kosten_genau_zwei(self):
        """Gegenprobe zur Einschraenkung 'nur der erste kaputte Eintrag zaehlt'."""
        def kaputt(data):
            data["fixture_groups"][0]["rows"] = "zwei"
            data["fixture_groups"][3]["cols"] = None
        self._datei_mit_vier_gruppen(kaputt)

        SF.load_show(self.pfad)
        uebrig = self._gruppen_in_db()
        print(f"[MESSUNG STAB-24c] Datei: 4 Gruppen (2 unlesbar) -> DB: {len(uebrig)} {uebrig}")

        self.assertEqual(["Back-Spots", "Truss-Bars"], uebrig)
        self.assertEqual(2, len([p for p in SF.letzte_ladeprobleme() if "Gruppe" in p]),
                         f"Nicht beide Ausfaelle gemeldet: {SF.letzte_ladeprobleme()}")

    # ── Positivkontrolle ─────────────────────────────────────────────────────

    def test_saubere_datei_laedt_alle_vier_gruppen_unveraendert(self):
        """Ein Fix, der 'gelingt', indem er nichts mehr laedt, besteht sonst
        jeden Test (Hausregel 5). Gleiche Datei, nur unbeschaedigt."""
        self._datei_mit_vier_gruppen()

        ok, msg = SF.load_show(self.pfad)
        with self.st._session() as s:
            geladen = {g.name: (g.cols, g.rows, g.positions_json, g.folder)
                       for g in s.execute(select(FixtureGroup)).scalars().all()}
        print(f"[MESSUNG STAB-24 Positivkontrolle] Datei: 4 saubere Gruppen -> DB: {len(geladen)}")

        self.assertTrue(ok, msg)
        self.assertEqual(sorted(self.NAMEN), sorted(geladen))
        self.assertEqual((4, 2, '{"0,0": 3}', "Front"), geladen["Truss-Bars"],
                         "Felder einer sauberen Gruppe wurden veraendert.")
        self.assertEqual([], SF.letzte_ladeprobleme(),
                         "Fehlalarm bei sauberer Datei - dann ist die Warnung wertlos.")
        self.assertNotIn("ABER", msg)

    def test_gescheiterte_db_meldet_sich_weiterhin(self):
        """STAB-23-Regress: schlaegt der DB-Zugriff SELBST fehl (kein Eintrags-
        problem), muss das weiterhin gemeldet werden."""
        self._datei_mit_vier_gruppen()

        class _Sperre(Exception):
            pass

        echt = self.st._session
        self.st._session = lambda: (_ for _ in ()).throw(_Sperre("database is locked"))
        try:
            SF.load_show(self.pfad)
        finally:
            self.st._session = echt

        self.assertTrue(any("groups" in p for p in SF.letzte_ladeprobleme()),
                        f"DB-Fehler nicht gemeldet: {SF.letzte_ladeprobleme()}")


# ══ STAB-25: Geraete-Patch ═══════════════════════════════════════════════════

class PatchTest(_Basis):

    LABELS = ["A-Spot 1", "B-Wash 2", "C-Bar 3", "D-Par 4"]

    def _datei_mit_vier_geraeten(self, beschaedigen=None):
        self._geraete_patchen(self.LABELS)
        self._speichern()
        if beschaedigen is not None:
            self._show_json_aendern(beschaedigen)
        SF.reset_show()
        self.assertEqual([], self._geraete_in_db(),
                         "Ausgangslage nicht leer - die Zaehlung danach waere wertlos.")

    def test_patch_block_der_keine_liste_ist_wird_gemeldet(self):
        """★ STAB-25 im Kern: der Block ist da, aber nicht lesbar - bisher fiel
        er durch ein ``if isinstance(...)`` OHNE ``else`` und war einfach weg."""
        def kaputt(data):
            data["patch"] = {str(i): e for i, e in enumerate(data["patch"])}
        self._geraete_patchen(self.LABELS)
        self._speichern()
        data = self._show_json_aendern(kaputt)
        # ★ Vorbedingung: der Block ist vorhanden, enthaelt alle vier Geraete und
        # ist wirklich keine Liste - sonst misst die Sonde einen anderen Fall.
        self.assertEqual(4, len(data["patch"]))
        self.assertNotIsInstance(data["patch"], list)
        SF.reset_show()

        ok, msg = SF.load_show(self.pfad)
        danach = self._geraete_in_db()
        print(f"[MESSUNG STAB-25] Datei: 4 Geraete in unlesbarem Block -> DB: "
              f"{len(danach)} {danach}, Ladeprobleme: {SF.letzte_ladeprobleme()}")

        self.assertTrue(ok, msg)
        self.assertTrue(SF.letzte_ladeprobleme(),
                        "Alle Geraete weg, und kein Wort darueber - das naechste "
                        "Speichern schreibt den Verlust fest.")
        self.assertIn("konnten nicht gelesen werden", msg,
                      f"load_show meldet glatten Erfolg: {msg!r}")
        # ⚠️ EINE klare Meldung ueber den BLOCK - nicht eine pro dict-Schluessel.
        # Ohne diese Zusicherung genuegt es, ueber den kaputten Block zu ITERIEREN
        # (ueber die Schluessel eines dicts, ueber die Zeichen eines Textes): dann
        # steht in der Warnung viermal "Gerät N übersprungen: Eintrag ist kein
        # Objekt, sondern str" und der Nutzer erfaehrt NICHT, was wirklich los ist.
        self.assertEqual(1, len(SF.letzte_ladeprobleme()),
                         f"Erwartet EINE Meldung ueber den Block: "
                         f"{SF.letzte_ladeprobleme()}")
        self.assertIn("Patch-Block", SF.letzte_ladeprobleme()[0])

    def test_patch_block_null_wird_gemeldet(self):
        """Zweite Auspraegung desselben Falls: ``"patch": null``. Bewusst mit
        dabei, weil ein ``data.get("patch") or []`` sie wieder verschluckte."""
        self._geraete_patchen(self.LABELS)
        self._speichern()
        data = self._show_json_aendern(lambda d: d.__setitem__("patch", None))
        self.assertIsNone(data["patch"])
        SF.reset_show()

        ok, msg = SF.load_show(self.pfad)
        print(f"[MESSUNG STAB-25d] patch-Block ist null -> DB: "
              f"{len(self._geraete_in_db())}, Ladeprobleme: {SF.letzte_ladeprobleme()}")
        self.assertTrue(ok, msg)
        self.assertEqual(1, len(SF.letzte_ladeprobleme()),
                         f"Erwartet EINE Meldung: {SF.letzte_ladeprobleme()}")
        self.assertIn("Patch-Block", SF.letzte_ladeprobleme()[0])

    def test_ein_eintrag_der_kein_objekt_ist_kostet_nur_sich_selbst(self):
        def kaputt(data):
            data["patch"][2] = "C-Bar 3"
        self._datei_mit_vier_geraeten(kaputt)

        SF.load_show(self.pfad)
        danach = self._geraete_in_db()
        print(f"[MESSUNG STAB-25b] Datei: 4 Geraete (1 kein Objekt) -> DB: {len(danach)} {danach}")

        self.assertEqual(["A-Spot 1", "B-Wash 2", "D-Par 4"], danach)
        self.assertEqual(1, len(SF.letzte_ladeprobleme()),
                         "Das verworfene Geraet bleibt still - der Nutzer erfaehrt "
                         "es erst nach dem Speichern, also zu spaet.")
        self.assertIn("Gerät 3", SF.letzte_ladeprobleme()[0],
                      "Die Meldung sagt nicht, WELCHES Geraet fehlt.")

    def test_ein_unlesbarer_eintrag_reisst_den_patch_nicht_mit(self):
        """Fehlerinjektion GENAU an einem Eintrag, echter Ladeweg drumherum:
        die Bauschleife war nicht pro Eintrag gekapselt, ein Wurf kostete ALLE
        Geraete."""
        self._datei_mit_vier_geraeten()
        gesehen = []
        echt = SF._patched_fixture_from_data

        def stolpert(d, fallback_fid):
            gesehen.append(d.get("label"))
            if d.get("label") == "C-Bar 3":
                raise ValueError("Feld unlesbar")
            return echt(d, fallback_fid)

        SF._patched_fixture_from_data = stolpert
        try:
            SF.load_show(self.pfad)
        finally:
            SF._patched_fixture_from_data = echt
        danach = self._geraete_in_db()
        print(f"[MESSUNG STAB-25c] Datei: 4 Geraete (1 wirft) -> DB: {len(danach)} {danach}; "
              f"Eintraege gesehen: {gesehen}")

        # ★ Vorbedingung: die Injektion hat den Zieleintrag WIRKLICH erreicht.
        self.assertIn("C-Bar 3", gesehen,
                      "Die Sonde hat den kaputten Eintrag nie beruehrt.")
        self.assertEqual(["A-Spot 1", "B-Wash 2", "D-Par 4"], danach,
                         "Ein kaputter Eintrag kostet weiterhin den ganzen Patch.")
        self.assertEqual(4, len(gesehen),
                         "Die Bauschleife bricht beim kaputten Eintrag weiterhin ab.")
        self.assertEqual(1, len(SF.letzte_ladeprobleme()),
                         f"Genau EIN Ausfall erwartet: {SF.letzte_ladeprobleme()}")
        self.assertIn("C-Bar 3", SF.letzte_ladeprobleme()[0],
                      "Die Meldung sagt nicht, WELCHES Geraet fehlt.")

    # ── Positivkontrolle ─────────────────────────────────────────────────────

    def test_saubere_datei_laedt_alle_vier_geraete_unveraendert(self):
        self._datei_mit_vier_geraeten()

        ok, msg = SF.load_show(self.pfad)
        danach = self._geraete_in_db()
        adressen = sorted((f.label, f.universe, f.address, f.channel_count)
                          for f in self.st.get_patched_fixtures())
        print(f"[MESSUNG STAB-25 Positivkontrolle] Datei: 4 saubere Geraete -> DB: {len(danach)}")

        self.assertTrue(ok, msg)
        self.assertEqual(sorted(self.LABELS), danach)
        self.assertEqual([("A-Spot 1", 1, 10, 8), ("B-Wash 2", 1, 20, 8),
                          ("C-Bar 3", 1, 30, 8), ("D-Par 4", 1, 40, 8)], adressen)
        self.assertEqual([], SF.letzte_ladeprobleme(),
                         "Fehlalarm bei sauberer Datei - dann ist die Warnung wertlos.")
        self.assertNotIn("ABER", msg)

    def test_show_ohne_patch_block_warnt_nicht(self):
        """Gegenprobe: FEHLT der Block ganz (Alt-Show/Teil-Show), ist das kein
        Ladeproblem - sonst warnt die UI bei Dateien, denen nichts fehlt."""
        self._geraete_patchen(self.LABELS)
        self._speichern()
        self._show_json_aendern(lambda data: data.pop("patch"))
        SF.reset_show()

        ok, msg = SF.load_show(self.pfad)
        print(f"[MESSUNG STAB-25 Gegenprobe] ohne patch-Block -> Ladeprobleme: "
              f"{SF.letzte_ladeprobleme()}")
        self.assertTrue(ok, msg)
        self.assertEqual([], SF.letzte_ladeprobleme())


if __name__ == "__main__":
    unittest.main()
