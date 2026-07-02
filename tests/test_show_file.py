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
    spider_mirrored: bool = True
    spider_dual_tilt: bool = False
    pan_range_deg: int = 540
    tilt_range_deg: int = 270
    pan_zero_dmx: int = 128
    tilt_zero_dmx: int = 128
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
            self.assertEqual(data["version"], "1.2")
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

    def test_implicit_brightness_roundtrip(self):
        """implicit_brightness wird gespeichert und beim Laden exakt (beide
        Richtungen) wiederhergestellt — der Schalter ueberlebt Save/Load."""
        for saved in (False, True):
            self.state.implicit_brightness = saved
            with tempfile.TemporaryDirectory() as td:
                path = os.path.join(td, "ib.lshow")
                self.show_file.save_show(path)
                with zipfile.ZipFile(path, "r") as zf:
                    data = json.loads(zf.read("show.json").decode("utf-8"))
                self.assertEqual(data["implicit_brightness"], saved)
                self.state.implicit_brightness = not saved   # vor dem Laden verschmutzen
                ok, msg = self.show_file.load_show(path)
                self.assertTrue(ok, msg)
                self.assertEqual(self.state.implicit_brightness, saved)

    def test_load_legacy_show_without_key_keeps_implicit_on(self):
        """Alt-Show OHNE implicit_brightness-Schluessel laedt mit True — der Look
        bestehender Shows bleibt erhalten; nur NEUE Shows starten strikt getrennt."""
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "legacy_ib.lshow")
            payload = {"version": "1.1", "name": "Legacy", "patch": [],
                       "functions": {"functions": []}}
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("show.json", json.dumps(payload))
            self.state.implicit_brightness = False   # verschmutzen
            ok, msg = self.show_file.load_show(path)
            self.assertTrue(ok, msg)
            self.assertTrue(self.state.implicit_brightness)

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

    def test_patch_replace_suppresses_emits_during_rebuild(self):
        """BUG-01 (Reload-Crash): Während _replace_patch_from_data den Patch
        ersetzt, muss die Emit-Unterdrückung aktiv sein (_suppress_emits=True),
        damit kein Listener re-entrant mitten im noch inkonsistenten Patch
        refresht (programmer_view._refresh_effects_list -> QListWidget.clear()
        -> AccessViolation). Nach dem Aufbau ist die Unterdrückung wieder
        aufgehoben — load_show()/reset_show() machen dann EINEN gebündelten
        Refresh."""
        seen_during_add: list[bool] = []
        orig_add = self.state.add_fixture

        def _spy_add(fixture, undoable=True):
            seen_during_add.append(getattr(self.state, "_suppress_emits", False))
            return orig_add(fixture, undoable=undoable)

        self.state.add_fixture = _spy_add

        patch_data = [
            {"id": 1, "profile_id": 10, "name": "PAR 1", "mode": "8ch",
             "universe": 1, "address": 1},
            {"id": 2, "profile_id": 10, "name": "PAR 2", "mode": "8ch",
             "universe": 1, "address": 9},
        ]
        self.show_file._replace_patch_from_data(self.state, patch_data)

        # Jeder add_fixture-Aufruf lief mit aktiver Unterdrückung.
        self.assertEqual(seen_during_add, [True, True])
        # Danach ist die Unterdrückung wieder aus (auf den vorherigen Wert restauriert).
        self.assertFalse(getattr(self.state, "_suppress_emits", False))
        self.assertEqual(len(self.state.get_patched_fixtures()), 2)


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
        # Neue Show startet strikt getrennt (Farbe macht Dimmer NICHT auf).
        self.assertFalse(self.state.implicit_brightness)

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


class _SceneAwareFakeState(_FakeState):
    """_FakeState erweitert um einen ECHTEN SceneGraph + die 5 Adapter-
    Properties (siehe src/core/stage/scene_adapters.py) — deckt den echten
    AppState-Vertrag ab (VIZ-11 Schritt 5), waehrend der Rest der
    show_file-Umgebung (Patch, Paletten, ...) weiter gefaked bleibt."""

    def __init__(self):
        super().__init__()
        from src.core.stage.scene_graph import SceneGraph
        from src.core.stage.scene_adapters import _ViewRegistry
        self._scene = SceneGraph()
        self._view_registry = _ViewRegistry()
        self._active_stage_name = "simple"
        self._live_view_transient: dict = {}
        self.live_view_meta: dict = {}

    @property
    def visualizer_positions(self):
        from src.core.stage.scene_adapters import _SceneBackedDict
        return _SceneBackedDict(self._scene, "pos", self._view_registry)

    @visualizer_positions.setter
    def visualizer_positions(self, value):
        from src.core.stage.scene_adapters import _SceneBackedDict
        view = _SceneBackedDict(self._scene, "pos", self._view_registry)
        view.clear()
        for fid, pos in dict(value or {}).items():
            view[fid] = pos

    @property
    def visualizer_rotations(self):
        from src.core.stage.scene_adapters import _SceneBackedDict
        return _SceneBackedDict(self._scene, "rot", self._view_registry)

    @visualizer_rotations.setter
    def visualizer_rotations(self, value):
        from src.core.stage.scene_adapters import _SceneBackedDict
        view = _SceneBackedDict(self._scene, "rot", self._view_registry)
        for fid, rot in dict(value or {}).items():
            view[fid] = rot
        stale = [n.fixture_id for n in self._scene.fixtures()
                 if n.fixture_id not in dict(value or {})]
        for fid in stale:
            view[fid] = (0.0, 0.0, 0.0)

    @property
    def visualizer_docks(self):
        from src.core.stage.scene_adapters import _DockView
        return _DockView(self._scene, self._view_registry)

    @visualizer_docks.setter
    def visualizer_docks(self, value):
        from src.core.stage.scene_adapters import _DockView
        view = _DockView(self._scene, self._view_registry)
        view.clear()
        for fid, sid in dict(value or {}).items():
            view[fid] = sid

    @property
    def live_view_positions(self):
        from src.core.stage.scene_adapters import _LiveViewDict
        return _LiveViewDict(self._scene, self._view_registry, self._live_view_transient)

    @live_view_positions.setter
    def live_view_positions(self, value):
        from src.core.stage.scene_adapters import _LiveViewDict
        view = _LiveViewDict(self._scene, self._view_registry, self._live_view_transient)
        view.clear()
        for fid, pos in dict(value or {}).items():
            view[fid] = pos

    @property
    def active_stage_name(self):
        return self._active_stage_name

    @active_stage_name.setter
    def active_stage_name(self, value):
        self._active_stage_name = value or "simple"
        self._scene.stage_snapshot["name"] = self._active_stage_name


