"""LAS-36: Der Laser-NOT-AUS loest sich NUR ueber die Rueckfrage am festen Knopf.

Befund S-01 (Audit des Bedientests QA-96): ``set_programmer_value`` hob den
Latch auf, sobald irgendwo ein ausgaberelevanter Laser-Wert gesetzt wurde
(shutter/laser_bank/gobo_wheel/macro). Damit liess sich die Rueckfrage aus
LAS-31 („Nur loesen, wenn der Strahlbereich frei ist“) umgehen — Laser-Tab,
VC-Fader, Snap-/Muster-Taste, Rueckgaengig und der MIDI-Regler „Programmer
Attribut“, der ohne Auswahl auf ALLE gepatchten Geraete schreibt.

Jetzt gilt: ein Laser-Wert bei stehendem NOT-AUS wird gemerkt, der Latch
bleibt, die Ausgabe bleibt auf den Aus-Werten. Geloest wird allein ueber
``AppState.laser_notaus_loesen`` — und das ruft die Oberflaeche nur nach der
Rueckfrage (``src/ui/laser_notaus.py``).

Echter Render-Pfad wie in LAS-31: ``_render_frame`` -> ``_send_all`` ->
Display-Frame.
"""
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

from PySide6.QtWidgets import QMessageBox                            # noqa: E402

import src.core.app_state as A                                       # noqa: E402
import src.core.midi.midi_mapper as mm                               # noqa: E402
import src.ui.main_window as MW                                      # noqa: E402
import test_las31_notaus_kopfleiste as l31                           # noqa: E402

_AUS, _MANUAL = l31._AUS, l31._MANUAL
_LASER_FID, _PAR_FID = 7, 9
# Betriebsart auf Adresse 10 (Index 9), Musterbank auf 11 (Index 10).
_I_SHUTTER, _I_BANK = 9, 10


