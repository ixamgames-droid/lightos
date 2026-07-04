"""VIZ-13 Schritt 3b-K-2: Bridge/Toolbar/Persistenz fuer Kamera-Presets +
benannte Kameras.

Deckt (siehe docs/VIZ13_JS_NEUAUFBAU_DESIGN.md "3b-Nachtrag" + Abschnitt (c)):
  1. Bridge-Signal-Emits: ``cameraPreset``/``namedCamerasChanged`` existieren als
     echte Qt-Signale und liefern den Payload unveraendert an verbundene
     Slots (Signal-Spy per connect(), analog test_viz12_bridge_batch.py).
  2. ``cameraSaved``-Slot: JS meldet eine gespeicherte Kamera zurueck -> landet
     additiv in ``AppState.visualizer_named_cameras`` (gleicher Name ersetzt
     den bestehenden Eintrag), Bridge pusht die aktualisierte Liste zurueck
     und meldet den Namen ueber ``pyCameraSaved`` ans Fenster.
  3. Persistenz-Roundtrip: ``visualizer.named_cameras`` ist ein additiver
     Show-Block (save_show/load_show), alte Shows OHNE den Block laden mit
     einer leeren Liste (kein SHOW_VERSION-Bump).
  4. JS-Klammer-Balance fuer die neu angefassten scene_src-Module.
"""
import json
import os
import re
import tempfile
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.ui.visualizer.visualizer_window as VW
from src.core.app_state import get_state
from src.core.show.show_file import load_show, reset_show, save_show
from src.core.undo import get_undo_stack

_app = QApplication.instance() or QApplication([])

_SCENE_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "ui", "visualizer", "scene_src",
)
_PRESETS_JS_PATH = os.path.join(_SCENE_SRC, "camera", "presets.js")
_BRIDGE_JS_PATH = os.path.join(_SCENE_SRC, "bridge", "bridge.js")
_APP_JS_PATH = os.path.join(_SCENE_SRC, "app.js")


class CameraBridgeSignalsTest(unittest.TestCase):
    def setUp(self):
        reset_show()
        self.state = get_state()
        get_undo_stack().clear()
        self.bridge = VW.VisualizerBridge(self.state)

    def tearDown(self):
        self.bridge.dispose()

    def test_camera_preset_signal_present(self):
        self.assertTrue(hasattr(VW.VisualizerBridge, "cameraPreset"))

    def test_set_named_cameras_signal_present(self):
        self.assertTrue(hasattr(VW.VisualizerBridge, "namedCamerasChanged"))

    def test_camera_reset_signal_still_present(self):
        """Kompat: bestehendes cameraReset() bleibt unveraendert (additiv)."""
        self.assertTrue(hasattr(VW.VisualizerBridge, "cameraReset"))

    def test_camera_preset_emit_roundtrip(self):
        received = []
        self.bridge.cameraPreset.connect(lambda name: received.append(name))
        self.bridge.cameraPreset.emit("top")
        self.assertEqual(received, ["top"])

    def test_push_camera_preset_helper_emits_signal(self):
        received = []
        self.bridge.cameraPreset.connect(lambda name: received.append(name))
        self.bridge.push_camera_preset("front")
        self.assertEqual(received, ["front"])

    def test_set_named_cameras_emit_roundtrip(self):
        received = []
        self.bridge.namedCamerasChanged.connect(lambda j: received.append(j))
        payload = json.dumps([{"name": "Weitwinkel", "mode": "3D"}])
        self.bridge.namedCamerasChanged.emit(payload)
        self.assertEqual(received, [payload])

    def test_push_named_cameras_helper_emits_json(self):
        received = []
        self.bridge.namedCamerasChanged.connect(lambda j: received.append(j))
        cams = [{"name": "Overview", "mode": "3D", "theta": 0.3}]
        self.bridge.push_named_cameras(cams)
        self.assertEqual(len(received), 1)
        self.assertEqual(json.loads(received[0]), cams)


