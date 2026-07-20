"""CDX-18 — EURON10-Fog fan-Split: Load-Zeit-Kompat fuer pre-split Playback-Daten.

Der 2-Kanal-EURON10 wurde per CDX-07 gesplittet: Kanal 2 wechselte von ``dimmer``
auf ``fan``. Vor dem Split spiegelte der eine ``dimmer``-Wert auf beide Kanaele;
attr-gekeyte Playback-Daten (Programmer/Snaps/Cues/Sequenzen/Paletten/base_levels/
Snapshots), die davor aufgezeichnet wurden, haben nur ``dimmer`` -> nach dem Split
bleibt der Luefter (Default 0) aus. ``load_show`` zieht ``fan=dimmer`` einmalig
nach — NUR fuer EURON10-2-Kanal, NUR wenn ``fan`` fehlt (bereits gesetztes ``fan``
gewinnt), pro Container inline VOR dessen Flush/Rebuild.
"""
import json
import os
import tempfile
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.core.database import fixture_db as fdb
from src.core.database.models import FixtureProfile, FixtureMode
from src.core.app_state import get_state
from src.core.show.show_file import (
    load_show, _euron10_2ch_fids, _fill_fan_from_dimmer,
)
from src.core.engine.cue import Cue
from src.core.engine.cue_stack import CueStack
from src.core.engine.sequence import Sequence, SequenceStep
from src.core.engine.palette import (
    Palette, PaletteManager, PaletteType, get_palette_manager,
)
from src.core.engine.snap_library import get_snap_library
from src.core.engine.function import FunctionType


def _euron10_profile():
    """(profile_id, 2-Kanal-Mode-Name, channel_count) des Builtin-EURON10."""
    fdb.ensure_builtins()
    with Session(fdb.engine()) as s:
        prof = s.execute(
            select(FixtureProfile)
            .options(selectinload(FixtureProfile.modes).selectinload(FixtureMode.channels))
            .where(FixtureProfile.short_name == "EURON10")
        ).scalars().first()
        m2 = next(m for m in prof.modes if m.name.startswith("2-Kanal"))
        return prof.id, m2.name, len(m2.channels)


def _euron10_patch_entry(pid, mode_name, cc, fid=1, address=1):
    return {
        "fid": fid, "label": "Fog", "fixture_profile_id": pid,
        "mode_name": mode_name, "universe": 1, "address": address,
        "channel_count": cc, "fixture_name": "N-10 Nebelmaschine",
        "manufacturer_name": "Eurolite", "fixture_type": "hazer",
    }


def _cue_stacks_block(values):
    cs = CueStack("CS")
    cs.cues.append(Cue.from_dict({"number": 1, "values": values}))
    return [cs.to_dict()]


def _functions_block(values):
    seq = Sequence(name="Seq")
    seq.steps.append(SequenceStep(values=values))
    return {"functions": [seq.to_dict()]}


def _palettes_block(generic, fixture_values):
    pm = PaletteManager()
    # Default-Farbpaletten ersetzen -> nur die Testpalette "P" im Block.
    pm._palettes = [Palette(
        name="P", type=PaletteType.COLOR, values=generic, fixture_values=fixture_values)]
    return pm.to_dict()


def _write_and_load(show: dict) -> None:
    path = os.path.join(tempfile.mkdtemp(), "cdx18.lshow")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("show.json", json.dumps(show))
    ok, _msg = load_show(path)
    assert ok, f"load_show fehlgeschlagen: {_msg}"


