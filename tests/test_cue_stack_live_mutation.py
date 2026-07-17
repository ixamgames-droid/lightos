"""CueStack-Robustheit unter Live-Mutation + Wert-Isolation (Bug-Hunt 2026-07-12).

Vier bestaetigte Defekte im Playback-Timing-Engine:
- F1: die Sub-Cuelisten-Mischung in tick() mutierte via geteilter dict-Referenz die
  gespeicherten Werte der Eltern-Cue (FadeState.current_values lieferte to_vals=cue.values
  by-ref) -> stille, in die .lshow geschriebene Show-Korruption.
- F2/F3: remove_cue() liess _current_idx unangetastet -> IndexError in back()/go(bounce).
- F4: manual_crossfade() committete gegen ein stale _manual_target -> IndexError.
- F6: add_cue() sortierte neu, ohne _current_idx der aktiven Cue nachzufuehren ->
  falsche Playback-Position (Replay/Skip) nach Live-Insert.

Jeder Test bildet das exakte Hunt-Szenario ab und faellt auf dem alten Code durch.
"""
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.cue import Cue
from src.core.engine.cue_stack import CueStack


def _cue(n, values=None, fade_in=0.0, **kw):
    return Cue(number=float(n), fade_in=fade_in, fade_out=0.0, values=values or {}, **kw)


class SubCueValueIsolationTest(unittest.TestCase):
    """F1: eine mitlaufende Sub-Cueliste darf die Eltern-Cue-Werte NIE mutieren."""

    def test_sub_merge_does_not_corrupt_parent_cue_values(self):
        parent = CueStack("parent")
        parent.add_cue(_cue(1, values={1: {"intensity": 100}}, sub_stack_ref=0))
        sub = CueStack("sub")
        sub.add_cue(_cue(1, values={1: {"color_r": 222}}))
        parent.set_sub_stack_resolver(lambda ref: sub if ref == 0 else None)

        parent.go()
        # Fade abschliessen lassen und den Merge mehrfach durchlaufen.
        for _ in range(12):
            time.sleep(0.004)
            parent.tick()

        parent_cue = parent.cues[0]
        # Die persistente Cue behaelt EXAKT ihren gespeicherten Wert.
        self.assertEqual(parent_cue.values, {1: {"intensity": 100}})
        # Der sichtbare Output mischt die Sub trotzdem drauf (LTP).
        out = parent.get_output()
        self.assertEqual(out.get(1, {}).get("intensity"), 100)
        self.assertEqual(out.get(1, {}).get("color_r"), 222)


class StaleIndexAfterRemoveTest(unittest.TestCase):
    """F2/F3: remove_cue darf go()/back() nicht mit einem stale Index crashen lassen."""

    def _stack(self, mode="single", n=5):
        s = CueStack("s")
        s.mode = mode
        for i in range(1, n + 1):
            s.add_cue(_cue(i, values={i: {"intensity": i * 10}}))
        return s

    def test_back_after_removing_leading_cues(self):
        s = self._stack("single", 5)
        for _ in range(5):
            s.go()                              # -> aktiv: Cue 5.0
        self.assertEqual(s.current_cue.number, 5.0)
        s.remove_cue(1.0)
        s.remove_cue(2.0)                       # cues = [3,4,5], aktiv bleibt 5.0
        self.assertEqual(s.current_cue.number, 5.0)
        s.back()                                # darf NICHT crashen
        self.assertEqual(s.current_cue.number, 4.0)

    def test_bounce_go_after_removing_trailing_cues(self):
        s = self._stack("bounce", 5)
        for _ in range(5):
            s.go()                              # bis ans Ende (Cue 5.0)
        self.assertEqual(s.current_cue.number, 5.0)
        s.remove_cue(5.0)
        s.remove_cue(4.0)
        s.remove_cue(3.0)                       # cues = [1,2]
        s.go()                                  # bounce-Umkehr, darf NICHT crashen
        self.assertIsNotNone(s.current_cue)
        self.assertIn(s.current_cue.number, (1.0, 2.0))


class ManualCrossfadeStaleTargetTest(unittest.TestCase):
    """F4: Ziel-Cue waehrend des manuellen Scrubs entfernt -> sauberer Abbruch."""

    def test_commit_after_target_removed_does_not_crash(self):
        s = CueStack("s")
        s.add_cue(_cue(1, values={1: {"intensity": 50}}))
        s.add_cue(_cue(2, values={1: {"intensity": 200}}))
        s.go()
        s.tick()
        armed = s.manual_crossfade(0.5)         # armiert _manual_target = Cue 2
        self.assertFalse(armed)                 # <1.0 -> noch kein Commit
        s.remove_cue(2.0)                       # Ziel-Cue entfernt
        committed = s.manual_crossfade(1.0)     # darf NICHT crashen
        self.assertFalse(committed)             # Abbruch statt falscher Commit
        self.assertEqual(s.current_cue.number, 1.0)


