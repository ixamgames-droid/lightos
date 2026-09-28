"""LAS-21: „Alles Weiss" (Panik-Licht) fasst Laser und Nebel & Co. nicht an.

Gemessen am 2026-09-28 (FM-48, Geraetepark des Betreibers): ein DMX-Laser
(Ehaho L2600, 6-Kanal Simple DMX) bekam Shutter 128 = „An" plus eine Farbe, die
Nebelmaschine Eurolite N-10 ihren einzigen Kanal auf 255 = Vollgas. Nur Netzwerk-
Laser waren ausgenommen (kein DMX-Adressraum, LAS-04).
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select                                        # noqa: E402
from sqlalchemy.orm import Session                                   # noqa: E402

from src.core.all_white import ist_geraet_ohne_licht, white_map      # noqa: E402
from src.core.app_state import get_state, open_value_of_channel      # noqa: E402
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins  # noqa: E402
from src.core.database.models import FixtureProfile, PatchedFixture  # noqa: E402
from src.core.show.show_file import reset_show                       # noqa: E402


def _pid(short):
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first())


def _fx(**kw):
    base = dict(fid=1, fixture_type="par", fixture_name="", label="", manufacturer_name="")
    base.update(kw)
    return SimpleNamespace(**base)


def _ch(attr):
    return SimpleNamespace(attribute=attr, ranges=[], highlight_value=255, name=attr)


class ErkennungTest(unittest.TestCase):

    def test_typen(self):
        for typ in ("laser", "hazer", "fog"):
            with self.subTest(typ=typ):
                self.assertTrue(ist_geraet_ohne_licht(_fx(fixture_type=typ)))
        self.assertFalse(ist_geraet_ohne_licht(_fx(fixture_type="moving_head")))

    def test_laser_kanaele_auch_bei_falschem_typ(self):
        self.assertTrue(ist_geraet_ohne_licht(_fx(fixture_type="moving_head"),
                                              [_ch("pan"), _ch("laser_x")]))

    def test_name_bei_typ_other(self):
        """26 Nebel-/Haze-/Funkengeraete der Bibliothek sind nur „other"."""
        for name in ("Accu Fog 1000", "Hurricane Haze 2", "Sparkular", "Stage Flame",
                     "N-10 Nebelmaschine", "3000mW RGB Laser"):
            with self.subTest(name=name):
                self.assertTrue(ist_geraet_ohne_licht(_fx(fixture_type="other",
                                                          fixture_name=name)))

    def test_beschriftung_im_patch_zaehlt(self):
        self.assertTrue(ist_geraet_ohne_licht(_fx(fixture_type="other", label="Nebel links")))

    def test_keine_fehlgriffe(self):
        for name in ("SparkleWall", "LED Flamenco PAR", "Brauchbar LED", "Stage Light ZQ01424",
                     "Hero Spot 90"):
            with self.subTest(name=name):
                self.assertFalse(ist_geraet_ohne_licht(_fx(fixture_name=name)))


class AllesWeissTest(unittest.TestCase):
    """Mit den eingebauten Profilen und dem echten AppState."""

    def setUp(self):
        ensure_builtins()
        reset_show()
        self.st = get_state()
        self.addCleanup(self.st.set_all_white, False)
        for fid, short, mode, n, typ, addr in (
                (1, "L2600LASER", "6-Kanal (Simple DMX)", 6, "laser", 1),
                (2, "EURON10", "1-Kanal (Nebel)", 1, "hazer", 10),
                (3, "ZQ01424", "8-Kanal RGBW", 8, "par", 20)):
            self.st.add_fixture(PatchedFixture(
                fid=fid, label=short, fixture_profile_id=_pid(short), mode_name=mode,
                universe=1, address=addr, channel_count=n, fixture_type=typ), undoable=False)

    def test_laser_und_nebel_bleiben_aus_par_wird_weiss(self):
        self.assertEqual(self.st.set_all_white(True), 1)
        schicht = self.st._all_white_map
        self.assertNotIn(1, schicht, "Laser darf nicht angehen")
        self.assertNotIn(2, schicht, "Nebelmaschine darf nicht auf Vollgas")
        self.assertEqual(schicht[3]["intensity"], 255)

    def test_ohne_die_regel_waeren_sie_drin(self):
        """Positivkontrolle der Messung: die Profile WUERDEN etwas bekommen —
        sonst bewiese der Test oben nichts."""
        from src.core.app_state import get_channels_for_patched
        from src.core.all_white import white_attrs_for_fixture
        fx = {f.fid: f for f in self.st.get_patched_fixtures()}
        self.assertIn("shutter", white_attrs_for_fixture(get_channels_for_patched(fx[1]),
                                                         open_value_of_channel))
        self.assertTrue(white_attrs_for_fixture(get_channels_for_patched(fx[2]),
                                                open_value_of_channel))


if __name__ == "__main__":
    unittest.main()
