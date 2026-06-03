"""Collection-Tick: kein doppeltes dt + Kinder stoppen mit der Collection.

Audit-Befund (collection.py): write() erhoehte child._elapsed UND rief child.write()
(das selbst hochzaehlt) -> doppelte Zeit; ausserdem blieb child._running nach dem
Collection-Stop True.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.function import Function, FunctionType
from src.core.engine.collection import Collection


class _Child(Function):
    function_type = FunctionType.Scene

    def __init__(self, fid=None):
        super().__init__("child", fid)
        self.write_calls = 0
        self.start_calls = 0

    def _on_start(self):
        self.start_calls += 1

    def write(self, universes, patch_cache, dt, function_registry=None):
        if not self._running:
            return
        self.write_calls += 1
        self._elapsed += dt


class TestCollection(unittest.TestCase):
    def setUp(self):
        self.child = _Child()
        self.reg = {self.child.id: self.child}
        self.col = Collection("c")
        self.col.add_function(self.child.id)

    def test_no_double_dt(self):
        self.col.start()
        for _ in range(5):
            self.col.write({}, [], 0.1, self.reg)
        # 5 Frames * 0.1 = 0.5 (nicht 1.0 durch doppeltes Zaehlen)
        self.assertAlmostEqual(self.child._elapsed, 0.5, places=6)
        self.assertEqual(self.child.write_calls, 5)

    def test_child_started_once(self):
        self.col.start()
        for _ in range(3):
            self.col.write({}, [], 0.1, self.reg)
        self.assertEqual(self.child.start_calls, 1)
        self.assertTrue(self.child.is_running)

    def test_child_stops_with_collection(self):
        self.col.start()
        self.col.write({}, [], 0.1, self.reg)
        self.assertTrue(self.child.is_running)
        self.col.stop()
        self.assertFalse(self.child.is_running)


if __name__ == "__main__":
    unittest.main()
