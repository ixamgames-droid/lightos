"""MIDI-9, MIDI-11, MIDI-12, MIDI-13: weitere Ausloeser im MIDI-Mapper.

Der Manager dekodierte Program Change, der Mapper bot ihn aber nicht an;
Endlos-Encoder, 14-Bit-CC und NRPN liefen nur als einzelne 7-Bit-CCs.

Abgesichert:

* MIDI-9 — Program Change: Bindung je Programmnummer, Druck-Semantik
  (kein Loslassen), Lernen, Speichern/Laden;
* MIDI-11 — Relativ-Encoder: Zweierkomplement, Binaer-Offset, Vorzeichenbit
  als Schritt +/-, Modus je Zuordnung, setzt an der echten Stellung an;
* MIDI-12 — 14-Bit-CC: MSB (CC 0..31) + LSB (CC +32), je Zuordnung; der MSB
  allein laesst den Wert nicht springen;
* MIDI-13 — NRPN: CC 99/98 + 6/38 werden in der gemeinsamen Empfangsschleife
  zu einem eigenen Ausloesertyp — ueber den python-rtmidi- UND den WinMM-Weg;
* Abwaertskompatibilitaet: alte Mappings laden und speichern unveraendert;
* MIDI-Ansicht: Spalte „Typ" kennt die neuen Typen.
"""
from __future__ import annotations

import json
import os
import time
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                           # noqa: E402

import src.core.midi.midi_manager as mgr                # noqa: E402
import src.core.midi.midi_mapper as mm                  # noqa: E402
from test_midi_mapper import _FakeMidiManager, _FakeState   # noqa: E402


def _roh(raw, port="Pult"):
    return mgr._decode(list(raw), port)


def _cc(nummer, wert, kanal=1, port="Pult"):
    return _roh([0xB0 | (kanal - 1), nummer, wert], port)


def _pc(programm, kanal=1, port="Pult"):
    return _roh([0xC0 | (kanal - 1), programm], port)


def _nrpn_folge(param, wert14, kanal=1, mit_lsb=True):
    st = 0xB0 | (kanal - 1)
    folge = [[st, 99, (param >> 7) & 0x7F], [st, 98, param & 0x7F],
             [st, 6, (wert14 >> 7) & 0x7F]]
    if mit_lsb:
        folge.append([st, 38, wert14 & 0x7F])
    return folge


def _dekodiert(folgen, port="Pult"):
    """Wie die Empfangsschleife: _decode + NRPN-Dekoder, alle Ergebnisse."""
    dek = mgr.NrpnDekoder()
    raus = []
    for raw in folgen:
        m = _roh(raw, port)
        raus.append(m)
        n = dek.einspeisen(m)
        if n is not None:
            raus.append(n)
    return raus


class _MapperTest(unittest.TestCase):

    def setUp(self):
        self.fake_midi = _FakeMidiManager()
        self.old_get = mm.get_midi_manager
        mm.get_midi_manager = lambda: self.fake_midi
        self.state = _FakeState()
        self.mapper = mm.MidiMapper(self.state)

    def tearDown(self):
        self.mapper.close()
        mm.get_midi_manager = self.old_get

    def _fader(self, msg_type, data1, modus="", slot=1):
        m = mm.MidiMapping(name="F", msg_type=msg_type, channel=1, data1=data1,
                           action=mm.ACTION_EXECUTOR_FADER, param=str(slot),
                           button_mode=mm.BUTTON_CONTINUOUS)
        m.midi_in.cc_modus = modus
        self.mapper.add_mapping(m)
        return self.state.playback_engine.get_executor(slot)


# ── MIDI-9: Program Change ──────────────────────────────────────────────────

