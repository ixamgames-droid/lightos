"""P4: Live-View-Zustand (Positionen + Zoom/Grid/Snap/Welt) wandert mit der
Show (.lshow) und wird beim Laden wiederhergestellt; alte Shows ohne
Meta-Block laden fehlerfrei (Fallback = leeres Meta -> ui_prefs-Defaults).
"""
import json
import os
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile

from src.core.app_state import get_state
from src.core.show.show_file import save_show, load_show

META = {"zoom": 1.5, "grid_size": 25, "snap": True,
        "grid_visible": False, "world_w": 1600, "world_h": 900}


class LiveViewMetaPersistTest(unittest.TestCase):
    def test_roundtrip(self):
        state = get_state()
        state.live_view_positions = {7: (10.0, 20.0)}
        state.live_view_meta = dict(META)
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "lvmeta.lshow")
            save_show(path)
            # State wegwerfen -> Laden muss alles wiederherstellen
            state.live_view_positions = {}
            state.live_view_meta = {}
            load_show(path)
            self.assertEqual(state.live_view_positions.get(7), (10.0, 20.0))
            self.assertEqual(state.live_view_meta, META)

    def test_old_show_without_meta_loads(self):
        state = get_state()
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "old.lshow")
            save_show(path)
            # Meta-Block entfernen = altes Show-Format simulieren
            with zipfile.ZipFile(path) as zf:
                data = json.loads(zf.read("show.json"))
            data["live_view"].pop("meta", None)
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("show.json", json.dumps(data))
            state.live_view_meta = {"zoom": 9.9}   # muss ueberschrieben werden
            load_show(path)
            self.assertEqual(state.live_view_meta, {})


if __name__ == "__main__":
    unittest.main()
