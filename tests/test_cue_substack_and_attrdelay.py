"""B3 Cue-Gruppe:
  F-6  — Pro-Attribut-Verzögerung (attr_delays) als verschobene Fade-Zeitachse.
  F-16 — Sequence-in-Sequence: eine Cue startet/mischt eine referenzierte Cueliste.

FadeState ist wanduhr-basiert (time.monotonic); für deterministische Tests wird
``start_time`` zurückgesetzt, um eine bestimmte verstrichene Zeit zu simulieren.
"""
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.cue import Cue
from src.core.engine.cue_stack import CueStack, FadeState


# ── F-6: Pro-Attribut-Verzögerung ────────────────────────────────────────────

class AttrDelayTest(unittest.TestCase):
    def _fs(self, attr_delays=None, curve="linear"):
        return FadeState({1: {"a": 0, "b": 0}}, {1: {"a": 100, "b": 100}},
                         duration=1.0, delay=0.0, curve=curve,
                         attr_delays=attr_delays)

    def test_delayed_attr_starts_later(self):
        fs = self._fs({1: {"b": 1.0}})           # b startet 1 s später
        fs.start_time = time.monotonic() - 0.5
        v = fs.current_values()
        self.assertAlmostEqual(v[1]["a"], 50, delta=3)   # a fadet normal
        self.assertEqual(v[1]["b"], 0)                   # b noch in Verzögerung
        self.assertFalse(fs.done)

    def test_delayed_attr_then_runs(self):
        fs = self._fs({1: {"b": 1.0}})
        fs.start_time = time.monotonic() - 1.5           # a fertig, b bei 0.5
        v = fs.current_values()
        self.assertEqual(v[1]["a"], 100)
        self.assertAlmostEqual(v[1]["b"], 50, delta=4)
        self.assertFalse(fs.done)                        # b braucht bis 2.0 s

    def test_done_only_when_last_attr_finishes(self):
        fs = self._fs({1: {"b": 1.0}})
        fs.start_time = time.monotonic() - 2.1           # auch b fertig
        v = fs.current_values()
        self.assertEqual(v[1]["b"], 100)
        self.assertTrue(fs.done)

    def test_no_attr_delays_is_unchanged(self):
        # Regression: ohne attr_delays exakt der bisherige gemeinsame Fortschritt.
        fs = self._fs(None)
        fs.start_time = time.monotonic() - 0.5
        v = fs.current_values()
        self.assertAlmostEqual(v[1]["a"], 50, delta=3)
        self.assertAlmostEqual(v[1]["b"], 50, delta=3)

    def test_manual_ignores_attr_delays(self):
        fs = self._fs({1: {"b": 5.0}})
        fs.manual = True
        fs.manual_pos = 0.5
        v = fs.current_values()
        self.assertAlmostEqual(v[1]["a"], 50, delta=3)
        self.assertAlmostEqual(v[1]["b"], 50, delta=3)   # Delay beim Scrub ignoriert

    def test_cue_roundtrip_attr_delays(self):
        c = Cue(1.0, values={5: {"pan": 128}}, attr_delays={5: {"pan": 0.3}})
        c2 = Cue.from_dict(c.to_dict())
        self.assertEqual(c2.attr_delays, {5: {"pan": 0.3}})

    def test_cue_old_show_defaults_empty(self):
        c = Cue.from_dict({"number": 1.0})
        self.assertEqual(c.attr_delays, {})

    def test_from_dict_skips_malformed_attr_delays(self):
        # Hand-editierte/kaputte Shows dürfen NICHT werfen (sonst Cuelisten-Verlust).
        c = Cue.from_dict({"number": 1.0, "attr_delays": "oops"})
        self.assertEqual(c.attr_delays, {})
        c = Cue.from_dict({"number": 1.0, "attr_delays": {"x": {"pan": 0.3}}})
        self.assertEqual(c.attr_delays, {})            # Nicht-int-Key übersprungen
        c = Cue.from_dict({"number": 1.0,
                           "attr_delays": {"5": {"pan": "fast", "tilt": 0.2}}})
        self.assertEqual(c.attr_delays, {5: {"tilt": 0.2}})   # nur valider Wert

    def test_from_dict_skips_malformed_values(self):
        c = Cue.from_dict({"number": 1.0, "values": "kaputt"})
        self.assertEqual(c.values, {})
        c = Cue.from_dict({"number": 1.0, "values": {"x": {"dimmer": 1}, "3": {"d": 2}}})
        self.assertEqual(c.values, {3: {"d": 2}})

    def test_cuestack_survives_bad_cue(self):
        # Eine Cue mit kaputten attr_delays darf die restlichen Cues nicht killen.
        data = {
            "name": "S",
            "cues": [
                {"number": 1.0, "values": {"1": {"dimmer": 255}}},
                {"number": 2.0, "attr_delays": {"bad": {"x": "y"}}},
            ],
        }
        st = CueStack.from_dict(data)
        self.assertEqual(len(st.cues), 2)
        self.assertEqual(st.cues[1].attr_delays, {})


# ── F-16: Sequence-in-Sequence ───────────────────────────────────────────────

def _stack(name, values, **cue_kw):
    s = CueStack(name)
    s.add_cue(Cue(1.0, values=values, fade_in=0.0, **cue_kw))
    return s


def _settle(stack):
    """Treibt den laufenden Fade sofort zu Ende (ohne zu warten)."""
    if stack._fade is not None:
        stack._fade.start_time -= 5.0


