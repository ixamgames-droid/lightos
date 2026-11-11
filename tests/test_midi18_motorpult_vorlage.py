"""MIDI-18: Motorpult (Mackie Control) als Ganzes in die Virtual Console.

Abgesichert (ohne Pult, mit gestelltem MIDI-Manager):

* Profil ``mackie_control`` laedt, ist gueltig und zeigt auf die Vorlage;
* Vorlage: 9 Motor-Fader (Pitchbend Kanal 1..9, Master = Grand Master),
  Tasten REC/SOLO/MUTE/SELECT auf den Mackie-Noten mit LED-Rueckmeldung,
  V-Pots als relative Encoder im Mackie-Format;
* eingefuegt in eine VCCanvas (ein Undo-Schritt, aktuelle Seite): Pitchbend
  vom Pult bewegt den passenden Fader, ein Wert in LightOS faehrt den Motor
  auf dem richtigen Kanal, die Beruehrungs-Note sperrt; Speichern/Laden
  behaelt Motor und LED;
* Tasten-LEDs: leuchtende Taste -> Note 127, sonst 0; andere Seite -> aus;
* der Knopf im Controller-Browser fuegt ein.
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


def _pb(kanal: int, wert14: int):
    return mgr._decode([0xE0 | (kanal - 1), wert14 & 0x7F, (wert14 >> 7) & 0x7F], "X-Touch")


def _note(kanal: int, nummer: int, velocity: int):
    return mgr._decode([0x90 | (kanal - 1), nummer, velocity], "X-Touch")


def _cc(kanal: int, nummer: int, wert: int):
    return mgr._decode([0xB0 | (kanal - 1), nummer, wert], "X-Touch")


class _FakeMM:
    def __init__(self):
        self.pb: list[tuple[int, int]] = []
        self.roh: list[list[int]] = []

    def send_pitchbend(self, kanal, wert):
        self.pb.append((kanal, wert))
        return True

    def send_message(self, msg):
        self.roh.append(list(msg))
        return True

    def subscribe(self, _cb):
        pass

    def unsubscribe(self, _cb):
        pass

    def __getattr__(self, name):         # alles andere: stumm
        return lambda *a, **k: None


class ProfilTest(unittest.TestCase):

    def test_profil_laedt_und_ist_gueltig(self):
        from src.core.controllers.controller_library import ControllerLibrary
        lib = ControllerLibrary()
        lib.ensure_loaded()
        p = lib.find("mackie_control")
        self.assertIsNotNone(p)
        self.assertEqual(p.vc_template, "mackie_control")
        self.assertEqual(p.device_type, "midi_fader_controller")
        self.assertTrue(p.source and p.license)
        pb = [c for c in p.controls if c.type == "pitchbend"]
        self.assertEqual([c.channel for c in pb], list(range(9)))   # 0-basiert
        touch = [c for c in p.controls if c.name.startswith("Fader-Berührung")]
        self.assertEqual(sorted(n for c in touch for n in c.nummern()),
                         list(range(104, 113)))
        namen = {c.name: c for c in p.controls}
        self.assertEqual(namen["SELECT 1-8"].nummern(), list(range(24, 32)))
        self.assertEqual(namen["V-Pot drehen 1-8"].type, "encoder")
        # Unsicheres ist gekennzeichnet
        self.assertTrue(any("unsicher" in c.name for c in p.controls))

    def test_mapping_generator_belegt_keine_beruehrung(self):
        """Die Startbelegung (Noten -> GO) darf die Beruehrungs-Noten nicht
        nehmen — sonst startet das Anfassen eines Faders einen Executor."""
        from src.core.controllers.controller_library import ControllerLibrary
        from src.core.controllers.mapping_generator import erzeuge_mapping_profil
        lib = ControllerLibrary()
        lib.ensure_loaded()
        prof = erzeuge_mapping_profil(lib.find("mackie_control"))
        noten = [m.data1 for m in prof.mappings
                 if getattr(m, "msg_type", "") == "note_on"]
        self.assertTrue(noten)
        self.assertFalse(set(noten) & set(range(104, 113)))


class VorlageTest(unittest.TestCase):

    def setUp(self):
        from src.ui.virtualconsole import controller_templates as ct
        self.ct = ct
        self.t = ct.vorlage_bauen("mackie_control")

    def test_neun_motorfader(self):
        f = [w for w in self.t if w["type"] == "VCSlider"]
        self.assertEqual(len(f), 9)
        self.assertEqual([w["midi_ch"] for w in f], list(range(1, 10)))
        for w in f:
            self.assertEqual(w["midi_type"], "pitchbend")
            self.assertTrue(w.get("midi_motor"))
        self.assertEqual(f[-1]["mode"], "GrandMaster")
        self.assertTrue(all(w["mode"] == "Level" for w in f[:8]))

    def test_tasten_mit_mackie_noten_und_led(self):
        tasten = [w for w in self.t if w["type"] == "VCButton"]
        self.assertEqual(sorted(w["midi_data1"] for w in tasten), list(range(32)))
        for w in tasten:
            self.assertEqual((w["midi_type"], w["midi_ch"]), ("note_on", 1))
            self.assertTrue(w.get("midi_led"))
        select = {w["caption"]: w["midi_data1"] for w in tasten}
        self.assertEqual(select["SELECT 1"], 24)
        self.assertEqual(select["MUTE 8"], 23)
        self.assertEqual(select["REC 3"], 2)

    def test_vpots_relativ_mackie(self):
        from src.ui.virtualconsole.vc_encoder import EncoderMidiMode
        e = [w for w in self.t if w["type"] == "VCEncoder"]
        self.assertEqual([w["midi_cc"] for w in e], list(range(16, 24)))
        self.assertTrue(all(w["midi_mode"] == EncoderMidiMode.RELATIVE_SIGN for w in e))

    def test_unbekannte_vorlage_ist_leer(self):
        self.assertEqual(self.ct.vorlage_bauen("gibt_es_nicht"), [])
        self.assertEqual(self.ct.vorlage_name("gibt_es_nicht"), "")
        self.assertTrue(self.ct.vorlage_bauen("apc_mini"))

    def test_vpot_vorzeichenbit(self):
        from src.ui.virtualconsole.vc_encoder import EncoderMidiMode, VCEncoder
        e = VCEncoder("V")
        e.midi_mode = EncoderMidiMode.RELATIVE_SIGN
        e.midi_cc, e.midi_ch = 16, 1
        schritte = []
        e.nudge = schritte.append
        e.handle_midi(_cc(1, 16, 65))
        e.handle_midi(_cc(1, 16, 3))
        self.assertEqual(schritte, [-1, 3])
        d = e.to_dict()
        neu = VCEncoder("W")
        neu.apply_dict(d)
        self.assertEqual(neu.midi_mode, EncoderMidiMode.RELATIVE_SIGN)


class CanvasTest(unittest.TestCase):

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
        self.c._led_timer.stop = lambda: None        # nicht wichtig im Test
        from src.ui.virtualconsole import controller_templates as ct
        self.erzeugt = self.c.vorlage_einfuegen(ct.vorlage_bauen("mackie_control"))

    def _fader(self, kanal):
        from src.ui.virtualconsole.vc_slider import VCSlider
        return next(w for w in self.c.findChildren(VCSlider) if w.midi_ch == kanal)

    def _taste(self, caption):
        from src.ui.virtualconsole.vc_button import VCButton
        return next(w for w in self.c.findChildren(VCButton) if w.caption == caption)

    def test_ein_undo_schritt_auf_aktueller_seite(self):
        from src.ui.virtualconsole import controller_templates as ct
        self.assertEqual(len(self.erzeugt), len(ct.vorlage_bauen("mackie_control")))
        self.assertEqual(len(self.c._undo_stack), 1)
        self.assertTrue(all(w.bank == self.c.active_bank for w in self.erzeugt))
        self.c.undo()
        self.assertEqual(self.c.to_dict()["widgets"], [])

    def test_zweites_einfuegen_liegt_darunter(self):
        unten = max(w.y() + w.height() for w in self.erzeugt)
        from src.ui.virtualconsole import controller_templates as ct
        from src.ui.virtualconsole.vc_widget import VCWidget
        zwei = self.c.vorlage_einfuegen(ct.vorlage_bauen("mackie_control"))
        self.assertGreaterEqual(min(w.y() for w in zwei), unten)
        ids = [w.widget_id for w in self.c.findChildren(VCWidget)]
        self.assertEqual(len(ids), len(set(ids)), "Kennungen eindeutig")

    def test_pult_bewegt_vc_fader(self):
        import time
        f3 = self._fader(3)
        # Beim Einfuegen fuhr der Motor auf 0 — eine Eingabe gleich danach
        # gaelte als Bericht dieser Fahrt (MIDI-17). Spaeter ist es die Hand.
        f3._motor._uhr = lambda: time.monotonic() + 5.0
        self.c._handle_midi(_pb(3, 16383))
        self.assertEqual(f3.value, 255)
        self.assertEqual(self._fader(2).value, 0)

    def test_vc_wert_faehrt_motor_auf_richtigem_kanal(self):
        self.mm.pb.clear()
        f5 = self._fader(5)
        f5.value = 255
        self.assertIn((5, 16383), self.mm.pb)
        self.assertTrue(all(k == 5 for k, _ in self.mm.pb))

    def test_beruehrung_sperrt(self):
        f1 = self._fader(1)
        self.c._handle_midi(_note(1, 104, 127))           # Fader 1 beruehrt
        self.mm.pb.clear()
        f1.value = 100
        self.assertEqual(self.mm.pb, [])
        self.c._handle_midi(_note(1, 104, 0))
        self.assertEqual(self.mm.pb, [(1, round(100 / 255 * 16383))])

    def test_speichern_laden_behaelt_motor_und_led(self):
        d = self.c.to_dict()
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        neu = VCCanvas()
        self.addCleanup(neu.deleteLater)
        neu.from_dict(d)
        from src.ui.virtualconsole.vc_slider import VCSlider
        from src.ui.virtualconsole.vc_button import VCButton
        f = neu.findChildren(VCSlider)
        self.assertEqual(len(f), 9)
        self.assertTrue(all(w.midi_motor for w in f))
        self.assertTrue(all(b.midi_led for b in neu.findChildren(VCButton)))

    def test_led_folgt_der_taste(self):
        mute2 = self._taste("MUTE 2")              # Note 17
        self.mm.roh.clear()
        mute2._pressed = True
        self.c._led_abgleich()
        self.assertIn([0x90, 17, 127], self.mm.roh)
        self.mm.roh.clear()
        self.c._led_abgleich()
        self.assertEqual(self.mm.roh, [], "nur Aenderungen senden")
        mute2._pressed = False
        self.c._led_abgleich()
        self.assertEqual(self.mm.roh, [[0x90, 17, 0]])

    def test_andere_seite_schaltet_led_aus(self):
        sel1 = self._taste("SELECT 1")             # Note 24
        sel1._pressed = True
        self.c._led_abgleich()
        self.mm.roh.clear()
        self.c._active_bank = 1                    # Seite gewechselt
        self.c._led_abgleich()
        self.assertIn([0x90, 24, 0], self.mm.roh)

    def test_ohne_haken_keine_led(self):
        sel1 = self._taste("SELECT 1")
        sel1.midi_led = False
        sel1._pressed = True
        self.mm.roh.clear()
        self.c._led_abgleich()
        self.assertNotIn([0x90, 24, 127], self.mm.roh)


class NoteLedSpiegelTest(unittest.TestCase):

    def test_fehlgeschlagen_wird_wiederholt_und_auffrischen(self):
        from src.core.midi.note_led import AUFFRISCHEN_S, NoteLedSpiegel
        t = [0.0]
        ok = [False]
        gesendet = []
        s = NoteLedSpiegel(lambda m: (gesendet.append(m), ok[0])[1], uhr=lambda: t[0])
        self.assertEqual(s.abgleichen({(1, 5): True}), 0)
        ok[0] = True
        self.assertEqual(s.abgleichen({(1, 5): True}), 1)
        self.assertEqual(s.abgleichen({(1, 5): True}), 0)
        t[0] += AUFFRISCHEN_S + 0.1
        self.assertEqual(s.abgleichen({(1, 5): True}), 1, "nach Neustecken neu senden")
        self.assertEqual(s.alle_aus(), 1)
        self.assertEqual(s.stand, {})


class BrowserTest(unittest.TestCase):

    def setUp(self):
        self.mm = _FakeMM()
        alt = mgr.get_midi_manager
        mgr.get_midi_manager = lambda: self.mm
        self.addCleanup(setattr, mgr, "get_midi_manager", alt)
        alt_info = QMessageBox.information
        self.meldungen = []
        QMessageBox.information = staticmethod(
            lambda *a, **k: self.meldungen.append(a))
        self.addCleanup(setattr, QMessageBox, "information", alt_info)

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

    def test_knopf_fuegt_ein(self):
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        from src.ui.virtualconsole.vc_slider import VCSlider
        c = VCCanvas()
        self.addCleanup(c.deleteLater)
        dlg = self._dlg(c)
        self.assertTrue(dlg._btn_vc.isEnabled())
        dlg._btn_vc.click()
        self.assertEqual(len(c.findChildren(VCSlider)), 9)
        self.assertEqual(len(c._undo_stack), 1)
        self.assertTrue(self.meldungen)
        self.assertIn("9 Fader", dlg._letzte_meldung)

    def test_knopf_aus_ohne_vorlage_oder_ohne_canvas(self):
        dlg = self._dlg(None)
        self.assertFalse(dlg._btn_vc.isEnabled(), "kein Weg zur Virtual Console")
        from PySide6.QtCore import Qt
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        c = VCCanvas()
        self.addCleanup(c.deleteLater)
        dlg2 = self._dlg(c)
        for i in range(dlg2._list.count()):
            pid = dlg2._list.item(i).data(Qt.ItemDataRole.UserRole)
            p = dlg2._lib.find(pid)
            if p is not None and not p.vc_template:
                dlg2._list.setCurrentRow(i)
                self.assertFalse(dlg2._btn_vc.isEnabled(), pid)
                break


if __name__ == "__main__":
    unittest.main()
