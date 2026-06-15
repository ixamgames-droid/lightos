"""P1: Intelligenter Kanalvorschlag (AppState.suggest_address).

Lueckenbewusst, pro Universum, kollisionsfrei; None wenn kein
zusammenhaengender Bereich mehr frei ist.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import AppState


class _Fx:
    def __init__(self, fid, universe, address, channel_count):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.channel_count = channel_count


def _state(*fixtures):
    st = AppState.__new__(AppState)   # ohne __init__ (keine DB/Threads)
    st._patch_cache = list(fixtures)
    return st


class SuggestAddressTest(unittest.TestCase):
    def test_appends_after_last_used(self):
        # Kanaele 1-46 belegt -> 8ch-Fixture startet bei 47
        st = _state(_Fx(1, 1, 1, 30), _Fx(2, 1, 31, 16))
        self.assertEqual(st.suggest_address(1, 8), 47)

    def test_uses_gap_if_it_fits(self):
        # Luecke 9-24 (16 Kanaele) zwischen zwei Fixtures wird genutzt
        st = _state(_Fx(1, 1, 1, 8), _Fx(2, 1, 25, 8))
        self.assertEqual(st.suggest_address(1, 16), 9)
        self.assertEqual(st.suggest_address(1, 8), 9)

    def test_skips_too_small_gap(self):
        # Luecke 9-12 (4 Kanaele) reicht fuer 8ch nicht -> hinter das Ende
        st = _state(_Fx(1, 1, 1, 8), _Fx(2, 1, 13, 8))
        self.assertEqual(st.suggest_address(1, 8), 21)

    def test_empty_universe_starts_at_1(self):
        st = _state(_Fx(1, 2, 1, 100))   # anderes Universum stoert nicht
        self.assertEqual(st.suggest_address(1, 12), 1)

    def test_full_universe_returns_none(self):
        st = _state(_Fx(1, 1, 1, 510))
        self.assertIsNone(st.suggest_address(1, 8))
        self.assertEqual(st.suggest_address(1, 2), 511)

    def test_exclude_fid(self):
        # Beim Bearbeiten eines Fixtures zaehlt sein eigener Bereich nicht
        st = _state(_Fx(1, 1, 1, 8))
        self.assertEqual(st.suggest_address(1, 8, exclude_fid=1), 1)

    def test_unsorted_patch_and_overlap_tolerant(self):
        # Unsortierte Adressen + (defekter) Overlap duerfen nichts kaputt machen
        st = _state(_Fx(2, 1, 20, 8), _Fx(1, 1, 1, 8), _Fx(3, 1, 24, 8))
        self.assertEqual(st.suggest_address(1, 8), 9)
        self.assertEqual(st.suggest_address(1, 20), 32)

    def test_invalid_count(self):
        st = _state()
        self.assertIsNone(st.suggest_address(1, "abc"))


if __name__ == "__main__":
    unittest.main()
