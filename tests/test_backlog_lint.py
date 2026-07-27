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
ROW = re.compile(r"^\|\s*([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|")
# Anerkannte Status-Keywords (irgendwo in der Status-Zelle, case-insensitiv).
STATUS_KEYWORDS = ("todo", "done", "wip", "review", "blocked", "decision",
                   "teils", "teil", "defer", "verifiziert", "reproduzierbar", "n/a")
PRIOS = ("P1", "P2", "P3")
GH_LINK = re.compile(r"\]\((https?://github\.com/[^)]+)\)")
GH_PR_ISSUE_OK = re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+/(pull|issues)/\d+")
# QA-18b: "GELANDET" ist die projektweite Vokabel fuer "ist gemergt" (Loop-Runden
# schreiben sie in die Zeile, wenn eine Teil-Lieferung in main ist).
LANDED = re.compile(r"gelandet", re.IGNORECASE)


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
            low = status.lower()
            if "todo" not in low or "done" in low or "wip" in low:
                continue
            if LANDED.search(line):
                bad.append((ln, id_, status[:60]))
        self.assertEqual(bad, [], f"Status 'todo', aber die Zeile meldet gelandete "
                                  f"Arbeit — auf 'wip'/'done' ziehen: {bad}")


if __name__ == "__main__":
    unittest.main()
