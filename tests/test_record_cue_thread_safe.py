"""STAB-21: record_cue snapshottet den Programmer unter _prog_lock.

Ohne den Lock konnte ein paralleler MIDI-/OSC-/Web-RX-set_programmer_value ein neues
fid in self.programmer einfuegen, waehrend record_cue die dict-Comprehension iteriert
(das innere dict(attrs) ist ein GIL-Yield-Punkt) -> "dictionary changed size during
iteration", unabgefangen -> Record-Cue bricht ab. Fix: Snapshot unter _prog_lock (wie
_render_frame). Dieser Test hammert die (gelockte) Insert-Seite und prueft, dass
record_cue nie eine RuntimeError wirft und einen konsistenten Snapshot liefert.
"""
import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import AppState


class _Stack:
    def __init__(self):
        self.cues = []

    def add_cue(self, cue):
        self.cues.append(cue)


class RecordCueThreadSafeTest(unittest.TestCase):
    def _state(self):
        st = AppState.__new__(AppState)
        st.programmer = {}
        st._prog_lock = threading.RLock()
        st._emit = lambda *a, **k: None
        return st

    def test_record_cue_no_race_with_concurrent_programmer_growth(self):
        st = self._state()
        stack = _Stack()
        stop = threading.Event()
        errors = []

        def writer():
            # Churnendes Fenster: pro Runde ein neues fid rein, ein altes raus ->
            # len(programmer) oszilliert (Groesse aendert sich = Race-Ausloeser),
            # bleibt aber klein (schnelle Snapshots, kein O(n^2)-Wachstum).
            i = 1000
            while not stop.is_set():
                with st._prog_lock:
                    st.programmer[i] = {"intensity": i % 255}
                    if i > 1080:
                        st.programmer.pop(i - 80, None)
                i += 1

        t = threading.Thread(target=writer, daemon=True)
        t.start()
        try:
            for n in range(2500):
                try:
                    cue = st.record_cue(stack, float(n))
                except RuntimeError as e:      # der frueher auftretende Race-Fehler
                    errors.append(str(e))
                    break
                # jede Cue ist ein konsistenter Snapshot (innere dicts eigenstaendig)
                self.assertIsInstance(cue.values, dict)
        finally:
            stop.set()
            t.join(timeout=3)

        self.assertEqual(errors, [], f"record_cue-Race (ohne _prog_lock): {errors}")
        self.assertTrue(stack.cues, "keine Cue aufgenommen")


if __name__ == "__main__":
    unittest.main()
