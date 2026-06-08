"""Tests fuer die Programmer-Merge/Priority-Logik (WP-6 / Abschnitt 8).

Der Programmer-LTP darf Nicht-Intensitaets-Kanaele, die der Funktions-Layer
(Matrix/EFX) gerade treibt, NICHT ueberschreiben — eine laufende Matrix-Farbe
bleibt erhalten. Intensitaet ist davon ausgenommen (sie wird ueber
skip_intensity_for multipliziert, EE-02). Testet _apply_fixture_map isoliert
(ohne den schweren AppState-Init / DB / Threads).
"""
import unittest

from src.core.app_state import AppState
from src.core.dmx.universe import Universe


class _Ch:
    def __init__(self, number, attribute):
        self.channel_number = number
        self.attribute = attribute


class _Fx:
    def __init__(self, universe, address):
        self.universe = universe
        self.address = address


def _carrier(fix_index):
    # AppState ohne __init__ (kein OutputManager/MIDI/DB/Thread) — _apply_fixture_map
    # nutzt nur self._fix_index.
    c = AppState.__new__(AppState)
    c._fix_index = fix_index
    return c


def _setup():
    # Fixture 1 @ Universe 1, Adresse 1: ch1=intensity, ch2=R, ch3=G, ch4=B
    chans = [_Ch(1, "intensity"), _Ch(2, "color_r"), _Ch(3, "color_g"), _Ch(4, "color_b")]
    fx = _Fx(1, 1)
    return _carrier({1: (fx, chans)})


class ProgrammerPriorityTest(unittest.TestCase):

    def test_programmer_protects_function_driven_color(self):
        c = _setup()
        u = Universe(1)
        u.set_channel(2, 200)               # Funktion (Matrix) treibt R auf 200
        func_driven = {1: {2}}              # Adresse 2 (R) ist funktionsgetrieben
        prog = {1: {"color_r": 50, "color_g": 80, "intensity": 255}}
        AppState._apply_fixture_map(c, {1: u}, prog, skip_intensity_for=set(),
                                    protect_addrs=func_driven)
        self.assertEqual(u.get_channel(2), 200, "Matrix-R darf nicht ueberschrieben werden")
        self.assertEqual(u.get_channel(3), 80, "G (nicht funktionsgetrieben) wird gesetzt")
        self.assertEqual(u.get_channel(1), 255, "Intensity ist von protect ausgenommen")

    def test_without_protect_programmer_overwrites(self):
        c = _setup()
        u = Universe(1)
        u.set_channel(2, 200)
        prog = {1: {"color_r": 50}}
        # Ohne protect_addrs -> normaler LTP: Programmer gewinnt (bisheriges Verhalten).
        AppState._apply_fixture_map(c, {1: u}, prog)
        self.assertEqual(u.get_channel(2), 50)

    def test_no_function_running_normal_ltp(self):
        c = _setup()
        u = Universe(1)
        prog = {1: {"color_r": 123}}
        AppState._apply_fixture_map(c, {1: u}, prog, skip_intensity_for=set(),
                                    protect_addrs={})   # nichts funktionsgetrieben
        self.assertEqual(u.get_channel(2), 123, "ohne laufende Funktion wirkt der Programmer normal")


if __name__ == "__main__":
    unittest.main()
