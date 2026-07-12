"""ENG-11: Sweep über den Multi-Head-`attr#N`-Pfad (Erzeuger/Verbraucher).

Das `#N`-Suffix (`key = attr if head==0 else f"{attr}#{head}"`) wird an >8 Stellen
unabhängig erzeugt/geparst (app_state set/get/paint, mapped_channel, efx, attr_groups,
occurrence-keys) und hat schon mehrere echte Bugs geliefert. Dieser Sweep sichert die
Kern-Invarianten an EINEM Mehrkopf-Fixture (SPIDER14: color_r/g/b/w DOPPELT — head=0
schreibt Bank 1, head=1 → `color_r#1` Bank 2):

  1. Kopf-Werte sind unabhängig (set→get→DMX pro Kopf).
  2. head=0 spiegelt auf Bank 2, solange head=1 nicht gesetzt ist.
  3. `#N`-Keys überleben save→load unverändert.
  4. Kein Phantom-Kopf: ein head jenseits der vorhandenen Bänke schreibt in KEINEN
     echten DMX-Kanal und verfälscht die vorhandenen Köpfe nicht.
  5. Pro-Kopf-Klassifizierung/Label trägt das `(#head)`-Suffix.
"""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.show.show_file import reset_show, save_show, load_show


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one())


class MultiHeadSweepTest(unittest.TestCase):
    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()
        self.state.add_fixture(PatchedFixture(
            fid=1, label="Spider", fixture_profile_id=_pid("SPIDER14"), mode_name="14-Kanal",
            universe=1, address=1, channel_count=14, manufacturer_name="U King",
            fixture_name="Spider 14ch", fixture_type="moving_head"), undoable=False)
        self.state._rebuild_render_plan()
        u = self.state.universes.get(1)
        if u is None:
            u = self.state.output_manager.add_universe(1)
            self.state.universes[1] = u
        self.u = self.state.universes[1]

    def tearDown(self):
        reset_show()

    # 1. Kopf-Werte unabhängig
    def test_heads_independent(self):
        self.state.set_programmer_value(1, "color_r", 200, head=0)
        self.state.set_programmer_value(1, "color_r", 50, head=1)
        self.assertEqual(self.u.get_channel(6), 200)     # Bank 1
        self.assertEqual(self.u.get_channel(10), 50)     # Bank 2
        self.assertEqual(self.state.get_programmer_value(1, "color_r", head=0), 200)
        self.assertEqual(self.state.get_programmer_value(1, "color_r", head=1), 50)

    # 2. head=0 spiegelt Bank 2, solange head=1 fehlt
    def test_head0_mirrors_bank2(self):
        self.state.set_programmer_value(1, "color_g", 170, head=0)
        self.assertEqual(self.u.get_channel(7), 170)     # Bank 1 color_g
        self.assertEqual(self.u.get_channel(11), 170)    # Bank 2 color_g spiegelt

    # 3. `#N`-Keys überleben save→load
    def test_hash_keys_survive_save_load(self):
        self.state.set_programmer_value(1, "color_r", 210, head=0)
        self.state.set_programmer_value(1, "color_r", 40, head=1)
        self.state.set_programmer_value(1, "color_b", 90, head=1)
        tmp = os.path.join(tempfile.gettempdir(), "eng11_multihead.lshow")
        try:
            save_show(tmp)
            reset_show()
            ok, _msg = load_show(tmp)
            self.assertTrue(ok)
            st = get_state()
            self.assertEqual(st.get_programmer_value(1, "color_r", head=0), 210)
            self.assertEqual(st.get_programmer_value(1, "color_r", head=1), 40)
            self.assertEqual(st.get_programmer_value(1, "color_b", head=1), 90)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    # 4. Kein Phantom-Kopf jenseits der vorhandenen Bänke
    def test_no_phantom_head(self):
        self.state.set_programmer_value(1, "color_r", 200, head=0)
        self.state.set_programmer_value(1, "color_r", 50, head=1)
        before = [self.u.get_channel(c) for c in range(1, 15)]
        # head=5 existiert nicht (nur 2 Bänke) -> darf KEINEN Kanal schreiben.
        self.state.set_programmer_value(1, "color_r", 111, head=5)
        after = [self.u.get_channel(c) for c in range(1, 15)]
        self.assertEqual(before, after, "Phantom-Kopf head=5 hat DMX verändert")

    # 5. Pro-Kopf-Label ist distinkt und kopf-indiziert (attr_label: "#N" -> "(Kopf N+1)")
    def test_perhead_label_is_distinct_and_head_indexed(self):
        from src.core.attr_groups import attr_label
        base = attr_label("color_r")        # "Rot"
        h1 = attr_label("color_r#1")        # "Rot (Kopf 2)"
        h2 = attr_label("color_r#2")        # "Rot (Kopf 3)"
        self.assertNotEqual(base, h1)
        self.assertNotEqual(h1, h2)         # kein Off-by-one: Koepfe distinkt
        self.assertIn("Kopf", h1)


if __name__ == "__main__":
    unittest.main()