class ProgramChangeTest(_MapperTest):

    def test_beide_laengen_werden_pc(self):
        """rtmidi liefert 2 Bytes, WinMM immer 3 — beides ist Program Change."""
        for raw in ([0xC2, 5], [0xC2, 5, 0]):
            m = _roh(raw)
            self.assertEqual((m.msg_type, m.channel, m.data1), ("pc", 3, 5))

    def test_bindung_je_programmnummer(self):
        b = mm.MidiInBinding(channel=1, trigger_id=5, message_type="pc")
        self.assertTrue(b.matches(_pc(5)))
        self.assertFalse(b.matches(_pc(6)))
        self.assertFalse(b.matches(_cc(5, 127)))
        self.assertFalse(mm.MidiInBinding(trigger_id=5, message_type="cc")
                         .matches(_pc(5)))

    def test_pc_loest_go_aus_jede_nachricht_ein_druck(self):
        m = mm.MidiMapping(name="PC", msg_type="pc", channel=1, data1=3,
                           action=mm.ACTION_EXECUTOR_GO, param="2")
        self.mapper.add_mapping(m)
        ex = self.state.playback_engine.get_executor(2)
        self.mapper._on_midi(_pc(3))
        self.mapper._on_midi(_pc(3))
        self.mapper._on_midi(_pc(4))
        self.assertEqual(ex.go_count, 2)
        self.assertEqual(ex.back_count, 0)

    def test_pc_startet_szene_im_toggle(self):
        m = mm.MidiMapping(name="Szene", msg_type="pc", channel=1, data1=7,
                           target_id="function:42")
        self.mapper.add_mapping(m)
        fm = self.state.function_manager
        self.mapper._on_midi(_pc(7))
        self.assertTrue(fm.is_running(42))
        self.mapper._on_midi(_pc(7))
        self.assertFalse(fm.is_running(42))

    def test_pc_flash_bleibt_nicht_haengen(self):
        m = mm.MidiMapping(name="Fl", msg_type="pc", channel=1, data1=1,
                           action=mm.ACTION_EXECUTOR_FLASH, param="1")
        self.mapper.add_mapping(m)
        self.mapper._on_midi(_pc(1))
        self.assertFalse(self.state.playback_engine.get_executor(1)._flash_active)

    def test_lernen_und_speichern(self):
        gelernt = []
        self.mapper.start_learn(gelernt.append, pitchbend=True)
        self.mapper._on_midi(_pc(9, kanal=2))
        self.assertEqual(len(gelernt), 1)
        m = mm.MidiMapping(name="X", action=mm.ACTION_EXECUTOR_GO, param="1")
        m.set_from_learn_message(gelernt[0])
        self.assertEqual((m.msg_type, m.channel, m.data1), ("pc", 2, 9))
        d = m.to_config_dict()
        self.assertEqual(d["midi_in"]["message_type"], "pc")
        neu = mm.MidiMapping.from_config_dict(json.loads(json.dumps(d)))
        self.assertEqual(neu.msg_type, "pc")
        self.assertTrue(neu.midi_in.matches(_pc(9, kanal=2)))

    def test_lernen_ohne_schalter_wie_bisher(self):
        """Aufrufer, die nur Tasten binden, bekommen weiter kein PC."""
        gelernt = []
        self.mapper.start_learn(gelernt.append)
        self.mapper._on_midi(_pc(9))
        self.assertEqual(gelernt, [])


# ── MIDI-11: Relativ-Encoder ────────────────────────────────────────────────

