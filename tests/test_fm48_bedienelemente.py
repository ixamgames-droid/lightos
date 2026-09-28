"""FM-48: passen die Bedienelemente zum Geraet? Zwei Befunde aus der Pruefung
in der ECHTEN App (Sandkasten, echter Bildschirm) mit dem Geraetepark des
Betreibers.

1. **Strobe-Kanal ohne Bereiche -> „Auf" = 255 = Strobe schnell.** Stage Light
   ZQ01424 (72-mal in den Shows): „CH6 total strobe from slow to fast". 575
   Shutter-Kanaele der Bibliothek haben keine Bereiche, fast alle heissen
   „Strobe". Dazu: „An"/„No Function"-Bereiche eines Shutters galten nicht als
   „offen" (U-King Speider: kein einziger Einschalt-Knopf).
2. **Doppelte Attribute an einem Einkopf-Geraet hatten keinen Regler.** Hero Spot
   90 „Gobo 2" (zweites Goborad) und „Moving Programs" fehlten ganz; 1328
   Einkopf-Modi der Bibliothek betroffen. Die Vorlage ist EIN Kanal je Attribut.

Nur eingebaute Profile (die CI hat keine importierte Bibliothek, QA-23).
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                          # noqa: E402
from sqlalchemy import select                                        # noqa: E402
from sqlalchemy.orm import Session                                   # noqa: E402

from src.core.app_state import (get_state, ist_strobe_kanal_ohne_bereiche,  # noqa: E402
                                open_value_of_channel, shutter_bereich_art)
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins  # noqa: E402
from src.core.database.models import FixtureProfile, PatchedFixture  # noqa: E402
from src.core.show.show_file import reset_show                       # noqa: E402
from src.ui.views.programmer_view import AttributeSlider, ProgrammerView  # noqa: E402
from src.ui.widgets.preset_tile import shutter_presets               # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first())


def _bereich(a, b, name, kind=""):
    return SimpleNamespace(range_from=a, range_to=b, name=name, kind=kind)


def _kanal(name, attribute="shutter", ranges=(), highlight=0):
    return SimpleNamespace(name=name, attribute=attribute, ranges=list(ranges),
                           highlight_value=highlight, default_value=0)


# ── 1. Shutter ──────────────────────────────────────────────────────────────────

class StrobeOhneBereicheTest(unittest.TestCase):

    def test_strobe_kanal_ohne_bereiche_auf_ist_kein_strobe(self):
        ch = _kanal("Strobe")
        self.assertTrue(ist_strobe_kanal_ohne_bereiche(ch))
        presets = dict(shutter_presets(ch))
        self.assertEqual(presets.get("Kein Strobe"), 0)
        self.assertNotIn(255, [v for k, v in presets.items() if "Strobe" not in k])
        self.assertEqual(open_value_of_channel(ch), 0)

    def test_echter_shutter_ohne_bereiche_bleibt_wie_bisher(self):
        """Kein Strobe im Namen: die alte Regel bleibt (nicht raten)."""
        ch = _kanal("Shutter")
        self.assertFalse(ist_strobe_kanal_ohne_bereiche(ch))
        self.assertEqual(dict(shutter_presets(ch)), {"Auf": 255, "Zu": 0})

    def test_zq01424_eingebautes_profil(self):
        """Der echte Fall: der Strobe-Kanal des ZQ01424 im Programmer."""
        _app()
        ensure_builtins()
        reset_show()
        st = get_state()
        st.add_fixture(PatchedFixture(
            fid=1, label="PAR", fixture_profile_id=_pid("ZQ01424"), mode_name="8-Kanal RGBW",
            universe=1, address=1, channel_count=8, fixture_type="par"), undoable=False)
        from src.core.app_state import get_channels_for_patched
        f = next(x for x in st.get_patched_fixtures() if x.fid == 1)
        strobe = next(c for c in get_channels_for_patched(f) if c.attribute == "shutter")
        # Unabhaengig vom Stand der Bibliothek (Installationen tragen teils eine
        # AELTERE Fassung ohne Bereiche, frisch geseedet hat sie 0–9 offen): der
        # Einschalt-Wert ist nie „Strobe schnell".
        self.assertLessEqual(open_value_of_channel(strobe), 9)
        auf = [v for k, v in shutter_presets(strobe)
               if not k.lower().startswith("strobe") and "zu" != k.lower()]
        self.assertTrue(auf)
        self.assertTrue(all(v <= 9 or v >= 251 for v in auf), auf)


class ShutterBereichArtTest(unittest.TestCase):

    def test_an_und_no_function_gelten_als_offen(self):
        for name in ("An", "No Function", "no strobe", "Licht an"):
            with self.subTest(name=name):
                self.assertEqual(shutter_bereich_art(_bereich(0, 7, name)), "open")

    def test_gespeicherte_art_gewinnt(self):
        self.assertEqual(shutter_bereich_art(_bereich(0, 7, "An", "closed")), "closed")

    def test_unbekanntes_bleibt_unbekannt(self):
        self.assertEqual(shutter_bereich_art(_bereich(240, 247, "Effects")), "")

    def test_speider_bekommt_einen_einschalt_wert(self):
        """U-King Speider (QLC+-Import): nur „An"-Bereiche ohne Art — vorher kein
        „Auf" und open_value fiel auf den Hervorhebungswert."""
        ch = _kanal("Shutter", ranges=[_bereich(8, 15, "An"), _bereich(16, 131, "Strobe", "strobe"),
                                       _bereich(132, 139, "An")])
        self.assertEqual(open_value_of_channel(ch), 11)
        labels = [k for k, _v in shutter_presets(ch)]
        self.assertIn("Auf", labels)

    def test_open_value_liest_no_function_nur_beim_shutter(self):
        """Auf einem Gobo-Kanal heisst „No Function" NICHT offen."""
        gobo = _kanal("Gobo", attribute="gobo_wheel", ranges=[_bereich(0, 7, "No Function")],
                      highlight=200)
        self.assertEqual(open_value_of_channel(gobo), 200)


