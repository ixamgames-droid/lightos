"""LAS-04: PatchedFixture.protocol — Netzwerk-Laser ohne DMX-Adressraum.

Deckt ab: fixture_uses_dmx-Helper, DB-Default + ALTER-TABLE-Migration,
.lshow-Serialisierung (beidseitig, Alt-Show-Default 'dmx') und die drei
Render-/Flush-Gates (_rebuild_render_plan, _apply_fixture_map,
_flush_programmer_to_dmx), die Platzhalter-Adressen von Netzwerk-Lasern aus
den DMX-Universen heraushalten.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import AppState, fixture_uses_dmx
from src.core.dmx.universe import Universe


class _Ch:
    def __init__(self, attr, num, default=0):
        self.attribute = attr
        self.channel_number = num
        self.default_value = default


class _Fx:
    def __init__(self, fid, address, protocol="dmx"):
        self.fid = fid
        self.universe = 1
        self.address = address
        self.protocol = protocol
        self.invert_pan = False
        self.invert_tilt = False
        self.swap_pan_tilt = False


class _OM:
    def set_gm_address_mask(self, mask):
        self.mask = mask


class FixtureUsesDmxTest(unittest.TestCase):
    def test_helper(self):
        self.assertTrue(fixture_uses_dmx(_Fx(1, 1, "dmx")))
        self.assertTrue(fixture_uses_dmx(_Fx(1, 1, "")))
        self.assertTrue(fixture_uses_dmx(object()))     # Alt-Objekt ohne Feld
        self.assertFalse(fixture_uses_dmx(_Fx(1, 1, "etherdream")))
        self.assertFalse(fixture_uses_dmx(_Fx(1, 1, "IDN")))


class ModelAndMigrationTest(unittest.TestCase):
    def test_default_dmx_on_insert(self):
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session
        from src.core.database.models import Base, PatchedFixture
        eng = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(eng)
        with Session(eng) as s:
            s.add(PatchedFixture(fid=1, label="L", fixture_profile_id=1,
                                 mode_name="m", address=1, channel_count=1))
            s.commit()
            row = s.execute(select(PatchedFixture)).scalars().one()
            self.assertEqual(row.protocol, "dmx")

    def test_migration_adds_protocol_column(self):
        from sqlalchemy import create_engine, text
        from src.core.database.models import migrate_show_db
        eng = create_engine("sqlite:///:memory:")
        with eng.begin() as conn:
            # Legacy-Schema OHNE protocol-Spalte (Minimal-Ausschnitt).
            conn.execute(text(
                "CREATE TABLE patched_fixtures ("
                "id INTEGER PRIMARY KEY, fid INTEGER, address INTEGER)"))
            conn.execute(text(
                "CREATE TABLE fixture_groups (id INTEGER PRIMARY KEY)"))
            conn.execute(text(
                "INSERT INTO patched_fixtures (fid, address) VALUES (7, 1)"))
        migrate_show_db(eng)
        with eng.begin() as conn:
            cols = {r[1] for r in conn.execute(
                text("PRAGMA table_info(patched_fixtures)"))}
            self.assertIn("protocol", cols)
            val = conn.execute(text(
                "SELECT protocol FROM patched_fixtures WHERE fid=7"
            )).scalar()
        self.assertEqual(val, "dmx")


class ShowFileSerializationTest(unittest.TestCase):
    def test_object_without_field_defaults_dmx(self):
        from src.core.show.show_file import _fixture_to_dict
        d = _fixture_to_dict(_Fx(1, 1))
        self.assertEqual(d["protocol"], "dmx")

    def test_dict_roundtrip_preserves_protocol(self):
        from src.core.show.show_file import (_fixture_to_dict,
                                             _patched_fixture_from_data)
        d = _fixture_to_dict({"fid": 2, "protocol": "etherdream"})
        self.assertEqual(d["protocol"], "etherdream")
        pf = _patched_fixture_from_data(d, fallback_fid=2)
        self.assertEqual(pf.protocol, "etherdream")

    def test_legacy_show_without_field_defaults_dmx(self):
        from src.core.show.show_file import _patched_fixture_from_data
        pf = _patched_fixture_from_data({"fid": 3}, fallback_fid=3)
        self.assertEqual(pf.protocol, "dmx")


def _bare_state(patch):
    st = AppState.__new__(AppState)
    st._patch_cache = list(patch)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.output_manager = _OM()
    return st


class RenderGateTest(unittest.TestCase):
    """Netzwerk-Laser (Adresse 1, ueberlappt den PAR) darf NIE in Universe-
    Bytes schreiben — weder Defaults/Spans noch Programmer-/Map-Flush."""

    def setUp(self):
        import src.core.app_state as app_state
        self._app_state = app_state
        self._saved = app_state.get_channels_for_patched
        self._chans = {
            1: [_Ch("dimmer", 1, default=10), _Ch("color_r", 2)],
            2: [_Ch("shutter", 1), _Ch("laser_x", 2)],
        }
        app_state.get_channels_for_patched = lambda f: self._chans[f.fid]

    def tearDown(self):
        self._app_state.get_channels_for_patched = self._saved

    def _state(self):
        par = _Fx(1, 1, "dmx")
        laser = _Fx(2, 1, "etherdream")   # Platzhalter-Adresse = PAR-Adresse!
        return _bare_state([par, laser]), par, laser

    def test_render_plan_excludes_network_laser(self):
        st, _par, laser = self._state()
        st._rebuild_render_plan()
        # Im fix_index bekannt (Programmer/Effekte adressieren per fid) ...
        self.assertIn(2, st._fix_index)
        # ... aber nur die PAR-Adressen (1-2) sind gepatcht/im Default-Frame.
        self.assertEqual(st._patched_set.get(1), frozenset({1, 2}))
        self.assertEqual(st._default_frame[1][0], 10)   # PAR-Dimmer-Default
        self.assertEqual(st._commit_spans[1], [(1, 2)])

    def test_apply_fixture_map_skips_network_laser(self):
        st, _par, _laser = self._state()
        st._rebuild_render_plan()
        scratch = {1: Universe(1)}
        st._apply_fixture_map(scratch, {2: {"laser_x": 200, "shutter": 255}})
        self.assertEqual(scratch[1].get_channel(1), 0)
        self.assertEqual(scratch[1].get_channel(2), 0)
        # Gegenprobe: das DMX-Geraet schreibt weiterhin.
        st._apply_fixture_map(scratch, {1: {"dimmer": 123}})
        self.assertEqual(scratch[1].get_channel(1), 123)

    def test_flush_programmer_skips_network_laser(self):
        st, _par, _laser = self._state()
        st._rebuild_render_plan()
        st.programmer = {2: {"laser_x": 222, "shutter": 255}}
        st._flush_programmer_to_dmx(2)
        self.assertEqual(st.universes[1].get_channel(1), 0)
        self.assertEqual(st.universes[1].get_channel(2), 0)
        st.programmer[1] = {"dimmer": 99}
        st._flush_programmer_to_dmx(1)
        self.assertEqual(st.universes[1].get_channel(1), 99)


class ExecutorGateTest(unittest.TestCase):
    def test_executor_flush_skips_network_laser(self):
        import src.core.app_state as app_state
        from src.core.engine.executor import PlaybackEngine
        chans = {2: [_Ch("laser_x", 1)], 1: [_Ch("dimmer", 1)]}
        saved = app_state.get_channels_for_patched
        app_state.get_channels_for_patched = lambda f: chans[f.fid]
        try:
            st = _bare_state([_Fx(1, 1, "dmx"), _Fx(2, 1, "etherdream")])
            st.get_patched_fixtures = lambda: st._patch_cache
            eng = PlaybackEngine.__new__(PlaybackEngine)
            eng._state = st
            eng._flush_to_dmx({2: {"laser_x": 240}, 1: {"dimmer": 55}})
            self.assertEqual(st.universes[1].get_channel(1), 55)
        finally:
            app_state.get_channels_for_patched = saved


if __name__ == "__main__":
    unittest.main()