class CameraSavedSlotTest(unittest.TestCase):
    def setUp(self):
        reset_show()
        self.state = get_state()
        get_undo_stack().clear()
        self.bridge = VW.VisualizerBridge(self.state)

    def tearDown(self):
        self.bridge.dispose()

    def test_camera_saved_slot_present(self):
        self.assertTrue(hasattr(VW.VisualizerBridge, "cameraSaved"))

    def test_camera_saved_fills_app_state(self):
        payload = {
            "name": "Frontal", "mode": "3D",
            "theta": 0.0, "phi": 1.5, "radius": 20.0,
            "target": [0.0, 2.0, 0.0], "orthoSize": 18.0, "orthoPan": [0.0, 0.0],
        }
        self.bridge.cameraSaved(json.dumps(payload))
        cams = self.state.visualizer_named_cameras
        self.assertEqual(len(cams), 1)
        self.assertEqual(cams[0]["name"], "Frontal")
        self.assertEqual(cams[0]["mode"], "3D")

    def test_camera_saved_same_name_replaces_entry(self):
        self.bridge.cameraSaved(json.dumps({"name": "A", "theta": 0.1}))
        self.bridge.cameraSaved(json.dumps({"name": "A", "theta": 0.9}))
        cams = self.state.visualizer_named_cameras
        self.assertEqual(len(cams), 1, "gleicher Name muss ersetzen, nicht duplizieren")
        self.assertEqual(cams[0]["theta"], 0.9)

    def test_camera_saved_different_names_are_additive(self):
        self.bridge.cameraSaved(json.dumps({"name": "A"}))
        self.bridge.cameraSaved(json.dumps({"name": "B"}))
        names = [c["name"] for c in self.state.visualizer_named_cameras]
        self.assertEqual(sorted(names), ["A", "B"])

    def test_camera_saved_blank_name_ignored(self):
        self.bridge.cameraSaved(json.dumps({"name": "  "}))
        self.assertEqual(self.state.visualizer_named_cameras, [])

    def test_camera_saved_pushes_updated_list_to_js(self):
        received = []
        self.bridge.namedCamerasChanged.connect(lambda j: received.append(json.loads(j)))
        self.bridge.cameraSaved(json.dumps({"name": "A"}))
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0]["name"], "A")

    def test_camera_saved_emits_py_camera_saved(self):
        received = []
        self.bridge.pyCameraSaved.connect(lambda name: received.append(name))
        self.bridge.cameraSaved(json.dumps({"name": "MeineKamera"}))
        self.assertEqual(received, ["MeineKamera"])


