"""FM-13 Slice 2 — benannte REALE Pixel-Panels als Builtins.

Bis Slice 1 gab es nur das generische ``MATRIXPANEL``. Hier kommen zwei am Markt
verbreitete Geraete dazu:

- **ADJ Dotz Matrix** (``DOTZMATRIX``) — 4x4 = 16 TRI-COB-Pixel, Modi 3/6/7/48/52ch.
  Quellen: ADJ „DOTZ MATRIX User Instructions 9/13" (Charts S. 13-19) + QLC+
  ``American-DJ-Dotz-Matrix.qxf``.
- **Stairville Pixel Panel 144 RGB** (``STAIRPP144``) — 12x12 = 144 SMD-RGB-Pixel,
  Modi 8/432ch. Quellen: Thomann/Stairville-Manual (Abschn. 6.2/6.3) + QLC+
  ``Stairville-Pixel-Panel-144-RGB.qxf``.

Die Tests nageln genau die Punkte fest, an denen ein geratenes oder vom
Schwestergeraet abgeschriebenes Chart teuer geworden waere:

1. **Pixel-Reihenfolge** ist pro Pixel R,G,B — NICHT blockweise. Faellt das um,
   zeigt das 3D-Panel Farbstreifen statt Pixeln.
2. **Makro-Baender != Dotz TPar** (dort 240-255 „Sound Active", hier 240-247
   „Color Flow 10" + 248-255 ohne Funktion).
3. **attr#N-Falle**: kein Attribut darf sich in einem Steuerblock wiederholen,
   sonst liest die Mehrkopf-Konvention einen Kopf hinein (ENG-03/07/09).
4. **nHeads** reist durch den ECHTEN ``_fixture_to_dict``-Pfad (Slice-1-Review-HIGH).
"""
import os
import tempfile
import unittest
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from _fixture_quelle import frische_library     # FIXTEST-FRESH

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


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


def _chans(mode):
    return sorted(mode.channels, key=lambda c: c.channel_number)


def _attrs(mode):
    return [c.attribute for c in _chans(mode)]


class _SeededCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._eng = frische_library(cls)


# ── ADJ Dotz Matrix ─────────────────────────────────────────────────────────

