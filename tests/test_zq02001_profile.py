"""Tests fuer das korrigierte ZQ02001-Moving-Head-Profil und die neue
Gobo-/Farbrad-/Strobe-Schnellwahl (Moving-Head-Initiative 2026-06-10).

Abgedeckt:
- Kanal-Layout 9ch/11ch laut realen Geraetedaten (Strobe VOR Dimmer,
  9ch ohne Fine-Kanaele, Gobo-FX + Reset vorhanden).
- DMX-Wertebereiche von Farbrad, Gobo (statisch/Shake/Wechsel) und Strobe.
- ensure_builtins() aktualisiert ein veraltetes Profil in-place
  (Profil-ID bleibt stabil).
- preset_tile-Helfer (Slot-Farben, Slot-Infos, Speed-im-Slot).
- gobo_icons (Stil-Erkennung, Pixmaps, Cache).
- Widget-Smoke: Quick-Bars + ResetActionButton headless.
"""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select
from sqlalchemy.orm import Session


def _temp_seeded_engine():
    """Frische Temp-DB mit komplettem Seed; gibt (modul, engine, alt) zurueck."""
    from src.core.database import fixture_db as FDB
    from src.core.database.fixture_db import get_engine, _seed
    saved = FDB._engine
    eng = get_engine(tempfile.mktemp(suffix=".db"))
    with Session(eng) as s:
        _seed(s)
        s.commit()
    FDB._engine = eng
    return FDB, eng, saved


def _load_zq(s):
    from src.core.database.models import FixtureProfile, FixtureMode
    from sqlalchemy.orm import selectinload
    return s.execute(
        select(FixtureProfile)
        .options(selectinload(FixtureProfile.modes)
                 .selectinload(FixtureMode.channels))
        .where(FixtureProfile.short_name == "ZQ02001")
    ).scalars().first()


def _mode(prof, name):
    return next(m for m in prof.modes if m.name == name)


def _attrs(mode):
    return [c.attribute for c in sorted(mode.channels,
                                        key=lambda c: c.channel_number)]


