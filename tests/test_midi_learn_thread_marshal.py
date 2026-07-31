"""MIDI-Learn im Input-Profil-Editor marshallt das Ergebnis in den GUI-Thread.

Regression (adversariale UI-Bug-Jagd 2026-07-09): der an `midi_mapper.start_learn()`
uebergebene Callback lief im MIDI-Dispatch-Thread und rief direkt `_refresh_table()` /
mutierte `self._table` — Qt-Widget-Zugriff aus einem Fremd-Thread (Absturzgefahr). Fix:
der Callback emittiert nur ein Signal (thread-sicher), die UI-/Model-Arbeit passiert in
`_on_learned` auf dem GUI-Thread (QueuedConnection).
"""
import os
import threading
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.widgets.input_profile_editor import InputProfileEditor
from src.core.input.profile import InputProfile
from src.core.midi.midi_mapper import MidiMapping, ACTION_NONE

_app = QApplication.instance() or QApplication([])


# XPLAT-15: nach JEDEM Test die uebrig gebliebenen Top-Level-Widgets WIRKLICH
# abbauen. `deleteLater()` allein stellt `DeferredDelete` nie zu — die Objekte
# ueberleben mitsamt Kindern, Signalen und (bei Views) Renderern. Segmentiert
# faellt das nicht auf, weil jede Datei allein laeuft; in einem Prozess mit
# genug angesammeltem Zustand ist es dieselbe Klasse Zeitzuender, die vor
# XPLAT-09 neun scheinbar gruene viz-Dateien zum Segfault brachte.
# Muster + Begruendung: tests/_qt_lifecycle.py, Vorbild test_views.py.
import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    # QApplication lokal importieren: manche Dateien holen es nur INNERHALB
    # ihrer Tests, dann gibt es den Modulnamen hier nicht.
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


class OnLearnedLogicTest(unittest.TestCase):
    """Reine Logik von _on_learned (Fake-self, kein Widget)."""

    def test_appends_when_no_row_selected(self):
        prof = SimpleNamespace(mappings=[])
        fake = SimpleNamespace(
            _profile=prof,
            _table=SimpleNamespace(currentRow=lambda: -1),
            _save_meta=lambda: None,
            _refresh_table=lambda: None,
        )
        InputProfileEditor._on_learned(
            fake, SimpleNamespace(msg_type="note_on", channel=1, data1=60))
        self.assertEqual(len(prof.mappings), 1)
        self.assertEqual(prof.mappings[0].data1, 60)

    def test_updates_selected_row(self):
        existing = MidiMapping(name="x", msg_type="cc", channel=0, data1=0,
                               action=ACTION_NONE, param="", port_filter="")
        prof = SimpleNamespace(mappings=[existing])
        fake = SimpleNamespace(
            _profile=prof,
            _table=SimpleNamespace(currentRow=lambda: 0),
            _save_meta=lambda: None,
            _refresh_table=lambda: None,
        )
        InputProfileEditor._on_learned(
            fake, SimpleNamespace(msg_type="note_on", channel=2, data1=64))
        self.assertEqual(existing.data1, 64)
        self.assertEqual(existing.channel, 2)


class LearnedSignalMarshalTest(unittest.TestCase):
    def test_signal_from_background_thread_reaches_gui_thread(self):
        """Emit aus einem FREMD-Thread (wie der MIDI-Thread) -> _on_learned laeuft
        via QueuedConnection auf dem GUI-Thread; kein Cross-Thread-Widget-Zugriff."""
        ed = InputProfileEditor()
        try:
            ed._profile = InputProfile(name="Test")
            ed._refresh_table()
            msg = SimpleNamespace(msg_type="note_on", channel=3, data1=72)
            t = threading.Thread(target=lambda: ed._learned_signal.emit(msg))
            t.start()
            t.join()
            # Vor processEvents darf der Slot NICHT gelaufen sein (Queued):
            self.assertEqual(len(ed._profile.mappings), 0)
            _app.processEvents()
            self.assertEqual(len(ed._profile.mappings), 1)
            self.assertEqual(ed._profile.mappings[0].data1, 72)
        finally:
            ed.deleteLater()
            _app.processEvents()


if __name__ == "__main__":
    unittest.main()