class DotzMatrixProfileTest(_SeededCase):
    def test_profile_identity_and_modes(self):
        with Session(self._eng) as s:
            p = _load(s, "DOTZMATRIX")
            self.assertIsNotNone(p, "DOTZMATRIX fehlt in der Library")
            self.assertEqual(p.name, "Dotz Matrix")
            self.assertEqual(p.fixture_type, "matrix")
            self.assertEqual(p.manufacturer.name, "ADJ")
            self.assertEqual(p.power_w, 480)          # 16 x 30 W TRI-COB
            self.assertEqual(
                {m.name: m.channel_count for m in p.modes},
                {"3-Kanal RGB": 3,
                 "6-Kanal RGB + Dimmer": 6,
                 "7-Kanal RGB Voll": 7,
                 "48-Kanal 16 Pixel RGB": 48,
                 "52-Kanal 16 Pixel RGB Voll": 52},
                "Modus-Satz weicht vom ADJ-Manual ab (3/6/7/48/52)")

    def test_pixel_order_is_interleaved_rgb(self):
        """Manual S. 16-17: RED 1, GREEN 1, BLUE 1, RED 2, … BLUE 16.
        NICHT alle Rot, dann alle Gruen (dann faerbte das 3D Streifen)."""
        with Session(self._eng) as s:
            attrs = _attrs(_mode(_load(s, "DOTZMATRIX"), "48-Kanal 16 Pixel RGB"))
        self.assertEqual(attrs, ["color_r", "color_g", "color_b"] * 16)

    def test_52ch_appends_controls_after_the_pixels(self):
        """Manual S. 18-19: 49 Makros, 50 Master Dimmer/Programm-Speed,
        51 Strobing, 52 Dimmerkurve — in dieser Reihenfolge, NACH den Pixeln."""
        with Session(self._eng) as s:
            attrs = _attrs(_mode(_load(s, "DOTZMATRIX"),
                                 "52-Kanal 16 Pixel RGB Voll"))
        self.assertEqual(attrs[:48], ["color_r", "color_g", "color_b"] * 16)
        self.assertEqual(attrs[48:], ["color_wheel", "intensity", "shutter", "raw"])

    def test_macro_bands_differ_from_dotz_tpar(self):
        """★ Der Fund dieser Runde: das Schwestergeraet Dotz TPar endet auf
        „Sound Active" (240-255). Die Matrix hat dort Color Flow 10 + ein
        Ohne-Funktion-Band. Abschreiben haette ein falsches Band erzeugt."""
        with Session(self._eng) as s:
            ch = _chans(_mode(_load(s, "DOTZMATRIX"), "7-Kanal RGB Voll"))[3]
            bands = {(r.range_from, r.range_to): r.name for r in ch.ranges}
        self.assertEqual(ch.attribute, "color_wheel")
        self.assertEqual(bands[(240, 247)], "Color Flow 10")
        self.assertEqual(bands[(248, 255)], "Ohne Funktion")
        self.assertNotIn("Sound Active", bands.values())
        self.assertEqual(bands[(0, 15)], "Manuelle RGB-Steuerung")

    def test_dim_curve_bands_match_manual(self):
        with Session(self._eng) as s:
            ch = _chans(_mode(_load(s, "DOTZMATRIX"), "7-Kanal RGB Voll"))[6]
            bands = {(r.range_from, r.range_to): r.name for r in ch.ranges}
        self.assertEqual(ch.attribute, "raw")
        self.assertEqual(bands[(0, 41)], "Standard")
        self.assertEqual(bands[(85, 127)], "TV")
        self.assertEqual(bands[(214, 255)], "Geraete-Einstellung")

    def test_safety_defaults(self):
        with Session(self._eng) as s:
            chans = _chans(_mode(_load(s, "DOTZMATRIX"),
                                 "52-Kanal 16 Pixel RGB Voll"))
        by_attr = {c.attribute: c for c in chans[48:]}
        # Strobe: Default 0 und 0 traegt ein 'open'-Band (kein Blitz beim Patchen).
        strobe = by_attr["shutter"]
        self.assertEqual(strobe.default_value, 0)
        opens = [r for r in strobe.ranges if r.range_from <= 0 <= r.range_to]
        self.assertTrue(opens and opens[0].kind == "open",
                        "Strobe-Default 0 liegt nicht in einem 'open'-Band")
        # Makros: Default 0 = manuelle RGB-Steuerung (kein Auto-Programm).
        self.assertEqual(by_attr["color_wheel"].default_value, 0)
        # Master voll: Pixel sind per Default schwarz -> nichts blendet, aber eine
        # gesetzte Pixelfarbe ist sofort sichtbar (MATRIXPANEL-Konvention).
        self.assertEqual(by_attr["intensity"].default_value, 255)
        # Pixel selbst aus.
        self.assertTrue(all(c.default_value == 0 for c in chans[:48]))

    def test_no_repeated_attribute_in_control_block(self):
        """attr#N-Falle: wiederholte Nicht-Farb-Attribute wuerden als Koepfe
        gelesen und der Programmer dedupliziert sie zu EINEM Regler."""
        with Session(self._eng) as s:
            p = _load(s, "DOTZMATRIX")
            for mode_name in ("6-Kanal RGB + Dimmer", "7-Kanal RGB Voll"):
                attrs = _attrs(_mode(p, mode_name))
                self.assertEqual(len(attrs), len(set(attrs)),
                                 f"{mode_name}: Attribut doppelt -> attr#N-Kopf")


# ── Stairville Pixel Panel 144 RGB ──────────────────────────────────────────

