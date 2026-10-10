"""VCB-41: zwei Knoepfe im Solo-Rahmen mit DERSELBEN Funktion.

Liegt dieselbe Funktion auf zwei Knoepfen eines Solo-Rahmens, stoppte der
Zwilling sie beim Ausschalten ueber ``deactivate_for_solo`` — und der
gedrueckte Knopf sah sie danach als „steht" und startete sie sofort neu.
Ein/Aus muss sich wie bei einem einzelnen Knopf verhalten.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.ui.virtualconsole.vc_button import ButtonAction, VCButton
from src.ui.virtualconsole.vc_frame import VCFrame

_app = QApplication.instance() or QApplication([])


class SoloFrameZwillingTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_state().function_manager
        self.fm.stop_all()
        self.f = self.fm.new_efx("VCB41 Regen Bogen")
        self.g = self.fm.new_efx("VCB41 Andere")
        self.h = self.fm.new_efx("VCB41 Dritte")
        self.frame = VCFrame("Hintergrund")
        self.frame.set_solo(True)
        self.btn_links = self._button("Links", self.f.id)
        self.btn_rechts = self._button("Rechts", self.f.id)

    def tearDown(self):
        self.fm.stop_all()
        for fn in (self.f, self.g, self.h):
            self.fm.remove(fn.id)

    def _button(self, caption, fid, action=ButtonAction.FUNCTION_TOGGLE):
        btn = VCButton(caption, parent=self.frame)
        btn.action = action
        btn.function_id = fid
        return btn

    def _druck(self, btn):
        btn._trigger(True)
        btn._trigger(False)

    def test_gleiche_funktion_an_und_aus_ueber_denselben_knopf(self):
        self._druck(self.btn_links)
        self.assertTrue(self.fm.is_running(self.f.id))
        self._druck(self.btn_links)
        self.assertFalse(self.fm.is_running(self.f.id))

    def test_gleiche_funktion_aus_ueber_den_zwilling(self):
        self._druck(self.btn_links)
        self.assertTrue(self.fm.is_running(self.f.id))
        self._druck(self.btn_rechts)
        self.assertFalse(self.fm.is_running(self.f.id))
        self._druck(self.btn_rechts)
        self.assertTrue(self.fm.is_running(self.f.id))

    def test_zwilling_stoppt_nur_die_nicht_geteilten_gruppenmitglieder(self):
        # Rechts steuert F + G; Links nur F. Links aus -> F steht, G (nur
        # Rechts) wird wie bisher per Solo gestoppt.
        self.btn_rechts.function_ids = [self.g.id]
        self._druck(self.btn_rechts)
        self.assertTrue(self.fm.is_running(self.f.id))
        self.assertTrue(self.fm.is_running(self.g.id))
        self._druck(self.btn_links)
        self.assertFalse(self.fm.is_running(self.f.id))
        self.assertFalse(self.fm.is_running(self.g.id))

    def test_verschiedene_funktionen_solo_unveraendert(self):
        andere = self._button("Andere", self.g.id)
        self._druck(self.btn_links)
        self.assertTrue(self.fm.is_running(self.f.id))
        self._druck(andere)
        self.assertFalse(self.fm.is_running(self.f.id))
        self.assertTrue(self.fm.is_running(self.g.id))
        self._druck(andere)
        self.assertFalse(self.fm.is_running(self.g.id))

    def test_anderer_knopf_ohne_funktion_stoppt_weiterhin(self):
        # Ein Knopf mit anderer Aktion (kein Funktions-Knopf) schuetzt nichts.
        dritte = self._button("Dritte", self.h.id, ButtonAction.FUNCTION_FLASH)
        self._druck(self.btn_links)
        dritte._trigger(True)
        self.assertFalse(self.fm.is_running(self.f.id))
        self.assertTrue(self.fm.is_running(self.h.id))
        dritte._trigger(False)
        self.assertFalse(self.fm.is_running(self.h.id))


if __name__ == "__main__":
    unittest.main()
