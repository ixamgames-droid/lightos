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

    def to_dict(self):
        return self.saved

    def from_dict(self, d: dict):
        self.loaded = d


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
            self.assertEqual(len(self.state._efx_instances), 1)
            self.assertEqual(self.state._efx_instances[0].name, "EFX A")
            self.assertEqual(len(self.state._rgb_matrix_instances), 1)
            self.assertEqual(self.state._rgb_matrix_instances[0].name, "RGB A")
            self.assertEqual(self.state.sync.refresh_count, 1)
            emitted_names = [ev[0] for ev in self.state.emitted]
            self.assertIn("show_loaded", emitted_names)

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


if __name__ == "__main__":
    unittest.main()
