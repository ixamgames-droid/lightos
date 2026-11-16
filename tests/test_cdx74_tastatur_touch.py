"""CDX-74: Bildschirmtastatur und Touch-Masse (Codex-Ernte, bestaetigt).

1. Abbruch der Bildschirmtastatur muss auch das ``textEdited``-Modell
   zuruecksetzen (``setText`` allein sendet kein ``textEdited``) — fuer
   „Abbruch“ und fuer das Schliessen per Tipp daneben.
2. Ein sehr langer Feldinhalt darf die Tastatur nicht ueber den Bildschirm
   hinaus aufblasen.
3. Snap-Editor-Tabellen sind auf Inhaltshoehe fixiert; im Touch-Modus hebt
   ``_touch_masse`` die Zeilen auf 44 px — die feste Hoehe muss mitwachsen.

Bedient wird mit dem Finger (``QTest.touchEvent``), wie am Geraet.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                          # noqa: E402
from PySide6.QtCore import QPoint                                      # noqa: E402
from PySide6.QtTest import QTest                                       # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget  # noqa: E402

from src.ui import bildschirm_tastatur as bt                           # noqa: E402
from src.ui import touch_keyboard as tk                                # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets               # noqa: E402

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _keine_fenster_mitnehmen():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _finger_tipp(widget, punkt: QPoint | None = None):
    dev = QTest.createTouchDevice()
    win = widget.window()
    p = widget.mapTo(win, punkt if punkt is not None else widget.rect().center())
    QTest.touchEvent(win, dev).press(0, p, win).commit()
    QTest.touchEvent(win, dev).release(0, p, win).commit()
    QApplication.processEvents()


class _TouchBasis(unittest.TestCase):
    def setUp(self):
        alt = tk.is_touch_mode()
        self.addCleanup(tk.setze_touch_modus, alt)
        tk.install(_app, touch=True)
        alt_app = bt.APP_TEXT_TASTATUR
        bt.APP_TEXT_TASTATUR = True
        self.addCleanup(setattr, bt, "APP_TEXT_TASTATUR", alt_app)


class AbbruchTextEditedTest(_TouchBasis):
    def setUp(self):
        super().setUp()
        self.w = QWidget()
        lay = QVBoxLayout(self.w)
        self.feld = QLineEdit("Sperrzone A")
        lay.addWidget(self.feld)
        self.w.resize(420, 200)
        self.w.show()
        QApplication.processEvents()
        self.addCleanup(self.w.close)
        # Modell wie im Sperrzonen-Planer: haengt nur an textEdited.
        self.modell = ["Sperrzone A"]
        self.feld.textEdited.connect(self.modell.append)
        self.feld.end(False)
        self.kb = bt.Bildschirmtastatur(self.feld)
        self.kb.zeigen()
        QApplication.processEvents()

    def _taste(self, klein):
        return next(t for t in self.kb._buchstaben if t.property("klein") == klein)

    def test_abbruch_per_finger_setzt_modell_zurueck(self):
        _finger_tipp(self._taste("x"))
        self.assertEqual(self.modell[-1], "Sperrzone Ax")
        _finger_tipp(self.kb.btn_abbruch)
        self.assertEqual(self.feld.text(), "Sperrzone A")
        self.assertEqual(self.modell[-1], "Sperrzone A")

    def test_schliessen_per_tipp_daneben_setzt_modell_zurueck(self):
        _finger_tipp(self._taste("q"))
        self.assertEqual(self.modell[-1], "Sperrzone Aq")
        # Qt schliesst ein Popup beim Tipp daneben ueber hide() -> hideEvent.
        self.kb.hide()
        QApplication.processEvents()
        self.assertEqual(self.feld.text(), "Sperrzone A")
        self.assertEqual(self.modell[-1], "Sperrzone A")

    def test_fertig_laesst_modell_stehen(self):
        _finger_tipp(self._taste("y"))
        _finger_tipp(self.kb.btn_fertig)
        self.assertEqual(self.feld.text(), "Sperrzone Ay")
        self.assertEqual(self.modell[-1], "Sperrzone Ay")

    def test_abbruch_ohne_aenderung_sendet_nichts(self):
        n = len(self.modell)
        self.kb.abbrechen()
        QApplication.processEvents()
        self.assertEqual(len(self.modell), n)


class LangerFeldinhaltTest(_TouchBasis):
    def test_tastatur_bleibt_auf_dem_bildschirm(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        feld = QLineEdit("/sehr/langer/pfad/" * 25)        # ~450 Zeichen
        lay.addWidget(feld)
        w.resize(420, 120)
        w.move(0, 0)
        w.show()
        QApplication.processEvents()
        self.addCleanup(w.close)
        kb = bt.Bildschirmtastatur(feld)
        kb.zeigen()
        QApplication.processEvents()
        self.addCleanup(lambda: bt._gueltig(kb) and kb.close())
        frei = (feld.screen() or QApplication.primaryScreen()).availableGeometry()
        self.assertLessEqual(kb.width(), frei.width())
        self.assertTrue(frei.contains(kb.frameGeometry()),
                        f"{kb.frameGeometry()} nicht in {frei}")
        # Das Ende des Textes (dort steht der Cursor) bleibt sichtbar.
        self.assertTrue(kb.anzeige.text().endswith("pfad/"), kb.anzeige.text()[-20:])
        # Tasten weiter erreichbar: Fertig liegt ganz im Bildschirm.
        oben_links = kb.btn_fertig.mapToGlobal(QPoint(0, 0))
        self.assertTrue(frei.contains(oben_links))
        self.assertTrue(frei.contains(oben_links + QPoint(kb.btn_fertig.width() - 1,
                                                          kb.btn_fertig.height() - 1)))
        # Fertig schliesst per Finger (Popup loescht sich beim Schliessen)
        _finger_tipp(kb.btn_fertig)
        self.assertFalse(bt._gueltig(kb) and kb.isVisible())

    def test_kurzer_text_unveraendert(self):
        w = QWidget()
        QVBoxLayout(w).addWidget(feld := QLineEdit("PAR 1"))
        w.show()
        QApplication.processEvents()
        self.addCleanup(w.close)
        kb = bt.Bildschirmtastatur(feld)
        kb.zeigen()
        QApplication.processEvents()
        self.addCleanup(kb.close)
        self.assertEqual(kb.anzeige.text(), "PAR 1")


class SnapEditorTouchHoeheTest(_TouchBasis):
    def _editor(self):
        from src.core.engine.snap_library import SnapLibrary
        from src.ui.views.snap_editor import SnapEditor
        lib = SnapLibrary()
        snap = lib.add_snap("CDX74", "", {1: {"intensity": 255, "color_r": 128,
                                              "color_g": 10}})
        ed = SnapEditor(snap)
        ed.resize(700, 600)
        ed.show()
        QApplication.processEvents()
        self.addCleanup(ed.close)
        return ed

    def test_tabelle_waechst_mit_touch_zeilen(self):
        ed = self._editor()
        self.assertTrue(ed._tables)
        tbl = ed._tables[0]
        self.assertEqual(tbl.rowCount(), 3)
        for r in range(3):
            self.assertGreaterEqual(tbl.rowHeight(r), tk.TABELLEN_ZEILE)
        hh = tbl.horizontalHeader()
        self.assertGreaterEqual(tbl.height(), hh.height() + 3 * tk.TABELLEN_ZEILE)
        # letzte Zeile ganz im sichtbaren Bereich der Tabelle
        unten = tbl.rowViewportPosition(2) + tbl.rowHeight(2)
        self.assertLessEqual(unten, tbl.viewport().height())

    def test_ohne_touch_bleibt_hoehe_fuer_30px(self):
        tk.setze_touch_modus(False)
        ed = self._editor()
        tbl = ed._tables[0]
        self.assertEqual(tbl.rowHeight(0), 30)
        unten = tbl.rowViewportPosition(2) + tbl.rowHeight(2)
        self.assertLessEqual(unten, tbl.viewport().height())
        self.assertLess(tbl.height(), tbl.horizontalHeader().height() + 3 * 44)


if __name__ == "__main__":
    unittest.main()
