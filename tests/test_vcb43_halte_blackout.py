"""VCB-43: eine gehaltene Blackout-Taste hebt keinen fremden Blackout auf.

Befund (Audit QA-96): die VC-Blackout-Taste ohne Ziel rief beim Druecken
``set_blackout(True)`` und beim Loslassen ``set_blackout(False)`` — Loslassen
schaltete IMMER aus, egal wer eingeschaltet hatte. Stand am Pult der Blackout
(Knopf oben rechts) und jemand tippte die VC-Taste an, wurde es beim Loslassen
hell.

Jetzt gilt: es ist dunkel, solange IRGENDEINE Quelle dunkel will.

* Der SCHALTER (Kopfzeile, Web, OSC, Kommandozeile, Skript) bleibt
  ``set_blackout``.
* Eine gehaltene Taste belegt einen eigenen Platz (``halte_blackout``) und
  nimmt beim Loslassen nur den wieder weg.
* ``blackout`` — und damit der Knopf oben rechts — zeigt, ob es WIRKLICH dunkel
  ist.

Es wird nichts gesendet (kein Ausgang eingerichtet, kein Ausgabe-Thread).
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                          # noqa: E402

from src.core.app_state import get_state                             # noqa: E402
from src.core.dmx.output_manager import OutputManager               # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


def _halter_loesen(om):
    """Aufraeumen zwischen den Faellen — auch auf einem Stand ohne die Halter
    (dann zeigt der Fall selbst, was fehlt, nicht sein Aufbau)."""
    getattr(om, "loese_alle_halte_blackouts", lambda: None)()


def _manager():
    """Manager ohne Ausgaenge — nur Schalter, Halter und Meldungen."""
    om = OutputManager.__new__(OutputManager)
    om._blackout = False
    om._blackout_callbacks = []
    return om


class ManagerTest(unittest.TestCase):

    def setUp(self):
        self.om = _manager()
        self.gehoert = []
        self.om.subscribe_blackout(self.gehoert.append)

    def test_halten_allein_ist_dunkel_bis_zum_loslassen(self):
        self.om.halte_blackout("taste", True)
        self.assertTrue(self.om.blackout)
        self.om.halte_blackout("taste", False)
        self.assertFalse(self.om.blackout)
        self.assertEqual(self.gehoert, [True, False])

    def test_loslassen_hebt_den_schalter_nicht_auf(self):
        """Der Fall aus dem Befund."""
        self.om.set_blackout(True)                      # Pult: Blackout steht
        self.om.halte_blackout("taste", True)           # jemand tippt die VC-Taste an
        self.om.halte_blackout("taste", False)          # … und laesst los
        self.assertTrue(self.om.blackout, "es wurde hell, obwohl der Blackout am Pult steht")
        self.assertEqual(self.gehoert, [True])          # die Anzeige flackert nicht

    def test_schalter_aus_waehrend_gehalten_bleibt_dunkel(self):
        """Der Knopf oben rechts bleibt wahr: wer ihn bei gehaltener Taste
        ausschaltet, bekommt „dunkel“ zurueckgemeldet — und hell wird es erst
        beim Loslassen."""
        self.om.set_blackout(True)
        self.om.halte_blackout("taste", True)
        self.gehoert.clear()
        self.om.set_blackout(False)                     # Klick auf den Knopf oben rechts
        self.assertTrue(self.om.blackout)
        self.assertEqual(self.gehoert, [True])          # Rueckmeldung: es ist noch dunkel
        self.om.halte_blackout("taste", False)
        self.assertFalse(self.om.blackout)
        self.assertEqual(self.gehoert, [True, False])

    def test_zwei_tasten_dunkel_bis_die_letzte_loslaesst(self):
        self.om.halte_blackout("a", True)
        self.om.halte_blackout("b", True)
        self.om.halte_blackout("a", False)
        self.assertTrue(self.om.blackout)
        self.om.halte_blackout("b", False)
        self.assertFalse(self.om.blackout)
        self.assertEqual(self.gehoert, [True, False])

    def test_doppeltes_druecken_und_loslassen_schadet_nicht(self):
        self.om.halte_blackout("a", True)
        self.om.halte_blackout("a", True)               # MIDI sendet NoteOn doppelt
        self.om.halte_blackout("a", False)
        self.assertFalse(self.om.blackout)
        self.om.halte_blackout("a", False)              # Loslassen ohne Druecken
        self.om.halte_blackout("nie gedrueckt", False)
        self.assertFalse(self.om.blackout)
        self.assertEqual(self.gehoert, [True, False])

    def test_schalter_meldet_weiter_nur_aenderungen(self):
        self.om.set_blackout(True)
        self.om.set_blackout(True)
        self.om.set_blackout(False)
        self.assertEqual(self.gehoert, [True, False])

    def test_alle_halter_loesen(self):
        """Show-Wechsel: gehaltene Tasten der alten Show duerfen nicht als
        unsichtbarer Dauer-Blackout stehen bleiben; der Schalter bleibt."""
        self.om.halte_blackout("a", True)
        self.om.halte_blackout("b", True)
        self.om.loese_alle_halte_blackouts()
        self.assertFalse(self.om.blackout)
        self.om.set_blackout(True)
        self.om.halte_blackout("a", True)
        self.om.loese_alle_halte_blackouts()
        self.assertTrue(self.om.blackout)

    def test_epoche_zaehlt_nur_den_schalter(self):
        """Der Schutz der Skripte (OUT-57) haengt an der Epoche: ein Skript nimmt
        seinen Blackout nur zurueck, wenn seither niemand den SCHALTER bewegt hat.
        Eine angetippte Taste bewegt ihn nicht."""
        self.om.set_blackout(True)
        epoche = self.om.blackout_epoch
        self.om.halte_blackout("taste", True)
        self.om.halte_blackout("taste", False)
        self.assertEqual(self.om.blackout_epoch, epoche)
        self.om.set_blackout(False)
        self.assertEqual(self.om.blackout_epoch, epoche + 1)

    def test_manager_ohne_init_kennt_keine_halter(self):
        """Tests bauen den Manager teils per ``__new__`` — ohne Halter-Menge."""
        self.assertFalse(self.om.blackout)
        self.om.set_blackout(True)
        self.assertTrue(self.om.blackout)


class SendePfadTest(unittest.TestCase):
    """Gehalten heisst: der gesendete Frame ist dunkel — nicht nur die Anzeige."""

    def setUp(self):
        self.om = OutputManager()
        self.om.add_universe(1)
        self.om.grand_master = 1.0
        self.om.universes[1].set_channel(1, 200)

    def _frame(self):
        self.om._send_all()
        return self.om._display_frame[1]

    def test_gehaltene_taste_macht_den_frame_dunkel(self):
        self.assertEqual(self._frame()[0], 200)
        self.om.halte_blackout("taste", True)
        self.assertEqual(self._frame()[0], 0)
        self.om.halte_blackout("taste", False)
        self.assertEqual(self._frame()[0], 200)

    def test_schalter_und_taste_zusammen(self):
        self.om.set_blackout(True)
        self.om.halte_blackout("taste", True)
        self.om.halte_blackout("taste", False)
        self.assertEqual(self._frame()[0], 0)           # der Schalter haelt weiter dunkel
        self.om.set_blackout(False)
        self.assertEqual(self._frame()[0], 200)


class VcTasteTest(unittest.TestCase):
    """Die echte VC-Taste (Aktion Blackout, ohne Ziel) gegen den echten Zustand."""

    @classmethod
    def setUpClass(cls):
        _app()
        cls.om = get_state().output_manager

    def setUp(self):
        from src.ui.virtualconsole.vc_button import ButtonAction, VCButton
        self.om.set_blackout(False)
        _halter_loesen(self.om)
        self.taste = VCButton("BLACKOUT")
        self.taste.action = ButtonAction.BLACKOUT
        self.gehoert = []
        self.om.subscribe_blackout(self.gehoert.append)

    def tearDown(self):
        self.om.unsubscribe_blackout(self.gehoert.append)
        self.taste._trigger_primary(False)
        self.taste.deleteLater()
        self.om.set_blackout(False)
        _halter_loesen(self.om)
        _app().processEvents()

    def test_antippen_bei_stehendem_blackout_laesst_es_dunkel(self):
        self.om.set_blackout(True)                      # Knopf oben rechts
        self.taste._trigger_primary(True)
        self.taste._trigger_primary(False)
        self.assertTrue(self.om.blackout, "Loslassen der VC-Taste hat den Blackout aufgehoben")
        self.assertEqual(self.gehoert, [True])

    def test_halten_ohne_stehenden_blackout_wie_bisher(self):
        self.taste._trigger_primary(True)
        self.assertTrue(self.om.blackout)
        self.taste._trigger_primary(False)
        self.assertFalse(self.om.blackout)

    def test_geloeschte_taste_gibt_ihren_platz_frei(self):
        """Wird die Taste entfernt, waehrend sie gehalten ist (Layout laden,
        Bank wechseln), bleibt kein Blackout ohne Besitzer stehen."""
        from src.ui.virtualconsole import vc_button
        self.taste._trigger_primary(True)
        self.assertTrue(self.om.blackout)
        vc_button._loese_halte_blackout(id(self.taste))     # was ``destroyed`` ruft
        self.assertFalse(self.om.blackout)

    def test_show_wechsel_loest_gehaltene_tasten(self):
        from src.core.show.show_file import reset_show
        self.taste._trigger_primary(True)
        self.assertTrue(self.om.blackout)
        reset_show()
        self.assertFalse(self.om.blackout)


class KopfzeileTest(unittest.TestCase):
    """Der Knopf oben rechts zeigt, ob es dunkel IST."""

    @classmethod
    def setUpClass(cls):
        _app()
        from src.ui.main_window import MainWindow
        cls.w = MainWindow()
        cls.om = get_state().output_manager

    @classmethod
    def tearDownClass(cls):
        cls.om.set_blackout(False)
        _halter_loesen(cls.om)
        cls.w.deleteLater()
        _app().processEvents()

    def setUp(self):
        self.om.set_blackout(False)
        _halter_loesen(self.om)
        _app().processEvents()

    def test_knopf_bleibt_an_solange_eine_taste_haelt(self):
        btn = self.w._btn_blackout
        self.om.halte_blackout("taste", True)
        _app().processEvents()
        self.assertTrue(btn.isChecked())                # dunkel -> Knopf an
        btn.click()                                     # jemand will „aus“
        _app().processEvents()
        self.assertTrue(self.om.blackout)
        self.assertTrue(btn.isChecked(), "der Knopf zeigt hell, obwohl eine Taste dunkel haelt")
        self.om.halte_blackout("taste", False)
        _app().processEvents()
        self.assertFalse(self.om.blackout)
        self.assertFalse(btn.isChecked())


if __name__ == "__main__":
    unittest.main()