class ShutterKachelnTest(unittest.TestCase):

    def test_gleich_benannte_bereiche_nur_einmal(self):
        """Spider-Profile: fuenfmal „Offen" -> EIN Knopf."""
        _app()
        from src.ui.widgets.preset_tile import PresetTile, ShutterQuickBar
        ch = _kanal("Shutter/Strobe", ranges=[
            _bereich(0, 7, "Geschlossen", "closed"), _bereich(8, 15, "Offen", "open"),
            _bereich(16, 131, "Strobe", "strobe"), _bereich(132, 139, "Offen", "open"),
            _bereich(182, 189, "Offen", "open")])
        bar = ShutterQuickBar(ch, [], get_state())
        self.addCleanup(bar.deleteLater)
        from PySide6.QtWidgets import QLabel
        namen = [t.findChild(QLabel).text() for t in bar.findChildren(PresetTile)]
        self.assertEqual(namen.count("Offen"), 1, namen)
        self.assertEqual(namen.count("Geschlossen"), 1, namen)

    def test_strobe_ohne_bereiche_zeigt_kein_strobe(self):
        _app()
        from src.ui.widgets.preset_tile import PresetTile, ShutterQuickBar
        bar = ShutterQuickBar(_kanal("Strobe"), [], get_state())
        self.addCleanup(bar.deleteLater)
        werte = sorted(t._payload for t in bar.findChildren(PresetTile))
        self.assertIn(0, werte)
        self.assertNotIn(255, werte)


# ── 2. Doppelte Attribute ──────────────────────────────────────────────────────

class DoppelteAttributeTest(unittest.TestCase):

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()

    def _patch(self, fid, short, mode, n, typ, addr):
        self.state.add_fixture(PatchedFixture(
            fid=fid, label=short, fixture_profile_id=_pid(short), mode_name=mode,
            universe=1, address=addr, channel_count=n, fixture_type=typ), undoable=False)

    def _regler(self, fids, reiter):
        v = ProgrammerView()
        self.addCleanup(v.deleteLater)
        self.state.set_selected_fids(list(fids))
        _app().processEvents()
        tabs = v._main_tabs
        out = []
        for i in range(tabs.count()):
            if tabs.tabText(i) == reiter:
                out += tabs.widget(i).findChildren(AttributeSlider)
        return out

    def test_dimmer_pack_hat_vier_regler(self):
        """DIM4: vier unabhaengige Dimmer — vorher EIN Regler fuer Kanal 1."""
        self._patch(1, "DIM4", "4-Kanal", 4, "dimmer", 1)
        regler = [s for s in self._regler([1], "Intensity") if s._channel.attribute == "intensity"]
        self.assertEqual(len(regler), 4, [s._display_name or s._channel.name for s in regler])
        self.assertEqual(sorted(s._head if s._head is not None else 0 for s in regler), [0, 1, 2, 3])

    def test_dritter_dimmer_trifft_dmx_kanal_3(self):
        self._patch(1, "DIM4", "4-Kanal", 4, "dimmer", 1)
        regler = [s for s in self._regler([1], "Intensity") if s._channel.attribute == "intensity"]
        dritter = next(s for s in regler if s._head == 2)
        dritter._slider.setValue(200)
        _app().processEvents()
        self.assertEqual(self.state.get_programmer_value(1, "intensity", head=2), 200)
        self.assertIn(self.state.get_programmer_value(1, "intensity"), (None, 0))
        from src.core.app_state import get_channels_for_patched
        from src.core.dmx.universe import Universe
        f = next(x for x in self.state.get_patched_fixtures() if x.fid == 1)
        uni = Universe(1)
        self.state._apply_fixture_map({1: uni}, {1: dict(self.state.programmer.get(1, {}))})
        self.assertEqual([uni.get_channel(a) for a in (1, 2, 3, 4)], [0, 0, 200, 0])

    def test_mehrkopf_geraet_bekommt_keine_extra_regler(self):
        """HYDRA4000 (vier Bewegungskoepfe): die Vorkommen SIND Koepfe und laufen
        ueber die Kopf-Auswahl — keine zusaetzlichen Regler."""
        self._patch(1, "HYDRA4000", "19-Kanal", 19, "moving_head", 1)
        for reiter in ("Intensity", "Position", "Weitere"):
            regler = self._regler([1], reiter)
            koepfe = [s for s in regler if s._head not in (None, 0)]
            with self.subTest(reiter=reiter):
                self.assertEqual(koepfe, [])


