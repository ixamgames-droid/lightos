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


class EstopWaehrendDesLadensTest(unittest.TestCase):
    """OUT-61b (Codex-P1 auf #927, von A bestaetigt): der NOT-AUS ist beim
    Ladebeginn AUS und wird erst WAEHREND des Ladens ausgeloest — nach dem
    reset-first, wenn der Plan leer ist. Echter Pfad: echter Laser im Patch,
    Show gespeichert und live geladen, ``set_laser_estop(True)`` im reset-first,
    dann sendet der Sende-Thread. Nichts injiziert."""

    def setUp(self):
        import tempfile
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
        from src.core.database.models import FixtureProfile, PatchedFixture
        from src.core.show.show_file import reset_show, save_show
        ensure_builtins()
        reset_show()
        self.st = get_state()
        self.om = self.st.output_manager
        with Session(fdb_engine()) as s:
            prof = s.execute(select(FixtureProfile).where(
                FixtureProfile.short_name == "PARTYLASER")).scalars().first()
            self.assertIsNotNone(prof, "Laser-Profil fehlt in der Bibliothek")
            pid, modus = prof.id, prof.modes[0].name
            n = len(prof.modes[0].channels)
        self.st.add_fixture(PatchedFixture(
            fid=1, label="Laser", fixture_profile_id=pid, mode_name=modus,
            universe=1, address=40, channel_count=n, fixture_type="laser"), undoable=False)
        self.laser = list(range(40, 40 + n))
        self.tmp = tempfile.mkdtemp(prefix="out61b_")
        self.show = os.path.join(self.tmp, "laser.lshow")
        save_show(self.show)
        self.addCleanup(self.st.set_laser_estop, False)
        self.addCleanup(self.st.clear_programmer)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_estop_im_lade_fenster_macht_den_laser_dunkel(self):
        from unittest import mock
        from src.core.show import show_file
        self.assertFalse(self.st.laser_estop_active)
        # Laser laeuft: Werte im Universum, also auch im eingefrorenen Frame.
        for attr in ("macro", "shutter"):
            self.st.set_programmer_value(1, attr, 200)
        self.st._render_frame(0.02)
        self.om._send_all()
        vorher = self.om._display_frame[1]
        self.assertTrue(any(vorher[a - 1] for a in self.laser), "Laser laeuft nicht")
        mitten = []
        echt = show_file._reset_state

        def reset_dann_notaus(*a, **k):
            echt(*a, **k)                       # Plan jetzt leer
            self.st.set_laser_estop(True)       # NOT-AUS genau jetzt
            self.st._render_frame(0.02)
            self.om._send_all()
            mitten.append(bytes(self.om._display_frame[1]))

        with mock.patch.object(show_file, "_reset_state", reset_dann_notaus):
            ok, msg = show_file.load_show(self.show)
        self.assertTrue(ok, msg)
        self.assertTrue(mitten, "reset-first lief nicht")
        offen = [a for a in self.laser if mitten[0][a - 1] != 0]
        self.assertEqual(offen, [], f"Laser im Lade-Fenster trotz NOT-AUS an (Adressen {offen})")


if __name__ == "__main__":
    unittest.main()