class Zq02001ProfileTest(unittest.TestCase):
    """Kanal-Layout + Wertebereiche des korrigierten Profils."""

    @classmethod
    def setUpClass(cls):
        cls._FDB, cls._eng, cls._saved = _temp_seeded_engine()

    @classmethod
    def tearDownClass(cls):
        cls._FDB._engine = cls._saved

    def test_layout_11_kanal(self):
        with Session(self._eng) as s:
            prof = _load_zq(s)
            self.assertIsNotNone(prof)
            attrs = _attrs(_mode(prof, "11-Kanal"))
        self.assertEqual(attrs, [
            "pan", "pan_fine", "tilt", "tilt_fine", "color_wheel",
            "gobo_wheel", "shutter", "intensity", "speed", "gobo_fx", "reset"])

    def test_layout_9_kanal_ohne_fine(self):
        with Session(self._eng) as s:
            prof = _load_zq(s)
            attrs = _attrs(_mode(prof, "9-Kanal"))
        self.assertEqual(attrs, [
            "pan", "tilt", "color_wheel", "gobo_wheel", "shutter",
            "intensity", "speed", "gobo_fx", "reset"])

    def test_strobe_vor_dimmer(self):
        """Die eigentliche Korrektur: Strobe Ch5/Ch7, Dimmer Ch6/Ch8."""
        with Session(self._eng) as s:
            prof = _load_zq(s)
            for mode_name, sh_num, dim_num in (("9-Kanal", 5, 6),
                                               ("11-Kanal", 7, 8)):
                chans = {c.channel_number: c.attribute
                         for c in _mode(prof, mode_name).channels}
                self.assertEqual(chans[sh_num], "shutter", mode_name)
                self.assertEqual(chans[dim_num], "intensity", mode_name)

    def _ranges_of(self, s, mode_name, attr):
        prof = _load_zq(s)
        ch = next(c for c in _mode(prof, mode_name).channels
                  if c.attribute == attr)
        return sorted(ch.ranges, key=lambda r: r.range_from)

    def _slot_at(self, ranges, value):
        return next(r for r in ranges
                    if r.range_from <= value <= r.range_to)

    def test_farbrad_slots(self):
        with Session(self._eng) as s:
            rr = self._ranges_of(s, "11-Kanal", "color_wheel")
            self.assertEqual(len(rr), 15)   # offen + 7 Farben + 6 Splits + auto
            self.assertEqual(self._slot_at(rr, 4).kind, "open")
            self.assertEqual(self._slot_at(rr, 14).name, "Rot")
            self.assertEqual(self._slot_at(rr, 84).name, "Hellblau/Rosa")
            self.assertEqual(self._slot_at(rr, 135).name, "Rot/Grün")
            auto = self._slot_at(rr, 200)
            self.assertEqual(auto.kind, "rotate")
            self.assertEqual((auto.range_from, auto.range_to), (140, 255))

    def test_gobo_slots(self):
        with Session(self._eng) as s:
            rr = self._ranges_of(s, "9-Kanal", "gobo_wheel")
            self.assertEqual(self._slot_at(rr, 3).kind, "open")
            self.assertEqual(self._slot_at(rr, 11).name, "Gobo 1 (Ring, 3 Spalten)")
            g2 = self._slot_at(rr, 20)   # interpretierter Tippfehler "3-16"
            self.assertEqual((g2.range_from, g2.range_to), (16, 23))
            self.assertEqual(self._slot_at(rr, 60).name, "Gobo 7 (Zebra)")
            self.assertEqual(self._slot_at(rr, 68).kind, "open")  # 64-71 leer
            sh1 = self._slot_at(rr, 75)
            self.assertEqual(sh1.kind, "shake")
            self.assertIn("Gobo 1", sh1.name)
            sh7 = self._slot_at(rr, 125)
            self.assertEqual((sh7.range_from, sh7.range_to), (120, 127))
            rot = self._slot_at(rr, 200)
            self.assertEqual(rot.kind, "rotate")
            self.assertEqual((rot.range_from, rot.range_to), (128, 255))

    def test_strobe_ranges(self):
        with Session(self._eng) as s:
            rr = self._ranges_of(s, "11-Kanal", "shutter")
        self.assertEqual([(r.range_from, r.range_to, r.kind) for r in rr], [
            (0, 9, "open"), (10, 249, "strobe"), (250, 255, "open")])

    def test_reset_und_gobo_fx(self):
        with Session(self._eng) as s:
            rr = self._ranges_of(s, "11-Kanal", "reset")
            self.assertEqual(self._slot_at(rr, 200).kind, "reset")
            fx = self._ranges_of(s, "11-Kanal", "gobo_fx")
            self.assertEqual(len(fx), 1)   # neutral, ein Bereich


class EnsureBuiltinsUpdateTest(unittest.TestCase):
    """ensure_builtins() korrigiert ein veraltetes ZQ02001 in-place."""

    def setUp(self):
        self._FDB, self._eng, self._saved = _temp_seeded_engine()

    def tearDown(self):
        self._FDB._engine = self._saved

    def test_veraltetes_profil_wird_korrigiert(self):
        from src.core.database.fixture_db import ensure_builtins
        # Veraltetes Layout simulieren: Dimmer/Strobe zuruecktauschen wie frueher
        with Session(self._eng) as s:
            prof = _load_zq(s)
            old_id = prof.id
            mode = _mode(prof, "11-Kanal")
            for c in mode.channels:
                if c.channel_number == 7:
                    c.attribute = "intensity"
                elif c.channel_number == 8:
                    c.attribute = "shutter"
            s.commit()
        ensure_builtins()
        with Session(self._eng) as s:
            prof = _load_zq(s)
            self.assertEqual(prof.id, old_id, "Profil-ID muss stabil bleiben")
            chans = {c.channel_number: c.attribute
                     for c in _mode(prof, "11-Kanal").channels}
            self.assertEqual(chans[7], "shutter")
            self.assertEqual(chans[8], "intensity")
            # 9-Kanal-Modus wurde mit neu aufgebaut (kein pan_fine mehr)
            self.assertNotIn("pan_fine", _attrs(_mode(prof, "9-Kanal")))

    def test_korrektes_profil_bleibt_unberuehrt(self):
        from src.core.database.fixture_db import ensure_builtins
        with Session(self._eng) as s:
            prof = _load_zq(s)
            ids_before = sorted(c.id for m in prof.modes for c in m.channels)
        ensure_builtins()
        with Session(self._eng) as s:
            prof = _load_zq(s)
            ids_after = sorted(c.id for m in prof.modes for c in m.channels)
        self.assertEqual(ids_before, ids_after,
                         "Idempotenz: korrektes Profil nicht neu aufbauen")


