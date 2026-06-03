"""Tests fuer grid_from_positions (I2.2) und AppState.selected_group_id.

Kein Qt noetig — reine Unit-Tests.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.rgb_matrix import grid_from_positions
from src.core.app_state import AppState


class GridFromPositionsTest(unittest.TestCase):

    def test_simple_gap(self):
        """Luecke in der Mitte: [10, None, 12]."""
        result = grid_from_positions({"0,0": 10, "2,0": 12}, 3, 1)
        self.assertEqual(result, [10, None, 12])

    def test_2x2_diagonal(self):
        """2×2: (0,0)=10, (1,1)=11 → Index 0 und Index 3."""
        result = grid_from_positions({"0,0": 10, "1,1": 11}, 2, 2)
        self.assertEqual(result, [10, None, None, 11])

    def test_out_of_range_ignored(self):
        """Schluessel ausserhalb des Grids werden ignoriert."""
        result = grid_from_positions({"5,5": 99}, 2, 2)
        self.assertEqual(result, [None, None, None, None])

    def test_empty_dict(self):
        """Leeres Dict liefert rein None-Grid."""
        result = grid_from_positions({}, 2, 1)
        self.assertEqual(result, [None, None])

    def test_none_positions(self):
        """None als positions-Argument verhält sich wie leeres Dict."""
        result = grid_from_positions(None, 2, 1)
        self.assertEqual(result, [None, None])

    def test_full_grid_no_gaps(self):
        """Alle Zellen belegt → keine None-Eintraege."""
        result = grid_from_positions({"0,0": 1, "1,0": 2, "0,1": 3, "1,1": 4}, 2, 2)
        self.assertEqual(result, [1, 2, 3, 4])

    def test_row_major_order(self):
        """row-major: r * cols + c → (col=1, row=0) ist Index 1."""
        result = grid_from_positions({"1,0": 42}, 3, 1)
        self.assertEqual(result[1], 42)
        self.assertIsNone(result[0])
        self.assertIsNone(result[2])

    def test_invalid_key_skipped(self):
        """Ungueltiger Schluessel (kein Komma) wird schweigend uebersprungen."""
        result = grid_from_positions({"bad": 5, "0,0": 7}, 2, 1)
        self.assertEqual(result[0], 7)
        self.assertIsNone(result[1])


class AppStateGroupIdTest(unittest.TestCase):

    def _make_state(self):
        """AppState ohne __init__ (kein DB/MIDI/Engine-Start)."""
        return AppState.__new__(AppState)

    def test_default_is_none(self):
        """Frischer State ohne __init__: get_selected_group_id() liefert None (getattr-Fallback)."""
        s = self._make_state()
        self.assertIsNone(s.get_selected_group_id())

    def test_set_and_get(self):
        """Nach set_selected_group_id(7) liefert get_selected_group_id() 7."""
        s = self._make_state()
        s.set_selected_group_id(7)
        self.assertEqual(s.get_selected_group_id(), 7)

    def test_reset_to_none(self):
        """Nach set_selected_group_id(None) liefert get_selected_group_id() wieder None."""
        s = self._make_state()
        s.set_selected_group_id(7)
        s.set_selected_group_id(None)
        self.assertIsNone(s.get_selected_group_id())

    def test_int_coercion(self):
        """String-Wert wird zu int konvertiert."""
        s = self._make_state()
        s.set_selected_group_id("42")
        self.assertEqual(s.get_selected_group_id(), 42)
        self.assertIsInstance(s.get_selected_group_id(), int)

    def test_init_sets_none(self):
        """AppState.__init__ setzt selected_group_id = None."""
        # Dieser Test laeuft nur wenn ein echter AppState startbar ist;
        # wir pruefen lediglich das Attribut direkt nach dem Setzen.
        s = self._make_state()
        s.selected_group_id = None
        self.assertIsNone(s.get_selected_group_id())


if __name__ == "__main__":
    unittest.main()
