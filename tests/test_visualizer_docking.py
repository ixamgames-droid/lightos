"""Andocken von Strahlern an Buehnen-Elemente + beweglicher Boden (3D-Visualizer).

Deckt die testbare Geometrie (``StageDefinition.dock_target_for``), den neuen
``floor``-Typ und die Persistenz der Andock-Beziehungen (``visualizer_docks``)
in der .lshow ab. Die JS-seitige Live-Vorschau wird hier nicht getestet
(sie spiegelt nur diese Logik).
"""
import json
import math
import os
import tempfile
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import get_state
from src.core.show.show_file import save_show, load_show, reset_show
from src.core.stage.stage_definition import (
    StageDefinition, StageElement, SUPPORTED_TYPES,
    DOCK_HANG_OFFSET, DOCK_TOP_OFFSET,
    get_default_simple, get_default, save_stage, delete_stage,
)


class DockGeometryTest(unittest.TestCase):
    def _stage(self):
        s = StageDefinition(name="T")
        # Boden (gross, flach) bei y=0.05, Truss daruber bei y=8.
        s.add("floor", id="floor", x=0, y=0.05, z=0, w=20, h=0.1, d=20)
        s.add("truss_h", id="truss", x=0, y=8, z=0, w=10, h=0.3, d=0.3)
        s.add("wall", id="wall", x=8, y=4, z=0, w=0.2, h=8, d=6)
        return s

    def test_truss_hangs_below(self):
        s = self._stage()
        # Direkt unter der Truss (deren Tiefe d=0.3 in z): Punkt (0,0)
        t = s.dock_target_for(0.0, 0.0)
        self.assertIsNotNone(t)
        self.assertEqual(t["id"], "truss")
        self.assertEqual(t["kind"], "hang")
        self.assertAlmostEqual(t["y"], 8 - 0.3 / 2 - DOCK_HANG_OFFSET)

    def test_floor_on_top_when_no_truss_above(self):
        s = self._stage()
        # Seitlich neben der Truss (z=5 ausserhalb truss-Tiefe 0.3) -> nur Boden
        t = s.dock_target_for(5.0, 5.0)
        self.assertIsNotNone(t)
        self.assertEqual(t["id"], "floor")
        self.assertEqual(t["kind"], "top")
        self.assertAlmostEqual(t["y"], 0.05 + 0.1 / 2 + DOCK_TOP_OFFSET)

    def test_highest_element_wins(self):
        # Truss (oben) hat Vorrang vor dem Boden (unten) am selben XZ-Punkt.
        s = self._stage()
        t = s.dock_target_for(0.0, 0.0)
        self.assertEqual(t["id"], "truss")

    def test_outside_footprint_returns_none(self):
        s = self._stage()
        self.assertIsNone(s.dock_target_for(100.0, 100.0))

    def test_wall_and_led_wall_do_not_dock(self):
        s = StageDefinition(name="W")
        s.add("wall", id="w", x=0, y=4, z=0, w=10, h=8, d=0.2)
        s.add("led_wall", id="l", x=0, y=4, z=2, w=10, h=6, d=0.15)
        self.assertIsNone(s.dock_target_for(0.0, 0.0))
        self.assertIsNone(s.dock_target_for(0.0, 2.0))

    def test_rotated_truss_footprint(self):
        # Truss um 90 deg gedreht: lange Achse zeigt nun entlang z.
        s = StageDefinition(name="R")
        s.add("truss_h", id="truss", x=0, y=8, z=0, w=10, h=0.3, d=0.3,
              rotation=math.radians(90))
        # Punkt bei z=4 liegt jetzt INNERHALB (vorher ausserhalb der 0.3-Tiefe).
        self.assertIsNotNone(s.dock_target_for(0.0, 4.0))
        # Punkt bei x=4 liegt jetzt AUSSERHALB (war vor Drehung innerhalb).
        self.assertIsNone(s.dock_target_for(4.0, 0.0))

    def test_contains_xz_margin(self):
        el = StageElement(id="t", type="truss_h", x=0, y=8, z=0, w=4, h=0.3, d=0.3)
        self.assertFalse(el.contains_xz(0.0, 0.5))
        self.assertTrue(el.contains_xz(0.0, 0.5, margin=0.5))


