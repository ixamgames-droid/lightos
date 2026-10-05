"""OUT-63 (Review B1): Rennen zwischen Laser-NOT-AUS-Aktivierung in einem
fremden Thread (MIDI/OSC/Web) und dem Plan-Rebuild. Ohne gemeinsames
_estop_lock um Flag-Check, Union-Push und Plan-Tausch stand im Fenster bis zum
abschliessenden Push nur die ALTE Laser-Maske — INVERSE auf der neuen Adresse
ergab 255 trotz Latch."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import get_state                                  # noqa: E402
from src.core.engine.channel_modifier import (ChannelModifier, CurveType,  # noqa: E402
                                              get_modifier_manager)

ALT, NEU = 40, 200


class Basis(unittest.TestCase):
    def setUp(self):
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
        from src.core.database.models import FixtureProfile
        from src.core.show.show_file import reset_show
        ensure_builtins()
        self.st = get_state()
        self.om = self.st.output_manager
        self.mods = get_modifier_manager()
        self.st.set_laser_estop(False)
        reset_show()
        with Session(fdb_engine()) as s:
            prof = s.execute(select(FixtureProfile).where(
                FixtureProfile.short_name == "PARTYLASER")).scalars().first()
            self.pid, self.modus = prof.id, prof.modes[0].name
            self.n = len(prof.modes[0].channels)
            par = s.execute(select(FixtureProfile).where(
                FixtureProfile.short_name == "PARD")).scalars().first()
            self.par_pid, self.par_modus = par.id, par.modes[0].name
            self.par_n = len(par.modes[0].channels)
        self.tmp = tempfile.mkdtemp(prefix="probe63_")
        self._mod = []
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(self._mods_weg)
        self.addCleanup(self.st.set_laser_estop, False)
        self.addCleanup(self.st.clear_programmer)

    def _mods_weg(self):
        for u, a in self._mod:
            self.mods.remove(u, a)

    def _inverse(self, u, start, n=None):
        for a in range(start, start + (n or self.n)):
            self.mods.add(ChannelModifier(universe=u, address=a, curve=CurveType.INVERSE))
            self._mod.append((u, a))

    def _laser(self, fid, u, adr, undoable=False):
        from src.core.database.models import PatchedFixture
        if u not in self.om.universes:
            self.om.add_universe(u)
        self.st.add_fixture(PatchedFixture(
            fid=fid, label=f"Laser {fid}", fixture_profile_id=self.pid,
            mode_name=self.modus, universe=u, address=adr,
            channel_count=self.n, fixture_type="laser"), undoable=undoable)

    def _par(self, fid, u, adr):
        from src.core.database.models import PatchedFixture
        self.st.add_fixture(PatchedFixture(
            fid=fid, label=f"PAR {fid}", fixture_profile_id=self.par_pid,
            mode_name=self.par_modus, universe=u, address=adr,
            channel_count=self.par_n, fixture_type="par"), undoable=False)

    def _senden(self):
        self.st._render_frame(0.02)
        self.om._send_all()

    def _offen(self, u, start, n=None):
        f = self.om._display_frame.get(u)
        self.assertIsNotNone(f)
        return [a for a in range(start, start + (n or self.n)) if f[a - 1] != 0]


class Rennen(Basis):
    """Latch wird ZWISCHEN dem Flag-Check des Rebuilds (laser_estop_active noch
    False -> kein Union-Push) und dem Plan-Tausch ausgeloest (anderer Thread:
    MIDI/OSC/Web/Laser-NOT-AUS-Taste). Das Interleaving wird deterministisch
    nachgestellt: der Hook auf _get_plan_lock feuert genau im Rebuild."""

    def _mit_rennen(self, aktion):
        echt = type(self.st)._get_plan_lock
        st = self.st
        frames = []
        threads = []

        def plan_lock_hook(*a, **k):
            if sys._getframe(1).f_code.co_name == "_rebuild_render_plan" \
                    and not st.laser_estop_active:
                import threading
                t = threading.Thread(target=st.set_laser_estop, args=(True,))
                t.start()
                t.join(0.3)        # echter Fremd-Thread; blockiert er, ist es gut
                threads.append(t)
            return echt(st)

        echt_rel = type(self.st)._release_engine_extra

        def rel_hook(*a, **k):
            r = echt_rel(st)
            for t in threads:
                t.join(5)
            assert st.laser_estop_active
            # Frame des Sende-Threads im Fenster Plan-Tausch -> finaler Push
            self._senden()
            frames.append(self.om._display_frame.get(1))
            return r

        with mock.patch.object(st, "_get_plan_lock", plan_lock_hook), \
                mock.patch.object(st, "_release_engine_extra", rel_hook):
            aktion()
        for t in threads:
            t.join()
        return frames

    def test_umadressieren_neue_adresse_im_fenster(self):
        self._laser(1, 1, ALT)
        self._inverse(1, NEU)
        frames = self._mit_rennen(
            lambda: self.st.update_fixture(1, undoable=False, address=NEU))
        self.assertTrue(self.st.laser_estop_active)
        offen = [a for a in range(NEU, NEU + self.n) if frames[0][a - 1] != 0]
        self.assertEqual(offen, [], "Rennen: Laser an NEUER Adresse AN trotz Latch")

    def test_neuer_laser_im_fenster(self):
        self._laser(1, 1, ALT)
        self._inverse(1, NEU)
        frames = self._mit_rennen(lambda: self._laser(2, 1, NEU))
        self.assertTrue(self.st.laser_estop_active)
        offen = [a for a in range(NEU, NEU + self.n) if frames[0][a - 1] != 0]
        self.assertEqual(offen, [], "Rennen: neu gepatchter Laser AN trotz Latch")


if __name__ == "__main__":
    unittest.main()