class StairvillePixelPanel144Test(_SeededCase):
    def test_profile_identity_and_modes(self):
        with Session(self._eng) as s:
            p = _load(s, "STAIRPP144")
            self.assertIsNotNone(p, "STAIRPP144 fehlt in der Library")
            self.assertEqual(p.name, "Pixel Panel 144 RGB")
            self.assertEqual(p.fixture_type, "matrix")
            self.assertEqual(p.manufacturer.name, "Stairville")
            self.assertEqual(p.power_w, 65)
            self.assertEqual(
                {m.name: m.channel_count for m in p.modes},
                {"8-Kanal Panel gesamt": 8, "432-Kanal 144 Pixel RGB": 432},
                "Modus-Satz weicht vom Manual ab (8 / 432)")

    def test_432_mode_is_pure_interleaved_pixels(self):
        """Manual Abschn. 6.3: Kanal 1-3 = R/G/B LED 1 … 430-432 = R/G/B LED 144.
        Bewusst OHNE Master-Dimmer — den bietet das Geraet in diesem Modus nicht."""
        with Session(self._eng) as s:
            m = _mode(_load(s, "STAIRPP144"), "432-Kanal 144 Pixel RGB")
            attrs = _attrs(m)
        self.assertEqual(attrs, ["color_r", "color_g", "color_b"] * 144)
        self.assertNotIn("intensity", attrs)

    def test_8ch_mode_matches_manual_order(self):
        """Manual Abschn. 6.2: 1 Dimmer, 2 Strobe, 3-5 RGB, 6/7 Show-Programme,
        8 Programm-Speed. Kanal 7 ist 'raw' statt eines zweiten 'macro'."""
        with Session(self._eng) as s:
            attrs = _attrs(_mode(_load(s, "STAIRPP144"), "8-Kanal Panel gesamt"))
        self.assertEqual(attrs, ["intensity", "shutter", "color_r", "color_g",
                                 "color_b", "macro", "raw", "speed"])
        self.assertEqual(len(attrs), len(set(attrs)), "Attribut doppelt -> attr#N-Kopf")

    def test_program_bands(self):
        with Session(self._eng) as s:
            chans = _chans(_mode(_load(s, "STAIRPP144"), "8-Kanal Panel gesamt"))
        b6 = {(r.range_from, r.range_to): r.name for r in chans[5].ranges}
        b7 = {(r.range_from, r.range_to): r.name for r in chans[6].ranges}
        self.assertEqual(b6[(0, 15)], "Ohne Funktion")
        self.assertEqual(b6[(16, 31)], "Show-Programm 01")
        self.assertEqual(b6[(240, 255)], "Show-Programm 15")
        self.assertEqual(b7[(16, 31)], "Show-Programm 16")
        self.assertEqual(b7[(224, 239)], "Show-Programm 29")
        self.assertEqual(b7[(240, 255)], "Show-Programm-Mix")

    def test_safety_defaults(self):
        with Session(self._eng) as s:
            chans = _chans(_mode(_load(s, "STAIRPP144"), "8-Kanal Panel gesamt"))
        self.assertEqual(chans[0].default_value, 255)   # Dimmer voll
        self.assertEqual(chans[1].default_value, 0)     # Strobe aus
        opens = [r for r in chans[1].ranges if r.range_from <= 0 <= r.range_to]
        self.assertTrue(opens and opens[0].kind == "open")
        self.assertTrue(all(c.default_value == 0 for c in chans[2:5]))  # RGB aus
        self.assertEqual(chans[5].default_value, 0)     # kein Auto-Programm


# ── Routing: beide Panels muessen als 'matrix' mit echter Pixelzahl reisen ───

class RealPanelRoutingTest(_SeededCase):
    """Slice-1-Review-HIGH als Regression fuer die neuen Geraete: kommt nHeads
    nicht durch den ECHTEN _fixture_to_dict-Pfad, baut buildMatrixPanel stumm
    ein 4x4 und die Pixel jenseits von 16 fallen weg (beim 144er waeren das 128)."""

    def _dict_for(self, short, mode_name):
        import types
        import src.core.app_state as AS
        import src.ui.visualizer.visualizer_window as VW
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        with Session(self._eng) as s:
            chans = [SimpleNamespace(attribute=c.attribute)
                     for c in _chans(_mode(_load(s, short), mode_name))]
        fake_state = SimpleNamespace(visualizer_positions={}, visualizer_rotations={},
                                     visualizer_docks={})
        fake_self = SimpleNamespace(_state=fake_state)
        fake_self._viz_model_for = types.MethodType(
            VisualizerBridge._viz_model_for, fake_self)
        fake_f = SimpleNamespace(fid=1, label="P", fixture_type="matrix")
        saved_as, saved_vw = AS.get_channels_for_patched, VW.get_channels_for_patched
        AS.get_channels_for_patched = lambda f: chans
        VW.get_channels_for_patched = lambda f: chans
        try:
            return VisualizerBridge._fixture_to_dict(fake_self, fake_f)
        finally:
            AS.get_channels_for_patched = saved_as
            VW.get_channels_for_patched = saved_vw

    def test_dotz_matrix_threads_16_pixels(self):
        d = self._dict_for("DOTZMATRIX", "52-Kanal 16 Pixel RGB Voll")
        self.assertEqual(d["model"], "matrix")
        self.assertEqual(d["nHeads"], 16)

    def test_stairville_threads_144_pixels(self):
        d = self._dict_for("STAIRPP144", "432-Kanal 144 Pixel RGB")
        self.assertEqual(d["model"], "matrix")
        self.assertEqual(d["nHeads"], 144)

    def test_narrow_modes_collapse_to_one_field(self):
        """3-Kanal-Dotz bzw. 8-Kanal-Stairville faerben das GANZE Geraet — eine
        Bank, also ein Feld. Das ist geraetetreu, kein Routing-Fehler."""
        self.assertEqual(self._dict_for("DOTZMATRIX", "3-Kanal RGB")["nHeads"], 1)
        self.assertEqual(
            self._dict_for("STAIRPP144", "8-Kanal Panel gesamt")["nHeads"], 1)

    def test_not_routed_to_par_bar(self):
        from src.core.app_state import suggest_viz_model
        attrs = ["color_r", "color_g", "color_b"] * 144
        self.assertIsNone(suggest_viz_model("matrix", attrs))
        self.assertEqual(suggest_viz_model("par", attrs), "par_bar")   # Gegenprobe


