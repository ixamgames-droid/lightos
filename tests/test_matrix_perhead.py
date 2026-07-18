"""FM-16: Multi-Head-Fixtures als Pro-Kopf-Matrix.

Die Kopf-Struktur (``attr#N``) existierte schon, aber Matrix-Engine + Gruppen
adressierten nur GANZE ``fid``s. Diese Runde macht die Einzelkoepfe eines
Mehrkopf-Fixtures (Spider/Mover-Bar/Hydrabeam) als eigene Matrix-Zellen
ansprechbar — jede Grid-Zelle kann ``"fid:head"`` sein, der Matrix-Write faerbt
dann NUR die Kanaele dieses Kopfes.

Getestet:
  * ``app_state.color_head_count`` / ``channels_for_head`` (Kopf-Projektion).
  * ``rgb_matrix._parse_cell`` / ``grids_from_positions`` (rueckwaertskompatibel).
  * ``RgbMatrixInstance`` head_grid to_dict/apply_dict-Roundtrip + Alt-Show-Default.
  * ``RgbMatrixInstance.write`` faerbt pro Kopf ISOLIERT (Kern) + RGBW-Weiss;
    ohne head_grid byte-identisch uniform (Rueckwaertskompat).
  * ``AppState.create_head_matrix_group`` (Auto-Kopf-Matrix, idempotent, nur Multi-Head).
"""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace as NS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.app_state import color_head_count, channels_for_head
from src.core.engine.rgb_matrix import (
    RgbMatrixInstance, RgbAlgorithm, MatrixStyle,
    _parse_cell, grids_from_positions, grid_from_positions,
)
from src.core.dmx.universe import Universe


class _Ch:
    def __init__(self, attribute, channel_number):
        self.attribute = attribute
        self.channel_number = channel_number
        self.default_value = 0


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 16

    def __init__(self, fid, universe, address):
        self.fid = fid
        self.universe = universe
        self.address = address


def _rgbw_heads(n):
    """n Koepfe, je color_r/g/b/w -> Kanaele 1..4n (Adresse 1 => addr == ch_num)."""
    chans, k = [], 1
    for _h in range(n):
        for a in ("color_r", "color_g", "color_b", "color_w"):
            chans.append(_Ch(a, k)); k += 1
    return chans


class HeadEnumerationTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def test_color_head_count(self):
        A.get_channels_for_patched = lambda fx: _rgbw_heads(4)
        self.assertEqual(color_head_count(NS(fixture_type="moving_head")), 4)
        A.get_channels_for_patched = lambda fx: _rgbw_heads(1)
        self.assertEqual(color_head_count(NS(fixture_type="par")), 1)
        # Laser = Punkt-Scanner, nie Multi-Emitter (auch bei >=2 color_r).
        A.get_channels_for_patched = lambda fx: _rgbw_heads(2)
        self.assertEqual(color_head_count(NS(fixture_type="laser")), 1)

    def test_channels_for_head_isolates_heads(self):
        chans = _rgbw_heads(4)
        h0 = channels_for_head(chans, 0)
        h2 = channels_for_head(chans, 2)
        # Kopf 0 -> color_r ch1; Kopf 2 -> color_r ch9 (3. Bank)
        self.assertEqual(h0["color_r"].channel_number, 1)
        self.assertEqual(h2["color_r"].channel_number, 9)
        self.assertNotEqual(h0["color_g"].channel_number, h2["color_g"].channel_number)

    def test_channels_for_head_shares_non_repeated(self):
        # Gemeinsamer Master-Dimmer (1x) erscheint bei JEDEM Kopf.
        chans = [_Ch("intensity", 1)] + _rgbw_heads(2)
        for head in (0, 1):
            proj = channels_for_head(chans, head)
            self.assertIn("intensity", proj)
            self.assertEqual(proj["intensity"].channel_number, 1)

    def test_channels_for_head_repeated_dimmer_is_per_head(self):
        # Pro-Kopf-Dimmer (intensity 2x, wie Hydrabeam 56ch) -> pro Kopf GETRENNT,
        # damit drive_intensity jeden Kopf einzeln dimmt (sonst blieben andere dunkel).
        chans = [_Ch("intensity", 1), _Ch("color_r", 2),
                 _Ch("intensity", 3), _Ch("color_r", 4)]
        h0 = channels_for_head(chans, 0)
        h1 = channels_for_head(chans, 1)
        self.assertEqual(h0["intensity"].channel_number, 1)
        self.assertEqual(h1["intensity"].channel_number, 3)   # eigener Dimmer
        self.assertEqual(h0["color_r"].channel_number, 2)
        self.assertEqual(h1["color_r"].channel_number, 4)


