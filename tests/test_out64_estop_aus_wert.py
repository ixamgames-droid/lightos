"""OUT-64/OUT-65 — der NOT-AUS schreibt auf JEDEM Ausgabeweg den Aus-Wert.

Befund (Review zu OUT-64): seit LAS-25 schreibt der NOT-AUS an Laser-Adressen
mit bekanntem Aus-Wert DIESEN Wert (Betriebsart 50 = „Laser off“), nicht 0 —
denn 0 heisst bei vielen Lasern „Auto run“, also AN. Die Sperre je Ausgabeweg
(OUT-64) setzte dieselben Adressen danach aber wieder hart auf 0, auch auf dem
eigenen Weg des Lasers: der NOT-AUS schaltete den Laser ueber
Art-Net/sACN/Enttec EIN. Die Anzeige (``_display_frame``) zeigte 50, gesendet
wurde 0 — deshalb prueft dieser Test die GESENDETEN Bytes einer Attrappe.

OUT-65: auf main passten OUT-63 (klebrige Maske) und LAS-25 nicht zusammen —
faellt ein Laser bei aktivem Latch aus dem Patch, fehlte sein Aus-Wert, der
NOT-AUS schrieb 0. Die Aus-Werte sind jetzt genauso klebrig wie die Adressen.

Echter Pfad: AppState-Render-Plan, ``set_laser_estop``, ``_render_frame`` und
``OutputManager._send_all`` mit Sender-Attrappen (kein Netz, keine Schnittstelle).
"""
import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.app_state import AppState
from src.core.dmx import output_manager as om_mod
from src.core.dmx.output_manager import OutputManager
from src.core.engine.channel_modifier import (ChannelModifier, CurveType,
                                              get_modifier_manager)


class _Rg:
    def __init__(self, von, bis, name, kind=""):
        self.range_from, self.range_to, self.name, self.kind = von, bis, name, kind


class _Ch:
    def __init__(self, attr, num, ranges=(), default=0):
        self.attribute = attr
        self.channel_number = num
        self.default_value = default
        self.ranges = list(ranges)
        self.name = attr


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 3
    protocol = ""

    def __init__(self, fid, universe, address, ftype=""):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.fixture_type = ftype
        self.fixture_name = f"fx{fid}"


class _FM:
    def tick(self, universes, patch_cache, dt):
        pass


# Laser auf 10: Betriebsart 0-49 „Auto run“ (DMX 0 = AN!), 50-99 „Laser off“.
ADR = 10
AUS = 50
MANUAL = 120
_LASER = _Fx(7, 1, ADR, "laser")
_CHANNELS = {
    7: [_Ch("shutter", 1, [_Rg(0, 49, "Auto run", "open"),
                           _Rg(50, 99, "Laser off", "closed"),
                           _Rg(100, 255, "Manual", "open")]),
        _Ch("laser_bank", 2), _Ch("laser_x", 3)],
}

GESENDET: dict = {}


class _Netz:
    def __init__(self, target_ip=None):
        self.target_ip = target_ip

    def send_dmx(self, universum, data):
        GESENDET[(type(self).__name__, universum)] = bytes(data)

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
        GESENDET[("Enttec", self.port)] = bytes(data)

    def close(self):
        pass

    def is_open(self):
        return True


def _make():
    om = OutputManager()
    om.add_universe(1)
    om.add_universe(2)
    st = AppState.__new__(AppState)
    st.universes = om.universes
    st.programmer = {7: {"shutter": MANUAL, "laser_bank": 5}}
    st.playback_engine = None
    st.function_manager = _FM()
    st._patch_cache = [_LASER]
    st._prog_lock = threading.RLock()
    st.output_manager = om
    st.laser_estop_active = False
    st._laser_estop_addrs = {}
    st._laser_fids = frozenset()
    st.base_levels = {}
    st._engine_extra_prev = {}
    st._suppress_emits = True
    st._emit = lambda *a, **k: None
    st._rebuild_render_plan()
    return st, om