class RelativEncoderTest(_MapperTest):

    def test_schritte_der_drei_kodierungen(self):
        zk, bo, vz = (mm.CC_REL_ZWEIERKOMPLEMENT, mm.CC_REL_BINAER_OFFSET,
                      mm.CC_REL_VORZEICHENBIT)
        self.assertEqual([mm.relativ_schritt(zk, w) for w in (1, 3, 127, 125, 0)],
                         [1, 3, -1, -3, 0])
        self.assertEqual([mm.relativ_schritt(bo, w) for w in (65, 67, 63, 61, 64)],
                         [1, 3, -1, -3, 0])
        self.assertEqual([mm.relativ_schritt(vz, w) for w in (1, 3, 65, 67, 0)],
                         [1, 3, -1, -3, 0])

    def test_encoder_bewegt_ab_der_echten_stellung(self):
        ex = self._fader("cc", 16, mm.CC_REL_ZWEIERKOMPLEMENT)
        ex.fader_value = 0.5
        self.mapper._on_midi(_cc(16, 1))
        self.assertAlmostEqual(ex.fader_value, 0.5 + 1 / 127)
        self.mapper._on_midi(_cc(16, 127))
        self.mapper._on_midi(_cc(16, 127))
        self.assertAlmostEqual(ex.fader_value, 0.5 - 1 / 127)
        ex.fader_value = 0.2                    # anderswo verstellt
        self.mapper._on_midi(_cc(16, 2))
        self.assertAlmostEqual(ex.fader_value, 0.2 + 2 / 127)

    def test_binaer_offset_und_vorzeichenbit(self):
        ex = self._fader("cc", 17, mm.CC_REL_BINAER_OFFSET, slot=3)
        ex.fader_value = 0.5
        self.mapper._on_midi(_cc(17, 63))       # -1, nicht "Stellung 63"
        self.assertAlmostEqual(ex.fader_value, 0.5 - 1 / 127)
        ex2 = self._fader("cc", 18, mm.CC_REL_VORZEICHENBIT, slot=4)
        ex2.fader_value = 0.5
        self.mapper._on_midi(_cc(18, 65))       # -1
        self.assertAlmostEqual(ex2.fader_value, 0.5 - 1 / 127)

    def test_grenzen_bleiben_0_bis_1(self):
        ex = self._fader("cc", 16, mm.CC_REL_ZWEIERKOMPLEMENT)
        ex.fader_value = 0.0
        self.mapper._on_midi(_cc(16, 127))
        self.assertEqual(ex.fader_value, 0.0)
        ex.fader_value = 1.0
        self.mapper._on_midi(_cc(16, 5))
        self.assertEqual(ex.fader_value, 1.0)

    def test_absolut_bleibt_absolut(self):
        ex = self._fader("cc", 16)
        ex.fader_value = 0.5
        self.mapper._on_midi(_cc(16, 1))
        self.assertAlmostEqual(ex.fader_value, 1 / 127)

    def test_modus_wird_gespeichert_und_geladen(self):
        m = mm.MidiMapping(name="E", msg_type="cc", data1=16,
                           action=mm.ACTION_GRAND_MASTER)
        m.midi_in.cc_modus = mm.CC_REL_BINAER_OFFSET
        d = json.loads(json.dumps(m.to_config_dict()))
        self.assertEqual(d["midi_in"]["cc_modus"], "rel_bo")
        neu = mm.MidiMapping.from_config_dict(d)
        self.assertEqual(neu.midi_in.cc_modus, mm.CC_REL_BINAER_OFFSET)

    def test_neu_lernen_behaelt_den_modus(self):
        m = mm.MidiMapping(name="E", msg_type="cc", data1=16,
                           action=mm.ACTION_GRAND_MASTER)
        m.midi_in.cc_modus = mm.CC_REL_ZWEIERKOMPLEMENT
        m.set_from_learn_message(_cc(20, 1))
        self.assertEqual((m.data1, m.midi_in.cc_modus), (20, "rel_zk"))


# ── MIDI-12: 14-Bit-CC ──────────────────────────────────────────────────────

