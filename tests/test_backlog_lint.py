"""QA-18: Backlog-Linter — ID-/Status-/PR-Link-Konsistenz in BACKLOG.md.

Verhindert, dass eine Tabellenzeile einen unbekannten/leeren Status bekommt oder
ein kaputter PR-/Issue-Link als „erledigt" durchgeht. Bewusst LENIENT: der Status
darf dekoriert sein (✅, Datum, PR-Link, Fortschritt „wip (3/8)") — geprueft wird
nur, dass irgendein anerkanntes Status-Keyword vorkommt und dass jeder GitHub-Link
im Status wohlgeformt ist. Historische Detailnotizen bleiben so als Log-Zeilen zu-
laessig (QA-18-Vorgabe). Tote Querverweise deckt QA-17 (`test_doc_links.py`) ab.
"""
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKLOG = os.path.join(REPO, "BACKLOG.md")

# Tabellenzeile: | <ID> | <Prio> | <Status> | … |  (ID darf mehrere Segmente haben,
# z.B. QA-P95-FLAKE, VIZ-MASTER-FEEDBACK).
# Muss mit tools/backlog_compact.py::ROW deckungsgleich bleiben — inkl. des
# optionalen Kleinbuchstaben-Suffix fuer Unterpunkte (LAS-18b, CDX-22b, …).
ROW = re.compile(r"^\|\s*([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+[a-z]?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|")
# Anerkannte Status-Keywords (irgendwo in der Status-Zelle, case-insensitiv).
STATUS_KEYWORDS = ("todo", "done", "wip", "review", "blocked", "decision",
                   "teils", "teil", "defer", "verifiziert", "reproduzierbar", "n/a")
PRIOS = ("P1", "P2", "P3")
GH_LINK = re.compile(r"\]\((https?://github\.com/[^)]+)\)")
GH_PR_ISSUE_OK = re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+/(pull|issues)/\d+")
# QA-18b: "GELANDET" ist die projektweite Vokabel fuer "ist gemergt" (Loop-Runden
# schreiben sie in die Zeile, wenn eine Teil-Lieferung in main ist).
LANDED = re.compile(r"gelandet", re.IGNORECASE)
# QA-18d/QA-55: "sieht aus wie ein Item" — bewusst VIEL breiter als ``ROW``.
# Auf Modulebene, damit der QA-55-Test es benutzen kann statt es nachzubauen:
# ein Test, der das Muster nachbildet, prueft seine eigene Kopie und bleibt
# gruen, wenn das Original zurueckfaellt (genau so blieb die Mutation hier
# zuerst unentdeckt — Fehlerklasse QA-52).
LOOKS_LIKE_ITEM = re.compile(r"^\|\s*([^|]+?)\s*\|\s*\**\s*(P[123])\b")