class SceneGraphPersistenceTests(unittest.TestCase):
    """VIZ-11 Schritt 5: .lshow scene_graph-Block (Dual-Write) + Einmal-
    Migration von Alt-Shows ohne den Block."""

    def setUp(self):
        self._orig_modules = {}
        self.state = _SceneAwareFakeState()
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

    def test_save_writes_scene_graph_block_and_roundtrips(self):
        """save_show schreibt zusaetzlich zu den Legacy-Bloecken einen
        scene_graph-Block; load_show baut den Graphen beim v1.2-Format
        DIREKT aus diesem Block (from_dict), nicht ueber from_legacy."""
        self.state.visualizer_positions = {1: (2.0, 6.0, -3.0)}
        self.state.visualizer_rotations = {1: (0.0, 45.0, 0.0)}
        self.state.active_stage_name = "simple"

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "scene.lshow")
            self.show_file.save_show(path)

            with zipfile.ZipFile(path, "r") as zf:
                data = json.loads(zf.read("show.json").decode("utf-8"))
            self.assertEqual(data["version"], "1.2")
            self.assertIn("scene_graph", data)
            self.assertIn("nodes", data["scene_graph"])
            node_ids = {n["id"] for n in data["scene_graph"]["nodes"]}
            self.assertIn("fix_1", node_ids)
            # Legacy-Bloecke bleiben unveraendert (Dual-Write, kein Drift).
            self.assertEqual(data["visualizer"]["positions"]["1"], [2.0, 6.0, -3.0])

            # Dirty state vor dem Laden.
            self.state.visualizer_positions = {}
            self.state.visualizer_rotations = {}
            self.state._scene.stage_snapshot = {}

            ok, msg = self.show_file.load_show(path)
            self.assertTrue(ok, msg)
            self.assertIn(1, dict(self.state.visualizer_positions))
            pos = dict(self.state.visualizer_positions)[1]
            for a, b in zip(pos, (2.0, 6.0, -3.0)):
                self.assertAlmostEqual(a, b, places=6)
            rot = dict(self.state.visualizer_rotations)[1]
            for a, b in zip(rot, (0.0, 45.0, 0.0)):
                self.assertAlmostEqual(a, b, places=6)
            # Graph ist beim v1.2-Format fuehrend: from_dict statt from_legacy.
            self.assertEqual(
                self.state._scene.to_dict()["nodes"],
                data["scene_graph"]["nodes"],
            )

    def test_load_legacy_show_without_scene_graph_migrates_from_legacy(self):
        """Alt-Show (kein scene_graph-Block) -> der geladene Graph muss
        identisch zu SceneGraph.from_legacy(...) mit denselben Legacy-Werten
        sein (Migrations-Algorithmus, Design (c))."""
        legacy_payload = {
            "version": "1.1",
            "name": "Legacy Viz",
            "patch": [],
            "visualizer": {
                "positions": {"7": [1.0, 0.6, 2.0]},
                "rotations": {"7": [0.0, 30.0, 0.0]},
                "docks": {},
                "active_stage": "simple",
            },
            "live_view": {"positions": {}, "meta": {}},
        }
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "legacy_viz.lshow")
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("show.json", json.dumps(legacy_payload))

            ok, msg = self.show_file.load_show(path)
            self.assertTrue(ok, msg)

            from src.core.stage.scene_graph import SceneGraph
            from src.core.stage.stage_definition import DEFAULT_PRESETS

            expected = SceneGraph.from_legacy(
                positions={7: (1.0, 0.6, 2.0)},
                rotations={7: (0.0, 30.0, 0.0)},
                docks={},
                active_stage_name="simple",
                live_view_positions={},
                stage_def=DEFAULT_PRESETS["simple"](),
            )
            self.assertEqual(
                self.state._scene.to_legacy_positions(),
                expected.to_legacy_positions(),
            )
            self.assertEqual(
                self.state._scene.to_legacy_rotations(),
                expected.to_legacy_rotations(),
            )
            # Kein sofortiges Zurueckschreiben: die geladenen Rohdaten (data)
            # auf Disk haben weiterhin KEINEN scene_graph-Block (Migration ist
            # rein in-memory, landet erst beim naechsten save_show).
            with zipfile.ZipFile(path, "r") as zf:
                reloaded = json.loads(zf.read("show.json").decode("utf-8"))
            self.assertNotIn("scene_graph", reloaded)


if __name__ == "__main__":
    unittest.main()