class EstopAusWertJeWegTest(unittest.TestCase):

    def setUp(self):
        GESENDET.clear()
        orig_kanaele = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _CHANNELS[fx.fid]
        orig = (om_mod.ArtNetSender, om_mod.SACNSender, om_mod._make_enttec_device)
        om_mod.ArtNetSender, om_mod.SACNSender = _ArtNet, _SACN
        om_mod._make_enttec_device = _Enttec

        def _zurueck():
            A.get_channels_for_patched = orig_kanaele
            om_mod.ArtNetSender, om_mod.SACNSender, om_mod._make_enttec_device = orig
        self.addCleanup(_zurueck)
        self.st, self.om = _make()
        self.mods = get_modifier_manager()
        self._mod_adressen = []
        self.addCleanup(self._modifier_weg)

    def _modifier_weg(self):
        for u, a in self._mod_adressen:
            self.mods.remove(u, a)

    def _senden(self):
        GESENDET.clear()
        self.st._render_frame(0.025)
        self.om._send_all()

    def _byte(self, schluessel, adr=ADR):
        data = GESENDET.get(schluessel)
        self.assertIsNotNone(data, f"nichts gesendet an {schluessel}")
        return data[adr - 1]

    # ── eigener Weg des Lasers ───────────────────────────────────────────────

    def test_artnet_eigener_weg_sendet_aus_wert(self):
        self.om.add_artnet(1, "2.0.0.1", out_universe=0)
        self._senden()
        self.assertEqual(MANUAL, self._byte(("_ArtNet", 0)))
        self.st.set_laser_estop(True)
        self._senden()
        self.assertEqual(AUS, self.om._display_frame[1][ADR - 1])
        self.assertEqual(AUS, self._byte(("_ArtNet", 0)),
                         "NOT-AUS sendet 0 (= Auto run, Laser AN) statt Aus-Wert")
        self.assertEqual(0, self._byte(("_ArtNet", 0), ADR + 1))   # Muster dunkel

    def test_sacn_eigener_weg_sendet_aus_wert(self):
        self.om.add_sacn(1, None, out_universe=1)
        self.st.set_laser_estop(True)
        self._senden()
        self.assertEqual(AUS, self._byte(("_SACN", 1)))

    def test_enttec_eigener_weg_sendet_aus_wert(self):
        self.om.add_enttec(1, "COM7")
        self.st.set_laser_estop(True)
        self._senden()
        self.assertEqual(AUS, self._byte(("Enttec", "COM7")))

    def test_aus_wert_schlaegt_inverse_auf_eigenem_weg(self):
        self.mods.add(ChannelModifier(universe=1, address=ADR, curve=CurveType.INVERSE))
        self._mod_adressen.append((1, ADR))
        self.om.add_artnet(1, "2.0.0.1", out_universe=0)
        self.st.set_laser_estop(True)
        self._senden()
        self.assertEqual(AUS, self._byte(("_ArtNet", 0)))

    # ── Umroutung bei aktivem Latch ──────────────────────────────────────────

    def test_umgeroutetes_universum_sendet_aus_wert(self):
        # Universum 2 hat INVERSE auf der Laser-Adresse (0 -> 255).
        self.mods.add(ChannelModifier(universe=2, address=ADR, curve=CurveType.INVERSE))
        self._mod_adressen.append((2, ADR))
        self.om.add_artnet(1, "2.0.0.1", out_universe=0)
        self.om.add_artnet(2, "2.0.0.1", out_universe=1)
        self.st.set_laser_estop(True)
        self._senden()
        self.assertEqual(AUS, self._byte(("_ArtNet", 0)))
        # Bei aktivem Latch: Universum 2 auf den Weg des Lasers.
        self.om.add_artnet(1, "2.0.0.1", out_universe=7)
        self.om.add_artnet(2, "2.0.0.1", out_universe=0)
        self._senden()
        self.assertEqual(AUS, self._byte(("_ArtNet", 0)),
                         "nach Umroutung: Laser-Weg bekommt nicht den Aus-Wert")
        self.assertEqual(0, self._byte(("_ArtNet", 0), ADR + 1))
        # Der Laser-Weg ueber sACN (gleiches Netz-Universum) ebenfalls.
        self.om.add_sacn(2, None, out_universe=1)
        self._senden()
        self.assertEqual(AUS, self._byte(("_SACN", 1)))

    def test_enttec_port_umgelegt_sendet_aus_wert(self):
        self.om.add_enttec(1, "COM7")
        self.st.set_laser_estop(True)
        self.om.add_enttec(2, "COM7")          # schliesst den Port auf Universum 1
        self._senden()
        self.assertEqual(AUS, self._byte(("Enttec", "COM7")))

    def test_latch_zwischen_remove_und_add(self):
        # Restluecke a: apply_output_config ruft remove_output(1) und erst dann
        # add_*(1). Faellt der NOT-AUS genau dazwischen, fehlte der alte Weg.
        self.mods.add(ChannelModifier(universe=2, address=ADR, curve=CurveType.INVERSE))
        self._mod_adressen.append((2, ADR))
        self.om.add_artnet(1, "2.0.0.1", out_universe=0)       # Laser an Art-Net 0
        self.om.remove_output(1)
        self.st.set_laser_estop(True)                          # genau hier
        self.om.add_artnet(1, "2.0.0.1", out_universe=7)
        self.om.add_artnet(2, "2.0.0.1", out_universe=0)
        self.om.vergiss_entfernte_wege()
        self._senden()
        self.assertEqual(AUS, self._byte(("_ArtNet", 0)),
                         "Latch zwischen remove_output und add_*: alter Weg offen")
        self.assertEqual(0, self._byte(("_ArtNet", 0), ADR + 1))

    def test_entfernte_wege_ohne_latch_folgenlos(self):
        self.om.add_artnet(1, "2.0.0.1", out_universe=0)
        self.om.remove_output(1)
        self.om.add_artnet(1, "2.0.0.1", out_universe=7)
        self.assertFalse(self.om._entfernte_wege)
        self.om.add_artnet(2, "2.0.0.1", out_universe=0)
        self.st.set_laser_estop(True)
        self._senden()
        # Universum 1 liegt jetzt auf Art-Net 7 — Art-Net 0 bleibt frei.
        self.assertEqual(AUS, self._byte(("_ArtNet", 7)))
        self.assertNotIn(("netz", 1), self.om._laser_estop_wege)

    def test_loesen_gibt_weg_frei(self):
        self.om.add_artnet(1, "2.0.0.1", out_universe=0)
        self.st.set_laser_estop(True)
        self.st.set_laser_estop(False)
        self.assertFalse(self.om._laser_estop_wege)
        self.assertFalse(getattr(self.om, "_laser_estop_aus", {}))

    # ── OUT-65: Aus-Werte klebrig wie die Adressen ───────────────────────────

    def test_out65_laser_faellt_aus_patch_aus_wert_bleibt(self):
        self.om.add_artnet(1, "2.0.0.1", out_universe=0)
        self.st.set_laser_estop(True)
        self._senden()
        self.assertEqual(AUS, self._byte(("_ArtNet", 0)))
        # Laser faellt bei aktivem Latch aus dem Patch (Show ohne ihn o. ae.).
        self.st._patch_cache = []
        self.st.programmer = {}
        self.st._rebuild_render_plan()
        self.assertNotIn(ADR, (self.om._gm_laser_aus_mask.get(1) or {}))
        self._senden()
        self.assertEqual(AUS, self.om._display_frame[1][ADR - 1],
                         "OUT-65: Aus-Wert nach Patch-Verlust vergessen (Anzeige)")
        self.assertEqual(AUS, self._byte(("_ArtNet", 0)),
                         "OUT-65: Aus-Wert nach Patch-Verlust vergessen (gesendet)")

    def test_out65_ohne_latch_nicht_klebrig(self):
        self.om.add_artnet(1, "2.0.0.1", out_universe=0)
        self.st._patch_cache = []
        self.st.programmer = {}
        self.st._rebuild_render_plan()
        self.st.set_laser_estop(True)
        self._senden()
        # Laser war schon vor dem Latch weg: weder Adresse noch Aus-Wert bekannt.
        self.assertEqual(0, self._byte(("_ArtNet", 0)))

    def test_out65_lade_fenster_latch_waehrend_laden(self):
        # OUT-61b: Latch erst waehrend des Ladens — der Plan ist schon leer.
        self.om.add_artnet(1, "2.0.0.1", out_universe=0)
        with self.om.lade_sperre():
            self.st._patch_cache = []
            self.st.programmer = {}
            self.st._rebuild_render_plan()
            self.st.set_laser_estop(True)
            self._senden()
            self.assertEqual(AUS, self._byte(("_ArtNet", 0)))
        self._senden()
        self.assertEqual(AUS, self._byte(("_ArtNet", 0)),
                         "nach dem Laden: Aus-Wert vom Ladebeginn verloren")


if __name__ == "__main__":
    unittest.main()
