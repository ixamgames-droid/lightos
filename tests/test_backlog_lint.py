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


if __name__ == "__main__":
    unittest.main()
