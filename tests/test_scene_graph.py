"""Kernmodell des Szenegraphen (src/core/stage/scene_graph.py).

Prueft add/remove/reparent(keep_world), Welt-Transform-Vererbung (inkl.
90-Grad-rotiertem Parent: Kind orbitiert um den Pivot + ry addiert sich) und
Bulk-Propagation via descendant_world_transforms.
"""
import math
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.stage.scene_graph import (
    MountType,
    NodeKind,
    SceneGraph,
    SceneNode,
    Transform,
)


class TestAddRemove(unittest.TestCase):
    def test_add_and_get(self):
        g = SceneGraph()
        node = SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1)
        g.add(node)
        self.assertIs(g.get("fix_1"), node)
        self.assertIsNone(g.get("does_not_exist"))

    def test_remove_unknown_is_noop(self):
        g = SceneGraph()
        g.remove("nope")  # darf nicht werfen

    def test_remove_reparents_children_to_root(self):
        g = SceneGraph()
        g.add(SceneNode(id="truss", kind=NodeKind.TRUSS_H, transform=Transform(pos_m=(1.0, 2.0, 3.0))))
        g.add(SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1, parent_id="truss"))
        world_before = g.world_pos("fix_1")

        g.remove("truss")

        self.assertIsNone(g.get("truss"))
        child = g.get("fix_1")
        self.assertIsNotNone(child)
        self.assertIsNone(child.parent_id)
        # Kind "schwebt" an seiner zuletzt gueltigen lokalen Position weiter
        # (Design: bestehendes Verhalten, E2-Gotcha) -- da die lokale
        # Transform unveraendert bleibt und jetzt Root ist, ist Welt == lokal.
        self.assertEqual(g.world_pos("fix_1"), child.transform.pos_m)
        self.assertNotEqual(world_before, (0.0, 0.0, 0.0))

    def test_remove_cascades_children_when_requested(self):
        g = SceneGraph()
        g.add(SceneNode(id="truss", kind=NodeKind.TRUSS_H))
        g.add(SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1, parent_id="truss"))
        g.remove("truss", reparent_children_to_root=False)
        self.assertIsNone(g.get("truss"))
        self.assertIsNone(g.get("fix_1"))

    def test_fixtures_and_fixture_ids(self):
        g = SceneGraph()
        g.add(SceneNode(id="truss", kind=NodeKind.TRUSS_H))
        g.add(SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1))
        g.add(SceneNode(id="fix_2", kind=NodeKind.FIXTURE, fixture_id=2))
        self.assertEqual({n.id for n in g.fixtures()}, {"fix_1", "fix_2"})
        self.assertEqual(g.fixture_ids(), {1, 2})

    def test_children_of(self):
        g = SceneGraph()
        g.add(SceneNode(id="truss", kind=NodeKind.TRUSS_H))
        g.add(SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1, parent_id="truss"))
        g.add(SceneNode(id="fix_2", kind=NodeKind.FIXTURE, fixture_id=2))
        children = g.children_of("truss")
        self.assertEqual([c.id for c in children], ["fix_1"])


