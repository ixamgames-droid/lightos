"""OUT-64 — Laser-NOT-AUS ueberlebt eine Routing-Umstellung.

Befund (Review zu OUT-63): die NOT-AUS-Maske arbeitet in INTERNEN Universen.
Wird bei aktivem Latch das Routing umgestellt — ein anderes internes Universum
geht jetzt auf den Ausgabeweg (Art-Net-/sACN-Universum, Enttec-Port), an dem der
Laser physisch haengt —, dann sendet dieses Universum ungesperrt an den Laser.
Ein Rig-Modifier (INVERSE: 0 -> 255) auf den Adressen genuegt, und der Laser
bekommt Licht, obwohl der NOT-AUS steht.

Fix: der OutputManager merkt sich bei aktivem Latch zusaetzlich die
AUSGABEWEGE der gesperrten Universen (Enttec-Port, Netz-Universum) und nullt die
Laser-Adressen in jedem Frame, der ueber einen dieser Wege hinausgeht — egal aus
welchem internen Universum. Art-Net ``n-1`` und sACN ``n`` gelten dabei als
dasselbe Netz-Universum (LightOS' eigene Zuordnung), vorsichtshalber.

Echter Pfad: echter AppState, echter Patch, ``set_laser_estop``,
``_render_frame`` und ``_send_all``; geprueft wird, was die Sender bekommen.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import get_state                                  # noqa: E402
from src.core.dmx import output_manager as om_mod                        # noqa: E402
from src.core.engine.channel_modifier import (ChannelModifier, CurveType,  # noqa: E402
                                              get_modifier_manager)

ADR = 40


class _Netz:
    """Art-Net-/sACN-Attrappe: merkt, was pro externem Universum hinausging."""
    gesendet: dict = {}

    def __init__(self, target_ip=None):
        self.target_ip = target_ip

    def send_dmx(self, universum, data):
        _Netz.gesendet[("netz", type(self).__name__, universum)] = bytes(data)

    def close(self):
        pass


class _ArtNet(_Netz):
    pass


class _SACN(_Netz):
    pass


class _Enttec:
    def __init__(self, port):
        self.port = port

    def send_dmx(self, data):
        _Netz.gesendet[("enttec", self.port)] = bytes(data)

    def close(self):
        pass

    def is_open(self):
        return True


class EstopUeberAusgabewegTest(unittest.TestCase):

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
            self.assertIsNotNone(prof, "Laser-Profil fehlt in der Bibliothek")
            self.pid, self.modus = prof.id, prof.modes[0].name
            self.n = len(prof.modes[0].channels)
        _Netz.gesendet = {}
        orig = (om_mod.ArtNetSender, om_mod.SACNSender, om_mod._make_enttec_device)
        om_mod.ArtNetSender, om_mod.SACNSender = _ArtNet, _SACN
        om_mod._make_enttec_device = _Enttec

        def _zurueck():
            om_mod.ArtNetSender, om_mod.SACNSender, om_mod._make_enttec_device = orig
        self.addCleanup(_zurueck)
        for u in (1, 2):
            if u not in self.om.universes:
                self.om.add_universe(u)
            self.addCleanup(self.om.remove_output, u)
        self._mod_adressen = []
        self.addCleanup(self._modifier_weg)
        self.addCleanup(self.st.set_laser_estop, False)
        self.addCleanup(self.st.clear_programmer)
        self.addCleanup(reset_show)
        # Laser in Universum 1; Universum 2 hat auf denselben Adressen einen
        # Rig-Modifier (INVERSE) - ungesperrt kommt dort 255 heraus.
        from src.core.database.models import PatchedFixture
        self.st.add_fixture(PatchedFixture(
            fid=1, label="Laser", fixture_profile_id=self.pid, mode_name=self.modus,
            universe=1, address=ADR, channel_count=self.n, fixture_type="laser"),
            undoable=False)
        for a in range(ADR, ADR + self.n):
            self.mods.add(ChannelModifier(universe=2, address=a, curve=CurveType.INVERSE))
            self._mod_adressen.append((2, a))

    def _modifier_weg(self):
        for u, a in self._mod_adressen:
            self.mods.remove(u, a)

    def _senden(self):
        self.st._render_frame(0.02)
        self.om._send_all()

    def _offen(self, schluessel):
        data = _Netz.gesendet.get(schluessel)
        self.assertIsNotNone(data, f"nichts gesendet an {schluessel}")
        return [a for a in range(ADR, ADR + self.n) if data[a - 1] != 0]

    # ── Art-Net: anderes Universum auf das Laser-Universum umgelegt ─────────

    def test_artnet_umgelegt_bleibt_dunkel(self):
        self.om.add_artnet(1, "2.0.0.1", out_universe=0)       # Laser haengt an Art-Net 0
        self.om.add_artnet(2, "2.0.0.1", out_universe=1)
        self._senden()
        self.assertTrue(self._offen(("netz", "_ArtNet", 1)),
                        "Testaufbau: INVERSE muesste in Universum 2 Werte != 0 liefern")
        self.st.set_laser_estop(True)
        self._senden()
        self.assertEqual([], self._offen(("netz", "_ArtNet", 0)), "Laser im NOT-AUS offen")
        # Bei aktivem Latch: Universum 2 geht jetzt auf Art-Net 0, 1 woandershin.
        self.om.add_artnet(1, "2.0.0.1", out_universe=7)
        self.om.add_artnet(2, "2.0.0.1", out_universe=0)
        _Netz.gesendet.clear()
        self._senden()
        self.assertEqual([], self._offen(("netz", "_ArtNet", 0)),
                         "OUT-64: nach Routing-Umstellung bekommt der Laser Licht (INVERSE)")
        # Loesen: der Ausgabeweg ist wieder frei.
        self.st.set_laser_estop(False)
        _Netz.gesendet.clear()
        self._senden()
        self.assertEqual(self.n, len(self._offen(("netz", "_ArtNet", 0))),
                         "nach dem Loesen bleibt der Ausgabeweg gesperrt")

    def test_sacn_auf_dasselbe_netz_universum_bleibt_dunkel(self):
        # Art-Net 0 und sACN 1 sind fuer LightOS dasselbe Netz-Universum 1.
        self.om.add_artnet(1, "2.0.0.1", out_universe=0)
        self.st.set_laser_estop(True)
        self.om.add_sacn(2, None, out_universe=1)
        self._senden()
        self.assertEqual([], self._offen(("netz", "_SACN", 1)),
                         "OUT-64: Laser ueber sACN auf seinem Netz-Universum offen")

    def test_enttec_port_umgelegt_bleibt_dunkel(self):
        self.om.add_enttec(1, "COM7")
        self.st.set_laser_estop(True)
        self._senden()
        self.assertEqual([], self._offen(("enttec", "COM7")))
        self.om.add_enttec(2, "COM7")           # schliesst den Port auf Universum 1
        _Netz.gesendet.clear()
        self._senden()
        self.assertEqual([], self._offen(("enttec", "COM7")),
                         "OUT-64: Enttec-Port des Lasers nach Umstellung offen")

    def test_ohne_latch_aendert_sich_nichts(self):
        self.om.add_artnet(1, "2.0.0.1", out_universe=5)
        self.om.add_artnet(2, "2.0.0.1", out_universe=0)
        self._senden()
        self.assertEqual(self.n, len(self._offen(("netz", "_ArtNet", 0))),
                         "ohne NOT-AUS muss Universum 2 normal senden")
        self.assertFalse(getattr(self.om, "_laser_estop_wege", {}),
                         "ohne NOT-AUS darf kein Ausgabeweg gesperrt sein")


if __name__ == "__main__":
    unittest.main()
