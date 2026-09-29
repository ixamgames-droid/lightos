"""UI-58: der BLACKOUT-Knopf der Kopfzeile zeigt den ECHTEN Zustand.

Gemessen im Stabilitaets-Durchlauf 2026-08-31: Kopf-Klick -> Blackout an; extern
(VC-Taster/Web/OSC/Kommandozeile) aus -> Knopf blieb eingerastet; naechster
Kopf-Klick machte NICHTS dunkel, erst der dritte wieder.
"""
import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                          # noqa: E402

from src.core.app_state import get_state                             # noqa: E402
from src.core.dmx.output_manager import OutputManager               # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


class ManagerMeldetTest(unittest.TestCase):

    def test_meldet_nur_aenderungen(self):
        om = OutputManager.__new__(OutputManager)
        om._blackout = False
        om._blackout_callbacks = []
        gehoert = []
        om.subscribe_blackout(gehoert.append)
        om.set_blackout(True)
        om.set_blackout(True)
        om.set_blackout(False)
        self.assertEqual(gehoert, [True, False])
        om.unsubscribe_blackout(gehoert.append)
        om.set_blackout(True)
        self.assertEqual(gehoert, [True, False])
        self.assertTrue(om.blackout)

    def test_kaputter_abonnent_stoppt_nicht(self):
        om = OutputManager.__new__(OutputManager)
        om._blackout = False
        om._blackout_callbacks = []
        gehoert = []
        om.subscribe_blackout(lambda _an: 1 / 0)
        om.subscribe_blackout(gehoert.append)
        om.set_blackout(True)
        self.assertTrue(om._blackout)
        self.assertEqual(gehoert, [True])


class KopfzeilenKnopfTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _app()
        from src.ui.main_window import MainWindow
        cls.w = MainWindow()
        cls.om = get_state().output_manager

    @classmethod
    def tearDownClass(cls):
        cls.om.set_blackout(False)
        cls.w.deleteLater()
        _app().processEvents()

    def setUp(self):
        self.om.set_blackout(False)
        _app().processEvents()

    def test_der_gemessene_ablauf(self):
        btn = self.w._btn_blackout
        btn.click()                                   # Kopf: an
        self.assertTrue(self.om.blackout)
        self.om.set_blackout(False)                   # extern aus (VC/Web/OSC)
        _app().processEvents()
        self.assertFalse(btn.isChecked(), "Knopf folgt dem echten Zustand")
        btn.click()                                   # naechster Druck: wieder dunkel
        self.assertTrue(self.om.blackout)
        self.assertTrue(btn.isChecked())

    def test_extern_an_zeigt_der_knopf(self):
        self.om.set_blackout(True)
        _app().processEvents()
        self.assertTrue(self.w._btn_blackout.isChecked())
        self.assertIn("#cc0000", self.w._btn_blackout.styleSheet())

    def test_aus_fremdem_thread(self):
        """Web/OSC schalten aus ihrem Thread — der Knopf wird im UI-Thread
        nachgefuehrt (queued), nie im Fremd-Thread angefasst."""
        t = threading.Thread(target=self.om.set_blackout, args=(True,))
        t.start()
        t.join()
        _app().processEvents()
        self.assertTrue(self.w._btn_blackout.isChecked())


if __name__ == "__main__":
    unittest.main()