class NamedCamerasPersistenceTest(unittest.TestCase):
    """Show-Roundtrip: additiver visualizer.named_cameras-Block, alte Shows
    ohne den Key laden mit leerer Liste (kein SHOW_VERSION-Bump)."""

    def setUp(self):
        reset_show()
        self.state = get_state()

    def test_reset_show_clears_named_cameras(self):
        self.state.visualizer_named_cameras = [{"name": "X"}]
        reset_show()
        self.assertEqual(get_state().visualizer_named_cameras, [])

    def test_save_load_roundtrip(self):
        cams = [
            {"name": "Top", "mode": "3D", "theta": 0.3, "phi": 0.01, "radius": 22.0,
             "target": [0.0, 2.0, 0.0], "orthoSize": 18.0, "orthoPan": [0.0, 0.0]},
            {"name": "Draufsicht2D", "mode": "2D", "orthoSize": 12.0,
             "orthoPan": [1.0, -2.0]},
        ]
        self.state.visualizer_named_cameras = cams
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "cam_roundtrip.lshow")
            save_show(path)

            with zipfile.ZipFile(path, "r") as zf:
                data = json.loads(zf.read("show.json").decode("utf-8"))
            # KEIN SHOW_VERSION-Bump (Schritt 3b-K-2 ist additiv).
            self.assertEqual(data["version"], "1.2")
            self.assertEqual(data["visualizer"]["named_cameras"], cams)

            # Dirty vor dem Laden.
            self.state.visualizer_named_cameras = [{"name": "Stale"}]

            ok, msg = load_show(path)
            self.assertTrue(ok, msg)
            loaded = get_state().visualizer_named_cameras
            self.assertEqual(loaded, cams)

    def test_old_show_without_named_cameras_block_loads_empty_list(self):
        """Alt-Show ganz ohne 'named_cameras'-Key im visualizer-Block ->
        leere Liste, kein Fehler (Design-Dokument: tolerant/additiv)."""
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "old_show.lshow")
            save_show(path)

            # Nachtraeglich den Key aus dem gespeicherten JSON entfernen, um
            # eine ECHTE Alt-Show (vor Schritt 3b-K-2) zu simulieren.
            with zipfile.ZipFile(path, "r") as zf:
                data = json.loads(zf.read("show.json").decode("utf-8"))
                names = zf.namelist()
            self.assertIn("named_cameras", data["visualizer"])
            del data["visualizer"]["named_cameras"]
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                for name in names:
                    if name == "show.json":
                        zf.writestr(name, json.dumps(data))
                    else:
                        # Andere Zip-Member (falls vorhanden) unveraendert
                        # durchreichen -- fuer show.json-only-Shows ist die
                        # Schleife trivial (nur ein Eintrag).
                        pass

            self.state.visualizer_named_cameras = [{"name": "ShouldBeCleared"}]
            ok, msg = load_show(path)
            self.assertTrue(ok, msg)
            self.assertEqual(get_state().visualizer_named_cameras, [])

    def test_malformed_named_cameras_entries_are_filtered_not_fatal(self):
        """Ein kaputter Eintrag (kein dict) darf den Rest des Ladevorgangs
        nicht zu Fall bringen -- wird einfach uebersprungen."""
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "malformed.lshow")
            save_show(path)
            with zipfile.ZipFile(path, "r") as zf:
                data = json.loads(zf.read("show.json").decode("utf-8"))
            data["visualizer"]["named_cameras"] = [
                {"name": "Valid"}, "not-a-dict", 42, None,
            ]
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("show.json", json.dumps(data))

            ok, msg = load_show(path)
            self.assertTrue(ok, msg)
            cams = get_state().visualizer_named_cameras
            self.assertEqual(len(cams), 1)
            self.assertEqual(cams[0]["name"], "Valid")


class JsCameraModulesBraceBalanceTest(unittest.TestCase):
    """Statische Klammer-/Parens-Balance-Pruefung ueber die in diesem Schritt
    angefassten scene_src-Module (kein echtes QWebEngine noetig)."""

    def setUp(self):
        with open(_PRESETS_JS_PATH, encoding="utf-8") as f:
            self.presets_js = f.read()
        with open(_BRIDGE_JS_PATH, encoding="utf-8") as f:
            self.bridge_js = f.read()
        with open(_APP_JS_PATH, encoding="utf-8") as f:
            self.app_js = f.read()

    def test_presets_js_braces_balanced(self):
        self.assertEqual(self.presets_js.count("{"), self.presets_js.count("}"))
        self.assertEqual(self.presets_js.count("("), self.presets_js.count(")"))

    def test_bridge_js_braces_balanced(self):
        self.assertEqual(self.bridge_js.count("{"), self.bridge_js.count("}"))
        self.assertEqual(self.bridge_js.count("("), self.bridge_js.count(")"))

    def test_app_js_braces_balanced(self):
        self.assertEqual(self.app_js.count("{"), self.app_js.count("}"))
        self.assertEqual(self.app_js.count("("), self.app_js.count(")"))

    def test_bridge_js_connects_new_signals(self):
        self.assertIn("bridge.cameraPreset", self.bridge_js)
        self.assertIn("bridge.namedCamerasChanged", self.bridge_js)
        # Alt-Signal bleibt verbunden (additiv, kein Ersatz).
        self.assertIn("bridge.cameraReset", self.bridge_js)

    def test_app_js_exposes_named_camera_api(self):
        self.assertIn("saveNamedCamera", self.app_js)
        self.assertIn("applyNamedCamera", self.app_js)
        self.assertIn("getNamedCameras", self.app_js)
        # Alt-API bleibt exponiert (additiv).
        self.assertIn("setCameraPreset", self.app_js)
        self.assertIn("fitAll", self.app_js)
        self.assertIn("fitSelected", self.app_js)
        self.assertIn("setFpsVisible", self.app_js)


if __name__ == "__main__":
    unittest.main()
