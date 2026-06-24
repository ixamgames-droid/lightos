"""STAB-01: Tests fuer die Crash-Logging-Logik (src/core/crash_logging.py).

Reine Logik, kein Qt noetig — laeuft schnell und headless. Verifiziert die
Bausteine, die crash.log "WANN/WIE" erkennbar machen: Rotation, Marker-Zeilen,
Freeze-/Standby-Klassifikation, Exception-Signatur + Sturm-Drossel und die
"zuletzt lebendig"/Running-Flag-Mechanik.
"""
import datetime
import io
import os
import tempfile
import unittest

from src.core import crash_logging as cl


class RotationTest(unittest.TestCase):
    def test_no_rotation_below_limit(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "crash.log")
            with open(p, "w", encoding="utf-8") as f:
                f.write("klein")
            self.assertFalse(cl.rotate_if_large(p, max_bytes=1024))
            self.assertTrue(os.path.exists(p))
            self.assertFalse(os.path.exists(p + ".1"))

    def test_rotation_above_limit_shifts_backups(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "crash.log")
            with open(p, "w", encoding="utf-8") as f:
                f.write("X" * 5000)
            self.assertTrue(cl.rotate_if_large(p, max_bytes=1024, backups=3))
            # Original ist jetzt .1, Original-Pfad weg (wird vom Aufrufer neu geoeffnet).
            self.assertTrue(os.path.exists(p + ".1"))
            self.assertFalse(os.path.exists(p))

    def test_rotation_drops_oldest(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "crash.log")
            for suffix, content in [("", "neu" * 1000), (".1", "a"), (".2", "b"), (".3", "c")]:
                with open(p + suffix, "w", encoding="utf-8") as f:
                    f.write(content)
            self.assertTrue(cl.rotate_if_large(p, max_bytes=1024, backups=3))
            # .3 (=alt "c") faellt raus; frueheres .2 ("b") wird zu .3.
            self.assertTrue(os.path.exists(p + ".3"))
            with open(p + ".3", encoding="utf-8") as f:
                self.assertEqual(f.read(), "b")

    def test_missing_file_is_safe(self):
        self.assertFalse(cl.rotate_if_large("/nonexistent/xyz.log"))
        self.assertFalse(cl.rotate_if_large(""))


class MarkerTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime.datetime(2026, 6, 23, 21, 30, 5)

    def test_session_banner(self):
        b = cl.session_banner(version="1.2.3", now=self.now, pid=4242)
        self.assertIn("LightOS STARTED 2026-06-23T21:30:05", b)
        self.assertIn("v1.2.3", b)
        self.assertIn("PID 4242", b)
        self.assertIn("Python", b)

    def test_clean_exit_marker(self):
        m = cl.clean_exit_marker(now=self.now)
        self.assertIn("CLOSED", m)
        self.assertIn("sauberer Exit", m)
        self.assertIn("2026-06-23T21:30:05", m)

    def test_previous_crash_notice_with_ts(self):
        n = cl.previous_crash_notice("2026-06-23T17:09:00", now=self.now)
        self.assertIn("NICHT SAUBER BEENDET", n)
        self.assertIn("2026-06-23T17:09:00", n)

    def test_previous_crash_notice_without_ts(self):
        n = cl.previous_crash_notice(None, now=self.now)
        self.assertIn("unbekannt", n)

    def test_suspend_and_freeze_headers(self):
        self.assertIn("Standby/Resume", cl.suspend_notice(24829, now=self.now))
        self.assertIn("24829s", cl.suspend_notice(24829, now=self.now))
        self.assertIn("UI-FREEZE", cl.freeze_header(12, now=self.now))
        self.assertIn("12s", cl.freeze_header(12, now=self.now))


class ClassifyTest(unittest.TestCase):
    def test_is_freeze(self):
        self.assertFalse(cl.is_freeze(5))
        self.assertTrue(cl.is_freeze(10))
        self.assertTrue(cl.is_freeze(238))

    def test_is_suspend_uses_loop_gap_not_stall(self):
        # Echter UI-Freeze: Watch-Thread tickt normal (loop_gap ~2s) -> KEIN Suspend.
        self.assertFalse(cl.is_suspend(2.0))
        self.assertFalse(cl.is_suspend(5.0))
        # Standby: der Watch-Thread selbst war Stunden weg.
        self.assertTrue(cl.is_suspend(24829))
        self.assertTrue(cl.is_suspend(2438))


