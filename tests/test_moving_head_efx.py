"""Moving-Head-Tests (Phase 0): EFX bewegt Pan/Tilt einer zugewiesenen Gruppe,
``open_beam`` macht die Strahler sichtbar, und Pan/Tilt-Invert/Swap wirken sowohl
im Programmer-Schreibpfad als auch im EFX-Output.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.app_state import AppState
from src.core.dmx.universe import Universe
from src.core.engine.efx import EfxInstance, EfxFixture, EfxAlgorithm


class _Range:
    def __init__(self, lo, hi, kind=""):
        self.range_from = lo
        self.range_to = hi
        self.kind = kind


class _Ch:
    def __init__(self, attr, num, default=0, highlight=255, ranges=None):
        self.attribute = attr
        self.channel_number = num
        self.default_value = default
        self.highlight_value = highlight
        self.ranges = ranges or []


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 4

    def __init__(self, fid, universe, address, **flags):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.invert_pan = flags.get("invert_pan", False)
        self.invert_tilt = flags.get("invert_tilt", False)
        self.swap_pan_tilt = flags.get("swap_pan_tilt", False)


# pan@1, tilt@2, intensity@3, shutter@4 (Open-Bereich 0..7)
MH_CHANS = [
    _Ch("pan", 1), _Ch("tilt", 2), _Ch("intensity", 3, 0),
    _Ch("shutter", 4, 0, ranges=[_Range(0, 7, "open")]),
]


class EfxMovingHeadTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: MH_CHANS

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _run(self, fx, **efxflags):
        uni = Universe(1)
        efx = EfxInstance(name="t")
        efx.algorithm = EfxAlgorithm.CIRCLE
        efx.fixtures = [EfxFixture(fid=fx.fid)]
        for k, v in efxflags.items():
            setattr(efx, k, v)
        efx._running = True
        efx.write({1: uni}, [fx], dt=0.5)
        return uni

    def test_efx_moves_pan_tilt(self):
        uni = self._run(_Fx(1, 1, 10))
        pan, tilt = uni.get_channel(10), uni.get_channel(11)
        self.assertTrue(pan > 0 or tilt > 0, "EFX hat Pan/Tilt nicht bewegt")

    def test_open_beam_sets_intensity_and_shutter(self):
        uni = self._run(_Fx(1, 1, 10), open_beam=True)
        self.assertEqual(uni.get_channel(12), 255)   # Dimmer voll
        self.assertEqual(uni.get_channel(13), 3)      # Shutter Open-Mitte (0..7)

    def test_efx_without_open_beam_leaves_dimmer(self):
        uni = self._run(_Fx(1, 1, 10))
        self.assertEqual(uni.get_channel(12), 0)      # Dimmer unberuehrt

    def test_efx_invert_pan(self):
        normal = self._run(_Fx(1, 1, 10)).get_channel(10)
        inverted = self._run(_Fx(1, 1, 10, invert_pan=True)).get_channel(10)
        self.assertEqual(inverted, 255 - normal)

    def test_efx_swap_pan_tilt(self):
        plain = self._run(_Fx(1, 1, 10))
        swapped = self._run(_Fx(1, 1, 10, swap_pan_tilt=True))
        # nach Swap traegt der Pan-Kanal den (alten) Tilt-Wert und umgekehrt
        self.assertEqual(swapped.get_channel(10), plain.get_channel(11))
        self.assertEqual(swapped.get_channel(11), plain.get_channel(10))


class ProgrammerOrientationTest(unittest.TestCase):
    """invert/swap wirken auch im Programmer-LTP (_apply_fixture_map)."""

    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: MH_CHANS

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _apply(self, fx, attrs):
        st = AppState.__new__(AppState)
        st._fix_index = {fx.fid: (fx, MH_CHANS)}
        uni = Universe(1)
        st._apply_fixture_map({1: uni}, {fx.fid: attrs})
        return uni

    def test_programmer_invert_pan(self):
        uni = self._apply(_Fx(1, 1, 10, invert_pan=True), {"pan": 10})
        self.assertEqual(uni.get_channel(10), 245)

    def test_programmer_swap(self):
        uni = self._apply(_Fx(1, 1, 10, swap_pan_tilt=True), {"pan": 10, "tilt": 200})
        self.assertEqual(uni.get_channel(10), 200)   # Pan-Kanal -> Tilt-Wert
        self.assertEqual(uni.get_channel(11), 10)    # Tilt-Kanal -> Pan-Wert

    def test_programmer_no_flags_unchanged(self):
        uni = self._apply(_Fx(1, 1, 10), {"pan": 10, "tilt": 200})
        self.assertEqual(uni.get_channel(10), 10)
        self.assertEqual(uni.get_channel(11), 200)


class ChannelRangesDetachedTest(unittest.TestCase):
    """Regression: get_channels_for_patched muss ChannelRange EAGER laden, sonst
    crasht open_value_for() im Per-Frame-Renderer (detached lazy load)."""

    def setUp(self):
        import tempfile
        from src.core.database import fixture_db as FDB
        from src.core.database.fixture_db import get_engine, _seed
        from sqlalchemy.orm import Session
        self._FDB = FDB
        self._saved = FDB._engine
        self._path = tempfile.mktemp(suffix=".db")
        eng = get_engine(self._path)
        with Session(eng) as s:
            _seed(s)
            s.commit()
        FDB._engine = eng
        import src.core.app_state as A
        A.clear_channel_cache()
        self._A = A

    def tearDown(self):
        self._FDB._engine = self._saved
        self._A.clear_channel_cache()

    def test_ranges_accessible_and_open_value(self):
        from sqlalchemy.orm import Session
        from sqlalchemy import select
        from src.core.database.models import FixtureProfile
        from src.core.app_state import get_channels_for_patched, open_value_for
        with Session(self._FDB._engine) as s:
            pid = s.execute(select(FixtureProfile.id)
                            .where(FixtureProfile.short_name == "ZQ02001")).scalar_one()
        fx = _Fx(1, 1, 33)
        fx.fixture_profile_id = pid
        fx.mode_name = "11-Kanal"
        fx.channel_count = 11
        chans = get_channels_for_patched(fx)
        sh = next(c for c in chans if c.attribute == "shutter")
        # Zugriff OHNE offene Session darf nicht werfen (eager geladen):
        kinds = [getattr(r, "kind", "") for r in sh.ranges]
        self.assertIn("open", kinds)
        self.assertTrue(0 <= open_value_for(fx, "shutter") <= 9)


class EfxPersistenceTest(unittest.TestCase):
    """M6: neue EFX-Felder (open_beam/spread/mirror) ueberleben to_dict/from_dict."""

    def test_roundtrip_new_fields(self):
        e = EfxInstance(name="Move")
        e.algorithm = EfxAlgorithm.EIGHT
        e.open_beam = True
        e.spread = 0.5
        e.mirror = True
        e.fixtures = [EfxFixture(fid=3), EfxFixture(fid=7)]
        d = e.to_dict()
        assert d.get("motion") is True
        e2 = EfxInstance.from_dict(d)
        self.assertEqual(e2.algorithm, EfxAlgorithm.EIGHT)
        self.assertTrue(e2.open_beam)
        self.assertAlmostEqual(e2.spread, 0.5)
        self.assertTrue(e2.mirror)
        self.assertEqual([f.fid for f in e2.fixtures], [3, 7])

    def test_legacy_dict_defaults(self):
        # Alt-Show ohne die neuen Schluessel -> sinnvolle Defaults, kein Crash.
        e = EfxInstance.from_dict({"name": "Old", "algorithm": "Circle",
                                   "fixtures": [{"fid": 1, "offset": 0.0}]})
        self.assertFalse(e.open_beam)
        self.assertFalse(e.mirror)
        self.assertEqual(e.spread, 1.0)


class EfxBounceTest(unittest.TestCase):
    """Regression (2026-06-10): 'bounce' pendelt zwischen 0 und 1. Frueher lief
    nach dem Klemmen auf 1.0 noch das gemeinsame ``%= 1.0`` -> Phase sprang auf
    0.0 zurueck und der Bounce wurde zum Saegezahn (MH 'Bounce' sprang sichtbar
    an den Anfang statt zurueckzulaufen)."""

    def _efx(self, phase, direction="bounce", bounce_dir=1.0):
        e = EfxInstance(name="b")
        e.direction = direction
        e.speed_hz = 1.0
        e.speed = 1.0
        e._phase = phase
        e._bounce_dir = bounce_dir
        return e

    def test_bounce_reverses_at_top(self):
        e = self._efx(0.95)
        e._advance(0.1)            # klemmt auf 1.0, Richtung dreht
        self.assertEqual(e._phase, 1.0)
        self.assertEqual(e._bounce_dir, -1.0)
        e._advance(0.1)            # muss RUNTER laufen, nicht bei 0.x starten
        self.assertAlmostEqual(e._phase, 0.9, places=6)

    def test_bounce_reverses_at_bottom(self):
        e = self._efx(0.05, bounce_dir=-1.0)
        e._advance(0.1)
        self.assertEqual(e._phase, 0.0)
        self.assertEqual(e._bounce_dir, 1.0)
        e._advance(0.1)
        self.assertAlmostEqual(e._phase, 0.1, places=6)

    def test_forward_wraps(self):
        e = self._efx(0.95, direction="forward")
        e._advance(0.1)
        self.assertAlmostEqual(e._phase, 0.05, places=6)

    def test_backward_wraps(self):
        e = self._efx(0.05, direction="backward")
        e._advance(0.1)
        self.assertAlmostEqual(e._phase, 0.95, places=6)


if __name__ == "__main__":
    unittest.main()
