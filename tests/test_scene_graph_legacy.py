"""Legacy-Bruecke des Szenegraphen (from_legacy/to_legacy_*, to_dict/from_dict).

Kernforderung: Roundtrip legacy -> SceneGraph -> legacy ist identitaetserhaltend
(inkl. Alt-Rotation-Float-Format), Docks werden zu parent_id, und ungueltige
parent_id-Referenzen werden beim Laden verworfen.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.stage.scene_graph import MountType, NodeKind, SceneGraph
from src.core.stage.stage_definition import StageDefinition, StageElement


class TestFromLegacyRoundtrip(unittest.TestCase):
    def test_roundtrip_positions_and_rotations_identity(self):
        positions = {1: (2.0, 6.0, -3.0), 2: (0.0, 0.6, 1.5)}
        rotations = {1: (0.0, 45.0, 0.0), 2: (10.0, 20.0, 30.0)}
        docks = {}
        live_view = {1: (340.0, 170.0), 2: (300.0, 230.0)}

        graph = SceneGraph.from_legacy(
            positions=positions,
            rotations=rotations,
            docks=docks,
            active_stage_name="my_stage",
            live_view_positions=live_view,
            stage_def=StageDefinition(name="my_stage"),
        )

        out_positions = graph.to_legacy_positions()
        out_rotations = graph.to_legacy_rotations()

        self.assertEqual(set(out_positions.keys()), {1, 2})
        for fid, pos in positions.items():
            for a, b in zip(out_positions[fid], pos):
                self.assertAlmostEqual(a, b, places=6)
        for fid, rot in rotations.items():
            for a, b in zip(out_rotations[fid], rot):
                self.assertAlmostEqual(a, b, places=6)

    def test_roundtrip_old_single_float_rotation_format(self):
        """Alt-Shows speichern Rotation als einzelnen Float (nur Y-Drehung)."""
        positions = {1: (1.0, 0.6, 1.0)}
        rotations = {1: 90.0}  # Alt-Format: nackter Float statt Tupel
        graph = SceneGraph.from_legacy(
            positions=positions,
            rotations=rotations,
            docks={},
            active_stage_name="simple",
            live_view_positions={},
            stage_def=StageDefinition(name="simple"),
        )
        out_rotations = graph.to_legacy_rotations()
        self.assertAlmostEqual(out_rotations[1][0], 0.0, places=6)
        self.assertAlmostEqual(out_rotations[1][1], 90.0, places=6)
        self.assertAlmostEqual(out_rotations[1][2], 0.0, places=6)

    def test_dock_becomes_parent_id_and_roundtrips(self):
        stage = StageDefinition(name="my_stage")
        truss = stage.add("truss_h", x=0.0, y=6.0, z=-3.0)
        positions = {1: (0.0, 5.75, -3.0)}
        rotations = {1: (0.0, 0.0, 0.0)}
        docks = {1: truss.id}

        graph = SceneGraph.from_legacy(
            positions=positions,
            rotations=rotations,
            docks=docks,
            active_stage_name="my_stage",
            live_view_positions={},
            stage_def=stage,
        )

        node = graph.get("fix_1")
        self.assertEqual(node.parent_id, truss.id)
        self.assertEqual(node.mount_type, MountType.HANG)

        out_docks = graph.to_legacy_docks()
        self.assertEqual(out_docks, {1: truss.id})
        # Welt-Position bleibt trotz Dock identisch zur Legacy-Eingabe (keep_world).
        out_positions = graph.to_legacy_positions()
        for a, b in zip(out_positions[1], positions[1]):
            self.assertAlmostEqual(a, b, places=6)

    def test_invalid_dock_parent_id_is_discarded(self):
        """Stale-Dock-Filter: Parent-Referenz auf nicht-existente Stage-Node
        wird beim from_legacy verworfen -> parent_id=None (test_stale_dock_
        discarded_on_load bleibt gruen)."""
        positions = {1: (1.0, 0.6, 1.0)}
        rotations = {1: (0.0, 0.0, 0.0)}
        docks = {1: "el_does_not_exist"}

        graph = SceneGraph.from_legacy(
            positions=positions,
            rotations=rotations,
            docks=docks,
            active_stage_name="simple",
            live_view_positions={},
            stage_def=StageDefinition(name="simple"),
        )

        node = graph.get("fix_1")
        self.assertIsNone(node.parent_id)
        self.assertEqual(graph.to_legacy_docks(), {})

    def test_live_view_only_fixture_gets_default_height(self):
        """Fixture ohne visualizer_positions, nur live_view -> wird ueber
        live_to_world3d abgeleitet."""
        graph = SceneGraph.from_legacy(
            positions={},
            rotations={},
            docks={},
            active_stage_name="simple",
            live_view_positions={5: (300.0, 200.0)},  # Ursprung -> (0,0)
            stage_def=StageDefinition(name="simple"),
        )
        node = graph.get("fix_5")
        self.assertIsNotNone(node)
        pos = graph.world_pos("fix_5")
        self.assertAlmostEqual(pos[0], 0.0, places=6)
        self.assertAlmostEqual(pos[2], 0.0, places=6)

    def test_stage_elements_become_nodes_with_geometry(self):
        stage = StageDefinition(name="my_stage")
        stage.add("platform", x=1.0, y=0.0, z=2.0, w=4.0, h=0.4, d=4.0, color="#123456", name="Deck")
        graph = SceneGraph.from_legacy(
            positions={}, rotations={}, docks={},
            active_stage_name="my_stage", live_view_positions={},
            stage_def=stage,
        )
        stage_nodes = [n for n in graph._nodes.values() if n.kind != NodeKind.FIXTURE]
        self.assertEqual(len(stage_nodes), 1)
        node = stage_nodes[0]
        self.assertEqual(node.kind, NodeKind.PLATFORM)
        self.assertEqual(node.color, "#123456")
        self.assertEqual(node.name, "Deck")
        self.assertEqual(node.size_m, (4.0, 0.4, 4.0))


class TestToDictFromDictRoundtrip(unittest.TestCase):
    def test_to_dict_from_dict_identity(self):
        stage = StageDefinition(name="my_stage")
        truss = stage.add("truss_h", x=0.0, y=6.0, z=-3.0, w=6.0, h=0.3, d=0.3, color="#888", name="FOH Truss")
        positions = {12: (2.0, 6.0, -3.0)}
        rotations = {12: (0.0, 45.0, 0.0)}
        docks = {12: truss.id}

        graph = SceneGraph.from_legacy(
            positions=positions, rotations=rotations, docks=docks,
            active_stage_name="my_stage", live_view_positions={}, stage_def=stage,
        )

        data = graph.to_dict()
        self.assertIn("nodes", data)
        self.assertIn("stage_snapshot", data)

        restored = SceneGraph.from_dict(data)

        self.assertEqual(restored.to_legacy_docks(), graph.to_legacy_docks())
        orig_pos = graph.to_legacy_positions()
        rest_pos = restored.to_legacy_positions()
        self.assertEqual(set(orig_pos.keys()), set(rest_pos.keys()))
        for fid in orig_pos:
            for a, b in zip(orig_pos[fid], rest_pos[fid]):
                self.assertAlmostEqual(a, b, places=6)

        orig_rot = graph.to_legacy_rotations()
        rest_rot = restored.to_legacy_rotations()
        for fid in orig_rot:
            for a, b in zip(orig_rot[fid], rest_rot[fid]):
                self.assertAlmostEqual(a, b, places=6)

    def test_from_dict_discards_invalid_parent_id(self):
        data = {
            "nodes": [
                {
                    "id": "fix_1",
                    "kind": "fixture",
                    "fixture_id": 1,
                    "transform": {"pos_m": [1.0, 0.6, 1.0], "rot_deg": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]},
                    "parent_id": "el_ghost",
                    "mount_type": "floor",
                }
            ],
            "stage_snapshot": {"name": "simple", "source": "user"},
        }
        graph = SceneGraph.from_dict(data)
        self.assertIsNone(graph.get("fix_1").parent_id)

    def test_from_dict_empty_nodes(self):
        graph = SceneGraph.from_dict({"nodes": [], "stage_snapshot": {}})
        self.assertEqual(graph.fixtures(), [])


class TestToLegacyLiveView(unittest.TestCase):
    def test_to_legacy_live_view_uses_world3d_to_live(self):
        graph = SceneGraph.from_legacy(
            positions={7: (0.0, 0.6, 0.0)}, rotations={}, docks={},
            active_stage_name="simple", live_view_positions={},
            stage_def=StageDefinition(name="simple"),
        )
        live = graph.to_legacy_live_view()
        self.assertIn(7, live)
        self.assertAlmostEqual(live[7][0], 300.0, places=6)
        self.assertAlmostEqual(live[7][1], 200.0, places=6)


if __name__ == "__main__":
    unittest.main()
