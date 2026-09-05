"""FM-9-Rest — der MIDI-„Programmer Attribut"-Regler kennt jetzt die Auswahl.

Zwei Dinge waren kaputt, das zweite ist das groebere:

1. Er kannte die **Kopf**-Auswahl nicht — „Kopf 2" gewaehlt, und trotzdem
   reagierten alle vier Koepfe (dieselbe Luecke wie beim XY-Pad, FM-9/A5).
2. Er kannte die Auswahl **ueberhaupt nicht**: geschrieben wurde stur auf
   ``get_patched_fixtures()``, also auf JEDES gepatchte Geraet. Ein mit
   „Programmer Attribut" beschrifteter Fader, der 30 Geraete anfasst obwohl zwei
   gewaehlt sind, ist auf keinem Lichtpult das erwartete Verhalten.

★ Der interessante Teil ist die Kopf-ZAEHLUNG. Sie haengt am **Attribut**, nicht
am Geraet: eine ``HYDRABEAM 4000 RGBW [19-Kanal]`` hat 4 Pan, 4 Tilt, **5
Intensity-KANAELE** (Master + je Kopf einer) und **1** Farbbank. „Wie viele
Koepfe hat das Geraet" hat dort also mehrere richtige Antworten.
``AttributBezogeneZaehlungTests`` faehrt genau dieses Geraet und zeigt, dass ein
Pan-Schreibvorgang die Kopf-Auswahl behaelt, ein Farb-Schreibvorgang auf
demselben Geraet sie aber fallen lassen muss.

★★ Seit FM-27/29 (2026-08-24) zaehlt ``attr_head_count_for_channels`` KOEPFE
statt Vorkommen: die 5 Intensity-Kanaele sind **4** Koepfe plus ein geteilter
Master (die Kopf-Karte aus FM-17 weiss das), und ein Attribut, das das Geraet
gar nicht hat, ist **0** Koepfe statt 1. ``ZaehlerTests`` misst beides.
"""
import unittest

from src.core import app_state as A
from src.core.midi import midi_mapper as mm


class _Ch:
    def __init__(self, attribute):
        self.attribute = attribute


class _Fx:
    def __init__(self, fid, channels):
        self.fid = fid
        self.channels = channels
        self.fixture_type = ""


def _hydrabeam19(fid):
    """Der reale Library-Fall: 4 Pan, 4 Tilt, 5 Intensity, 1 Farbbank."""
    ch = []
    for _ in range(4):
        ch += [_Ch("pan"), _Ch("tilt"), _Ch("intensity")]
    ch += [_Ch("intensity")]                       # gemeinsamer Master-Dimmer
    ch += [_Ch("color_r"), _Ch("color_g"), _Ch("color_b"), _Ch("color_w")]
    return _Fx(fid, ch)


def _par(fid):
    ch = [_Ch("intensity"), _Ch("color_r"), _Ch("color_g"), _Ch("color_b")]
    return _Fx(fid, ch)


class _State:
    def __init__(self, fixtures, cells=()):
        self._fx = list(fixtures)
        self._cells = list(cells)
        self.writes = []

    def get_patched_fixtures(self):
        return list(self._fx)

    def get_selected_cells(self):
        return list(self._cells)

    def get_selected_fids(self):
        from src.core.group_cells import base_fids_in_cells
        return base_fids_in_cells(self._cells)

    def set_programmer_value(self, fid, attribute, value, undoable=False, head=0):
        key = attribute if not head else f"{attribute}#{int(head)}"
        self.writes.append((fid, key, value))

    def validate_head_restrictions(self, heads, *, count_heads=None):
        return A.AppState.validate_head_restrictions(self, heads,
                                                     count_heads=count_heads)

    def fids_ohne_bedienbaren_kopf(self, heads, *, count_heads=None):
        return A.AppState.fids_ohne_bedienbaren_kopf(
            self, heads, count_heads=count_heads)

    def _head_restrictions_geprueft(self, heads, count_heads=None):
        return A.AppState._head_restrictions_geprueft(
            self, heads, count_heads)

    def nur_bedienbare_fids(self, fids, heads, *, count_heads=None):
        # FM-45/2 — wie die Schwester darueber an die ECHTE Regel
        # delegiert. Die GANZE Kette, nicht nur der Einstieg: die
        # Methode ruft intern `self.fids_ohne_bedienbaren_kopf`, und
        # eine Attrappe, der die fehlt, laesst den Aufrufer in seinen
        # `except`-Zweig laufen statt zu delegieren.
        return A.AppState.nur_bedienbare_fids(
            self, fids, heads, count_heads=count_heads)

    # vom Mapper beruehrt, aber hier ohne Bedeutung
    playback_engine = None
    output_manager = None
    function_manager = None


