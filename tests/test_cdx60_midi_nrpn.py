"""CDX-60: Codex-Befunde zu #1195 (MIDI-13, NRPN).

Abgesichert:

* P1 — die erste 14-Bit-Folge eines Parameters meldet vorlaeufig beim MSB
  (CC 6) und praezisiert beim LSB (CC 38). Eine Tasten-Aktion darf dadurch
  nicht doppelt ausloesen (GO zweimal, Toggle an und gleich wieder aus);
  ein Fader bekommt den praezisierten Wert weiterhin;
* P2 — „dieses Geraet sendet LSB" gilt je Parameter, nicht je Kanal: ein
  reiner 7-Bit-Parameter bleibt bedienbar, nachdem ein anderer Parameter
  auf demselben Kanal einen LSB geschickt hat;
* P3 — der Monitor drosselt den NRPN getrennt vom rohen CC-Strom: die
  Empfangsschleife stellt den NRPN direkt nach seinem CC zu, mit gemeinsamer
  Drossel kam er nie an.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.midi.midi_manager as mgr                # noqa: E402
import src.core.midi.midi_mapper as mm                  # noqa: E402
from test_midi_mapper import _FakeMidiManager, _FakeState   # noqa: E402
from test_midi9_11_12_13_ausloeser import (            # noqa: E402
    _dekodiert, _nrpn_folge, _roh)


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

    def _speise(self, folgen):
        for m in _dekodiert(folgen):
            self.mapper._on_midi(m)


class ErsteFolgeKeinDoppelDruckTest(_MapperTest):
    """P1: erste Folge mit LSB, Wert in der oberen Haelfte."""

    def test_go_genau_einmal(self):
        m = mm.MidiMapping(name="GO", msg_type="nrpn", channel=1, data1=3,
                           action=mm.ACTION_EXECUTOR_GO, param="2")
        self.mapper.add_mapping(m)
        ex = self.state.playback_engine.get_executor(2)
        self._speise(_nrpn_folge(3, 10000))
        self.assertEqual(ex.go_count, 1)
        # Folgende Folgen am SELBEN Dekoder (wie die Empfangsschleife): eine
        # Meldung je Folge -> ein Druck je Folge.
        ex.go_count = 0
        self._speise(_nrpn_folge(3, 10000) + _nrpn_folge(3, 9000)
                     + _nrpn_folge(3, 12000))
        self.assertEqual(ex.go_count, 3)

    def test_toggle_bleibt_an(self):
        m = mm.MidiMapping(name="Szene", msg_type="nrpn", channel=1, data1=3,
                           target_id="function:42",
                           button_mode=mm.BUTTON_TOGGLE)
        self.mapper.add_mapping(m)
        self._speise(_nrpn_folge(3, 16000))
        self.assertTrue(self.state.function_manager.is_running(42))

    def test_reines_7_bit_geraet_druckt_weiter_jedes_mal(self):
        m = mm.MidiMapping(name="GO", msg_type="nrpn", channel=1, data1=3,
                           action=mm.ACTION_EXECUTOR_GO, param="2")
        self.mapper.add_mapping(m)
        ex = self.state.playback_engine.get_executor(2)
        for _ in range(3):
            self._speise(_nrpn_folge(3, 127 << 7, mit_lsb=False))
        self.assertEqual(ex.go_count, 3)

    def test_fader_bekommt_den_praezisierten_wert(self):
        m = mm.MidiMapping(name="F", msg_type="nrpn", channel=1, data1=3,
                           action=mm.ACTION_EXECUTOR_FADER, param="1",
                           button_mode=mm.BUTTON_CONTINUOUS)
        self.mapper.add_mapping(m)
        ex = self.state.playback_engine.get_executor(1)
        self._speise(_nrpn_folge(3, 10001))
        self.assertAlmostEqual(ex.fader_value, 10001 / 16383)

    def test_dekoder_markiert_nur_die_praezisierung(self):
        nrpn = [m for m in _dekodiert(_nrpn_folge(3, 10000)
                                      + _nrpn_folge(3, 500))
                if m.msg_type == "nrpn"]
        self.assertEqual([m.nrpn_praezisiert for m in nrpn],
                         [False, True, False])


class LsbJeParameterTest(unittest.TestCase):
    """P2: die LSB-Erfahrung eines Parameters bremst keinen anderen."""

    def test_7_bit_parameter_nach_14_bit_parameter(self):
        folge = (_nrpn_folge(1, 9999)                       # sendet LSB
                 + _nrpn_folge(2, 100 << 7, mit_lsb=False))  # nur MSB
        nrpn = [m for m in _dekodiert(folge) if m.msg_type == "nrpn"]
        self.assertEqual([m.data1 for m in nrpn], [1, 1, 2])
        self.assertEqual(nrpn[-1].wert14bit, round(100 * 16383 / 127))

    def test_14_bit_parameter_springt_weiter_nicht(self):
        folge = (_nrpn_folge(1, 0x0A7F) + _nrpn_folge(2, 5 << 7, mit_lsb=False)
                 + _nrpn_folge(1, 0x0B01))
        nrpn = [m for m in _dekodiert(folge) if m.msg_type == "nrpn"]
        p1 = [m.wert14bit for m in nrpn if m.data1 == 1]
        # Parameter 1 meldet ab dem ersten LSB nur noch beim LSB.
        self.assertEqual(p1[1:], [0x0A7F, 0x0B01])

    def test_rpn_wahl_dazwischen(self):
        dek = mgr.NrpnDekoder()
        for raw in _nrpn_folge(1, 9999) + [[0xB0, 101, 0], [0xB0, 100, 0],
                                           [0xB0, 6, 2], [0xB0, 38, 0]]:
            dek.einspeisen(_roh(raw))
        raus = [dek.einspeisen(_roh(raw))
                for raw in _nrpn_folge(7, 64 << 7, mit_lsb=False)]
        self.assertIsNotNone(raus[-1])
        self.assertEqual(raus[-1].data1, 7)


class MonitorDrosselTest(unittest.TestCase):
    """P3: der NRPN direkt nach seinem CC erreicht den Monitor."""

    def _view(self):
        import src.ui.views.midi_view as mv
        view = mv.MidiView.__new__(mv.MidiView)
        view._monitor_active = True
        view._last_monitor_emit = 0.0
        gesehen = []

        class _Signal:
            def emit(self, msg):
                gesehen.append(msg)

        class _LogSignal:
            msg_received = _Signal()

        view._log_signal = _LogSignal()
        return view, gesehen

    def test_nrpn_nach_seinem_cc(self):
        view, gesehen = self._view()
        for m in _dekodiert(_nrpn_folge(1234, 9999, mit_lsb=False)):
            view._on_midi_msg(m)
        self.assertIn("nrpn", [m.msg_type for m in gesehen])

    def test_nrpn_strom_bleibt_gedrosselt(self):
        view, gesehen = self._view()
        for w in range(20):
            for m in _dekodiert(_nrpn_folge(5, w << 7, mit_lsb=False)):
                view._on_midi_msg(m)
        self.assertEqual(sum(m.msg_type == "nrpn" for m in gesehen), 1)


if __name__ == "__main__":
    unittest.main()