class FloorTypeTest(unittest.TestCase):
    def test_floor_supported(self):
        self.assertIn("floor", SUPPORTED_TYPES)

    def test_add_floor(self):
        s = StageDefinition(name="X")
        el = s.add("floor", x=0, y=0.05, z=0, w=14, h=0.1, d=10)
        self.assertEqual(el.type, "floor")

    def test_default_stage_is_empty(self):
        # Der Visualizer startet jetzt mit einer LEEREN Buehne (keine
        # vorgerenderten Presets mehr) — der User baut seine Buehne selbst.
        s = get_default_simple()
        self.assertEqual(s.elements, [])

    def test_unknown_preset_falls_back_to_empty(self):
        # Alt-Shows mit active_stage="theatre"/"rock" -> leere Buehne.
        for name in ("theatre", "rock", "irgendwas"):
            self.assertEqual(get_default(name).elements, [])


class DockPersistenceTest(unittest.TestCase):
    # Die Default-Buehne ist jetzt leer; fuer Dock-Tests brauchen wir eine echte
    # User-Buehne mit bekannten Element-IDs als Andock-Ziel.
    STAGE_NAME = "DockTestStage_pytest"

    def setUp(self):
        s = StageDefinition(name=self.STAGE_NAME)
        s.add("floor", id="simple_floor", x=0, y=0.05, z=0, w=20, h=0.1, d=20)
        save_stage(s)

    def tearDown(self):
        delete_stage(self.STAGE_NAME)

    def test_dock_roundtrip(self):
        state = get_state()
        state.active_stage_name = self.STAGE_NAME
        state.visualizer_positions = {7: (1.0, 7.75, -2.0)}
        state.visualizer_docks = {7: "simple_floor"}
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "dock.lshow")
            save_show(path)
            state.visualizer_positions = {}
            state.visualizer_docks = {}
            load_show(path)
            self.assertEqual(state.visualizer_docks.get(7), "simple_floor")
            self.assertEqual(state.visualizer_positions.get(7), (1.0, 7.75, -2.0))

    def test_stale_dock_discarded_on_load(self):
        state = get_state()
        state.active_stage_name = self.STAGE_NAME
        state.visualizer_positions = {1: (0.0, 6.5, 0.0), 2: (0.0, 6.5, 0.0)}
        # fid 1 -> gueltiges Element; fid 2 -> nicht (mehr) existierendes Element
        state.visualizer_docks = {1: "simple_floor", 2: "el_geloescht"}
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "stale.lshow")
            save_show(path)
            state.visualizer_docks = {}
            load_show(path)
            self.assertEqual(state.visualizer_docks.get(1), "simple_floor")
            self.assertNotIn(2, state.visualizer_docks)

    def test_old_show_without_docks_loads(self):
        state = get_state()
        state.active_stage_name = "simple"
        state.visualizer_positions = {3: (0.0, 6.5, 0.0)}
        state.visualizer_docks = {3: "simple_floor"}
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "old.lshow")
            save_show(path)
            # VIZ-11: scene_graph-Block ebenfalls entfernen (save_show schreibt
            # ihn seit v1.2 dual) -- sonst greift die Direkt-Migration
            # (from_dict) statt from_legacy und der manipulierte Legacy-Block
            # wird ignoriert (s. test_stale_dock_discarded_on_load-Nachbarn).
            with zipfile.ZipFile(path) as zf:
                data = json.loads(zf.read("show.json"))
            data["visualizer"].pop("docks", None)
            data.pop("scene_graph", None)
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("show.json", json.dumps(data))
            state.visualizer_docks = {3: 999}   # muss geleert werden
            load_show(path)
            self.assertEqual(state.visualizer_docks, {})

    def test_reset_clears_docks(self):
        state = get_state()
        state.visualizer_docks = {5: "simple_floor"}
        reset_show()
        self.assertEqual(state.visualizer_docks, {})

    def test_appstate_has_docks_field(self):
        state = get_state()
        self.assertTrue(hasattr(state, "visualizer_docks"))
        self.assertIsInstance(state.visualizer_docks, dict)


if __name__ == "__main__":
    unittest.main()
