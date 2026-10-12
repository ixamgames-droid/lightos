"""MIDI-10: Pitchbend als 14-Bit-Fader.

Mackie-Control- und X-Touch-Pulte senden ihre (Motor-)Fader nicht als CC,
sondern als Pitchbend: je Fader ein MIDI-Kanal, der Wert mit 14 Bit
(``d1`` = untere 7 Bit, ``d2`` = obere 7 Bit). Der Manager dekodierte die
Nachricht zwar, niemand konnte sie aber binden: Mapper und VC-Fader kannten
nur Note und CC, und wer ``d2`` allein nahm, hatte 128 statt 16384 Stufen.

Abgesichert:

* 14-Bit-Wert und Normierung (0..1) an der Nachricht;
* Bindung: ein Pitchbend-Fader ist sein KANAL — ``d1`` gehoert zum Wert und
  darf die Bindung nicht mitbestimmen; Speichern/Laden und Lernen behalten
  den Typ;
* der Mapper reicht stufenlose Ziele mit 14 Bit weiter;
* Konflikt-Erkennung: Pitchbend kollidiert nur mit Pitchbend desselben Kanals;
* VC-Fader: lernen, bedienen (auch mit Soft-Takeover), speichern, laden —
  CC-Fader bleiben, wie sie waren;
* keine LED-Rueckmeldung „Note 0“ fuer einen Fader ohne Nummer;
* Lern-Dialog und MIDI-Monitor zeigen Pitchbend als das, was es ist.
"""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication             # noqa: E402

import src.core.midi.midi_manager as mgr                # noqa: E402
import src.core.midi.midi_mapper as mm                  # noqa: E402
from src.ui.virtualconsole.vc_slider import SliderMode, VCSlider    # noqa: E402
from test_midi_mapper import _FakeMidiManager, _FakeState             # noqa: E402
from src.ui.virtualconsole.vc_widget import midi_binding_matches    # noqa: E402

_app = QApplication.instance() or QApplication([])


def _pb(kanal: int, wert14: int, port: str = "X-Touch"):
    """Pitchbend, wie das Pult ihn sendet: Status 0xE0 + Kanal, LSB, MSB."""
    return mgr._decode([0xE0 | (kanal - 1), wert14 & 0x7F, (wert14 >> 7) & 0x7F], port)


def _cc(kanal: int, nummer: int, wert: int, port: str = "X-Touch"):
    return mgr._decode([0xB0 | (kanal - 1), nummer, wert], port)


def _note(kanal: int, nummer: int, velocity: int, port: str = "X-Touch"):
    """Note-On; Velocity 0 ist das Loslassen, wie Mackie-Pulte es senden."""
    return mgr._decode([0x90 | (kanal - 1), nummer, velocity], port)


def _note_aus(kanal: int, nummer: int, port: str = "X-Touch"):
    return mgr._decode([0x80 | (kanal - 1), nummer, 0], port)


class NachrichtTest(unittest.TestCase):

    def test_pitchbend_traegt_seinen_14_bit_wert(self):
        for wert in (0, 1, 127, 128, 8192, 12345, 16383):
            m = _pb(3, wert)
            self.assertEqual(m.msg_type, "pitchbend")
            self.assertEqual(m.channel, 3)
            self.assertEqual(mgr.wert14(m), wert)

    def test_normierung_null_bis_eins(self):
        self.assertEqual(mgr.fader_wert(_pb(1, 0)), 0.0)
        self.assertEqual(mgr.fader_wert(_pb(1, 16383)), 1.0)
        self.assertAlmostEqual(mgr.fader_wert(_pb(1, 8192)), 8192 / 16383)

    def test_untere_bits_zaehlen(self):
        """Der Grund fuer das Item: 16384 Stufen statt 128."""
        a, b = _pb(1, 0x2000), _pb(1, 0x2001)
        self.assertEqual(a.data2, b.data2)                  # gleiches oberes Byte
        self.assertLess(mgr.fader_wert(a), mgr.fader_wert(b))

    def test_cc_und_note_wie_bisher(self):
        self.assertEqual(mgr.fader_wert(_cc(1, 7, 127)), 1.0)
        self.assertAlmostEqual(mgr.fader_wert(_cc(1, 7, 64)), 64 / 127)
        self.assertEqual(mgr.wert14(_cc(1, 7, 64)), 64 << 7)

    def test_fader_wert_nimmt_auch_schlichte_objekte(self):
        """VC-Tests und Vorlagen reichen einfache Objekte ohne Methoden herein."""
        m = SimpleNamespace(msg_type="pitchbend", channel=1, data1=0x7F, data2=0x7F)
        self.assertEqual(mgr.fader_wert(m), 1.0)
        m = SimpleNamespace(msg_type="cc", channel=1, data1=7, data2=127)
        self.assertEqual(mgr.fader_wert(m), 1.0)