class SignatureTest(unittest.TestCase):
    def _exc(self):
        try:
            raise KeyError(0)
        except KeyError:
            import sys
            return sys.exc_info()

    def test_signature_has_type_file_line(self):
        et, _ev, tb = self._exc()
        sig = cl.exc_signature(et, tb)
        self.assertTrue(sig.startswith("KeyError@"))
        self.assertIn("test_crash_logging.py:", sig)

    def test_format_python_exception(self):
        et, ev, tb = self._exc()
        block = cl.format_python_exception(et, ev, tb, thread_name="MidiDispatch")
        self.assertIn("Python Exception", block)
        self.assertIn("[Thread: MidiDispatch]", block)
        self.assertIn("Traceback", block)
        self.assertIn("KeyError", block)


class DedupTest(unittest.TestCase):
    def test_first_writes_full_repeats_suppressed(self):
        d = cl.ExceptionDedup(min_interval=5.0)
        sig = "KeyError@vc_slider.py:52"
        # t=0: erster -> Volltext, nichts unterdrueckt.
        self.assertEqual(d.decide(sig, 0.0), (True, 0))
        # t=1..4: gleicher Sturm -> gedrosselt.
        self.assertEqual(d.decide(sig, 1.0), (False, 0))
        self.assertEqual(d.decide(sig, 2.0), (False, 0))
        self.assertEqual(d.decide(sig, 3.0), (False, 0))
        # t=6: Intervall vorbei -> wieder Volltext, meldet 3 unterdrueckte.
        self.assertEqual(d.decide(sig, 6.0), (True, 3))
        # danach wieder bei 0.
        self.assertEqual(d.decide(sig, 7.0), (False, 0))

    def test_distinct_signatures_independent(self):
        d = cl.ExceptionDedup(min_interval=5.0)
        self.assertEqual(d.decide("A@x.py:1", 0.0), (True, 0))
        # andere Signatur -> eigener Volltext, nicht gedrosselt.
        self.assertEqual(d.decide("B@y.py:2", 0.5), (True, 0))


class LivenessTest(unittest.TestCase):
    def test_last_alive_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "last_alive.txt")
            now = datetime.datetime(2026, 6, 23, 17, 9, 0)
            cl.write_last_alive(p, now=now)
            self.assertEqual(cl.read_last_alive(p), "2026-06-23T17:09:00")

    def test_read_last_alive_missing(self):
        self.assertIsNone(cl.read_last_alive("/nonexistent/last_alive.txt"))
        self.assertIsNone(cl.read_last_alive(""))

    def test_running_flag_lifecycle(self):
        with tempfile.TemporaryDirectory() as td:
            flag = os.path.join(td, "lightos_running.flag")
            self.assertFalse(os.path.exists(flag))
            self.assertTrue(cl.mark_running(flag))
            self.assertTrue(os.path.exists(flag))      # Crash: bliebe hier liegen.
            cl.clear_running(flag)                      # sauberer Exit.
            self.assertFalse(os.path.exists(flag))
            cl.clear_running(flag)                      # doppelt -> kein Fehler.


