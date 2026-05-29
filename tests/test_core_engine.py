"""Unit-Tests fuer Core-Engine: Universe, CueStack/FadeState, ChannelModifier,
Command-Line Parser und UndoStack.

Keine externen Abhaengigkeiten ausser der Standard-Library. Alle Qt/Hardware-
Importe werden via sys.modules gemockt.
"""
from __future__ import annotations
import sys
import types
import unittest
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ─── Minimal Stubs fuer Module ohne Hardware-Abhaengigkeit ──────────────────

def _stub(name: str, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules.setdefault(name, m)
    return m


# PySide6 nur stubben, wenn es NICHT installiert ist. Sonst wuerden die leeren
# Stub-Module dauerhaft in sys.modules verbleiben und den echten Qt-Import in
# anderen Testmodulen desselben pytest-Laufs zerstoeren (z. B. test_views ->
# "cannot import name 'QPoint' from 'PySide6.QtCore'").
try:
    import PySide6.QtCore       # noqa: F401
    import PySide6.QtGui        # noqa: F401
    import PySide6.QtWidgets    # noqa: F401
except Exception:
    for _n in [
        "PySide6", "PySide6.QtCore", "PySide6.QtWidgets", "PySide6.QtGui",
        "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel",
    ]:
        sys.modules.setdefault(_n, types.ModuleType(_n))

# SQLAlchemy
_sa = _stub("sqlalchemy")
_sa_orm = _stub("sqlalchemy.orm")
sys.modules.setdefault("sqlalchemy", _sa)
sys.modules.setdefault("sqlalchemy.orm", _sa_orm)


# ════════════════════════════════════════════════════════════════════════════
# 1) Universe
# ════════════════════════════════════════════════════════════════════════════

from src.core.dmx.universe import Universe


class TestUniverse(unittest.TestCase):

    def setUp(self):
        self.u = Universe(number=1)

    def test_initial_all_zero(self):
        self.assertEqual(self.u.get_all(), bytes(512))

    def test_set_and_get_channel(self):
        self.u.set_channel(1, 200)
        self.assertEqual(self.u.get_channel(1), 200)

    def test_set_channel_boundary_1(self):
        self.u.set_channel(1, 0)
        self.assertEqual(self.u.get_channel(1), 0)

    def test_set_channel_boundary_512(self):
        self.u.set_channel(512, 255)
        self.assertEqual(self.u.get_channel(512), 255)

    def test_set_range(self):
        self.u.set_range(10, bytes([10, 20, 30]))
        self.assertEqual(self.u.get_channel(10), 10)
        self.assertEqual(self.u.get_channel(11), 20)
        self.assertEqual(self.u.get_channel(12), 30)

    def test_clear(self):
        self.u.set_channel(100, 255)
        self.u.clear()
        self.assertEqual(self.u.get_all(), bytes(512))

    def test_get_all_length(self):
        self.assertEqual(len(self.u.get_all()), 512)

    def test_set_channel_out_of_range_raises(self):
        with self.assertRaises((AssertionError, Exception)):
            self.u.set_channel(0, 100)
        with self.assertRaises((AssertionError, Exception)):
            self.u.set_channel(513, 100)

    def test_set_channel_value_out_of_range_raises(self):
        with self.assertRaises((AssertionError, Exception)):
            self.u.set_channel(1, 256)
        with self.assertRaises((AssertionError, Exception)):
            self.u.set_channel(1, -1)

    def test_multiple_channels_independent(self):
        for ch in range(1, 513):
            self.u.set_channel(ch, ch % 256)
        for ch in range(1, 513):
            self.assertEqual(self.u.get_channel(ch), ch % 256)


# ════════════════════════════════════════════════════════════════════════════
# 2) Cue - Serialisierung
# ════════════════════════════════════════════════════════════════════════════

from src.core.engine.cue import Cue


class TestCue(unittest.TestCase):

    def _make_cue(self) -> Cue:
        c = Cue(number=2.5, label="Test", fade_in=1.5, fade_out=0.5,
                delay_in=0.1, delay_out=0.0, follow=3.0)
        c.values = {1: {"intensity": 200, "color_r": 128}, 3: {"pan": 90}}
        return c

    def test_roundtrip(self):
        c = self._make_cue()
        d = c.to_dict()
        c2 = Cue.from_dict(d)
        self.assertAlmostEqual(c2.number, 2.5, places=3)
        self.assertEqual(c2.label, "Test")
        self.assertAlmostEqual(c2.fade_in, 1.5)
        self.assertAlmostEqual(c2.fade_out, 0.5)
        self.assertAlmostEqual(c2.delay_in, 0.1)
        self.assertAlmostEqual(c2.delay_out, 0.0)
        self.assertAlmostEqual(c2.follow or 0.0, 3.0)
        self.assertIn(1, c2.values)
        self.assertEqual(c2.values[1]["intensity"], 200)
        self.assertEqual(c2.values[3]["pan"], 90)

    def test_number_rounded(self):
        c = Cue(number=1.00001)
        self.assertAlmostEqual(c.number, 1.0, places=3)

    def test_default_values(self):
        c = Cue(number=1.0)
        self.assertAlmostEqual(c.fade_in, 2.0)
        self.assertAlmostEqual(c.fade_out, 0.0)
        self.assertIsNone(c.follow)
        self.assertEqual(c.values, {})

    def test_from_dict_int_keys(self):
        d = {
            "number": 1.0,
            "label": "X",
            "fade_in": 0.0,
            "fade_out": 0.0,
            "delay_in": 0.0,
            "delay_out": 0.0,
            "follow": None,
            "values": {"5": {"intensity": 100}},
        }
        c = Cue.from_dict(d)
        self.assertIn(5, c.values)   # Keys muss int sein

    def test_to_dict_keys_are_strings(self):
        c = Cue(number=1.0)
        c.values = {7: {"intensity": 50}}
        d = c.to_dict()
        self.assertIn("7", d["values"])   # JSON-kompatibel (str Keys)


# ════════════════════════════════════════════════════════════════════════════
# 3) FadeState
# ════════════════════════════════════════════════════════════════════════════

from src.core.engine.cue_stack import FadeState, CueStack


class TestFadeState(unittest.TestCase):

    def test_immediate_start_returns_from_vals_during_delay(self):
        from_v = {1: {"intensity": 0}}
        to_v   = {1: {"intensity": 200}}
        fs = FadeState(from_v, to_v, duration=1.0, delay=999.0)
        # Sofort nach Start: noch im Delay → from_vals
        result = fs.current_values()
        self.assertEqual(result[1]["intensity"], 0)

    def test_after_full_duration_returns_to_vals(self):
        from_v = {1: {"intensity": 0}}
        to_v   = {1: {"intensity": 200}}
        # Setze start_time weit in die Vergangenheit
        fs = FadeState(from_v, to_v, duration=0.001, delay=0.0)
        time.sleep(0.05)
        result = fs.current_values()
        self.assertEqual(result[1]["intensity"], 200)
        self.assertTrue(fs.done)

    def test_interpolation_in_range(self):
        from_v = {1: {"intensity": 0}}
        to_v   = {1: {"intensity": 200}}
        fs = FadeState(from_v, to_v, duration=10.0, delay=0.0)
        # Direkt nach Start: t ≈ 0 → nahe 0
        val = fs.current_values()[1]["intensity"]
        self.assertLessEqual(val, 5)

    def test_fid_only_in_to_uses_0_as_from(self):
        from_v = {}
        to_v   = {2: {"intensity": 100}}
        fs = FadeState(from_v, to_v, duration=0.001, delay=0.0)
        time.sleep(0.05)
        result = fs.current_values()
        self.assertEqual(result[2]["intensity"], 100)


# ════════════════════════════════════════════════════════════════════════════
# 4) CueStack
# ════════════════════════════════════════════════════════════════════════════

class TestCueStack(unittest.TestCase):

    def _stack_with_cues(self, n: int = 3) -> CueStack:
        s = CueStack(name="Test Stack")
        for i in range(1, n + 1):
            cue = Cue(number=float(i), fade_in=0.0)
            cue.values = {1: {"intensity": i * 50}}
            s.add_cue(cue)
        return s

    # Initialer Zustand
    def test_initial_state(self):
        s = CueStack()
        self.assertEqual(s.current_index, -1)
        self.assertIsNone(s.current_cue)
        self.assertEqual(s.get_output(), {})

    # Go voranschreiten
    def test_go_advances_index(self):
        s = self._stack_with_cues(3)
        s.go()
        self.assertEqual(s.current_index, 0)
        s.go()
        self.assertEqual(s.current_index, 1)

    def test_go_empty_stack_noop(self):
        s = CueStack()
        s.go()   # Darf nicht abstuerzen
        self.assertEqual(s.current_index, -1)

    def test_go_stops_at_end_without_loop(self):
        s = self._stack_with_cues(2)
        s.go()
        s.go()
        s.go()   # Kein weiteres Voranschreiten
        self.assertEqual(s.current_index, 1)

    def test_go_wraps_with_loop(self):
        s = self._stack_with_cues(2)
        s.loop = True
        s.go()
        s.go()
        s.go()   # Wrap auf 0
        self.assertEqual(s.current_index, 0)

    # Back
    def test_back_at_start_noop(self):
        s = self._stack_with_cues(2)
        s.go()
        s.back()  # Zurueck auf -1? Nein: back() nur wenn _current_idx > 0
        # bei idx=0 noop
        self.assertEqual(s.current_index, 0)

    def test_back_goes_to_previous(self):
        s = self._stack_with_cues(3)
        s.go()
        s.go()   # Cue 1
        s.back()
        self.assertEqual(s.current_index, 0)

    # Stop
    def test_stop_resets(self):
        s = self._stack_with_cues(2)
        s.go()
        s.stop()
        self.assertEqual(s.current_index, -1)
        self.assertEqual(s.get_output(), {})

    # go_to
    def test_go_to_specific_cue(self):
        s = self._stack_with_cues(4)
        s.go_to(3.0)
        self.assertEqual(s.current_index, 2)

    def test_go_to_nonexistent_noop(self):
        s = self._stack_with_cues(2)
        s.go_to(99.0)
        self.assertEqual(s.current_index, -1)

    # add/remove/update
    def test_add_cue_sorted(self):
        s = CueStack()
        s.add_cue(Cue(number=3.0))
        s.add_cue(Cue(number=1.0))
        s.add_cue(Cue(number=2.0))
        self.assertEqual([c.number for c in s.cues], [1.0, 2.0, 3.0])

    def test_remove_cue(self):
        s = self._stack_with_cues(3)
        s.remove_cue(2.0)
        self.assertEqual(len(s.cues), 2)
        numbers = [c.number for c in s.cues]
        self.assertNotIn(2.0, numbers)

    def test_update_existing_cue(self):
        s = self._stack_with_cues(2)
        updated = Cue(number=1.0, label="Updated", fade_in=5.0)
        s.update_cue(updated)
        self.assertEqual(s.cues[0].label, "Updated")
        self.assertEqual(len(s.cues), 2)

    # Serialisierung
    def test_roundtrip(self):
        s = self._stack_with_cues(2)
        s.loop = True
        d = s.to_dict()
        s2 = CueStack.from_dict(d)
        self.assertEqual(s2.name, "Test Stack")
        self.assertTrue(s2.loop)
        self.assertEqual(len(s2.cues), 2)
        self.assertEqual(s2.cues[0].number, 1.0)

    # Output-Callback
    def test_output_callback_on_stop(self):
        outputs = []
        s = self._stack_with_cues(1)
        s.subscribe_output(lambda o: outputs.append(dict(o)))
        s.go()
        s.stop()
        self.assertTrue(len(outputs) >= 1)

    # Cue-change Callback
    def test_cue_change_callback(self):
        events = []
        s = self._stack_with_cues(2)
        s.subscribe_cue(lambda idx, cue: events.append((idx, cue.number)))
        s.go()
        self.assertEqual(events, [(0, 1.0)])
        s.go()
        self.assertEqual(events[-1], (1, 2.0))


# ════════════════════════════════════════════════════════════════════════════
# 5) ChannelModifier + ChannelModifierManager
# ════════════════════════════════════════════════════════════════════════════

from src.core.engine.channel_modifier import (
    ChannelModifier, ChannelModifierManager, CurveType
)


class TestChannelModifier(unittest.TestCase):

    def _mod(self, curve: CurveType, **kw) -> ChannelModifier:
        return ChannelModifier(universe=1, address=1, curve=curve, **kw)

    def test_linear_identity(self):
        m = self._mod(CurveType.LINEAR)
        for v in (0, 127, 255):
            self.assertEqual(m.apply(v), v)

    def test_inverse(self):
        m = self._mod(CurveType.INVERSE)
        self.assertEqual(m.apply(0), 255)
        self.assertEqual(m.apply(255), 0)
        self.assertEqual(m.apply(128), 127)

    def test_scurve_midpoint(self):
        m = self._mod(CurveType.SCURVE)
        # Bei x=0.5 → smoothstep = 0.5 → Wert ~127
        result = m.apply(127)
        self.assertAlmostEqual(result, 127, delta=3)

    def test_scurve_boundaries(self):
        m = self._mod(CurveType.SCURVE)
        self.assertEqual(m.apply(0), 0)
        self.assertEqual(m.apply(255), 255)

    def test_gamma22(self):
        m = self._mod(CurveType.GAMMA22)
        self.assertEqual(m.apply(0), 0)
        self.assertEqual(m.apply(255), 255)
        # Gamma 2.2: dunkler → Mittelpunkt tiefer als 127
        self.assertLess(m.apply(127), 127)

    def test_squared(self):
        m = self._mod(CurveType.SQUARED)
        self.assertEqual(m.apply(0), 0)
        self.assertEqual(m.apply(255), 255)
        # Quadrat: dunkler als linear
        self.assertLess(m.apply(127), 127)

    def test_sqrt(self):
        m = self._mod(CurveType.SQRT)
        self.assertEqual(m.apply(0), 0)
        self.assertEqual(m.apply(255), 255)
        # Wurzel: heller als linear
        self.assertGreater(m.apply(127), 127)

    def test_custom_lut(self):
        lut = [255 - i for i in range(256)]   # Inverse via LUT
        m = self._mod(CurveType.CUSTOM, custom_lut=lut)
        self.assertEqual(m.apply(0), 255)
        self.assertEqual(m.apply(255), 0)

    def test_range_min_max(self):
        # range_min=100, range_max=200: 0 → 100, 255 → 200
        m = ChannelModifier(universe=1, address=1,
                            curve=CurveType.LINEAR,
                            range_min=100, range_max=200)
        self.assertEqual(m.apply(0), 100)
        self.assertEqual(m.apply(255), 200)

    def test_clamp_input(self):
        m = self._mod(CurveType.LINEAR)
        # apply() muss clamp ohne Exception
        self.assertEqual(m.apply(-10), 0)
        self.assertEqual(m.apply(300), 255)


class TestChannelModifierManager(unittest.TestCase):

    def setUp(self):
        self.mgr = ChannelModifierManager()

    def test_add_and_get(self):
        m = ChannelModifier(universe=1, address=5, curve=CurveType.INVERSE)
        self.mgr.add(m)
        self.assertIs(self.mgr.get(1, 5), m)

    def test_remove(self):
        m = ChannelModifier(universe=1, address=5)
        self.mgr.add(m)
        self.mgr.remove(1, 5)
        self.assertIsNone(self.mgr.get(1, 5))

    def test_apply_to_universe_no_modifiers(self):
        data = bytes(range(256)) + bytes(range(256))
        result = self.mgr.apply_to_universe(1, data)
        self.assertEqual(result, data)

    def test_apply_to_universe_inverse(self):
        # Universe 1, Adresse 1: Inverse-Modifier
        m = ChannelModifier(universe=1, address=1, curve=CurveType.INVERSE)
        self.mgr.add(m)
        data = bytes([200] + [0] * 511)
        result = self.mgr.apply_to_universe(1, data)
        self.assertEqual(result[0], 55)    # 255 - 200
        self.assertEqual(result[1], 0)     # Unberuehrt

    def test_apply_to_universe_wrong_universe(self):
        m = ChannelModifier(universe=2, address=1, curve=CurveType.INVERSE)
        self.mgr.add(m)
        data = bytes([200] + [0] * 511)
        result = self.mgr.apply_to_universe(1, data)
        # Universe 1 hat keinen Modifier → unveraendert
        self.assertEqual(result[0], 200)

    def test_clear(self):
        self.mgr.add(ChannelModifier(universe=1, address=1))
        self.mgr.clear()
        self.assertEqual(self.mgr.all(), [])

    def test_save_load_roundtrip(self):
        import tempfile, os
        m = ChannelModifier(universe=1, address=5, name="Test",
                            curve=CurveType.GAMMA22,
                            range_min=10, range_max=240)
        self.mgr.add(m)
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "mods.json")
            self.mgr.save(path)
            mgr2 = ChannelModifierManager()
            mgr2.load(path)
            m2 = mgr2.get(1, 5)
            self.assertIsNotNone(m2)
            self.assertEqual(m2.curve, CurveType.GAMMA22)
            self.assertEqual(m2.range_min, 10)
            self.assertEqual(m2.range_max, 240)
            self.assertEqual(m2.name, "Test")


