"""T-7: spam-sicheres Debug-Logging fuer verschluckte Fehler.

Default aus (kein Verhaltenswechsel in Produktion); bei aktivem Debug wird jede
einzigartige (tag, Fehler)-Kombination genau einmal ausgegeben (kein Hot-Path-Spam).
"""
import io
import unittest
from contextlib import redirect_stdout

from src.core import debug_log


class DebugLogTest(unittest.TestCase):
    def setUp(self):
        self._prev = debug_log.is_enabled()
        debug_log.reset()

    def tearDown(self):
        debug_log.set_debug(self._prev)
        debug_log.reset()

    def _capture(self, fn) -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            fn()
        return buf.getvalue()

    def test_disabled_produces_no_output(self):
        debug_log.set_debug(False)
        out = self._capture(
            lambda: debug_log.debug_swallow("t", ValueError("x")))
        self.assertEqual(out, "")

    def test_enabled_logs_tag_type_and_message(self):
        debug_log.set_debug(True)
        out = self._capture(
            lambda: debug_log.debug_swallow("mytag", ValueError("boom")))
        self.assertIn("mytag", out)
        self.assertIn("ValueError", out)
        self.assertIn("boom", out)

    def test_dedup_same_error_logged_once(self):
        debug_log.set_debug(True)

        def spam():
            for _ in range(50):
                debug_log.debug_swallow("tag", ValueError("same"))

        self.assertEqual(self._capture(spam).count("ValueError"), 1)

    def test_distinct_messages_each_logged(self):
        debug_log.set_debug(True)

        def two():
            debug_log.debug_swallow("tag", ValueError("a"))
            debug_log.debug_swallow("tag", ValueError("b"))

        self.assertEqual(self._capture(two).count("ValueError"), 2)

    def test_reset_clears_dedup(self):
        debug_log.set_debug(True)

        def again():
            debug_log.debug_swallow("tag", ValueError("x"))
            debug_log.reset()
            debug_log.debug_swallow("tag", ValueError("x"))

        self.assertEqual(self._capture(again).count("ValueError"), 2)


if __name__ == "__main__":
    unittest.main()
