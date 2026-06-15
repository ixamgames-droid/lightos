"""Unit tests for src.core.show.show_file without external dependencies."""
from __future__ import annotations
import importlib
import json
import os
import sys
import tempfile
import types
import unittest
import zipfile
from dataclasses import dataclass


@dataclass
class _FakePatchedFixture:
    fid: int
    label: str = ""
    fixture_profile_id: int = 0
    mode_name: str = ""
    universe: int = 1
    address: int = 1
    channel_count: int = 1
    invert_pan: bool = False
    invert_tilt: bool = False
    swap_pan_tilt: bool = False
    dimmer_curve: str = "linear"
    manufacturer_name: str = ""
    fixture_name: str = ""
    fixture_type: str = "other"


class _FakeCueStack:
    def __init__(self, name: str):
        self.name = name

    def to_dict(self):
        return {"name": self.name}

    @classmethod
    def from_dict(cls, d: dict):
        return cls(d.get("name", "Stack"))


class _FakePaletteManager:
    def __init__(self):
        self.loaded = None

    def to_dict(self):
        return {"palettes": [{"name": "Palette 1"}]}

    def from_dict(self, d: dict):
        self.loaded = d


class _FakeFunctionManager:
    def __init__(self):
        self.saved = {"functions": [{"id": 1, "name": "Scene 1", "type": "Scene"}]}
        self.loaded = None
        self.added = []  # via add() migrierte Funktionen (z. B. Legacy-EFX/RGB)

    def to_dict(self):
        return self.saved

    def from_dict(self, d: dict):
        self.loaded = d

    def add(self, f):
        self.added.append(f)
        return f


class _FakeSync:
    def __init__(self):
        self.refresh_count = 0

    def refresh_all(self):
        self.refresh_count += 1


class _FakeEfxInstance:
    def __init__(self, name: str):
        self.name = name

    def to_dict(self):
        return {"name": self.name}

    @classmethod
    def from_dict(cls, d: dict):
        return cls(d.get("name", "EFX"))


class _FakeRgbMatrixInstance:
    def __init__(self, name: str):
        self.name = name

    def to_dict(self):
        return {"name": self.name}

    @classmethod
    def from_dict(cls, d: dict):
        return cls(d.get("name", "RGB"))


class _FakeState:
    def __init__(self):
        self._patch_cache: list[_FakePatchedFixture] = []
        self.cue_stacks: list[_FakeCueStack] = []
        self.programmer = {}
        self.base_levels = {}
        self.render_rebuilds = 0
        self.function_manager = _FakeFunctionManager()
        self.sync = _FakeSync()
        self._efx_instances: list[_FakeEfxInstance] = []
        self._rgb_matrix_instances: list[_FakeRgbMatrixInstance] = []
        self._vc_layout = {}
        self.show_name = "Neue Show"
        self.emitted: list[tuple[str, object]] = []

    def get_patched_fixtures(self):
        return list(self._patch_cache)

    def add_fixture(self, fixture, undoable=True):
        self._patch_cache.append(fixture)

    def remove_fixture(self, fid: int, undoable=True):
        self._patch_cache = [f for f in self._patch_cache if f.fid != fid]

    def clear_programmer(self):
        self.programmer.clear()

    def _rebuild_render_plan(self):
        self.render_rebuilds += 1

    def _emit(self, event: str, data=None):
        self.emitted.append((event, data))


