"""Multi-Achsen-Ausrichtung (rx, ry, rz) je Fixture im 3D-Visualizer wandert mit
der Show (.lshow) und wird beim Laden wiederhergestellt. Alte Shows ohne den
``rotations``-Block laden fehlerfrei (Fallback = keine Rotationen). Alte Shows mit
EINEM Y-Float pro Fixture werden abwaertskompatibel als (0, y, 0) geladen.
Positionen bleiben unveraendert 3-Tupel (keine Migration noetig).
"""
import json
import os
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile

from src.core.app_state import get_state
from src.core.show.show_file import save_show, load_show


class VisualizerRotationPersistTest(unittest.TestCase):
    def test_rotation_roundtrip(self):
        state = get_state()
        state.visualizer_positions = {7: (1.0, 6.5, -2.0)}
        # Multi-Achsen: Kippen X, Drehen Y, Roll Z (Grad)
        state.visualizer_rotations = {7: (15.0, 90.0, -5.0)}
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "viz_rot.lshow")
            save_show(path)
            # State wegwerfen -> Laden muss alles wiederherstellen
            state.visualizer_positions = {}
            state.visualizer_rotations = {}
            load_show(path)
            self.assertEqual(state.visualizer_positions.get(7), (1.0, 6.5, -2.0))
            self.assertEqual(state.visualizer_rotations.get(7), (15.0, 90.0, -5.0))

    def test_old_show_without_rotations_loads(self):
        state = get_state()
        state.visualizer_positions = {3: (0.0, 6.5, 0.0)}
        state.visualizer_rotations = {3: (0.0, 45.0, 0.0)}
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "old.lshow")
            save_show(path)
            # rotations-Block entfernen = altes Show-Format simulieren. VIZ-11:
            # zusaetzlich den scene_graph-Block entfernen (save_show schreibt
            # ihn seit v1.2 dual) -- sonst ist die Datei kein echtes Alt-Show-
            # Abbild mehr und load_show wuerde den (unveraenderten) Graphen
            # statt der manipulierten Legacy-Daten fuehren.
            with zipfile.ZipFile(path) as zf:
                data = json.loads(zf.read("show.json"))
            data["visualizer"].pop("rotations", None)
            data.pop("scene_graph", None)
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("show.json", json.dumps(data))
            state.visualizer_rotations = {3: (0.0, 999.0, 0.0)}   # muss geleert werden
            load_show(path)
            self.assertEqual(state.visualizer_rotations, {})
            # Positionen unveraendert wiederhergestellt
            self.assertEqual(state.visualizer_positions.get(3), (0.0, 6.5, 0.0))

    def test_legacy_scalar_rotation_migrates(self):
        """Alt-Show speicherte EINEN Y-Float pro Fixture. Laden muss das als
        (0, y, 0)-Tupel normalisieren (Yaw-only), nicht crashen oder verwerfen."""
        state = get_state()
        state.visualizer_positions = {5: (2.0, 6.5, 1.0)}
        state.visualizer_rotations = {5: (0.0, 30.0, 0.0)}
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "legacy.lshow")
            save_show(path)
            # rotations als ALT-Format (Skalar) zurueckschreiben. VIZ-11:
            # scene_graph-Block ebenfalls entfernen (s. test_old_show_without_
            # rotations_loads) -- sonst greift die Direkt-Migration (from_dict)
            # statt from_legacy und der manipulierte Legacy-Block wird ignoriert.
            with zipfile.ZipFile(path) as zf:
                data = json.loads(zf.read("show.json"))
            data["visualizer"]["rotations"] = {"5": 90.0}
            data.pop("scene_graph", None)
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("show.json", json.dumps(data))
            state.visualizer_rotations = {}
            load_show(path)
            self.assertEqual(state.visualizer_rotations.get(5), (0.0, 90.0, 0.0))


if __name__ == "__main__":
    unittest.main()