class _Kern(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: l31._CHANNELS[fx.fid]
        self.addCleanup(setattr, A, "get_channels_for_patched", self._orig)
        self.st, self.om = l31._make_state()

    def _frame(self):
        self.st._render_frame(0.025)
        self.om._send_all()
        return self.om._display_frame[1]


class LaserWertLoestNichtTest(_Kern):
    """Kern von S-01: kein Programmer-Wert hebt den NOT-AUS auf."""

    def test_kein_laser_attribut_loest_den_latch(self):
        for attr in ("shutter", "laser_bank", "gobo_wheel", "macro",
                     "shutter#1", "gobo_wheel#1", "laser_x", "intensity"):
            with self.subTest(attr=attr):
                self.st.set_laser_estop(True)
                self.st.set_programmer_value(_LASER_FID, attr, 200)
                self.assertTrue(self.st.laser_estop_active,
                                f"{attr} hat den NOT-AUS ohne Rueckfrage geloest")
                self.assertTrue(self.om._laser_estop_aktiv,
                                "Ausgabe-Maske (Ebene 2) wurde geleert")

    def test_wert_wird_gemerkt_ausgabe_bleibt_auf_aus(self):
        self.assertEqual(self._frame()[_I_SHUTTER], _MANUAL)
        self.st.set_laser_estop(True)
        self.assertEqual(self._frame()[_I_SHUTTER], _AUS)
        self.st.set_programmer_value(_LASER_FID, "shutter", 200)
        self.st.set_programmer_value(_LASER_FID, "laser_bank", 77)
        # gemerkt …
        self.assertEqual(self.st.programmer[_LASER_FID]["shutter"], 200)
        self.assertEqual(self.st.programmer[_LASER_FID]["laser_bank"], 77)
        # … aber dunkel: Betriebsart auf dem Aus-Wert, der Rest auf 0.
        frame = self._frame()
        self.assertEqual(frame[_I_SHUTTER], _AUS)
        self.assertEqual(frame[_I_BANK], 0)
        # Das Licht daneben laeuft weiter.
        self.assertEqual(frame[19], 200)

    def test_nach_dem_loesen_kommt_was_eingestellt_ist(self):
        self.st.set_laser_estop(True)
        self.st.set_programmer_value(_LASER_FID, "shutter", 200)
        self.st.set_programmer_value(_LASER_FID, "laser_bank", 77)
        self.st.laser_notaus_loesen()
        self.assertFalse(self.st.laser_estop_active)
        frame = self._frame()
        self.assertEqual(frame[_I_SHUTTER], 200)
        self.assertEqual(frame[_I_BANK], 77)

    def test_loesen_meldet_sich_fuer_die_anzeigen(self):
        """Ohne Ereignis bliebe „NOT-AUS aktiv“ im Laser-Tab stehen."""
        from src.core.sync import get_sync, SyncEvent
        gesehen = []

        def merke(*_a):
            gesehen.append(bool(self.st.laser_estop_active))
        get_sync().subscribe(SyncEvent.LASER_ESTOP, merke)
        self.addCleanup(get_sync().unsubscribe, SyncEvent.LASER_ESTOP, merke)
        self.st.set_laser_estop(True)
        self.st.laser_notaus_loesen()
        self.assertEqual(gesehen, [False])

    def test_midi_programmer_attribut_ohne_auswahl_loest_nicht(self):
        """Der Shutter-Fader fuer die Moving Heads: ohne Auswahl schreibt er auf
        alle gepatchten Geraete — also auch auf den Laser."""
        st = self.st
        st.get_patched_fixtures = lambda: list(st._patch_cache)
        st.get_selected_cells = lambda: []
        st.get_selected_fids = lambda: []
        orig = mm.get_midi_manager
        mm.get_midi_manager = lambda: mock.MagicMock()
        self.addCleanup(setattr, mm, "get_midi_manager", orig)
        mapper = mm.MidiMapper(st)
        self.addCleanup(mapper.close)
        st.set_laser_estop(True)
        mapper._execute_continuous(
            mm.MidiMapping(name="x", msg_type="control_change", channel=1,
                           data1=7, action=mm.ACTION_PROGRAMMER_VAL,
                           param="shutter"), 1.0)
        self.assertEqual(st.programmer[_LASER_FID]["shutter"], 255,
                         "der Regler hat den Laser gar nicht erreicht")
        self.assertTrue(st.laser_estop_active)
        self.assertEqual(self._frame()[_I_SHUTTER], _AUS)

    def test_es_gibt_keine_loese_liste_mehr(self):
        """Die Liste „diese Attribute loesen“ ist weg — kein Attribut loest."""
        self.assertFalse(hasattr(A, "_LASER_REARM_ATTRS"))


class RueckfrageTest(l31._Basis):
    """Der eine Loese-Weg: Knopf oben rechts, Rueckfrage, ``laser_notaus_loesen``."""

    def _ausloesen(self):
        self.btn.click()
        self.w._notaus_sperre_bis = 0.0

    def test_rueckfrage_sagt_dass_sofort_wieder_ausgegeben_wird(self):
        self._ausloesen()
        self._antwort(QMessageBox.StandardButton.Cancel)
        self.btn.click()
        text = self.frage.call_args[0][2]
        self.assertIn("Der Laser gibt danach sofort wieder aus, was eingestellt ist",
                      text)
        self.assertIn("Nur lösen, wenn der Strahlbereich frei ist", text)

    def test_wert_bei_not_aus_dann_loesen_mit_rueckfrage(self):
        self._ausloesen()
        self.st.set_programmer_value(_LASER_FID, "shutter", 200)
        self.w._notaus_tick()
        self.assertEqual(self.btn.text(), "LASER NOT-AUS AKTIV")
        self.assertEqual(self._frame()[_I_SHUTTER], _AUS)
        self._antwort(QMessageBox.StandardButton.Yes)
        self.btn.click()
        self.assertEqual(self.frage.call_count, 1)
        self.assertFalse(self.st.laser_estop_active)
        self.assertEqual(self._frame()[_I_SHUTTER], 200)

    def test_knopf_erklaert_warum_der_laser_dunkel_bleibt(self):
        self._ausloesen()
        tip = self.btn.toolTip()
        self.assertIn("Werte werden gemerkt, der Laser bleibt dunkel", tip)
        self.assertIn("Rückfrage", tip)

    def test_loesen_zeigt_keinen_ausgeloest_alarm(self):
        """Das Ereignis kommt jetzt auch beim Loesen — die rote Statuszeile
        „ausgelöst“ darf dann nicht erscheinen."""
        self.w.statusBar().clearMessage()
        self.st.set_laser_estop(False)
        self.w._on_laser_estop_ui()
        self.assertNotIn("ausgelöst", self.w.statusBar().currentMessage())
        self.st.set_laser_estop(True)
        self.w._on_laser_estop_ui()
        self.assertIn("ausgelöst", self.w.statusBar().currentMessage())
        self.w.statusBar().clearMessage()
        self.w._reset_statusbar_style()

    def test_ein_weg_fuer_die_rueckfrage(self):
        """Wer kuenftig einen zweiten Loese-Knopf baut (VCB-38), nimmt dieselbe
        Rueckfrage — sie liegt nicht im Hauptfenster vergraben."""
        from src.ui import laser_notaus
        self.st.set_laser_estop(True)
        self._antwort(QMessageBox.StandardButton.Cancel)
        self.assertFalse(laser_notaus.loesen_mit_rueckfrage(self.w, self.st))
        self.assertTrue(self.st.laser_estop_active)
        self._antwort(QMessageBox.StandardButton.Yes)
        self.assertTrue(laser_notaus.loesen_mit_rueckfrage(self.w, self.st))
        self.assertFalse(self.st.laser_estop_active)


class KeinZweiterLoeseWegTest(unittest.TestCase):
    """Quelltext-Waechter: den Latch nimmt nur ``set_laser_estop`` zurueck, und
    ``set_laser_estop(False)`` ruft im Programm nur ``laser_notaus_loesen``."""

    WURZEL = os.path.join(os.path.dirname(__file__), "..", "src")

    def _quellen(self):
        for ordner, _d, dateien in os.walk(self.WURZEL):
            for name in dateien:
                if name.endswith(".py"):
                    pfad = os.path.join(ordner, name)
                    with open(pfad, encoding="utf-8") as f:
                        yield os.path.relpath(pfad, self.WURZEL), f.read()

    def test_latch_wird_nur_an_einer_stelle_zurueckgenommen(self):
        import re
        flag, aufruf, loesen = [], [], []
        for rel, text in self._quellen():
            for nr, zeile in enumerate(text.splitlines(), 1):
                code = zeile.split("#", 1)[0]
                if "``" in code:
                    continue                    # Erwaehnung im Docstring
                if re.search(r"laser_estop_active\s*=\s*False", code):
                    flag.append((rel, nr))
                if re.search(r"set_laser_estop\(\s*False\s*\)", code):
                    aufruf.append((rel, nr))
                if re.search(r"\.laser_notaus_loesen\(", code):
                    loesen.append(rel)
        # Nur der Deaktivieren-Zweig in set_laser_estop (der Startwert in
        # __init__ traegt eine Typangabe und zaehlt hier nicht).
        self.assertEqual([rel for rel, _ in flag],
                         [os.path.join("core", "app_state.py")], flag)
        self.assertEqual([rel for rel, _ in aufruf],
                         [os.path.join("core", "app_state.py")], aufruf)
        self.assertEqual(sorted(set(loesen)), [os.path.join("ui", "laser_notaus.py")])


if __name__ == "__main__":
    unittest.main()
