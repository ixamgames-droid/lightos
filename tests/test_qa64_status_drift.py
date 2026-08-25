"""QA-64 — die Logik des Backlog-Drift-Waechters ist festgenagelt.

Was hier geprueft wird und was NICHT
------------------------------------
``tools/backlog_status_drift.py`` beantwortet zwei Fragen, und beide brauchen
Git-Refs, die es in der CI nicht gibt: ``actions/checkout@v4`` holt
standardmaessig **einen** Commit ohne weitere Refs — kein ``origin/main``, keine
Zweigliste. Ein Test, der dort still ueberspringt, waere die Sorte Absicherung,
die dieses Repo schon zweimal teuer bezahlt hat (PROC-02b, PROC-04): sie laeuft,
wird gruen und wirkt nicht.

Deshalb die Trennung: das **Werkzeug** greift nach dem echten Repo, dieser
**Test** nagelt seine Entscheidungsregeln an Nachbildungen fest — beide
Richtungen, plus die Formen, die es NICHT beanstanden darf.

★★ **QA-65 hat die Regel geschaerft, und dieser Test ist der Grund, warum das
auffiel.** Die erste Fassung gab jedem Status zwischen ``todo`` und ``done``
einen Freibrief in beide Richtungen — festgehalten in
``test_unterwegs_wird_in_keiner_richtung_beanstandet``. Die eine Richtung war
richtig, die andere blind: ``review`` + Spur AUF ``main`` heisst, der PR ist
gelandet und nur der Status wurde nie nachgezogen. Am 25.08.2026 standen neun
Items genau so da. Seither ist ``review`` eine eigene Klasse; ``blocked`` und
``decision`` behalten den Freibrief (Begruendung samt Messung im Docstring des
Werkzeugs).

★ Die Regeln stecken absichtlich in eigenen, ref-freien Funktionen
(``zeilen_mit_items``, ``status_klasse``, ``spur_urteil``, ``SPUR``, ``ZWEIG``).
Waeren sie in der Hauptschleife verwoben, koennte dieser Test nur den Aufruf
nachbilden — und pruefte dann seine eigene Nachbildung statt des Produktionscodes
(QA-52).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

from backlog_status_drift import (          # noqa: E402
    REVIEW_SPUR_AUF_MAIN, SPUR, ZWEIG, spur_urteil, status_klasse,
    zeilen_mit_items)


TABELLE = """
| ID | Prio | Status | Titel | Details |
|---|---|---|---|---|
| QA-63 | P2 | ✅ done (2026-08-24) | Waechter | Text <!-- spur: tools/zeitbomben_gate.py --> |
| FM-26 | P2 | todo | Generator | Text <!-- spur: src/ui/widgets/fixture_generator.py :: grid_rows --> |
| FM-14b | P3 | review (Umsetzung auf `feature/fm14b-ring-bedienung-v3`) | Ring | Text <!-- spur: tests/test_fm14b_ring.py --> |
| HW-1 | P1 | blocked (Hardware) | Kopf-Reihenfolge | Ohne Spur, ohne Zweig |
"""


class ZeilenTest(unittest.TestCase):
    def test_findet_genau_die_item_zeilen(self):
        ids = [i for i, _s, _z in zeilen_mit_items(TABELLE)]
        self.assertEqual(ids, ["QA-63", "FM-26", "FM-14b", "HW-1"])

    def test_kopf_und_trennzeile_sind_keine_items(self):
        # `| ID | Prio | ...` und `|---|---|` beginnen beide mit "| " — ohne die
        # ID-Form als Filter waeren sie zwei Geister-Items in jedem Bericht.
        ids = [i for i, _s, _z in zeilen_mit_items(TABELLE)]
        self.assertNotIn("ID", ids)
        self.assertNotIn("---", ids)

    def test_fliesstext_ausserhalb_der_tabelle_zaehlt_nicht(self):
        self.assertEqual(zeilen_mit_items("Ein Satz ueber | Striche | im Text."), [])


class StatusKlasseTest(unittest.TestCase):
    def test_erledigt(self):
        for s in ("✅ done (2026-08-24)", "done", "✅ teils (2026-08-11)",
                  "done → Archiv"):
            self.assertEqual(status_klasse(s), "erledigt", s)

    def test_offen(self):
        self.assertEqual(status_klasse("todo"), "offen")

    def test_review_ist_eine_eigene_klasse(self):
        # ★ QA-65. `review` behauptet etwas Pruefbares: „liegt in einem PR, ist
        # NICHT gelandet". Nur deshalb kann eine Spur auf `main` dem Status
        # widersprechen. `blocked`/`decision` behaupten das nicht.
        for s in ("review (Umsetzung auf `x`)", "review (PR #660)",
                  "review (Werkzeug in [#664](https://example/pull/664))"):
            self.assertEqual(status_klasse(s), "review", s)

    def test_blocked_und_decision_bleiben_ohne_urteil(self):
        # Wer hier „offen" oder „erledigt" erzwingt, erzeugt Fehlalarme fuer
        # jedes Item, das auf Hardware oder eine Entscheidung wartet.
        for s in ("blocked (Hardware)", "blocked (Robin — Produktentscheidung)",
                  "decision (Produktentscheidung + Hardware)"):
            self.assertEqual(status_klasse(s), "unterwegs", s)

    def test_erledigt_schlaegt_review(self):
        # `startswith` fuer REVIEW, und die Erledigt-Probe steht davor: ein
        # Status „done (Rest ging in review)" ist erledigt, nicht `review` —
        # sonst wuerde ausgerechnet ein FERTIGES Item beanstandet.
        self.assertEqual(status_klasse("✅ done (Rest ging in review)"),
                         "erledigt")
        self.assertEqual(status_klasse("✅ teils (2026-08-25, [#664](…))"),
                         "erledigt")

    def test_todo_als_teil_eines_wortes_zaehlt_nicht_als_offen(self):
        # `startswith` statt `in`: sonst faengt ein Status wie
        # „done (Rest als todo ausgelagert)" beide Klassen.
        self.assertEqual(status_klasse("done (Rest als todo ausgelagert)"), "erledigt")


class SpurUrteilTest(unittest.TestCase):
    """Die eigentliche Aussage des Werkzeugs — beide Richtungen."""

    def test_erledigt_ohne_spur_auf_main_ist_drift(self):
        self.assertIsNotNone(spur_urteil("erledigt", auf_main=False))

    def test_todo_mit_spur_auf_main_ist_drift(self):
        self.assertIsNotNone(spur_urteil("offen", auf_main=True))

    # ── Positivkontrolle: die gesunden Faelle MUESSEN durchgehen ────────────
    def test_erledigt_mit_spur_auf_main_ist_in_ordnung(self):
        self.assertIsNone(spur_urteil("erledigt", auf_main=True))

    def test_todo_ohne_spur_auf_main_ist_in_ordnung(self):
        self.assertIsNone(spur_urteil("offen", auf_main=False))

    def test_review_mit_spur_auf_main_ist_drift(self):
        """★★ QA-65 — der haeufigste Drift-Fall, den QA-64 per Bauart uebersah.

        Die Spur ist auf `main`, der Status sagt trotzdem „liegt im PR": der PR
        ist gelandet, nur der Status wurde nie nachgezogen. Am 25.08.2026 traf
        das auf NEUN Items zugleich zu, und der Bericht meldete „keine Drift".
        """
        self.assertEqual(spur_urteil("review", auf_main=True),
                         REVIEW_SPUR_AUF_MAIN)

    def test_review_ohne_spur_auf_main_ist_in_ordnung(self):
        # ★ Die Gegenrichtung. Ein Item, an dem gerade jemand arbeitet, hat
        # seine Spur naturgemaess NICHT auf main. Wer beide Richtungen meldet,
        # hat einen Waechter gebaut, der bei JEDEM laufenden PR anschlaegt —
        # der wird abgeschaltet.
        self.assertIsNone(spur_urteil("review", auf_main=False))

    def test_blocked_und_decision_werden_in_keiner_richtung_beanstandet(self):
        # Gemessen (25.08.2026): von den 11 `blocked`/`decision`-Items nennen
        # vier ueberhaupt Dateien, und alle 8 genannten liegen bereits auf
        # `main`. Diese Status behaupten keinen offenen PR, sondern dass jemand
        # auf Hardware/Entscheidung wartet — die Vorarbeit darf gelandet sein.
        # Dieselbe Schaerfung haette dort 4 Fehlalarme und 0 Funde gebracht.
        self.assertIsNone(spur_urteil("unterwegs", auf_main=True))
        self.assertIsNone(spur_urteil("unterwegs", auf_main=False))


class SpurSyntaxTest(unittest.TestCase):
    def test_datei_und_kennzeichen(self):
        m = SPUR.search("Text <!-- spur: src/core/app_state.py :: white_grid_for -->")
        self.assertEqual(m.group(1), "src/core/app_state.py")
        self.assertEqual(m.group(2), "white_grid_for")

    def test_nur_datei(self):
        m = SPUR.search("Text <!-- spur: tools/zeitbomben_gate.py -->")
        self.assertEqual(m.group(1), "tools/zeitbomben_gate.py")
        self.assertIsNone(m.group(2))

    def test_kennzeichen_darf_sonderzeichen_tragen(self):
        # `9>&-` ist die Spur von PROC-02d. Wer hier zu eng parst, verliert
        # ausgerechnet die Spuren der interessanten Items.
        m = SPUR.search("Text <!-- spur: tools/verify_segmented.sh :: 9>&- -->")
        self.assertEqual(m.group(1), "tools/verify_segmented.sh")
        self.assertEqual(m.group(2), "9>&-")

    def test_zeile_ohne_spur_liefert_nichts(self):
        self.assertIsNone(SPUR.search("| HW-1 | P1 | blocked | Kopf | Text |"))


class ZweigBehauptungTest(unittest.TestCase):
    def test_liest_den_zweig_aus_dem_status(self):
        m = ZWEIG.search("review (Umsetzung auf `feature/fm14b-ring-bedienung-v3`)")
        self.assertEqual(m.group(1), "feature/fm14b-ring-bedienung-v3")

    def test_ein_dateipfad_in_der_beschreibung_ist_KEIN_zweig(self):
        # ★ Der Grund fuer den engen Zuschnitt. Die erste Fassung las jeden
        # Backtick der Form `a/b` als Zweignamen und beanstandete 60 Zeilen,
        # fast alle davon gewoehnliche Dateipfade. Der enge Zuschnitt fand
        # dieselbe eine echte Drift und sonst nichts.
        for text in ("`tools/verify_loop.sh` setzt die Variable",
                     "steht in `docs/FIXTURE_LIBRARY.md`",
                     "`src/ui/views/live_view.py:160`"):
            self.assertIsNone(ZWEIG.search(text), text)


class EchterBacklogTest(unittest.TestCase):
    """Der Griff nach der ECHTEN Datei — soweit er ohne Git-Refs geht."""

    def setUp(self):
        pfad = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "BACKLOG.md")
        with open(pfad, encoding="utf-8") as f:
            self.items = zeilen_mit_items(f.read())

    def test_der_echte_backlog_liefert_ueberhaupt_items(self):
        # Ohne diese Wache waeren alle Aussagen unten trivial wahr.
        self.assertGreater(len(self.items), 100)

    def test_spur_eines_erledigten_items_zeigt_auf_eine_vorhandene_datei(self):
        """Eine Spur mit Tippfehler kann nie erfuellt werden.

        ★ Die erste Fassung dieses Tests verlangte die Datei fuer JEDES Item —
        und war damit falsch: die Spur eines OFFENEN Items zeigt naturgemaess
        auf etwas, das es noch nicht gibt (FM-14b zeigt auf eine Testdatei, die
        nur auf ihrem Zweig liegt). Genau dafuer ist die Spur ja da. Verlangt
        wird die Datei deshalb nur dort, wo der Status behauptet, sie sei
        gelandet.
        """
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        fehlend, gefunden = [], 0
        for item, status, zeile in self.items:
            m = SPUR.search(zeile)
            if not m or status_klasse(status) != "erledigt":
                continue
            gefunden += 1
            if not os.path.exists(os.path.join(wurzel, m.group(1))):
                fehlend.append(f"{item} -> {m.group(1)}")
        self.assertGreater(gefunden, 0, "kein erledigtes Item mit Spur gefunden")
        self.assertEqual(fehlend, [], f"Spuren ohne Datei: {fehlend}")

    def test_es_gibt_ueberhaupt_review_items_und_sie_werden_so_gelesen(self):
        """Wache gegen Leerlauf fuer die QA-65-Regel.

        Die Regel kann nur greifen, wenn ``status_klasse`` im ECHTEN Backlog
        auch wirklich ``review`` zurueckgibt. Die Schwelle ist abgeleitet, nicht
        gesetzt: es genuegt, dass es die Klasse ueberhaupt gibt — wie viele
        Items gerade in einem PR liegen, schwankt taeglich.
        """
        review = [(i, s) for i, s, _z in self.items
                  if status_klasse(s) == "review"]
        self.assertGreater(len(review), 0,
                           "kein Item auf `review` — dann prueft die QA-65-Regel"
                           " im echten Backlog nichts")
        for item, status in review:
            self.assertTrue(status.lower().startswith("review"), f"{item}: {status}")
            self.assertNotIn("✅", status, f"{item}: erledigt UND review?")

    def test_spur_eines_offenen_items_zeigt_wenigstens_in_ein_vorhandenes_verzeichnis(self):
        """Der Tippfehler-Fang fuer noch nicht gelandete Arbeit.

        Die Datei darf fehlen, das Verzeichnis nicht — ``tets/…`` oder
        ``src/ui/wigets/…`` faellt damit sofort auf, statt erst dann, wenn das
        Item landet und der Waechter es faelschlich als „nicht gelandet" meldet.
        """
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        schlecht = []
        for item, status, zeile in self.items:
            m = SPUR.search(zeile)
            if not m or status_klasse(status) == "erledigt":
                continue
            ordner = os.path.dirname(os.path.join(wurzel, m.group(1)))
            if not os.path.isdir(ordner):
                schlecht.append(f"{item} -> {m.group(1)}")
        self.assertEqual(schlecht, [], f"Spuren in unbekanntem Verzeichnis: {schlecht}")


if __name__ == "__main__":
    unittest.main()
