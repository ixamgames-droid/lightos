"""CDX-65 (1) — SH-LASER3W: Alt-Shows nach LAS-28 (#1211) auf die neuen
Flip-Schluessel umsetzen.

LAS-28 gab den vertikalen Flips das eigene Attribut ``laser_twist_y``. Vorher
trugen alle vier Flip-Kanaele ``laser_twist``, gespeicherte Werte zaehlten die
Vorkommen in Kanalreihenfolge:

=================  =======================  ==================
alter Schluessel   Kanal                     neuer Schluessel
=================  =======================  ==================
laser_twist        Pattern A Horizontal      laser_twist
laser_twist#1      Pattern A Vertical        laser_twist_y
laser_twist#2      Pattern B Horizontal      laser_twist#1
laser_twist#3      Pattern B Vertical        laser_twist_y#1
=================  =======================  ==================

Ohne Umsetzung stellte ``laser_twist#1`` einer Alt-Show still den
horizontalen Flip von B, ``#2``/``#3`` gingen verloren. ``load_show`` setzt die
Schluessel fuer erkannte SH-LASER3W einmal um — nicht fuer Shows mit dem
Marker ``attribut_migrationen: ["LAS-28"]``, den jedes Speichern schreibt.
"""
import json
import os
import tempfile
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from _fixture_quelle import frische_library
from src.core.app_state import clear_channel_cache, get_state
from src.core.database import bibliothek_format as BF
from src.core.database.models import FixtureMode, FixtureProfile
from src.core.engine.cue import Cue
from src.core.engine.cue_stack import CueStack
from src.core.engine.function import FunctionType
from src.core.engine.palette import (Palette, PaletteManager, PaletteType,
                                     get_palette_manager)
from src.core.engine.sequence import Sequence, SequenceStep
from src.core.engine.snap_library import get_snap_library
from src.core.show.show_file import _las28_umschluesseln, _show_daten, load_show

ALT = {"laser_twist": 10, "laser_twist#1": 20, "laser_twist#2": 30,
       "laser_twist#3": 40}
NEU = {"laser_twist": 10, "laser_twist_y": 20, "laser_twist#1": 30,
       "laser_twist_y#1": 40}
# Physische Kanaele (1-basiert) im Modus "25 Channel" bei Adresse 1.
KANAL = {"Pattern A Horizontal Flip": 5, "Pattern A Vertical Flip": 6,
         "Pattern B Horizontal Flip": 17, "Pattern B Vertical Flip": 18}


def frische_library_engine():
    from src.core.database import fixture_db as FDB
    return FDB._engine


def _laden(show: dict) -> None:
    path = os.path.join(tempfile.mkdtemp(), "cdx65.lshow")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("show.json", json.dumps(show))
    ok, msg = load_show(path)
    assert ok, f"load_show fehlgeschlagen: {msg}"