# ════════════════════════════════════════════════════════════════════════════
# 6) Command-Line Parser (rein logisch, kein AppState noetig)
# ════════════════════════════════════════════════════════════════════════════

from src.core.cmdline.parser import (
    parse, SelectionExpr,
    SetValueCommand, ClearCommand, BlackoutCommand,
    GoCommand, BackCommand, PageCommand, RecordCueCommand,
    HighlightCommand, LowlightCommand, SelectionCommand, ErrorCommand
)


class TestSelectionExpr(unittest.TestCase):

    def test_single(self):
        s = SelectionExpr(add=[3])
        self.assertEqual(s.resolve([1, 2, 3, 4, 5]), [3])

    def test_range(self):
        s = SelectionExpr(ranges=[(2, 4)])
        self.assertEqual(s.resolve([1, 2, 3, 4, 5]), [2, 3, 4])

    def test_range_inverted(self):
        s = SelectionExpr(ranges=[(4, 2)])
        self.assertEqual(s.resolve([1, 2, 3, 4, 5]), [2, 3, 4])

    def test_all(self):
        s = SelectionExpr(all_fixtures=True)
        self.assertEqual(s.resolve([10, 20, 30]), [10, 20, 30])

    def test_exclude(self):
        s = SelectionExpr(ranges=[(1, 5)], excludes=[3])
        result = s.resolve([1, 2, 3, 4, 5])
        self.assertNotIn(3, result)
        self.assertIn(1, result)
        self.assertIn(5, result)

    def test_fid_not_in_patched_excluded(self):
        s = SelectionExpr(add=[99])
        self.assertEqual(s.resolve([1, 2, 3]), [])

    def test_is_empty(self):
        self.assertTrue(SelectionExpr().is_empty())
        self.assertFalse(SelectionExpr(add=[1]).is_empty())
        self.assertFalse(SelectionExpr(all_fixtures=True).is_empty())