class AddCueReindexTest(unittest.TestCase):
    """F6: Live-Insert vor der aktiven Cue verschiebt _current_idx korrekt mit."""

    def test_insert_before_active_keeps_playback_position(self):
        s = CueStack("s")
        for i in (1, 2, 3):
            s.add_cue(_cue(i, values={i: {"intensity": i * 10}}))
        s.go()
        s.go()                                  # aktiv: Cue 2.0
        self.assertEqual(s.current_cue.number, 2.0)
        s.add_cue(_cue(0.5, values={9: {"intensity": 5}}))   # vor die aktive Cue
        self.assertEqual(s.current_cue.number, 2.0)          # aktiv bleibt Cue 2.0
        s.go()                                  # muss zu Cue 3.0 vorruecken (kein Replay von 2.0)
        self.assertEqual(s.current_cue.number, 3.0)


class ManualCrossfadeTargetIdentityTest(unittest.TestCase):
    """A3D-16: ein Live-Insert/-Remove waehrend des Scrubs verschiebt den Ziel-Index
    (er bleibt in-bounds, zeigt aber auf eine ANDERE Cue). Der Commit muss die beim
    Armieren gewaehlte Ziel-Cue per IDENTITAET treffen, nicht den verschobenen Index
    blind uebernehmen. (F4 oben deckt nur das ENTFERNEN des Ziels ab; hier bleibt das
    Ziel erhalten und darf trotz Verschiebung nicht zur falschen Cue committen.)"""

    def test_insert_before_target_commits_original_target(self):
        s = CueStack("s")
        s.add_cue(_cue(1, values={1: {"intensity": 10}}))
        s.add_cue(_cue(2, values={1: {"intensity": 20}}))
        s.add_cue(_cue(3, values={1: {"intensity": 30}}))
        s.go()                                   # aktiv: Cue 1.0 (idx 0)
        s.tick()
        self.assertFalse(s.manual_crossfade(0.5))            # armiert Ziel = Cue 2.0 (idx 1)
        s.add_cue(_cue(0.5, values={9: {"intensity": 5}}))   # sortiert davor -> Cue 2.0 rutscht auf idx 2
        self.assertTrue(s.manual_crossfade(1.0))             # Commit
        # ORIGINAL-Ziel Cue 2.0, NICHT die auf idx 1 nachgerutschte Cue 1.0.
        self.assertEqual(s.current_cue.number, 2.0)
        self.assertEqual(s.get_output()[1]["intensity"], 20)

    def test_remove_before_target_commits_original_target(self):
        s = CueStack("s")
        for i in (1, 2, 3, 4):
            s.add_cue(_cue(i, values={1: {"intensity": i * 10}}))
        s.go(); s.go()                           # aktiv: Cue 2.0 (idx 1)
        s.tick()
        self.assertEqual(s.current_cue.number, 2.0)
        self.assertFalse(s.manual_crossfade(0.5))            # armiert Ziel = Cue 3.0 (idx 2)
        s.remove_cue(1.0)                        # Cue 3.0 rutscht auf idx 1 (bleibt in-bounds)
        self.assertTrue(s.manual_crossfade(1.0))             # Commit
        # ORIGINAL-Ziel Cue 3.0, NICHT die auf idx 2 verbliebene Cue 4.0.
        self.assertEqual(s.current_cue.number, 3.0)
        self.assertEqual(s.get_output()[1]["intensity"], 30)

    def test_go_abandons_armed_manual_target(self):
        """Ein programmatischer GO waehrend eines armierten Scrubs verwirft den
        manuellen Ziel-Anker (Fader-Scrub hinfaellig) statt ihn stale zu halten."""
        s = CueStack("s")
        for i in (1, 2, 3):
            s.add_cue(_cue(i, values={1: {"intensity": i * 10}}))
        s.go()                                   # aktiv Cue 1.0
        s.tick()
        self.assertFalse(s.manual_crossfade(0.5))    # armiert Ziel Cue 2.0
        s.go()                                   # GO -> Cue 2.0, manueller Anker weg
        # Erneuter (Fader-auf-1)-Aufruf armiert frisch das NAECHSTE Ziel (Cue 3.0),
        # committet nicht versehentlich gegen ein stale Ziel.
        self.assertTrue(s.manual_crossfade(1.0))
        self.assertEqual(s.current_cue.number, 3.0)


if __name__ == "__main__":
    unittest.main()
