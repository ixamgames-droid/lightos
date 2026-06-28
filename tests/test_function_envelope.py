"""B2 / ARC-04: zeitbasierte Ein-/Ausblend-Hüllkurve (env_fade_in/out) als
Engine-Schicht im FunctionManager.tick — wirkt als Output-Multiplikator über ALLE
Kanäle (nicht nur Dimmer), Fade-Out über einen Release-State nach stop()."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx.universe import Universe
from src.core.engine.function import Function
from src.core.engine.function_manager import FunctionManager


class _Writer(Function):
    """Minimal-Funktion: schreibt beim Tick einen festen Wert auf Kanal 1."""

    def __init__(self, value):
        super().__init__("W")
        self._value = value

    def write(self, universes, patch_cache, dt, registry=None):
        universes[1].set_channel(1, self._value)


class EnvelopeFactorTest(unittest.TestCase):
    def test_fade_in_ramps_up(self):
        f = _Writer(255)
        f.env_fade_in = 1.0
        f.start()
        self.assertAlmostEqual(f.env_factor(0.5), 0.5, places=2)
        self.assertAlmostEqual(f.env_factor(0.5), 1.0, places=2)
        self.assertAlmostEqual(f.env_factor(0.5), 1.0, places=2)   # bleibt voll

    def test_no_fade_returns_full(self):
        f = _Writer(255)
        f.start()
        self.assertEqual(f.env_factor(0.5), 1.0)

    def test_fade_out_ramps_down_after_release(self):
        f = _Writer(255)
        f.env_fade_out = 1.0
        f.start()
        self.assertEqual(f.env_factor(0.1), 1.0)   # vor release voll
        f.release()
        self.assertAlmostEqual(f.env_factor(0.5), 0.5, places=2)
        self.assertFalse(f.env_release_done())
        self.assertAlmostEqual(f.env_factor(0.6), 0.0, places=2)
        self.assertTrue(f.env_release_done())

    def test_start_resets_release(self):
        f = _Writer(255)
        f.env_fade_out = 1.0
        f.start()
        f.release()
        f.start()                                   # Neustart hebt Release auf
        self.assertFalse(f._releasing)
        self.assertEqual(f.env_factor(0.1), 1.0)

    def test_env_curve_shapes_fade(self):
        # FW-4: S-Kurve blendet am Anfang langsamer ein als linear.
        f = _Writer(255)
        f.env_fade_in = 1.0
        f.env_curve = "scurve"
        f.start()
        val = f.env_factor(0.25)                     # linear wäre 0.25
        self.assertGreater(val, 0.0)
        self.assertLess(val, 0.25)

    def test_env_curve_linear_is_identity(self):
        f = _Writer(255)
        f.env_fade_in = 1.0
        f.env_curve = "linear"
        f.start()
        self.assertAlmostEqual(f.env_factor(0.3), 0.3, places=3)


class EnvelopeInTickTest(unittest.TestCase):
    def _fm_with(self, f):
        fm = FunctionManager()
        fm._functions[f.id] = f
        fm.start(f.id)
        return fm

    def test_fade_in_scales_all_channels(self):
        # Kanal 1 ist KEIN Dimmer (kein Patch) -> intensity würde ihn nicht
        # skalieren; die Hüllkurve aber schon (Beweis: env wirkt auf alle Kanäle).
        f = _Writer(200)
        f.env_fade_in = 2.0
        fm = self._fm_with(f)
        u = {1: Universe(1)}
        fm.tick(u, [], 1.0)                          # _env_elapsed=1.0 -> env=0.5
        self.assertEqual(u[1].get_channel(1), 100)

    def test_default_no_envelope_unchanged(self):
        f = _Writer(200)
        fm = self._fm_with(f)
        u = {1: Universe(1)}
        fm.tick(u, [], 0.02)
        self.assertEqual(u[1].get_channel(1), 200)   # 0 Regression ohne Hüllkurve

    def test_fade_out_keeps_running_then_finishes(self):
        f = _Writer(200)
        f.env_fade_out = 1.0
        fm = self._fm_with(f)
        fm.stop(f.id)                                # -> Release, bleibt laufend
        self.assertIn(f.id, fm._running_ids)
        u = {1: Universe(1)}
        fm.tick(u, [], 0.5)                          # env 0.5 -> 100, noch laufend
        self.assertEqual(u[1].get_channel(1), 100)
        self.assertIn(f.id, fm._running_ids)
        fm.tick(u, [], 0.6)                          # release fertig -> entfernt
        self.assertNotIn(f.id, fm._running_ids)

    def test_stop_all_is_immediate(self):
        f = _Writer(200)
        f.env_fade_out = 5.0
        fm = self._fm_with(f)
        fm.stop_all()                                # Sofort-Stopp, kein Fade-Out
        self.assertNotIn(f.id, fm._running_ids)
        self.assertFalse(f.is_running)


class EnvelopePersistenceTest(unittest.TestCase):
    def test_env_roundtrip(self):
        fm = FunctionManager()
        s = fm.new_scene("EnvScene")
        s.env_fade_in = 1.5
        s.env_fade_out = 2.5
        fm2 = FunctionManager()
        fm2.from_dict(fm.to_dict())
        loaded = [f for f in fm2.all() if f.name == "EnvScene"][0]
        self.assertAlmostEqual(loaded.env_fade_in, 1.5)
        self.assertAlmostEqual(loaded.env_fade_out, 2.5)

    def test_env_curve_roundtrip(self):
        fm = FunctionManager()
        s = fm.new_scene("CurveScene")
        s.env_curve = "ease_in"
        fm2 = FunctionManager()
        fm2.from_dict(fm.to_dict())
        loaded = [f for f in fm2.all() if f.name == "CurveScene"][0]
        self.assertEqual(loaded.env_curve, "ease_in")

    def test_matrix_apply_dict_env_roundtrip(self):
        # Matrix-Draft-Commit (_save_edit -> apply_dict(to_dict)) muss env halten.
        from src.core.engine.rgb_matrix import RgbMatrixInstance
        m = RgbMatrixInstance(name="MXenv")
        m.env_fade_in = 3.0
        m.env_fade_out = 4.0
        m.env_curve = "snap"
        m2 = RgbMatrixInstance(name="x")
        m2.apply_dict(m.to_dict())
        self.assertEqual((m2.env_fade_in, m2.env_fade_out), (3.0, 4.0))
        self.assertEqual(m2.env_curve, "snap")

    def test_matrix_apply_dict_tempo_roundtrip(self):
        # Matrix-Editor-Drafts duerfen die Tempo-Sync-Bindung nicht verlieren.
        from src.core.engine.rgb_matrix import RgbMatrixInstance
        m = RgbMatrixInstance(name="MXtempo")
        m.tempo_bus_id = "Global"
        m.tempo_multiplier = 2.0
        m.phase_offset = 0.25
        m.sync_group = "Farben"
        m2 = RgbMatrixInstance(name="x")
        m2.apply_dict(m.to_dict())
        self.assertEqual(m2.tempo_bus_id, "Global")
        self.assertEqual(m2.tempo_multiplier, 2.0)
        self.assertEqual(m2.phase_offset, 0.25)
        self.assertEqual(m2.sync_group, "Farben")

    def test_old_show_defaults_zero(self):
        fm = FunctionManager()
        fm.new_scene("Old")
        data = fm.to_dict()
        for fd in data["functions"]:
            fd.pop("env_fade_in", None)
            fd.pop("env_fade_out", None)
        fm2 = FunctionManager()
        fm2.from_dict(data)
        loaded = [f for f in fm2.all() if f.name == "Old"][0]
        self.assertEqual(loaded.env_fade_in, 0.0)
        self.assertEqual(loaded.env_fade_out, 0.0)


if __name__ == "__main__":
    unittest.main()
