"""CDX-77: Handy-Gruppe mit einer absoluten Freeze-Taste.

Eine Effekt-Aktions-Taste „Einfrieren" (``effect_action_key == "freeze"``)
leuchtet, solange ihr Effekt eingefroren ist. Ein Tipp friert ERNEUT ein —
die Taste laesst sich vom Handy also nicht ausschalten. Drueckt das Handy
eine andere Taste derselben Gruppe, muss der Druck abgelehnt werden
(``GRUPPE_BLOCKIERT``): sonst leuchten zwei Kacheln der Gruppe, und die
Regel „hoechstens eine aktiv" ist verletzt. Vorher wurde die neue Taste
trotzdem ausgeloest.
"""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LIGHTOS_PREFS_DIR"] = tempfile.mkdtemp(prefix="lightos_prefs_cdx77_")

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.core import handy_seiten as hs  # noqa: E402
from src.core.app_state import get_state  # noqa: E402
from src.ui.virtualconsole import vc_fernbedienung as vf  # noqa: E402
from src.ui.virtualconsole.vc_button import ButtonAction  # noqa: E402
from src.ui.virtualconsole.vc_canvas import VCCanvas  # noqa: E402

_app = QApplication.instance() or QApplication([])


class HandyGruppeFreezeTest(unittest.TestCase):

    def setUp(self):
        self.fm = get_state().function_manager
        self.fm.stop_all()
        self.canvas = VCCanvas()
        self.efx_frieren = self.fm.new_efx("CDX77 Frieren")
        self.efx_tanz = self.fm.new_efx("CDX77 Tanz")
        self.efx_toggle = self.fm.new_efx("CDX77 Umschalten")
        self.fern = vf.VCFernbedienung(self.canvas)

        def taste(text, x, aktion, fid, key=None):
            w = self.canvas._add_widget("VCButton", QPoint(x, 10))
            w.caption = text
            w.action = aktion
            w.function_id = fid
            if key is not None:
                w.effect_action_key = key
            return w

        self.frieren = taste("Einfrieren", 10, ButtonAction.EFFECT_ACTION,
                             self.efx_frieren.id, "freeze")
        self.umschalten = taste("Einfrieren an/aus", 120, ButtonAction.EFFECT_ACTION,
                                self.efx_toggle.id, "toggle_freeze")
        self.tanz = taste("Tanz", 230, ButtonAction.FUNCTION_TOGGLE, self.efx_tanz.id)
        a = hs.seite_hinzufuegen(hs.leer(), "Party")
        for i, w in enumerate((self.frieren, self.umschalten, self.tanz)):
            a = hs.eintrag_setzen(a, 0, w.widget_id, i, 0)
        self.assertTrue(self.canvas.setze_handy_seiten(a))

    def tearDown(self):
        self.fm.stop_all()
        for f in (self.efx_frieren, self.efx_tanz, self.efx_toggle):
            f._frozen = False
            self.fm.remove(f.id)
        self.canvas.close()
        self.canvas.deleteLater()
        _app.processEvents()

    def _gruppe(self, *widgets):
        ok, grund = self.canvas.handy_gruppe_setzen(
            None, "Effekt", [w.widget_id for w in widgets])
        self.assertTrue(ok, grund)

    def _tipp(self, w):
        return self.fern.aktion(w.widget_id, "umschalten", nur_handy_seiten=True)

    def test_absolute_freeze_taste_blockiert_die_gruppe(self):
        self._gruppe(self.frieren, self.tanz)
        self.assertTrue(self._tipp(self.frieren)["ok"])
        self.assertTrue(self.frieren.leuchtet())
        r = self._tipp(self.tanz)
        self.assertEqual(r, {"ok": False, "fehler": vf.GRUPPE_BLOCKIERT})
        # die neue Taste laeuft nicht, die Freeze-Taste bleibt unveraendert
        self.assertFalse(self.tanz.leuchtet())
        self.assertFalse(self.fm.is_running(self.efx_tanz.id))
        self.assertTrue(self.frieren.leuchtet())
        self.assertTrue(self.efx_frieren._frozen)

    def test_nicht_leuchtende_freeze_taste_stoert_nicht(self):
        self._gruppe(self.frieren, self.tanz)
        r = self._tipp(self.tanz)
        self.assertTrue(r["ok"], r)
        self.assertTrue(self.tanz.leuchtet())
        self.assertFalse(self.frieren.leuchtet())

    def test_umschalt_freeze_taste_geht_normal_aus(self):
        self._gruppe(self.umschalten, self.tanz)
        self.assertTrue(self._tipp(self.umschalten)["ok"])
        self.assertTrue(self.umschalten.leuchtet())
        r = self._tipp(self.tanz)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["gruppe_aus"], [self.umschalten.widget_id])
        self.assertFalse(self.efx_toggle._frozen)
        self.assertEqual([self.umschalten.leuchtet(), self.tanz.leuchtet()],
                         [False, True])

    def test_bleibt_eine_taste_unerwartet_an_wird_nicht_ausgeloest(self):
        """Rueckfallnetz: laesst sich eine Taste trotz Vorpruefung nicht
        ausschalten (leuchtet nach dem Ausschalteversuch weiter), wird der
        neue Druck abgelehnt statt eine zweite Kachel anzuschalten."""
        self._gruppe(self.umschalten, self.tanz)
        self.assertTrue(self._tipp(self.umschalten)["ok"])
        echt = vf._gruppe_aus
        vf._gruppe_aus = lambda w, ausloeser: True        # tut nichts
        try:
            r = self._tipp(self.tanz)
        finally:
            vf._gruppe_aus = echt
        self.assertEqual(r, {"ok": False, "fehler": vf.GRUPPE_BLOCKIERT})
        self.assertFalse(self.tanz.leuchtet())
        self.assertFalse(self.fm.is_running(self.efx_tanz.id))


if __name__ == "__main__":
    unittest.main()
