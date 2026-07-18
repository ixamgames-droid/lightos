"""Katalog-Erweiterung Runde 3 (2026-07-18): reale Nutzer-Geraete.

  (A) Cameo HYDRABEAM 4000 RGBW — 4-Kopf-Moving-Beam-Bar (moving_head), Modi
      6/10/19/32/56. Nur der 56-Kanal-Modus hat pro Kopf eigenes RGBW -> viz
      'mover_bar' mit pro-Kopf-Farbe; die uebrigen Modi fallen auf den Einzel-
      'moving_head'.
  (B) Varytec Event PAR IP65 4in1 14x8W 25° — IP65-RGBW-PAR (par), Modi 4/7/9.

Getestet werden Profil-Struktur/Geraeteklasse, die gegen die HERSTELLER-Manuals
(Adam Hall/Cameo + QLC+ .qxf bzw. Varytec/Thomann) verifizierten Kanal-Charts,
die Safety-Shutter-Defaults (0..10 = offen), die Mehrkopf-Layouts und die ECHTE
viz_model_for-Routing-Entscheidung. Analog test_catalog_round2_profiles.
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
    return next(mode for mode in profile.modes if mode.name == name)


def _channels(mode):
    return sorted(mode.channels, key=lambda channel: channel.channel_number)


def _attrs(mode):
    return [c.attribute for c in _channels(mode)]


class _SeededCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._FDB, cls._eng, cls._saved = _temp_seeded_engine()

    @classmethod
    def tearDownClass(cls):
        cls._FDB._engine = cls._saved

    def _first_shutter(self, short, mode_name):
        with Session(self._eng) as s:
            return next(c for c in _channels(_mode(_load(s, short), mode_name))
                        if c.attribute == "shutter")

    def _assert_default_open(self, short, mode_name):
        """Der (erste) Shutter-Default MUSS auf einen 'open'-Range fallen, sonst
        haengt das Geraet im geschlossenen Shutter (dunkel) — dokumentierte Falle."""
        sh = self._first_shutter(short, mode_name)
        hit = next(r for r in sh.ranges
                   if r.range_from <= sh.default_value <= r.range_to)
        self.assertEqual(hit.kind, "open",
                         f"{short}/{mode_name}: Shutter-Default "
                         f"{sh.default_value} faellt auf '{hit.name}' ({hit.kind})")


class CameoHydrabeam4000Test(_SeededCase):
    """Cameo HYDRABEAM 4000 RGBW — 4-Kopf-Moving-Beam, Chart: Adam Hall/Cameo + QLC+."""

    def test_profile_class_and_modes(self):
        with Session(self._eng) as s:
            p = _load(s, "HYDRA4000")
            self.assertIsNotNone(p)
            self.assertEqual(p.name, "HYDRABEAM 4000 RGBW")
            self.assertEqual(p.fixture_type, "moving_head")
            self.assertEqual(p.manufacturer.name, "Cameo")
            self.assertEqual(
                {m.name: m.channel_count for m in p.modes},
                {"6-Kanal Kompakt": 6, "10-Kanal Move": 10,
                 "19-Kanal 4×Move + RGBW": 19, "32-Kanal 4×Move + Makro": 32,
                 "56-Kanal Voll (pro Kopf RGBW)": 56},
            )

    def test_compact_modes_have_no_duplicate_attribute(self):
        """6/10-Kanal sind Single-Head-Modi (kein Kopf-Attribut-Repeat) — kein
        Attribut darf sich wiederholen, sonst deutet die Mehrkopf-Konvention es
        faelschlich als zweiten Kopf (ENG-03/07/09-Falle). Show-Speed und Farb-
        Speed sind darum bewusst 'speed' vs. 'effect_speed'."""
        with Session(self._eng) as s:
            p = _load(s, "HYDRA4000")
            for mode_name in ("6-Kanal Kompakt", "10-Kanal Move"):
                a = _attrs(_mode(p, mode_name))
                self.assertEqual(len(a), len(set(a)),
                                 f"{mode_name}: doppeltes Attribut {sorted(a)}")

    def test_56ch_per_head_rgbw_layout(self):
        """56-Kanal: 4 identische 14-Kanal-Bloecke, je Kopf mit eigenem Pan/Tilt
        (+Fine)/Speed/Dimmer/Strobe/Farbwahl/Auto/Sound/RGBW."""
        head = ["pan", "pan_fine", "tilt", "tilt_fine", "speed", "intensity",
                "shutter", "color_wheel", "macro", "effect_speed",
                "color_r", "color_g", "color_b", "color_w"]
        with Session(self._eng) as s:
            a = _attrs(_mode(_load(s, "HYDRA4000"), "56-Kanal Voll (pro Kopf RGBW)"))
        self.assertEqual(a, head * 4)
        # 4 unabhaengige Pan- UND RGBW-Banks -> mover_bar mit pro-Kopf-Farbe
        self.assertEqual(a.count("pan"), 4)
        self.assertEqual(a.count("color_r"), 4)
        self.assertEqual(a.count("color_w"), 4)

    def test_19ch_shared_color_per_head_move(self):
        # 19ch: global Dimmer/Strobe + gemeinsame RGBW, dann 4x (Pan/Tilt/Dimmer),
        # Head Speed. Nur EINE color_r-Bank -> kein Multi-Emitter (Single-MH-Render).
        with Session(self._eng) as s:
            a = _attrs(_mode(_load(s, "HYDRA4000"), "19-Kanal 4×Move + RGBW"))
        self.assertEqual(
            a,
            ["intensity", "shutter", "color_r", "color_g", "color_b", "color_w"]
            + ["pan", "tilt", "intensity"] * 4 + ["speed"])
        self.assertEqual(a.count("color_r"), 1)   # kein mover_bar
        self.assertEqual(a.count("pan"), 4)

    def test_strobe_defaults_open_all_modes(self):
        # Jeder Modus mit Strobe: Default 0 muss auf 0..10 = offen fallen.
        for mode_name in ("6-Kanal Kompakt", "10-Kanal Move",
                          "19-Kanal 4×Move + RGBW", "32-Kanal 4×Move + Makro",
                          "56-Kanal Voll (pro Kopf RGBW)"):
            self._assert_default_open("HYDRA4000", mode_name)

    def test_reset_bands_avoided_by_default(self):
        # 32ch Sound/Reset (200..209) und 56ch Auto/Reset (200..224) duerfen im
        # Default (0) NICHT getroffen werden.
        with Session(self._eng) as s:
            p = _load(s, "HYDRA4000")
            for mode_name, attr in (("32-Kanal 4×Move + Makro", "macro"),
                                     ("56-Kanal Voll (pro Kopf RGBW)", "macro")):
                ch = next(c for c in _channels(_mode(p, mode_name))
                          if c.attribute == attr)
                hit = next(r for r in ch.ranges
                           if r.range_from <= ch.default_value <= r.range_to)
                self.assertNotEqual(hit.kind, "reset", f"{mode_name}: {hit.name}")


class VarytecEventParTest(_SeededCase):
    """Varytec Event PAR IP65 4in1 — IP65-RGBW-PAR, Chart: Varytec/Thomann Manual."""

    def test_profile_class_and_modes(self):
        with Session(self._eng) as s:
            p = _load(s, "EVENTPARIP65")
            self.assertIsNotNone(p)
            self.assertEqual(p.name, "Event PAR IP65 4in1")
            self.assertEqual(p.fixture_type, "par")
            self.assertEqual(p.manufacturer.name, "Varytec")
            self.assertEqual(
                {m.name: m.channel_count for m in p.modes},
                {"4-Kanal RGBW": 4, "7-Kanal RGBW+Dimmer": 7, "9-Kanal Voll": 9},
            )

    def test_channel_charts(self):
        with Session(self._eng) as s:
            p = _load(s, "EVENTPARIP65")
            self.assertEqual(_attrs(_mode(p, "4-Kanal RGBW")),
                             ["color_r", "color_g", "color_b", "color_w"])
            # 7ch laut Manual: R, G, B, W, Master-Dimmer, Strobe, Farbprogramm
            self.assertEqual(_attrs(_mode(p, "7-Kanal RGBW+Dimmer")),
                             ["color_r", "color_g", "color_b", "color_w",
                              "intensity", "shutter", "macro"])
            # 9ch: + Programm-Speed (speed) und Sound-Empf. (effect_speed, distinkt!)
            self.assertEqual(_attrs(_mode(p, "9-Kanal Voll")),
                             ["color_r", "color_g", "color_b", "color_w",
                              "intensity", "shutter", "macro", "speed", "effect_speed"])

    def test_no_repeated_attribute_single_head(self):
        """Single-Head-PAR: kein Attribut darf sich wiederholen. Nagelt fest, dass
        Programm-Speed ('speed') und Sound-Empf. ('effect_speed') NICHT beide auf
        dasselbe Attribut fallen (sonst deduplizierte der Programmer sie zu EINEM
        Regler — EURON10-Falle)."""
        with Session(self._eng) as s:
            p = _load(s, "EVENTPARIP65")
            for m in p.modes:
                a = _attrs(m)
                self.assertEqual(len(a), len(set(a)),
                                 f"{m.name}: doppeltes Attribut {sorted(a)}")

    def test_strobe_default_open(self):
        for mode_name in ("7-Kanal RGBW+Dimmer", "9-Kanal Voll"):
            self._assert_default_open("EVENTPARIP65", mode_name)


class CatalogRound3RoutingTest(_SeededCase):
    """Die ECHTE _viz_model_for-Entscheidung ueber die geseedeten Profil-Kanaele:
    Nur der 56-Kanal-Hydrabeam-Modus (>=2 color_r-Banks + >=2 pan) -> 'mover_bar';
    die uebrigen Modi fallen auf den fixture_type ('moving_head' bzw. 'par')."""

    def _model_for(self, short, mode_name, fixture_type):
        with Session(self._eng) as s:
            chans = [SimpleNamespace(attribute=c.attribute)
                     for c in _channels(_mode(_load(s, short), mode_name))]
        import src.core.app_state as AS
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        saved = AS.get_channels_for_patched
        AS.get_channels_for_patched = lambda f: chans
        try:
            return VisualizerBridge._viz_model_for(
                SimpleNamespace(), SimpleNamespace(fixture_type=fixture_type))
        finally:
            AS.get_channels_for_patched = saved

    def test_hydrabeam_56ch_routes_to_mover_bar(self):
        self.assertEqual(
            self._model_for("HYDRA4000", "56-Kanal Voll (pro Kopf RGBW)",
                            "moving_head"), "mover_bar")

    def test_hydrabeam_shared_color_modes_stay_single_head(self):
        # 19/32ch: 4x pan, aber nur 1 RGBW-Bank -> kein Multi-Emitter -> Einzel-MH.
        for mode_name in ("19-Kanal 4×Move + RGBW", "32-Kanal 4×Move + Makro",
                          "6-Kanal Kompakt", "10-Kanal Move"):
            self.assertEqual(
                self._model_for("HYDRA4000", mode_name, "moving_head"),
                "moving_head", mode_name)

    def test_varytec_par_routes_to_par(self):
        for mode_name in ("4-Kanal RGBW", "7-Kanal RGBW+Dimmer", "9-Kanal Voll"):
            self.assertEqual(
                self._model_for("EVENTPARIP65", mode_name, "par"), "par", mode_name)


class CatalogRound3PayloadTest(_SeededCase):
    """Der Multi-Head-Payload des 56-Kanal-Hydrabeam: 4 Koepfe, pro-Kopf-Weiss
    wird in die Kopf-Farbe eingerechnet (heads[i].r = min(255, r+w))."""

    def test_56ch_per_head_white_folds_into_head_color(self):
        from src.core.app_state import channel_occurrence_keys
        from src.ui.visualizer.visualizer_service import (
            _build_fixture_payload, _multihead_count,
        )
        with Session(self._eng) as s:
            chans = [SimpleNamespace(attribute=c.attribute) for c in
                     _channels(_mode(_load(s, "HYDRA4000"),
                                     "56-Kanal Voll (pro Kopf RGBW)"))]
        keys = [k for _, k in channel_occurrence_keys(chans)]
        vals = {k: 0 for k in keys}
        vals["intensity"] = 255
        vals["color_r#1"] = 200   # Kopf 2 (Index 1) rot
        vals["color_w#1"] = 100   # + Weiss
        payload = _build_fixture_payload(SimpleNamespace(fid=1), vals)
        self.assertEqual(_multihead_count(vals), 4)
        h1 = payload["heads"][1]
        self.assertEqual(h1["r"], 255)   # 200 + 100 (Weiss), geklemmt
        self.assertEqual(h1["g"], 100)   # 0 + 100 Weiss
        self.assertEqual(h1["b"], 100)
        # Kopf 0/2/3 bleiben unabhaengig aus
        self.assertEqual(payload["heads"][0]["r"], 0)
        self.assertEqual(payload["heads"][2]["r"], 0)


class EnsureBuiltinsRound3Test(unittest.TestCase):
    """Nachruesten bei bereits befuellter (aelterer) DB ist idempotent —
    keine Duplikate, Profil-IDs bleiben stabil."""

    _SHORTS = ("HYDRA4000", "EVENTPARIP65")

    def setUp(self):
        self._FDB, self._eng, self._saved = _temp_seeded_engine()

    def tearDown(self):
        self._FDB._engine = self._saved

    def test_backfill_is_idempotent(self):
        from src.core.database.fixture_db import ensure_builtins
        from src.core.database.models import FixtureProfile
        with Session(self._eng) as s:
            for short in self._SHORTS:
                s.delete(_load(s, short))
            s.commit()

        ensure_builtins()
        ensure_builtins()

        with Session(self._eng) as s:
            for short, n_modes in (("HYDRA4000", 5), ("EVENTPARIP65", 3)):
                rows = s.execute(
                    select(FixtureProfile)
                    .where(FixtureProfile.short_name == short)
                ).scalars().all()
                self.assertEqual(len(rows), 1, short)
                self.assertEqual(len(_load(s, short).modes), n_modes, short)


if __name__ == "__main__":
    unittest.main()
