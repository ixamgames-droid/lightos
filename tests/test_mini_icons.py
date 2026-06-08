"""Tests fuer die programmatischen Mini-Icons (UI-ICONS-01).

Prueft, dass jedes Icon ohne Exception gebaut wird, nicht-leer ist (eine
gueltige Groesse hat) und der Cache gleiche Objekte zurueckgibt.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.widgets import mini_icons as mi


def _app():
    return QApplication.instance() or QApplication([])


ALL_KINDS = list(mi._PAINTERS.keys())


class TestMiniIcons(unittest.TestCase):
    def setUp(self):
        _app()

    def test_alle_kinds_bauen(self):
        for kind in ALL_KINDS:
            with self.subTest(kind=kind):
                icon = mi.icon_for_kind(kind)
                self.assertFalse(icon.isNull(), f"Icon '{kind}' ist null")
                pm = icon.pixmap(16, 16)
                self.assertEqual(pm.size().width(), 16)
                self.assertEqual(pm.size().height(), 16)

    def test_unbekannter_kind_kein_crash(self):
        icon = mi.icon_for_kind("gibtsnicht")
        self.assertFalse(icon.isNull())

    def test_cache_liefert_gleiches_objekt(self):
        a = mi.icon_for_kind("snap")
        b = mi.icon_for_kind("snap")
        self.assertIs(a, b)

    def test_snap_und_folder_helfer(self):
        self.assertFalse(mi.snap_icon().isNull())
        self.assertFalse(mi.folder_icon().isNull())

    def test_fixture_icon_mapping(self):
        # bekannte und unbekannte Typen liefern ein gueltiges Icon
        for ft in ("moving_head", "par", "led_bar", "strobe", "dimmer",
                   "other", "", "VOLLKOMMEN_UNBEKANNT"):
            with self.subTest(ft=ft):
                self.assertFalse(mi.fixture_icon(ft).isNull())

    def test_kind_for_function(self):
        class _F:
            is_script = False
            is_layered_effect = False
            is_carousel = False
            class function_type:
                value = "RGBMatrix"
        self.assertEqual(mi.kind_for_function(_F()), "rgbmatrix")

        class _Script:
            is_script = True
        self.assertEqual(mi.kind_for_function(_Script()), "script")


if __name__ == "__main__":
    unittest.main()