class TestCmdlineParser(unittest.TestCase):

    def test_clear(self):
        self.assertIsInstance(parse("clear"), ClearCommand)
        self.assertIsInstance(parse("cl"), ClearCommand)

    def test_blackout(self):
        self.assertIsInstance(parse("blackout"), BlackoutCommand)
        self.assertIsInstance(parse("bo"), BlackoutCommand)

    def test_highlight(self):
        self.assertIsInstance(parse("highlight"), HighlightCommand)
        self.assertIsInstance(parse("hi"), HighlightCommand)

    def test_lowlight(self):
        self.assertIsInstance(parse("lowlight"), LowlightCommand)

    def test_go_default_slot(self):
        cmd = parse("go")
        self.assertIsInstance(cmd, GoCommand)
        self.assertEqual(cmd.slot, 1)

    def test_go_with_slot(self):
        cmd = parse("go 3")
        self.assertIsInstance(cmd, GoCommand)
        self.assertEqual(cmd.slot, 3)

    def test_back(self):
        cmd = parse("back 2")
        self.assertIsInstance(cmd, BackCommand)
        self.assertEqual(cmd.slot, 2)

    def test_page_number(self):
        cmd = parse("page 5")
        self.assertIsInstance(cmd, PageCommand)
        self.assertEqual(cmd.page, 5)

    def test_page_next(self):
        cmd = parse("page +")
        self.assertIsInstance(cmd, PageCommand)
        self.assertEqual(cmd.delta, 1)

    def test_page_prev(self):
        cmd = parse("page -")
        self.assertIsInstance(cmd, PageCommand)
        self.assertEqual(cmd.delta, -1)

    def test_record_cue(self):
        cmd = parse("record cue 2.5")
        self.assertIsInstance(cmd, RecordCueCommand)
        self.assertAlmostEqual(cmd.number, 2.5)

    def test_set_value_pct(self):
        cmd = parse("1 thru 5 @ 80")
        self.assertIsInstance(cmd, SetValueCommand)
        self.assertEqual(cmd.value_pct, 80)
        self.assertEqual(cmd.attribute, "intensity")
        self.assertEqual(cmd.selection.ranges, [(1, 5)])

    def test_set_value_full(self):
        cmd = parse("all @ full")
        self.assertIsInstance(cmd, SetValueCommand)
        self.assertEqual(cmd.value_pct, 100)
        self.assertTrue(cmd.selection.all_fixtures)

    def test_set_value_off(self):
        cmd = parse("3 @ off")
        self.assertIsInstance(cmd, SetValueCommand)
        self.assertEqual(cmd.value_pct, 0)

    def test_set_raw_attribute(self):
        cmd = parse("1 r 200")
        self.assertIsInstance(cmd, SetValueCommand)
        self.assertEqual(cmd.attribute, "color_r")
        self.assertEqual(cmd.value_raw, 200)

    def test_selection_only(self):
        cmd = parse("1 thru 5")
        self.assertIsInstance(cmd, SelectionCommand)
        self.assertEqual(cmd.selection.ranges, [(1, 5)])

    def test_empty_is_error(self):
        cmd = parse("")
        self.assertIsInstance(cmd, ErrorCommand)

    def test_unknown_is_error(self):
        cmd = parse("xyzzy")
        self.assertIsInstance(cmd, ErrorCommand)

    def test_at_without_value_is_error(self):
        cmd = parse("1 @")
        self.assertIsInstance(cmd, ErrorCommand)


