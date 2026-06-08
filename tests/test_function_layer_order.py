"""Regression: FunctionManager.tick() muss in Start-Reihenfolge (LTP) schreiben.

Frueher iterierte tick() ueber das ungeordnete _running_ids-Set. Schrieben zwei
laufende Funktionen denselben DMX-Kanal (z. B. zwei Effekte auf denselben Dimmer),
gewann ein zufaelliger Writer (Hash-Reihenfolge des Sets) statt der zuletzt
gestarteten Funktion -> nicht-deterministisches Ueberschreiben von Werten.

Erwartung (Last-Takes-Precedence): die zuletzt gestartete Funktion schreibt
zuletzt und gewinnt damit bei Kanal-Ueberschneidung.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx.universe import Universe
from src.core.engine.function_manager import FunctionManager


class _WriterFunc:
    """Minimal-Funktion: schreibt beim Tick einen festen Wert auf Kanal 1."""

    def __init__(self, fid: int, value: int):
        self.id = fid
        self._value = value
        self.is_running = True
        self.intensity = 1.0

    def start(self):
        self.is_running = True

    def stop(self):
        self.is_running = False

    def write(self, universes, patch_cache, dt, registry):
        universes[1].set_channel(1, self._value)


def _run(start_order):
    """Startet Funktionen in der gegebenen Reihenfolge, tickt einmal und liefert
    den resultierenden Wert auf Kanal 1."""
    fm = FunctionManager()
    for fid, val in start_order:
        fm._functions[fid] = _WriterFunc(fid, val)
    for fid, _ in start_order:
        fm.start(fid)
    u = {1: Universe(1)}
    fm.tick(u, [], 0.02)
    return u[1].get_channel(1)


class FunctionLayerOrderTest(unittest.TestCase):
    def test_last_started_wins_regardless_of_fid(self):
        # fids bewusst so gewaehlt, dass die Set-Hash-Reihenfolge der
        # Start-Reihenfolge widerspricht (12 landet im Set vor 5).
        self.assertEqual(_run([(5, 200), (12, 50)]), 50)
        self.assertEqual(_run([(12, 50), (5, 200)]), 200)

    def test_restart_moves_function_to_top(self):
        fm = FunctionManager()
        fm._functions[5] = _WriterFunc(5, 200)
        fm._functions[12] = _WriterFunc(12, 50)
        fm.start(5)
        fm.start(12)  # 12 zuletzt -> gewinnt
        u = {1: Universe(1)}
        fm.tick(u, [], 0.02)
        self.assertEqual(u[1].get_channel(1), 50)
        fm.start(5)  # 5 erneut starten -> ans Ende -> gewinnt jetzt
        u = {1: Universe(1)}
        fm.tick(u, [], 0.02)
        self.assertEqual(u[1].get_channel(1), 200)

    def test_stop_keeps_order_consistent(self):
        fm = FunctionManager()
        fm._functions[5] = _WriterFunc(5, 200)
        fm._functions[12] = _WriterFunc(12, 50)
        fm.start(5)
        fm.start(12)
        fm.stop(12)  # nur noch 5 laeuft
        u = {1: Universe(1)}
        fm.tick(u, [], 0.02)
        self.assertEqual(u[1].get_channel(1), 200)
        self.assertEqual(fm._start_order, [5])


if __name__ == "__main__":
    unittest.main()