class FinalizeExitTest(unittest.TestCase):
    """STAB-05: finalize_exit schreibt nur bei SAUBEREM Exit den Clean-Marker und
    entfernt die Running-Flag. Nach einer fatalen Exception bleibt die Flag liegen
    (Absturz beim naechsten Start erkennbar) und der Crash-Marker wird geschrieben."""

    def test_clean_exit_marks_clean_and_clears_flag(self):
        with tempfile.TemporaryDirectory() as td:
            flag = os.path.join(td, "lightos_running_123.flag")
            cl.mark_running(flag)
            buf = io.StringIO()
            cl.finalize_exit(buf, flag, had_fatal=False)
            self.assertIn("sauberer Exit", buf.getvalue())
            self.assertNotIn("ABGESTUERZT", buf.getvalue())
            self.assertFalse(os.path.exists(flag), "sauberer Exit -> Flag entfernt")

    def test_fatal_exit_marks_crash_and_keeps_flag(self):
        with tempfile.TemporaryDirectory() as td:
            flag = os.path.join(td, "lightos_running_123.flag")
            cl.mark_running(flag)
            buf = io.StringIO()
            cl.finalize_exit(buf, flag, had_fatal=True)
            self.assertIn("ABGESTUERZT", buf.getvalue())
            self.assertNotIn("sauberer Exit", buf.getvalue())
            self.assertTrue(os.path.exists(flag),
                            "fataler Exit -> Flag BLEIBT (naechster Start erkennt Absturz)")

    def test_handle_none_is_safe(self):
        """Fehlt das Log-Handle (Setup-Fehler), darf finalize_exit nicht crashen;
        die Flag-Logik greift trotzdem."""
        with tempfile.TemporaryDirectory() as td:
            flag = os.path.join(td, "lightos_running_9.flag")
            cl.mark_running(flag)
            cl.finalize_exit(None, flag, had_fatal=False)
            self.assertFalse(os.path.exists(flag))


class PerPidFlagTest(unittest.TestCase):
    """STAB-06: per-PID-Running-Flags + Liveness machen die Crash-Erkennung
    multi-instanz-sicher (keine globale Flag, die eine 2. Instanz ueberschreibt/
    loescht; laufende Parallel-Instanzen werden NICHT als Absturz gemeldet)."""

    @staticmethod
    def _dead_pid() -> int:
        """Eine PID, deren Prozess garantiert beendet ist."""
        import subprocess
        import sys
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        p.wait()                       # Kind beendet (+ unter POSIX reaped)
        return p.pid

    def test_pid_is_alive_for_self(self):
        self.assertTrue(cl.pid_is_alive(os.getpid()))

    def test_pid_is_alive_false_for_dead_process(self):
        self.assertFalse(cl.pid_is_alive(self._dead_pid()))

    def test_pid_is_alive_rejects_garbage(self):
        self.assertFalse(cl.pid_is_alive(None))
        self.assertFalse(cl.pid_is_alive(-1))
        self.assertFalse(cl.pid_is_alive("nope"))

    def test_read_flag_pid_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            flag = os.path.join(td, f"lightos_running_{os.getpid()}.flag")
            cl.mark_running(flag)
            self.assertEqual(cl.read_flag_pid(flag), os.getpid())
            self.assertIsNone(cl.read_flag_pid(os.path.join(td, "fehlt.flag")))

    def test_find_running_flags_matches_perpid_and_legacy(self):
        with tempfile.TemporaryDirectory() as td:
            cl.mark_running(os.path.join(td, "lightos_running_111.flag"))
            cl.mark_running(os.path.join(td, "lightos_running.flag"))  # Legacy
            with open(os.path.join(td, "andere.txt"), "w", encoding="utf-8") as f:
                f.write("x")
            found = {os.path.basename(p) for p in cl.find_running_flags(td)}
            self.assertEqual(found, {"lightos_running_111.flag", "lightos_running.flag"})

    def test_find_crashed_sessions_reports_dead_skips_self_and_alive(self):
        with tempfile.TemporaryDirectory() as td:
            # eigene (lebende) Flag -> NICHT als Crash melden
            own = os.path.join(td, f"lightos_running_{os.getpid()}.flag")
            cl.mark_running(own)
            # tote Vorsitzung -> ALS Crash melden
            dead_pid = self._dead_pid()
            dead = os.path.join(td, f"lightos_running_{dead_pid}.flag")
            with open(dead, "w", encoding="utf-8") as f:
                f.write(str(dead_pid))
            crashed = cl.find_crashed_sessions(td, own_pid=os.getpid())
            self.assertIn(dead, crashed)
            self.assertNotIn(own, crashed)

    def test_find_crashed_sessions_reports_unreadable_legacy_flag(self):
        with tempfile.TemporaryDirectory() as td:
            legacy = os.path.join(td, "lightos_running.flag")
            with open(legacy, "w", encoding="utf-8") as f:
                f.write("")            # leer/unlesbare PID -> als Absturz werten
            self.assertIn(legacy, cl.find_crashed_sessions(td, own_pid=os.getpid()))


if __name__ == "__main__":
    unittest.main()