class TestWorldTransform(unittest.TestCase):
    def test_root_node_world_equals_local(self):
        g = SceneGraph()
        g.add(SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1,
                         transform=Transform(pos_m=(1.0, 2.0, 3.0), rot_deg=(10.0, 20.0, 30.0))))
        wt = g.world_transform("fix_1")
        self.assertEqual(wt.pos_m, (1.0, 2.0, 3.0))
        self.assertEqual(wt.rot_deg, (10.0, 20.0, 30.0))

    def test_child_inherits_parent_translation(self):
        g = SceneGraph()
        g.add(SceneNode(id="truss", kind=NodeKind.TRUSS_H, transform=Transform(pos_m=(5.0, 6.0, -3.0))))
        g.add(SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1, parent_id="truss",
                         transform=Transform(pos_m=(1.0, 0.0, 0.0))))
        self.assertEqual(g.world_pos("fix_1"), (6.0, 6.0, -3.0))

    def test_child_orbits_pivot_with_90deg_parent_rotation_and_ry_adds(self):
        """90-Grad-rotierter Parent: das Kind (Offset (1,0,0) lokal) orbitiert
        um den Pivot -> landet bei Welt-X=parent.x, Welt-Z=parent.z+1 (fuer
        +90 Grad Y-Drehung). Die Kind-ry addiert sich zur Parent-ry."""
        g = SceneGraph()
        g.add(SceneNode(id="truss", kind=NodeKind.TRUSS_H,
                         transform=Transform(pos_m=(0.0, 6.0, 0.0), rot_deg=(0.0, 90.0, 0.0))))
        g.add(SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1, parent_id="truss",
                         transform=Transform(pos_m=(1.0, 0.0, 0.0), rot_deg=(0.0, 15.0, 0.0))))

        world_pos = g.world_pos("fix_1")
        self.assertAlmostEqual(world_pos[0], 0.0, places=6)
        self.assertAlmostEqual(world_pos[1], 6.0, places=6)
        self.assertAlmostEqual(world_pos[2], 1.0, places=6)

        world_rot = g.world_rot_deg("fix_1")
        self.assertAlmostEqual(world_rot[1], 105.0, places=6)  # 90 + 15
        self.assertAlmostEqual(world_rot[0], 0.0, places=6)
        self.assertAlmostEqual(world_rot[2], 0.0, places=6)

    def test_grandchild_composes_through_two_levels(self):
        g = SceneGraph()
        g.add(SceneNode(id="a", kind=NodeKind.TRUSS_H, transform=Transform(pos_m=(1.0, 0.0, 0.0), rot_deg=(0.0, 90.0, 0.0))))
        g.add(SceneNode(id="b", kind=NodeKind.TRUSS_H, parent_id="a",
                         transform=Transform(pos_m=(1.0, 0.0, 0.0), rot_deg=(0.0, 90.0, 0.0))))
        g.add(SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1, parent_id="b",
                         transform=Transform(pos_m=(1.0, 0.0, 0.0))))
        # a: welt (1,0,0), ry=90. b lokal (1,0,0) -> orbit um a-Pivot: (1,0,1), ry=180
        wt_b = g.world_transform("b")
        self.assertAlmostEqual(wt_b.pos_m[0], 1.0, places=6)
        self.assertAlmostEqual(wt_b.pos_m[2], 1.0, places=6)
        self.assertAlmostEqual(wt_b.rot_deg[1], 180.0, places=6)
        # fix_1 lokal (1,0,0) unter b (ry=180) -> Offset zeigt in -X -> welt x = b.x - 1
        wt_fix = g.world_transform("fix_1")
        self.assertAlmostEqual(wt_fix.pos_m[0], 0.0, places=6)
        self.assertAlmostEqual(wt_fix.pos_m[2], 1.0, places=6)
        self.assertAlmostEqual(wt_fix.rot_deg[1], 180.0, places=6)


class TestReparent(unittest.TestCase):
    def test_reparent_keep_world_true_preserves_world_position(self):
        g = SceneGraph()
        g.add(SceneNode(id="truss", kind=NodeKind.TRUSS_H,
                         transform=Transform(pos_m=(2.0, 6.0, -3.0), rot_deg=(0.0, 45.0, 0.0))))
        g.add(SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1,
                         transform=Transform(pos_m=(10.0, 1.0, -2.0))))
        world_before = g.world_pos("fix_1")
        rot_before = g.world_rot_deg("fix_1")

        g.reparent("fix_1", "truss", keep_world=True)

        self.assertEqual(g.get("fix_1").parent_id, "truss")
        world_after = g.world_pos("fix_1")
        rot_after = g.world_rot_deg("fix_1")
        for a, b in zip(world_before, world_after):
            self.assertAlmostEqual(a, b, places=6)
        for a, b in zip(rot_before, rot_after):
            self.assertAlmostEqual(a, b, places=6)

    def test_reparent_keep_world_false_jumps(self):
        g = SceneGraph()
        g.add(SceneNode(id="truss", kind=NodeKind.TRUSS_H, transform=Transform(pos_m=(2.0, 6.0, -3.0))))
        g.add(SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1,
                         transform=Transform(pos_m=(10.0, 1.0, -2.0))))
        g.reparent("fix_1", "truss", keep_world=False)
        self.assertEqual(g.get("fix_1").parent_id, "truss")
        # lokale Transform blieb (10,1,-2) -> Welt = truss + local (keine Rotation)
        self.assertAlmostEqual(g.world_pos("fix_1")[0], 12.0, places=6)
        self.assertAlmostEqual(g.world_pos("fix_1")[1], 7.0, places=6)
        self.assertAlmostEqual(g.world_pos("fix_1")[2], -5.0, places=6)

    def test_undock_keep_world_true_freezes_current_world_pos(self):
        g = SceneGraph()
        g.add(SceneNode(id="truss", kind=NodeKind.TRUSS_H,
                         transform=Transform(pos_m=(2.0, 6.0, -3.0), rot_deg=(0.0, 45.0, 0.0))))
        g.add(SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1, parent_id="truss",
                         transform=Transform(pos_m=(1.0, 0.0, 0.0))))
        world_before = g.world_pos("fix_1")

        g.reparent("fix_1", None, keep_world=True)

        self.assertIsNone(g.get("fix_1").parent_id)
        world_after = g.world_pos("fix_1")
        for a, b in zip(world_before, world_after):
            self.assertAlmostEqual(a, b, places=6)

    def test_reparent_to_unknown_parent_falls_back_to_none(self):
        g = SceneGraph()
        g.add(SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1))
        g.reparent("fix_1", "ghost", keep_world=True)
        self.assertIsNone(g.get("fix_1").parent_id)

    def test_reparent_unknown_node_is_noop(self):
        g = SceneGraph()
        g.reparent("ghost", None, keep_world=True)  # darf nicht werfen


