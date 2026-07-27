"""FM-HEADLAYOUT Slice 2: die Pro-Fixture-Wahl „Mehrkopf-Programmierung"
(`PatchedFixture.head_mode`) steuert jetzt die Programmer-Farbregler.

Slice 1 hat die Option gebaut, sie wirkte aber NUR auf die automatische
Kopf-Matrix-Gruppe beim Patchen — die Programmer-UI hing weiter allein an der
GLOBALEN Voreinstellung `programmer_color_head_mode` ("sync"/"separate"). Davids
Wunsch ist „Köpfe einzeln ODER als eine Lampe steuern", also muss die Wahl am
Gerät die Regler bestimmen.

Vorrang-Regel (EINE Quelle: `core.head_mode.effective_color_head_mode`):
  * `single` -> sync     (als eine Lampe)      — schlägt die globale Wahl
  * `heads`  -> separate (Köpfe einzeln)       — schlägt die globale Wahl
  * `auto`   -> globale Voreinstellung         — Bestandsverhalten
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.head_mode import effective_color_head_mode
from src.core.show.show_file import reset_show
from src.ui.views.programmer_view import ProgrammerView, AttributeSlider


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one())


class EffectiveColorHeadModeTest(unittest.TestCase):
    """Reine Vorrang-Regel im Leaf-Modul (ohne Qt/DB)."""

    def test_single_forces_sync_even_if_global_is_separate(self):
        self.assertEqual(effective_color_head_mode("single", "separate"), "sync")

    def test_heads_forces_separate_even_if_global_is_sync(self):
        self.assertEqual(effective_color_head_mode("heads", "sync"), "separate")

    def test_auto_inherits_global(self):
        self.assertEqual(effective_color_head_mode("auto", "separate"), "separate")
        self.assertEqual(effective_color_head_mode("auto", "sync"), "sync")

    def test_garbage_falls_back_to_bestandsverhalten(self):
        # Unbekannter Fixture-Modus -> wie "auto"; unbekannte globale Wahl -> sync.
        self.assertEqual(effective_color_head_mode("Quatsch", "separate"), "separate")
        self.assertEqual(effective_color_head_mode(None, None), "sync")
        self.assertEqual(effective_color_head_mode("auto", "Quatsch"), "sync")
        # Gross-/Kleinschreibung + Leerraum wie in normalize_head_mode.
        self.assertEqual(effective_color_head_mode(" SINGLE ", "separate"), "sync")


class _SpiderHeadModeBase(unittest.TestCase):
    """SPIDER14: color_r/g/b/w DOPPELT (Bank 1 = CH6-9 Kopf 0, Bank 2 = CH10-13
    Kopf 1) — dasselbe Geraet wie in test_spider_color_head_mode.py."""

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        # Qt-GC: die Wegwerf-Hosts aus _build() MUESSEN referenziert bleiben —
        # sammelt Python das QWidget ein, loescht Qt seine Kinder (die Slider)
        # und jeder spaetere Zugriff wirft "Internal C++ object already deleted".
        self._hosts: list = []
        self._add_spider(fid=1, addr=1)
        u = self.state.universes.get(1)
        if u is None:
            u = self.state.output_manager.add_universe(1)
            self.state.universes[1] = u
        self.u = self.state.universes[1]

    def _add_spider(self, fid=1, addr=1, head_mode="auto"):
        self.state.add_fixture(PatchedFixture(
            fid=fid, label=f"Spider{fid}", fixture_profile_id=_pid("SPIDER14"),
            mode_name="14-Kanal", universe=1, address=addr, channel_count=14,
            manufacturer_name="U King", fixture_name="Spider 14ch",
            fixture_type="moving_head", head_mode=head_mode), undoable=False)
        self.state._rebuild_render_plan()

    def _fx(self, fid=1):
        return next(f for f in self.state.get_patched_fixtures() if f.fid == fid)

    def _view(self, fids=(1,), global_pref="sync"):
        v = ProgrammerView()
        v._selected_fids = list(fids)
        v._color_head_mode = global_pref
        self.addCleanup(v.deleteLater)
        return v

    def _build(self, view, fixtures):
        """Farbregler in ein Wegwerf-Layout bauen und einsammeln (Host bleibt in
        ``self._hosts`` am Leben, sonst reisst der Python-GC die Slider mit)."""
        host = QWidget()
        self._hosts.append(host)
        lay = QVBoxLayout(host)
        view._add_color_head_sliders(lay, fixtures)
        return [w for w in (lay.itemAt(i).widget() for i in range(lay.count()))
                if isinstance(w, AttributeSlider)]


class PerFixtureModeWinsTest(_SpiderHeadModeBase):

    def test_single_builds_sync_sliders_despite_global_separate(self):
        self.state.update_fixture(1, head_mode="single", undoable=False)
        v = self._view(global_pref="separate")
        sliders = self._build(v, [self._fx()])
        self.assertEqual(len(sliders), 4, "‚Als eine Lampe' gab Pro-Kopf-Regler")
        for sl in sliders:
            self.assertEqual(sl._sync_heads, 2, "Regler treibt nicht beide Köpfe")

    def test_heads_builds_per_head_sliders_despite_global_sync(self):
        self.state.update_fixture(1, head_mode="heads", undoable=False)
        v = self._view(global_pref="sync")
        sliders = self._build(v, [self._fx()])
        self.assertEqual(len(sliders), 8, "‚Köpfe einzeln' gab Synchron-Regler")
        self.assertEqual({sl._head for sl in sliders}, {0, 1})

    def test_auto_still_follows_global_preference(self):
        # Bestandsverhalten (Regressionsschutz): ohne Pro-Fixture-Wahl entscheidet
        # weiter der globale Umschalter — in BEIDE Richtungen.
        v = self._view(global_pref="separate")
        self.assertEqual(len(self._build(v, [self._fx()])), 8)
        v2 = self._view(global_pref="sync")
        self.assertEqual(len(self._build(v2, [self._fx()])), 4)

    def test_single_sync_slider_reunifies_previously_split_heads(self):
        # „Als eine Lampe" nach früherem Pro-Kopf-Programmieren: der Synchron-
        # Regler räumt die attr#N-Abweichung beim Schreiben weg -> beide Bänke
        # zeigen wieder dasselbe (sonst wirkte der Regler auf Bank 2 tot).
        self.state.set_programmer_value(1, "color_r", 30, head=1)
        self.state.update_fixture(1, head_mode="single", undoable=False)
        v = self._view(global_pref="separate")
        sliders = self._build(v, [self._fx()])
        rot = next(s for s in sliders if s._channel.attribute == "color_r")
        rot._slider.setValue(150)
        self.assertIsNone(self.state.get_programmer_value(1, "color_r", head=1))
        self.assertEqual(self.u.get_channel(6), 150)    # Bank 1
        self.assertEqual(self.u.get_channel(10), 150)   # Bank 2 folgt wieder


class GlobalSwitchRespectsPerFixtureTest(_SpiderHeadModeBase):

    def test_switch_to_sync_keeps_per_head_values_of_heads_fixture(self):
        self.state.update_fixture(1, head_mode="heads", undoable=False)
        self.state.set_programmer_value(1, "color_r", 100, head=0)
        self.state.set_programmer_value(1, "color_r", 40, head=1)
        v = self._view(global_pref="separate")
        v._set_color_head_mode("sync")
        self.assertEqual(self.state.get_programmer_value(1, "color_r", head=1), 40,
                         "globaler Umschalter hat die gewollte Pro-Kopf-Farbe "
                         "eines ‚Köpfe einzeln'-Geräts geplättet")
        self.assertEqual(self.u.get_channel(10), 40)

    def test_switch_to_sync_still_clears_per_head_values_of_auto_fixture(self):
        # Gegenprobe: für „auto" bleibt das Aufräumen wie bisher.
        self.state.set_programmer_value(1, "color_r", 100, head=0)
        self.state.set_programmer_value(1, "color_r", 40, head=1)
        v = self._view(global_pref="separate")
        v._set_color_head_mode("sync")
        self.assertIsNone(self.state.get_programmer_value(1, "color_r", head=1))
        self.assertEqual(self.u.get_channel(10), 100)


class MixedSelectionTest(_SpiderHeadModeBase):

    def setUp(self):
        super().setUp()
        self._add_spider(fid=3, addr=30)
        self.state.update_fixture(1, head_mode="heads", undoable=False)
        self.state.update_fixture(3, head_mode="single", undoable=False)

    def test_both_blocks_are_built(self):
        v = self._view(fids=(1, 3), global_pref="sync")
        sliders = self._build(v, v._selected_fixtures())
        per_head = [s for s in sliders if s._sync_heads == 0]
        sync = [s for s in sliders if s._sync_heads > 0]
        self.assertEqual(len(per_head), 8, "Pro-Kopf-Block fehlt")
        self.assertEqual(len(sync), 4, "Synchron-Block fehlt")

    def test_per_head_sliders_never_touch_the_single_fixture(self):
        # Kernfalle: „Rot 2" darf auf dem als EINE Lampe gesetzten Gerät kein
        # color_r#1 anlegen — sonst zerfällt es doch in Köpfe.
        v = self._view(fids=(1, 3), global_pref="sync")
        sliders = self._build(v, v._selected_fixtures())
        rot2 = next(s for s in sliders
                    if s._channel.attribute == "color_r" and s._sync_heads == 0
                    and s._head == 1)
        self.assertEqual([f.fid for f in rot2._fixtures], [1])
        rot2._slider.setValue(90)
        self.assertEqual(self.state.get_programmer_value(1, "color_r", head=1), 90)
        self.assertNotIn("color_r#1", self.state.programmer.get(3, {}))
        # Und der Synchron-Regler des Einzel-Lampen-Geräts treibt dessen 2 Bänke.
        rot_sync = next(s for s in sliders
                        if s._channel.attribute == "color_r" and s._sync_heads > 0)
        self.assertEqual([f.fid for f in rot_sync._fixtures], [3])
        rot_sync._slider.setValue(200)
        self.assertEqual(self.u.get_channel(35), 200)   # addr 30 + CH6 - 1
        self.assertEqual(self.u.get_channel(39), 200)   # addr 30 + CH10 - 1


class ComboGateTest(_SpiderHeadModeBase):
    """Der globale Umschalter darf nicht vorgeben zu entscheiden, wenn alle
    ausgewaehlten Mehrkopf-Geraete eine feste Pro-Fixture-Wahl haben."""

    def test_auto_fixture_keeps_switch_meaningful(self):
        v = self._view()
        self.assertTrue(v._has_auto_mode_color_head_fixture())

    def test_all_explicit_disables_switch(self):
        self.state.update_fixture(1, head_mode="single", undoable=False)
        v = self._view()
        self.assertFalse(v._has_auto_mode_color_head_fixture())

    def test_one_auto_among_explicit_keeps_switch(self):
        self._add_spider(fid=3, addr=30)
        self.state.update_fixture(1, head_mode="heads", undoable=False)
        v = self._view(fids=(1, 3))
        self.assertTrue(v._has_auto_mode_color_head_fixture())


if __name__ == "__main__":
    unittest.main()
