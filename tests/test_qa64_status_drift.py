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
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import backlog_status_drift as bsd          # noqa: E402
from backlog_status_drift import (          # noqa: E402
    REVIEW_SPUR_AUF_MAIN, SPUR, ZWEIG, neuere_fassungen, spur_urteil,
    status_klasse, zeilen_mit_items)


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
        for s in ("✅ done (2026-08-24)", "done", "done → Archiv",
                  # Ein Haken VOR einem unbekannten Leitwort zaehlt weiter.
                  "✅ verifiziert → 🎨 Design"):
            self.assertEqual(status_klasse(s), "erledigt", s)

    def test_ein_haken_im_fliesstext_macht_teils_nicht_fertig(self):
        """★★ CDX-57, von Codex gefunden — der Grund fuer das Leitwort.

        Die erste Fassung fragte ``any(k in s for k in ("done", "✅"))``. Jede
        Zelle, die IRGENDWO einen Haken fuer einen fertigen TEILschritt nennt,
        galt damit als erledigt. Gemessen auf `main` 28e137f2: sieben Items
        stehen so da (VIZ-15, VIZ-PERF2, VIZ-BEAM-OCCLUSION, FM-20, FM-13,
        XPLAT-19, DOC-10). Sobald eines eine Spur bekaeme, verlangte der
        Waechter sie faelschlich auf `main`.
        """
        for s in (
                "teils (**Kegel-Laengs-Falloff ✅ 2026-08-05**; Bloom offen)",
                "teils — **Teil 1 ✅ done (2026-08-05)**: Rest offen",
                "teils (Diagnose ✅ 2026-08-05; Ursache weiter offen)",
                "✅ teils (2026-08-11)"):
            self.assertEqual(status_klasse(s), "unterwegs", s)

    def test_dieselbe_aussage_bekommt_dieselbe_klasse(self):
        """★ Die zweite Form, die Codex fand: `teils` OHNE Haken (QA-LIVE,
        LAS-08) landete in einer ANDEREN Klasse als `✅ teils` — zwei Zellen mit
        derselben Aussage, zwei verschiedene Urteile.
        """
        self.assertEqual(status_klasse("teils (2026-07-09)"),
                         status_klasse("✅ teils (2026-07-09)"))

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
        self.assertEqual(status_klasse("done (2026-08-25, review folgt)"),
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

    def test_review_items_im_echten_backlog_werden_als_review_gelesen(self):
        """Die QA-65-Klasse am echten Backlog — ohne Zeitbombe.

        ★★ **Die erste Fassung war invertiert** und stand als Zeitbombe ohne
        Datum: sie verlangte ``assertGreater(len(review), 0)`` und wurde damit
        ausgerechnet von dem Zustand rot gemacht, den QA-65 herstellen will —
        kein Item mehr faelschlich auf ``review``. Der GESUNDE Fall darf nicht
        beanstandet werden. Die Wache haengt deshalb jetzt an einer Eigenschaft
        des WERKZEUGS, nicht am Aufraeumgrad des Backlogs: gibt es
        ``review``-Items, muessen sie so gelesen werden; gibt es keine, ist
        nichts zu pruefen. Dass die Klasse ueberhaupt existiert, nagelt
        ``StatusKlasseTest`` an Nachbildungen fest — dafuer braucht es den
        echten Backlog nicht.
        """
        review = [(i, s) for i, s, _z in self.items
                  if status_klasse(s) == "review"]
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


class NeuereFassungTest(unittest.TestCase):
    """★★ CDX-57, von Codex gefunden: die ``-vN``-Suche uebersah die naechste
    Fassung. ``x.startswith(b + "-v")`` sucht bei ``…-v3`` nach ``…-v3-v…`` —
    ein ``-v4`` faellt durch, und genau das ist der Fall, der zaehlt.
    """

    ZWEIGE = {"feature/ring", "feature/ring-v2", "feature/ring-v3",
              "feature/ring-v4", "feature/ring-v10", "feature/anderes-v9"}

    def test_findet_die_naechste_fassung_einer_vN_behauptung(self):
        self.assertEqual(neuere_fassungen("feature/ring-v3", self.ZWEIGE),
                         ["feature/ring-v4", "feature/ring-v10"])

    def test_ohne_suffix_ist_fassung_1(self):
        self.assertEqual(neuere_fassungen("feature/ring", self.ZWEIGE),
                         ["feature/ring-v2", "feature/ring-v3",
                          "feature/ring-v4", "feature/ring-v10"])

    def test_numerisch_sortiert_nicht_alphabetisch(self):
        # Alphabetisch stuende `-v10` vor `-v2`; die Meldung nennt dann die
        # falsche „neueste" Fassung.
        self.assertEqual(neuere_fassungen("feature/ring-v9", self.ZWEIGE),
                         ["feature/ring-v10"])

    def test_ein_fremder_stamm_ist_keine_neuere_fassung(self):
        self.assertEqual(neuere_fassungen("feature/anderes-v9", self.ZWEIGE), [])

    def test_die_juengste_fassung_hat_keine_juengere(self):
        # Positivkontrolle: der GESUNDE Fall darf nicht beanstandet werden.
        self.assertEqual(neuere_fassungen("feature/ring-v10", self.ZWEIGE), [])


class WerkzeugEndeZuEndeTest(unittest.TestCase):
    """★★ Der ECHTE Weg: ``main(["--strict"])``, gemessen an Exit-Code und Bericht.

    Alle Regeltests darueber rufen ``spur_urteil``/``status_klasse`` direkt. Das
    laesst ``main()`` selbst ungeprueft — und der Pruefer hat vorgefuehrt, was
    das kostet: haengt man in die Spur-Schleife von ``main()``, direkt nach
    ``klasse = status_klasse(status)``, ein ``if klasse == "review": continue``
    (also den QA-65-Fehler eine Ebene tiefer), bleiben die Regeltests gruen und
    das Werkzeug meldet „keine Drift" mit Exit 0.

    Der Griff nach dem echten Repo ist ersetzt, nicht die Logik: ``BACKLOG``
    zeigt auf eine temporaere Tabelle, ``_git``/``spur_auf_main``/
    ``zweige_auf_origin`` sind die Naht zum Netz. Alles dazwischen — Einlesen,
    Klassifizieren, Urteilen, Berichten, Exit-Code — ist der Produktionscode.
    Damit laeuft diese Probe auch in der CI, wo es keine Refs gibt.
    """

    KOPF = ("| ID | Prio | Status | Titel | Details |\n"
            "|---|---|---|---|---|\n")
    SPUR_TXT = "tools/backlog_status_drift.py :: REVIEW_SPUR_AUF_MAIN"
    SPUR_KEY = ("tools/backlog_status_drift.py", "REVIEW_SPUR_AUF_MAIN")
    GELANDET = (
        "| QA-65 | P2 | review (PR [#668](https://example/pull/668)) | Waechter"
        " | Text <!-- spur: " + SPUR_TXT + " --> |\n")

    def _lauf(self, tabelle, spuren_auf_main, fetch_rc=0, argv=("--strict",)):
        """Faehrt das Werkzeug wie die Kommandozeile. ``(Exit-Code, Bericht)``."""
        verz = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, verz)
        pfad = os.path.join(verz, "BACKLOG.md")
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(self.KOPF + tabelle)

        gerufen = []
        # ★ Aus der Gegenpruefung: `zweige_auf_origin` war fest auf `set()`
        # gepatcht — damit schnitt der Harnisch die ZWEITE der beiden Pruefungen
        # (die Zweig-Behauptung) ab, und der Fix dafuer war nur an der
        # ausgelagerten Funktion gemessen, nicht auf dem Weg durch `main()`.
        # Jetzt kann jeder Fall seine Zweigliste mitgeben.
        self.zweige = getattr(self, "zweige", ())

        def falsches_git(*args):
            gerufen.append(args)
            if args[:1] == ("fetch",):
                return fetch_rc, ""
            if args[:1] == ("rev-parse",):
                return 0, "0123456789abcdef\n"
            raise AssertionError(f"unerwarteter git-Aufruf: {args}")

        puffer = io.StringIO()
        with mock.patch.object(bsd, "BACKLOG", pfad), \
                mock.patch.object(bsd, "_git", falsches_git), \
                mock.patch.object(bsd, "spur_auf_main",
                                  lambda d, k: (d, k) in spuren_auf_main), \
                mock.patch.object(bsd, "zweige_auf_origin",
                                  lambda: set(self.zweige)), \
                contextlib.redirect_stdout(puffer):
            rc = bsd.main(list(argv))
        self.gerufen = gerufen
        return rc, puffer.getvalue()

    # ── Die Abnahmebedingung von QA-65, am Werkzeug gemessen ────────────────
    def test_gelandetes_item_auf_review_macht_das_werkzeug_rot(self):
        rc, bericht = self._lauf(self.GELANDET, {self.SPUR_KEY})
        self.assertEqual(rc, 1, bericht)
        self.assertIn("1 Drift(s)", bericht)
        self.assertIn("QA-65: " + REVIEW_SPUR_AUF_MAIN, bericht)
        self.assertIn(self.SPUR_TXT, bericht)
        self.assertNotIn("keine Drift", bericht)

    def test_ohne_strict_bleibt_der_exit_code_0_der_fund_steht_trotzdem(self):
        # Der Bericht ist der Standardlauf; erst `--strict` macht daraus ein Gate.
        rc, bericht = self._lauf(self.GELANDET, {self.SPUR_KEY}, argv=())
        self.assertEqual(rc, 0, bericht)
        self.assertIn("QA-65: " + REVIEW_SPUR_AUF_MAIN, bericht)

    # ── Positivkontrolle: der GESUNDE Backlog darf nicht rot werden ─────────
    def test_laufendes_review_item_ohne_spur_auf_main_ist_keine_drift(self):
        rc, bericht = self._lauf(self.GELANDET, set())
        self.assertEqual(rc, 0, bericht)
        self.assertIn("✓ keine Drift", bericht)

    def test_sauberer_backlog_meldet_nichts_und_nennt_die_abdeckung(self):
        tabelle = (
            "| QA-63 | P2 | ✅ done (2026-08-24) | Fertig |"
            " Text <!-- spur: tools/zeitbomben_gate.py --> |\n"
            "| FM-30 | P2 | todo | Offen |"
            " Text <!-- spur: src/ui/widgets/fixture_generator.py :: grid_rows --> |\n"
            "| HW-1 | P1 | blocked (Hardware) | Wartet | ohne Spur |\n")
        rc, bericht = self._lauf(tabelle, {("tools/zeitbomben_gate.py", None)})
        self.assertEqual(rc, 0, bericht)
        self.assertIn("✓ keine Drift", bericht)
        self.assertIn("2 von 3 Items haben eine Spur", bericht)
        self.assertIn("beurteilt: 2", bericht)

    def test_die_abdeckungszeile_nennt_die_BEURTEILTEN_nicht_nur_die_spuren(self):
        """★ Aus der Gegenpruefung: die Zeile sagte „19 von 478 Items haben eine
        Spur", waehrend nur 15 davon ueberhaupt ein Urteil bekamen — die
        restlichen vier lagen an Items der Freibrief-Klasse (`teils`, `blocked`,
        `decision`). In kleiner Form war damit genau der Fleck zurueck, gegen den
        diese Zeile gebaut ist: eine Zahl, die mehr Pruefung behauptet, als
        stattfindet.
        """
        tabelle = (
            "| QA-63 | P2 | ✅ done (2026-08-24) | Fertig |"
            " Text <!-- spur: tools/zeitbomben_gate.py --> |\n"
            "| VIZ-15 | P2 | teils (Teil 1 ✅) | Halb |"
            " Text <!-- spur: tools/zeitbomben_gate.py --> |\n"
            "| HW-1 | P1 | blocked (Hardware) | Wartet |"
            " Text <!-- spur: tools/zeitbomben_gate.py --> |\n")
        rc, bericht = self._lauf(tabelle, {("tools/zeitbomben_gate.py", None)})
        self.assertEqual(rc, 0, bericht)
        self.assertIn("3 von 3 Items haben eine Spur", bericht)
        self.assertIn("beurteilt: 1", bericht)
        self.assertIn("ohne Urteil (Freibrief-Klasse): 2", bericht)

    # ── Die ZWEITE Pruefung des Werkzeugs, jetzt auch end-zu-ende ──────────
    def test_eine_neuere_zweigfassung_macht_das_werkzeug_rot(self):
        """★ Der Codex-Befund, gemessen auf dem Weg durch ``main()``.

        Vorher lief die Zweig-Behauptung nur ueber die ausgelagerte Funktion —
        also an der Naht. Drei Mutationen im Werkzeug blieben deshalb gruen.
        """
        self.zweige = ("feature/ring-v3", "feature/ring-v4")
        tabelle = ("| FM-14b | P3 | review (Umsetzung auf `feature/ring-v3`) |"
                   " Ring | ohne Spur |\n")
        rc, bericht = self._lauf(tabelle, set(), argv=("--strict",))
        self.assertEqual(rc, 1, bericht)
        self.assertIn("neuere Fassung", bericht)
        self.assertIn("feature/ring-v4", bericht)

    def test_ein_genannter_zweig_der_gar_nicht_existiert_macht_rot(self):
        self.zweige = ("feature/etwas-anderes",)
        tabelle = ("| FM-14b | P3 | review (Umsetzung auf `feature/weg`) |"
                   " Ring | ohne Spur |\n")
        rc, bericht = self._lauf(tabelle, set(), argv=("--strict",))
        self.assertEqual(rc, 1, bericht)
        self.assertIn("existiert auf origin nicht", bericht)

    def test_der_neueste_zweig_wird_NICHT_beanstandet(self):
        # Positivkontrolle: sonst meldete das Werkzeug bei jedem Item mit
        # Zweig-Angabe, und niemand traegt sie mehr ein.
        self.zweige = ("feature/ring-v3",)
        tabelle = ("| FM-14b | P3 | review (Umsetzung auf `feature/ring-v3`) |"
                   " Ring | ohne Spur |\n")
        rc, bericht = self._lauf(tabelle, set(), argv=("--strict",))
        self.assertEqual(rc, 0, bericht)
        self.assertIn("✓ keine Drift", bericht)

    def test_ohne_freibrief_items_steht_kein_zusatz_in_der_zeile(self):
        # Positivkontrolle: der Normalfall soll die Zeile nicht laenger machen.
        tabelle = ("| QA-63 | P2 | ✅ done (2026-08-24) | Fertig |"
                   " Text <!-- spur: tools/zeitbomben_gate.py --> |\n")
        _rc, bericht = self._lauf(tabelle, {("tools/zeitbomben_gate.py", None)})
        self.assertIn("beurteilt: 1", bericht)
        self.assertNotIn("Freibrief-Klasse", bericht)

    def test_ein_teils_item_mit_haken_im_text_wird_nicht_beanstandet(self):
        """★ CDX-57 am ECHTEN Weg: sieben `teils`-Items nennen ein `✅` im
        Fliesstext. Galten sie als erledigt, verlangte das Werkzeug ihre Spur
        auf `main` — hier liegt sie NICHT dort, und trotzdem ist das kein Fund.
        """
        tabelle = ("| VIZ-15 | P2 | teils (Falloff ✅ 2026-08-05; Bloom offen)"
                   " | Teilweise | Text <!-- spur: src/core/viz/beam.py --> |\n")
        rc, bericht = self._lauf(tabelle, set())
        self.assertEqual(rc, 0, bericht)
        self.assertIn("✓ keine Drift", bericht)

    # ── CDX-57: ein fehlgeschlagenes `git fetch` bleibt nicht folgenlos ─────
    def test_fehlgeschlagenes_fetch_bricht_ab_statt_zu_urteilen(self):
        """*Fail closed*, gleiche Behandlung wie `tools/backlog_ids.py` (#670).

        Mit veralteten Refs meldet das Werkzeug eine gerade GELANDETE Spur als
        „fehlt" — ein Fehlalarm genau gegen die Items, die eben durchgegangen
        sind. Vorher blieb der Fehlschlag folgenlos.
        """
        rc, bericht = self._lauf(self.GELANDET, {self.SPUR_KEY}, fetch_rc=1)
        self.assertEqual(rc, 2, bericht)
        self.assertIn("`git fetch` fehlgeschlagen", bericht)
        self.assertNotIn("keine Drift", bericht)
        self.assertNotIn("Drift(s)", bericht)

    def test_kein_fetch_faehrt_bewusst_auf_dem_geholten_stand(self):
        # Positivkontrolle zur Sperre: der Ausweg existiert und holt nicht.
        rc, bericht = self._lauf(self.GELANDET, {self.SPUR_KEY},
                                 fetch_rc=1, argv=("--strict", "--kein-fetch"))
        self.assertEqual(rc, 1, bericht)
        self.assertEqual([a for a in self.gerufen if a[:1] == ("fetch",)], [])



if __name__ == "__main__":
    unittest.main()
