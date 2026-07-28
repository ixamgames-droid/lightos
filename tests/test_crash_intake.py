"""TOOLS-CRASHINTAKE: crash.log → Bug-Intake für den Loop.

Das Log wuchs bei David auf 1,3 MB, ohne dass ein Werkzeug es je gelesen hätte —
echte Abstürze und UI-Freezes kamen nie im Backlog an. Getestet wird der reine
Parser gegen ein synthetisches Log, das mit den ECHTEN Marker-Funktionen aus
``src.core.crash_logging`` gebaut wird (keine zweite Format-Quelle; ändert sich
dort ein Präfix, fällt es hier auf).

Die drei Fallen, die beim ersten Lauf gegen Davids echtes Log auffielen und die
hier festgenagelt sind:

  1. **Zwei Frame-Formate.** Tracebacks schreiben ``, line N, in fn``,
     faulthandler-Dumps (also ALLE Freeze-Stacks) ``, line N in fn`` — ohne
     Komma. Wer nur das erste kennt, verliert die halbe Auswertung still.
  2. **Der GUI-Thread ist der UNBENANNTE.** Attribuiert man den Freeze auf den
     ersten passenden Frame, zeigt die Signatur auf den FreezeWatchdog, also auf
     die Stelle, die den Freeze MELDET statt auf die, die ihn verursacht.
  3. **Die Testsuite schreibt in dasselbe Log.** Mehrere Tests werfen absichtlich;
     ungefiltert bestand der Intake zum grossen Teil aus diesen gewollten Fehlern.
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, REPO)

import collect_crash_report as cci                  # noqa: E402
from src.core import crash_logging as cl            # noqa: E402

SRC = r"C:\repo\lightos-main\src\ui\views\live_view.py"
TESTF = r"C:\repo\lightos-main\tests\test_viz10_stability.py"


def _exception_block(ts: str, exc: str, msg: str, frames) -> str:
    out = [f"=== Python Exception {ts} ===", "Traceback (most recent call last):"]
    for path, line, fn in frames:
        out.append(f'  File "{path}", line {line}, in {fn}')
    out.append(f"{exc}: {msg}")
    return "\n".join(out) + "\n"


def _freeze_block(ts_line: str, named_frames, gui_frames) -> str:
    """faulthandler-Form: benannte Threads zuerst, GUI-Thread OHNE [Name]."""
    out = [ts_line.rstrip("\n")]
    out.append("Current thread 0x00007564 [FreezeWatchdog] (most recent call first):")
    for path, line, fn in named_frames:
        out.append(f'  File "{path}", line {line} in {fn}')      # KEIN Komma
    out.append("")
    out.append("Thread 0x00005e68 (most recent call first):")
    for path, line, fn in gui_frames:
        out.append(f'  File "{path}", line {line} in {fn}')
    return "\n".join(out) + "\n"


WATCHDOG = [(r"C:\repo\lightos-main\main.py", 138, "_watch")]


class ParseExceptionsTest(unittest.TestCase):
    def test_same_error_at_same_place_is_one_signature(self):
        log = cl.session_banner(version="1", pid=1)
        for ts in ("2026-07-01T10:00:00", "2026-07-01T10:00:05", "2026-07-01T10:01:00"):
            log += _exception_block(ts, "AttributeError", "kein Attribut",
                                    [(SRC, 42, "paintEvent")])
        found = cci.parse_log(log)
        self.assertEqual(len(found), 1)
        f = found[0]
        self.assertEqual(f.count, 3)
        self.assertEqual(f.signature, "AttributeError@live_view.py:42")
        self.assertEqual(f.first_ts, "2026-07-01T10:00:00")
        self.assertEqual(f.last_ts, "2026-07-01T10:01:00")

    def test_different_line_is_a_different_signature(self):
        log = (_exception_block("2026-07-01T10:00:00", "ValueError", "x",
                                [(SRC, 42, "a")])
               + _exception_block("2026-07-01T10:00:01", "ValueError", "x",
                                  [(SRC, 99, "b")]))
        self.assertEqual(len(cci.parse_log(log)), 2)

    def test_top_src_frame_skips_library_frames(self):
        lib = r"C:\repo\venv\Lib\site-packages\pluggy\_hooks.py"
        log = _exception_block("2026-07-01T10:00:00", "TypeError", "x",
                               [(SRC, 42, "handler"), (lib, 7, "call")])
        f = cci.parse_log(log)[0]
        self.assertIn("live_view.py:42", f.top_src_frame,
                      "die interessante Stelle ist der letzte eigene Frame")
        self.assertIn("_hooks.py:7", f.deepest_frame)

    def test_exception_without_traceback_keeps_its_message_as_signature(self):
        """Der QtWebEngine-Renderabsturz liefert nur eine Meldung. Ohne
        Sonderfall bekaemen ALLE solchen Faelle die Signatur '@:0'."""
        log = ("=== Python Exception 2026-07-01T10:00:00 ===\n"
               "RuntimeError: status=CrashedTerminationStatus exit_code=-1\n")
        f = cci.parse_log(log)[0]
        self.assertIn("CrashedTerminationStatus", f.signature)

    def test_sessions_are_counted_separately(self):
        blk = _exception_block("2026-07-01T10:00:00", "KeyError", "k",
                               [(SRC, 5, "f")])
        log = (cl.session_banner(version="1", pid=1) + blk
               + cl.session_banner(version="1", pid=2) + blk)
        f = cci.parse_log(log)[0]
        self.assertEqual(f.count, 2)
        self.assertEqual(len(f.sessions), 2)


class TestNoiseFilterTest(unittest.TestCase):
    def test_errors_from_the_test_suite_are_dropped_by_default(self):
        log = (_exception_block("2026-07-01T10:00:00", "ValueError", "kaputt",
                                [(SRC, 10, "wrapper"), (TESTF, 44, "test_x")])
               + _exception_block("2026-07-01T10:00:01", "KeyError", "echt",
                                  [(SRC, 20, "on_click")]))
        sigs = {f.signature for f in cci.parse_log(log)}
        self.assertEqual(sigs, {"KeyError@live_view.py:20"})

    def test_include_tests_brings_them_back(self):
        log = _exception_block("2026-07-01T10:00:00", "ValueError", "kaputt",
                               [(SRC, 10, "wrapper"), (TESTF, 44, "test_x")])
        self.assertEqual(len(cci.parse_log(log, include_tests=True)), 1)

    def test_standby_resume_is_not_a_finding(self):
        """Der Watchdog kennzeichnet Standby ausdruecklich als NICHT-Freeze —
        als Bug gemeldet wuerde es den Intake mit Schlafmodus-Rauschen fuellen."""
        log = cl.suspend_notice(24829.0)
        self.assertEqual(cci.parse_log(log), [])

    def test_clean_exit_alone_produces_nothing(self):
        log = cl.session_banner(version="1", pid=1) + cl.clean_exit_marker()
        self.assertEqual(cci.parse_log(log), [])


class FreezeAttributionTest(unittest.TestCase):
    def test_freeze_points_at_the_frozen_gui_thread_not_the_watchdog(self):
        log = _freeze_block(cl.freeze_header(238.0), WATCHDOG,
                            [(SRC, 794, "paintEvent"),
                             (r"C:\repo\lightos-main\main.py", 195, "main")])
        f = cci.parse_log(log)[0]
        self.assertEqual(f.kind, "freeze")
        self.assertIn("live_view.py:794", f.signature,
                      "die Signatur muss auf den eingefrorenen Thread zeigen")
        self.assertNotIn("_watch", f.top_src_frame)
        self.assertIn("238s", f.message)

    def test_faulthandler_frames_without_comma_are_parsed(self):
        """Freeze-Stacks kommen AUSSCHLIESSLICH in dieser Form — wer nur die
        Traceback-Form kennt, findet hier gar keinen Frame."""
        log = _freeze_block(cl.freeze_header(12.0), WATCHDOG,
                            [(SRC, 100, "paintEvent")])
        f = cci.parse_log(log)[0]
        self.assertIn("live_view.py:100", f.signature)

    def test_freeze_without_any_own_frame_stays_reportable(self):
        lib = r"C:\repo\venv\Lib\site-packages\numpy\core.py"
        log = _freeze_block(cl.freeze_header(30.0), WATCHDOG, [(lib, 9, "x")])
        f = cci.parse_log(log)[0]
        self.assertIn("unbekannt", f.signature)
        self.assertEqual(f.count, 1)


class SeenStateTest(unittest.TestCase):
    def test_seen_signatures_round_trip(self):
        import tempfile
        p = os.path.join(tempfile.mkdtemp(), "seen.json")
        self.assertEqual(cci.load_seen(p), set())
        cci.save_seen({"A@x:1", "B@y:2"}, p)
        self.assertEqual(cci.load_seen(p), {"A@x:1", "B@y:2"})

    def test_report_marks_unseen_signatures(self):
        log = _exception_block("2026-07-01T10:00:00", "KeyError", "k",
                               [(SRC, 5, "f")])
        found = cci.parse_log(log)
        neu = cci.format_report(found, seen=set())
        alt = cci.format_report(found, seen={"KeyError@live_view.py:5"})
        self.assertIn("1 neu", neu)
        self.assertIn("🆕", neu)
        self.assertIn("0 neu", alt)
        self.assertNotIn("🆕", alt)

    def test_empty_log_says_so(self):
        self.assertIn("Keine", cci.format_report([], seen=set()))


class MarkerCouplingTest(unittest.TestCase):
    """Die Praefixe stammen aus den echten Schreibfunktionen — nicht kopiert."""

    def test_prefixes_match_what_crash_logging_writes(self):
        self.assertTrue(cl.session_banner(version="9", pid=7).strip()
                        .startswith(cci.P_STARTED))
        self.assertTrue(cl.freeze_header(5.0).strip().startswith(cci.P_FREEZE))
        self.assertTrue(cl.clean_exit_marker().strip().startswith(cci.P_CLEAN))
        self.assertTrue(cl.fatal_exit_marker().strip().startswith(cci.P_FATAL))
        for p in (cci.P_STARTED, cci.P_FREEZE, cci.P_CLEAN, cci.P_FATAL):
            self.assertTrue(p.startswith("==="), f"kein Marker-Praefix: {p!r}")
            self.assertNotIn("20", p, "Zeitstempel darf nicht im Praefix stehen")


if __name__ == "__main__":
    unittest.main()


class RecencyTest(unittest.TestCase):
    """Triage fragt „was passiert NOCH?", nicht „was passierte am haeufigsten?".

    Real erlebt 2026-07-28: nach Anzahl sortiert stand ein 159x aufgetretener,
    seit Wochen toter Testlauf-Absturz ganz oben, waehrend der einzige noch
    lebende Fehler weiter unten unterging — und die daraus abgeleitete
    Prioritaet im Backlog war falsch.
    """

    def _log(self):
        return (_exception_block("2026-01-01T10:00:00", "OldError", "alt",
                                 [(SRC, 1, "a")]) * 5
                + _exception_block("2026-07-20T10:00:00", "NewError", "neu",
                                   [(SRC, 2, "b")]))

    def test_newest_signature_comes_first(self):
        found = cci.parse_log(self._log())
        self.assertEqual(found[0].signature, "NewError@live_view.py:2",
                         "die juengste Signatur gehoert nach oben, nicht die haeufigste")
        self.assertEqual(found[1].count, 5, "die alte ist trotzdem noch da")

    def test_report_marks_cold_signatures(self):
        found = cci.parse_log(self._log())
        report = cci.format_report(found, seen=set())
        old_line = next(l for l in report.splitlines()
                        if "2026-01-01" in l)
        new_line = next(l for l in report.splitlines()
                        if "2026-07-20" in l)
        self.assertIn("❄", old_line, "alte Signatur muss als kalt erkennbar sein")
        self.assertNotIn("❄", new_line)

    def test_cold_threshold_is_a_date_in_the_past(self):
        import datetime as d
        self.assertLess(cci._cold_before(), d.date.today().isoformat())
