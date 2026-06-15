"""T-VIZ-03: Y-Rotation je Fixture im 3D-Visualizer wandert mit der Show (.lshow)
und wird beim Laden wiederhergestellt. Alte Shows ohne den ``rotations``-Block
laden fehlerfrei (Fallback = keine Rotationen). Positionen bleiben unveraendert
3-Tupel (keine Migration noetig).
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
        state.visualizer_rotations = {7: 90.0}
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "viz_rot.lshow")
            save_show(path)
            # State wegwerfen -> Laden muss alles wiederherstellen
            state.visualizer_positions = {}
            state.visualizer_rotations = {}
            load_show(path)
            self.assertEqual(state.visualizer_positions.get(7), (1.0, 6.5, -2.0))
            self.assertEqual(state.visualizer_rotations.get(7), 90.0)

    def test_old_show_without_rotations_loads(self):
        state = get_state()
        state.visualizer_positions = {3: (0.0, 6.5, 0.0)}
        state.visualizer_rotations = {3: 45.0}
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "old.lshow")
            save_show(path)
            # rotations-Block entfernen = altes Show-Format simulieren
            with zipfile.ZipFile(path) as zf:
                data = json.loads(zf.read("show.json"))
            data["visualizer"].pop("rotations", None)
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("show.json", json.dumps(data))
            state.visualizer_rotations = {3: 999.0}   # muss geleert werden
            load_show(path)
            self.assertEqual(state.visualizer_rotations, {})
            # Positionen unveraendert wiederhergestellt
            self.assertEqual(state.visualizer_positions.get(3), (0.0, 6.5, 0.0))


if __name__ == "__main__":
    unittest.main()
