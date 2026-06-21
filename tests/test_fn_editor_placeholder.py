"""CODE-fn-editor-placeholder: EFX/RGBMatrix-Functions landen nicht mehr in der
generischen 'Editor kommt bald'-Sackgasse, sondern bekommen einen Hinweis, dass
sie im Programmer bearbeitet werden."""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from src.core.engine.function import FunctionType
from src.ui.views.function_manager_view import create_function_editor

_app = QApplication.instance() or QApplication([])


def _txt(w) -> str:
    lbl = w.findChild(QLabel)
    return lbl.text() if lbl else ""


class FnEditorPlaceholderTest(unittest.TestCase):
    def _fake(self, ftype, name="X"):
        return SimpleNamespace(function_type=ftype, name=name,
                               is_script=False, is_layered_effect=False,
                               is_carousel=False)

    def test_efx_routes_to_programmer(self):
        t = _txt(create_function_editor(self._fake(FunctionType.EFX, "MyEFX")))
        self.assertIn("EFX", t)
        self.assertIn("Programmer", t)
        self.assertNotIn("kommt bald", t)

    def test_rgbmatrix_routes_to_programmer(self):
        t = _txt(create_function_editor(self._fake(FunctionType.RGBMatrix, "MyMatrix")))
        self.assertIn("Matrix", t)
        self.assertIn("Programmer", t)
        self.assertNotIn("kommt bald", t)

    def test_no_dead_end_for_efx_or_matrix(self):
        for ft in (FunctionType.EFX, FunctionType.RGBMatrix):
            self.assertNotIn("kommt bald", _txt(create_function_editor(self._fake(ft))))


if __name__ == "__main__":
    unittest.main()