class BindungTest(unittest.TestCase):

    def test_aus_nachricht_ist_der_kanal_die_kennung(self):
        b = mm.MidiInBinding.from_message(_pb(5, 12345))
        self.assertEqual(b.message_type, "pitchbend")
        self.assertEqual(b.channel, 5)
        self.assertEqual(b.trigger_id, 0, "d1 ist Teil des WERTS, nicht der Kennung")

    def test_trifft_jeden_wert_dieses_kanals(self):
        b = mm.MidiInBinding(device="", channel=5, trigger_id=0, message_type="pitchbend")
        for wert in (0, 1, 77, 8192, 16383):
            self.assertTrue(b.matches(_pb(5, wert)), wert)
        self.assertFalse(b.matches(_pb(6, 8192)))
        self.assertFalse(b.matches(_cc(5, 0, 64)))
        self.assertFalse(b.matches(mgr._decode([0x94, 0, 100], "X-Touch")))

    def test_kanal_null_heisst_alle(self):
        b = mm.MidiInBinding(device="", channel=0, trigger_id=0, message_type="pitchbend")
        self.assertTrue(b.matches(_pb(1, 5)) and b.matches(_pb(9, 5)))

    def test_cc_bindung_trifft_keinen_pitchbend(self):
        b = mm.MidiInBinding(device="", channel=5, trigger_id=0, message_type="cc")
        self.assertFalse(b.matches(_pb(5, 0)))

    def test_speichern_und_laden_behalten_den_typ(self):
        m = mm.MidiMapping(name="Fader 1", action=mm.ACTION_EXECUTOR_FADER, param="1")
        m.set_from_learn_message(_pb(1, 9000))
        self.assertEqual(m.msg_type, "pitchbend")
        self.assertEqual(m.midi_in.message_type, "pitchbend")
        d = m.to_config_dict()
        self.assertEqual(d["midi_in"]["message_type"], "pitchbend")
        neu = mm.MidiMapping.from_config_dict(d)
        self.assertEqual(neu.midi_in.message_type, "pitchbend")
        self.assertEqual(neu.msg_type, "pitchbend")
        self.assertTrue(neu.midi_in.matches(_pb(1, 3)))
        self.assertFalse(neu.midi_in.matches(_cc(1, 0, 3)))

    def test_flache_felder_reichen_den_typ_durch(self):
        """Der Editor schreibt die flachen Felder; daraus entsteht die Bindung."""
        m = mm.MidiMapping(name="F", msg_type="pitchbend", channel=2, data1=0,
                           action=mm.ACTION_GRAND_MASTER)
        self.assertEqual(m.midi_in.message_type, "pitchbend")
        self.assertTrue(m.midi_in.matches(_pb(2, 100)))


class KonfliktTest(unittest.TestCase):

    def test_pitchbend_kollidiert_nur_mit_pitchbend_desselben_kanals(self):
        ueber = mm._bindings_overlap
        self.assertTrue(ueber("pitchbend", 1, 0, "pitchbend", 1, 0))
        self.assertTrue(ueber("pitchbend", 1, 55, "pitchbend", 1, 99), "d1 zaehlt nicht")
        self.assertTrue(ueber("pitchbend", 0, 0, "pitchbend", 7, 0), "Kanal 0 = alle")
        self.assertFalse(ueber("pitchbend", 1, 0, "pitchbend", 2, 0))
        self.assertFalse(ueber("pitchbend", 1, 0, "note_on", 1, 0))
        self.assertFalse(ueber("pitchbend", 1, 0, "cc", 1, 0))
        self.assertFalse(ueber("cc", 1, 0, "pitchbend", 1, 0))

    def test_note_und_cc_wie_bisher(self):
        ueber = mm._bindings_overlap
        self.assertTrue(ueber("note_on", 1, 5, "note", 1, 5))
        self.assertTrue(ueber("cc", 1, 5, "cc", 0, 5))
        self.assertFalse(ueber("cc", 1, 5, "note_on", 1, 5))
        self.assertFalse(ueber("cc", 1, 5, "cc", 1, 6))


