"""F-17: Layer-Priorität im Engine-Merge.

FunctionManager.tick() tickt jetzt nach (priority, Start-Reihenfolge): höhere
Priorität schreibt zuletzt und gewinnt bei Kanal-Überschneidung; gleiche
Priorität fällt auf die Start-Reihenfolge zurück (Verhalten wie bisher).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx.universe import Universe
from src.core.engine.function_manager import FunctionManager


class _WriterFunc:
    """Minimal-Funktion: schreibt beim Tick einen festen Wert auf Kanal 1."""

    def __init__(self, fid, value, priority=0):
        self.id = fid
        self._value = value
        self.is_running = True
        self.intensity = 1.0
        self.priority = priority

    def start(self):
        self.is_running = True

    def stop(self):
        self.is_running = False

    def write(self, universes, patch_cache, dt, registry):
        universes[1].set_channel(1, self._value)


def _run(specs):
    """specs: Liste (fid, value, priority) in START-Reihenfolge. Liefert Kanal 1."""
    fm = FunctionManager()
    for fid, val, prio in specs:
        fm._functions[fid] = _WriterFunc(fid, val, prio)
    for fid, _, _ in specs:
        fm.start(fid)
    u = {1: Universe(1)}
    fm.tick(u, [], 0.02)
    return u[1].get_channel(1)


class FunctionPriorityTest(unittest.TestCase):
    def test_higher_priority_wins_regardless_of_start_order(self):
        # A (prio 5) zuerst gestartet, B (prio 0) zuletzt -> A gewinnt trotzdem.
        self.assertEqual(_run([(5, 200, 5), (12, 50, 0)]), 200)
        # Reihenfolge umgedreht -> A (prio 5) gewinnt weiterhin.
        self.assertEqual(_run([(12, 50, 0), (5, 200, 5)]), 200)

    def test_equal_priority_last_started_wins(self):
        # Gleiche Priorität -> Start-Reihenfolge entscheidet (wie bisher).
        self.assertEqual(_run([(5, 200, 2), (12, 50, 2)]), 50)
        self.assertEqual(_run([(12, 50, 2), (5, 200, 2)]), 200)

    def test_negative_priority_loses(self):
        # A (prio -1) zuletzt gestartet, B (prio 0) zuerst -> B gewinnt.
        self.assertEqual(_run([(12, 50, 0), (5, 200, -1)]), 50)

    def test_default_zero_preserves_start_order(self):
        # Default-Priorität 0 -> reines Last-Started-Wins (0 Regression).
        self.assertEqual(_run([(5, 200, 0), (12, 50, 0)]), 50)

    def test_three_layers_priority_then_start_order(self):
        # prio: A=0, B=1, C=1; Start A,B,C. Höchste prio = B,C; C zuletzt -> C.
        self.assertEqual(_run([(1, 10, 0), (2, 20, 1), (3, 30, 1)]), 30)

    def test_higher_priority_low_intensity_wins_on_dim_channel(self):
        # Regression (Review): höhere Priorität mit intensity<1.0 muss auch dann
        # gewinnen (und skaliert werden), wenn sie denselben Rohwert wie ein
        # darunterliegender Voll-Intensitäts-Effekt schreibt. Früher (Wert-Diff)
        # wurde der Kanal übersprungen -> der unskalierte Wert überlebte.
        fm = FunctionManager()
        fm._dim_addr_map = lambda pc: {1: frozenset({1})}   # Kanal 1 = Dimmer
        low = _WriterFunc(1, 200, priority=0)
        low.intensity = 1.0
        high = _WriterFunc(2, 200, priority=5)
        high.intensity = 0.5
        fm._functions[1] = low
        fm._functions[2] = high
        fm.start(1)
        fm.start(2)
        u = {1: Universe(1)}
        fm.tick(u, [], 0.02)
        self.assertEqual(u[1].get_channel(1), 100)   # 200*0.5: hohe Prio gewinnt skaliert


class FunctionPriorityPersistenceTest(unittest.TestCase):
    def test_priority_roundtrip(self):
        fm = FunctionManager()
        s = fm.new_scene("PrioScene")
        s.priority = 7
        data = fm.to_dict()
        fm2 = FunctionManager()
        fm2.from_dict(data)
        loaded = [f for f in fm2.all() if f.name == "PrioScene"]
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].priority, 7)

    def test_old_show_without_priority_defaults_zero(self):
        fm = FunctionManager()
        fm.new_scene("OldScene")
        data = fm.to_dict()
        for fd in data["functions"]:           # alte Show ohne priority-Key
            fd.pop("priority", None)
        fm2 = FunctionManager()
        fm2.from_dict(data)
        loaded = [f for f in fm2.all() if f.name == "OldScene"]
        self.assertEqual(loaded[0].priority, 0)

    def test_efx_priority_via_manager_roundtrip(self):
        fm = FunctionManager()
        e = fm.new_efx("PrioEfx")
        e.priority = 4
        fm2 = FunctionManager()
        fm2.from_dict(fm.to_dict())
        loaded = [f for f in fm2.all() if f.name == "PrioEfx"]
        self.assertEqual(loaded[0].priority, 4)

    def test_matrix_apply_dict_priority_roundtrip(self):
        # Deckt den Matrix-Draft-Commit ab (_save_edit -> apply_dict(to_dict)).
        from src.core.engine.rgb_matrix import RgbMatrixInstance
        m = RgbMatrixInstance(name="MX")
        m.priority = 9
        m2 = RgbMatrixInstance(name="MX2")
        m2.apply_dict(m.to_dict())
        self.assertEqual(m2.priority, 9)


if __name__ == "__main__":
    unittest.main()
