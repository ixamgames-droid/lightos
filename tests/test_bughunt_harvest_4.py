"""Bug-Hunt-Harvest 4 (Runde 2, 2026-07-12) — Command-Line-DoS, stop 0, tote
CueStack-Referenz, Channel-Group-Universe-Range.

- SelectionExpr.resolve: `1 thru 999999999` iterierte milliardenfach (GUI-Freeze/DoS).
  Jetzt Iteration ueber die gepatchten fids (O(n) statt O(hi-lo)).
- `stop 0` fiel durch den Falsy-Check auf Stop-ALL; `go 0`/`back 0` still auf Slot 1;
  Slot 0 haette zudem via get_executor(0) den LETZTEN Executor getroffen (Negativindex).
- AppState.remove_cue_stack liess Executor-Bindungen stehen -> Ghost-Playback der
  geloeschten Cueliste.
- Channel-Group-Universe-Spinbox war auf 1-16 statt 1-32 begrenzt.
"""
import os
import time
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.cmdline.parser import (
    SelectionExpr, parse, GoCommand, BackCommand, StopCommand)


class ThruRangeDoSTest(unittest.TestCase):
    def test_huge_thru_range_resolves_fast(self):
        expr = SelectionExpr(ranges=[(1, 999_999_999)])
        t0 = time.monotonic()
        out = expr.resolve(all_fids=[1, 5, 7])
        dt = time.monotonic() - t0
        self.assertEqual(out, [1, 5, 7])
        self.assertLess(dt, 1.0, f"resolve() dauerte {dt:.2f}s — DoS-Regression!")

    def test_reversed_range_still_works(self):
        expr = SelectionExpr(ranges=[(5, 2)])
        self.assertEqual(expr.resolve(all_fids=[1, 2, 3, 4, 5, 6]), [2, 3, 4, 5])


class StopZeroParseTest(unittest.TestCase):
    def test_stop_0_targets_slot_0_not_stop_all(self):
        cmd = parse("stop 0")
        self.assertIsInstance(cmd, StopCommand)
        self.assertEqual(cmd.slot, 0, "stop 0 darf NICHT als Stop-ALL (slot=None) parsen")

    def test_stop_without_number_is_stop_all(self):
        cmd = parse("stop")
        self.assertIsInstance(cmd, StopCommand)
        self.assertIsNone(cmd.slot)

    def test_go_back_stop_slot_0_rejected_on_execute(self):
        """Slot 0 (1-basiert ungueltig) darf nie get_executor erreichen —
        get_executor(0) waere Python-Negativindex = LETZTER Executor."""
        pe = SimpleNamespace(
            get_executor=lambda s: (_ for _ in ()).throw(AssertionError("erreicht!")),
            stop_all=lambda: (_ for _ in ()).throw(AssertionError("stop_all!")))
        state = SimpleNamespace(playback_engine=pe, cue_stacks=[])
        for cmd in (GoCommand(slot=0), BackCommand(slot=0), StopCommand(slot=0),
                    GoCommand(slot=-3)):
            res = cmd.execute(state)
            self.assertFalse(res.ok, f"{cmd} muss als ungueltig abgelehnt werden")


class RemoveCueStackUnbindsTest(unittest.TestCase):
    def test_remove_cue_stack_unbinds_executors_on_all_pages(self):
        from src.core.app_state import AppState
        stack = SimpleNamespace(stop=lambda: None)
        ex_a = SimpleNamespace(stack=stack)     # Page 1
        ex_b = SimpleNamespace(stack=stack)     # Page 2 (nicht sichtbar)
        ex_c = SimpleNamespace(stack="other")
        fake = SimpleNamespace(
            cue_stacks=[stack],
            playback_engine=SimpleNamespace(pages=[[ex_a, ex_c], [ex_b]]),
            _emit=lambda *a, **k: None,
        )
        AppState.remove_cue_stack(fake, stack)
        self.assertNotIn(stack, fake.cue_stacks)
        self.assertIsNone(ex_a.stack, "Executor-Bindung Page 1 muss geloest sein")
        self.assertIsNone(ex_b.stack, "Executor-Bindung Page 2 muss geloest sein")
        self.assertEqual(ex_c.stack, "other", "fremde Bindung bleibt unangetastet")


class ChannelGroupUniverseRangeTest(unittest.TestCase):
    def test_universe_spinbox_goes_to_32(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from src.ui.views.channel_groups_view import ChannelGroupsView, ChannelGroup
        view = ChannelGroupsView()
        try:
            view._groups.append(ChannelGroup(name="T", universe=1, channels=[1]))
            view._refresh_table()
            spin = view._table.cellWidget(view._table.rowCount() - 1, 1)
            self.assertIsNotNone(spin)
            self.assertEqual(spin.maximum(), 32)
        finally:
            view.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