class Cc14BitTest(_MapperTest):

    def test_msb_und_lsb_ergeben_14_bit(self):
        ex = self._fader("cc", 7, mm.CC_14BIT)
        self.mapper._on_midi(_cc(7, 0x40))          # MSB (noch nie ein LSB)
        self.mapper._on_midi(_cc(39, 0x01))         # LSB
        self.assertAlmostEqual(ex.fader_value, 0x2001 / 16383)
        self.mapper._on_midi(_cc(7, 0x7F))
        self.mapper._on_midi(_cc(39, 0x7F))
        self.assertEqual(ex.fader_value, 1.0)

    def test_msb_allein_springt_nicht(self):
        ex = self._fader("cc", 7, mm.CC_14BIT)
        self.mapper._on_midi(_cc(7, 10))
        self.mapper._on_midi(_cc(39, 127))
        vorher = ex.fader_value
        self.assertAlmostEqual(vorher, (10 * 128 + 127) / 16383)
        self.mapper._on_midi(_cc(7, 11))            # MSB allein: kein Sprung
        self.assertEqual(ex.fader_value, vorher)
        self.mapper._on_midi(_cc(39, 0))
        self.assertAlmostEqual(ex.fader_value, (11 * 128) / 16383)

    def test_nur_msb_regler_bleibt_bedienbar(self):
        ex = self._fader("cc", 7, mm.CC_14BIT)
        self.mapper._on_midi(_cc(7, 127))
        self.assertEqual(ex.fader_value, 1.0)

    def test_ohne_schalter_bleibt_cc_7_bit(self):
        ex = self._fader("cc", 7)
        self.mapper._on_midi(_cc(7, 64))
        self.mapper._on_midi(_cc(39, 127))          # fremder CC, kein LSB
        self.assertAlmostEqual(ex.fader_value, 64 / 127)

    def test_bindung_nimmt_lsb_nur_mit_schalter(self):
        b = mm.MidiInBinding(trigger_id=7, message_type="cc", cc_modus="14bit")
        self.assertTrue(b.matches(_cc(7, 1)))
        self.assertTrue(b.matches(_cc(39, 1)))
        self.assertFalse(b.matches(_cc(40, 1)))
        self.assertFalse(mm.MidiInBinding(trigger_id=7, message_type="cc")
                         .matches(_cc(39, 1)))

    def test_lsb_druckt_keine_taste(self):
        m = mm.MidiMapping(name="GO", msg_type="cc", data1=7,
                           action=mm.ACTION_EXECUTOR_GO, param="1")
        m.midi_in.cc_modus = mm.CC_14BIT
        self.mapper.add_mapping(m)
        self.mapper._on_midi(_cc(39, 127))
        self.assertEqual(self.state.playback_engine.get_executor(1).go_count, 0)
        self.mapper._on_midi(_cc(7, 127))
        self.assertEqual(self.state.playback_engine.get_executor(1).go_count, 1)


# ── MIDI-13: NRPN ───────────────────────────────────────────────────────────

class NrpnDekoderTest(unittest.TestCase):

    def test_folge_mit_lsb(self):
        """Erste Folge: vor dem ersten LSB meldet der MSB (das Geraet koennte
        ein reines 7-Bit-Geraet sein), der LSB praezisiert. Ab dann genau
        eine Meldung je Folge, beim LSB."""
        raus = _dekodiert(_nrpn_folge(1234, 9999) + _nrpn_folge(1234, 100))
        nrpn = [m for m in raus if m.msg_type == "nrpn"]
        self.assertEqual([m.data1 for m in nrpn], [1234, 1234, 1234])
        self.assertEqual(nrpn[1].wert14bit, 9999)
        self.assertEqual(nrpn[2].wert14bit, 100)
        self.assertEqual(mgr.wert14(nrpn[1]), 9999)
        self.assertAlmostEqual(mgr.fader_wert(nrpn[1]), 9999 / 16383)
        # Die einzelnen CCs bleiben (Bestand).
        self.assertEqual([m.data1 for m in raus if m.msg_type == "cc"],
                         [99, 98, 6, 38] * 2)

    def test_nur_msb_geraet(self):
        raus = _dekodiert(_nrpn_folge(5, 127 << 7, mit_lsb=False))
        nrpn = [m for m in raus if m.msg_type == "nrpn"]
        self.assertEqual(len(nrpn), 1)
        self.assertEqual(nrpn[0].wert14bit, 16383)

    def test_msb_allein_springt_nicht_nach_lsb(self):
        folge = _nrpn_folge(5, 0x0A7F) + [[0xB0, 6, 0x0B]]   # zweiter MSB allein
        nrpn = [m for m in _dekodiert(folge) if m.msg_type == "nrpn"]
        self.assertEqual([m.wert14bit for m in nrpn][1:], [0x0A7F])

    def test_kanal_und_port_getrennt(self):
        dek = mgr.NrpnDekoder()
        for raw in _nrpn_folge(3, 100, kanal=1)[:2]:
            dek.einspeisen(_roh(raw, "A"))
        # Wert auf anderem Kanal / anderem Port: keine NRPN-Wahl dort.
        self.assertIsNone(dek.einspeisen(_roh([0xB1, 6, 1], "A")))
        self.assertIsNone(dek.einspeisen(_roh([0xB0, 6, 1], "B")))
        self.assertIsNotNone(dek.einspeisen(_roh([0xB0, 6, 1], "A")))

    def test_rpn_und_null_parameter_beenden_die_wahl(self):
        dek = mgr.NrpnDekoder()
        for raw in _nrpn_folge(3, 100)[:2] + [[0xB0, 101, 0], [0xB0, 100, 0]]:
            dek.einspeisen(_roh(raw))
        self.assertIsNone(dek.einspeisen(_roh([0xB0, 6, 1])))
        for raw in ([0xB0, 99, 127], [0xB0, 98, 127]):
            dek.einspeisen(_roh(raw))
        self.assertIsNone(dek.einspeisen(_roh([0xB0, 6, 1])))