class TestEuron10FanMigration(unittest.TestCase):

    def test_all_containers_migrated_and_dmx_timing(self):
        pid, mode, cc = _euron10_profile()
        show = {
            "version": "1.2",
            "patch": [
                _euron10_patch_entry(pid, mode, cc, fid=1, address=1),
                # Kontrolle: 2-Kanal, aber NICHT EURON10 (profile 0) -> nie migriert.
                {"fid": 2, "label": "Ctrl", "fixture_profile_id": 0, "mode_name": "",
                 "universe": 1, "address": 20, "channel_count": 2},
            ],
            "programmer": {"1": {"dimmer": 180}, "2": {"dimmer": 180}},
            "base_levels": {"1": {"dimmer": 30}},
            "cue_stacks": _cue_stacks_block({"1": {"dimmer": 90}}),
            "functions": _functions_block({"1": {"dimmer": 60}}),
            "palettes": _palettes_block({"dimmer": 100}, {1: {"dimmer": 150}}),
            "library": {"folders": [], "snaps": [
                {"id": 4, "name": "S1", "folder": "", "values": {"1": {"dimmer": 200}}}]},
            "snapshots": [{"id": 1, "name": "Snap", "values": {"1": {"dimmer": 210}}}],
        }
        _write_and_load(show)
        st = get_state()

        # (1) Programmer migriert + KRITISCHES TIMING: der Fan-DMX-Kanal (Adresse 2)
        # ist bereits direkt nach load_show gesetzt (Migration lief VOR _flush_all_to_dmx).
        self.assertEqual(st.programmer[1].get("fan"), 180)
        self.assertEqual(st.universes[1].get_channel(2), 180,
                         "Fan-DMX war nach load_show nicht 180 -> Migration lief zu spaet")
        # Kontrolle: Nicht-EURON10 (fid 2) bleibt unberuehrt (kein fan-Key injiziert).
        self.assertNotIn("fan", st.programmer.get(2, {}))

        # (2) base_levels migriert.
        self.assertEqual(st.base_levels[1].get("fan"), 30)

        # (3) Cue-Werte migriert.
        self.assertEqual(st.cue_stacks[0].cues[0].values[1].get("fan"), 90)

        # (4) Sequence-Step migriert (STRING-fid-Key).
        seqs = st.function_manager.by_type(FunctionType.Sequence)
        self.assertEqual(seqs[0].steps[0].values["1"].get("fan"), 60)

        # (5) Palette: NUR der per-Fixture-Override, NICHT die generischen values.
        pal = next(p for p in get_palette_manager().get_all() if p.name == "P")
        self.assertEqual(pal.fixture_values[1].get("fan"), 150)
        self.assertNotIn("fan", pal.values)

        # (6) Snap migriert.
        s1 = next(s for s in get_snap_library().snaps() if s.name == "S1")
        self.assertEqual(s1.values[1].get("fan"), 200)

        # (7) Snapshots (rohe Dicts, str-fid) migriert.
        self.assertEqual(st._snapshots_data[0]["values"]["1"].get("fan"), 210)

    def test_base_levels_timing_default_frame(self):
        """Ohne Programmer faehrt der Default-Render-Frame den Fan aus base_levels —
        beweist, dass base_levels VOR _rebuild_render_plan migriert wurde."""
        pid, mode, cc = _euron10_profile()
        _write_and_load({
            "version": "1.2",
            "patch": [_euron10_patch_entry(pid, mode, cc)],
            "base_levels": {"1": {"dimmer": 45}},
        })
        st = get_state()
        self.assertEqual(st.base_levels[1].get("fan"), 45)
        # Ein Render-Tick wendet den (bei _rebuild_render_plan aus den MIGRIERTEN
        # base_levels gebackenen) Default-Frame auf das Live-Universe an.
        st._render_frame(0.02)
        self.assertEqual(st.universes[1].get_channel(2), 45,
                         "Default-Frame fuehrte den Fan nicht auf den base_levels-Wert")

    def test_fan_already_set_never_overwritten(self):
        """Ein bereits vorhandenes fan (auch 0) gilt als bewusst editiert."""
        pid, mode, cc = _euron10_profile()
        _write_and_load({
            "version": "1.2",
            "patch": [_euron10_patch_entry(pid, mode, cc)],
            "programmer": {"1": {"dimmer": 180, "fan": 0}},
        })
        st = get_state()
        self.assertEqual(st.programmer[1].get("fan"), 0,
                         "bewusst gesetztes fan=0 wurde faelschlich ueberschrieben")

    def test_idempotent(self):
        pid, mode, cc = _euron10_profile()
        show = {
            "version": "1.2",
            "patch": [_euron10_patch_entry(pid, mode, cc)],
            "programmer": {"1": {"dimmer": 170}},
        }
        _write_and_load(show)
        self.assertEqual(get_state().programmer[1].get("fan"), 170)
        # Zweiter Lauf derselben (unmigrierten) Show aendert nichts Zusaetzliches.
        _write_and_load(show)
        self.assertEqual(get_state().programmer[1].get("fan"), 170)

    def test_detection_and_fill_helpers(self):
        # _fill_fan_from_dimmer: nur bei passender fid, nur wenn fan fehlt.
        fids = {1}
        a = {"dimmer": 120}
        _fill_fan_from_dimmer(a, 1, fids)
        self.assertEqual(a.get("fan"), 120)
        # str-fid-Key wird normalisiert.
        b = {"dimmer": 130}
        _fill_fan_from_dimmer(b, "1", fids)
        self.assertEqual(b.get("fan"), 130)
        # fan bereits da -> nie ueberschreiben.
        c = {"dimmer": 140, "fan": 5}
        _fill_fan_from_dimmer(c, 1, fids)
        self.assertEqual(c.get("fan"), 5)
        # fid nicht in der Menge -> unberuehrt.
        d = {"dimmer": 150}
        _fill_fan_from_dimmer(d, 2, fids)
        self.assertNotIn("fan", d)
        # kein dimmer -> nichts.
        e = {"color_r": 200}
        _fill_fan_from_dimmer(e, 1, fids)
        self.assertNotIn("fan", e)

        # _euron10_2ch_fids erkennt den echten gepatchten EURON10.
        pid, mode, cc = _euron10_profile()
        _write_and_load({
            "version": "1.2",
            "patch": [_euron10_patch_entry(pid, mode, cc)],
        })
        st = get_state()
        self.assertEqual(_euron10_2ch_fids(st), {1})

    def test_user_euron10_name_collision_not_migrated(self):
        """source-Gate: ein NICHT-Builtin-Profil (source='user') mit demselben
        short_name 'EURON10' UND exakter [dimmer,fan]-Kanalform wird NICHT
        migriert. Beweist, dass das Gate wirklich auf source=='builtin' beruht
        (nicht auf einer zufaelligen Profil-ID-Kollision). Nutzt eine Temp-
        Fixture-DB (monkeypatch fdb.engine) — Davids echte fixtures.db bleibt
        unberuehrt."""
        from src.core.database.fixture_db import get_engine
        from src.core.database.models import (
            Manufacturer, FixtureProfile, FixtureMode, FixtureChannel,
        )
        orig_engine = fdb.engine
        eng = get_engine(tempfile.mktemp(suffix=".db"))
        fdb.engine = lambda: eng
        self.addCleanup(lambda: setattr(fdb, "engine", orig_engine))
        fdb.ensure_builtins()  # echtes EURON10 (builtin) mit in die Temp-DB seeden
        with Session(eng) as s:
            mfr = Manufacturer(name="TestMfr", short_name="TSTM")
            s.add(mfr); s.flush()
            prof = FixtureProfile(manufacturer_id=mfr.id, name="UserFog",
                                  short_name="EURON10", fixture_type="hazer", source="user")
            s.add(prof); s.flush()
            mode = FixtureMode(fixture_id=prof.id, name="2ch", channel_count=2)
            s.add(mode); s.flush()
            s.add(FixtureChannel(mode_id=mode.id, channel_number=1, name="Nebel", attribute="dimmer"))
            s.add(FixtureChannel(mode_id=mode.id, channel_number=2, name="Lüfter", attribute="fan"))
            s.commit()
            pid = prof.id
        _write_and_load({
            "version": "1.2",
            "patch": [{"fid": 5, "label": "UserFog", "fixture_profile_id": pid,
                       "mode_name": "2ch", "universe": 1, "address": 1, "channel_count": 2}],
            "programmer": {"5": {"dimmer": 175}},
        })
        st = get_state()
        self.assertNotIn(5, _euron10_2ch_fids(st),
                         "user-Profil mit EURON10-Namen faelschlich erkannt (source-Gate defekt)")
        self.assertNotIn("fan", st.programmer.get(5, {}),
                         "Nicht-Builtin-Fixture wurde faelschlich fan-migriert")

    def test_overflow_value_does_not_abort_container(self):
        """Regression F3: ein roher, nicht-sanitisierter Container-Wert wie
        Infinity (int(inf) -> OverflowError) darf die Cue-Migration nicht
        abbrechen — ein nachfolgender valider Cue-Eintrag wird weiter migriert."""
        pid, mode, cc = _euron10_profile()
        cs = CueStack("CS")
        # Cue 1 mit kaputtem Wert (inf), Cue 2 danach valide.
        cs.cues.append(Cue.from_dict({"number": 1, "values": {"1": {"dimmer": float("inf")}}}))
        cs.cues.append(Cue.from_dict({"number": 2, "values": {"1": {"dimmer": 90}}}))
        _write_and_load({
            "version": "1.2",
            "patch": [_euron10_patch_entry(pid, mode, cc)],
            "cue_stacks": [cs.to_dict()],
        })
        st = get_state()
        cues = st.cue_stacks[0].cues
        # Der nachfolgende valide Cue MUSS trotz des kaputten Vorgaengers migriert sein.
        self.assertEqual(cues[1].values[1].get("fan"), 90,
                         "OverflowError im 1. Cue brach die Migration des 2. Cue ab")


if __name__ == "__main__":
    unittest.main()
