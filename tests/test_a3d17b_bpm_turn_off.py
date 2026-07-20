"""A3D-17b: manuelles „0/aus" (BPM-Dialog → turn_off) überstimmt laufende
AUTO-Tempo-Quellen und flippt in MANUAL — der BPM-Wert springt nicht mehr zurück.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.bpm_manager import get_bpm_manager, BpmMode


class TestA3d17bTurnOff(unittest.TestCase):
    def setUp(self):
        self.mgr = get_bpm_manager()
        self.mgr.reset()
        self.mgr.set_mode(BpmMode.AUTO)

    def tearDown(self):
        self.mgr.reset()
        self.mgr.set_mode(BpmMode.AUTO)

    def test_turn_off_overrides_live_sources(self):
        m = self.mgr
        m.request_bpm(128, "os2l")
        self.assertEqual(m.bpm, 128)
        self.assertEqual(m.mode, BpmMode.AUTO)

        m._audio_active = True   # simuliert laufenden Audio-Sync
        m.turn_off()

        self.assertEqual(m.mode, BpmMode.MANUAL, "turn_off flippt nicht in MANUAL")
        self.assertEqual(m.bpm, 0)
        self.assertEqual(m.current_source, "off")
        self.assertFalse(m.audio_active, "turn_off liess den Audio-Sync an")

        # Die Live-Quellen sind jetzt überstimmt → BPM springt NICHT zurück.
        m.request_bpm(140, "os2l")
        self.assertEqual(m.bpm, 0, "os2l setzte _bpm wieder (MANUAL blockt request_bpm nicht)")
        m._apply_detected_bpm(140)
        self.assertEqual(m.bpm, 0, "Audio-Detektor setzte _bpm wieder (MANUAL blockt nicht)")

    def test_turn_off_blocks_inflight_audio_beat(self):
        # Race (Review-HIGH): eine VERSPÄTETE Audio-Beat-Invocation, die MITTEN in
        # turn_off durchläuft (unsubscribe ist ungelockt), darf _bpm NICHT wieder
        # setzen. Der Fix (MANUAL ZUERST) schliesst das Fenster. Injiziert wird der
        # in-flight-Beat, indem reset() während turn_off ein _apply_detected_bpm
        # feuert — läuft turn_off korrekt (MANUAL vor reset), ist der Modus dann
        # schon MANUAL und der Beat wird geblockt.
        m = self.mgr
        m.request_bpm(128, "os2l")
        orig_reset = m.reset

        def _reset_with_inflight_beat():
            orig_reset()
            m._apply_detected_bpm(150)   # verspäteter Audio-Beat mitten im turn_off

        m.reset = _reset_with_inflight_beat
        try:
            m.turn_off()
        finally:
            m.reset = orig_reset

        self.assertEqual(m.mode, BpmMode.MANUAL)
        self.assertEqual(m.bpm, 0,
                         "in-flight Audio-Beat setzte _bpm trotz turn_off wieder (Race offen)")

    def test_reset_leaves_mode_auto(self):
        # Regression: reset() bleibt der Low-Level-Clean-Slate, der den MODUS lässt
        # (Test-Setup erwartet danach AUTO). NUR turn_off() flippt MANUAL.
        m = self.mgr
        m.request_bpm(120, "os2l")
        m.reset()
        self.assertEqual(m.mode, BpmMode.AUTO, "reset() hat den Modus verändert (bricht Test-Setup)")
        self.assertEqual(m.bpm, 0)
        m.request_bpm(122, "os2l")
        self.assertEqual(m.bpm, 122, "nach reset() (AUTO) darf eine Live-Quelle wieder setzen")


if __name__ == "__main__":
    unittest.main()