class BigModePatchTest(unittest.TestCase):
    """Der 432-Kanal-Modus ist mit Abstand der groesste der Bibliothek (bisher
    193 beim generischen 8x8-Panel, 56 bei der Hydrabeam). Deshalb explizit
    nachgewiesen, dass der Adress-Pfad damit umgeht statt still zu klemmen."""

    def setUp(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from src.core.database.fixture_db import ensure_builtins
        from src.core.show.show_file import reset_show
        from src.core.app_state import get_state
        ensure_builtins()
        reset_show()
        self.state = get_state()
        self.addCleanup(reset_show)

    def _add(self, fid, address, channel_count=432):
        from src.core.database.models import PatchedFixture
        f = PatchedFixture(fid=fid, label=f"Panel {fid}", fixture_profile_id=1,
                           mode_name="432-Kanal 144 Pixel RGB", universe=1,
                           address=address, channel_count=channel_count,
                           fixture_type="matrix")
        self.state.add_fixture(f)
        return f

    def test_432ch_fixture_patches_and_spans_to_channel_432(self):
        self._add(fid=1, address=1)
        f = next(x for x in self.state.get_patched_fixtures() if x.fid == 1)
        self.assertEqual(f.channel_count, 432)
        # Pixel 144 liegt auf 430-432 -> das Fixture endet genau auf 432.
        self.assertEqual(f.address + f.channel_count - 1, 432)

    def test_second_panel_does_not_fit_in_the_same_universe(self):
        """2 x 432 > 512: die Adressvergabe muss das melden (None), nicht still
        ueberlappen — sonst kaempfen zwei Panels um dieselben Kanaele."""
        self._add(fid=1, address=1)
        nxt = self.state.suggest_address(universe=1, channel_count=432)
        self.assertIsNone(nxt, "432er-Panel wurde trotz vollem Universum platziert")
        # Ein kleines Geraet passt dagegen noch in den Rest (433-512).
        self.assertEqual(self.state.suggest_address(universe=1, channel_count=8), 433)
        # Und die Ueberlappungs-Pruefung sieht das zweite 432er-Panel auch dann,
        # wenn jemand es von Hand auf eine kollidierende Adresse setzt.
        self.assertEqual(
            self.state.check_address_conflict(universe=1, address=100,
                                              channel_count=432), [1])


class RealPanelBackfillTest(unittest.TestCase):
    """Bestandsdatenbanken (ohne die zwei Profile) muessen sie per
    ensure_builtins nachgereicht bekommen — idempotent, ohne Duplikate."""

    def test_ensure_builtins_backfills_both(self):
        from src.core.database import fixture_db as FDB
        from src.core.database.models import FixtureProfile
        saved = FDB._engine
        eng = FDB.get_engine(tempfile.mktemp(suffix=".db"))
        FDB._engine = eng
        try:
            with Session(eng) as s:
                FDB._seed(s)
                for short in ("DOTZMATRIX", "STAIRPP144"):
                    p = s.execute(select(FixtureProfile).where(
                        FixtureProfile.short_name == short)).scalars().first()
                    s.delete(p)          # Bestands-DB von VOR dieser Runde
                s.commit()
            # ensure_builtins arbeitet auf der Modul-Engine (oben gesetzt).
            FDB.ensure_builtins()
            FDB.ensure_builtins()                # idempotent
            with Session(eng) as s:
                for short in ("DOTZMATRIX", "STAIRPP144"):
                    rows = s.execute(select(FixtureProfile).where(
                        FixtureProfile.short_name == short)).scalars().all()
                    self.assertEqual(len(rows), 1, f"{short}: Backfill fehlt/doppelt")
                    self.assertEqual(rows[0].fixture_type, "matrix")
        finally:
            FDB._engine = saved


if __name__ == "__main__":
    unittest.main()