class NrpnMapperTest(_MapperTest):

    def _speise(self, folgen):
        for m in _dekodiert(folgen):
            self.mapper._on_midi(m)

    def test_nrpn_fader_mit_14_bit(self):
        ex = self._fader("nrpn", 1234)
        self._speise(_nrpn_folge(1234, 8192))
        self.assertAlmostEqual(ex.fader_value, 8192 / 16383)
        self._speise(_nrpn_folge(1235, 16383))      # anderer Parameter
        self.assertAlmostEqual(ex.fader_value, 8192 / 16383)

    def test_nrpn_bindung_und_speichern(self):
        b = mm.MidiInBinding(channel=1, trigger_id=1234, message_type="nrpn")
        nrpn = [m for m in _dekodiert(_nrpn_folge(1234, 1)) if m.msg_type == "nrpn"]
        self.assertTrue(b.matches(nrpn[0]))
        self.assertFalse(b.matches(_cc(1234 & 0x7F, 1)))
        m = mm.MidiMapping(name="N", msg_type="nrpn", data1=1234,
                           action=mm.ACTION_GRAND_MASTER,
                           midi_out=mm.MidiOutFeedback())
        self.assertLess(m.midi_out.trigger_id, 0)   # keine "Note 1234"
        neu = mm.MidiMapping.from_config_dict(
            json.loads(json.dumps(m.to_config_dict())))
        self.assertEqual((neu.msg_type, neu.data1), ("nrpn", 1234))

    def test_lernen_nimmt_den_nrpn_nicht_cc_99(self):
        gelernt = []
        self.mapper.start_learn(gelernt.append, pitchbend=True)
        self._speise(_nrpn_folge(700, 4000))
        self.assertEqual(len(gelernt), 1)
        self.assertEqual((gelernt[0].msg_type, gelernt[0].data1), ("nrpn", 700))

    def test_regler_auf_cc_99_bleibt_lernbar(self):
        gelernt = []
        self.mapper.start_learn(gelernt.append, pitchbend=True)
        self.mapper._on_midi(_cc(99, 10))
        self.mapper._on_midi(_cc(99, 11))
        self.assertEqual([(m.msg_type, m.data1) for m in gelernt], [("cc", 99)])


    def test_lernen_nimmt_nrpn_ohne_neue_parameterwahl(self):
        """Pruefung: viele Geraete waehlen den Parameter (CC 99/98) nur einmal
        und schicken danach nur noch Werte (CC 6/38). Hat die Wahl vor dem
        Lernen stattgefunden, darf das Lernen nicht den nackten CC 6 nehmen."""
        dek = mgr.NrpnDekoder()

        def speise(folge):
            for raw in folge:
                m = _roh(raw)
                self.mapper._on_midi(m)
                n = dek.einspeisen(m)
                if n is not None:
                    self.mapper._on_midi(n)

        speise(_nrpn_folge(700, 4000))              # Wahl VOR dem Lernen
        gelernt = []
        self.mapper.start_learn(gelernt.append, pitchbend=True)
        speise([[0xB0, 6, 40], [0xB0, 38, 1]])      # nur noch Werte
        self.assertEqual([(m.msg_type, m.data1) for m in gelernt],
                         [("nrpn", 700)])

    def test_regler_auf_cc_6_bleibt_lernbar(self):
        gelernt = []
        self.mapper.start_learn(gelernt.append, pitchbend=True)
        self.mapper._on_midi(_cc(6, 10))
        self.mapper._on_midi(_cc(6, 11))
        self.assertEqual([(m.msg_type, m.data1) for m in gelernt], [("cc", 6)])