class MapperTest(unittest.TestCase):

    def setUp(self):
        self.midi = _FakeMidiManager()
        alt = mm.get_midi_manager
        mm.get_midi_manager = lambda: self.midi
        self.addCleanup(setattr, mm, "get_midi_manager", alt)
        self.zustand = _FakeState()
        self.mapper = mm.MidiMapper(self.zustand)
        self.addCleanup(self.mapper.close)
        self.ex = self.zustand.playback_engine.executors[0]

    def _mapping(self, **kw):
        m = mm.MidiMapping(**kw)
        self.mapper.add_mapping(m)
        return m

    def test_executor_fader_bekommt_14_bit(self):
        self._mapping(name="F1", msg_type="pitchbend", channel=1, data1=0,
                      action=mm.ACTION_EXECUTOR_FADER, param="1")
        for wert in (0, 5000, 8192, 8193, 16383):
            self.mapper._on_midi(_pb(1, wert))
            self.assertAlmostEqual(self.ex.fader_value, wert / 16383, places=9)

    def test_grand_master(self):
        self._mapping(name="GM", msg_type="pitchbend", channel=9, data1=0,
                      action=mm.ACTION_GRAND_MASTER)
        self.mapper._on_midi(_pb(9, 16383))
        self.assertEqual(self.zustand.output_manager.grand_master, 1.0)
        self.mapper._on_midi(_pb(9, 4096))
        self.assertAlmostEqual(self.zustand.output_manager.grand_master, 4096 / 16383)

    def test_anderer_kanal_bewegt_nichts(self):
        self._mapping(name="F1", msg_type="pitchbend", channel=1, data1=0,
                      action=mm.ACTION_EXECUTOR_FADER, param="1")
        self.mapper._on_midi(_pb(2, 16383))
        self.assertEqual(self.ex.fader_value, 0.0)

    def test_cc_fader_wie_bisher(self):
        self._mapping(name="F1", msg_type="cc", channel=1, data1=7,
                      action=mm.ACTION_EXECUTOR_FADER, param="1")
        self.mapper._on_midi(_cc(1, 7, 127))
        self.assertEqual(self.ex.fader_value, 1.0)
        self.mapper._on_midi(_cc(1, 7, 64))
        self.assertAlmostEqual(self.ex.fader_value, 64 / 127)

    def test_flash_ueber_pitchbend_schaltet_an_der_mitte(self):
        """Ein Fader an einer Tasten-Aktion: obere Haelfte = gedrueckt."""
        self._mapping(name="Flash", msg_type="pitchbend", channel=3, data1=0,
                      action=mm.ACTION_EXECUTOR_FLASH, param="1")
        self.mapper._on_midi(_pb(3, 16000))
        self.assertTrue(self.ex._flash_active)
        self.mapper._on_midi(_pb(3, 100))
        self.assertFalse(self.ex._flash_active)

    def test_lernen_nimmt_pitchbend_an(self):
        gelernt = []
        self.mapper.start_learn(gelernt.append, pitchbend=True)
        self.mapper._on_midi(_pb(4, 7777))
        self.assertEqual(len(gelernt), 1)
        self.assertEqual(gelernt[0].msg_type, "pitchbend")
        self.assertFalse(self.mapper._learn_mode)

    def test_lernen_ohne_schalter_wie_bisher(self):
        """Aufrufer, die nur Tasten binden (Funktionen, Snaps), bekommen
        keinen Pitchbend — und die erste Note sofort, nicht erst beim Loslassen."""
        gelernt = []
        self.mapper.start_learn(gelernt.append)
        self.mapper._on_midi(_pb(4, 7777))
        self.assertEqual(gelernt, [])
        self.assertTrue(self.mapper._learn_mode)
        self.mapper._on_midi(_note(1, 104, 127))
        self.assertEqual([(g.msg_type, g.data1) for g in gelernt],
                         [("note_on", 104)])
        self.assertFalse(self.mapper._learn_mode)

    def test_beruehrungs_note_verliert_gegen_den_fader(self):
        """Mackie/X-Touch: Anfassen schickt Note 104+n, erst dann kommt der
        Pitchbend. Gelernt wird der Fader."""
        gelernt = []
        self.mapper.start_learn(gelernt.append, pitchbend=True)
        self.mapper._on_midi(_note(1, 104, 127))        # Finger auf dem Fader
        self.assertEqual(gelernt, [])
        self.assertTrue(self.mapper._learn_mode)
        self.mapper._on_midi(_pb(1, 300))
        self.assertEqual([g.msg_type for g in gelernt], ["pitchbend"])
        self.assertFalse(self.mapper._learn_mode)
        # Das Loslassen danach ist gewoehnlicher Verkehr, kein zweites Lernen.
        self.mapper._on_midi(_note(1, 104, 0))
        self.assertEqual(len(gelernt), 1)

    def test_taste_wird_beim_loslassen_gelernt(self):
        for loslassen in (_note(1, 20, 0), _note_aus(1, 20)):
            gelernt = []
            self.mapper.start_learn(gelernt.append, pitchbend=True)
            self.mapper._on_midi(_note(1, 20, 90))
            self.assertEqual(gelernt, [])
            self.mapper._on_midi(loslassen)
            self.assertEqual([(g.msg_type, g.data1, g.data2) for g in gelernt],
                             [("note_on", 20, 90)])
            self.assertFalse(self.mapper._learn_mode)

    def test_geraet_ohne_note_off_haengt_nicht(self):
        gelernt = []
        self.mapper.start_learn(gelernt.append, pitchbend=True)
        self.mapper._on_midi(_note(1, 20, 127))
        self.mapper._on_midi(_note(1, 20, 127))
        self.assertEqual([(g.msg_type, g.data1) for g in gelernt],
                         [("note_on", 20)])

    def test_cc_wird_sofort_gelernt(self):
        gelernt = []
        self.mapper.start_learn(gelernt.append, pitchbend=True)
        self.mapper._on_midi(_cc(1, 48, 10))
        self.assertEqual([(g.msg_type, g.data1) for g in gelernt], [("cc", 48)])

    def test_neues_lernen_vergisst_die_gehaltene_note(self):
        gelernt = []
        self.mapper.start_learn(gelernt.append, pitchbend=True)
        self.mapper._on_midi(_note(1, 20, 127))
        self.mapper.stop_learn()
        self.mapper.start_learn(gelernt.append, pitchbend=True)
        self.mapper._on_midi(_note(1, 30, 127))
        self.assertEqual(gelernt, [])
        self.mapper._on_midi(_note(1, 30, 0))
        self.assertEqual([g.data1 for g in gelernt], [30])


