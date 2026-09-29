"""ENG-18: STOP ALL beendet Audio sofort — auch mit Fade-Out, auch beim zweiten Mal.

Gemessen im Stabilitaets-Durchlauf 2026-08-31: nach ``stop_all()`` war
``running_ids`` leer, ``player.stop()`` wurde 0-mal gerufen, die Fade-Art
„out" lief die volle Ausblendzeit (bei 8 s acht Sekunden Musik bei stehendem
Licht). Ein zweites STOP ALL half nicht — die Funktion galt schon als gestoppt.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                          # noqa: E402

from src.core.engine.audio_func import AudioFunction                # noqa: E402
from src.core.engine.function_manager import FunctionManager        # noqa: E402

_app = QApplication.instance() or QApplication([])


class _Player:
    def __init__(self):
        self.stops = 0

    def stop(self):
        self.stops += 1


class _Out:
    def __init__(self, vol):
        self.vol = vol

    def volume(self):
        return self.vol

    def setVolume(self, v):
        self.vol = v


class StopAllAudioTest(unittest.TestCase):

    def setUp(self):
        self.fm = FunctionManager()
        self.af = AudioFunction("Musik")
        self.af.fade_out = 8.0
        self.af._available = True
        self.af._player = _Player()
        self.af._audio_out = _Out(0.8)
        self.fm.add(self.af)
        # „laeuft" — ohne echte Datei/Wiedergabe
        self.af._running = True
        self.fm._running_ids.add(self.af.id)
        self.addCleanup(self.af._cancel_fade)

    def test_normaler_stopp_blendet_weiter_aus(self):
        """Positivkontrolle: ein einzelnes Stoppen darf ausblenden."""
        self.fm.stop(self.af.id)
        self.assertEqual(self.af._fade_kind, "out")
        self.assertEqual(self.af._player.stops, 0)

    def test_stop_all_ist_sofort_still(self):
        self.fm.stop_all()
        self.assertEqual(list(self.fm.running_ids()), [])
        self.assertGreaterEqual(self.af._player.stops, 1, "Ton hart beendet")
        self.assertIsNone(self.af._fade_timer)
        self.assertEqual(self.af._fade_kind, "")

    def test_stop_all_faengt_einen_laufenden_fade_out(self):
        self.fm.stop(self.af.id)                       # blendet aus, gilt als gestoppt
        self.assertNotIn(self.af.id, list(self.fm.running_ids()))
        self.fm.stop_all()                             # zweiter Griff zur Panik-Taste
        self.assertGreaterEqual(self.af._player.stops, 1)
        self.assertIsNone(self.af._fade_timer)

    def test_ohne_player_kein_fehler(self):
        leer = AudioFunction("Leer")
        self.fm.add(leer)
        self.fm.stop_all()                             # darf nicht werfen


if __name__ == "__main__":
    unittest.main()