class _Range:
    def __init__(self, lo, hi, name="", kind=""):
        self.range_from = lo
        self.range_to = hi
        self.name = name
        self.kind = kind


class _Ch:
    def __init__(self, attr, ranges=None, default=0):
        self.attribute = attr
        self.name = attr
        self.channel_number = 1
        self.default_value = default
        self.highlight_value = 255
        self.ranges = ranges or []


class PresetTileHelpersTest(unittest.TestCase):
    def test_slot_colors_for_name(self):
        from src.ui.widgets.preset_tile import slot_colors_for_name
        self.assertEqual(len(slot_colors_for_name("Rot")), 1)
        self.assertEqual(len(slot_colors_for_name("Hellblau/Rosa")), 2)
        self.assertEqual(len(slot_colors_for_name("Weiß / Offen")), 1)
        self.assertEqual(slot_colors_for_name("Gobo 1 (Ring)"), [])
        # "Farbrotation" darf nicht als Rot erkannt werden
        self.assertEqual(slot_colors_for_name("Farbrotation"), [])
        # "Hellblau" nicht als "Blau"
        self.assertNotEqual(slot_colors_for_name("Hellblau"),
                            slot_colors_for_name("Blau"))

    def test_wheel_slot_info_und_speed(self):
        from src.ui.widgets.preset_tile import wheel_slot_info, _slot_speed_value
        ch = _Ch("gobo_wheel", [_Range(72, 79, "Gobo 1 Shake", "shake")])
        info = wheel_slot_info(ch)
        self.assertEqual(info[0]["kind"], "shake")
        self.assertEqual(info[0]["from"], 72)
        self.assertEqual(_slot_speed_value(info[0], 0), 72)
        self.assertEqual(_slot_speed_value(info[0], 100), 79)
        self.assertEqual(_slot_speed_value(info[0], 50), 76)

    def test_shutter_presets_fallback(self):
        from src.ui.widgets.preset_tile import shutter_presets
        self.assertEqual(shutter_presets(_Ch("shutter")), [("Auf", 255), ("Zu", 0)])


class GoboIconsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication([])

    def test_stil_erkennung(self):
        from src.ui.widgets import gobo_icons as gi
        cases = {
            "Gobo 1 (Ring, 3 Spalten)": "ring_slits",
            "Gobo 2 (Ovale)": "ovals",
            "Gobo 3 (Kreis aus Kreisen)": "circle_of_circles",
            "Gobo 4 (Tetris)": "tetris",
            "Gobo 5 (Punkte)": "dots",
            "Gobo 6 (Spirale)": "spiral",
            "Gobo 7 (Zebra)": "zebra",
            "Kein Gobo": "open",
            "Irgendwas": "",
        }
        for name, style in cases.items():
            with self.subTest(name=name):
                self.assertEqual(gi.gobo_style_for(name), style)

    def test_nummer_und_shake(self):
        from src.ui.widgets import gobo_icons as gi
        self.assertEqual(gi.gobo_number_for("Gobo 3 Shake"), 3)
        self.assertIsNone(gi.gobo_number_for("Kein Gobo"))
        self.assertTrue(gi.is_shake_name("Gobo 3 Shake"))
        self.assertFalse(gi.is_shake_name("Gobo 3"))

    def test_pixmaps_bauen_und_cache(self):
        from src.ui.widgets import gobo_icons as gi
        for style in gi.STYLES + ("open", ""):
            with self.subTest(style=style):
                pm = gi.gobo_pixmap(style, size=24, number=9)
                self.assertFalse(pm.isNull())
                self.assertEqual(pm.width(), 24)
        a = gi.gobo_pixmap("spiral", size=24)
        b = gi.gobo_pixmap("spiral", size=24)
        self.assertIs(a, b)
        sh = gi.gobo_pixmap_for_name("Gobo 6 Shake (Spirale)", size=24)
        self.assertFalse(sh.isNull())


