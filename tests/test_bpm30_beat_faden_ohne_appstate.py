"""BPM-30: der Beat-Takt legt den App-Zustand nie selbst an.

Gemessen 2026-10-08 (Sitzung D, Gate zu BPM-28, ``test_bpm_view_state_table``):
Access Violation im Faden 'BPM-Beat' — ``_loop`` -> ``_emit_beat`` ->
``get_state()`` -> ``open_show`` -> ``create_engine``. ``get_state()`` baute den
kompletten AppState im Beat-Faden (Datenumzug, Show-DB, Ausgabe-Thread); ein
zweiter Beat-Faden hing im selben ``get_state()``, denn das Anlegen war nicht
gesperrt. Die Speicherbereinigung lief im Faden, waehrend der Hauptthread
Qt-Fenster abbaute.

Jetzt: ``_emit_beat`` nimmt nur ``app_state.vorhandener_state()`` (legt nie an),
und ``get_state()`` legt auch bei gleichzeitigen Erstaufrufen genau EINEN an.
"""
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core import app_state as A                       # noqa: E402
from src.core.engine.bpm_manager import BPMManager        # noqa: E402


class _AppStateAttrappe:
    """Statt des echten AppState: zaehlt, wie oft angelegt wird. Der Aufbau
    dauert etwas, damit gleichzeitige Faeden sich sicher ueberlappen."""
    angelegt = 0

    def __init__(self):
        type(self).angelegt += 1
        time.sleep(0.2)
        self.cue_stacks = []
        self.output_manager = mock.Mock()

    def open_show(self):
        pass

    def apply_output_config(self):
        pass

    def start_playback(self):
        pass


class _Liste:
    def __init__(self, beat_sync: bool):
        self.beat_sync = beat_sync
        self.beats = 0

    def on_beat(self):
        self.beats += 1


class BeatFadenOhneAppState(unittest.TestCase):

    def setUp(self):
        alt = A._state
        A._state = None
        self.addCleanup(setattr, A, "_state", alt)
        _AppStateAttrappe.angelegt = 0
        for p in (mock.patch.object(A, "AppState", _AppStateAttrappe),
                  mock.patch("src.core.datenumzug.einmal_je_prozess", lambda: None)):
            p.start()
            self.addCleanup(p.stop)

    def test_beat_legt_keinen_app_zustand_an(self):
        BPMManager()._emit_beat()
        self.assertEqual(_AppStateAttrappe.angelegt, 0)
        self.assertIsNone(A._state)

    def test_beat_im_hintergrund_faden_legt_keinen_an(self):
        m = BPMManager()
        faden = threading.Thread(target=m._emit_beat, name="BPM-Beat")
        faden.start()
        faden.join(5)
        self.assertEqual(_AppStateAttrappe.angelegt, 0)
        self.assertIsNone(A._state)

    def test_vorhandener_zustand_schaltet_beat_sync_listen_weiter(self):
        sync, frei = _Liste(True), _Liste(False)
        A._state = mock.Mock(cue_stacks=[sync, frei])
        BPMManager()._emit_beat()
        self.assertEqual((sync.beats, frei.beats), (1, 0))

    def test_vorhandener_state_legt_nie_an(self):
        self.assertIsNone(A.vorhandener_state())
        self.assertEqual(_AppStateAttrappe.angelegt, 0)

    def test_get_state_legt_bei_gleichzeitigen_faeden_genau_einen_an(self):
        ergebnisse = []
        start = threading.Barrier(4)

        def holen():
            start.wait()
            ergebnisse.append(A.get_state())

        faeden = [threading.Thread(target=holen) for _ in range(4)]
        for f in faeden:
            f.start()
        for f in faeden:
            f.join(10)
        self.assertEqual(_AppStateAttrappe.angelegt, 1)
        self.assertEqual(len(ergebnisse), 4)
        self.assertEqual(len({id(e) for e in ergebnisse}), 1)


if __name__ == "__main__":
    unittest.main()