class CellParsingTest(unittest.TestCase):
    def test_parse_cell_backward_compatible(self):
        self.assertEqual(_parse_cell(5), (5, None))
        self.assertEqual(_parse_cell("5"), (5, None))
        self.assertEqual(_parse_cell("7:3"), (7, 3))
        self.assertEqual(_parse_cell("bad"), (None, None))

    def test_grids_from_positions_perhead(self):
        pos = {"0,0": "9:0", "1,0": "9:1", "2,0": "9:2", "3,0": "9:3"}
        fg, hg = grids_from_positions(pos, 4, 1)
        self.assertEqual(fg, [9, 9, 9, 9])
        self.assertEqual(hg, [0, 1, 2, 3])

    def test_grids_from_positions_legacy_fids(self):
        # Alt-Gruppen (reine fids) -> head_grid all None (rueckwaertskompat).
        fg, hg = grids_from_positions({"0,0": 9, "1,0": 10}, 2, 1)
        self.assertEqual(fg, [9, 10])
        self.assertEqual(hg, [None, None])

    def test_grid_from_positions_facade_unchanged(self):
        self.assertEqual(grid_from_positions({"0,0": 9, "1,0": "9:1"}, 2, 1), [9, 9])


class HeadGridRoundtripTest(unittest.TestCase):
    def test_head_grid_roundtrip(self):
        m = RgbMatrixInstance("M", fid=1, cols=4, rows=1,
                              fixture_grid=[9, 9, 9, 9], head_grid=[0, 1, 2, 3])
        d = m.to_dict()
        self.assertEqual(d["head_grid"], [0, 1, 2, 3])
        m2 = RgbMatrixInstance("M2", fid=2)
        m2.apply_dict(d)
        self.assertEqual(m2.head_grid, [0, 1, 2, 3])

    def test_legacy_show_without_head_grid(self):
        m = RgbMatrixInstance("M", fid=1, cols=1, rows=1, fixture_grid=[9])
        d = m.to_dict()
        d.pop("head_grid", None)          # Alt-Show ohne den Key
        m2 = RgbMatrixInstance("M2", fid=2)
        m2.apply_dict(d)
        self.assertEqual(m2.head_grid, [])   # -> ganzes Fixture, byte-identisch


class PerHeadWriteTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _rgbw_heads(4)

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _matrix(self, fixture_grid, head_grid):
        m = RgbMatrixInstance(name="t", cols=len(fixture_grid), rows=1,
                              fixture_grid=fixture_grid, head_grid=head_grid,
                              algorithm=RgbAlgorithm.PLAIN)
        m.style = MatrixStyle.RGBW
        m.start()
        return m

    def test_each_cell_colors_only_its_head(self):
        m = self._matrix([10, 10, 10, 10], [0, 1, 2, 3])
        # deterministische Zellfarben: Kopf0 rot, Kopf1 gruen, Kopf2 blau, Kopf3 gelb
        m._render = lambda step: [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
        u = Universe(1)
        m.write({1: u}, [_Fx(10, 1, 1)], 0.0)
        # Kopf0 (ch1-4) rot
        self.assertEqual((u.get_channel(1), u.get_channel(2), u.get_channel(3)), (255, 0, 0))
        # Kopf1 (ch5-8) gruen -> Isolation: Kopf1-R bleibt 0 (nicht von Kopf0 gesetzt)
        self.assertEqual((u.get_channel(5), u.get_channel(6), u.get_channel(7)), (0, 255, 0))
        # Kopf2 (ch9-12) blau
        self.assertEqual((u.get_channel(9), u.get_channel(10), u.get_channel(11)), (0, 0, 255))
        # Kopf3 (ch13-16) gelb: RGBW-Split -> W=0
        self.assertEqual((u.get_channel(13), u.get_channel(14), u.get_channel(15), u.get_channel(16)),
                         (255, 255, 0, 0))

    def test_perhead_rgbw_white_split(self):
        m = self._matrix([10, 10, 10, 10], [0, 1, 2, 3])
        m._render = lambda step: [(0, 0, 0), (255, 255, 255), (0, 0, 0), (0, 0, 0)]
        u = Universe(1)
        m.write({1: u}, [_Fx(10, 1, 1)], 0.0)
        # Kopf1 rein weiss -> nur W-Chip (ch8), RGB (ch5-7) = 0
        self.assertEqual((u.get_channel(5), u.get_channel(6), u.get_channel(7), u.get_channel(8)),
                         (0, 0, 0, 255))

    def test_backward_compat_uniform_without_head_grid(self):
        # 1 Zelle, KEIN head_grid -> ganzes Fixture: alle 4 Koepfe uniform.
        m = self._matrix([10], [])
        m._render = lambda step: [(255, 0, 0)]
        u = Universe(1)
        m.write({1: u}, [_Fx(10, 1, 1)], 0.0)
        for r_ch in (1, 5, 9, 13):        # color_r jedes Kopfes
            self.assertEqual(u.get_channel(r_ch), 255)


class CreateHeadMatrixGroupTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        self.state = A.AppState()
        self.state.open_show(tempfile.mktemp(suffix=".db"))

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _load_group(self, gid):
        from sqlalchemy.orm import Session
        from src.core.database.models import FixtureGroup
        with Session(self.state._show_engine) as s:
            return s.get(FixtureGroup, gid)

    def test_multihead_creates_perhead_group(self):
        A.get_channels_for_patched = lambda fx: _rgbw_heads(4)
        fx = NS(fid=7, label="Hydrabeam", fixture_type="moving_head")
        gid = self.state.create_head_matrix_group(fx)
        self.assertIsNotNone(gid)
        g = self._load_group(gid)
        self.assertEqual((g.cols, g.rows), (4, 1))
        self.assertEqual(json.loads(g.positions_json),
                         {"0,0": "7:0", "1,0": "7:1", "2,0": "7:2", "3,0": "7:3"})

    def test_idempotent_no_duplicate(self):
        A.get_channels_for_patched = lambda fx: _rgbw_heads(4)
        fx = NS(fid=7, label="Hydrabeam", fixture_type="moving_head")
        gid1 = self.state.create_head_matrix_group(fx)
        gid2 = self.state.create_head_matrix_group(fx)
        self.assertEqual(gid1, gid2)
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from src.core.database.models import FixtureGroup
        with Session(self.state._show_engine) as s:
            self.assertEqual(len(s.execute(select(FixtureGroup)).scalars().all()), 1)

    def test_single_head_creates_nothing(self):
        A.get_channels_for_patched = lambda fx: _rgbw_heads(1)
        fx = NS(fid=8, label="PAR", fixture_type="par")
        self.assertIsNone(self.state.create_head_matrix_group(fx))

    def test_remove_fixture_cleans_up_auto_group(self):
        # Review-Fix (MEDIUM): Delete/Undo eines Multi-Head-Fixtures raeumt seine
        # auto-erzeugte "· Köpfe"-Gruppe mit ab (keine verwaiste "fid:head"-Gruppe).
        A.get_channels_for_patched = lambda fx: _rgbw_heads(4)
        gid = self.state.create_head_matrix_group(
            NS(fid=7, label="HB", fixture_type="moving_head"))
        self.assertIsNotNone(self._load_group(gid))
        self.state.remove_fixture(7, undoable=False)
        self.assertIsNone(self._load_group(gid))

    def test_remove_fixture_spares_combined_group(self):
        # Eine vom Nutzer ZUSAMMENGELEGTE Matrix (mehrere fids) darf remove_fixture
        # NICHT loeschen — nur die dedizierte 1×N-Auto-Gruppe genau dieses fids.
        from sqlalchemy.orm import Session
        from src.core.database.models import FixtureGroup
        with Session(self.state._show_engine) as s:
            g = FixtureGroup(name="Combo", cols=2, rows=1,
                             positions_json=json.dumps({"0,0": "7:0", "1,0": "8:0"}),
                             folder="Multi-Head")
            s.add(g); s.commit(); gid = g.id
        self.state.remove_fixture(7, undoable=False)
        self.assertIsNotNone(self._load_group(gid))   # bleibt erhalten

    def test_create_under_suppression_no_crash(self):
        # Review-Fix (HIGH): unter _suppress_emits (Bulk-Load) erzeugt der Aufruf
        # die Gruppe, aber der group_changed-Emit wird ueber notify_groups_changed
        # unterdrueckt (kein re-entranter View-Rebuild). Hier: kein Crash.
        A.get_channels_for_patched = lambda fx: _rgbw_heads(4)
        self.state._suppress_emits = True
        try:
            gid = self.state.create_head_matrix_group(
                NS(fid=9, label="HB", fixture_type="moving_head"))
        finally:
            self.state._suppress_emits = False
        self.assertIsNotNone(gid)


if __name__ == "__main__":
    unittest.main()
