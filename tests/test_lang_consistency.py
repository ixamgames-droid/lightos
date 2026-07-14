"""UI-22: Sprachkonsistenz — nutzer-sichtbare Titel/Kategorien durchgaengig
Deutsch.

Prueft die ANZEIGE-Strings (nicht die internen Keys/Serialisierung):
  * Preset-Browser-Kategorien: das Typ-Label im Untertitel ist deutsch
    (``PaletteType.COLOR`` -> "Farbe", nicht "Color") — die Enum-.value bleibt
    unveraendert der interne, serialisierte Schluessel.
  * VC-Cuelist-Widget: Anzeige-Titel (Default-Caption) == "Cueliste"; das
    Inspector-Typ-Label und der Quick-Add-Button sind ebenfalls "Cueliste"
    (kein englisches "Cue List" mehr).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")

from src.core.engine.palette import (Palette, PaletteType, palette_type_label,
                                      PALETTE_TYPE_LABELS_DE)
from src.core.engine.preset_search import palette_entries


class PaletteTypeLabelTest(unittest.TestCase):
    """Das Anzeige-Label ist deutsch, die serialisierte .value unveraendert."""

    def test_labels_are_german(self):
        self.assertEqual(palette_type_label(PaletteType.COLOR), "Farbe")
        self.assertEqual(palette_type_label(PaletteType.EFFECT), "Effekt")
        self.assertEqual(palette_type_label(PaletteType.ALL), "Alle")
        # Beam/Position/Laser sind im Deutschen identisch (Fachbegriffe).
        self.assertEqual(palette_type_label(PaletteType.BEAM), "Beam")
        self.assertEqual(palette_type_label(PaletteType.POSITION), "Position")
        self.assertEqual(palette_type_label(PaletteType.LASER), "Laser")

    def test_every_type_has_a_label(self):
        for t in PaletteType:
            self.assertIn(t, PALETTE_TYPE_LABELS_DE)
            self.assertTrue(PALETTE_TYPE_LABELS_DE[t])

    def test_internal_value_unchanged(self):
        # UI-22 darf die Serialisierung NICHT anfassen (sonst brechen Shows).
        self.assertEqual(PaletteType.COLOR.value, "Color")
        self.assertEqual(PaletteType.EFFECT.value, "Effect")
        d = Palette(name="Rot", type=PaletteType.COLOR).to_dict()
        self.assertEqual(d["type"], "Color")
        self.assertEqual(Palette.from_dict(d).type, PaletteType.COLOR)

    def test_accepts_raw_value(self):
        self.assertEqual(palette_type_label("Color"), "Farbe")
        self.assertEqual(palette_type_label(""), "")
        self.assertEqual(palette_type_label(None), "")


class PresetBrowserSubtitleTest(unittest.TestCase):
    def test_subtitle_is_german(self):
        e = palette_entries([Palette(name="Rot", type=PaletteType.COLOR)])
        self.assertIn("Farbe", e[0].subtitle)
        self.assertNotIn("Color", e[0].subtitle)


class VCCuelistTitleTest(unittest.TestCase):
    """Der VC-Cuelist-Anzeigetitel ist durchgaengig "Cueliste"."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_default_caption(self):
        from src.ui.virtualconsole.vc_cuelist import VCCueList
        w = VCCueList()
        self.assertEqual(w.caption, "Cueliste")

    def test_inspector_type_label(self):
        from src.ui.virtualconsole.vc_inspector_panel import _TYPE_LABELS
        # Klassenname ist VCCueList (grosses L) — Label deutsch, kein Fallback
        # auf den rohen Klassennamen.
        self.assertEqual(_TYPE_LABELS.get("VCCueList"), "Cueliste")

    def test_quick_add_button_is_german(self):
        from PySide6.QtWidgets import QPushButton
        from src.ui.views.virtual_console_view import VirtualConsoleView
        view = VirtualConsoleView()
        texts = [b.text() for b in view.findChildren(QPushButton)]
        self.assertIn("Cueliste", texts)
        self.assertNotIn("Cue List", texts)


if __name__ == "__main__":
    unittest.main()
