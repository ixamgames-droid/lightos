"""Grand-Master-Adressmaske: ein rein positions-basiertes Universum (Pan/Tilt/
Gobo/Farbrad, KEIN Dimmer/RGB) darf beim Absenken des Grand Masters NICHT global
gedimmt werden (Bug-Hunt 2026-07-12).

Vorher: _rebuild_render_plan legte einen gm_mask-Eintrag NUR an, wenn ein Fixture
mindestens eine Intensitaets-/Farbadresse hatte. Ein Universum voller Farbrad-Spots
ohne Dimmer/RGB bekam gar keinen Key -> output_manager._send_all fiel in den
``mask is None``-Global-Dim-Zweig (gedacht fuer UNGEPATCHTE Roh-Universen) und
skalierte ALLE 512 Bytes inkl. Pan/Tilt -> Moving Heads fuhren bei GM<100 % auf
falsche Positionen. Jetzt bekommt jedes gepatchte Universum einen (ggf. leeren)
Eintrag; leere Maske = nichts skalieren, fehlender Key = ungepatcht = global dimmen.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import AppState
from src.core.dmx.output_manager import OutputManager


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num


class _Fx:
    def __init__(self, fid, universe, address):
        self.fid = fid
        self.universe = universe
        self.address = address


class _FakeSender:
    def __init__(self):
        self.last = None

    def send_dmx(self, data):
        self.last = data

    def close(self):
        pass


class BuildGmMaskTest(unittest.TestCase):
    """Die Maske selbst: jedes gepatchte Universum ist vertreten (ggf. leer)."""

    def _st(self):
        return AppState.__new__(AppState)

    def test_position_only_universe_gets_empty_entry(self):
        st = self._st()
        fx = _Fx(1, 3, 10)
        chans = [_Ch("pan", 1), _Ch("tilt", 2), _Ch("gobo", 3), _Ch("color_wheel", 4)]
        mask = st._build_gm_mask({1: (fx, chans)})
        self.assertIn(3, mask)                 # Universum ist REGISTRIERT ...
        self.assertEqual(set(mask[3]), set())  # ... aber ohne zu skalierende Adresse

    def test_dimmer_universe_masks_the_dimmer_addr(self):
        st = self._st()
        fx = _Fx(1, 1, 5)
        chans = [_Ch("dimmer", 1), _Ch("pan", 2), _Ch("tilt", 3)]
        mask = st._build_gm_mask({1: (fx, chans)})
        self.assertEqual(set(mask[1]), {5})    # nur die Dimmer-Adresse (5), nicht Pan/Tilt

    def test_unpatched_universe_absent(self):
        st = self._st()
        # Universum 1 gepatcht, Universum 2 gar nicht -> 2 fehlt im Mask-Dict.
        fx = _Fx(1, 1, 1)
        mask = st._build_gm_mask({1: (fx, [_Ch("dimmer", 1)])})
        self.assertIn(1, mask)
        self.assertNotIn(2, mask)

    def test_cmy_only_fixture_not_dimmed_via_color(self):
        # A3D-37: ein CMY-only-Mover (KEIN echter Dimmer) darf NICHT ueber seine
        # SUBTRAKTIVEN CMY-Farbkanaele "gedimmt" werden — Skalieren Richtung 0 wuerde
        # CMY OEFFNEN (aufhellen/weiss) statt dunkeln. Er traegt also NICHTS zur
        # GM/Blackout-Dimm-Maske bei (Universum bleibt registriert = leere Maske).
        st = self._st()
        fx = _Fx(1, 2, 20)
        chans = [_Ch("cmy_c", 1), _Ch("cmy_m", 2), _Ch("cmy_y", 3), _Ch("pan", 4)]
        mask = st._build_gm_mask({1: (fx, chans)})
        self.assertIn(2, mask)                  # Universum registriert ...
        self.assertEqual(set(mask[2]), set())   # ... aber KEINE CMY-Adresse in der Maske

    def test_additive_rgb_only_still_dimmed_via_color(self):
        # Gegenprobe: ADDITIVES RGB ohne Dimmer bleibt virtueller Dimmer (Skalieren
        # Richtung 0 = dunkler, korrekt) -> die Farbadressen stehen weiter in der Maske.
        st = self._st()
        fx = _Fx(1, 2, 30)
        chans = [_Ch("color_r", 1), _Ch("color_g", 2), _Ch("color_b", 3), _Ch("pan", 4)]
        mask = st._build_gm_mask({1: (fx, chans)})
        self.assertEqual(set(mask[2]), {30, 31, 32})   # RGB gedimmt, Pan (33) nicht


class SendPathGmMaskTest(unittest.TestCase):
    """Der Sende-Pfad: leere Maske skaliert nichts, fehlender Key dimmt global."""

    def _om(self):
        om = OutputManager()
        u = om.add_universe(1)
        u.set_channel(1, 200)   # z. B. Pan
        u.set_channel(2, 128)   # z. B. Tilt
        fake = _FakeSender()
        om._enttec_outputs[1] = fake
        om.grand_master = 0.5
        return om, fake

    def test_present_empty_mask_scales_nothing(self):
        om, fake = self._om()
        om.set_gm_address_mask({1: frozenset()})   # gepatcht, keine Intensitaet
        om._send_all()
        self.assertEqual(fake.last[0], 200)         # Pan bleibt (NICHT gedimmt)
        self.assertEqual(fake.last[1], 128)         # Tilt bleibt

    def test_absent_universe_still_global_dims(self):
        om, fake = self._om()
        om.set_gm_address_mask({})                  # Universum 1 fehlt -> ungepatcht/roh
        om._send_all()
        self.assertEqual(fake.last[0], 100)         # global gedimmt wie bisher
        self.assertEqual(fake.last[1], 64)

    def test_intensity_addr_dimmed_position_untouched(self):
        om, fake = self._om()
        om.set_gm_address_mask({1: frozenset({1})})  # nur Adr 1 (Intensitaet)
        om._send_all()
        self.assertEqual(fake.last[0], 100)          # Adr 1 gedimmt
        self.assertEqual(fake.last[1], 128)          # Adr 2 (Pan) unberuehrt


if __name__ == "__main__":
    unittest.main()