# ── 3. Programm-/Makrokanaele als Kacheln ──────────────────────────────────────

class ProgrammKachelnTest(unittest.TestCase):
    """Vorher nur ein nackter Regler — man sah nicht, dass 11–32 „7 Farben" heisst."""

    def _bar(self, ranges, fixtures=()):
        _app()
        from src.ui.widgets.preset_tile import ProgrammQuickBar
        ch = _kanal("Farbmakro", attribute="macro", ranges=ranges)
        st = SimpleNamespace(werte=[], set_programmer_value=lambda fid, a, v, **k:
                             st.werte.append((fid, a, v)))
        bar = ProgrammQuickBar(ch, list(fixtures), st)
        self.addCleanup(bar.deleteLater)
        return bar, st

    def _kacheln(self, bar):
        from PySide6.QtWidgets import QLabel
        from src.ui.widgets.preset_tile import PresetTile
        return [(t.findChild(QLabel).text(), t._payload) for t in bar.findChildren(PresetTile)]

    def test_aus_vorn_gleiche_namen_einmal(self):
        bar, _st = self._bar([_bereich(11, 32, "7-Farben-Wechsel"), _bereich(0, 10, "Without function"),
                              _bereich(201, 255, "Sound"), _bereich(33, 50, "7-Farben-Wechsel")])
        self.assertEqual(self._kacheln(bar), [("Aus", 5), ("7-Farben-Wechsel", 21), ("Sound", 228)])

    def test_klick_schreibt_den_bereichswert(self):
        f = SimpleNamespace(fid=7)
        bar, st = self._bar([_bereich(0, 10, "No function"), _bereich(201, 255, "Sound")], [f])
        bar._on_tile_clicked(228)
        self.assertEqual(st.werte, [(7, "macro", 228)])

    def test_im_programmer_unter_weitere(self):
        """Echter Programmer, eingebauter ZQ01424: die „Funktion" hat Kacheln."""
        _app()
        ensure_builtins()
        reset_show()
        st = get_state()
        st.add_fixture(PatchedFixture(
            fid=1, label="PAR", fixture_profile_id=_pid("ZQ01424"), mode_name="8-Kanal RGBW",
            universe=1, address=1, channel_count=8, fixture_type="par"), undoable=False)
        v = ProgrammerView()
        self.addCleanup(v.deleteLater)
        st.set_selected_fids([1])
        _app().processEvents()
        from src.ui.widgets.preset_tile import ProgrammQuickBar
        tabs = v._main_tabs
        bars = [b for i in range(tabs.count()) if tabs.tabText(i) == "Weitere"
                for b in tabs.widget(i).findChildren(ProgrammQuickBar)]
        self.assertEqual(len(bars), 1)
        self.assertGreaterEqual(bars[0]._anzahl, 4)


# ── 4. 2D-Ansicht: blinkt nur, was wirklich strobt ────────────────────────────

class Strobe2DTest(unittest.TestCase):
    """Bis 2026-09-28 galt in der 2D-Ansicht pauschal „Shutter > 10 = Strobe" —
    offene Geraete blinkten (in der echten App gesehen: Spider 14ch und Hero Spot
    90 dunkel/blinkend bei offenem Shutter)."""

    def _hz(self, ranges, val):
        from src.ui.views.live_view import _strobe_hz
        return _strobe_hz(_kanal("Shutter", ranges=ranges), val)

    def test_hero_spot_offen_bei_253_blinkt_nicht(self):
        r = [_bereich(0, 4, "Closed", "closed"), _bereich(5, 250, "Strobe 0-20Hz", "strobe"),
             _bereich(251, 255, "Open", "open")]
        self.assertEqual(self._hz(r, 253), 0.0)
        self.assertGreater(self._hz(r, 128), 0.0)

    def test_spider_offen_bei_11_blinkt_nicht(self):
        r = [_bereich(0, 7, "Geschlossen", "closed"), _bereich(8, 15, "Offen", "open"),
             _bereich(16, 131, "Strobe", "strobe")]
        self.assertEqual(self._hz(r, 11), 0.0)
        self.assertAlmostEqual(self._hz(r, 16), 0.5)
        self.assertAlmostEqual(self._hz(r, 131), 20.0)

    def test_speider_an_ohne_art_blinkt_nicht(self):
        self.assertEqual(self._hz([_bereich(8, 15, "An"), _bereich(16, 131, "Strobe", "strobe")], 11), 0.0)

    def test_ohne_bereiche_alte_regel(self):
        self.assertEqual(self._hz([], 5), 0.0)
        self.assertGreater(self._hz([], 200), 0.0)


if __name__ == "__main__":
    unittest.main()