class ShLaser3wFlipMigration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        eng = frische_library(cls)
        with Session(eng) as s:
            BF.einspielen_wenn_noetig(s)
            s.commit()
            prof = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes)
                         .selectinload(FixtureMode.channels))
                .where(FixtureProfile.short_name == "SH-LASER3W")).scalar_one()
            modus = next(m for m in prof.modes if m.name == "25 Channel")
            cls.pid = prof.id
            cls.modus = modus.name
            cls.cc = len(modus.channels)
            namen = sorted(modus.channels, key=lambda c: c.channel_number)
            # Testannahme absichern: die Kanalnummern der vier Flips.
            for c in namen:
                if c.name in KANAL:
                    assert c.channel_number == KANAL[c.name], (c.name, c.channel_number)
        clear_channel_cache()

    @classmethod
    def tearDownClass(cls):
        clear_channel_cache()

    def _patch(self):
        return [{"fid": 1, "label": "Laser", "fixture_profile_id": self.pid,
                 "mode_name": self.modus, "universe": 1, "address": 1,
                 "channel_count": self.cc, "fixture_name": "3000mW RGB Laser",
                 "manufacturer_name": "Shehds", "fixture_type": "laser"}]

    def _alte_show(self, **extra):
        cs = CueStack("CS")
        cs.cues.append(Cue.from_dict({"number": 1, "values": {"1": dict(ALT)}}))
        seq = Sequence(name="Seq")
        seq.steps.append(SequenceStep(values={"1": dict(ALT)}))
        pm = PaletteManager()
        pm._palettes = [Palette(name="P", type=PaletteType.LASER,
                                values=dict(ALT), fixture_values={1: dict(ALT)})]
        show = {
            "version": "1.2",
            "patch": self._patch(),
            "programmer": {"1": dict(ALT)},
            "base_levels": {"1": dict(ALT)},
            "cue_stacks": [cs.to_dict()],
            "functions": {"functions": [seq.to_dict()]},
            "palettes": pm.to_dict(),
            "library": {"folders": [], "snaps": [
                {"id": 4, "name": "S1", "folder": "", "values": {"1": dict(ALT)}}]},
            "snapshots": [{"id": 1, "name": "Snap", "values": {"1": dict(ALT)}}],
        }
        show.update(extra)
        return show

    def test_alte_show_trifft_dieselben_physischen_kanaele(self):
        _laden(self._alte_show())
        st = get_state()
        self.assertEqual(st.programmer[1], NEU)
        # Programmer liegt VOR dem Flush um: dieselben DMX-Kanaele wie vorher.
        u = st.universes[1]
        self.assertEqual(u.get_channel(KANAL["Pattern A Horizontal Flip"]), 10)
        self.assertEqual(u.get_channel(KANAL["Pattern A Vertical Flip"]), 20)
        self.assertEqual(u.get_channel(KANAL["Pattern B Horizontal Flip"]), 30)
        self.assertEqual(u.get_channel(KANAL["Pattern B Vertical Flip"]), 40)

        self.assertEqual(st.base_levels[1], NEU)
        self.assertEqual(st.cue_stacks[0].cues[0].values[1], NEU)
        seq = st.function_manager.by_type(FunctionType.Sequence)[0]
        self.assertEqual(seq.steps[0].values["1"], NEU)
        pal = next(p for p in get_palette_manager().get_all() if p.name == "P")
        self.assertEqual(pal.fixture_values[1], NEU)
        self.assertEqual(pal.values, NEU)
        snap = next(s for s in get_snap_library().snaps() if s.name == "S1")
        self.assertEqual(snap.values[1], NEU)
        self.assertEqual(st._snapshots_data[0]["values"]["1"], NEU)

    def test_show_mit_marker_bleibt_unberuehrt(self):
        _laden(self._alte_show(attribut_migrationen=["LAS-28"]))
        st = get_state()
        self.assertEqual(st.programmer[1], ALT)
        self.assertEqual(st.cue_stacks[0].cues[0].values[1], ALT)

    def test_speichern_schreibt_den_marker(self):
        _laden(self._alte_show())
        daten = _show_daten(get_state(), [])
        self.assertIn("LAS-28", daten.get("attribut_migrationen", []))
        self.assertEqual(daten["programmer"][1], NEU)

    def test_neu_geschriebenes_dict_bleibt(self):
        d = {"laser_twist#1": 5, "laser_twist_y": 7}
        _las28_umschluesseln(d)
        self.assertEqual(d, {"laser_twist#1": 5, "laser_twist_y": 7})
        d = dict(ALT)
        _las28_umschluesseln(d)
        _las28_umschluesseln(d)   # idempotent
        self.assertEqual(d, NEU)

    def _generisch_laden(self, patch):
        pm = PaletteManager()
        pm._palettes = [Palette(name="Q", type=PaletteType.LASER,
                                values={"laser_twist": 8, "laser_twist#1": 9})]
        _laden({"version": "1.2", "patch": patch, "palettes": pm.to_dict()})
        return next(p for p in get_palette_manager().get_all() if p.name == "Q")

    def test_generische_palette_mit_nur_kopf_1_bleibt_neben_l2600(self):
        """Ein einzelnes ``laser_twist#1`` in generischen Werten kann von einem
        Zweigruppen-Laser stammen (L2600) — steht einer im Patch, bleibt es."""
        with Session(frische_library_engine()) as s:
            l2600 = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes)
                         .selectinload(FixtureMode.channels))
                .where(FixtureProfile.short_name == "L2600LASER")).scalar_one()
            modus = max(l2600.modes, key=lambda m: len(m.channels))
            zweiter = {"fid": 2, "label": "L2600", "fixture_profile_id": l2600.id,
                       "mode_name": modus.name, "universe": 1, "address": 101,
                       "channel_count": len(modus.channels),
                       "fixture_name": l2600.name, "fixture_type": "laser"}
            self.assertGreaterEqual(
                sum(c.attribute == "laser_twist" for c in modus.channels), 2)
        pal = self._generisch_laden(self._patch() + [zweiter])
        self.assertEqual(pal.values, {"laser_twist": 8, "laser_twist#1": 9})

    def test_generische_palette_flip_a_nur_mit_sh_laser3w(self):
        """Review CDX-65: eine alte generische Palette „Flip A" (``laser_twist``
        + ``laser_twist#1``) traf ohne Umsetzung den horizontalen Flip von B.
        Ist kein anderes Mehrfach-twist-Geraet gepatcht, ist #1 eindeutig."""
        pal = self._generisch_laden(self._patch())
        self.assertEqual(pal.values, {"laser_twist": 8, "laser_twist_y": 9})

if __name__ == "__main__":
    unittest.main()
