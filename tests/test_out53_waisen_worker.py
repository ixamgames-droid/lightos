"""OUT-53: der Ausgabe-Worker beendet sich, wenn sein Elternprozess weg ist.

WARUM (am 26.08.2026 real passiert, eine Stunde Fehlersuche gekostet)
--------------------------------------------------------------------
LightOS lagert die serielle Ausgabe bewusst in einen eigenen Prozess aus, damit
eine native Access Violation im FTDI-Treiber nicht die ganze App mitreisst.
Stirbt der Parent aber HART (Kill, Absturz, abgewuergtes Skript), setzt niemand
mehr ``stop_flag`` — und ``daemon=True`` greift nur beim sauberen Exit. Der
Worker sendet dann fuer immer weiter.

Gemessen: FUENF solcher Waisen hingen gleichzeitig an ``/dev/ttyUSB0``, jeder
mit ~15,6 kB/s. Bei 57600 Baud traegt die Leitung 5760 B/s — also 13,5-fach
ueberbucht. Am Geraet sah das aus wie ein Softwarefehler in der Show:

* **Blinken** — der Kopf bekommt abwechselnd Frames von fuenf Sendern, vier
  davon mit eingefrorenem Alt-Zustand.
* **Nichts steuerbar** — nur jeder fuenfte Frame trug die Werte der lebenden App.
* **Blackout funktionierte** — und genau diese Asymmetrie war der Hinweis:
  Dunkel ist der EINZIGE Zustand, ueber den sich alle Sender einig sind. Jedes
  "an" kaempft gegen vier "aus", jedes "aus" wird von allen bestaetigt.

Die Wache prueft die PID, nicht ``multiprocessing.parent_process()``: die
Waisen liefen unter ``PPID = 989 = systemd`` weiter, weil der Kernel sie beim
Tod des Parents an den Subreaper umgehaengt hatte.
"""
from __future__ import annotations

import unittest

from src.core.dmx.serial_process import _serial_worker_loop, ST_OK


class _Flag:
    def __init__(self, v=0):
        self.value = v


class _Puffer:
    def __init__(self):
        self._d = bytes(512)

    def __getitem__(self, k):
        return self._d[k]


class _Geraet:
    def __init__(self):
        self.frames = 0

    def send_dmx(self, data):
        self.frames += 1

    def is_disabled(self):
        return False

    def close(self):
        pass


def _lauf(parent_alive, max_runden=50):
    """Schleife mit gestelltem Takt laufen lassen; zaehlt gesendete Frames."""
    dev = _Geraet()
    stop = _Flag(0)
    runden = {"n": 0}

    def _clock():
        runden["n"] += 1
        if runden["n"] > max_runden * 4:      # Notbremse gegen Endlosschleife
            stop.value = 1
        return runden["n"] * 0.001

    _serial_worker_loop(lambda: dev, _Puffer(), stop, _Flag(ST_OK),
                        frame_interval=0.0, sleep=lambda s: None, clock=_clock,
                        parent_alive=parent_alive)
    return dev.frames


class WaisenWacheTest(unittest.TestCase):
    def test_lebender_parent_laesst_senden(self):
        """Gegenprobe: die Wache darf den Normalbetrieb nicht abwuergen."""
        gesendet = {"n": 0}

        def lebt():
            gesendet["n"] += 1
            return gesendet["n"] < 20      # nach 20 Runden "Parent tot"

        frames = _lauf(lebt)
        self.assertGreater(frames, 10, "der Worker hat gar nicht gesendet")

    def test_toter_parent_beendet_die_schleife(self):
        """★ Der Kern: ohne diese Wache sendet der Worker fuer immer weiter und
        haelt den seriellen Port."""
        frames = _lauf(lambda: False)
        self.assertEqual(frames, 0,
                         "der Worker hat trotz totem Elternprozess gesendet — "
                         "genau so entsteht ein Waisenkind auf dem Port")

    def test_ohne_wache_unveraendert(self):
        """Bestandsverhalten: ``parent_alive=None`` (Default) darf die Schleife
        NICHT beenden — Tests und Fremdaufrufer verlassen sich darauf."""
        frames = _lauf(None, max_runden=10)
        self.assertGreater(frames, 5)

    def test_wache_wird_in_jeder_runde_geprueft(self):
        """Einmal am Anfang zu pruefen genuegt nicht: der Parent stirbt
        typischerweise MITTEN im Betrieb (Kill, Absturz)."""
        zaehler = {"n": 0}

        def lebt():
            zaehler["n"] += 1
            return zaehler["n"] < 5

        frames = _lauf(lebt)
        self.assertGreaterEqual(zaehler["n"], 5, "Wache nur einmal geprueft")
        self.assertLess(frames, 10, "Schleife lief nach dem Tod weiter")


class WorkerEinstiegTest(unittest.TestCase):
    def test_worker_main_haengt_die_wache_ein(self):
        """Der Fix muss im ECHTEN Einstieg verdrahtet sein, nicht nur in der
        Schleife — sonst laeuft der Produktivpfad weiter ohne Wache."""
        import inspect
        from src.core.dmx import serial_process
        quelle = inspect.getsource(serial_process._worker_main)
        self.assertIn("parent_alive", quelle)
        self.assertIn("getppid", quelle,
                      "PID-Vergleich fehlt — parent_process().is_alive() faengt "
                      "den gemessenen systemd-Subreaper-Fall NICHT")


if __name__ == "__main__":
    unittest.main()