class ShowFileTests(unittest.TestCase):
    def setUp(self):
        self._orig_modules = {}
        self.state = _FakeState()
        self.palette_manager = _FakePaletteManager()

        mod_app_state = types.ModuleType("src.core.app_state")
        mod_app_state.get_state = lambda: self.state

        mod_palette = types.ModuleType("src.core.engine.palette")
        mod_palette.get_palette_manager = lambda: self.palette_manager

        mod_cue_stack = types.ModuleType("src.core.engine.cue_stack")
        mod_cue_stack.CueStack = _FakeCueStack

        mod_models = types.ModuleType("src.core.database.models")
        mod_models.PatchedFixture = _FakePatchedFixture

        mod_efx = types.ModuleType("src.core.engine.efx")
        mod_efx.EfxInstance = _FakeEfxInstance

        mod_rgb = types.ModuleType("src.core.engine.rgb_matrix")
        mod_rgb.RgbMatrixInstance = _FakeRgbMatrixInstance

        self._install_module("src.core.app_state", mod_app_state)
        self._install_module("src.core.engine.palette", mod_palette)
        self._install_module("src.core.engine.cue_stack", mod_cue_stack)
        self._install_module("src.core.database.models", mod_models)
        self._install_module("src.core.engine.efx", mod_efx)
        self._install_module("src.core.engine.rgb_matrix", mod_rgb)

        self.show_file = importlib.import_module("src.core.show.show_file")
        self.show_file = importlib.reload(self.show_file)

    def tearDown(self):
        for name, old in self._orig_modules.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old

    def _install_module(self, name: str, module):
        self._orig_modules[name] = sys.modules.get(name)
        sys.modules[name] = module

    def test_roundtrip_restores_patch_and_state(self):
        self.state.show_name = "Test Show"
        self.state._patch_cache = [
            _FakePatchedFixture(
                fid=1,
                label="PAR 1",
                fixture_profile_id=100,
                mode_name="3ch",
                universe=1,
                address=1,
                channel_count=3,
                fixture_name="Generic PAR",
                fixture_type="par",
            ),
            _FakePatchedFixture(
                fid=2,
                label="MH 1",
                fixture_profile_id=200,
                mode_name="16ch",
                universe=1,
                address=10,
                channel_count=16,
                fixture_name="Moving Head",
                fixture_type="moving_head",
            ),
        ]
        self.state.cue_stacks = [_FakeCueStack("Main Stack")]
        self.state._vc_layout = {"page": 1}
        # EFX/RGB-Matrix sind seit dem Programmer-Umbau echte Funktionen und
        # werden NICHT mehr ueber State-Listen gespeichert (Bloecke bleiben leer).
        self.state._efx_instances = [_FakeEfxInstance("EFX A")]
        self.state._rgb_matrix_instances = [_FakeRgbMatrixInstance("RGB A")]

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "roundtrip.lshow")
            self.show_file.save_show(path, layout={"current_section": 3})

            with zipfile.ZipFile(path, "r") as zf:
                data = json.loads(zf.read("show.json").decode("utf-8"))
            self.assertEqual(data["version"], "1.1")
            self.assertIn("patch", data)
            self.assertEqual(data["patch"][0]["fixture_profile_id"], 100)
            self.assertIn("functions", data)
            self.assertNotIn("profile_id", data["patch"][0])
            # Neuer Vertrag: separate Bloecke werden leer geschrieben.
            self.assertEqual(data.get("efx", []), [])
            self.assertEqual(data.get("rgb_matrix", []), [])

            # Dirty current state before load to ensure replacement.
            self.state._patch_cache = [_FakePatchedFixture(fid=999, label="Old")]
            self.state.cue_stacks = [_FakeCueStack("Old Stack")]
            self.state._vc_layout = {"old": True}
            self.state._efx_instances = []
            self.state._rgb_matrix_instances = []
            self.state.show_name = "Old Show"

            ok, msg = self.show_file.load_show(path)
            self.assertTrue(ok, msg)
            self.assertEqual(self.state.show_name, "Test Show")
            self.assertEqual(len(self.state.get_patched_fixtures()), 2)
            self.assertEqual(self.state.get_patched_fixtures()[0].fid, 1)
            self.assertEqual(self.state.get_patched_fixtures()[1].label, "MH 1")
            self.assertEqual(len(self.state.cue_stacks), 1)
            self.assertEqual(self.state.cue_stacks[0].name, "Main Stack")
            self.assertEqual(self.state._vc_layout, {"page": 1})
            self.assertEqual(getattr(self.state, "_last_loaded_layout", {}), {"current_section": 3})
            # State-Listen werden beim Laden geleert (Instanzen leben jetzt im
            # FunctionManager). Keine Legacy-Bloecke in dieser Show -> keine
            # Migration.
            self.assertEqual(self.state._efx_instances, [])
            self.assertEqual(self.state._rgb_matrix_instances, [])
            self.assertEqual(self.state.function_manager.added, [])
            self.assertEqual(self.state.sync.refresh_count, 1)
            emitted_names = [ev[0] for ev in self.state.emitted]
            self.assertIn("show_loaded", emitted_names)

    def test_channel_groups_roundtrip(self):
        # SDK-02: Kanal-Gruppen werden pro Show gespeichert/geladen.
        self.state.show_name = "CG Show"
        cg = [{"name": "G1", "universe": 1, "channels": [1, 2, 3], "value": 100}]
        self.state._channel_groups_data = list(cg)
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "cg.lshow")
            self.show_file.save_show(path)
            with zipfile.ZipFile(path, "r") as zf:
                data = json.loads(zf.read("show.json").decode("utf-8"))
            self.assertEqual(data["channel_groups"], cg)
            self.state._channel_groups_data = []          # dirty vor dem Laden
            ok, msg = self.show_file.load_show(path)
            self.assertTrue(ok, msg)
            self.assertEqual(self.state._channel_groups_data, cg)

    def test_legacy_efx_rgb_blocks_migrate_to_functions(self):
        """Alt-Shows mit separaten efx/rgb_matrix-Bloecken werden beim Laden in
        echte Funktionen (function_manager.add) migriert."""
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "legacy.lshow")
            payload = {
                "version": "1.1",
                "name": "Legacy",
                "patch": [],
                "functions": {"functions": []},
                "efx": [{"name": "Alt-EFX"}],
                "rgb_matrix": [{"name": "Alt-RGB"}],
            }
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("show.json", json.dumps(payload))

            ok, msg = self.show_file.load_show(path)
            self.assertTrue(ok, msg)
            added_names = sorted(getattr(f, "name", "") for f in
                                 self.state.function_manager.added)
            self.assertEqual(added_names, ["Alt-EFX", "Alt-RGB"])
            # State-Listen bleiben leer — Migration geht in den FunctionManager.
            self.assertEqual(self.state._efx_instances, [])
            self.assertEqual(self.state._rgb_matrix_instances, [])

    def test_base_levels_roundtrip(self):
        """base_levels (z. B. PAR-Grundhelligkeit) wird gespeichert, beim Laden
        wiederhergestellt und der Render-Plan neu gebaut."""
        self.state.base_levels = {2: {"intensity": 255}, 3: {"intensity": 200}}
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "base.lshow")
            self.show_file.save_show(path)
            with zipfile.ZipFile(path, "r") as zf:
                data = json.loads(zf.read("show.json").decode("utf-8"))
            self.assertIn("base_levels", data)

            self.state.base_levels = {}            # vor dem Laden verschmutzen
            self.state.render_rebuilds = 0
            ok, msg = self.show_file.load_show(path)
            self.assertTrue(ok, msg)
            self.assertEqual(self.state.base_levels,
                             {2: {"intensity": 255}, 3: {"intensity": 200}})
            self.assertGreaterEqual(self.state.render_rebuilds, 1)

    def test_load_legacy_patch_schema(self):
        legacy_payload = {
            "version": "1.0",
            "name": "Legacy",
            "patch": [
                {
                    "id": 5,
                    "profile_id": 42,
                    "name": "Legacy Fixture",
                    "mode": "Basic",
                    "universe": 2,
                    "address": 50,
                }
            ],
            "cue_stacks": [],
        }
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "legacy.lshow")
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("show.json", json.dumps(legacy_payload))

            ok, msg = self.show_file.load_show(path)
            self.assertTrue(ok, msg)
            fixtures = self.state.get_patched_fixtures()
            self.assertEqual(len(fixtures), 1)
            self.assertEqual(fixtures[0].fid, 5)
            self.assertEqual(fixtures[0].fixture_profile_id, 42)
            self.assertEqual(fixtures[0].label, "Legacy Fixture")
            self.assertEqual(fixtures[0].mode_name, "Basic")
            self.assertEqual(fixtures[0].universe, 2)
            self.assertEqual(fixtures[0].address, 50)