class VcBindungTest(unittest.TestCase):

    def test_pitchbend_bindung_ignoriert_d1(self):
        self.assertTrue(midi_binding_matches(_pb(2, 12345), "pitchbend", 2, 0))
        self.assertTrue(midi_binding_matches(_pb(2, 1), "pitchbend", 0, 0))
        self.assertFalse(midi_binding_matches(_pb(3, 1), "pitchbend", 2, 0))
        self.assertFalse(midi_binding_matches(_cc(2, 0, 1), "pitchbend", 2, 0))
        self.assertFalse(midi_binding_matches(_pb(2, 1), "cc", 2, 0))
        self.assertFalse(midi_binding_matches(_pb(2, 1), "pitchbend", 2, -1), "ungebunden")

    def test_note_und_cc_wie_bisher(self):
        self.assertTrue(midi_binding_matches(_cc(1, 7, 3), "cc", 1, 7))
        self.assertFalse(midi_binding_matches(_cc(1, 8, 3), "cc", 1, 7))
        note_aus = mgr._decode([0x80, 60, 0], "P")
        self.assertTrue(midi_binding_matches(note_aus, "note_on", 1, 60))


class VcFaderTest(unittest.TestCase):

    def setUp(self):
        VCSlider.soft_takeover = False
        self.addCleanup(setattr, VCSlider, "soft_takeover", False)
        self.s = VCSlider("F")
        self.s.mode = SliderMode.SPEED          # harmloser Modus

    def test_fader_bietet_pitchbend_zum_lernen_an(self):
        self.assertIn("pitchbend", self.s._midi_teach_kinds())
        self.assertIn("cc", self.s._midi_teach_kinds())

    def test_lernen_und_bedienen(self):
        self.assertIsNone(self.s.current_midi_binding())
        self.s.apply_midi_binding("pitchbend", 3, 0)
        self.assertEqual(self.s.current_midi_binding(), ("pitchbend", 3, 0))
        self.assertTrue(self.s.handle_midi(_pb(3, 16383)))
        self.assertEqual(self.s.value, 255)
        self.s.handle_midi(_pb(3, 0))
        self.assertEqual(self.s.value, 0)
        self.s.handle_midi(_pb(3, 8192))
        self.assertEqual(self.s.value, 128)
        self.assertFalse(self.s.handle_midi(_pb(4, 16383)), "anderer Kanal")
        self.assertFalse(self.s.handle_midi(_cc(3, 0, 127)), "CC trifft keinen Pitchbend-Fader")
        self.assertEqual(self.s.value, 128)

    def test_alle_256_stufen_erreichbar(self):
        """Mit CC (128 Stufen) blieb jede zweite DMX-Stufe unerreichbar."""
        self.s.apply_midi_binding("pitchbend", 1, 0)
        werte = set()
        for wert in range(0, 16384, 16):
            self.s.handle_midi(_pb(1, wert))
            werte.add(self.s.value)
        self.s.handle_midi(_pb(1, 16383))
        werte.add(self.s.value)
        self.assertEqual(werte, set(range(256)))

    def test_cc_fader_wie_bisher(self):
        self.s.apply_midi_binding("cc", 1, 10)
        self.assertEqual(self.s.current_midi_binding(), ("cc", 1, 10))
        self.assertTrue(self.s.handle_midi(_cc(1, 10, 127)))
        self.assertEqual(self.s.value, 255)
        self.assertFalse(self.s.handle_midi(_pb(1, 0)), "Pitchbend trifft keinen CC-Fader")
        self.assertEqual(self.s.value, 255)

    def test_umlernen_von_pitchbend_auf_cc_und_loesen(self):
        self.s.apply_midi_binding("pitchbend", 3, 0)
        self.s.apply_midi_binding("cc", 2, 44)
        self.assertEqual(self.s.current_midi_binding(), ("cc", 2, 44))
        self.assertFalse(self.s.handle_midi(_pb(3, 16383)))
        self.s.apply_midi_binding("cc", 0, -1)
        self.assertIsNone(self.s.current_midi_binding())
        self.s.apply_midi_binding("pitchbend", 3, 0)
        self.s.apply_midi_binding("pitchbend", 0, -1)
        self.assertIsNone(self.s.current_midi_binding())
        self.assertFalse(self.s.handle_midi(_pb(3, 16383)))

    def test_soft_takeover_gilt_auch_fuer_pitchbend(self):
        VCSlider.soft_takeover = True
        self.s.apply_midi_binding("pitchbend", 1, 0)
        self.s._value = 200
        self.s.arm_pickup()
        self.s.handle_midi(_pb(1, 0))
        self.assertEqual(self.s.value, 200, "kein Sprung")
        self.s.handle_midi(_pb(1, 16383))               # durchfaehrt den Wert
        self.assertEqual(self.s.value, 255)

    def test_speichern_und_laden(self):
        self.s.apply_midi_binding("pitchbend", 5, 0)
        d = self.s.to_dict()
        self.assertEqual(d["midi_type"], "pitchbend")
        neu = VCSlider("G")
        neu.apply_dict(d)
        self.assertEqual(neu.current_midi_binding(), ("pitchbend", 5, 0))
        neu.mode = SliderMode.SPEED
        self.assertTrue(neu.handle_midi(_pb(5, 16383)))

    def test_cc_layout_bleibt_zeichen_fuer_zeichen(self):
        """Ein CC-Fader schreibt kein neues Feld; ein altes Layout laedt als CC."""
        self.s.apply_midi_binding("cc", 1, 10)
        self.assertNotIn("midi_type", self.s.to_dict())
        alt = VCSlider("A")
        alt.apply_dict({"midi_cc": 10, "midi_ch": 1})
        self.assertEqual(alt.current_midi_binding(), ("cc", 1, 10))

    def test_unlesbarer_typ_laedt_als_cc(self):
        for kaputt in ("note_on", "", None, 5, ["pitchbend"]):
            s = VCSlider("K")
            s.apply_dict({"midi_cc": 10, "midi_ch": 1, "midi_type": kaputt})
            self.assertEqual(s.current_midi_binding(), ("cc", 1, 10), kaputt)

    def test_eigenschaften_dialog_uebernimmt_die_art(self):
        """Pitchbend gewaehlt heisst gebunden — auch wenn das (dann gesperrte)
        Nummernfeld auf „keine“ steht."""
        self.s._midi_bindung_aus_dialog("pitchbend", -1, 3)
        self.assertEqual(self.s.current_midi_binding(), ("pitchbend", 3, 0))
        self.s._midi_bindung_aus_dialog("cc", 12, 2)
        self.assertEqual(self.s.current_midi_binding(), ("cc", 2, 12))
        self.s._midi_bindung_aus_dialog("cc", -1, 0)
        self.assertIsNone(self.s.current_midi_binding())

    def _dialog_und(self, fader, im_dialog):
        """Eigenschaften-Dialog mit ersetztem ``exec``: ``im_dialog(dlg)`` laeuft
        im offenen Dialog, danach OK."""
        from PySide6.QtWidgets import QDialog
        echt = QDialog.exec

        def ersatz(dlg):
            im_dialog(dlg)
            return QDialog.DialogCode.Accepted

        QDialog.exec = ersatz
        try:
            fader._open_properties()
        finally:
            QDialog.exec = echt

    @staticmethod
    def _felder(dlg):
        from PySide6.QtWidgets import QComboBox, QSpinBox
        art = [c for c in dlg.findChildren(QComboBox) if c.findData("pitchbend") >= 0]
        nummer = [f for f in dlg.findChildren(QSpinBox) if f.specialValueText() == "keine"]
        kanal = [f for f in dlg.findChildren(QSpinBox) if f.specialValueText() == "Alle"]
        return art[0], nummer[0], kanal[0]

    def test_eigenschaften_dialog_stellt_auf_pitchbend(self):
        self.s.apply_midi_binding("cc", 1, 10)
        gesehen = {}

        def im_dialog(dlg):
            art, nummer, kanal = self._felder(dlg)
            gesehen["vorher"] = (art.currentData(), nummer.value(), nummer.isEnabled())
            art.setCurrentIndex(art.findData("pitchbend"))
            gesehen["nummer_gesperrt"] = not nummer.isEnabled()
            kanal.setValue(4)

        self._dialog_und(self.s, im_dialog)
        self.assertEqual(gesehen["vorher"], ("cc", 10, True))
        self.assertTrue(gesehen["nummer_gesperrt"])
        self.assertEqual(self.s.current_midi_binding(), ("pitchbend", 4, 0))

    def test_eigenschaften_dialog_ohne_aenderung_laesst_die_bindung(self):
        for bindung in (("cc", 2, 10), ("pitchbend", 5, 0)):
            s = VCSlider("D")
            self.addCleanup(s.deleteLater)
            s.apply_midi_binding(*bindung)
            self._dialog_und(s, lambda dlg: None)
            self.assertEqual(s.current_midi_binding(), bindung)

    def test_eigenschaften_dialog_zurueck_auf_cc_ist_nicht_still_cc_null(self):
        self.s.apply_midi_binding("pitchbend", 5, 0)

        def im_dialog(dlg):
            art, _nummer, _kanal = self._felder(dlg)
            art.setCurrentIndex(art.findData("cc"))

        self._dialog_und(self.s, im_dialog)
        self.assertIsNone(self.s.current_midi_binding())