# ════════════════════════════════════════════════════════════════════════════
# 7) UndoStack
# ════════════════════════════════════════════════════════════════════════════

from src.core.undo import UndoStack, Command


class TestUndoStack(unittest.TestCase):

    def setUp(self):
        self.stack = UndoStack()

    def _counter_cmd(self, store: list, label: str = "cmd") -> Command:
        """Erstellt ein Command das einen Zaehler inkrementiert/dekrementiert."""
        return Command(
            label=label,
            do=lambda: store.append(+1),
            undo=lambda: store.append(-1),
            redo=lambda: store.append(+1),
        )

    def test_push_executes_do(self):
        store = []
        self.stack.push(self._counter_cmd(store))
        self.assertEqual(store, [+1])

    def test_push_without_execute(self):
        store = []
        self.stack.push(self._counter_cmd(store), execute=False)
        self.assertEqual(store, [])   # do() wurde nicht aufgerufen
        self.assertTrue(self.stack.can_undo())

    def test_undo(self):
        store = []
        self.stack.push(self._counter_cmd(store))
        result = self.stack.undo()
        self.assertTrue(result)
        self.assertIn(-1, store)

    def test_redo(self):
        store = []
        self.stack.push(self._counter_cmd(store))
        self.stack.undo()
        result = self.stack.redo()
        self.assertTrue(result)
        self.assertEqual(store.count(+1), 2)

    def test_push_clears_redo(self):
        store = []
        self.stack.push(self._counter_cmd(store, "A"))
        self.stack.undo()
        self.stack.push(self._counter_cmd(store, "B"))
        self.assertFalse(self.stack.can_redo())

    def test_undo_empty_returns_false(self):
        self.assertFalse(self.stack.undo())

    def test_redo_empty_returns_false(self):
        self.assertFalse(self.stack.redo())

    def test_can_undo_redo(self):
        store = []
        self.assertFalse(self.stack.can_undo())
        self.assertFalse(self.stack.can_redo())
        self.stack.push(self._counter_cmd(store))
        self.assertTrue(self.stack.can_undo())
        self.assertFalse(self.stack.can_redo())
        self.stack.undo()
        self.assertFalse(self.stack.can_undo())
        self.assertTrue(self.stack.can_redo())

    def test_labels(self):
        store = []
        self.stack.push(self._counter_cmd(store, "Aktion A"))
        self.assertEqual(self.stack.undo_label(), "Aktion A")
        self.stack.undo()
        self.assertEqual(self.stack.redo_label(), "Aktion A")

    def test_max_size_cap(self):
        store = []
        for _ in range(UndoStack.MAX_SIZE + 20):
            self.stack.push(self._counter_cmd(store), execute=False)
        self.assertLessEqual(len(self.stack._undo), UndoStack.MAX_SIZE)

    def test_clear(self):
        store = []
        self.stack.push(self._counter_cmd(store))
        self.stack.clear()
        self.assertFalse(self.stack.can_undo())
        self.assertFalse(self.stack.can_redo())

    def test_listener_called_on_push(self):
        events = []
        self.stack.subscribe(lambda: events.append("change"))
        store = []
        self.stack.push(self._counter_cmd(store))
        self.assertGreater(len(events), 0)

    def test_listener_called_on_undo_redo(self):
        events = []
        store = []
        self.stack.push(self._counter_cmd(store))
        self.stack.subscribe(lambda: events.append("change"))
        self.stack.undo()
        self.stack.redo()
        self.assertGreaterEqual(len(events), 2)

    def test_multiple_undo_redo(self):
        store = []
        for _ in range(5):
            self.stack.push(self._counter_cmd(store, "x"), execute=False)
        for _ in range(5):
            self.stack.undo()
        self.assertFalse(self.stack.can_undo())
        for _ in range(5):
            self.stack.redo()
        self.assertFalse(self.stack.can_redo())

    def test_push_simple(self):
        store = []
        self.stack.push_simple("simple", lambda: store.append(1), lambda: store.append(-1))
        self.assertEqual(store, [1])
        self.stack.undo()
        self.assertEqual(store[-1], -1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
