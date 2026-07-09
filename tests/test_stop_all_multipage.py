"""STOP ALL muss Executoren auf ALLEN Playback-Pages stoppen, nicht nur der aktuellen.

Regression (2026-07-09, Feature-Verifikations-Sweep): ``MainWindow._stop_all``
iterierte ``pe.executors`` — das ist die Backwards-Compat-Property und liefert NUR
``self.pages[current_page]``. Ein Chaser/Cue-Stack, der auf einer NICHT aktuell
sichtbaren Page lief, wurde vom Kopfzeilen-„STOP ALL"-Button also nicht gestoppt
(sicherheitsrelevant: der Operator erwartet, dass STOP ALL wirklich alles stoppt).
Der Fix delegiert an ``PlaybackEngine.stop_all()``, das bewusst ueber alle Pages
iteriert.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.executor import PlaybackEngine
from src.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


class _FakeStack:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


class StopAllMultiPageTest(unittest.TestCase):
    def _engine_two_pages(self):
        """PlaybackEngine mit je einem laufenden Stack auf Page 1 UND Page 2,
        aktuell sichtbar ist NUR Page 1."""
        engine = PlaybackEngine(SimpleNamespace())
        s_page1 = _FakeStack()
        s_page2 = _FakeStack()
        engine.pages[0][0].stack = s_page1   # Executor 1 auf Page 1
        engine.pages[1][0].stack = s_page2   # Executor 1 auf Page 2
        engine.current_page = 0              # nur Page 1 ist sichtbar
        return engine, s_page1, s_page2

    def test_engine_stop_all_stops_every_page(self):
        engine, s1, s2 = self._engine_two_pages()
        engine.stop_all()
        self.assertTrue(s1.stopped)
        self.assertTrue(s2.stopped, "PlaybackEngine.stop_all muss ALLE Pages stoppen")

    def test_mainwindow_stop_all_delegates_to_all_pages(self):
        """Eigentlicher Regressionswaechter: der UI-Handler darf sich NICHT auf
        pe.executors (nur aktuelle Page) beschraenken."""
        engine, s1, s2 = self._engine_two_pages()
        fake = SimpleNamespace(_state=SimpleNamespace(playback_engine=engine))
        MainWindow._stop_all(fake)
        self.assertTrue(s1.stopped, "Executor auf der aktuellen Page muss gestoppt sein")
        self.assertTrue(
            s2.stopped,
            "Executor auf einer ANDEREN Page muss durch STOP ALL ebenfalls gestoppt "
            "werden (Regression: pe.executors deckte nur die aktuelle Page ab)")

    def test_mainwindow_stop_all_safe_without_engine(self):
        """Kein Playback-Engine -> _stop_all darf nicht werfen."""
        fake = SimpleNamespace(_state=SimpleNamespace(playback_engine=None))
        MainWindow._stop_all(fake)  # darf einfach nichts tun (kein Absturz)


if __name__ == "__main__":
    unittest.main()
