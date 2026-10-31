"""VIZ-75 — die Liste „Bühnen-Elemente“ im Reiter Bühne zeigt mindestens vier Zeilen.

**Der Fehler (DOC-59, Bild ``02_buehne_bauen.png``):** ueber „Element
hinzufuegen“ und „Eigenschaften (Selektion)“ blieb der Liste etwa 1,5 Zeilen
Hoehe; schon die zweite Zeile war halb abgeschnitten.

**Ursache:** der Reiter liegt in einem Scrollbereich (VIZ-55). Die beiden
Gruppen darunter sind zusammen hoeher als die Spalte, der Reiter ist also
ohnehin hoeher als sein Sichtfenster — und dann bekommt die Liste trotz
Streckfaktor nur ihre Mindesthoehe, die bei einer QTreeWidget kaum mehr als
Kopfzeile plus eine Zeile ist.

**Abnahme:** Fenster 1800×950, acht Elemente (wie die Doku-Bühne), ganz oben
im Reiter: mindestens vier Zeilen ganz sichtbar. Gemessen wird in Zeilen der
Liste selbst, damit die Ersatzschrift der Testumgebung nichts verfaelscht.

**Theme/Touch:** das Hauptfenster ist Eltern des Visualizers, sein Stylesheet
(``assets/themes/dark.qss``, im Touch-Modus zusaetzlich ``min-height: 36px``
je Zeile) wirkt also auf die Liste. Eine fest aus der Schrift gerechnete
Mindesthoehe reichte dort nur fuer 4 bzw. 3 Zeilen — darum laeuft die
Abnahme auch mit beiden Stylesheets und mit einem Wechsel zur Laufzeit.
"""
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QScrollArea, QTreeWidgetItem

from src.ui.visualizer import visualizer_window as VW

_FENSTER_B, _FENSTER_H = 1800, 950
# Breiteste rechte Spalte (Splitter des Fensters, s. test_viz108).
_SPALTE_B = 420
_ELEMENTE = 8
_MIN_ZEILEN = 4

_DARK_QSS = (Path(__file__).resolve().parents[1] / "assets" / "themes" / "dark.qss"
             ).read_text(encoding="utf-8")
# Spiegel des Touch-Overrides aus MainWindow._apply_theme (nur die Zeilen-Regel).
_TOUCH_QSS = _DARK_QSS + (
    "\nQListWidget::item, QTreeWidget::item, QTableWidget::item { "
    "min-height: 36px; padding: 6px; }\n")


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class _NurRechteSpalte(VW.VisualizerWindow):
    """Baut nur die rechte Spalte — ohne Web-Ansicht (Muster: test_viz108)."""

    def __init__(self):
        VW.QMainWindow.__init__(self)
        self._state = VW.get_state()
        self._suppress_property_signals = False
        self._stage_dirty = False
        self._build_tool = "edit"
        self._selected_stage_id = ""
        self._current_stage = VW.get_default_simple()
        self.spalte = self._build_right_panel()
        self.setCentralWidget(self.spalte)
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)

    def _on_tab_changed(self, *_a):
        pass

    def showEvent(self, event):
        VW.QMainWindow.showEvent(self, event)


class BuehnenElementeHoeheTest(unittest.TestCase):
    QSS = ""

    @classmethod
    def setUpClass(cls):
        _app().setStyleSheet(cls.QSS)
        cls.fenster = _NurRechteSpalte()
        cls.fenster.spalte.setFixedWidth(_SPALTE_B)
        # Das echte Fenster hat ueber/unter der Spalte noch Werkzeug- und
        # Statusleiste; die Spalte bekommt hier also eher MEHR Hoehe als echt.
        cls.fenster.resize(_FENSTER_B, _FENSTER_H)
        cls.fenster.show()
        tabs = cls.fenster._tabs
        for i in range(tabs.count()):
            if tabs.tabText(i) == "Bühne":
                tabs.setCurrentIndex(i)
                cls.bereich = tabs.widget(i)
                break
        else:
            raise AssertionError("Reiter Bühne fehlt")
        baum = cls.fenster._stage_tree
        for n in range(_ELEMENTE):
            baum.addTopLevelItem(QTreeWidgetItem(["Truss horiz.", f"Element {n + 1}"]))
        QApplication.processEvents()
        cls.bereich.verticalScrollBar().setValue(0)
        QApplication.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.fenster.hide()
        cls.fenster.deleteLater()
        _app().setStyleSheet("")

    def _ganz_sichtbare_zeilen(self) -> int:
        baum = self.fenster._stage_tree
        vp = baum.viewport()
        assert isinstance(self.bereich, QScrollArea)
        sicht = self.bereich.viewport()
        # Ausschnitt der Liste, der im Sichtfenster des Reiters liegt —
        # in Koordinaten des Listen-Viewports.
        oben_links = vp.mapFrom(sicht, QPoint(0, 0))
        sicht_rect = sicht.rect().translated(oben_links)
        frei = vp.rect().intersected(sicht_rect)
        zaehler = 0
        for i in range(baum.topLevelItemCount()):
            r = baum.visualItemRect(baum.topLevelItem(i))
            if r.isValid() and frei.contains(r):
                zaehler += 1
        return zaehler

    def test_mindestens_vier_zeilen_sichtbar(self):
        """★ Vorher gut eine Zeile; die zweite war halb abgeschnitten."""
        self.assertGreaterEqual(self._ganz_sichtbare_zeilen(), _MIN_ZEILEN)

    def test_gruppen_bleiben_per_bildlauf_erreichbar(self):
        """Die Liste waechst auf Kosten der Reiter-Hoehe, nicht der Gruppen:
        der Scrollbereich traegt den Rest (VIZ-55)."""
        f = self.fenster
        inhalt = self.bereich.widget()
        unten = f._stage_color_btn.mapTo(inhalt, QPoint(0, f._stage_color_btn.height()))
        self.assertLessEqual(unten.y(), inhalt.height())
        self.assertGreater(f._stage_color_btn.height(), 0)



class BuehnenElementeHoeheDarkTest(BuehnenElementeHoeheTest):
    QSS = _DARK_QSS


class BuehnenElementeHoeheTouchTest(BuehnenElementeHoeheTest):
    QSS = _TOUCH_QSS


class BuehnenElementeHoeheWechselTest(BuehnenElementeHoeheTest):
    """Touch-Modus wird erst NACH dem Aufbau eingeschaltet (Einstellungen)."""
    QSS = _DARK_QSS

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _app().setStyleSheet(_TOUCH_QSS)
        QApplication.processEvents()
        cls.bereich.verticalScrollBar().setValue(0)
        QApplication.processEvents()


if __name__ == "__main__":
    unittest.main()
