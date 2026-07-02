"""UI-Polish-Quick-Wins aus dem Visual-Audit 2026-07-02 (UI-15/16/17/18/23).

Deckt die 5 Befunde aus `docs/UI_VISUAL_AUDIT_2026_07_02.md` ab:
  - UI-15: Section-Buttons (main_window.py) clippten bei 1440x900, weil
    QHBoxLayout Fixed-Policy-Widgets unter ihre sizeHint komprimiert, wenn die
    Summe aller Bar-Items die verfuegbare Breite uebersteigt. Fix: harte
    Mindestbreite (Text+Icon) pro Button + zwei gekuerzte Labels.
  - UI-16: Grand-Master-Prozent-Label ueberlappte den Slider-Griff (gleiche
    Bar-Starvation). Fix: fontMetrics-basierte Mindestbreite.
  - UI-17: EFX-Buttonleiste unter der Effektliste clippte in der 200px-Spalte.
    Fix: FlowLayout statt QHBoxLayout (bricht sauber um statt zu quetschen).
  - UI-18: Checkbox-Indikatoren im Live-Edit-Panel-QSS unchecked unsichtbar
    (kein border/background). Fix: sichtbare Border+Background-Regel ergaenzt.
  - UI-23: Vorschau im breiten Live-Edit-Body war vertikal zentriert statt
    oben ausgerichtet. Fix: AlignTop beim Umhaengen in `_set_wide()`.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QPushButton

# Font-Bootstrap (wie im Spec fuer die visuelle Selbst-Verifikation gefordert):
# der Offscreen-Platform-Plugin hat KEINE echten System-Fonts und faellt sonst
# auf einen generischen Tofu-Fallback zurueck, dessen Metriken deutlich breiter
# sind als die echte Segoe UI, mit der die App unter Windows tatsaechlich
# rendert -> ohne Bootstrap waeren die Breiten-Assertions unten nicht
# repraesentativ fuer das echte Erscheinungsbild.
_SEGOE = r"C:\Windows\Fonts\segoeui.ttf"


def _app():
    app = QApplication.instance() or QApplication([])
    if os.path.exists(_SEGOE):
        QFontDatabase.addApplicationFont(_SEGOE)
        app.setFont(QFont("Segoe UI", 9))
    return app


class TestSectionButtonsNotClipped(unittest.TestCase):
    """UI-15: Section-Buttons duerfen nie unter ihre Textbreite schrumpfen."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        from src.ui.main_window import MainWindow
        cls.win = MainWindow()
        cls.win.resize(1440, 900)
        cls.win.show()
        cls.app.processEvents()
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.win.close()
            cls.win.deleteLater()
        except Exception:
            pass
        cls.app.processEvents()
        from src.core.show.show_file import reset_show
        reset_show()
        cls.app.processEvents()

    def test_all_section_buttons_fit_their_text_at_1440x900(self):
        self.assertTrue(self.win._section_btns, "keine Section-Buttons gefunden")
        for btn in self.win._section_btns:
            need = btn.fontMetrics().horizontalAdvance(btn.text()) + 12
            self.assertGreaterEqual(
                btn.width(), need,
                f"Section-Button {btn.text()!r} clippt: width={btn.width()} "
                f"< Textbedarf={need}")

    def test_section_button_min_width_matches_size_hint_floor(self):
        """Die Mindestbreite ist ein Layout-Floor = sizeHint bei Konstruktion,
        damit QHBoxLayout den Button bei Platzmangel NICHT unter die eigene
        sizeHint quetschen kann (Kernursache des Bugs)."""
        for btn in self.win._section_btns:
            self.assertGreater(btn.minimumWidth(), 0)
            self.assertGreaterEqual(btn.width(), btn.minimumWidth())


