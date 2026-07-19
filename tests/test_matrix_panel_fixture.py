"""FM-13 — LED-Matrix/Pixel-Panel als eigener Fixture-Typ ('matrix').

Slice 1 (Foundation): neuer fixture_type 'matrix' + generisches Pixel-Panel-
Builtin (Master-Dimmer + per-Pixel-RGB), Routing-Gate (kein par_bar/spider-
Fehlrouting), per-Pixel-heads[]-Payload, coords-Hoehe, Klassen-Audit. Der 3D-
Panel-Render + die Per-Pixel-Farbe im QtWebEngine sind in
test_viz13_scene_modules_smoke.py nachgewiesen (buildMatrixPanel/updateMatrixPanelDmx).
"""
import os
import tempfile
import unittest
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _temp_seeded_engine():
    from src.core.database import fixture_db as FDB
    from src.core.database.fixture_db import get_engine, _seed
    saved = FDB._engine
    eng = get_engine(tempfile.mktemp(suffix=".db"))
    with Session(eng) as s:
        _seed(s)
        s.commit()
    FDB._engine = eng
    return FDB, eng, saved


def _load(session, short):
    from src.core.database.models import (
        FixtureChannel, FixtureMode, FixtureProfile,
    )
    return session.execute(
        select(FixtureProfile)
        .options(
            selectinload(FixtureProfile.manufacturer),
            selectinload(FixtureProfile.modes)
            .selectinload(FixtureMode.channels)
            .selectinload(FixtureChannel.ranges),
        )
        .where(FixtureProfile.short_name == short)
    ).scalars().first()


def _mode(profile, name):
    return next(m for m in profile.modes if m.name == name)


def _attrs(mode):
    return [c.attribute for c in sorted(mode.channels,
                                        key=lambda c: c.channel_number)]


class _SeededCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._FDB, cls._eng, cls._saved = _temp_seeded_engine()

    @classmethod
    def tearDownClass(cls):
        cls._FDB._engine = cls._saved


class MatrixPanelProfileTest(_SeededCase):
    def test_profile_class_and_modes(self):
        with Session(self._eng) as s:
            p = _load(s, "MATRIXPANEL")
            self.assertIsNotNone(p)
            self.assertEqual(p.name, "LED Matrix Panel")
            self.assertEqual(p.fixture_type, "matrix")
            self.assertEqual(p.manufacturer.name, "Generic")
            self.assertEqual(
                {m.name: m.channel_count for m in p.modes},
                {"4×4 (16 Pixel RGB)": 49, "8×8 (64 Pixel RGB)": 193},
            )

    def test_channel_layout_master_plus_per_pixel_rgb(self):
        with Session(self._eng) as s:
            p = _load(s, "MATRIXPANEL")
            for name, npx in (("4×4 (16 Pixel RGB)", 16), ("8×8 (64 Pixel RGB)", 64)):
                a = _attrs(_mode(p, name))
                self.assertEqual(a[0], "intensity")                 # Master-Dimmer
                self.assertEqual(a[1:4], ["color_r", "color_g", "color_b"])
                self.assertEqual(a.count("color_r"), npx)           # eine RGB-Bank je Pixel
                self.assertEqual(a.count("color_g"), npx)
                self.assertEqual(a.count("color_b"), npx)
                self.assertEqual(len(a), 1 + 3 * npx)

    def test_master_dimmer_default_full(self):
        # Master default 255 -> Pixel (per Default schwarz) sind sofort sichtbar,
        # sobald RGB gesetzt wird; keine Blend-Gefahr (schwarz bleibt schwarz).
        with Session(self._eng) as s:
            p = _load(s, "MATRIXPANEL")
            ch = sorted(_mode(p, "4×4 (16 Pixel RGB)").channels,
                        key=lambda c: c.channel_number)[0]
            self.assertEqual(ch.attribute, "intensity")
            self.assertEqual(ch.default_value, 255)


class MatrixPanelRoutingTest(_SeededCase):
    """Das Panel darf NICHT ueber die Multi-Emitter-Heuristik auf par_bar/spider
    routen (es hat rows*cols color_r-Banks) — es nutzt seinen fixture_type 'matrix'
    (buildMatrixPanel). Gates: is_spider_fixture + suggest_viz_model + viz_model_for."""

    def test_suggest_viz_model_gates_matrix(self):
        from src.core.app_state import suggest_viz_model
        attrs = ["intensity"] + ["color_r", "color_g", "color_b"] * 16
        self.assertIsNone(suggest_viz_model("matrix", attrs))
        # Gegenprobe: dieselben Banks als 'par' wuerden auf par_bar routen.
        self.assertEqual(suggest_viz_model("par", attrs), "par_bar")

    def test_viz_model_for_returns_none_for_matrix(self):
        import src.core.app_state as AS
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        with Session(self._eng) as s:
            chans = [SimpleNamespace(attribute=c.attribute)
                     for c in sorted(_mode(_load(s, "MATRIXPANEL"),
                                           "4×4 (16 Pixel RGB)").channels,
                                     key=lambda c: c.channel_number)]
        saved = AS.get_channels_for_patched
        AS.get_channels_for_patched = lambda f: chans
        try:
            self.assertFalse(AS.is_spider_fixture(SimpleNamespace(fixture_type="matrix")))
            self.assertIsNone(AS.viz_model_for(SimpleNamespace(fixture_type="matrix")))
            # Der Renderer nutzt daher fixture_type 'matrix' direkt.
            model = VisualizerBridge._viz_model_for(
                SimpleNamespace(), SimpleNamespace(fixture_type="matrix"))
            self.assertEqual(model, "matrix")
        finally:
            AS.get_channels_for_patched = saved


