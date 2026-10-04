"""OUT-61 — Laser-NOT-AUS gilt auch im Lade-Fenster (Review A zu #925).

Befund: der reset-first eines Live-Show-Loads schiebt bei aktivem NOT-AUS-Latch
eine LEERE ``_laser_estop_mask`` (leerer Patch). Ebene 2 des NOT-AUS (die Maske
in ``_send_all``) faellt damit im Lade-Fenster weg; uebrig bleibt nur die 0 im
eingefrorenen Frame (Ebene 1). Liegt auf der Laser-Adresse ein INVERSE- oder
Range-Lock-Modifier, wird aus dieser 0 eine 255 — der Laser ginge waehrend des
Ladens AN.

Fix: die Lade-Sperre haelt auch die Estop-Maske vom Start fest; ``_send_all``
nullt die VEREINIGUNG aus Start- und Live-Maske (ein waehrend des Ladens neu
ausgeloester NOT-AUS wirkt also sofort).
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import get_state                                  # noqa: E402
from src.core.engine.channel_modifier import (ChannelModifier, CurveType,  # noqa: E402
                                              get_modifier_manager)

LASER = 40


class EstopImLadeFensterTest(unittest.TestCase):

    def setUp(self):
        self.om = get_state().output_manager
        self.u = self.om.universes[1]
        self.mods = get_modifier_manager()
        self._alt_mask = self.om._laser_estop_mask
        self.u.set_channel(LASER, 0)                 # Ebene 1: Renderer nullt
        self.mods.add(ChannelModifier(universe=1, address=LASER, curve=CurveType.INVERSE))
        self.addCleanup(self.mods.remove, 1, LASER)
        self.om._laser_estop_mask = {1: frozenset({LASER})}

    def tearDown(self):
        self.om._laser_estop_mask = self._alt_mask

    def test_vorbedingung_inverse_macht_aus_0_255(self):
        self.om._laser_estop_mask = {}
        self.om._send_all()
        self.assertEqual(self.om._display_frame[1][LASER - 1], 255,
                         "Testaufbau: ohne Maske muesste INVERSE 255 liefern")

    def test_estop_haelt_im_lade_fenster(self):
        with self.om.lade_sperre():
            self.om._laser_estop_mask = {}           # reset-first: leerer Patch
            self.om._send_all()
            self.assertEqual(self.om._display_frame[1][LASER - 1], 0,
                             "Laser im Lade-Fenster AN (NOT-AUS-Maske verloren)")

    def test_neuer_estop_waehrend_des_ladens_wirkt_sofort(self):
        self.om._laser_estop_mask = {}
        with self.om.lade_sperre():
            self.om._laser_estop_mask = {1: frozenset({LASER})}
            self.om._send_all()
            self.assertEqual(self.om._display_frame[1][LASER - 1], 0,
                             "waehrend des Ladens ausgeloester NOT-AUS wirkt nicht")

    def test_nach_dem_laden_gilt_wieder_nur_die_live_maske(self):
        with self.om.lade_sperre():
            self.om._laser_estop_mask = {}
        self.om._send_all()
        self.assertEqual(self.om._display_frame[1][LASER - 1], 255)


if __name__ == "__main__":
    unittest.main()
