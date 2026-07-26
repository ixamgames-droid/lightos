"""CDX-23 (A3D-17b-Folge): `turn_off()` serialisiert nicht mit in-flight AUTO-Writes.

Die Modus-Guards der AUTO-Writer (`request_bpm`, `_apply_detected_bpm`) lasen
`_mode` UNGELOCKT, und `set_bpm` prüfte den Modus gar nicht. Ein AUTO-Thread
(Audio/OS2L/Timeline), der den Guard PASSIERT hatte, bevor `turn_off()`
`_mode=MANUAL` flippte, schrieb danach trotzdem sein positives `_bpm` — der von
A3D-17b bekämpfte „BPM springt zurück"-Effekt kehrte zurück.

Fix: `set_bpm(..., only_if_auto=True)` = Compare-and-Set — der Modus-Re-Check
läuft unter DEMSELBEN Lock-Hold wie der Write.

Die Rennen werden hier DETERMINISTISCH injiziert (Flip genau im Fenster zwischen
Guard und Write), plus ein echter Thread-Stresslauf als Zusatz-Netz.
"""
import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.bpm_manager import get_bpm_manager, BpmMode


class TestCdx23TurnOffRace(unittest.TestCase):
    def setUp(self):
        self.mgr = get_bpm_manager()
        self.mgr.reset()
        self.mgr.set_mode(BpmMode.AUTO)
        self.mgr.set_locked(False)

    def tearDown(self):
        self.mgr._audio_active = False
        self.mgr.reset()
        self.mgr.set_mode(BpmMode.AUTO)
        self.mgr.set_locked(False)

    # ── Der eigentliche CDX-23-Fund ─────────────────────────────────────────

    def test_inflight_audio_write_loses_against_turn_off(self):
        """Audio-Beat passiert den AUTO-Guard, DANN läuft turn_off() komplett
        durch, DANN schreibt der Beat — der Write muss verworfen werden.

        Injektion: `_clamp_bounds` liegt in `_apply_detected_bpm` GENAU zwischen
        Guard (`_mode != AUTO`) und `set_bpm` — der realistischste Aufhänger für
        das Fenster, ohne Thread-Timing.
        """
        m = self.mgr
        m.request_bpm(128, "os2l")
        self.assertEqual(m.bpm, 128)

        orig_clamp = m._clamp_bounds

        def _clamp_with_turn_off(bpm):
            m.turn_off()          # User drückt „0/aus", während der Beat in-flight ist
            return orig_clamp(bpm)

        m._clamp_bounds = _clamp_with_turn_off
        try:
            m._apply_detected_bpm(150)
        finally:
            del m._clamp_bounds

        self.assertEqual(m.mode, BpmMode.MANUAL)
        self.assertEqual(m.bpm, 0,
                         "in-flight Audio-Write überholte turn_off — BPM springt zurück (CDX-23)")
        self.assertEqual(m.current_source, "off")

    def test_inflight_os2l_write_loses_against_mode_flip(self):
        """Gleiches Fenster in `request_bpm`: Guard passiert, dann flippt der
        Leader nach MANUAL, dann erst kommt der Write an."""
        m = self.mgr
        orig_set = m.set_bpm

        def _flip_then_set(*a, **kw):
            with m._lock:                       # turn_off flippt hier (unter Lock)
                m._mode = BpmMode.MANUAL
            return orig_set(*a, **kw)

        m.set_bpm = _flip_then_set
        try:
            m.request_bpm(140, "os2l")
        finally:
            del m.set_bpm

        self.assertEqual(m.bpm, 0,
                         "in-flight OS2L-Write landete trotz MANUAL (CDX-23)")
        self.assertEqual(m.current_source, "off")

    def test_rejected_write_emits_no_state_change(self):
        """Ein verworfener Write darf auch keinen State-Emit auslösen — sonst
        zieht die UI (Modus-Badge/Audio-Checkbox) einen Zustand nach, den es nie
        gab."""
        m = self.mgr
        m.turn_off()                       # -> MANUAL
        seen = []

        def _on_state():
            seen.append(1)

        m.subscribe_state_change(_on_state)
        try:
            m.request_bpm(140, "os2l")     # blockt schon am äusseren Guard
            self.assertEqual(m.bpm, 0)
            self.assertEqual(seen, [], "verworfener AUTO-Write emittierte State-Change")
        finally:
            m.unsubscribe_state_change(_on_state)

    def test_locked_leader_blocks_inflight_write(self):
        """Dieselbe Sequenz mit `set_locked(True)` statt turn_off: der Lock ist
        der zweite Grund, aus dem ein AUTO-Write sterben muss."""
        m = self.mgr
        orig_clamp = m._clamp_bounds

        def _clamp_with_lock(bpm):
            m.set_locked(True)
            return orig_clamp(bpm)

        m._clamp_bounds = _clamp_with_lock
        try:
            m._apply_detected_bpm(150)
        finally:
            del m._clamp_bounds

        self.assertEqual(m.bpm, 0, "in-flight Write überholte set_locked(True)")

    # ── Nicht-Regression: der Compare-and-Set darf den Normalbetrieb nicht bremsen ──

    def test_auto_sources_still_write_in_auto(self):
        m = self.mgr
        m.request_bpm(120, "os2l")
        self.assertEqual(m.bpm, 120)
        self.assertEqual(m.current_source, "os2l")
        m._apply_detected_bpm(132)
        self.assertEqual(m.bpm, 132)
        self.assertEqual(m.current_source, "audio")
        # reset() lässt AUTO stehen -> Live-Quellen dürfen weiter setzen (A3D-17b)
        m.reset()
        m.request_bpm(126, "os2l")
        self.assertEqual(m.bpm, 126)

    def test_manual_paths_unaffected_by_compare_and_set(self):
        """`only_if_auto` ist opt-in: manuelle/restaurierende Writer (Tap, Nudge,
        Top-Bar-Eingabe, Freeze-Auftauen via `set_bpm(x, source=…)`) setzen im
        MANUAL-Modus weiter durch."""
        m = self.mgr
        m.set_manual_bpm(123)
        self.assertEqual(m.mode, BpmMode.MANUAL)
        self.assertEqual(m.bpm, 123)
        # Freeze-Restore-Pfad (tempo_bus.toggle_freeze) — ohne only_if_auto
        m.set_bpm(0.0)
        self.assertEqual(m.bpm, 0)
        self.assertTrue(m.set_bpm(137, source="manual"))
        self.assertEqual(m.bpm, 137)
        self.assertEqual(m.current_source, "manual")

    def test_set_bpm_return_value_contract(self):
        m = self.mgr
        self.assertTrue(m.set_bpm(120, source="audio", only_if_auto=True))
        m.turn_off()
        self.assertFalse(m.set_bpm(120, source="audio", only_if_auto=True),
                         "Compare-and-Set meldete Erfolg trotz MANUAL")
        self.assertEqual(m.bpm, 0)

    # ── Echter Thread-Stresslauf (Zusatz-Netz zum deterministischen Teil) ────

    def test_concurrent_auto_writers_never_survive_turn_off(self):
        m = self.mgr
        stop = threading.Event()
        started = threading.Event()
        # Beat-/Tick-Emits stummschalten: der Timer-Thread-Lebenszyklus bleibt echt
        # (Phantom-Timer-Abdeckung aus A3D-17b), aber die Beat-Callbacks ziehen im
        # Stresslauf nicht FunctionManager/AppState/Cuelisten hinter sich her.
        m._emit_beat = lambda: None
        m._emit_tick = lambda is_beat: None   # Signatur muss zu _emit_tick passen
        # Singleton: die Stubs MUESSEN weg, egal wie der Test endet.
        self.addCleanup(m.__dict__.pop, "_emit_beat", None)
        self.addCleanup(m.__dict__.pop, "_emit_tick", None)

        def _writer():
            started.set()
            while not stop.is_set():
                m._apply_detected_bpm(150)
                m.request_bpm(145, "os2l")

        threads = [threading.Thread(target=_writer, daemon=True) for _ in range(3)]
        for t in threads:
            t.start()
        started.wait(2.0)
        try:
            for _ in range(50):
                m.turn_off()
                self.assertEqual(m.mode, BpmMode.MANUAL)
                self.assertEqual(
                    m.bpm, 0,
                    "AUTO-Writer setzte _bpm nach turn_off wieder (CDX-23-Race offen)")
                m.set_mode(BpmMode.AUTO)   # wieder scharf schalten für die nächste Runde
        finally:
            stop.set()
            for t in threads:
                t.join(timeout=2.0)
        m.turn_off()
        self.assertEqual(m.bpm, 0)
        # Kein Phantom-Timer: nach dem letzten turn_off darf kein Beat-Thread
        # weiterlaufen (ein durchgerutschter Write hätte einen neu gestartet).
        self.assertFalse(m._running, "Timer lief nach turn_off weiter (Phantom-Timer)")


if __name__ == "__main__":
    unittest.main()