class Cc14BitNurFuerMsbTest(unittest.TestCase):

    def test_ab_cc_32_kein_lsb_dazu(self):
        """Pruefung: 14 Bit gibt es nur fuer CC 0..31. Auf CC 40 eingeschaltet
        darf die Bindung nicht CC 72 als „LSB" mitnehmen."""
        b = mm.MidiInBinding(trigger_id=40, message_type="cc", cc_modus="14bit")
        self.assertTrue(b.matches(_cc(40, 1)))
        self.assertFalse(b.matches(_cc(72, 1)))


# ── Beide Eingangswege (python-rtmidi und WinMM) ───────────────────────────

class _FakeWinMMInput:
    def __init__(self, device_idx, port_name, on_raw):
        self.on_raw = on_raw

    def is_alive(self):
        return True

    def close_port(self):
        pass


class _FakeRtMidiIn:
    def __init__(self):
        self.cb = None

    def get_port_count(self):
        return 1

    def get_port_name(self, _i):
        return "Pult"

    def open_port(self, _i):
        pass

    def set_callback(self, cb):
        self.cb = cb
        _FakeRtMidiIn.letzter = self

    def close_port(self):
        pass


def _empfangen(manager, speise, roh_folgen):
    raus = []
    manager.subscribe(raus.append)
    for raw in roh_folgen:
        speise(raw)
    frist = time.monotonic() + 2.0
    erwartet = len(roh_folgen)
    while time.monotonic() < frist and len(raus) < erwartet + 2:
        time.sleep(0.01)
    time.sleep(0.05)
    return raus


@pytest.mark.parametrize("weg", ["winmm", "rtmidi"])
def test_beide_eingangswege_liefern_pc_und_nrpn(monkeypatch, weg):
    if weg == "winmm":
        monkeypatch.setattr(mgr, "_USE_WINMM", True)
        monkeypatch.setattr(mgr, "_winmm_list_inputs", lambda: ["Pult"],
                            raising=False)
        monkeypatch.setattr(mgr, "WinMMInput", _FakeWinMMInput, raising=False)
    else:
        monkeypatch.setattr(mgr, "_USE_WINMM", False)
        monkeypatch.setattr(mgr, "RTMIDI_OK", True)
        monkeypatch.setattr(mgr, "rtmidi",
                            types.SimpleNamespace(MidiIn=_FakeRtMidiIn,
                                                  MidiOut=object),
                            raising=False)
    manager = mgr.MidiManager()
    try:
        assert manager.open_input("Pult")
        if weg == "winmm":
            handle = manager._inputs["Pult"]

            def speise(raw):    # WinMM meldet immer drei Bytes
                handle.on_raw((list(raw) + [0, 0])[:3], "Pult")
            pc = [0xC0, 12, 0]
        else:
            fake = _FakeRtMidiIn.letzter

            def speise(raw):    # rtmidi: (Bytes, Zeitstempel)
                fake.cb((list(raw), 0.0), None)
            pc = [0xC0, 12]
        raus = _empfangen(manager, speise, [pc] + _nrpn_folge(321, 5000))
    finally:
        manager.close_all()
    arten = [(m.msg_type, m.data1) for m in raus]
    assert ("pc", 12) in arten
    nrpn = [m for m in raus if m.msg_type == "nrpn"]
    assert [m.data1 for m in nrpn] == [321, 321]
    assert nrpn[-1].wert14bit == 5000


