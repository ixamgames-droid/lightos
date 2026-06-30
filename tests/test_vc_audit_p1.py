"""VC-Code-Audit P1-Bugfixes (VCB-01..10), Stand 2026-06-30.

Getestet werden die strukturellen Fixes; die reinen Index-/Guard-Fixes
(VCB-08 negativer Executor-Slot, VCB-09 negativer Snapshot-Index, VCB-10
event.accept()) sind selbstevidente Guards und per Code-Review abgedeckt.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint

from src.core.app_state import get_state
from src.core.show.show_file import reset_show
from src.ui.virtualconsole.vc_frame import VCFrame
from src.ui.virtualconsole.vc_canvas import VCCanvas
from src.ui.virtualconsole.vc_button import VCButton
from src.ui.virtualconsole.vc_widget import VCWidget

_app = QApplication.instance() or QApplication([])


class VCB01_02_03_FramePageVisibility(unittest.TestCase):
    def test_vcb02_child_on_other_page_is_hidden(self):
        """VCB-02: add_child_to_page auf einer NICHT-aktuellen Seite versteckt das
        Widget (kein bedingungsloses widget.show() mehr)."""
        f = VCFrame()
        f._page_count = 2
        f._current_page = 0
        on_cur = VCButton("cur")
        off_cur = VCButton("off")
        f.add_child_to_page(on_cur, page=0)
        f.add_child_to_page(off_cur, page=1)
        self.assertFalse(on_cur.isHidden(), "Seite-0-Kind sichtbar (aktuelle Seite)")
        self.assertTrue(off_cur.isHidden(),
                        "Seite-1-Kind muss versteckt sein, solange Frame Seite 0 zeigt")

    def test_vcb01_switch_page_leaves_nested_frame_children(self):
        """VCB-01: switch_page des aeusseren Frames fasst die Kinder eines
        verschachtelten inneren Frames NICHT an (FindDirectChildrenOnly)."""
        outer = VCFrame()
        outer._page_count = 2
        inner = VCFrame()
        inner._page_count = 2
        outer.add_child_to_page(inner, page=0)
        grand = VCButton("g")
        inner.add_child_to_page(grand, page=1)
        inner.switch_page(1)                      # inner zeigt seine Seite 1 -> grand sichtbar
        self.assertFalse(grand.isHidden())
        outer.switch_page(0)                      # outer zeigt Seite 0 (= inner)
        # Mit Fix: outer toucht das Grandchild nicht -> bleibt wie vom inneren Frame
        # gesetzt. Ohne Fix wuerde outer es (vc_page=1 != outer.current=0) verstecken.
        self.assertFalse(grand.isHidden(),
                         "switch_page des aeusseren Frames darf Grandchildren nicht "
                         "verstecken (VCB-01)")

    def test_vcb03_switch_page_clamps_out_of_range(self):
        """VCB-03: nach Seitenzahl-Reduktion klemmt switch_page den _current_page."""
        f = VCFrame()
        f._page_count = 3
        f.switch_page(2)
        self.assertEqual(f._current_page, 2)
        f._page_count = 1                         # wie in _open_properties reduziert
        f.switch_page(f._current_page)            # der VCB-03-Aufruf
        self.assertEqual(f._current_page, 0, "ungueltiger _current_page muss geklemmt werden")


class VCB05_FixtureDimmersCleared(unittest.TestCase):
    def setUp(self):
        get_state()
        reset_show()

    def test_reset_show_clears_fixture_dimmers(self):
        state = get_state()
        state.fixture_dimmers = {1: 0.3, 2: 0.5}
        reset_show()
        self.assertEqual(get_state().fixture_dimmers, {},
                         "reset_show muss die Gruppen-/Fixture-Dimmer der alten Show "
                         "leeren (VCB-05) — sonst Ghost-Dimmer")


class VCB06_ClearUndoable(unittest.TestCase):
    def test_push_undo_then_clear_is_undoable(self):
        """VCB-06: 'Alle loeschen' wird per _push_undo() vor _clear() rueckgaengig-
        machbar (der Kontextmenue-Pfad ruft jetzt beides)."""
        c = VCCanvas()
        c._add_widget("VCButton", QPoint(20, 20))
        self.assertTrue(len(c.findChildren(VCWidget)) >= 1)
        c._push_undo()
        c._clear()
        self.assertEqual(len(c.findChildren(VCWidget)), 0, "Canvas geleert")
        self.assertTrue(c.can_undo(), "nach push_undo+clear muss Undo moeglich sein")
        c.undo()
        self.assertTrue(len(c.findChildren(VCWidget)) >= 1,
                        "Undo stellt das geloeschte Widget wieder her")


class VCB07_SetParamNormalizedNonNumeric(unittest.TestCase):
    def setUp(self):
        self.fm = get_state().function_manager
        self.fn = self.fm.new_rgb_matrix("VCB07Matrix")

    def tearDown(self):
        try:
            self.fm.remove(self.fn.id)
        except Exception:
            pass

    def test_color_sequence_param_returns_false_not_raise(self):
        """VCB-07: set_param_normalized auf einem nicht-numerischen Param
        (color_sequence) gibt False zurueck statt mit AttributeError zu crashen."""
        from src.core.engine import effect_live
        # 'colors' ist ParamSpec kind 'color_sequence' (min/max = None).
        try:
            result = effect_live.set_param_normalized("colors", 0.5, self.fn.id)
        except Exception as e:
            self.fail(f"set_param_normalized darf nicht crashen: {e!r}")
        self.assertFalse(result, "nicht-numerischer Param -> False")

    def test_numeric_param_still_works(self):
        from src.core.engine import effect_live
        # 'speed' ist numerisch -> normalisiertes Setzen bleibt funktionsfaehig.
        self.assertTrue(effect_live.set_param_normalized("speed", 0.5, self.fn.id))


if __name__ == "__main__":
    unittest.main()
