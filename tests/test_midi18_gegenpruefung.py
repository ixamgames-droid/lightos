"""MIDI-18 Gegenpruefung (11.11.): Befunde aus der Review.

* Misslungenes Motor-Senden (Ausgang noch zu) geht nicht verloren, sondern
  wird gedrosselt nachgetragen.
* Zeigt der gemeinsame Ausgang auf einen APC, gehen keine Mackie-LEDs und
  keine Motor-Befehle dorthin (sonst werden die APC-Pads ueberschrieben).
* Die Vorlage ein zweites Mal auf dieselbe Seite: der Browser fragt nach.
* Profil-Hinweis zum Extender verspricht nichts, was die VC nicht kann.
* LED-Spiegel vergisst geloeschte Tasten, Canvas-Abbau schaltet LEDs aus.
* Mapping-Profil fuer das Motorpult: Hinweis auf die Doppelbelegung.

Ohne echtes Pult, ohne echte App-Daten (Fake-MidiManager).
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest as _pytest                                # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import src.core.midi.midi_manager as mgr                # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402

_app = QApplication.instance() or QApplication([])


@_pytest.fixture(autouse=True)
def _keine_fenster_uebrig():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


class _FakeMM:
    def __init__(self):
        self.pb: list[tuple[int, int]] = []
        self.roh: list[list[int]] = []
        self.ok = True
        self.ausgang = ""

    def current_output_name(self):
        return self.ausgang

    def send_pitchbend(self, kanal, wert):
        if not self.ok:
            return False
        self.pb.append((kanal, wert))
        return True

    def send_message(self, msg):
        if not self.ok:
            return False
        self.roh.append(list(msg))
        return True

    def __getattr__(self, name):         # alles andere: stumm
        return lambda *a, **k: None


class _Uhr:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class MotorNachtragTest(unittest.TestCase):

    def test_misslungenes_senden_wird_gedrosselt_nachgetragen(self):
        from src.core.midi.motor_fader import WIEDERHOLEN_S, MotorFader
        uhr = _Uhr()
        ok = [False]
        gesendet: list[int] = []
        m = MotorFader(lambda w: (gesendet.append(w), ok[0])[1], uhr=uhr)
        self.assertFalse(m.melden(5000, erzwingen=True))   # Ausgang noch zu
        self.assertTrue(m.wartet, "der Auftrag darf nicht verloren gehen")
        ok[0] = True                                         # Ausgang geoeffnet
        self.assertFalse(m.nachtrag(), "gerade misslungen: kurz warten")
        uhr.t += WIEDERHOLEN_S + 0.01
        self.assertTrue(m.nachtrag())
        self.assertEqual(gesendet[-1], 5000)
        self.assertFalse(m.wartet)

    def test_gleicher_wert_nach_fehlschlag_wird_trotzdem_gesendet(self):
        from src.core.midi.motor_fader import WIEDERHOLEN_S, MotorFader
        uhr = _Uhr()
        ok = [True]
        gesendet: list[int] = []
        m = MotorFader(lambda w: (gesendet.append(w), ok[0])[1], uhr=uhr)
        self.assertTrue(m.melden(7000))
        uhr.t += 5
        ok[0] = False                                        # Pult abgezogen
        self.assertFalse(m.melden(7000, erzwingen=True))
        ok[0] = True
        uhr.t += WIEDERHOLEN_S + 0.01
        self.assertTrue(m.nachtrag(), "wo der Motor steht, weiss niemand")
        self.assertEqual(gesendet, [7000, 7000, 7000])


class _CanvasBasis(unittest.TestCase):

    def setUp(self):
        from src.ui.virtualconsole.vc_slider import VCSlider
        VCSlider.soft_takeover = False
        self.addCleanup(setattr, VCSlider, "soft_takeover", False)
        self.mm = _FakeMM()
        alt = mgr.get_midi_manager
        mgr.get_midi_manager = lambda: self.mm
        self.addCleanup(setattr, mgr, "get_midi_manager", alt)
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        self.c = VCCanvas()
        self.addCleanup(self.c.deleteLater)
        self.c._led_timer.stop = lambda: None

    def _einfuegen(self):
        from src.ui.virtualconsole import controller_templates as ct
        return self.c.vorlage_einfuegen(ct.vorlage_bauen("mackie_control"))

    def _fader(self, kanal):
        from src.ui.virtualconsole.vc_slider import VCSlider
        return next(w for w in self.c.findChildren(VCSlider) if w.midi_ch == kanal)

    def _taste(self, caption):
        from src.ui.virtualconsole.vc_button import VCButton
        return next(w for w in self.c.findChildren(VCButton) if w.caption == caption)


class CanvasGegenpruefungTest(_CanvasBasis):

    def test_motor_kommt_nach_spaetem_oeffnen_des_ausgangs_an(self):
        self.mm.ok = False                      # LightOS-Start: Ausgang zu
        self._einfuegen()
        f1 = self._fader(1)
        f1.value = 200
        self.assertTrue(f1._motor_timer.isActive(), "Nachtrag ist geplant")
        self.mm.ok = True                       # Bediener oeffnet den Ausgang
        import time
        f1._motor._uhr = lambda: time.monotonic() + 5.0
        f1._motor_nachtrag()
        self.assertIn((1, round(200 / 255 * 16383)), self.mm.pb)

    def test_apc_ausgang_bekommt_keine_mackie_leds_und_motoren(self):
        self._einfuegen()
        self.mm.ausgang = "APC MINI:APC MINI MIDI 1 24:0"
        self.mm.roh.clear()
        self.mm.pb.clear()
        self._taste("MUTE 2")._pressed = True
        self.c._led_abgleich()
        self._fader(3).value = 255
        self.assertEqual(self.mm.roh, [], "APC-Pads nicht ueberschreiben")
        self.assertEqual(self.mm.pb, [])
        self.mm.ausgang = "X-Touch:X-Touch MIDI 1 28:0"
        self.c._led_abgleich()
        self.assertIn([0x90, 17, 127], self.mm.roh)

    def test_ueberschneidungen_nur_auf_der_aktiven_seite(self):
        from src.ui.virtualconsole import controller_templates as ct
        vorlage = ct.vorlage_bauen("mackie_control")
        self.assertEqual(self.c.vorlage_ueberschneidungen(vorlage), 0)
        self._einfuegen()
        self.assertGreaterEqual(self.c.vorlage_ueberschneidungen(vorlage), 9 + 8 + 32)
        self.c._active_bank = 1
        self.assertEqual(self.c.vorlage_ueberschneidungen(vorlage), 0)

    def test_abbau_schaltet_leds_aus(self):
        self._einfuegen()
        self._taste("SELECT 1")._pressed = True     # Note 24
        self.c._led_abgleich()
        self.mm.roh.clear()
        self.c._teardown_midi()
        self.assertIn([0x90, 24, 0], self.mm.roh)


class NoteLedVergessenTest(unittest.TestCase):

    def test_geloeschte_taste_verschwindet_aus_dem_stand(self):
        from src.core.midi.note_led import NoteLedSpiegel
        s = NoteLedSpiegel(lambda m: True, uhr=lambda: 0.0)
        s.abgleichen({(1, 5): False})
        self.assertEqual(s.stand, {(1, 5): 0})
        s.abgleichen({})
        self.assertEqual(s.stand, {}, "sonst laeuft der Abgleich-Timer ewig")


class ProfilHinweisTest(unittest.TestCase):

    def test_extender_hinweis_verspricht_keine_zweite_vorlage(self):
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parents[1] / "data" / "controller_library" / "mackie_control.json"
        features = json.loads(p.read_text(encoding="utf-8"))["features"]
        text = " ".join(features)
        self.assertNotIn("zweite Vorlage einfügen", text)
        self.assertIn("Extender wird noch nicht unterstützt", text)


class BrowserGegenpruefungTest(unittest.TestCase):

    def setUp(self):
        self.mm = _FakeMM()
        alt = mgr.get_midi_manager
        mgr.get_midi_manager = lambda: self.mm
        self.addCleanup(setattr, mgr, "get_midi_manager", alt)
        self.meldungen = []
        self.fragen = []
        self.antwort = QMessageBox.StandardButton.No
        for name in ("information", "warning"):
            alt_fn = getattr(QMessageBox, name)
            setattr(QMessageBox, name, staticmethod(
                lambda *a, **k: self.meldungen.append(a)))
            self.addCleanup(setattr, QMessageBox, name, alt_fn)
        alt_q = QMessageBox.question
        QMessageBox.question = staticmethod(
            lambda *a, **k: (self.fragen.append(a), self.antwort)[1])
        self.addCleanup(setattr, QMessageBox, "question", alt_q)

    def _dlg(self, canvas):
        from PySide6.QtCore import Qt
        from src.ui.widgets.controller_browser import ControllerBrowserDialog
        dlg = ControllerBrowserDialog(midi_only=True,
                                      vc_canvas=(lambda: canvas) if canvas else None)
        self.addCleanup(dlg.deleteLater)
        for i in range(dlg._list.count()):
            if dlg._list.item(i).data(Qt.ItemDataRole.UserRole) == "mackie_control":
                dlg._list.setCurrentRow(i)
        return dlg

    def test_zweites_einfuegen_fragt_nach(self):
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        from src.ui.virtualconsole.vc_slider import VCSlider
        c = VCCanvas()
        self.addCleanup(c.deleteLater)
        dlg = self._dlg(c)
        dlg._btn_vc.click()
        self.assertEqual(self.fragen, [], "leere Seite: keine Frage")
        self.assertEqual(len(c.findChildren(VCSlider)), 9)
        dlg._btn_vc.click()                       # Antwort: Nein
        self.assertEqual(len(self.fragen), 1)
        self.assertEqual(len(c.findChildren(VCSlider)), 9, "nichts gedoppelt")
        self.antwort = QMessageBox.StandardButton.Yes
        dlg._btn_vc.click()
        self.assertEqual(len(c.findChildren(VCSlider)), 18, "auf Wunsch doch")

    def test_mapping_profil_fuer_motorpult_fragt_vorher(self):
        import src.core.controllers.mapping_generator as mg
        aufgerufen = []

        def _kein_profil(p):
            aufgerufen.append(p)
            raise RuntimeError("im Test nichts speichern")

        alt = mg.erzeuge_mapping_profil
        mg.erzeuge_mapping_profil = _kein_profil
        self.addCleanup(setattr, mg, "erzeuge_mapping_profil", alt)
        dlg = self._dlg(None)
        self.assertTrue(dlg._btn_mapping.isEnabled())
        dlg._btn_mapping.click()                  # Antwort: Nein
        self.assertEqual(len(self.fragen), 1)
        self.assertEqual(aufgerufen, [], "ohne Ja kein Profil")


if __name__ == "__main__":
    unittest.main()
