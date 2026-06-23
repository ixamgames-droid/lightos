"""Color-Tab Synchron/Getrennt-Umschalter fuer Mehrkopf-Farbgeraete (Spider).

Der Spider (SPIDER14) hat color_r/g/b/w DOPPELT (Bank 1 = CH6-9 = Kopf 0,
Bank 2 = CH10-13 = Kopf 1). Der Programmer-Color-Tab bietet zwei Modi:

  * "sync"     — ein Regler je Farbe treibt BEIDE Koepfe gemeinsam (und raeumt
                 etwaige "attr#N"-Abweichungen weg, damit der Flush-Fallback
                 spiegelt; so wirken auch Schnellwahl/Picker auf beide Koepfe).
  * "separate" — ein Regler je Kopf (CH6 vs CH10 usw.), unabhaengig steuerbar.

Reiner UI-Umschalter: keine Profil-/Core-Aenderung, nutzt den bestehenden
head/"attr#N"-Mechanismus aus app_state.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state, get_channels_for_patched
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.show.show_file import reset_show
from src.ui.views.programmer_view import ProgrammerView, AttributeSlider


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one())


class _SpiderBase(unittest.TestCase):
    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        self.state.add_fixture(PatchedFixture(
            fid=1, label="Spider", fixture_profile_id=_pid("SPIDER14"),
            mode_name="14-Kanal", universe=1, address=1, channel_count=14,
            manufacturer_name="U King", fixture_name="Spider 14ch",
            fixture_type="moving_head"), undoable=False)
        self.state._rebuild_render_plan()
        u = self.state.universes.get(1)
        if u is None:
            u = self.state.output_manager.add_universe(1)
            self.state.universes[1] = u
        self.u = self.state.universes[1]

    def _fx(self, fid=1):
        return next(f for f in self.state.get_patched_fixtures() if f.fid == fid)

    def _color_channel(self, attr, occurrence=0):
        chs = [c for c in get_channels_for_patched(self._fx())
               if c.attribute == attr]
        return chs[occurrence]

    def _add_par(self, fid=2, addr=20):
        """Einzelkopf-RGBW-PAR (color_r/g/b/w je EINMAL) fuer Mix-Tests."""
        self.state.add_fixture(PatchedFixture(
            fid=fid, label="PAR", fixture_profile_id=_pid("ZQ01424"),
            mode_name="8-Kanal RGBW", universe=1, address=addr, channel_count=8,
            manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
            fixture_type="par"), undoable=False)
        self.state._rebuild_render_plan()


class AttributeSliderHeadTest(_SpiderBase):
    """Schreib-Semantik der erweiterten AttributeSlider (head / sync_heads)."""

    def test_separate_head1_writes_only_bank2(self):
        ch = self._color_channel("color_r", occurrence=1)   # CH10 = Kopf 1
        sl = AttributeSlider(ch, [self._fx()], self.state, owner=None, head=1)
        sl._slider.setValue(77)
        self.assertEqual(self.state.get_programmer_value(1, "color_r", head=1), 77)
        self.assertIsNone(self.state.get_programmer_value(1, "color_r", head=0))
        self.assertEqual(self.u.get_channel(10), 77)   # Bank 2 (Bar R)
        self.assertEqual(self.u.get_channel(6), 0)     # Bank 1 unveraendert

    def test_separate_head0_writes_only_bank1(self):
        ch = self._color_channel("color_r", occurrence=0)   # CH6 = Kopf 0
        # Vorab eine Abweichung auf Kopf 1 setzen, damit kein Spiegeln passiert.
        self.state.set_programmer_value(1, "color_r", 20, head=1)
        sl = AttributeSlider(ch, [self._fx()], self.state, owner=None, head=0)
        sl._slider.setValue(140)
        self.assertEqual(self.u.get_channel(6), 140)   # Bank 1 (Bar L)
        self.assertEqual(self.u.get_channel(10), 20)   # Bank 2 behaelt eigenen Wert

    def test_sync_drives_both_and_clears_head_override(self):
        # Eine alte Pro-Kopf-Abweichung auf Bank 2 ...
        self.state.set_programmer_value(1, "color_r", 30, head=1)
        ch = self._color_channel("color_r", occurrence=0)
        sl = AttributeSlider(ch, [self._fx()], self.state, owner=None, sync_heads=2)
        sl._slider.setValue(150)
        # ... wird beim Synchron-Regeln entfernt -> beide Koepfe spiegeln 150.
        self.assertEqual(self.state.get_programmer_value(1, "color_r", head=0), 150)
        self.assertIsNone(self.state.get_programmer_value(1, "color_r", head=1))
        self.assertEqual(self.u.get_channel(6), 150)
        self.assertEqual(self.u.get_channel(10), 150)

    def test_sync_display_name_strips_head_suffix(self):
        ch = self._color_channel("color_r", occurrence=0)   # name "Rot 1"
        sl = AttributeSlider(ch, [self._fx()], self.state, owner=None,
                             sync_heads=2, display_name="Rot")
        # Der angezeigte Name ist der bereinigte (ohne Kopf-Nummer).
        self.assertEqual(sl._display_name, "Rot")


class ProgrammerColorHeadModeTest(_SpiderBase):
    """ProgrammerView-Logik: Erkennung, Umschalten, Slider-Aufbau."""

    def _view(self):
        return self._view_sel([1])

    def _view_sel(self, fids):
        v = ProgrammerView()
        v._selected_fids = list(fids)
        v._rebuild_attr_editor()
        return v

    def test_head_count_detects_spider(self):
        v = self._view()
        self.assertEqual(v._color_head_count(), 2)
        v.deleteLater()

    def test_strip_head_suffix(self):
        self.assertEqual(ProgrammerView._strip_head_suffix("Rot 1"), "Rot")
        self.assertEqual(ProgrammerView._strip_head_suffix("Weiß 2"), "Weiß")
        self.assertEqual(ProgrammerView._strip_head_suffix("Master Dimmer"),
                         "Master Dimmer")

    def test_switch_to_separate_seeds_per_head_for_independence(self):
        # Getrennt verankert den effektiven Wert PRO KOPF, damit ein Kopf>0 nicht
        # laenger Kopf 0 spiegelt (Bug: Bewegen von Regler 1 zog Regler 2 mit).
        v = self._view()
        # Sauber in Synchron starten (Prefs koennten "separate" persistiert haben
        # -> dann haette _view() Kopf 1 schon auf Default verankert).
        v._color_head_mode = "sync"
        v._normalize_color_heads_to_sync()
        self.state.set_programmer_value(1, "color_r", 100, head=0)
        self.assertIsNone(self.state.get_programmer_value(1, "color_r", head=1))
        v._set_color_head_mode("separate")
        self.assertEqual(v.color_head_mode(), "separate")
        # Kopf 1 bekommt jetzt einen EIGENEN Schluessel (= effektiver Wert 100) ...
        self.assertEqual(self.state.get_programmer_value(1, "color_r", head=1), 100)
        # ... die Ausgabe bleibt im Moment des Verankerns byte-genau gleich ...
        self.assertEqual(self.u.get_channel(6), 100)
        self.assertEqual(self.u.get_channel(10), 100)
        # ... und der Pro-Kopf-Regler ZEIGT den verankerten Wert.
        ch = self._color_channel("color_r", occurrence=1)
        sl = AttributeSlider(ch, [self._fx()], self.state, owner=None, head=1)
        self.assertEqual(sl._slider.value(), 100)
        # Kernpunkt: Bewegen von Kopf 0 zieht Kopf 1 NICHT mehr mit.
        ch0 = self._color_channel("color_r", occurrence=0)
        sl0 = AttributeSlider(ch0, [self._fx()], self.state, owner=None, head=0)
        sl0._slider.setValue(200)
        self.assertEqual(self.u.get_channel(6), 200)    # Kopf 0 neu
        self.assertEqual(self.u.get_channel(10), 100)   # Kopf 1 bleibt verankert
        v.deleteLater()

    def test_separate_head1_does_not_follow_head0_via_built_sliders(self):
        # Davids Report (frischer Spider): im Getrennt-Modus zog das Bewegen von
        # Regler 1 (Kopf 0) den Regler 2 (Kopf 1) mit, bis Kopf 1 einmal selbst
        # bewegt wurde. Mit Pro-Kopf-Seeding ist Kopf 1 ab dem ersten Zug stabil.
        v = self._view()
        v._color_head_mode = "separate"
        host = QWidget()
        lay = QVBoxLayout(host)
        v._add_color_head_sliders(lay, [self._fx()])
        sliders = [w for w in (lay.itemAt(i).widget() for i in range(lay.count()))
                   if isinstance(w, AttributeSlider)]
        r0 = next(s for s in sliders
                  if s._channel.attribute == "color_r" and s._head == 0)
        r1 = next(s for s in sliders
                  if s._channel.attribute == "color_r" and s._head == 1)
        # Kopf 1 wurde beim Aufbau auf den Default (0) verankert.
        self.assertEqual(self.state.get_programmer_value(1, "color_r", head=1), 0)
        r0._slider.setValue(180)
        self.assertEqual(self.u.get_channel(6), 180)    # Kopf 0
        self.assertEqual(self.u.get_channel(10), 0)     # Kopf 1 bleibt
        # Der Live-Refresh zieht Regler 2 nicht mehr mit.
        r1._load_current_value()
        self.assertEqual(r1._slider.value(), 0)
        v.deleteLater()

    def test_switch_to_sync_clears_head_overrides(self):
        v = self._view()
        self.state.set_programmer_value(1, "color_r", 100, head=0)
        self.state.set_programmer_value(1, "color_r", 40, head=1)
        v._color_head_mode = "separate"
        v._set_color_head_mode("sync")
        self.assertEqual(v.color_head_mode(), "sync")
        # Pro-Kopf-Abweichung weg -> Kopf 1 spiegelt wieder Kopf 0.
        self.assertIsNone(self.state.get_programmer_value(1, "color_r", head=1))
        self.assertEqual(self.u.get_channel(6), 100)
        self.assertEqual(self.u.get_channel(10), 100)
        v.deleteLater()

    def test_separate_builds_one_slider_per_head(self):
        v = self._view()
        v._color_head_mode = "separate"
        host = QWidget()
        lay = QVBoxLayout(host)
        v._add_color_head_sliders(lay, [self._fx()])
        sliders = [lay.itemAt(i).widget() for i in range(lay.count())]
        sliders = [w for w in sliders if isinstance(w, AttributeSlider)]
        # 2 Koepfe x (R,G,B,W) = 8 Regler.
        self.assertEqual(len(sliders), 8)
        v.deleteLater()

    def test_sync_builds_one_slider_per_color(self):
        v = self._view()
        v._color_head_mode = "sync"
        host = QWidget()
        lay = QVBoxLayout(host)
        v._add_color_head_sliders(lay, [self._fx()])
        sliders = [lay.itemAt(i).widget() for i in range(lay.count())]
        sliders = [w for w in sliders if isinstance(w, AttributeSlider)]
        # Nur erstes Vorkommen je Farbe -> 4 Regler (R,G,B,W).
        self.assertEqual(len(sliders), 4)
        for sl in sliders:
            self.assertEqual(sl._sync_heads, 2)
        v.deleteLater()

    def test_color_label_from_attribute(self):
        class _C:
            def __init__(self, a, n):
                self.attribute, self.name = a, n
        v = self._view()
        self.assertEqual(v._color_label(_C("color_r", "Seg.1 Rot")), "Rot")
        self.assertEqual(v._color_label(_C("color_w", "Weiß 2")), "Weiß")
        # Unbekanntes Attribut -> Fallback auf bereinigten Kanalnamen.
        self.assertEqual(v._color_label(_C("color_x", "Custom 1")), "Custom")
        v.deleteLater()

    def test_toggle_and_sliders_independent_of_selection_order(self):
        # Finding 6: PAR zuerst, Spider danach -> Umschalter + Pro-Kopf-Regler
        # muessen trotzdem erscheinen (nicht nur an selected[0] gekoppelt).
        self._add_par(fid=2, addr=20)
        v = self._view_sel([2, 1])
        self.assertEqual(v._color_head_count(), 2)
        v._color_head_mode = "separate"
        host = QWidget()
        lay = QVBoxLayout(host)
        v._add_color_head_sliders(lay, v._selected_fixtures())
        sliders = [w for w in (lay.itemAt(i).widget() for i in range(lay.count()))
                   if isinstance(w, AttributeSlider)]
        self.assertEqual(len(sliders), 8)   # Spider-Koepfe, obwohl PAR = selected[0]
        v.deleteLater()

    def test_separate_head_slider_skips_single_head_fixture(self):
        # Finding 5: in gemischter Auswahl darf "Rot 2" KEIN color_r#1 auf den
        # Einzelkopf-PAR schreiben (Owner-Filter).
        self._add_par(fid=2, addr=20)
        v = self._view_sel([1, 2])
        v._color_head_mode = "separate"
        host = QWidget()
        lay = QVBoxLayout(host)
        v._add_color_head_sliders(lay, v._selected_fixtures())
        sliders = [w for w in (lay.itemAt(i).widget() for i in range(lay.count()))
                   if isinstance(w, AttributeSlider)]
        rot2 = next(s for s in sliders
                    if s._channel.attribute == "color_r" and s._head == 1)
        self.assertEqual([f.fid for f in rot2._fixtures], [1])   # nur Spider
        rot2._slider.setValue(90)
        self.assertEqual(self.state.get_programmer_value(1, "color_r", head=1), 90)
        self.assertNotIn("color_r#1", self.state.programmer.get(2, {}))
        v.deleteLater()

    def test_mixed_selection_switch_creates_no_stray_keys(self):
        # Findings 1/4: Umschalten in gemischter Auswahl darf keine toten
        # "attr#N"-Schluessel auf dem Einzelkopf-PAR hinterlassen.
        self._add_par(fid=2, addr=20)
        v = self._view_sel([1, 2])
        # Beide Fixtures haben einen Kopf-0-Farbwert (linked).
        self.state.set_programmer_value(1, "color_r", 120, head=0)
        self.state.set_programmer_value(2, "color_r", 120, head=0)
        v._color_head_mode = "sync"
        v._set_color_head_mode("separate")   # frueher: seedete color_r#1 ueberall
        v._set_color_head_mode("sync")
        par_keys = [k for k in self.state.programmer.get(2, {}) if "#" in k]
        self.assertEqual(par_keys, [])
        v.deleteLater()

    def test_preset_recolors_all_heads_clearing_overrides(self):
        # Finding 3: ein Farb-Preset entfernt Pro-Kopf-Overrides -> faerbt BEIDE
        # Bars (nicht nur Bar L / Kopf 0).
        from src.ui.widgets.preset_tile import ColorQuickBar
        self.state.set_programmer_value(1, "color_b", 200, head=1)   # Bar R blau
        qb = ColorQuickBar([self._fx()], self.state,
                           {"color_r", "color_g", "color_b", "color_w"}, None)
        qb._apply_payload({"color_r": 255, "color_g": 0, "color_b": 0})
        self.assertIsNone(self.state.get_programmer_value(1, "color_b", head=1))
        self.assertEqual(self.u.get_channel(6), 255)    # Bar L Rot
        self.assertEqual(self.u.get_channel(10), 255)   # Bar R Rot (Fallback)
        self.assertEqual(self.u.get_channel(12), 0)     # Bar R Blau-Override weg
        qb.deleteLater()


if __name__ == "__main__":
    unittest.main()
