"""UI-139 (Klick-Test 16.11.2026): Leerzustaende und Texte im Programmer.

* Fund 16: Paletten-Reiter ohne Paletten = grosse schwarze Flaeche ohne
  Hinweis; „+ Neu aufzeichnen“ klein (26 px, auch am Finger).
* Fund 22: Prioritaeten — Gruppenkoepfe „eigene Zahl (9999)  (1)“ mit
  doppelten Klammern, Spalte „Fasst an“ missverstaendlich, leere Zellen in
  „Zustand“/„Verdeckt“ ohne Platzhalter.
* Fund 23: Laser-Abzeichen „Nur Anzeige · schaltet nicht ab“ — es stand nicht
  da, WAS nicht abschaltet. Der Hinweis bleibt (nie wie ein Schutz), sagt
  jetzt aber „den Laser“.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtWidgets import (                                      # noqa: E402
    QApplication, QStyleOptionViewItem,
)

import _ui139_masse as m                                             # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _aufraeumen():
    yield
    destroy_all_top_level_widgets(_app)


class PalettenLeerTest(unittest.TestCase):
    def _seite(self, touch, palettes=()):
        m.touch_setzen(self, touch)
        from src.core.engine.palette import PaletteManager, PaletteType
        from src.ui.views.palette_view import PalettePage
        mgr = PaletteManager()
        mgr._palettes.clear()            # ohne die mitgelieferten Vorgaben
        for p in palettes:
            mgr._palettes.append(p)
        r = m.Rahmen(touch, (700, 400))
        return r, r.zeige(PalettePage(PaletteType.COLOR, mgr)), mgr

    def test_hinweis_ohne_paletten(self):
        for touch in (False, True):
            r, seite, _ = self._seite(touch)
            with self.subTest(touch=touch):
                h = seite._leer_hinweis
                self.assertIsNotNone(h, "kein Leerhinweis")
                self.assertTrue(h.isVisible())
                self.assertIn("Noch keine Paletten", h.text())
                self.assertIn("+ Neu aufzeichnen", h.text())
            r.close()

    def test_suche_ohne_treffer_sagt_das(self):
        from src.core.engine.palette import Palette, PaletteType
        r, seite, _ = self._seite(False, [Palette("Rot", PaletteType.COLOR,
                                                  {"color_r": 255})])
        self.assertIsNone(seite._leer_hinweis)
        seite._search.setText("blau")
        self.assertIn("blau", seite._leer_hinweis.text())
        seite._search.setText("")
        self.assertIsNone(seite._leer_hinweis)

    def test_neu_knopf_am_finger(self):
        r, seite, _ = self._seite(True)
        b = seite._btn_new
        self.assertGreaterEqual(b.height(), 44)
        self.assertTrue(m.text_passt(b))

    def test_neu_knopf_maus_wie_bisher(self):
        r, seite, _ = self._seite(False)
        self.assertLessEqual(seite._btn_new.height(), 32)
        self.assertTrue(m.text_passt(seite._btn_new))


class PrioritaetenTextTest(unittest.TestCase):
    def setUp(self):
        from src.core.engine.function_manager import get_function_manager
        fm = get_function_manager()
        self.fm = fm
        self.szene = fm.new_scene("UI139 Szene")
        self.szene.priority = 9999                     # eigene Zahl
        self.addCleanup(fm.remove, self.szene.id)

    def _ansicht(self):
        from src.ui.views.prioritaeten_view import PrioritaetenView
        r = m.Rahmen(False, m.KLEIN["1366x768"])
        v = r.zeige(PrioritaetenView())
        v.neu_aufbauen()
        return r, v

    def _kopf(self, v, zahl):
        wurzel = v._baum.invisibleRootItem()
        from src.ui.views import prioritaeten_view as pv
        for i in range(wurzel.childCount()):
            k = wurzel.child(i)
            if k.data(0, pv._ROLLE_ZAHL) == zahl:
                return k
        raise AssertionError(f"Gruppe {zahl} fehlt")

    def test_kopf_ohne_doppelte_klammern(self):
        r, v = self._ansicht()
        k = self._kopf(v, 9999)
        self.assertEqual(k.text(0), "eigene Zahl (9999) · 1 Effekt")
        self.assertNotIn(")  (", k.text(0))
        leer = self._kopf(v, 60)                         # Notfall: meist leer
        self.assertTrue(leer.text(0).startswith("Notfall · "), leer.text(0))
        self.assertRegex(leer.text(0), r"· \d+ Effekte?$")

    def test_spalte_heisst_betrifft(self):
        r, v = self._ansicht()
        self.assertEqual(v._baum.headerItem().text(2), "Betrifft")

    def test_leere_zellen_zeigen_platzhalter(self):
        r, v = self._ansicht()
        zeile = next(it for it in v._effekt_zeilen() if it.text(0) == "UI139 Szene")
        self.assertEqual(zeile.text(3), "", "Laufzustand bleibt in den Daten leer")
        idx = v._baum.indexFromItem(zeile, 3)
        opt = QStyleOptionViewItem()
        v._baum.itemDelegateForIndex(idx).initStyleOption(opt, idx)
        self.assertEqual(opt.text, "—")
        idx4 = v._baum.indexFromItem(zeile, 4)
        opt4 = QStyleOptionViewItem()
        v._baum.itemDelegateForIndex(idx4).initStyleOption(opt4, idx4)
        self.assertEqual(opt4.text, "—")
        # Gruppenkoepfe bekommen keinen Platzhalter
        kidx = v._baum.indexFromItem(self._kopf(v, 9999), 3)
        optk = QStyleOptionViewItem()
        v._baum.itemDelegateForIndex(kidx).initStyleOption(optk, kidx)
        self.assertEqual(optk.text, "")


class LaserHinweisTest(unittest.TestCase):
    def test_sagt_was_nicht_abschaltet(self):
        from src.ui.views import laser_view as lv
        self.assertIn("Nur Anzeige", lv.NUR_ANZEIGE)
        self.assertIn("schaltet den Laser nicht ab", lv.NUR_ANZEIGE)


if __name__ == "__main__":
    unittest.main()