class MatrixPanelPayloadTest(unittest.TestCase):
    """Per-Pixel-Farbe reist ueber die attr#N-Konvention -> heads[]-Array
    (visualizer_service). Pixel i <-> heads[i] <-> color_r#i."""

    def test_per_pixel_heads(self):
        from src.ui.visualizer.visualizer_service import (
            _build_fixture_payload, _multihead_count,
        )
        attrs = {"intensity": 255}
        for i in range(16):
            sfx = "" if i == 0 else f"#{i}"
            attrs[f"color_r{sfx}"] = 200 if i == 5 else 0
            attrs[f"color_g{sfx}"] = 0
            attrs[f"color_b{sfx}"] = 0
        self.assertEqual(_multihead_count(attrs), 16)
        pl = _build_fixture_payload(SimpleNamespace(fid=1), attrs)
        self.assertEqual(len(pl["heads"]), 16)
        self.assertEqual(pl["heads"][5]["r"], 200)   # Pixel 5 rot
        self.assertEqual(pl["heads"][0]["r"], 0)      # Pixel 0 aus
        self.assertEqual(pl["heads"][5]["g"], 0)


class MatrixPanelPayloadNHeadsTest(_SeededCase):
    """Adversariale-Review-HIGH (Regression): der ECHTE _fixture_to_dict-Pfad MUSS
    nHeads = Pixel-Anzahl (color_r-Banks) mitschicken — sonst baut buildMatrixPanel
    (0 -> 16) IMMER ein 4x4-Panel und das 8x8 (64px) verliert heads[16..63]. Der
    QtWebEngine-Smoke maskierte das mit hartkodiertem nHeads:16; dieser Test faehrt
    den echten Python-Payload-Pfad und schlaegt VOR dem Fix fehl (nHeads==0)."""

    def _nheads_via_fixture_to_dict(self, mode_name):
        import types
        import src.core.app_state as AS
        import src.ui.visualizer.visualizer_window as VW
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        with Session(self._eng) as s:
            chans = [SimpleNamespace(attribute=c.attribute)
                     for c in sorted(_mode(_load(s, "MATRIXPANEL"), mode_name).channels,
                                     key=lambda c: c.channel_number)]
        fake_state = SimpleNamespace(visualizer_positions={}, visualizer_rotations={},
                                     visualizer_docks={})
        fake_self = SimpleNamespace(_state=fake_state)
        # _viz_model_for an das Fake-Self binden -> nutzt die ECHTE Routing-Kette.
        fake_self._viz_model_for = types.MethodType(VisualizerBridge._viz_model_for, fake_self)
        fake_f = SimpleNamespace(fid=1, label="M", fixture_type="matrix")
        saved_as, saved_vw = AS.get_channels_for_patched, VW.get_channels_for_patched
        AS.get_channels_for_patched = lambda f: chans
        VW.get_channels_for_patched = lambda f: chans
        try:
            return VisualizerBridge._fixture_to_dict(fake_self, fake_f)
        finally:
            AS.get_channels_for_patched = saved_as
            VW.get_channels_for_patched = saved_vw

    def test_fixture_to_dict_threads_pixel_count(self):
        d16 = self._nheads_via_fixture_to_dict("4×4 (16 Pixel RGB)")
        self.assertEqual(d16["model"], "matrix")
        self.assertEqual(d16["nHeads"], 16)
        d64 = self._nheads_via_fixture_to_dict("8×8 (64 Pixel RGB)")
        self.assertEqual(d64["model"], "matrix")
        self.assertEqual(d64["nHeads"], 64)   # 8x8, NICHT 16 (Review-HIGH-Fix)


class MatrixPanelClassAuditTest(_SeededCase):
    def test_matrix_in_fixture_types_and_builtin_not_other(self):
        from src.ui.widgets.fixture_editor import FIXTURE_TYPES
        self.assertIn("matrix", FIXTURE_TYPES)
        with Session(self._eng) as s:
            p = _load(s, "MATRIXPANEL")
            self.assertNotEqual(p.fixture_type, "other")
            self.assertIn(p.fixture_type, FIXTURE_TYPES)

    def test_mini_icon_has_matrix_painter(self):
        from src.ui.widgets import mini_icons
        self.assertIn("fx_matrix", mini_icons._PAINTERS)

    def test_default_height(self):
        from src.core.stage.coords import default_height_for
        self.assertEqual(default_height_for("matrix"), 3.0)


if __name__ == "__main__":
    unittest.main()