def _rows():
    with open(BACKLOG, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            m = ROW.match(line)
            if not m:
                continue
            prio = m.group(2).strip().strip("* ").strip()   # **P1** -> P1
            # Kopf-/Trennzeilen der Tabelle ueberspringen (|----|).
            if set(m.group(2).strip()) <= set("-: "):
                continue
            yield lineno, m.group(1), prio, m.group(3).strip()


def _rows_with_line():
    """Wie _rows(), aber mit der kompletten Zeile (fuer Status-vs-Inhalt-Checks)."""
    with open(BACKLOG, "r", encoding="utf-8") as f:
        lines = f.readlines()
    for lineno, id_, prio, status in _rows():
        yield lineno, id_, prio, status, lines[lineno - 1]


class BacklogLintTest(unittest.TestCase):
    def test_backlog_exists_and_has_rows(self):
        self.assertTrue(os.path.exists(BACKLOG))
        self.assertGreater(len(list(_rows())), 10, "kaum Tabellenzeilen erkannt")

    def test_every_row_has_valid_prio(self):
        bad = [(ln, i, p) for ln, i, p, _s in _rows() if p not in PRIOS]
        self.assertEqual(bad, [], f"Zeilen mit ungueltiger Prio (nicht P1/P2/P3): {bad}")

    def test_every_row_has_recognized_status(self):
        bad = []
        for ln, id_, _p, status in _rows():
            low = status.lower()
            if not any(kw in low for kw in STATUS_KEYWORDS):
                bad.append((ln, id_, status))
        self.assertEqual(bad, [], f"Zeilen mit unbekanntem Status-Keyword: {bad}")

    def test_status_github_links_are_wellformed_pr_or_issue(self):
        bad = []
        for ln, id_, _p, status in _rows():
            for url in GH_LINK.findall(status):
                if not GH_PR_ISSUE_OK.match(url):
                    bad.append((ln, id_, url))
        self.assertEqual(bad, [], f"Status-GitHub-Links, die kein wohlgeformter "
                                  f"pull/issues-Link sind: {bad}")

    def test_todo_rows_do_not_claim_landed_work(self):
        """QA-18b: 'todo' und 'GELANDET' in derselben Zeile widersprechen sich.

        Wiederkehrender Loop-Fehler (bis 2026-07-27 fuenfmal): eine Teil-Lieferung
        wird in die Zeile geschrieben, der Status bleibt 'todo' — `--queue` bietet
        das Item dann als naechste Aufgabe an, obwohl der Kern laengst in `main`
        ist (real passiert mit FM-9, dem obersten P1). Richtig ist 'wip', solange
        noch etwas offen ist, sonst 'done'. Bewusst eng: nur der harte Widerspruch
        todo↔GELANDET, damit dekorierte wip-Staten weiter frei formulierbar sind.
        """
        bad = []
        for ln, id_, _p, status, line in _rows_with_line():
            # Nur der Status-KOPF (vor der ersten Klammer) ist der Status; was in
            # Klammern steht, ist Kommentar. Sonst entwertet ein blosses
            # "todo (Slice 1 done)" die Regel, und ein zitiertes Wort im
            # Fliesstext loest sie faelschlich aus (Review-Fund 2026-07-28).
            head = status.split("(")[0].lower()
            if "todo" not in head:
                continue
            if any(k in head for k in ("done", "wip", "teils", "teil")):
                continue
            if LANDED.search(line):
                bad.append((ln, id_, status[:60]))
        self.assertEqual(bad, [], f"Status 'todo', aber die Zeile meldet gelandete "
                                  f"Arbeit — auf 'wip'/'teils'/'done' ziehen: {bad}")

    def test_status_has_no_dangling_this_pr(self):
        """FINALIZE 2026-08-02: „dieser PR" ist im Backlog kein Verweis.

        Beim Schreiben ist er eindeutig — der Autor sitzt im Branch. Nach dem
        Merge steht er dauerhaft in einer Datei, in der niemand mehr auflösen
        kann, welcher PR gemeint war. Gemessen: vier Status-Angaben trugen ihn
        (LAS-07, LAS-08, VIZ-15, OUT-06), teils seit dem 2026-07-03; aufgelöst
        wurden sie erst über `git log -S` — Arbeit, die der Schreibende in einer
        Sekunde erspart hätte.

        **Bewusst nur die Status-Spalte:** sie ist das Feld, aus dem der Loop
        seine nächste Aufgabe wählt. Im Fliesstext der Beschreibung stehen
        weitere Fundstellen; die sind Erzählung und werden hier nicht angefasst,
        damit die Regel scharf bleibt statt breit.
        """
        bad = []
        for ln, id_, _p, status, _line in _rows_with_line():
            if re.search(r"dies(er|em)\s+PR|diesem?\s+Branch", status, re.I):
                bad.append((ln, id_, status[:70]))
        self.assertEqual(
            bad, [],
            'Status verweist auf "diesen PR" - nach dem Merge nicht mehr '
            'aufloesbar. Stattdessen die PR-Nummer oder Commit+Datum nennen: '
            f'{bad}')

    def test_item_rows_are_all_recognized(self):
        """QA-18d: eine Zeile, die wie ein Item aussieht (ID-Zelle + P1/P2/P3),
        MUSS vom ID-Muster erfasst werden.

        Beim Entzerren der doppelten `DOC-10` war die Umbenennung zuerst
        `DOC-10b` — mit Kleinbuchstaben faellt die Zeile durch `ROW` und ist damit
        fuer Verdichtung, Queue, Stats und diesen Lint **gar nicht vorhanden**.
        Dieselbe stille Unsichtbarkeit, gegen die dieser Branch antritt.
        """
        # ★★ QA-55: Der Guard hatte dieselbe Blindstelle wie das Muster, gegen
        # das er schuetzt. Er verlangte selbst `[A-Za-z][\w.-]*` — also fast
        # genau `ROW`. Eine Item-Zeile, deren ID-Zelle damit nicht anfaengt,
        # war fuer BEIDE unsichtbar, und der Waechter meldete Ruhe.
        #
        # **Gemessen beim Umbau:** genau so ein Fall stand im Backlog — eine
        # blockierte P3-Zeile mit einem Gedankenstrich statt einer ID
        # (Hardware-Verifikation Ether Dream/IDN). Fuer Verdichtung, Queue,
        # Stats und diesen Lint existierte sie schlicht nicht. Sie hat jetzt
        # die ID `LAS-HW-VERIFY`.
        #
        # Das neue Muster nimmt JEDE nichtleere erste Zelle. Gegenprobe: es
        # erfasst 435 statt 434 Zeilen — die eine Differenz war der echte Fund,
        # es gibt also keinen Schwall Fehlalarme.
        looks_like_item = LOOKS_LIKE_ITEM
        bad = []
        with open(BACKLOG, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if looks_like_item.match(line) and not ROW.match(line):
                    bad.append((lineno, line.split("|")[1].strip()))
        self.assertEqual(bad, [], f"Item-Zeile passt nicht aufs ID-Muster "
                                  f"(GROSSBUCHSTABEN/Ziffern, mit Bindestrich): {bad}")

    def test_ids_are_unique(self):
        """QA-18c: eine ID darf nur EIN Item bezeichnen.

        Real vorgefunden 2026-07-28: zwei voellig verschiedene Items trugen beide
        `DOC-10` (Anleitungs-/Bild-Audit und der AUDIT_COVERAGE-Tracker). Jede
        Auswertung, die per ID zusammenfuehrt — Verdichtung, Archiv-Rueckholung,
        Queue — greift dann die falsche Zeile; beim Archivieren war genau das der
        Weg, auf dem offene Arbeit still verschwand.
        """
        seen: dict[str, int] = {}
        dupes = []
        for ln, id_, _p, _status in _rows():
            if id_ in seen:
                dupes.append((id_, seen[id_], ln))
            else:
                seen[id_] = ln
        self.assertEqual(dupes, [], f"doppelte IDs (ID, erste Zeile, zweite Zeile): {dupes}")


if __name__ == "__main__":
    unittest.main()