class RueckmeldungTest(unittest.TestCase):
    """Ein Pitchbend-Fader hat keine Nummer. Frueher fuellte ``data1`` das
    Ziel der LED-Rueckmeldung — bei Pitchbend waere das Note 0 gewesen
    (am Mackie-Pult eine echte LED)."""

    def test_lernen_fuellt_kein_rueckmelde_ziel(self):
        m = mm.MidiMapping(name="F", msg_type="note_on", channel=1, data1=-1,
                           action=mm.ACTION_EXECUTOR_FADER, param="1",
                           midi_out=mm.MidiOutFeedback())
        m.midi_out.trigger_id = -1
        m.set_from_learn_message(_pb(3, 7000))
        self.assertEqual(m.msg_type, "pitchbend")
        self.assertEqual(m.midi_out.trigger_id, -1)

    def test_bauen_fuellt_kein_rueckmelde_ziel(self):
        m = mm.MidiMapping(name="F", msg_type="pitchbend", channel=3, data1=0,
                           action=mm.ACTION_EXECUTOR_FADER, param="1",
                           midi_out=mm.MidiOutFeedback())
        self.assertEqual(m.midi_out.trigger_id, -1)

    def test_cc_fuellt_wie_bisher(self):
        m = mm.MidiMapping(name="F", msg_type="cc", channel=1, data1=48,
                           action=mm.ACTION_EXECUTOR_FADER, param="1",
                           midi_out=mm.MidiOutFeedback())
        self.assertEqual(m.midi_out.trigger_id, 48)
        m.midi_out.trigger_id = -1
        m.set_from_learn_message(_cc(1, 50, 10))
        self.assertEqual(m.midi_out.trigger_id, 50)

    def test_bewegen_sendet_nichts_zurueck(self):
        import time
        midi = _FakeMidiManager()
        alt = mm.get_midi_manager
        mm.get_midi_manager = lambda: midi
        self.addCleanup(setattr, mm, "get_midi_manager", alt)
        mapper = mm.MidiMapper(_FakeState())
        self.addCleanup(mapper.close)
        mapper.add_mapping(mm.MidiMapping(
            name="F", msg_type="pitchbend", channel=1, data1=0,
            action=mm.ACTION_EXECUTOR_FADER, param="1",
            midi_out=mm.MidiOutFeedback()))
        # Gegenprobe im selben Lauf: ein CC-Fader MIT Rueckmeldung sendet.
        mapper.add_mapping(mm.MidiMapping(
            name="C", msg_type="cc", channel=1, data1=48,
            action=mm.ACTION_EXECUTOR_FADER, param="2",
            midi_out=mm.MidiOutFeedback(message_type="cc")))
        midi.sent.clear()
        midi.an_port.clear()
        mapper._on_midi(_pb(1, 16383))
        mapper._on_midi(_cc(1, 48, 100))
        ende = time.monotonic() + 2.0
        while time.monotonic() < ende and ("cc", 1, 48, 100) not in midi.sent:
            time.sleep(0.02)
        self.assertIn(("cc", 1, 48, 100), midi.sent)
        zu_null = [e for e in midi.sent if e[2] == 0]
        self.assertEqual(zu_null, [], "Rueckmeldung an Note/CC 0 gesendet")
        self.assertEqual(midi.an_port, [])


