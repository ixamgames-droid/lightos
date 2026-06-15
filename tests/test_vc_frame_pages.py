"""VC-Audit 2026-06-13 (A3): VCFrame Mehrseiten-Laden.

Früher überschrieb in apply_dict ein bedingungsloses child.show() die Seiten-
Sichtbarkeit → alle Seiten überlappten nach dem Laden. Jetzt setzt switch_page()
die Sichtbarkeit konsistent (nur aktuelle Seite sichtbar).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.virtualconsole.vc_frame import VCFrame
from src.ui.virtualconsole.vc_button import VCButton

_app = QApplication.instance() or QApplication([])


def _build_two_page_frame() -> VCFrame:
    f = VCFrame("Frame")
    f._page_count = 2
    b0 = VCButton("P1-Btn")
    f.add_child_to_page(b0, 0)
    b1 = VCButton("P2-Btn")
    f.add_child_to_page(b1, 1)
    return f


class FrameMultiPageLoadTest(unittest.TestCase):
    def test_only_current_page_visible_after_load(self):
        src = _build_two_page_frame()
        dst = VCFrame("Loaded")
        dst.apply_dict(src.to_dict())

        kids = dst.findChildren(VCButton)
        self.assertEqual(len(kids), 2)
        by_page = {(k.property("vc_page") or 0): k for k in kids}
        # Seite 0 sichtbar, Seite 1 versteckt — KEINE Überlappung.
        self.assertFalse(by_page[0].isHidden())
        self.assertTrue(by_page[1].isHidden())

    def test_switch_page_toggles_visibility(self):
        dst = VCFrame("Loaded")
        dst.apply_dict(_build_two_page_frame().to_dict())
        kids = {(k.property("vc_page") or 0): k for k in dst.findChildren(VCButton)}
        dst.switch_page(1)
        self.assertTrue(kids[0].isHidden())
        self.assertFalse(kids[1].isHidden())

    def test_current_page_clamped(self):
        dst = VCFrame("Loaded")
        dst._current_page = 5            # ungültig
        dst.apply_dict(_build_two_page_frame().to_dict())
        self.assertLess(dst._current_page, dst._page_count)
        self.assertGreaterEqual(dst._current_page, 0)

    def test_children_inherit_edit_mode(self):
        dst = VCFrame("Loaded")
        dst.set_edit_mode(True)          # Frame im Edit-Mode VOR dem Laden
        dst.apply_dict(_build_two_page_frame().to_dict())
        for k in dst.findChildren(VCButton):
            self.assertTrue(k._edit_mode)

    def test_page_count_at_least_one(self):
        dst = VCFrame("Loaded")
        dst.apply_dict({"type": "VCFrame", "page_count": 0, "children": []})
        self.assertGreaterEqual(dst._page_count, 1)


if __name__ == "__main__":
    unittest.main()
