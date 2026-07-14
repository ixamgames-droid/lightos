"""QOL-03: Fixture-Namen in der Geraete-Liste — Vollname im Tooltip + mittige
Kuerzung, damit lange, gleich beginnende Namen unterscheidbar bleiben.

Sichert:
- `FixtureTreeWithDrag` kuerzt Text mittig (ElideMiddle) statt rechts — so bleibt
  der unterscheidende Namens-Schwanz sichtbar.
- `LiveView._refresh_fixture_list` UND `FixtureGroupView._refresh_fixtures` setzen
  auf jedem Fixture-Kind einen Tooltip == angezeigtem Text (Vollname bei Kuerzung).
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

_app = QApplication.instance() or QApplication([])


def _fixtures():
    return [
        SimpleNamespace(fid=13, universe=1, address=1,
                        label="PAR Tri LED RGBW Langname Rechts", fixture_type="PAR"),
        SimpleNamespace(fid=9, universe=1, address=20,
                        label="MH Live Beam 230 Spot", fixture_type="MovingHead"),
        SimpleNamespace(fid=2, universe=2, address=5,
                        label="Strobe Blinder", fixture_type="Strobe"),
    ]


def _fixture_children(tree):
    """Alle Kind-(Fixture-)Items unter den Universe-Ordnern."""
    out = []
    root = tree.invisibleRootItem()
    for i in range(root.childCount()):
        uni = root.child(i)
        for j in range(uni.childCount()):
            out.append(uni.child(j))
    return out


class TestElideMode(unittest.TestCase):
    def test_tree_elides_middle(self):
        from src.ui.views.fixture_group_view import FixtureTreeWithDrag
        t = FixtureTreeWithDrag()
        try:
            self.assertEqual(t.textElideMode(), Qt.TextElideMode.ElideMiddle)
        finally:
            t.deleteLater()


class TestLiveViewTooltips(unittest.TestCase):
    def test_refresh_sets_full_name_tooltip(self):
        from src.ui.views.live_view import LiveView
        lv = LiveView()
        try:
            fx = _fixtures()
            lv._state.get_patched_fixtures = lambda: list(fx)
            lv._refresh_fixture_list()
            children = _fixture_children(lv._fixture_list)
            self.assertEqual(len(children), len(fx))
            for ch in children:
                txt = ch.text(0)
                self.assertTrue(txt.startswith("["))
                self.assertEqual(ch.toolTip(0), txt)  # Vollname == Anzeigetext
            joined = " ".join(ch.toolTip(0) for ch in children)
            self.assertIn("Langname Rechts", joined)   # langer Name voll im Tooltip
        finally:
            lv._state.__dict__.pop("get_patched_fixtures", None)
            lv.deleteLater()


class TestGroupViewTooltips(unittest.TestCase):
    def test_refresh_sets_full_name_tooltip(self):
        from src.ui.views.fixture_group_view import FixtureGroupView
        gv = FixtureGroupView()
        try:
            fx = _fixtures()
            gv._state.get_patched_fixtures = lambda: list(fx)
            gv._refresh_fixtures()
            children = _fixture_children(gv._fixture_list)
            self.assertEqual(len(children), len(fx))
            for ch in children:
                self.assertEqual(ch.toolTip(0), ch.text(0))
        finally:
            gv._state.__dict__.pop("get_patched_fixtures", None)
            gv.deleteLater()


if __name__ == "__main__":
    unittest.main()
