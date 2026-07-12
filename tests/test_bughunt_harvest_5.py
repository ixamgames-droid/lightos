"""Bug-Hunt-Harvest 5 (Runde 2, 2026-07-12) — MIDI-View-Learn-Threading,
SimpleDesk-Universe-Wechsel, _delete_stack-Refresh-Respekt.

- midi_view._start_learn: der Learn-Callback lief im MIDI-Dispatch-Thread und
  oeffnete dort einen MODALEN QInputDialog + mutierte die Mapping-Tabelle. Jetzt
  emittiert der Callback NUR das learn_received-Signal (GUI-Thread-Slot).
- simple_desk: Klick auf ein Fixture in Universe 5+ wechselte die Fader-Ansicht
  nicht (hartes 1..4-Limit + 4-Eintraege-Combo) -> falsches Universe angezeigt.
- playback_view._delete_stack: ueberschrieb den vom synchronen stacks_changed-
  Refresh bereits neu gesetzten _current_stack mit None.
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class MidiLearnCallbackOnlyEmitsTest(unittest.TestCase):
    def test_start_learn_callback_only_emits_signal(self):
        """Der an start_learn uebergebene Callback (laeuft im MIDI-Thread) darf
        NICHTS ausser dem Signal-Emit tun — keine Widget-/Dialog-Arbeit."""
        from src.ui.views.midi_view import MidiView
        cbs, emitted, logs = [], [], []
        fake = SimpleNamespace(
            _map_table=SimpleNamespace(
                selectedIndexes=lambda: [SimpleNamespace(row=lambda: 0)]),
            _learn_target_row=None,
            _append_log=logs.append,
            _mapper=SimpleNamespace(start_learn=lambda cb: cbs.append(cb)),
            _log_signal=SimpleNamespace(
                learn_received=SimpleNamespace(emit=lambda m: emitted.append(m))),
        )
        MidiView._start_learn(fake)
        self.assertEqual(len(cbs), 1)
        cbs[0]("FAKE_MSG")            # simuliert den Aufruf aus dem MIDI-Thread
        self.assertEqual(emitted, ["FAKE_MSG"],
                         "Callback muss das Ergebnis NUR per Signal marshallen")


class SimpleDeskUniverseSwitchTest(unittest.TestCase):
    def test_overview_universe_5_plus_switches_combo(self):
        from src.ui.views.simple_desk import SimpleDeskView
        calls = []
        fake = SimpleNamespace(
            _uni_combo=SimpleNamespace(count=lambda: 32,
                                       setCurrentIndex=calls.append),
            _universe=1,
        )
        SimpleDeskView._on_overview_universe(fake, 7)
        self.assertEqual(calls, [6], "Universe 7 muss die Combo auf Index 6 stellen")

    def test_overview_universe_out_of_range_is_noop(self):
        from src.ui.views.simple_desk import SimpleDeskView
        calls = []
        fake = SimpleNamespace(
            _uni_combo=SimpleNamespace(count=lambda: 32,
                                       setCurrentIndex=calls.append),
            _universe=1,
        )
        SimpleDeskView._on_overview_universe(fake, 33)
        self.assertEqual(calls, [])

    def test_combo_has_32_universes(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from src.ui.views.simple_desk import SimpleDeskView
        view = SimpleDeskView()
        try:
            self.assertEqual(view._uni_combo.count(), 32)
        finally:
            view.deleteLater()
            app.processEvents()


class DeleteStackRespectsRefreshTest(unittest.TestCase):
    def _run(self, refresh_sets_new):
        import src.ui.views.playback_view as PV
        removed = SimpleNamespace(name="Alt")
        newer = SimpleNamespace(name="Neu")

        fake = SimpleNamespace(_current_stack=removed)

        def _remove(stack):
            # simuliert den SYNCHRONEN stacks_changed-Refresh waehrend
            # remove_cue_stack: die Combo waehlt ggf. schon die naechste Liste.
            if refresh_sets_new:
                fake._current_stack = newer
        fake._state = SimpleNamespace(remove_cue_stack=_remove)

        with patch.object(PV, "QMessageBox") as MB:
            MB.question.return_value = MB.StandardButton.Yes
            PV.PlaybackView._delete_stack(fake)
        return fake, removed, newer

    def test_refresh_selection_survives_delete(self):
        fake, _removed, newer = self._run(refresh_sets_new=True)
        self.assertIs(fake._current_stack, newer,
                      "der vom Refresh gesetzte Stack darf nicht mit None "
                      "ueberschrieben werden")

    def test_without_refresh_current_becomes_none(self):
        fake, _removed, _newer = self._run(refresh_sets_new=False)
        self.assertIsNone(fake._current_stack)


if __name__ == "__main__":
    unittest.main()
