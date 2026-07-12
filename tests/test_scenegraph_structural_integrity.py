"""SceneGraph-Struktur-Integritaet (Bug-Hunt 2026-07-12): drei bestaetigte Defekte.

- remove() haengte Kinder per ``parent_id=None`` ab, OHNE die Welt-Pose in die
  lokale Transform zu backen -> gedockte Fixtures teleportierten um die volle
  Parent-Transform (Docstring verspricht "schweben an ihrer Welt-Position weiter").
- reparent() hatte keinen Zyklen-Check -> ein Knoten unter einen eigenen Nachfahren
  gehaengt bildete eine geschlossene parent-Kette -> falsche Welt-Transform + Hang.
- descendant_world_transforms() hatte kein Besuchs-Set -> Endlosschleife bei Zyklus.
"""
import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.stage.scene_graph import SceneGraph, SceneNode, NodeKind, Transform


def _node(nid, kind, pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0), parent=None, fid=None):
    return SceneNode(id=nid, kind=kind,
                     transform=Transform(pos_m=pos, rot_deg=rot),
                     parent_id=parent, fixture_id=fid)


class RemoveKeepWorldTest(unittest.TestCase):
    def _approx(self, a, b, places=6):
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=places)

    def test_removing_parent_keeps_child_world_pos_unrotated(self):
        g = SceneGraph()
        g.add(_node("truss", NodeKind.PLATFORM, pos=(10.0, 5.0, 0.0)))
        g.add(_node("fix", NodeKind.FIXTURE, pos=(2.0, 0.0, 1.0), parent="truss", fid=1))
        before = g.world_pos("fix")
        self._approx(before, (12.0, 5.0, 1.0))
        g.remove("truss")
        self._approx(g.world_pos("fix"), before)      # KEINE Teleportation
        self.assertIsNone(g.get("fix").parent_id)

    def test_removing_rotated_parent_keeps_child_world_pos(self):
        g = SceneGraph()
        g.add(_node("truss", NodeKind.PLATFORM, pos=(10.0, 5.0, 0.0), rot=(0.0, 90.0, 0.0)))
        g.add(_node("fix", NodeKind.FIXTURE, pos=(2.0, 0.0, 1.0), parent="truss", fid=1))
        before = g.world_pos("fix")
        g.remove("truss")
        self._approx(g.world_pos("fix"), before)       # auch mit Parent-Rotation stabil


class ReparentCycleGuardTest(unittest.TestCase):
    def _graph(self):
        g = SceneGraph()
        g.add(_node("R", NodeKind.PLATFORM))
        g.add(_node("A", NodeKind.FIXTURE, pos=(10.0, 0.0, 0.0), parent="R", fid=1))
        g.add(_node("B", NodeKind.FIXTURE, pos=(5.0, 0.0, 0.0), parent="A", fid=2))
        return g

    def test_reparent_under_descendant_is_rejected(self):
        g = self._graph()
        before = g.world_pos("A")                       # (10,0,0)
        g.reparent("A", "B", keep_world=True)           # B ist Nachfahre von A -> No-Op
        self.assertEqual(g.get("A").parent_id, "R")     # unveraendert
        self.assertEqual(g.get("B").parent_id, "A")
        for x, y in zip(g.world_pos("A"), before):
            self.assertAlmostEqual(x, y)                 # NICHT teleportiert

    def test_reparent_under_self_is_rejected(self):
        g = self._graph()
        g.reparent("A", "A")
        self.assertEqual(g.get("A").parent_id, "R")

    def test_legit_reparent_still_keeps_world(self):
        g = self._graph()
        g.add(_node("C", NodeKind.PLATFORM, pos=(3.0, 0.0, 0.0), parent="R"))
        before = g.world_pos("A")
        g.reparent("A", "C", keep_world=True)           # C ist KEIN Nachfahre -> erlaubt
        self.assertEqual(g.get("A").parent_id, "C")
        for x, y in zip(g.world_pos("A"), before):
            self.assertAlmostEqual(x, y)                 # Welt-Pose bleibt


class DescendantTraversalCycleTest(unittest.TestCase):
    def test_descendant_world_transforms_terminates_on_cycle(self):
        # Zyklus DIREKT bauen (parent_id von Hand), um den Traversal-Guard zu pruefen
        # (reparent verhindert Zyklen jetzt an der Quelle).
        g = SceneGraph()
        g.add(_node("A", NodeKind.FIXTURE, parent="B", fid=1))
        g.add(_node("B", NodeKind.FIXTURE, parent="A", fid=2))
        box = {}

        def run():
            box["r"] = g.descendant_world_transforms("A")

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(timeout=3.0)
        self.assertFalse(t.is_alive(),
                         "descendant_world_transforms hing (Zyklus nicht abgefangen)")
        self.assertLessEqual(set(box.get("r", {}).keys()), {1, 2})


if __name__ == "__main__":
    unittest.main()