class _StummerManager:
    """Fuer den Lern-Dialog: kein Geraet, nichts oeffnen."""

    def open_all_inputs(self):
        return None

    def subscribe(self, cb):
        return None

    def unsubscribe(self, cb):
        return None

    def list_inputs(self):
        return []


class LernDialogTest(unittest.TestCase):

    def setUp(self):
        alt = mgr.get_midi_manager
        mgr.get_midi_manager = lambda: _StummerManager()
        self.addCleanup(setattr, mgr, "get_midi_manager", alt)

    def _dialog(self, **kw):
        from src.ui.widgets.midi_teach_dialog import MidiTeachDialog
        d = MidiTeachDialog(**kw)
        self.addCleanup(d.deleteLater)
        return d

    def test_fader_dialog_lernt_pitchbend(self):
        d = self._dialog(accept_kinds=("cc", "pitchbend"))
        d._on_midi(_pb(4, 9000))
        self.assertEqual(d._binding, ("pitchbend", 4, 0))
        self.assertIn("Pitchbend", d._status.text())
        self.assertIn("Kanal 4", d._status.text())
        # kein Element des APC-Bilds hervorgehoben (schon gar nicht Note 0)
        self.assertIsNone(d._view._selected)

    def test_untere_bits_aendern_die_bindung_nicht(self):
        d = self._dialog(accept_kinds=("cc", "pitchbend"))
        d._on_midi(_pb(4, 9000))
        d._on_midi(_pb(4, 9001))
        self.assertEqual(d._binding, ("pitchbend", 4, 0))

    def test_tasten_dialog_nimmt_keinen_pitchbend(self):
        d = self._dialog(accept_kinds=("note", "cc"))
        d._on_midi(_pb(4, 9000))
        self.assertIsNone(d._binding)

    def test_vorbelegung_mit_pitchbend(self):
        d = self._dialog(current=("pitchbend", 2, 0),
                         accept_kinds=("cc", "pitchbend"))
        self.assertEqual(d._binding, ("pitchbend", 2, 0))
        self.assertIsNone(d._view._selected)
        self.assertIn("Kanal 2", d._status.text())

    def test_cc_wie_bisher(self):
        d = self._dialog(accept_kinds=("cc", "pitchbend"))
        d._on_midi(_cc(1, 50, 64))
        self.assertEqual(d._binding, ("cc", 1, 50))
        self.assertEqual(d._view._selected, ("cc", 50))


