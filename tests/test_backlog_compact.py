"""Tests fuer tools/backlog_compact.py (Backlog-Verdichter + Queue-View).

Arbeitet auf einem synthetischen Backlog-Fixture (kein Schreiben am echten
BACKLOG.md); ein Smoke-Test prueft zusaetzlich read-only, dass Queue/Stats auf
der echten Datei laufen. Die verdichtete Kurzzeile muss die QA-18-Lint-
Konvention aus tests/test_backlog_lint.py erfuellen (ROW-Match + Status-Keyword).
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backlog_compact as bc                      # noqa: E402
from test_backlog_lint import ROW, STATUS_KEYWORDS  # noqa: E402

FIXTURE = """# Test-Backlog

| ID | Prio | Status | Titel / Notiz |
|----|------|--------|---------------|
| AA-01 | P2 | todo | **Erstes offenes Item.** Detailtext hier. |
| BB-02 | P1 | ✅ done ([#123](https://github.com/ixamgames-droid/lightos/pull/123)) | **Erledigtes Item.** Sehr langer Detailtext der archiviert werden soll. |
| CC-03 | P1 | todo | **Wichtiges offenes Item.** |
| DD-04 | P3 | wip (1a done, 1b offen) | **Laufende Arbeit.** Teilweise done, bleibt aktiv. |
| EE-05 | P2 | review | **PR offen.** |
| FF-06 | P3 | done → Archiv | Schon frueher verdichtet (Details: BACKLOG_ARCHIVE.md) |
| GG-07 | P2 | done ([PR #100](https://github.com/ixamgames-droid/lightos/pull/100)) | Unformatierter Titel ohne Bold am Anfang. **Fix:** spaeter Bold-Span darf nicht Titel werden. |
| HH-08 | P3 | done ([Codex-Review](https://github.com/ixamgames-droid/lightos/pull/280)) | **Codex-Fund.** Details egal. |
""".replace("\n", "\n")


def _lines():
    return FIXTURE.splitlines(keepends=True)


class ParseTest(unittest.TestCase):
    def test_parse_finds_all_rows(self):
        rows = bc.parse_rows(_lines())
        self.assertEqual([r.id for r in rows],
                         ["AA-01", "BB-02", "CC-03", "DD-04", "EE-05", "FF-06",
                          "GG-07", "HH-08"])

    def test_done_detection_respects_decorated_wip(self):
        rows = {r.id: r for r in bc.parse_rows(_lines())}
        self.assertTrue(rows["BB-02"].is_done)
        self.assertFalse(rows["DD-04"].is_done, "wip (… done) darf NICHT als done zaehlen")
        self.assertFalse(rows["AA-01"].is_done)
        self.assertTrue(rows["FF-06"].is_done, "bereits verdichtete Zeile bleibt done")


class QueueTest(unittest.TestCase):
    def test_queue_orders_by_prio_then_position(self):
        out = bc.cmd_queue(_lines(), 10)
        self.assertLess(out.index("CC-03"), out.index("AA-01"), "P1 vor P2")
        self.assertNotIn("BB-02", out, "done-Items gehoeren nicht in die Queue")
        self.assertIn("DD-04", out)
        self.assertIn("EE-05", out)

    def test_queue_limit(self):
        out = bc.cmd_queue(_lines(), 1)
        self.assertIn("CC-03", out)
        self.assertNotIn("AA-01  [P2]", out)


class StatsTest(unittest.TestCase):
    def test_stats_counts(self):
        out = bc.cmd_stats(_lines())
        self.assertIn("todo=2", out)
        self.assertIn("wip=1", out)
        self.assertIn("review=1", out,
                      "[Codex-Review]-Linktext in HH-08 darf NICHT als review zaehlen")
        self.assertIn("done=4", out)


class ArchiveTest(unittest.TestCase):
    def test_archive_split_moves_only_pure_done(self):
        new_lines, done = bc.archive_split(_lines())
        self.assertEqual({r.id for r in done}, {"BB-02", "GG-07", "HH-08"},
                         "FF-06 ist schon verdichtet und darf nicht erneut wandern")
        text = "".join(new_lines)
        self.assertIn("AA-01", text)
        self.assertIn("Sehr langer Detailtext", "".join(_lines()))
        self.assertNotIn("Sehr langer Detailtext", text, "Volltext muss raus")
        self.assertIn("BB-02", text, "Kurzzeile mit ID bleibt")
        self.assertIn("[#123](https://github.com/ixamgames-droid/lightos/pull/123)", text,
                      "PR-Link bleibt in der Kurzzeile")

    def test_condensed_line_passes_qa18_lint(self):
        new_lines, _done = bc.archive_split(_lines())
        for line in new_lines:
            m = ROW.match(line)
            if not m or set(m.group(2).strip()) <= set("-: "):
                continue
            status = m.group(3).strip().lower()
            self.assertTrue(any(kw in status for kw in STATUS_KEYWORDS),
                            f"Kurzzeile faellt durch QA-18-Lint: {line!r}")

    def test_archive_is_idempotent(self):
        new_lines, _ = bc.archive_split(_lines())
        again, done2 = bc.archive_split(new_lines)
        self.assertEqual(done2, [], "zweiter Lauf darf nichts mehr finden")
        self.assertEqual("".join(again), "".join(new_lines),
                         "kein Aufschaukeln der Kurzform")


class ReviewRegressionTest(unittest.TestCase):
    """Regressionen aus der adversarialen Review 2026-07-19."""

    def _row(self, rid):
        return {r.id: r for r in bc.parse_rows(_lines())}[rid]

    def test_pr_link_matches_arbitrary_link_text(self):
        self.assertIn("pull/100", self._row("GG-07").first_pr_link(),
                      "[PR #100](...)-Format muss gefunden werden")
        self.assertIn("pull/280", self._row("HH-08").first_pr_link(),
                      "[Codex-Review](...)-Format muss gefunden werden")

    def test_short_title_ignores_later_bold_span(self):
        title = self._row("GG-07").short_title()
        self.assertNotEqual(title, "Fix:", "spaeterer **Fix:**-Span darf nicht Titel werden")
        self.assertIn("Unformatierter Titel", title)

    def test_condensed_line_keeps_pr_link(self):
        new_lines, _ = bc.archive_split(_lines())
        gg = next(l for l in new_lines if l.startswith("| GG-07"))
        self.assertIn("https://github.com/ixamgames-droid/lightos/pull/100", gg)


class RealBacklogSmokeTest(unittest.TestCase):
    """Read-only gegen das echte BACKLOG.md — schreibt nichts."""

    def test_queue_and_stats_run_on_real_backlog(self):
        with open(bc.BACKLOG, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.assertTrue(bc.cmd_queue(lines, 5))
        out = bc.cmd_stats(lines)
        self.assertIn("Tabellenzeilen", out)


if __name__ == "__main__":
    unittest.main()
