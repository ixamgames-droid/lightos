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

Nachbesserung (Codex): Die show.json verraet nicht, ob sie vor oder nach
LAS-28 gespeichert wurde; nur der ZIP-Zeitstempel des Eintrags belegt „vorher".
Ein Dict nur mit ``laser_twist#1`` wird deshalb nur umgesetzt, wenn die Show
nirgends ``laser_twist_y`` traegt und entweder anderswo eindeutig im Altstand
ist (``#2``/``#3``) oder vor dem 01.11.2026 gestempelt wurde. Generische Palettenwerte bleiben neben einem
anderen Mehrfach-twist-Geraet (L2600) unveraendert; die Umsetzung landet als
Override je SH-LASER3W.
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


def _laden(show: dict, zeit: tuple | None = None) -> None:
    """``zeit``: Zeitstempel des ZIP-Eintrags show.json (Vorgabe: jetzt, wie
    ``zipfile.writestr`` beim echten Speichern)."""
    path = os.path.join(tempfile.mkdtemp(), "cdx65.lshow")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        if zeit is None:
            z.writestr("show.json", json.dumps(show))
        else:
            info = zipfile.ZipInfo("show.json", date_time=zeit)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, json.dumps(show))
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

    def _l2600(self):
        with Session(frische_library_engine()) as s:
            l2600 = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes)
                         .selectinload(FixtureMode.channels))
                .where(FixtureProfile.short_name == "L2600LASER")).scalar_one()
            modus = max(l2600.modes, key=lambda m: len(m.channels))
            self.assertGreaterEqual(
                sum(c.attribute == "laser_twist" for c in modus.channels), 2)
            return {"fid": 2, "label": "L2600", "fixture_profile_id": l2600.id,
                    "mode_name": modus.name, "universe": 1, "address": 101,
                    "channel_count": len(modus.channels),
                    "fixture_name": l2600.name, "fixture_type": "laser"}

    def _generisch_laden(self, patch, werte=None, fixture_values=None, **extra):
        pm = PaletteManager()
        pm._palettes = [Palette(
            name="Q", type=PaletteType.LASER,
            values=dict(werte or {"laser_twist": 8, "laser_twist#1": 9}),
            fixture_values=dict(fixture_values or {}))]
        show = {"version": "1.2", "patch": patch, "palettes": pm.to_dict()}
        show.update(extra)
        _laden(show)
        return next(p for p in get_palette_manager().get_all() if p.name == "Q")

    def test_generische_palette_mit_nur_kopf_1_bleibt_neben_l2600(self):
        """Ein einzelnes ``laser_twist#1`` in generischen Werten kann von einem
        Zweigruppen-Laser stammen (L2600) — steht einer im Patch, bleibt es."""
        pal = self._generisch_laden(self._patch() + [self._l2600()])
        self.assertEqual(pal.values, {"laser_twist": 8, "laser_twist#1": 9})

    def test_generische_palette_flip_a_mit_altstands_merkmal(self):
        """Review CDX-65: eine alte generische Palette „Flip A" (``laser_twist``
        + ``laser_twist#1``) traf ohne Umsetzung den horizontalen Flip von B.
        Traegt die Show anderswo eindeutig den Altstand (#2/#3) und kein
        ``laser_twist_y``, ist #1 eindeutig und wird umgesetzt."""
        pal = self._generisch_laden(self._patch(),
                                    programmer={"1": dict(ALT)})
        self.assertEqual(pal.values, {"laser_twist": 8, "laser_twist_y": 9})

    # ── CDX-65 Nachbesserung (Codex) ─────────────────────────────────────

    def test_generische_palette_neben_l2600_bleibt_fuer_l2600_gleich(self):
        """Codex (A): generische ``#1``/``#2`` neben einem L2600. Umgesetzt
        werden darf nur fuer den SH-LASER3W — als Override je Geraet. Der L2600
        bekommt weiter dieselben generischen Werte (zweiter Twist = 20)."""
        alt = {"laser_twist#1": 20, "laser_twist#2": 30}
        pal = self._generisch_laden(self._patch() + [self._l2600()], werte=alt)
        self.assertEqual(pal.values, alt)
        self.assertEqual(pal.get_values_for_fixture(2)["laser_twist#1"], 20)
        laser = pal.get_values_for_fixture(1)
        self.assertEqual(laser["laser_twist_y"], 20)     # A vertikal
        self.assertEqual(laser["laser_twist#1"], 30)     # B horizontal

    def test_override_des_geraets_gewinnt_ueber_generisch(self):
        alt = {"laser_twist#1": 20, "laser_twist#2": 30}
        pal = self._generisch_laden(
            self._patch() + [self._l2600()], werte=alt,
            fixture_values={1: {"laser_twist#2": 77}})
        self.assertEqual(pal.values, alt)
        self.assertEqual(pal.fixture_values[1],
                         {"laser_twist_y": 20, "laser_twist#1": 77})

    def test_nur_kopf_1_ohne_altstands_merkmal_bleibt(self):
        """Codex (B): eine nach LAS-28, aber vor dieser Migration gespeicherte
        Show traegt keinen Marker. ``laser_twist#1`` heisst dort schon „B
        horizontal" und darf nicht zu ``laser_twist_y`` werden."""
        cs = CueStack("CS")
        cs.cues.append(Cue.from_dict(
            {"number": 1, "values": {"1": {"laser_twist#1": 30}}}))
        _laden({"version": "1.2", "patch": self._patch(),
                "programmer": {"1": {"laser_twist#1": 30}},
                "cue_stacks": [cs.to_dict()]})
        st = get_state()
        self.assertEqual(st.programmer[1], {"laser_twist#1": 30})
        self.assertEqual(st.cue_stacks[0].cues[0].values[1], {"laser_twist#1": 30})
        self.assertEqual(st.universes[1].get_channel(
            KANAL["Pattern B Horizontal Flip"]), 30)

    def test_nur_kopf_1_neben_neuem_stand_bleibt(self):
        """Mischstand: ein Dict traegt schon ``laser_twist_y`` -> die Show ist
        nach LAS-28 gespeichert, ein ``#1`` allein bleibt; eindeutig alte
        Dicts (#2/#3) werden trotzdem umgesetzt."""
        cs = CueStack("CS")
        cs.cues.append(Cue.from_dict({"number": 1, "values": {"1": dict(ALT)}}))
        _laden({"version": "1.2", "patch": self._patch(),
                "programmer": {"1": {"laser_twist#1": 30}},
                "base_levels": {"1": {"laser_twist_y": 5}},
                "cue_stacks": [cs.to_dict()]})
        st = get_state()
        self.assertEqual(st.programmer[1], {"laser_twist#1": 30})
        self.assertEqual(st.cue_stacks[0].cues[0].values[1], NEU)

    def test_nur_kopf_1_mit_altstands_merkmal_wird_umgesetzt(self):
        cs = CueStack("CS")
        cs.cues.append(Cue.from_dict({"number": 1, "values": {"1": dict(ALT)}}))
        _laden({"version": "1.2", "patch": self._patch(),
                "programmer": {"1": {"laser_twist#1": 20}},
                "cue_stacks": [cs.to_dict()]})
        self.assertEqual(get_state().programmer[1], {"laser_twist_y": 20})

    # ── ZIP-Zeitstempel als Speicherstand-Hinweis ────────────────────────

    def _nur_kopf_1_show(self):
        cs = CueStack("CS")
        cs.cues.append(Cue.from_dict(
            {"number": 1, "values": {"1": {"laser_twist#1": 20}}}))
        return {"version": "1.2", "patch": self._patch(),
                "programmer": {"1": {"laser_twist#1": 20}},
                "cue_stacks": [cs.to_dict()]}

    def test_nur_kopf_1_vor_dem_stichtag_gespeichert_wird_umgesetzt(self):
        """Eine Alt-Show, die nur den vertikalen Flip von A nutzt (nur
        ``laser_twist#1``), traegt kein Inhaltsmerkmal — aber der ZIP-Eintrag
        show.json ist vor LAS-28 gestempelt: eindeutig Altstand."""
        _laden(self._nur_kopf_1_show(), zeit=(2026, 10, 20, 18, 30, 0))
        st = get_state()
        self.assertEqual(st.programmer[1], {"laser_twist_y": 20})
        self.assertEqual(st.cue_stacks[0].cues[0].values[1], {"laser_twist_y": 20})
        self.assertEqual(st.universes[1].get_channel(
            KANAL["Pattern A Vertical Flip"]), 20)

    def test_nur_kopf_1_nach_dem_stichtag_bleibt(self):
        _laden(self._nur_kopf_1_show(), zeit=(2026, 11, 1, 14, 0, 0))
        self.assertEqual(get_state().programmer[1], {"laser_twist#1": 20})

    def test_unplausibler_zeitstempel_zaehlt_nicht(self):
        """ZIP-Vorgabe 1980 (Uhr ohne Zeit) ist kein Beleg fuer „vorher"."""
        _laden(self._nur_kopf_1_show(), zeit=(1980, 1, 1, 0, 0, 0))
        self.assertEqual(get_state().programmer[1], {"laser_twist#1": 20})

    def test_vor_dem_stichtag_aber_mit_neuem_stand_bleibt(self):
        """``laser_twist_y`` im Inhalt widerlegt den Zeitstempel (falsche Uhr)."""
        show = self._nur_kopf_1_show()
        show["base_levels"] = {"1": {"laser_twist_y": 5}}
        _laden(show, zeit=(2026, 10, 20, 18, 30, 0))
        self.assertEqual(get_state().programmer[1], {"laser_twist#1": 20})


if __name__ == "__main__":
    unittest.main()