class TestSetTransform(unittest.TestCase):
    def test_set_transform_only_updates_given_fields(self):
        g = SceneGraph()
        g.add(SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1,
                         transform=Transform(pos_m=(1.0, 2.0, 3.0), rot_deg=(0.0, 0.0, 0.0))))
        g.set_transform("fix_1", rot_deg=(0.0, 90.0, 0.0))
        node = g.get("fix_1")
        self.assertEqual(node.transform.pos_m, (1.0, 2.0, 3.0))
        self.assertEqual(node.transform.rot_deg, (0.0, 90.0, 0.0))

    def test_set_transform_unknown_node_is_noop(self):
        g = SceneGraph()
        g.set_transform("ghost", pos_m=(1.0, 1.0, 1.0))  # darf nicht werfen

    def test_set_world_pos_on_rotated_parent_roundtrips(self):
        g = SceneGraph()
        g.add(SceneNode(id="truss", kind=NodeKind.TRUSS_H,
                         transform=Transform(pos_m=(0.0, 6.0, 0.0), rot_deg=(0.0, 90.0, 0.0))))
        g.add(SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1, parent_id="truss"))
        g.set_world_pos("fix_1", (5.0, 6.0, 2.0))
        world = g.world_pos("fix_1")
        self.assertAlmostEqual(world[0], 5.0, places=6)
        self.assertAlmostEqual(world[1], 6.0, places=6)
        self.assertAlmostEqual(world[2], 2.0, places=6)

    def test_set_world_rot_deg_on_rotated_parent_roundtrips(self):
        g = SceneGraph()
        g.add(SceneNode(id="truss", kind=NodeKind.TRUSS_H,
                         transform=Transform(rot_deg=(0.0, 90.0, 0.0))))
        g.add(SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1, parent_id="truss"))
        g.set_world_rot_deg("fix_1", (0.0, 200.0, 0.0))
        self.assertAlmostEqual(g.world_rot_deg("fix_1")[1], 200.0, places=6)


class TestDescendantWorldTransforms(unittest.TestCase):
    def test_only_fixture_descendants_are_returned(self):
        g = SceneGraph()
        g.add(SceneNode(id="truss", kind=NodeKind.TRUSS_H,
                         transform=Transform(pos_m=(0.0, 6.0, 0.0), rot_deg=(0.0, 90.0, 0.0))))
        g.add(SceneNode(id="sub_truss", kind=NodeKind.TRUSS_V, parent_id="truss",
                         transform=Transform(pos_m=(0.0, -1.0, 0.0))))
        g.add(SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1, parent_id="truss",
                         transform=Transform(pos_m=(1.0, 0.0, 0.0))))
        g.add(SceneNode(id="fix_2", kind=NodeKind.FIXTURE, fixture_id=2, parent_id="sub_truss",
                         transform=Transform(pos_m=(0.0, 0.0, 1.0))))
        g.add(SceneNode(id="fix_orphan", kind=NodeKind.FIXTURE, fixture_id=99))

        result = g.descendant_world_transforms("truss")

        self.assertEqual(set(result.keys()), {1, 2})
        self.assertNotIn(99, result)
        self.assertAlmostEqual(result[1].pos_m[0], 0.0, places=6)
        self.assertAlmostEqual(result[1].pos_m[2], 1.0, places=6)
        # fix_2 haengt am sub_truss (kein eigenes ry) unter truss (ry=90):
        # sub_truss welt = (0,5,0), ry=90; lokal (0,0,1) orbitiert -> welt x=-1,z=0
        self.assertAlmostEqual(result[2].pos_m[0], -1.0, places=6)
        self.assertAlmostEqual(result[2].pos_m[1], 5.0, places=6)
        self.assertAlmostEqual(result[2].pos_m[2], 0.0, places=6)

    def test_empty_when_no_children(self):
        g = SceneGraph()
        g.add(SceneNode(id="truss", kind=NodeKind.TRUSS_H))
        self.assertEqual(g.descendant_world_transforms("truss"), {})


if __name__ == "__main__":
    unittest.main()