class _FakeStateWithDB(_FakeState):
    """_FakeState erweitert um echten SQLite-In-Memory-Store fuer FixtureGroup-Tests."""

    def __init__(self):
        super().__init__()
        from sqlalchemy import create_engine as _ce
        from src.core.database.models import Base
        from sqlalchemy.orm import Session as _Session
        self._show_engine = _ce("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self._show_engine)
        self._Session = _Session

    def _session(self):
        return self._Session(self._show_engine)

    def _flush_all_to_dmx(self):
        pass


class ResetGroupsTest(unittest.TestCase):
    """Regressionstest: reset_show() leert Fixture-Gruppen in der Show-DB."""

    def setUp(self):
        self._orig_modules = {}
        self.state = _FakeStateWithDB()
        self.palette_manager = _FakePaletteManager()

        from src.core.database.models import FixtureGroup as _RealFG

        mod_app_state = types.ModuleType("src.core.app_state")
        mod_app_state.get_state = lambda: self.state

        mod_palette = types.ModuleType("src.core.engine.palette")
        mod_palette.get_palette_manager = lambda: self.palette_manager

        mod_cue_stack = types.ModuleType("src.core.engine.cue_stack")
        mod_cue_stack.CueStack = _FakeCueStack

        mod_models = types.ModuleType("src.core.database.models")
        mod_models.PatchedFixture = _FakePatchedFixture
        mod_models.FixtureGroup = _RealFG

        mod_efx = types.ModuleType("src.core.engine.efx")
        mod_efx.EfxInstance = _FakeEfxInstance

        mod_rgb = types.ModuleType("src.core.engine.rgb_matrix")
        mod_rgb.RgbMatrixInstance = _FakeRgbMatrixInstance

        self._install_module("src.core.app_state", mod_app_state)
        self._install_module("src.core.engine.palette", mod_palette)
        self._install_module("src.core.engine.cue_stack", mod_cue_stack)
        self._install_module("src.core.database.models", mod_models)
        self._install_module("src.core.engine.efx", mod_efx)
        self._install_module("src.core.engine.rgb_matrix", mod_rgb)

        self.show_file = importlib.import_module("src.core.show.show_file")
        self.show_file = importlib.reload(self.show_file)

    def tearDown(self):
        for name, old in self._orig_modules.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old

    def _install_module(self, name: str, module):
        self._orig_modules[name] = sys.modules.get(name)
        sys.modules[name] = module

    def test_reset_show_clears_fixture_groups(self):
        """Nach reset_show() darf keine FixtureGroup mehr in der DB vorhanden sein."""
        from sqlalchemy import select
        from src.core.database.models import FixtureGroup

        # Gruppe anlegen
        with self.state._session() as s:
            s.add(FixtureGroup(name="T", cols=4, rows=1, positions_json="{}"))
            s.commit()

        # Sicherstellen, dass sie wirklich drin ist
        with self.state._session() as s:
            before = list(s.execute(select(FixtureGroup)).scalars())
        self.assertEqual(len(before), 1)

        # Dirty State vor Reset setzen
        self.state.programmer = {"x": 1}
        self.state.live_view_positions = {"1": {"x": 10, "y": 20}}

        self.show_file.reset_show()

        # Gruppen-Tabelle muss leer sein
        with self.state._session() as s:
            after = list(s.execute(select(FixtureGroup)).scalars())
        self.assertEqual(after, [], "Fixture-Gruppen wurden nach reset_show() nicht geleert")

        # Weitere Reset-Zustaende pruefen
        self.assertEqual(self.state.programmer, {})
        self.assertEqual(self.state.live_view_positions, {})

    def test_reset_show_zeroes_universes(self):
        """Nach reset_show() muessen alle DMX-Universe-Puffer auf 0 stehen, damit
        der Output-Thread keine alten Werte der vorigen Show weitersendet."""
        from src.core.dmx.universe import Universe

        u1, u2 = Universe(1), Universe(2)
        u1.set_channel(1, 255)
        u1.set_channel(17, 200)
        u2.set_channel(5, 128)
        self.state.universes = {1: u1, 2: u2}

        self.show_file.reset_show()

        self.assertEqual(u1.get_all(), bytes(Universe.SIZE))
        self.assertEqual(u2.get_all(), bytes(Universe.SIZE))


if __name__ == "__main__":
    unittest.main()
