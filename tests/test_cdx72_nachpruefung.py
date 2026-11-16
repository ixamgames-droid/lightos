"""CDX-72, Nachpruefung: Motorfader OHNE Beruehrungssensor beim Bankwechsel.

Schiebt die Hand den Pult-Fader und wird dabei die Bank gewechselt, ging die
Eingabe an den Fader der verlassenen Bank. Der Fader der neuen Bank kannte
keine Hand und fuhr sofort (erzwungen) auf seinen Wert — gegen die Hand. Die
Flaeche merkt sich jetzt auch die letzte Fader-Eingabe je Pitchbend-Kanal;
der neue Fader wartet die Hand-Ruhe ab und traegt danach nach.
"""
from __future__ import annotations

from test_cdx72_vc_codex_ernte import (  # noqa: F401  (Fixture mm)
    _canvas_zwei_banken, _note, _pb, _w14, mm)

from src.core.midi.midi_mapper import MOTOR_HAND_RUHE_S


def _abbauen(c):
    c._teardown_midi()
    c._teardown_keyboard()
    c.deleteLater()


def test_ohne_sensor_bankwechsel_waehrend_die_hand_schiebt(mm):
    c, a, b, _ua, ub = _canvas_zwei_banken(mm)
    try:
        c._handle_midi(_pb(2, 5000))          # Hand schiebt Fader 2 (Bank 0)
        mm.pb.clear()
        c.set_active_bank(1)
        assert mm.pb == [], "der Motor darf nicht gegen die schiebende Hand fahren"
        assert b._motor.wartet
        ub.t += MOTOR_HAND_RUHE_S + 0.05      # Hand ruht
        b._motor_nachtrag()
        assert mm.pb == [(2, _w14(200))], "nach der Ruhe auf den Wert der neuen Bank"
    finally:
        _abbauen(c)


def test_ohne_sensor_alte_eingabe_haelt_nicht_auf(mm):
    c, a, b, _ua, _ub = _canvas_zwei_banken(mm)
    try:
        c._handle_midi(_pb(2, 5000))
        c._motor_hand[2] -= MOTOR_HAND_RUHE_S + 0.1   # lange her
        mm.pb.clear()
        c.set_active_bank(1)
        assert mm.pb == [(2, _w14(200))]
    finally:
        _abbauen(c)


def test_andere_kanal_eingabe_haelt_nicht_auf(mm):
    c, a, b, _ua, _ub = _canvas_zwei_banken(mm)
    try:
        c._handle_midi(_pb(3, 5000))          # anderer Pult-Fader
        mm.pb.clear()
        c.set_active_bank(1)
        assert mm.pb == [(2, _w14(200))]
    finally:
        _abbauen(c)


def test_mit_sensor_zurueck_auf_die_alte_bank(mm):
    c, a, b, _ua, _ub = _canvas_zwei_banken(mm)
    try:
        c._handle_midi(_note(1, 105, 127))
        c.set_active_bank(1)
        mm.pb.clear()
        c.set_active_bank(0)
        assert mm.pb == []
        c._handle_midi(_note(1, 105, 0))
        assert mm.pb == [(2, _w14(40))]
    finally:
        _abbauen(c)


# ── Cueliste: Seitenwechsel WAEHREND der Rueckfrage ─────────────────────────

def test_cueliste_seitenwechsel_waehrend_rueckfrage_springt_nicht(monkeypatch):
    from test_cdx72_vc_codex_ernte import _cue, _cueliste
    w, pe, s1, s2 = _cueliste(monkeypatch)
    s2.cues[0] = _cue(2, "Andere Zwei")          # gleiche Nummer auf Seite 2
    w._refresh()
    item = w._cue_list.item(1)                    # „2 Strophe" auf Seite 1

    def frage(_text):
        pe.current_page = 1                       # Pult blaettert, Dialog offen
        return True
    monkeypatch.setattr(w, "_bestaetige_sprung", frage)
    w._on_cue_double(item)
    assert s1.sprung == [] and s2.sprung == []
    assert "Andere Zwei" in w._cue_list.item(0).text(), "Liste zeigt die neue Seite"


def test_cueliste_ohne_seitenwechsel_springt_richtig(monkeypatch):
    from test_cdx72_vc_codex_ernte import _cueliste
    w, pe, s1, _s2 = _cueliste(monkeypatch)
    w._refresh()
    monkeypatch.setattr(w, "_bestaetige_sprung", lambda _t: True)
    w._on_cue_double(w._cue_list.item(1))
    assert s1.sprung == [2.0]
