"""F-9: Crash-Report-Dialog — Formatierung + thread-sicheres Marshalling.

Der Dialog selbst (QMessageBox.exec) wird nicht ausgefuehrt (wuerde blockieren);
getestet werden die reine Formatierung und dass report() das Signal mit Titel +
Details feuert.
"""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.widgets.crash_dialog import format_crash, read_log_tail, CrashReporter


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _raise(n: int):
    raise ValueError(f"kaputt-{n}")


def _exc_info():
    try:
        _raise(7)
    except ValueError:
        import sys
        return sys.exc_info()
    return (None, None, None)


class FormatCrashTest(unittest.TestCase):
    def test_title_has_type_and_message(self):
        et, ev, tb = _exc_info()
        title, details = format_crash(et, ev, tb)
        self.assertEqual(title, "ValueError: kaputt-7")

    def test_details_contain_traceback(self):
        et, ev, tb = _exc_info()
        _, details = format_crash(et, ev, tb)
        self.assertIn("Traceback", details)
        self.assertIn("_raise", details)
        self.assertIn("kaputt-7", details)

    def test_details_include_log_tail_and_path(self):
        et, ev, tb = _exc_info()
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "crash.log")
            with open(log, "w", encoding="utf-8") as f:
                f.write("frühere Zeile A\nfrühere Zeile B\n")
            _, details = format_crash(et, ev, tb, log)
            self.assertIn("crash.log (Auszug)", details)
            self.assertIn("frühere Zeile B", details)
            self.assertIn(log, details)


class ReadLogTailTest(unittest.TestCase):
    def test_returns_last_lines(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "x.log")
            with open(p, "w", encoding="utf-8") as f:
                f.write("\n".join(f"Zeile {i}" for i in range(100)))
            tail = read_log_tail(p, max_lines=5)
            self.assertIn("Zeile 99", tail)
            self.assertNotIn("Zeile 90", tail)

    def test_missing_file_is_empty(self):
        self.assertEqual(read_log_tail("/nonexistent/abc.log"), "")
        self.assertEqual(read_log_tail(""), "")


class ReporterTest(unittest.TestCase):
    def test_report_emits_signal_without_showing(self):
        _app()
        reporter = CrashReporter(log_path="")
        # WICHTIG: die eingebaute QueuedConnection auf _show trennen, sonst bliebe
        # nach report() ein QMessageBox.exec()-Aufruf in der Event-Queue liegen und
        # wuerde beim naechsten processEvents() (z. B. im Teardown eines spaeteren
        # Tests) re-entrant headless feuern -> Abort. Wir testen nur das Marshalling.
        reporter._report.disconnect(reporter._show)
        captured = []
        reporter._report.connect(lambda t, d: captured.append((t, d)))
        et, ev, tb = _exc_info()
        reporter.report(et, ev, tb)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][0], "ValueError: kaputt-7")
        self.assertIn("Traceback", captured[0][1])


if __name__ == "__main__":
    unittest.main()