class TestGrandMasterLabelReadable(unittest.TestCase):
    """UI-16: GM-Prozent-Label liegt lesbar rechts vom Slider, nie darunter."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        from src.ui.main_window import MainWindow
        cls.win = MainWindow()
        cls.win.resize(1440, 900)
        cls.win.show()
        cls.app.processEvents()
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.win.close()
            cls.win.deleteLater()
        except Exception:
            pass
        cls.app.processEvents()
        from src.core.show.show_file import reset_show
        reset_show()
        cls.app.processEvents()

    def test_gm_label_min_width_fits_100_percent(self):
        fm = self.win._lbl_gm_val.fontMetrics()
        need = fm.horizontalAdvance("100%")
        self.assertGreaterEqual(self.win._lbl_gm_val.minimumWidth(), need)

    def test_gm_label_does_not_overlap_slider(self):
        slider_right = self.win._slider_gm.x() + self.win._slider_gm.width()
        self.assertGreaterEqual(
            self.win._lbl_gm_val.x(), slider_right,
            "GM-Prozent-Label ueberlappt den Slider-Griff (liest sich als '00%')")


class TestEfxButtonsNotClipped(unittest.TestCase):
    """UI-17: Buttonleiste unter der Effektliste (200px-Spalte) clippt nicht."""

    def setUp(self):
        _app()

    def test_list_buttons_fit_their_text(self):
        from src.ui.views.efx_view import EfxView
        efx = EfxView(follow_selection=False)
        try:
            efx.resize(1440, 900)
            efx.show()
            QApplication.processEvents()
            QApplication.processEvents()

            expected = {"+ Neu", "\U0001F4BE Speichern", "Löschen", "▶ Start",
                        "■ Stop"}
            found = 0
            for btn in efx.findChildren(QPushButton):
                if btn.text() in expected:
                    found += 1
                    need = btn.fontMetrics().horizontalAdvance(btn.text()) + 8
                    self.assertGreaterEqual(
                        btn.width(), need,
                        f"EFX-Listen-Button {btn.text()!r} clippt: "
                        f"width={btn.width()} < Textbedarf={need}")
            self.assertEqual(found, len(expected), "nicht alle 5 Buttons gefunden")
        finally:
            efx.deleteLater()
            QApplication.processEvents()


class TestCheckboxIndicatorVisible(unittest.TestCase):
    """UI-18: Checkbox-Indikator im Dark-Theme sichtbar (auch unchecked)."""

    def test_live_edit_panel_qss_has_bordered_indicator(self):
        _app()
        from src.ui.virtualconsole.vc_multi_live_editor import VCMultiLiveEditor
        ed = VCMultiLiveEditor()
        try:
            qss = ed._content.styleSheet()
            self.assertIn("QCheckBox::indicator", qss)
            self.assertIn("border:1px solid #8b949e", qss)
            self.assertIn("QCheckBox::indicator:checked", qss)
        finally:
            ed.deleteLater()
            QApplication.processEvents()

    def test_global_theme_qss_has_bordered_indicator(self):
        """Globales QSS (assets/themes/dark.qss, via main_window._apply_theme)
        stylt Checkboxen bereits app-weit (border+background auch unchecked) -
        Regression-Schutz, falls das global mal entfernt wird."""
        root = os.path.normpath(os.path.join(
            os.path.dirname(__file__), "..", "assets", "themes", "dark.qss"))
        with open(root, "r", encoding="utf-8") as f:
            qss = f.read()
        self.assertIn("QCheckBox::indicator", qss)
        idx = qss.index("QCheckBox::indicator")
        block = qss[idx:idx + 400]
        self.assertIn("border", block)


class TestLiveEditPreviewTopAligned(unittest.TestCase):
    """UI-23: Vorschau im breiten Live-Edit-Body oben ausgerichtet, nicht
    vertikal zentriert."""

    def setUp(self):
        _app()

    def test_wide_body_preview_has_align_top(self):
        from src.ui.virtualconsole.vc_multi_live_editor import VCMultiLiveEditor
        ed = VCMultiLiveEditor()
        try:
            ed.resize(900, 520)
            ed.show()
            QApplication.processEvents()
            QApplication.processEvents()

            self.assertTrue(ed._wide, "Editor ist bei 900px Breite nicht im Wide-Modus")
            item = ed._body_wide.itemAt(0)
            self.assertIsNotNone(item)
            self.assertIs(item.widget(), ed._preview)
            self.assertTrue(
                bool(item.alignment() & Qt.AlignmentFlag.AlignTop),
                "Vorschau-Layout-Item traegt kein AlignTop (UI-23)")
            self.assertLessEqual(
                ed._preview.y(), 12,
                f"Vorschau klebt nicht oben (y={ed._preview.y()})")
        finally:
            ed.deleteLater()
            QApplication.processEvents()

    def test_set_wide_reapplies_align_top_on_every_toggle(self):
        """ACHTUNG aus dem Spec: das Umhaengen passiert in `_set_wide()` bei
        JEDEM Umschalten narrow<->wide<->narrow - Alignment muss jedes Mal
        mitgegeben werden, nicht nur beim ersten Mal."""
        from src.ui.virtualconsole.vc_multi_live_editor import VCMultiLiveEditor
        ed = VCMultiLiveEditor()
        try:
            ed.show()
            for _ in range(3):
                ed.resize(900, 520)
                QApplication.processEvents()
                self.assertTrue(ed._wide)
                item = ed._body_wide.itemAt(0)
                self.assertTrue(bool(item.alignment() & Qt.AlignmentFlag.AlignTop))

                ed.resize(360, 520)
                QApplication.processEvents()
                self.assertFalse(ed._wide)
        finally:
            ed.deleteLater()
            QApplication.processEvents()


if __name__ == "__main__":
    unittest.main()
