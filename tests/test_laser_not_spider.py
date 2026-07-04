"""Regression: ein Laser (fixture_type=='laser') ist NIE ein Spider-Multi-Emitter.

Das PARTYLASER-Builtin ("Laser Stage Lighting", 7ch) modelliert zwei rote Dioden
als zwei getrennte `color_r`-Kanaele. Ohne Gate liefert die Bank-Zaehlung in
`is_spider_fixture` >=2 -> True, und `_viz_model_for` rendert den Laser als
'spider' (Doppel-Bar) statt 'laser' (auch 2D-Icon + Patch-Spiegel-Option). Das
Gate in `is_spider_fixture` schliesst `fixture_type=='laser'` zentral aus.
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


def _partylaser_chans(eng):
    from src.core.database.models import (
        FixtureChannel, FixtureMode, FixtureProfile,
    )
    with Session(eng) as s:
        prof = s.execute(
            select(FixtureProfile)
            .options(
                selectinload(FixtureProfile.modes)
                .selectinload(FixtureMode.channels)
                .selectinload(FixtureChannel.ranges),
            )
            .where(FixtureProfile.short_name == "PARTYLASER")
        ).scalars().first()
        assert prof is not None, "PARTYLASER-Builtin fehlt"
        mode = prof.modes[0]
        return [SimpleNamespace(attribute=c.attribute) for c in mode.channels]


class LaserNotSpiderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._FDB, cls._eng, cls._saved = _temp_seeded_engine()
        cls._chans = _partylaser_chans(cls._eng)

    @classmethod
    def tearDownClass(cls):
        cls._FDB._engine = cls._saved

    def test_partylaser_really_has_two_color_r_banks(self):
        # Voraussetzung des Findings: genau die Konstellation, die die
        # Spider-Heuristik ohne Gate ausloesen wuerde (>=2 color_r).
        banks = sum(1 for c in self._chans if c.attribute == "color_r")
        self.assertGreaterEqual(banks, 2)

    def test_laser_type_is_never_spider(self):
        import src.core.app_state as A
        saved = A.get_channels_for_patched
        A.get_channels_for_patched = lambda f: self._chans
        try:
            # Laser: trotz >=2 color_r-Banken KEIN Spider -> das Gate greift
            # (ohne es zaehlt es 2 Banken und wuerde True liefern).
            self.assertFalse(
                A.is_spider_fixture(SimpleNamespace(fixture_type="laser")))
            # Kontrolle: EXAKT dieselben Kanaele, aber Nicht-Laser -> Spider.
            # Beweist, dass nur der Typ (nicht das Kanal-Layout) entscheidet.
            self.assertTrue(
                A.is_spider_fixture(SimpleNamespace(fixture_type="led_bar")))
        finally:
            A.get_channels_for_patched = saved

    def test_central_viz_model_for_falls_back_for_laser(self):
        # FM-6/7 fuehrte app_state.viz_model_for als EINZIGE Modell-Routing-Quelle
        # ein (2D-Symbol/3D/Icon/Patch-Spiegel). Sie ruft is_spider_fixture -> fuer
        # einen Laser muss sie None liefern (Aufrufer nutzt dann fixture_type=
        # 'laser'), NICHT 'spider'. Sperrt die End-to-End-Kette des Fixes.
        import src.core.app_state as A
        if not hasattr(A, "viz_model_for"):
            self.skipTest("viz_model_for (FM-6/7) nicht vorhanden")
        saved = A.get_channels_for_patched
        A.get_channels_for_patched = lambda f: self._chans
        try:
            self.assertIsNone(
                A.viz_model_for(SimpleNamespace(fixture_type="laser")))
            # Kontrolle: gleiche Kanaele als Nicht-Laser -> 'spider' (1 Pan/Motor,
            # kein Pro-Kopf-Pan) statt None. Der Typ entscheidet.
            self.assertEqual(
                A.viz_model_for(SimpleNamespace(fixture_type="led_bar")),
                "spider")
        finally:
            A.get_channels_for_patched = saved


if __name__ == "__main__":
    unittest.main()