class _FakeState:
    """Minimaler AppState-Ersatz: zeichnet set_programmer_value auf."""

    def __init__(self):
        self.values: dict[tuple[int, str], int] = {}

    def set_programmer_value(self, fid, attr, value):
        self.values[(fid, attr)] = int(value)

    def get_programmer_value(self, fid, attr):
        return self.values.get((fid, attr))


class _FakeFx:
    def __init__(self, fid):
        self.fid = fid


class QuickBarWidgetTest(unittest.TestCase):
    """Smoke-Tests der Quick-Bars (headless): bauen + Werte setzen."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication([])

    def _gobo_channel(self):
        return _Ch("gobo_wheel", [
            _Range(0, 7, "Kein Gobo", "open"),
            _Range(8, 15, "Gobo 1 (Ring, 3 Spalten)", "gobo"),
            _Range(16, 23, "Gobo 2 (Ovale)", "gobo"),
            _Range(72, 79, "Gobo 1 Shake", "shake"),
            _Range(128, 255, "Gobo-Wechsel langsam → schnell", "rotate"),
        ])

    def test_gobo_quickbar_shake_speed(self):
        from src.ui.widgets.preset_tile import GoboQuickBar
        st = _FakeState()
        bar = GoboQuickBar(self._gobo_channel(), [_FakeFx(1)], st)
        slot = {"label": "Gobo 1 Shake", "value": 75, "kind": "shake",
                "from": 72, "to": 79}
        bar._shake_pct = 0
        bar._on_shake_clicked(slot)
        self.assertEqual(st.values[(1, "gobo_wheel")], 72)
        bar._on_shake_speed(100)
        self.assertEqual(st.values[(1, "gobo_wheel")], 79)
        bar.deleteLater()

    def test_gobo_quickbar_fallback_ohne_kinds(self):
        from src.ui.widgets.preset_tile import GoboQuickBar
        ch = _Ch("gobo_wheel", [_Range(0, 10, "Slot A"), _Range(11, 20, "Slot B")])
        bar = GoboQuickBar(ch, [_FakeFx(1)], _FakeState())
        self.assertIsNotNone(bar)   # darf ohne kind-Daten nicht crashen
        bar.deleteLater()

    def test_shutter_quickbar_strobe_slider(self):
        from src.ui.widgets.preset_tile import ShutterQuickBar
        ch = _Ch("shutter", [
            _Range(0, 9, "Kein Strobe (offen)", "open"),
            _Range(10, 249, "Strobe langsam → schnell", "strobe"),
            _Range(250, 255, "Strobe aus (offen)", "open"),
        ])
        st = _FakeState()
        bar = ShutterQuickBar(ch, [_FakeFx(2)], st)
        bar._set_on_fixtures("shutter", 130)
        self.assertEqual(st.values[(2, "shutter")], 130)
        bar.deleteLater()

    def test_color_quickbar_mit_wheel(self):
        from src.ui.widgets.preset_tile import ColorQuickBar
        ch = _Ch("color_wheel", [
            _Range(0, 9, "Weiß / Offen", "open"),
            _Range(10, 19, "Rot", "color"),
            _Range(80, 89, "Hellblau/Rosa", "color"),
            _Range(140, 255, "Farbwechsel langsam → schnell", "rotate"),
        ])
        st = _FakeState()
        bar = ColorQuickBar([_FakeFx(3)], st, set(), color_wheel_channel=ch)
        bar._apply_payload({"color_wheel": 14})
        self.assertEqual(st.values[(3, "color_wheel")], 14)
        bar.deleteLater()

    def test_colorwheel_autobar_software_zyklus(self):
        from src.ui.widgets.preset_tile import ColorWheelAutoBar
        slots = [
            {"label": "Rot", "value": 14, "kind": "color", "from": 10, "to": 19},
            {"label": "Grün", "value": 24, "kind": "color", "from": 20, "to": 29},
            {"label": "Rot/Grün", "value": 135, "kind": "color",
             "from": 130, "to": 139},
        ]
        rotate = {"label": "Auto", "value": 197, "kind": "rotate",
                  "from": 140, "to": 255}
        st = _FakeState()
        bar = ColorWheelAutoBar("color_wheel", slots, rotate,
                                {"label": "Weiß", "value": 4, "kind": "open",
                                 "from": 0, "to": 9},
                                [_FakeFx(4)], st)
        # Hardware-Start setzt Wert im Rotate-Bereich
        bar._hw_start()
        self.assertTrue(140 <= st.values[(4, "color_wheel")] <= 255)
        # Software-Zyklus: drei Ticks durchlaufen die gewaehlten Slots
        bar._cb_from.setCurrentIndex(0)
        bar._cb_to.setCurrentIndex(1)
        seen = []
        for _ in range(3):
            bar._sw_tick()
            seen.append(st.values[(4, "color_wheel")])
        self.assertEqual(seen, [14, 24, 14])
        # "Nur Split-Farben" beschraenkt auf Splits
        bar._chk_split.setChecked(True)
        bar._sw_index = 0
        bar._sw_tick()
        self.assertEqual(st.values[(4, "color_wheel")], 135)
        # Stopp -> zurueck auf Offen
        bar._all_stop()
        self.assertEqual(st.values[(4, "color_wheel")], 4)
        bar.deleteLater()

    def test_reset_button(self):
        from src.ui.widgets.preset_tile import ResetActionButton
        ch = _Ch("reset", [
            _Range(0, 149, "Keine Funktion", ""),
            _Range(150, 255, "Reset / Rekalibrierung", "reset"),
        ])
        st = _FakeState()
        btn = ResetActionButton(ch, [_FakeFx(5)], st)
        # _trigger_reset = Pfad nach bestaetigter Sicherheitsabfrage
        btn._trigger_reset()
        self.assertEqual(st.values[(5, "reset")], 202)   # Mitte von 150-255
        self.assertFalse(btn.isEnabled())
        # Revert-Logik direkt pruefen (ohne Event-Loop — der echte Aufruf
        # laeuft ueber QTimer.singleShot nach HOLD_MS)
        btn._make_revert()()
        self.assertEqual(st.values[(5, "reset")], 0)
        self.assertTrue(btn.isEnabled())
        btn.deleteLater()


class _FakePatched:
    """PatchedFixture-Ersatz fuer den Programmer-Integrationstest."""

    def __init__(self, fid):
        self.fid = fid
        self.label = f"MH {fid}"
        self.fixture_profile_id = 1
        self.mode_name = "11-Kanal"
        self.channel_count = 11
        self.universe = 1
        self.address = 1
        self.invert_pan = False
        self.invert_tilt = False
        self.swap_pan_tilt = False


def _zq_like_channels():
    """Kanalliste wie das korrigierte ZQ02001-11ch-Profil (mit kinds)."""
    return [
        _Ch("pan"), _Ch("pan_fine"), _Ch("tilt"), _Ch("tilt_fine"),
        _Ch("color_wheel", [
            _Range(0, 9, "Weiß / Offen", "open"),
            _Range(10, 19, "Rot", "color"),
            _Range(80, 89, "Hellblau/Rosa", "color"),
            _Range(140, 255, "Farbwechsel langsam → schnell", "rotate"),
        ]),
        _Ch("gobo_wheel", [
            _Range(0, 7, "Kein Gobo", "open"),
            _Range(8, 15, "Gobo 1 (Ring, 3 Spalten)", "gobo"),
            _Range(72, 79, "Gobo 1 Shake", "shake"),
            _Range(128, 255, "Gobo-Wechsel langsam → schnell", "rotate"),
        ]),
        _Ch("shutter", [
            _Range(0, 9, "Kein Strobe (offen)", "open"),
            _Range(10, 249, "Strobe langsam → schnell", "strobe"),
            _Range(250, 255, "Strobe aus (offen)", "open"),
        ]),
        _Ch("intensity"),
        _Ch("speed"),
        _Ch("gobo_fx", [_Range(0, 255, "Gobo-Effekte / Sound", "")]),
        _Ch("reset", [_Range(150, 255, "Reset / Rekalibrierung", "reset")]),
    ]


class ProgrammerMovingHeadIntegrationTest(unittest.TestCase):
    """ProgrammerView headless mit ZQ02001-artiger Auswahl: Strobe im
    Intensity-Tab (Dimmer zuerst), Gobo-Tab sichtbar inkl. gobo_fx-Fader,
    Reset nur als Button (kein Slider)."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication([])

    def test_tabs_mit_moving_head_auswahl(self):
        import src.ui.views.programmer_view as pv_mod
        from src.ui.views.programmer_view import ProgrammerView, AttributeSlider
        from src.ui.widgets.preset_tile import (ShutterQuickBar, GoboQuickBar,
                                                ColorWheelAutoBar,
                                                ResetActionButton)
        chans = _zq_like_channels()
        for i, c in enumerate(chans, 1):
            c.channel_number = i
        orig_gcp = pv_mod.get_channels_for_patched
        pv_mod.get_channels_for_patched = lambda fx: chans
        view = ProgrammerView()
        orig_gpf = view._state.get_patched_fixtures
        fake = _FakePatched(990)
        view._state.get_patched_fixtures = lambda: [fake]
        try:
            view._selected_fids = [990]
            view._rebuild_attr_editor()

            # Gobo-Tab sichtbar
            self.assertTrue(view._main_tabs.isTabVisible(view._gobo_tab_index))

            def sliders(tab_key):
                cont = view._attr_group_tabs[tab_key]
                return [s._channel.attribute
                        for s in cont.findChildren(AttributeSlider)]

            inten = sliders("Intensity")
            self.assertIn("intensity", inten)
            self.assertIn("shutter", inten)
            self.assertLess(inten.index("intensity"), inten.index("shutter"),
                            "Dimmer muss vor dem Strobe stehen")
            self.assertEqual(
                len(view._attr_group_tabs["Intensity"]
                    .findChildren(ShutterQuickBar)), 1)

            self.assertIn("gobo_fx", sliders("Gobo"))
            self.assertEqual(
                len(view._attr_group_tabs["Gobo"].findChildren(GoboQuickBar)), 1)

            self.assertEqual(
                len(view._attr_group_tabs["Color"]
                    .findChildren(ColorWheelAutoBar)), 1)

            self.assertNotIn("reset", sliders("Weitere"))
            self.assertEqual(
                len(view._attr_group_tabs["Weitere"]
                    .findChildren(ResetActionButton)), 1)
        finally:
            pv_mod.get_channels_for_patched = orig_gcp
            view._state.get_patched_fixtures = orig_gpf
            try:
                view._state.unsubscribe(view._on_state_change)
            except Exception:
                pass
            view.deleteLater()


if __name__ == "__main__":
    unittest.main()