def _mapper(test, state):
    """Mapper mit Fake-State — und ``get_channels_for_patched`` auf die
    Fake-Fixtures umgelenkt."""
    orig_mm, orig_ch = mm.get_midi_manager, A.get_channels_for_patched

    class _NoMidi:
        def subscribe(self, cb):
            pass

        def send_note(self, *a, **k):
            pass

        def send_cc(self, *a, **k):
            pass

        def open_output(self, *a, **k):
            pass

        def current_output_name(self):
            return ""

    mm.get_midi_manager = lambda: _NoMidi()
    A.get_channels_for_patched = lambda fx: list(getattr(fx, "channels", []))
    m = mm.MidiMapper(state)

    def _restore():
        try:
            m.close()
        except Exception:
            pass
        mm.get_midi_manager = orig_mm
        A.get_channels_for_patched = orig_ch

    test.addCleanup(_restore)
    return m


def _fire(m, attr, value=1.0):
    m._execute_continuous(
        mm.MidiMapping(name="x", msg_type="control_change", channel=1, data1=7,
                       action=mm.ACTION_PROGRAMMER_VAL, param=attr),
        value)


def _keys(state, fid):
    return sorted({k for f, k, _v in state.writes if f == fid})


def _fids(state):
    return sorted({f for f, _k, _v in state.writes})


class ReichweiteTests(unittest.TestCase):
    def test_ohne_auswahl_weiterhin_alle_gepatchten(self):
        """Der Alt-Fall muss byte-identisch bleiben: wer den Fader als globalen
        Attribut-Regler benutzt und nichts selektiert, merkt keinen Unterschied."""
        st = _State([_par(1), _par(2), _par(3)])
        _fire(_mapper(self, st), "intensity")
        self.assertEqual(_fids(st), [1, 2, 3])
        self.assertEqual(_keys(st, 1), ["intensity"])

    def test_mit_auswahl_nur_die_gewaehlten(self):
        st = _State([_par(1), _par(2), _par(3)], cells=["2"])
        _fire(_mapper(self, st), "intensity")
        self.assertEqual(_fids(st), [2],
                         "ein 'Programmer Attribut'-Fader darf nicht 3 Geraete "
                         "anfassen, wenn eines gewaehlt ist")

    def test_leere_patchliste_schreibt_nichts(self):
        st = _State([])
        _fire(_mapper(self, st), "intensity")
        self.assertEqual(st.writes, [])


class KopfAuswahlTests(unittest.TestCase):
    def test_gewaehlter_kopf_bekommt_nur_seinen_kanal(self):
        st = _State([_hydrabeam19(1)], cells=["1:2"])
        _fire(_mapper(self, st), "pan")
        self.assertEqual(_keys(st, 1), ["pan#2"])

    def test_ganzes_geraet_schlaegt_kopf_zellen(self):
        st = _State([_hydrabeam19(1)], cells=["1", "1:2"])
        _fire(_mapper(self, st), "pan")
        self.assertEqual(_keys(st, 1), ["pan"])

    def test_alle_koepfe_gewaehlt_ist_das_ganze_geraet(self):
        st = _State([_hydrabeam19(1)], cells=["1:0", "1:1", "1:2", "1:3"])
        _fire(_mapper(self, st), "pan")
        self.assertEqual(_keys(st, 1), ["pan"])