# ── Abwaertskompatibilitaet ─────────────────────────────────────────────────

ALT = [
    {"id": "a1", "name": "GO", "target": "executor_go:1",
     "midi_in": {"device": "", "channel": 1, "trigger_id": 0,
                 "message_type": "note"},
     "button_mode": "press", "midi_out": None,
     "continuous_min": 0.0, "continuous_max": 1.0},
    {"id": "a2", "name": "GM", "target": "grand_master",
     "midi_in": {"device": "APC", "channel": 1, "trigger_id": 56,
                 "message_type": "cc"},
     "button_mode": "continuous", "midi_out": None,
     "continuous_min": 0.0, "continuous_max": 1.0},
]


class AltbestandTest(_MapperTest):

    def test_alte_datei_laedt_und_speichert_unveraendert(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            pfad = os.path.join(d, "alt.json")
            with open(pfad, "w", encoding="utf-8") as f:
                json.dump(ALT, f)
            self.assertTrue(self.mapper.load(pfad))
            for m in self.mapper.get_mappings():
                self.assertEqual(m.midi_in.cc_modus, "")
            raus = os.path.join(d, "neu.json")
            self.assertTrue(self.mapper.save(raus))
            with open(raus, encoding="utf-8") as f:
                self.assertEqual(json.load(f), ALT)

    def test_unbekannter_modus_wird_absolut(self):
        b = mm.MidiInBinding.from_dict({"message_type": "cc", "cc_modus": "xyz"})
        self.assertEqual(b.cc_modus, "")


# ── MIDI-Ansicht: Spalte „Typ" ──────────────────────────────────────────────

class TypSpalteTest(unittest.TestCase):

    def test_text_hin_und_zurueck(self):
        for text in ("note_on", "cc", "cc14", "cc_rel_zk", "cc_rel_bo",
                     "cc_rel_vz", "pc", "nrpn", "pitchbend"):
            msg_type, modus = mm.typ_aus_text(text)
            m = mm.MidiMapping(name="T", msg_type=msg_type, data1=1)
            m.midi_in.cc_modus = modus
            self.assertEqual(mm.typ_text(m), text)

    def test_view_spalte_typ_setzt_modus(self):
        from PySide6.QtWidgets import QApplication, QTableWidgetItem
        _app = QApplication.instance() or QApplication([])   # noqa: F841
        import src.ui.views.midi_view as mv
        mapping = mm.MidiMapping(name="T", msg_type="cc", data1=7,
                                 action=mm.ACTION_GRAND_MASTER)
        view = mv.MidiView.__new__(mv.MidiView)
        view._mapper = types.SimpleNamespace(get_mappings=lambda: [mapping])

        class _Tabelle:
            def item(self, *_a):
                return None

            def blockSignals(self, *_a):
                pass
        view._map_table = _Tabelle()
        zelle = QTableWidgetItem("cc14")
        zelle.row = lambda: 0
        zelle.column = lambda: 2
        view._on_map_item_changed(zelle)
        self.assertEqual((mapping.msg_type, mapping.midi_in.cc_modus),
                         ("cc", "14bit"))
        zelle.setText("pc")
        view._on_map_item_changed(zelle)
        self.assertEqual((mapping.msg_type, mapping.midi_in.message_type,
                          mapping.midi_in.cc_modus), ("pc", "pc", ""))


if __name__ == "__main__":
    unittest.main()
