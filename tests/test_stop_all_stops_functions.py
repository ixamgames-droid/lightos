"""STOP-ALL-PANIK: STOP ALL stoppt jetzt auch FunctionManager-Funktionen.

Regression (live gefunden): `ButtonAction.STOP_ALL` (+ Toolbar-„STOP ALL" +
cmdline `stop`) riefen frueher NUR `playback_engine.stop_all()` (Executor-
Cuestacks) → VC-getoggelte Szenen/EFX/Programmer-Matrizen, die in
`FunctionManager._running_ids` leben, liefen WEITER (Banner „Aktiver Effekt" +
DMX blieben, bis die Show neu geladen wurde). Der Panik-Knopf war also keiner.

Fix: STOP ALL ist jetzt das Superset — Cuestacks UND FunctionManager-Funktionen
(derselbe `function_manager.stop_all()`-Call, den STOP_EFFECTS schon nutzt). Der
Programmer bleibt bewusst unberuehrt (das ist CLEARs Aufgabe).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.core.cmdline.parser import StopCommand

_app = QApplication.instance() or QApplication([])


class StopAllStopsFunctionsTest(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self.fm = self.state.function_manager
        self.fm.stop_all()
        # eine FunctionManager-Funktion (wie eine VC-getoggelte Szene/Matrix)
        self.m = RgbMatrixInstance(name="PanicMx", cols=2, rows=1,
                                   algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2])
        self.fm.add(self.m)
        self.fid = self.m.id

    def tearDown(self):
        self.fm.stop_all()
        try:
            self.fm.remove(self.m.id)
        except Exception:
            pass

    def _assert_stopped(self):
        self.assertFalse(self.fm.is_running(self.fid),
                         "STOP ALL muss die laufende FunctionManager-Funktion stoppen")
        self.assertEqual(list(self.fm.running_ids()), [],
                         "keine FunctionManager-Funktion darf nach STOP ALL laufen")

    def test_vc_stop_all_button_stops_running_function(self):
        self.fm.start(self.fid)
        self.assertTrue(self.fm.is_running(self.fid))          # Vorbedingung
        b = VCButton()
        b.action = ButtonAction.STOP_ALL
        b._trigger(True)
        self._assert_stopped()

    def test_vc_stop_all_multi_action_keeps_functions_running(self):
        # BEWUSSTE Unterscheidung (Review-Fund): der komponierbare Multi-Action-
        # Baustein „stop_all" (Label „Alle Executors stoppen") ist NICHT das Panik-
        # Superset — er stoppt nur Executor-Cuestacks und laesst per Button gestartete
        # Funktionen laufen (Master-Look-Komposition: Szene starten + Cuelists leeren).
        # Nur der STOP_ALL-*Button* + cmdline sind das Superset.
        self.fm.start(self.fid)
        b = VCButton()
        b.action = ButtonAction.TOGGLE        # Primaer no-op (function_id None)
        b.function_id = None
        b.actions = [{"type": "stop_all"}]
        b._trigger(True)
        self.assertTrue(self.fm.is_running(self.fid),
                        "Multi-Action 'stop_all' (Executor-only) darf Funktionen NICHT stoppen")

    def test_cmdline_stop_all_stops_function(self):
        self.fm.start(self.fid)
        res = StopCommand(slot=None).execute(self.state)
        self.assertTrue(res.ok)
        self._assert_stopped()

    def test_stop_effects_unchanged_still_stops_function(self):
        # Gegenprobe: STOP_EFFECTS stoppt weiterhin die Funktion (unveraendert).
        self.fm.start(self.fid)
        b = VCButton()
        b.action = ButtonAction.STOP_EFFECTS
        b._trigger(True)
        self._assert_stopped()


if __name__ == "__main__":
    unittest.main()