class MonitorTest(unittest.TestCase):

    @staticmethod
    def _monitor(msg) -> str:
        """Die Zeile, die die MIDI-Ansicht fuer ``msg`` in den Monitor schreibt."""
        from src.ui.views.midi_view import MidiView
        zeilen = []
        MidiView._on_midi_msg_ui(
            SimpleNamespace(_console=SimpleNamespace(appendPlainText=zeilen.append)),
            msg)
        return zeilen[0]

    def test_pitchbend_zeile_nennt_den_14_bit_wert(self):
        zeile = self._monitor(_pb(3, 8192))
        self.assertIn("PITCH", zeile)
        self.assertIn("CH 3", zeile)
        self.assertIn("8192", zeile)
        self.assertIn("50.0 %", zeile)
        self.assertNotIn("D1=", zeile)

    def test_cc_zeile_wie_bisher(self):
        self.assertEqual(self._monitor(_cc(1, 12, 64)),
                         "CC    [X-Touch] CH 1 D1= 12 D2= 64")

    def test_lernen_in_der_midi_ansicht_fragt_nicht_nach_led_werten(self):
        from src.ui.views.midi_view import MidiView
        m = mm.MidiMapping(name="F", msg_type="note_on", channel=1, data1=5,
                           action=mm.ACTION_EXECUTOR_FADER, param="1")
        gefragt, zeilen = [], []
        ansicht = SimpleNamespace(
            _learn_target_row=0,
            _mapper=SimpleNamespace(get_mappings=lambda: [m]),
            _prompt_feedback_values=gefragt.append,
            _refresh_map_table=lambda: None,
            _append_log=zeilen.append,
        )
        MidiView._on_learn_received(ansicht, _pb(6, 1234))
        self.assertEqual(gefragt, [])
        self.assertEqual(m.msg_type, "pitchbend")
        self.assertEqual(m.midi_in.message_type, "pitchbend")
        self.assertEqual((m.channel, m.data1), (6, 0))
        self.assertIsNone(m.midi_out)
        self.assertIn("Pitchbend", zeilen[-1])
        # Gegenprobe: bei CC wird wie bisher gefragt.
        MidiView._on_learn_received(ansicht, _cc(1, 50, 64))
        self.assertEqual(gefragt, [m])

    def test_midi_ansicht_lernt_mit_pitchbend(self):
        from src.ui.views.midi_view import MidiView
        aufrufe = []
        ansicht = SimpleNamespace(
            _map_table=SimpleNamespace(
                selectedIndexes=lambda: [SimpleNamespace(row=lambda: 2)]),
            _append_log=lambda _t: None,
            _log_signal=SimpleNamespace(learn_received=SimpleNamespace(emit=lambda _m: None)),
            _mapper=SimpleNamespace(
                start_learn=lambda cb, **kw: aufrufe.append(kw)),
        )
        MidiView._start_learn(ansicht)
        self.assertEqual(aufrufe, [{"pitchbend": True}])
        self.assertEqual(ansicht._learn_target_row, 2)


class ProfilEditorTest(unittest.TestCase):

    def test_gelernter_pitchbend_bekommt_keine_nummer(self):
        from src.ui.widgets.input_profile_editor import InputProfileEditor
        profil = SimpleNamespace(mappings=[])
        editor = SimpleNamespace(
            _profile=profil,
            _table=SimpleNamespace(currentRow=lambda: -1),
            _save_meta=lambda: None,
            _refresh_table=lambda: None,
        )
        InputProfileEditor._on_learned(editor, _pb(7, 12345))
        m = profil.mappings[0]
        self.assertEqual((m.msg_type, m.channel, m.data1), ("pitchbend", 7, 0))
        self.assertEqual(m.midi_in.message_type, "pitchbend")
        # vorhandene Zeile umlernen
        editor._table = SimpleNamespace(currentRow=lambda: 0)
        InputProfileEditor._on_learned(editor, _pb(8, 99))
        self.assertEqual((m.msg_type, m.channel, m.data1), ("pitchbend", 8, 0))
        InputProfileEditor._on_learned(editor, _cc(1, 48, 10))
        self.assertEqual((m.msg_type, m.channel, m.data1), ("cc", 1, 48))


if __name__ == "__main__":
    unittest.main()