class AttributBezogeneZaehlungTests(unittest.TestCase):
    """★ Dasselbe Geraet, dieselbe Auswahl — aber je nach geschriebenem Attribut
    muss die Kopf-Einschraenkung greifen oder fallen."""

    def test_pan_behaelt_die_kopf_auswahl(self):
        st = _State([_hydrabeam19(1)], cells=["1:2"])
        _fire(_mapper(self, st), "pan")
        self.assertEqual(_keys(st, 1), ["pan#2"], "4 Pan-Kanaele -> Kopf 3 gibt es")

    def test_farbe_faellt_auf_geraeteweit_zurueck(self):
        st = _State([_hydrabeam19(1)], cells=["1:2"])
        _fire(_mapper(self, st), "color_r")
        self.assertEqual(
            _keys(st, 1), ["color_r"],
            "nur EINE Farbbank -> 'color_r#2' waere ein Schluessel ohne Kanal, "
            "und der Kopf fiele auf seinen Default-Wert")

    def test_intensity_hat_wieder_eine_andere_kopfzahl(self):
        """5 Intensity-KANAELE (4 pro Kopf + 1 Master) = 4 Koepfe — Kopf 3 gibt
        es also, und er adressiert seinen eigenen Dimmer."""
        st = _State([_hydrabeam19(1)], cells=["1:2"])
        _fire(_mapper(self, st), "intensity")
        self.assertEqual(_keys(st, 1), ["intensity#2"])


class ZaehlerTests(unittest.TestCase):
    def test_zaehlt_koepfe_nicht_vorkommen(self):
        """★ FM-29: die 5 Intensity-Kanaele der Hydrabeam sind **4** Koepfe plus
        ein geteilter Master. Wer hier 5 antwortet, laesst die Kopf-Zelle ``1:4``
        einen fuenften Regler bauen, der auf denselben Kanal wie „K4" schreibt."""
        fx = _hydrabeam19(1)
        n = A.attr_head_count_for_channels
        self.assertEqual(n(fx, fx.channels, "pan"), 4)
        self.assertEqual(n(fx, fx.channels, "tilt"), 4)
        self.assertEqual(n(fx, fx.channels, "intensity"), 4)
        self.assertEqual(n(fx, fx.channels, "color_r"), 1)

    def test_fehlendes_attribut_ist_null_koepfe(self):
        """★ FM-27: ``1`` hiess „hat Kopf 1" und liess ein Geraet ohne diesen
        Kanal im Regler stehen — der Wert landete dann nirgends auf DMX."""
        fx = _hydrabeam19(1)
        self.assertEqual(A.attr_head_count_for_channels(fx, fx.channels, "gobo"), 0)

    def test_raw_ist_kein_kopf_attribut(self):
        """★ FM-28: die Vorkommen von ``raw`` sind verschiedene Funktionen, keine
        Koepfe — geraeteweit ist die einzige richtige Antwort."""
        fx = _Fx(1, [_Ch("raw") for _ in range(20)] + [_Ch("pan"), _Ch("pan")])
        self.assertEqual(A.attr_head_count_for_channels(fx, fx.channels, "raw"), 1)
        self.assertFalse(A.attr_has_head_axis("raw"))
        self.assertTrue(A.attr_has_head_axis("pan"))

    def test_composite_key_wird_auf_den_basisnamen_reduziert(self):
        """Snap-/VC-Restore-Pfade reichen ``attr#N`` direkt durch."""
        fx = _hydrabeam19(1)
        self.assertEqual(A.attr_head_count_for_channels(fx, fx.channels, "pan#2"), 4)

    def test_leeres_attribut_und_kaputte_kanaele_werfen_nicht(self):
        fx = _hydrabeam19(1)
        self.assertEqual(A.attr_head_count_for_channels(fx, fx.channels, ""), 1)
        self.assertEqual(A.attr_head_count_for_channels(fx, None, "pan"), 1)


if __name__ == "__main__":
    unittest.main()