class SubStackTest(unittest.TestCase):
    def _wire(self, *stacks):
        lst = list(stacks)

        def resolver(idx):
            return lst[idx] if isinstance(idx, int) and 0 <= idx < len(lst) else None
        for s in lst:
            s._resolve_sub = resolver
        return lst

    def test_sub_stack_output_is_merged(self):
        a = _stack("A", {1: {"dimmer": 100}}, sub_stack_ref=1)
        b = _stack("B", {2: {"dimmer": 200}})
        self._wire(a, b)
        a.go()
        _settle(a)
        a.tick()            # A settelt, B wird gestartet
        _settle(b)
        a.tick()            # B settelt -> gemischt
        out = a.get_output()
        self.assertEqual(out.get(1, {}).get("dimmer"), 100)
        self.assertEqual(out.get(2, {}).get("dimmer"), 200)

    def test_cycle_does_not_recurse(self):
        a = _stack("A", {1: {"dimmer": 100}}, sub_stack_ref=1)
        b = _stack("B", {2: {"dimmer": 200}}, sub_stack_ref=0)   # zurück auf A
        self._wire(a, b)
        a.go()
        for _ in range(5):
            a.tick()        # darf NICHT in RecursionError/Deadlock laufen
        out = a.get_output()
        self.assertIn(2, out)     # B trotzdem gemischt

    def test_self_reference_ignored(self):
        a = _stack("A", {1: {"dimmer": 100}}, sub_stack_ref=0)   # zeigt auf sich
        self._wire(a)
        a.go()
        _settle(a)
        a.tick()
        self.assertIsNone(a._active_sub)
        self.assertNotIn(2, a.get_output())

    def test_sub_drops_when_leaving_cue(self):
        a = CueStack("A")
        a.add_cue(Cue(1.0, values={1: {"dimmer": 100}}, fade_in=0.0, sub_stack_ref=1))
        a.add_cue(Cue(2.0, values={1: {"dimmer": 50}}, fade_in=0.0))   # ohne Sub
        b = _stack("B", {2: {"dimmer": 200}})
        self._wire(a, b)
        a.go(); _settle(a); a.tick(); _settle(b); a.tick()
        self.assertIn(2, a.get_output())          # Sub aktiv
        a.go()                                    # weiter auf Cue 2 (ohne Sub)
        _settle(a); a.tick()
        self.assertNotIn(2, a.get_output())       # Sub-Kanal weg
        self.assertEqual(b.current_index, -1)     # Sub gestoppt

    def test_stop_stops_sub(self):
        a = _stack("A", {1: {"dimmer": 100}}, sub_stack_ref=1)
        b = _stack("B", {2: {"dimmer": 200}})
        self._wire(a, b)
        a.go(); _settle(a); a.tick()
        self.assertIsNotNone(a._active_sub)
        a.stop()
        self.assertIsNone(a._active_sub)
        self.assertEqual(b.current_index, -1)

    def test_no_sub_returns_none_when_idle(self):
        a = _stack("A", {1: {"dimmer": 100}})
        self._wire(a)
        self.assertIsNone(a.tick())               # kein Fade, keine Sub -> None

    def test_roundtrip_sub_fields(self):
        c = Cue(1.0, sub_stack_ref=3, sub_stack_mode="merge", values={1: {"x": 1}})
        c2 = Cue.from_dict(c.to_dict())
        self.assertEqual(c2.sub_stack_ref, 3)
        self.assertEqual(c2.sub_stack_mode, "merge")
        c3 = Cue.from_dict({"number": 1.0})
        self.assertIsNone(c3.sub_stack_ref)
        self.assertEqual(c3.sub_stack_mode, "merge")

    def test_from_dict_coerces_bad_sub_fields(self):
        # Hand-editierte Show: "2" statt 2, unbekannter Modus.
        c = Cue.from_dict({"number": 1.0, "sub_stack_ref": "2",
                           "sub_stack_mode": "quatsch"})
        self.assertEqual(c.sub_stack_ref, 2)
        self.assertEqual(c.sub_stack_mode, "merge")


class AttrDelayViaFadeToTest(unittest.TestCase):
    """F-6 über den echten CueStack._fade_to-Pfad (nicht nur FadeState direkt)."""

    def test_fade_to_passes_attr_delays(self):
        s = CueStack("S")
        s.add_cue(Cue(1.0, values={1: {"a": 100, "b": 100}},
                      fade_in=1.0, attr_delays={1: {"b": 1.0}}))
        s.go()
        self.assertIsNotNone(s._fade)
        s._fade.start_time = time.monotonic() - 0.5     # 0.5 s in den 1-s-Fade
        vals = s._fade.current_values()
        self.assertAlmostEqual(vals[1]["a"], 50, delta=6)  # a fadet (scurve@0.5≈0.5)
        self.assertEqual(vals[1]["b"], 0)                  # b noch verzögert


class ResolverInjectionTest(unittest.TestCase):
    """F-16: AppState injiziert den Sub-Cuelisten-Resolver bei new_cue_stack."""

    def test_new_cue_stack_has_working_resolver(self):
        try:
            from src.core.app_state import get_state
            st = get_state()
        except Exception as e:                              # pragma: no cover
            self.skipTest(f"AppState nicht verfügbar: {e}")
        a = st.new_cue_stack("subtest_A")
        b = st.new_cue_stack("subtest_B")
        try:
            self.assertIsNotNone(a._resolve_sub)
            idx_b = st.cue_stacks.index(b)
            self.assertIs(a._resolve_sub(idx_b), b)
            self.assertIsNone(a._resolve_sub(9999))         # ungültiger Index
        finally:
            st.remove_cue_stack(a)
            st.remove_cue_stack(b)


if __name__ == "__main__":
    unittest.main()
